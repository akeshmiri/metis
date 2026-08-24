"""
CLI for the MBT engine (application spec §9.4, first slice).

    python3 -m metis_mcp.mbt.cli paths    <model.json> [--criterion C] [--max-setup N]
    python3 -m metis_mcp.mbt.cli render   <model.json> [--criterion C]
    python3 -m metis_mcp.mbt.cli report   <model.json> [--criterion C]
    python3 -m metis_mcp.mbt.cli payload  <model.json> [--criterion C]

This is the seed of §9.4's command set, scoped to what stage 1 of N-16 needs: a
model in, paths/cases/coverage out. It reads a model from a JSON file rather than
the graph -- the loader arrives with extraction (§5), and keeping the engine
database-free is what makes it verifiable now (see mbt/model.py).

No command here writes anything external. Publication is gated (T-18) and is not
part of this slice.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path as FsPath

from metis_mcp.mbt.coverage import ComponentRef, build_ledger, format_report
from metis_mcp.mbt.criteria import DEFAULT_CRITERION, criterion_names
from metis_mcp.mbt.model import QUARANTINE, Model, State, Transition
from metis_mcp.mbt.path_generation import DEFAULT_SETUP_CAP, generate
from metis_mcp.mbt.test_levels import (
    format_grades, from_pack as inventory_from_pack, grade_transitions,
)
from metis_mcp.mbt.validation import (
    ValidationFailed, format_validation, require_valid, validate,
)
from metis_mcp.rendering import build_payload, format_case, render
from metis_mcp.review import ReviewFile, apply, export, format_audit
from metis_mcp.review.roles import (
    CONFIRM_PUBLICATION, PUBLISHER, ROLES, Identity, NotPermitted, require,
)
from metis_mcp.reconciliation import (
    AcceptanceCriterion, format_reconciliation, prefilter, reconcile,
)
from metis_mcp.reconciliation.matching import CODE_DERIVED, HUMAN_CONFIRMED
# The ontology gate for a partial `SET`. Deliberately not named `validate`:
# that name in this module is already the *model* validator (M-18), and giving
# two different checks one name is how a write skips the one that applies to it.
from metis_mcp.ontology.validation import validate_update
from metis_mcp.mbt.cross_surface import (
    InvokesLink, LinkSet, divergences, format_divergences,
)
from metis_mcp.review.state import (
    OverlayResult, ReviewState, default_state_path, overlay, record, summarise,
    source_fingerprint,
)
from metis_mcp.mbt.graph_loader import (
    load_component, load_from_graph, load_inherited_guards, load_validating_criteria,
)
from metis_mcp.mbt.graph_session import GraphNotConfigured, session
from metis_mcp.mbt.graph_writer import GENERATOR_VERSION, persist, plan_persist
from metis_mcp.model_sources import availability, get as get_source, land, plan_landing
from metis_mcp.specgen import build as build_spec, dated_export, living_page
from metis_mcp.specgen import writeback as spec_writeback
from metis_mcp.publishing import (
    AFFIRMATIVE, ConfirmationRefused, DryRunTransport, PublicationLedger, compare, confirm,
    default_ledger_path, format_batch, format_drift, plan_publication, publish,
    record_generation,
)
from metis_mcp.overrides import (
    CLASSIFICATIONS, OPERATIONS, STATE, TRANSITION,
    OverrideLog, OverrideRefused, apply_overrides, check_staleness, default_log_path,
    density, findings, format_overrides, plan_override,
)


def read_source(path: str) -> Model:
    """The model exactly as a source emitted it — no edits, no decisions.

    Kept separate because E-8's staleness check must compare an override against
    the *machine* value. Reading a model that already has overrides applied would
    compare an edit to itself and never report staleness.

    Source shape:
        {"id": "login-api",
         "states": [{"id": "...", "name": "...", "surface": "api", "is_initial": true}],
         "transitions": [{"id": "...", "source": "...", "trigger": "...",
                          "target": "...", "guard": "...",
                          "implementation_status": "implemented"}]}
    """
    data = json.loads(FsPath(path).read_text())
    # Lifecycle is NOT read from the source: it is a human fact and lives in the
    # review-state file. Everything a source emits starts at Quarantine (spec S-4).
    states = {
        s["id"]: State(
            id=s["id"], name=s.get("name", s["id"]),
            surface=s.get("surface", "api"), is_initial=bool(s.get("is_initial", False)),
            lifecycle_state=QUARANTINE,
        )
        for s in data["states"]
    }
    transitions = {
        t["id"]: Transition(
            id=t["id"], source=t["source"], trigger=t["trigger"], target=t["target"],
            guard=t.get("guard", ""),
            implementation_status=t.get("implementation_status", "implemented"),
            lifecycle_state=QUARANTINE,
            # Carried across the file boundary. Dropping unknown keys here meant
            # a model written by extraction and read back lost everything the
            # pack had recovered about what a caller must send.
            outcome_status=t.get("outcome_status"),
            guard_anchor=t.get("guard_anchor", ""),
            source_state_unresolved=bool(t.get("source_state_unresolved", False)),
            inputs=tuple(t.get("inputs", ()) or ()),
            security=tuple(t.get("security", ()) or ()),
        )
        for t in data["transitions"]
    }
    return Model(id=data["id"], states=states, transitions=transitions)


def load_model(path: str, state_path: str | None = None,
               override_path: str | None = None) -> tuple[Model, OverlayResult]:
    """Read a model source, layer overrides on it, then overlay durable review state.

    Three files, three owners (spec I-14, E-1): the source holds machine facts and
    is replaced by re-extraction; the override log holds human *edits*; the review
    state holds human *decisions*. Neither human file is touched by re-extraction.

    **Order matters and is deliberate.** Overrides are applied *before* the review
    overlay, so the fingerprint a decision binds to is taken over the model as the
    reviewer actually saw it. That also delivers E-11 without a special case: an
    edit changes the fingerprint, so decisions recorded before the edit read stale
    and are not applied, and the edited element stays at Quarantine.

    Disclosed bluntness: the fingerprint covers the whole model, so one edit
    stales every prior decision, not merely the edited element's. That is stricter
    than E-11 and E-13 require. It is left strict rather than narrowed, because
    N-14 is the stronger rule -- a decision made against different evidence must
    not be applied -- and narrowing it would need per-element fingerprints, which
    is a change to the review format, not to this function.

    Where the source has moved since the decisions were made, the overlay reports
    **stale** and is not applied -- the caller decides, nothing is silently
    carried forward.

    Source shape:
        {"id": "login-api",
         "states": [{"id": "...", "name": "...", "surface": "api", "is_initial": true}],
         "transitions": [{"id": "...", "source": "...", "trigger": "...",
                          "target": "...", "guard": "...",
                          "implementation_status": "implemented"}]}
    """
    model = read_source(path)

    log_file = FsPath(override_path) if override_path else default_log_path(path)
    log = OverrideLog.load(log_file)
    if log.entries:
        model = apply_overrides(model, log).model

    state_file = FsPath(state_path) if state_path else default_state_path(path)
    return model, overlay(model, ReviewState.load(state_file))


class ApprovalRequired(Exception):
    """Raised when generation is attempted on a model that is not approved (G1)."""


def _require_approved(model: Model) -> None:
    """Spec G1: a model must be approved before anything is generated from it.

    Reports *which* elements are outstanding, not merely that some are -- a
    reviewer cannot act on a count.
    """
    outstanding = model.unapproved_elements()
    if not outstanding:
        return
    lines = [
        f"{model.id} is not approved — {len(outstanding)} element(s) awaiting review.",
        "Generating from an unreviewed model would produce confidently wrong tests.",
        "",
    ]
    for kind, element_id, state in outstanding[:12]:
        lines.append(f"    {kind:<11} {element_id:<26} {state}")
    if len(outstanding) > 12:
        lines.append(f"    ... and {len(outstanding) - 12} more")
    lines += [
        "",
        "  Review them:  python3 -m metis_mcp.mbt.cli review export <model> -o review.json",
        "  Then apply:   python3 -m metis_mcp.mbt.cli review apply review.json --model <model>",
    ]
    raise ApprovalRequired("\n".join(lines))


CRITERIA_CYPHER = """
MATCH (a:AcceptanceCriterion)-[:VALIDATES]->(t:Transition|ApiCall|UiAction)
WHERE $journey IN t.functional_areas
RETURN t.id AS transition, a.id AS criterion_id, a.text AS text
"""


def _criteria_from_graph(args) -> dict[str, tuple[str, str]]:
    """`{transition_id: (criterion_id, text)}` for the review export (S-19)."""
    if not getattr(args, "journey", None):
        return {}
    try:
        with session(getattr(args, "uri", None), getattr(args, "user", None)) as s:
            return {r["transition"]: (r["criterion_id"], r["text"] or "")
                    for r in s.run(CRITERIA_CYPHER, journey=args.journey)}
    except GraphNotConfigured:
        return {}


PROPOSERS_CYPHER = """
MATCH (n)
WHERE ($journey IN n.functional_areas) AND (n:State OR n:Transition OR n:ApiCall OR n:UiAction)
MATCH (e:Episode {id: n.source_episode_id})
RETURN n.id AS element_id, e.proposed_by AS proposed_by
"""


def _proposers_from_graph(args) -> dict[str, str]:
    """`{element_id: proposed_by}` for N-10, joined through the Episode.

    The file-based path takes this from the override log, which is why the gate
    only ever fired on hand-edited elements. A landed model's proposer lives on
    its Episode -- the provenance record every node already points at -- so no
    new property on `State` or `Transition` is needed to make N-10 real.
    """
    if not getattr(args, "journey", None):
        return {}
    try:
        with session(getattr(args, "uri", None), getattr(args, "user", None)) as s:
            return {r["element_id"]: r["proposed_by"]
                    for r in s.run(PROPOSERS_CYPHER, journey=args.journey)
                    if r["proposed_by"]}
    except GraphNotConfigured:
        return {}


GRAPH_CRITERIA_CYPHER = """
MATCH (a:AcceptanceCriterion)-[:VALIDATES]->(t:Transition|ApiCall|UiAction)
WHERE $journey IN t.functional_areas
RETURN DISTINCT a.id AS id, a.text AS text,
       coalesce(a.provenance, 'code_derived') AS provenance
"""


def _graph_confirmed(args) -> list:
    """The `VALIDATES` edges, as the confirmed matches they are (spec X-18).

    A `VALIDATES` edge exists only because a human confirmed the match, so it is
    precisely what `reconcile` means by `confirmed`. Passing an empty list
    instead -- which this verb did -- made every already-matched criterion report
    as *unimplemented* and every already-covered transition as *unspecified*: a
    report that contradicted the graph it was reading from, in the alarming
    direction.
    """
    from metis_mcp.reconciliation.matching import ConfirmedMatch

    if not getattr(args, "journey", None):
        return []
    try:
        with session(getattr(args, "uri", None), getattr(args, "user", None)) as s:
            return [ConfirmedMatch(
                        ac_id=r["ac_id"], transition_id=r["transition_id"],
                        confirmed_by=r["confirmed_by"] or "unknown",
                        provenance=r["provenance"])
                    for r in s.run(GRAPH_CONFIRMED_CYPHER, journey=args.journey)]
    except GraphNotConfigured:
        return []


GRAPH_CONFIRMED_CYPHER = """
MATCH (a:AcceptanceCriterion)-[v:VALIDATES]->(t:Transition|ApiCall|UiAction)
WHERE $journey IN t.functional_areas
RETURN a.id AS ac_id, t.id AS transition_id,
       coalesce(v.confirmed_by, '') AS confirmed_by,
       coalesce(a.provenance, 'code_derived') AS provenance
"""


def _graph_criteria(args) -> list:
    """Acceptance criteria for this journey, carrying their S-19 grade.

    **Scoped through `VALIDATES`, and that is a real limitation worth stating.**
    An `AcceptanceCriterion` records no journey or functional area of its own, so
    the only link between a criterion and a scope is a confirmed match to a
    transition in it. That means this returns the criteria already matched and
    cannot see one that belongs to this journey but has never been linked --
    exactly the "criteria with no transition" direction F-4 asks about.

    Reporting the limit is the honest option. The alternative -- returning every
    criterion in the graph -- would have reconciled all 66 of the pilot estate's
    criteria against one six-transition service and called 60 of them
    unimplemented, which is a fabricated finding, not a wider search.
    """
    if not getattr(args, "journey", None):
        return []
    try:
        with session(getattr(args, "uri", None), getattr(args, "user", None)) as s:
            return [AcceptanceCriterion(id=r["id"], text=r["text"] or "",
                                        provenance=r["provenance"])
                    for r in s.run(GRAPH_CRITERIA_CYPHER, journey=args.journey)]
    except GraphNotConfigured:
        return []


def _inherited_from_graph(args) -> dict[str, str] | None:
    """Guards a UI model borrows across INVOKES (M-5c).

    Without this a UI model validated from the graph reads as ambiguous exactly
    where the API side determines it -- the CLI had the edges available and was
    not using them.
    """
    if not getattr(args, "journey", None):
        return None
    try:
        with session(getattr(args, "uri", None), getattr(args, "user", None)) as s:
            return load_inherited_guards(s, args.journey)
    except GraphNotConfigured:
        return None


def _coverage_context(args) -> tuple[ComponentRef | None, dict[str, list[str]] | None]:
    """P-16's version, and the criteria a coverage figure is about.

    Two sources, in the order the caller actually knows them:

      * `--journey` reads the real `Component` and the real `VALIDATES` edges
        from the graph;
      * a file-based run has neither, so `--commit`/`--version` name the version
        explicitly and there are no criteria to load.

    Returns `(None, None)` when neither is available. That is a reported state,
    not a swallowed one -- `format_report` prints "not recorded for this run"
    rather than a figure that quietly names no version.
    """
    if getattr(args, "journey", None):
        try:
            with session(getattr(args, "uri", None), getattr(args, "user", None)) as s:
                surface = getattr(args, "surface", "api")
                return (load_component(s, args.journey, surface),
                        load_validating_criteria(s, args.journey, surface))
        except GraphNotConfigured:
            return None, None

    commit = getattr(args, "commit", "") or ""
    version = getattr(args, "version", "") or ""
    if not commit and not version:
        return None, None
    model_id = getattr(args, "model", "") or ""
    return ComponentRef(
        id=f"cli:{model_id}:{commit or version}",
        component=FsPath(model_id).stem if model_id else "model",
        version=str(version),
        commit_sha=str(commit),
    ), None


def _ledger(args, model: Model, result, test_case_ids: dict[str, str] | None = None):
    """A ledger that always knows what P-16 asks it to state."""
    component, criteria = _coverage_context(args)
    return build_ledger(model, result, test_case_ids,
                        component=component, validating_criteria=criteria)


def _load_from_graph(args) -> Model:
    """Load a model from the graph.

    Lifecycle lives in the graph itself (spec §8.6), so there is no review-state
    overlay to apply -- decisions were written there by `review apply --graph`.
    """
    with session(getattr(args, "uri", None), getattr(args, "user", None)) as s:
        report = load_from_graph(s, args.journey, args.surface)
    if report.skipped:
        print(f"NOTE: {len(report.skipped)} element(s) skipped while loading:")
        for element_id, reason in report.skipped[:5]:
            print(f"    {element_id}: {reason}")
    return report.model


def _load(args) -> Model:
    """Load source + review state, refusing to proceed on a stale overlay."""
    if getattr(args, "journey", None):
        return _load_from_graph(args)
    if not getattr(args, "model", None):
        raise ApprovalRequired(
            "no model given. Provide a model file, or --journey/--surface to read "
            "from the graph."
        )
    model, overlay_result = load_model(args.model, getattr(args, "state", None),
                                       getattr(args, "overrides", None))
    if overlay_result.stale:
        raise ApprovalRequired(
            f"{model.id}: the model source has changed since its review decisions "
            f"were made (decided against {overlay_result.recorded_fingerprint}, "
            f"source is now {overlay_result.current_fingerprint}).\n"
            f"Decisions are retained, not discarded — but they are not applied "
            f"until re-reviewed against the current source (spec E-8).\n\n"
            f"  Re-export:  python3 -m metis_mcp.mbt.cli review export {args.model} -o review.json"
        )
    return model


def _grades(args, model: Model):
    """Existing-coverage grades, when an inventory is supplied (REQ-METIS-PG-01).

    Absent an inventory this returns None and generation behaves exactly as
    before -- additive generation is opt-in, because claiming a transition is
    covered without evidence would be worse than generating a duplicate.
    """
    path = getattr(args, "inventory", None)
    if not path:
        return None
    inventory = inventory_from_pack(json.loads(FsPath(path).read_text()))
    return grade_transitions(model, inventory)


def cmd_coverage_gap(args) -> int:
    """What already covers this model, and what would still be generated."""
    model = _load(args)
    grades = _grades(args, model)
    if grades is None:
        print("No inventory given. Pass --inventory <jvm-test-inventory.json> to "
              "see what existing tests already cover (REQ-METIS-PG-01).")
        return 1
    print(format_grades(grades, model))
    return 0


def _generate(args) -> tuple[Model, object]:
    """Stage 3 then stage 5 (spec §3.2), in that order and both blocking.

    Validation runs **before** the approval gate deliberately: G1 shows validation
    findings as evidence to the reviewer (§3.4), so a model that cannot be
    well-formed should never reach a decision screen at all. Until this call
    existed, approval was gated and well-formedness was not -- a model could be
    approved and still be non-deterministic, and paths generated from it anyway.
    """
    model = _load(args)
    require_valid(model, allow_unverifiable=getattr(args, "allow_unverifiable", False),
                  inherited=_inherited_from_graph(args))
    _require_approved(model)
    result = generate(model, args.criterion, args.max_setup, grades=_grades(args, model))
    return model, result


def _rendered(args):
    """Everything publication needs: the model, its cases, and the ledger."""
    model, result = _generate(args)
    cases = render(model, result.paths).cases
    ledger_path = (FsPath(args.ledger) if args.ledger
                   else default_ledger_path(args.model or model.id))
    ledger = PublicationLedger.load(ledger_path)
    if not ledger.model_id:
        ledger.model_id = model.id
    return model, cases, ledger, ledger_path


def cmd_drift(args) -> int:
    """Spec §7.6: what changed, and whether the model or a human changed it."""
    _, cases, ledger, _ = _rendered(args)
    print(format_drift(compare(cases, ledger)))
    return 0


def cmd_publish(args) -> int:
    """Spec §7.7. The single external-write path, behind a literal gate (T-18, T-20).

    Two invocations by design: the first shows the batch in full and sends
    nothing; the second carries `--confirm publish` and the batch size it was
    shown. Making confirmation a separate act is what stops it being reflexive.
    """
    _, cases, ledger, ledger_path = _rendered(args)
    report = compare(cases, ledger)
    batch = plan_publication(report, cases)

    print(format_drift(report))
    print()
    print(format_batch(batch))

    if not args.confirm:
        # The scope as it was actually given. `args.model` is None when
        # publishing from the graph (`--journey/--surface`), and interpolating
        # it printed `publish None --confirm publish` -- an instruction that
        # fails if a reader copies it, which is the only reason this line
        # exists.
        scope = (args.model if args.model
                 else f"--journey {args.journey} --surface {args.surface}")
        print("\nNothing was sent. Re-run with:")
        print(f"  ... publish {scope} --confirm {AFFIRMATIVE} "
              f"--batch-size {batch.size} --as <your-identity>")
        return 0

    # N-12/O-4b: publication is a separate capability from review, because it
    # writes outside Métis's control and is the least reversible action.
    try:
        identity = Identity(args.as_identity, args.role)
        require(identity, CONFIRM_PUBLICATION)
        confirmation = confirm(args.confirm, args.as_identity, args.batch_size)
    except (NotPermitted, ConfirmationRefused, ValueError) as e:
        print(f"\nREFUSED: {e}")
        return 1

    # T-21/C3: dry-run is the only transport registered in the first release.
    transport = DryRunTransport()
    result = publish(batch, transport, confirmation)

    if not result.ok:
        print(f"\nREFUSED: {result.refused}")
        return 1

    print(f"\n{len(result.sent)} operation(s) sent via {result.transport} "
          f"(dry run: {result.dry_run}), confirmed by {result.confirmed_by}.")

    # The baseline moves only now -- see drift.record_generation's docstring.
    record_generation(ledger, ledger.model_id, cases)
    ledger.save(ledger_path)
    print(f"Baseline updated -> {ledger_path}")
    return 0


def cmd_spec(args) -> int:
    """Spec §18: a stakeholder-readable rendering of the model.

    Deliberately does NOT require approval. §18's whole purpose is showing people
    what the model currently says, and SP-4 makes unapproved rules visible in the
    body -- so gating this on G1 would hide exactly the document a reviewer needs
    in order to decide. Validation findings are carried in as open questions.
    """
    model = _load(args)
    log_path = FsPath(args.overrides) if args.overrides else default_log_path(args.model or "")
    log = OverrideLog.load(log_path) if args.model else OverrideLog()

    coverage = ""
    try:
        # Not gated on approval: an unapproved model simply yields no paths, and
        # saying so is more useful to a reviewer than refusing to render at all.
        result = generate(model, DEFAULT_CRITERION, DEFAULT_SETUP_CAP)
        summary = _ledger(args, model, result).summary()
        total = summary["covered"] + summary["uncovered"]
        coverage = (f"{summary['covered']} of {total} transitions covered under the "
                    f"`{summary['criterion']}` criterion "
                    f"({summary['uncovered']} uncovered, "
                    f"{summary['indirect_only']} covered only indirectly).")
        if summary["covered"] == 0 and not model.is_approved:
            # A bare "0 of 17" would read as a quality statement. It is not: no
            # path can be generated from an unapproved model at all (D-10), so
            # zero here means "not yet generated", not "tested and failing".
            coverage += ("\n\nZero is not a measurement here: the model is not yet "
                         "approved, so no path can be generated from it (D-10). "
                         "Coverage becomes meaningful after review.")
    except (ValidationFailed, ApprovalRequired) as e:
        # P-4/A-17: never state a coverage figure without its criterion. If it
        # cannot be computed, say why rather than printing a number that is not one.
        # Deliberately narrow: a bare `except Exception` here swallowed a real
        # AttributeError during this build and printed "Not computed" over it.
        coverage = (f"Not computed — the model is blocked: "
                    f"{str(e).splitlines()[0]} No coverage figure is claimed.")

    spec = build_spec(
        model, validation=validate(model),
        override_density=density(model, log) if log.entries else None,
        model_version=args.version, commit=args.commit,
    )
    document = dated_export(spec, coverage) if args.dated else living_page(spec, coverage)

    if args.write_back:
        # §18.4 / T-18: an external write into a product repository. Same gate,
        # same single owner as test-case publication -- there is no second path.
        feature = args.feature or spec.journey
        plan = spec_writeback.plan_writeback(
            args.write_back, {feature: document},
            allow_unapproved=args.allow_unapproved, specs={feature: spec})
        print(spec_writeback.format_plan(plan))
        if not args.confirm:
            print(f"\nNothing was written. Re-run with --confirm {AFFIRMATIVE} "
                  f"--batch-size {plan.size} --as <your-identity>")
            return 0
        try:
            confirmation = confirm(args.confirm, args.as_identity, args.batch_size)
        except (ConfirmationRefused, ValueError) as e:
            print(f"\nREFUSED: {e}")
            return 1
        result = spec_writeback.apply(plan, confirmation)
        if not result["ok"]:
            print(f"\nREFUSED: {result['refused']}")
            return 1
        for path in result["written"]:
            print(f"  wrote {path}")
        return 0

    if args.land:
        # F-12: the graph is the interface consumers query. A specification that
        # exists only as a file has to be re-rendered by everyone who wants it
        # and cannot carry an edge to the behaviour it describes.
        from metis_mcp.mbt.graph_loader import load_component
        from metis_mcp.model_sources.landing import land
        from metis_mcp.specgen.documents import plan_spec_document

        journey = args.journey or spec.journey
        with session(args.uri, args.user) as s:
            component = load_component(s, journey, args.surface)
            if component is None:
                # P-16's absence, said plainly. A document DESCRIBING a component
                # that was never persisted would be an edge to nothing.
                print(f"REFUSED: no Component for {journey}-{args.surface}. "
                      f"Run `persist` first — a specification describes a "
                      f"component version, and none has been recorded (P-16).")
                return 1
            doc_plan = plan_spec_document(
                spec, component.id, args.episode, document.body, spec.content_hash)
            if not doc_plan.is_legal:
                print(f"REFUSED: {len(doc_plan.errors)} validation error(s) — "
                      f"nothing was written. First: {doc_plan.errors[0]}")
                return 1
            outcome = land(s, doc_plan)
        if not outcome.ok:
            print(f"REFUSED: {outcome.refused}")
            return 1
        print(f"Landed the specification: {outcome.nodes_written} node(s), "
              f"{outcome.edges_written} edge(s)")
        print(f"  document:  specdoc-{spec.model_id}")
        print(f"  describes: {component.id}")
        # From the plan, not from `len(spec.rules)`. A rule renders whether or
        # not a real AcceptanceCriterion validates its transition, so the two
        # numbers differ and only one of them is a fact about the graph.
        cited = sum(1 for e in doc_plan.edges if e.rel_type == "CITES")
        print(f"  cites:     {cited} acceptance criterion/criteria "
              f"(of {len(spec.rules)} rules rendered)")
        print("  lifecycle: Quarantine — generated is not agreed (S-4)")
        if outcome.unmatched:
            print(f"\n  UNMATCHED — {len(outcome.unmatched)} edge group(s) planned "
                  f"but not written:")
            for group, shortfall, why in outcome.unmatched:
                print(f"    {group}: {shortfall}")
                print(f"        {why}")
            return 1
        return 0

    if args.out:
        FsPath(args.out).write_text(document.body)
        print(f"Wrote {args.out} — {len(spec.rules)} rule(s), "
              f"{spec.unsettled} not approved, {len(spec.open_questions)} open question(s).")
    else:
        print(document.body)
    return 0


def cmd_ac_mine(args) -> int:
    """Spec §4.5: mine a model from acceptance criteria, deterministically."""
    from metis_mcp.model_sources.ac_mining import Criterion, format_mining, mine

    criteria = [Criterion(id=e["id"], text=e["text"],
                          requirement_id=e.get("requirement_id"))
                for e in json.loads(FsPath(args.criteria).read_text())]
    result = mine(criteria, model_id=args.model_id, surface=args.surface,
                  initial_state=args.initial_state)
    print(format_mining(result))

    if result.model is None:
        return 1
    if args.out:
        FsPath(args.out).write_text(json.dumps({
            "id": result.model.id,
            "states": [{"id": s.id, "name": s.name, "surface": s.surface,
                        "is_initial": s.is_initial}
                       for s in result.model.states.values()],
            "transitions": [{"id": t.id, "source": t.source, "trigger": t.trigger,
                             "target": t.target, "guard": t.guard,
                             "implementation_status": t.implementation_status}
                            for t in result.model.transitions.values()],
        }, indent=2))
        print(f"\nWrote {args.out} — everything at Quarantine (S-4).")
    return 0


def cmd_doctor(args) -> int:
    """Is this machine able to finish an extraction? (X-3)

    Run before the slow path, not inside it: a CPG build is minutes long, and
    every reason it fails here is a reason it would have failed there — with
    the failure buried in engine output instead of stated up front.
    """
    from code_analysis.engine import preflight

    result = preflight(check_engine_version=not getattr(args, "fast", False))
    print(result.describe())
    from code_analysis.project_profile import list_profiles, profiles_dir

    known = list_profiles()
    print(f"\n  profiles in {profiles_dir()}: {', '.join(known) or 'none'}")

    if getattr(args, "repo", None):
        from code_analysis.project_profile import (
            ProfileInvalid, ProfileMissing, format_profile, load_for,
        )
        print()
        try:
            profile = load_for(args.repo, getattr(args, "project", "") or "")
            print(format_profile(profile))
            for note in profile.notes:
                print(f"  note: {note}")
        except (ProfileMissing, ProfileInvalid) as e:
            print(f"  [FAIL] profile            {e}")
            return 1
    return 0 if result.ok else 1


def cmd_init(args) -> int:
    """Scaffold `.metis/project.json` inside the target repository.

    What is mechanically knowable is filled in; every judgement is left marked
    REPLACE, the way `.metis/config.yaml` already does. A plausible default for
    a judgement is worse than a marker, because nobody revisits it.
    """
    import json

    from code_analysis.project_profile import (
        profile_path, profiles_dir, project_name_for, scaffold,
    )

    name = args.project or project_name_for(args.repo)
    target = profile_path(name)
    if target.exists() and not args.force:
        print(f"{target} already exists. Pass --force to overwrite it — but read "
              f"it first: it is the only place your layout is written down.")
        return 1
    document = scaffold(args.repo, project=name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2) + "\n")
    markers = sum(1 for line in json.dumps(document).split('"')
                  if line.startswith("REPLACE: "))
    print(f"wrote {target}")
    print(f"  describes: {document['repo']}")
    print(f"  detected: language={document['language']}, "
          f"{len(document['journeys'][0]['modules'])} module(s)")
    print(f"  {markers} judgement(s) marked REPLACE — fill them in before "
          f"`metis analyse`")
    return 0


def cmd_analyse(args) -> int:
    """Repository -> approval gate, in one command (§3.2).

    A thin front end over `workflow run model-build`: it resolves the profile,
    runs the engine (or reuses the cache) and hands the reports to the same
    pipeline the CLI has always run. `workflow/stages.py` stays the single place
    that knows the order — a second pipeline here would be a second order to
    keep in step.
    """
    from code_analysis.engine import EngineUnavailable, extract
    from code_analysis.project_profile import (
        ProfileInvalid, ProfileMissing, load_for,
    )

    try:
        profile = load_for(args.repo, args.project or "")
        journey = profile.journey(args.journey or "", args.surface or "")
    except (ProfileMissing, ProfileInvalid) as e:
        print(f"REFUSED: {e}")
        return 1
    for note in profile.notes:
        print(f"  note: {note}")

    # **X-4, and it was not being checked here.** `analyse` took the profile's
    # language to build a CPG and never asked whether the framework it declares
    # is one extraction supports. Against an undeclared one the packs recover
    # nothing and the run reports "no behaviour", which §5.8 says must never
    # happen — the refusal belongs before the CPG, not after it.
    from code_analysis.framework_config import FrameworkUnsupported
    from code_analysis.framework_config import default as default_frameworks

    try:
        default_frameworks().get(profile.framework, journey.surface)
    except FrameworkUnsupported as e:
        print(f"REFUSED: {e}")
        return 1

    # The profile's module map replaces the derivation that used to be a regex
    # over one company's directory names.
    from metis_mcp.mbt.test_levels import set_service_resolver

    set_service_resolver(profile.service_of)

    try:
        extraction = extract(args.repo, language=profile.language,
                             project=profile.project,
                             framework=profile.framework,
                             project_annotations=profile.annotations,
                             commit=args.commit or "",
                             refresh=args.refresh)
    except EngineUnavailable as e:
        print(f"REFUSED: {e}")
        return 1

    for line in extraction.log:
        print(f"  {line}")
    print(f"  commit: {extraction.commit}")

    args.workflow = "model-build"
    args.scope = args.scope or profile.project

    # **The source follows the surface.** `code` reads the two JVM pack reports;
    # `web` reads a UI pack's. Hardcoding `code` meant a ui journey handed a
    # react-ui report to a reader expecting jvm-behaviour, which fails on a
    # missing key rather than saying the surfaces differ.
    if journey.surface == "ui":
        ui_report = next((r for name, r in extraction.reports.items()
                          if name.endswith("-ui")), None)
        if ui_report is None:
            print(f"REFUSED: {profile.framework!r} declares no UI pack, so there "
                  f"is nothing to extract for the {journey.surface!r} surface")
            return 1
        args.source = "web"
        args.model = str(ui_report)
        args.endpoints = None
    else:
        args.source = "code"
        args.model = str(extraction.behaviour)
        args.endpoints = str(extraction.structural)
    # REQ-METIS-PG-01: what already passes, so generation is additive rather
    # than proposing a case for behaviour a real test already covers.
    args.inventory = str(extraction.inventory) if extraction.inventory else None
    args.journey = journey.journey
    args.surface = journey.surface
    args.service = ""
    for name, value in (("author", ""), ("job_id", "analyse"), ("state", None),
                        ("overrides", None), ("glossary", None),
                        ("knowledge", None), ("confirm", ""), ("as_user", ""),
                        ("allow_unverifiable", False)):
        if not hasattr(args, name):
            setattr(args, name, value)
    return _run_workflow(args, resume=False)


def cmd_frameworks(args) -> int:
    """Spec RD-6/X-4: what extraction is declared to support."""
    from code_analysis.framework_config import default, format_config, load_file
    config = load_file(args.config) if args.config else default()
    print(format_config(config))
    return 0


def cmd_ui(args) -> int:
    """Spec §9.3: serve the review UI.

    The context is given a real `commit`. Without one the server refuses to take
    a decision at all -- which is the correct behaviour and a change from what
    this command used to do: it passed a fresh `AuditLog()` that was never saved,
    so every approval taken through the web surface returned 200 and vanished
    (N-1's "no surface has a privileged or unlogged path", violated by the
    surface §9.2 calls *primary*).
    """
    from metis_mcp.review.roles import AuditLog
    from metis_mcp.review_ui.server import ReviewContext, serve

    graph_mode = bool(getattr(args, "journey", None))
    model = _load(args)

    if graph_mode:
        proposers = _proposers_from_graph(args)
        drafted = {cid: text for cid, text in _criteria_from_graph(args).values()}

        def commit(ctx, applied) -> None:
            _write_lifecycle_to_graph(args, ctx.model)
            _write_criteria_to_graph(args, applied)
    else:
        log = OverrideLog.load(args.overrides or default_log_path(args.model or ""))
        proposers = {o.element_id: o.author for o in log.entries}
        drafted = {}
        state_file = FsPath(args.state) if args.state else default_state_path(args.model)

        def commit(ctx, applied) -> None:
            state = ReviewState.load(state_file)
            record(state, ctx.model, applied)
            state.save(state_file)

    serve(ReviewContext(model=model, audit=AuditLog(), proposers=proposers,
                        criterion=args.criterion, max_setup=args.max_setup,
                        commit=commit, drafted=drafted),
          host=args.host, port=args.port)
    return 0


def cmd_reconcile(args) -> int:
    """Spec §3.3 stage 4. Never blocks — its findings ARE the output (F-4)."""
    model = _load(args)
    criteria = []
    if args.criteria:
        for entry in json.loads(FsPath(args.criteria).read_text()):
            criteria.append(AcceptanceCriterion(
                id=entry["id"], text=entry["text"],
                functional_areas=tuple(entry.get("functional_areas", ())),
                requirement_id=entry.get("requirement_id")))
    elif getattr(args, "journey", None):
        # The criteria already in the graph, with the grade they carry. Reading
        # them was previously impossible from this verb -- it accepted only a
        # file -- so reconciling what had actually been landed and reviewed meant
        # exporting it to JSON by hand first. The grade matters: S-19 makes a
        # match against a code_derived criterion documentation agreeing with
        # itself, and dropping the grade here would silently promote it.
        criteria = _graph_criteria(args)

    if not criteria:
        where = ("nothing in the graph for this journey" if getattr(args, "journey", None)
                 else "none supplied")
        print(f"No acceptance criteria to reconcile against — {where}.\n"
              "S-3: a deployment running only code extraction gets coverage, not\n"
              "correctness. Pass --criteria <file.json>, or land criteria for this\n"
              "journey, to compare against intent.")
        return 0

    routes = {tid: model.transitions[tid].trigger.split()[-1]
              for tid in model.transition_ids() if model.transitions[tid].trigger}
    confirmed = [] if args.criteria else _graph_confirmed(args)
    print(format_reconciliation(reconcile(model, criteria, confirmed=confirmed)))
    if not args.criteria and getattr(args, "journey", None):
        # F-10: say what this view cannot see, rather than letting its silence
        # read as "there is nothing there".
        print("\n  NOTE: criteria were read from the graph, where the only link to a\n"
              "  journey is a confirmed VALIDATES match. A criterion that belongs to\n"
              "  this journey but has never been matched is INVISIBLE here, so the\n"
              "  'no transition' direction is incomplete from this source (F-4).")
    print()
    print("Pre-filter candidates (evidence, NOT a verdict — X-17):")
    for ac in criteria[:8]:
        proposal = prefilter(ac, model, routes)
        top = ", ".join(c.transition_id for c in proposal.candidates[:3]) or "none"
        print(f"  {ac.id}: {top}")
        if proposal.note:
            print(f"      {proposal.note}")
    return 0


def cmd_divergence(args) -> int:
    """Spec M-5f: cross-surface divergence, as a query rather than a judgement."""
    ui = read_source(args.ui_model)
    api = read_source(args.api_model)
    links = LinkSet(journey=args.journey or "")
    if args.links:
        for entry in json.loads(FsPath(args.links).read_text()):
            links.links.append(InvokesLink(
                ui_transition_id=entry["ui"], api_transition_id=entry["api"],
                proposed_by=entry.get("proposed_by", "manual"),
                evidence=entry.get("evidence", {}),
                confirmed_by=entry.get("confirmed_by", "")))
    print(format_divergences(divergences(ui, api, links)))
    return 0


def cmd_validate(args) -> int:
    """Spec §2.6 / §3.2 stage 3, run on its own."""
    model = _load(args)
    result = validate(model, include_ac_coverage=args.include_ac_coverage,
                      inherited=_inherited_from_graph(args))
    print(format_validation(result, args.allow_unverifiable))
    return 0 if result.is_valid(args.allow_unverifiable) else 1


def cmd_paths(args) -> int:
    model, result = _generate(args)
    print(f"{model.id} — {result.criterion} (setup cap {result.setup_cap})")
    print(f"  {len(result.paths)} paths, {len(result.uncoverable)} uncoverable, "
          f"{len(result.excluded)} excluded\n")
    for p in result.paths:
        setup = " → ".join(p.setup_transition_ids) or "(none)"
        print(f"  {p.target_key:<24} setup: {setup:<40} validate: {p.validated_transition_id}")
    if result.uncoverable:
        print("\n  Uncoverable:")
        for u in result.uncoverable:
            print(f"    {u.target_key:<24} {u.reason}: {u.detail}")
    if result.excluded:
        print("\n  Excluded:")
        for tid, reason in result.excluded:
            print(f"    {tid:<24} {reason}")
    return 0


def cmd_render(args) -> int:
    model, result = _generate(args)
    rendered = render(model, result.paths)
    for case in rendered.cases:
        print(format_case(case))
        print("\n" + "-" * 68 + "\n")
    print(f"{len(rendered.cases)} test cases, one validation each.")
    if rendered.failures:
        print("\nRendering failures:")
        for key, reason in rendered.failures:
            print(f"  {key}: {reason}")
        return 1
    return 0


def cmd_report(args) -> int:
    model, result = _generate(args)
    rendered = render(model, result.paths)
    ids = {c.target_key: c.id for c in rendered.cases}
    print(format_report(_ledger(args, model, result, ids)))
    return 0


def cmd_payload(args) -> int:
    model, result = _generate(args)
    rendered = render(model, result.paths)
    print(json.dumps([build_payload(model, c) for c in rendered.cases], indent=2))
    return 0


def _edit_target(args) -> Model:
    """The model an edit is planned against: source plus prior overrides.

    Not the review-overlaid model: `previous_value` must record the machine value
    (E-2), not a decision. Prior overrides ARE included, so a second edit to the
    same property supersedes the first rather than colliding with the source.
    """
    log_path = FsPath(args.overrides) if args.overrides else default_log_path(args.model)
    model = read_source(args.model)
    log = OverrideLog.load(log_path)
    return apply_overrides(model, log).model if log.entries else model


def cmd_override_edit(args) -> int:
    """Record one edit (spec E-1 .. E-4). Nothing is applied to the source file."""
    log_path = FsPath(args.overrides) if args.overrides else default_log_path(args.model)
    log = OverrideLog.load(log_path)
    model = _edit_target(args)
    log.model_id = model.id

    payload = json.loads(args.payload) if args.payload else None
    try:
        override = plan_override(
            model, kind=args.kind, element_id=args.element, operation=args.operation,
            author=args.author, rationale=args.rationale, classification=args.classification,
            prop=args.property or "", new_value=args.value, payload=payload,
            machine=read_source(args.model),
        )
    except OverrideRefused as e:
        print(f"REFUSED: {e}")
        return 1

    log.append(override)
    log.save(log_path)

    print(f"Recorded: {override.describe()}")
    print(f"  classification: {override.classification} "
          f"-> finding against {override.finding_target}")
    print(f"  written to:     {log_path}")

    result = apply_overrides(read_source(args.model), log)
    if result.quarantined:
        print(f"\n{len(result.quarantined)} element(s) returned to Quarantine (E-11): "
              f"{', '.join(result.quarantined)}")
    for note in result.notes:
        print(f"  ! {note}")
    print("\nAn edit is a proposal, not an approval. Re-export review to decide it;")
    print("you may not approve your own edit (N-10/E-12).")
    return 0


def cmd_override_list(args) -> int:
    log_path = FsPath(args.overrides) if args.overrides else default_log_path(args.model)
    log = OverrideLog.load(log_path)
    if not log.entries:
        print(f"No overrides recorded for {args.model}.")
        return 0
    print(format_overrides(apply_overrides(read_source(args.model), log), log))
    return 0


def cmd_override_stale(args) -> int:
    """Spec E-8/E-9: report, never auto-resolve — even when the code catches up."""
    log_path = FsPath(args.overrides) if args.overrides else default_log_path(args.model)
    log = OverrideLog.load(log_path)
    stale = check_staleness(read_source(args.model), log)
    if not stale:
        print(f"No stale overrides — every edit still matches the value it was made against.")
        return 0
    print(f"{len(stale)} stale override(s). Applied, and awaiting revalidation:\n")
    for s in stale:
        print(s.describe())
        print()
    print("None of these is auto-resolved, including any the code now agrees with:")
    print("someone confirms the divergence is closed (E-9).")
    return 0


def _write_lifecycle_to_graph(args, model) -> None:
    """Persist review decisions onto the graph's own nodes (spec §8.6).

    In the graph, `lifecycle_state` *is* where human decisions live, so there is
    no separate overlay file -- the two-file split (I-14) applies to the
    file-based path only.
    """
    from metis_mcp.ontology.labels import NEEDS_REVIEW_STATES

    def marker(lifecycle: str) -> str:
        """`SET`/`REMOVE` for `:NeedReview`, from the state being written.

        The marker is derived from `lifecycle_state`, never independent of it —
        so a decision that settles a node has to clear it in the same statement
        that records the decision. Leaving it behind would put an approved
        element in the review queue forever, which is the failure mode a second
        representation of one fact always has.
        """
        return ("SET n:NeedReview" if lifecycle in NEEDS_REVIEW_STATES
                else "REMOVE n:NeedReview")

    with session(args.uri, args.user) as s:
        for sid, state in model.states.items():
            s.run(f"MATCH (n:State {{id:$i}}) "
                  f"SET n.lifecycle_state=$l, n.name=$n {marker(state.lifecycle_state)}",
                  i=sid, l=state.lifecycle_state, n=state.name)
        for tid, transition in model.transitions.items():
            s.run(f"MATCH (n:Transition|ApiCall|UiAction {{id:$i}}) "
                  f"SET n.lifecycle_state=$l {marker(transition.lifecycle_state)}",
                  i=tid, l=transition.lifecycle_state)


def _write_criteria_to_graph(args, applied) -> int:
    """Persist S-19 promotions and the edited text. Returns the count.

    **This is the write that did not exist.** `decisions.promotion_for` computed
    the grade correctly and `AuditRecord.criterion_promoted_to` carried it, and
    then nothing read it -- the same computed-but-never-read defect this project
    criticised in Atlas's `stage-gate.json`. A grade that cannot be read back is
    not a grade; it is a log line.

    The reviewer's own words are written alongside it. An edit is what *earns*
    `human_confirmed`, so discarding the edited text would promote a criterion on
    the strength of wording the graph no longer holds -- the promotion would be
    unauditable against its own cause (N-14).
    """
    promotions = [r for r in applied if r.criterion_id and r.criterion_promoted_to]
    if not promotions:
        return 0

    with session(args.uri, args.user) as s:
        for record in promotions:
            outcome = validate_update("AcceptanceCriterion",
                                      {"provenance": record.criterion_promoted_to})
            if not outcome.valid:
                # D-10: every write goes through the gate. On Community the gate
                # is the *only* thing enforcing the enum (D-8a).
                print(f"  REFUSED {record.criterion_id}: {'; '.join(outcome.errors)}")
                continue
            s.run("MATCH (n:AcceptanceCriterion {id:$i}) "
                  "SET n.provenance=$p, n.text=coalesce($t, n.text)",
                  i=record.criterion_id, p=record.criterion_promoted_to,
                  t=record.criterion_text)
    return len(promotions)


def _promote_tier_one(args, model) -> tuple[int, int, int]:
    """X-7 tier 1, applied to everything a criterion can speak for.

    Runs after a review is applied, because that is the moment the confirmed
    matches and the reviewer's edits are both current. Landing produces tier 2 --
    the code's own vocabulary, decoded and rearranged -- and this is the only
    step that can raise an element to the domain's language, and only where a
    person confirmed the match (X-9, X-18).

    **It used to promote transition names and nothing else**, so
    `propose_from_criteria` and `conflicts` had no callers at all: a criterion's
    Then clause never reached the state it describes, its When clause never
    reached the guard, and two criteria naming one state in different words were
    resolved by whichever happened to be written last.

    Returns `(transitions, states, conflicts)`.
    """
    from metis_mcp.mbt.naming import (
        TIER_AC_VOCABULARY,
        conflicts,
        guard_wording_from_criterion,
        propose_from_criteria,
        split_criterion,
        transition_display_name,
    )

    criteria = _criteria_from_graph(args)
    if not criteria:
        return 0, 0, 0

    confirmed = {}
    for tid, (cid, text) in criteria.items():
        when, then = split_criterion(text or "")
        if when and then:
            confirmed[tid] = (cid, when, then)

    proposals = propose_from_criteria(model, confirmed)
    clashes = conflicts(proposals)
    if clashes:
        # S-10: two criteria describing one state in different words disagree
        # about what that state IS. Reported and left alone -- picking one
        # silently is how a real disagreement becomes invisible.
        print(f"\n  {len(clashes)} element(s) have competing names from different "
              f"criteria — left unchanged for a human to settle (X-10, S-10):")
        for element_id, competing in sorted(clashes.items()):
            names = " | ".join(sorted({p.proposed_name for p in competing}))
            print(f"    {element_id}: {names}")

    state_names = {p.element_id: p.proposed_name for p in proposals
                   if p.kind == "state" and p.element_id not in clashes}

    transitions = states = 0
    with session(args.uri, args.user) as s:
        for tid, (_cid, text) in criteria.items():
            transition = model.transitions.get(tid)
            if transition is None or not text:
                continue
            name = transition_display_name(transition, model.states,
                                           criterion_text=text)
            if not name or tid in clashes:
                continue
            # The raw `guard_expression` is deliberately untouched: it is the
            # anchored fact, and the criterion is a second source about the same
            # behaviour rather than a correction to it (§4.4).
            s.run("MATCH (n:Transition|ApiCall|UiAction {id:$i}) "
                  "SET n.name=$n, n.name_tier=$tier, "
                  "    n.guard_wording=coalesce($w, n.guard_wording), "
                  "    n.guard_tier=CASE WHEN $w IS NULL THEN n.guard_tier ELSE $tier END",
                  i=tid, n=name, tier=TIER_AC_VOCABULARY,
                  w=guard_wording_from_criterion(text) or None)
            transitions += 1

        for element_id, proposed in sorted(state_names.items()):
            s.run("MATCH (n:State {id:$i}) SET n.name=$n, n.name_tier=$tier",
                  i=element_id, n=proposed, tier=TIER_AC_VOCABULARY)
            states += 1

    return transitions, states, len(clashes)


def cmd_review_queue(args) -> int:
    """Everything awaiting a decision, across every label (D-1's reader for
    `:NeedReview`).

    This is the question that justified the marker. `lifecycle_state` is indexed
    on 54 labels, so asking it of any ONE of them is cheap; asking it of all of
    them means scanning every node in the graph. `MATCH (n:NeedReview)` is the
    same question as one index lookup.

    The marker is never consulted to DECIDE anything — `lifecycle_state` stays
    authoritative and this command prints it beside every row, so a
    disagreement would be visible here first.
    """
    from metis_mcp.mbt.graph_session import session

    rows = []
    with session(args.uri, args.user) as s:
        for r in s.run(
                "MATCH (n:NeedReview) "
                "WITH n, [l IN labels(n) WHERE l <> 'NeedReview'][0] AS label "
                + ("WHERE $journey IN coalesce(n.functional_areas, []) "
                   if getattr(args, "journey", None) else "")
                + "RETURN label, n.id AS id, n.name AS name, "
                  "coalesce(n.lifecycle_state, '<none>') AS state "
                  "ORDER BY label, n.id",
                journey=getattr(args, "journey", None)):
            rows.append(dict(r))

    if not rows:
        print("Nothing is awaiting a decision.")
        return 0

    by_label: dict[str, int] = {}
    for row in rows:
        by_label[row["label"]] = by_label.get(row["label"], 0) + 1
    print(f"{len(rows)} element(s) awaiting a decision:\n")
    for label, count in sorted(by_label.items()):
        print(f"  {count:>4}  {label}")
    print()
    for row in rows[:args.limit]:
        print(f"  {row['state']:<11} {row['label']:<14} {row['id'][:70]}")
    if len(rows) > args.limit:
        print(f"  … and {len(rows) - args.limit} more (--limit to see them)")
    print("\n  lifecycle_state is authoritative; the marker is kept in step "
          "with it.\n  Decide with: review export … then review apply … --resume")
    return 0


def cmd_review_export(args) -> int:
    if getattr(args, "journey", None):
        model = _load_from_graph(args)
        review = export(model, include_approved=args.include_approved,
                        criteria=_criteria_from_graph(args),
                        authors=_proposers_from_graph(args))
        text = review.to_json()
        if args.out:
            FsPath(args.out).write_text(text)
            print(f"Wrote {args.out} — {len(review.items)} item(s) awaiting a decision.")
            print("Set 'reviewer', choose approve/reject/defer per item, then:")
            # `--surface` is not optional here even though it has a default:
            # the export is scoped to one surface, `apply` defaults to `api`,
            # and omitting it made the printed command refuse with "review file
            # is for model 'archive-ui', not 'archive-api'". An
            # instruction the tool tells you to run has to run.
            print(f"  python3 -m metis_mcp.mbt.cli review apply "
                  f"--journey {args.journey} --surface {args.surface} {args.out}")
        else:
            print(text)
        return 0

    model, overlay_result = load_model(args.model, args.state, args.overrides)
    if overlay_result.stale:
        print(f"NOTE: prior decisions were made against source "
              f"{overlay_result.recorded_fingerprint}; the source is now "
              f"{overlay_result.current_fingerprint}. They are retained but not "
              f"applied — re-decide against this export.\n")
    # Spec N-10/E-12: the editor of an element may not approve it. The override
    # log is what supplies `proposed_by`; without it the gate stays latent.
    log = OverrideLog.load(args.overrides or default_log_path(args.model))
    authors = {o.element_id: o.author for o in log.entries}
    review = export(model, include_approved=args.include_approved, authors=authors)
    text = review.to_json()
    if args.out:
        FsPath(args.out).write_text(text)
        print(f"Wrote {args.out} — {len(review.items)} item(s) awaiting a decision.")
        print(f"Set 'reviewer', choose approve/reject/defer per item, then:")
        print(f"  python3 -m metis_mcp.mbt.cli review apply {args.out} --model {args.model}")
    else:
        print(text)
    return 0


def _resume_after_decision(args, model, outstanding) -> int:
    """Continue the run this decision unblocked.

    **Not an auto-promotion (F-8).** The promotion was the `apply` that just
    ran — a human editing a file and recording a decision against a fingerprint.
    Resuming only executes the stages that decision released, and any further
    gate halts exactly as before. What it removes is a second command whose
    entire content is "yes, continue the thing I just authorised".

    Opt-in, because a resumed run writes: the operator says so with `--resume`,
    and the halt message offers it rather than assuming it.
    """
    from metis_mcp.workflow import RunRecord, run_path

    if outstanding:
        print(f"\n  not resuming — {len(outstanding)} element(s) still "
              f"outstanding. Decide those first.")
        return 0

    from code_analysis.project_profile import metis_home

    candidates = [r for r in (RunRecord.load(p) for p in
                              sorted((metis_home() / "runs").glob("*.json")))
                  if r is not None and r.is_blocked]
    for record in candidates:
        # Same model, or nothing: resuming somebody else's halted run because it
        # happened to be the only one would be worse than not resuming at all.
        if record.scope and record.scope not in (model.id, getattr(args, "scope", "")):
            journey = getattr(args, "journey", "")
            if journey and journey not in record.run_id:
                continue
        print(f"\n  resuming {record.run_id} — the decision that blocked it is "
              f"recorded")
        args.workflow = record.workflow
        args.scope = record.scope
        return _run_workflow(args, resume=True)

    print("\n  nothing to resume — no halted run is waiting on this model")
    return 0


def cmd_review_apply(args) -> int:
    graph_mode = bool(getattr(args, "journey", None))
    model = (_load_from_graph(args) if graph_mode
             else load_model(args.model, args.state, args.overrides)[0])
    review = ReviewFile.from_json(FsPath(args.decisions).read_text())

    # Spec S-19. `drafted` is what the reviewer was SHOWN -- the criterion text as
    # it stands in the graph. Without it `promotion_for`'s edit branch tests
    # `drafted_text is not None` and can never be true, so half of S-19 (the half
    # that does not require the reviewer to know about `affirmed_as_intent`) was
    # dead in every real run. The baseline is re-read rather than carried in the
    # file so a stale file cannot assert what it was compared against.
    drafted = ({cid: text for cid, text in _criteria_from_graph(args).values()}
               if graph_mode else {})
    result = apply(model, review, drafted=drafted)

    if not result.ok:
        print(f"REFUSED: {result.blocked_reason}")
        return 1

    print(format_audit(result.applied))
    if result.refused:
        print("\nRefused:")
        for element_id, reason in result.refused:
            print(f"  {element_id}: {reason}")

    if graph_mode:
        _write_lifecycle_to_graph(args, model)
        promoted = _write_criteria_to_graph(args, result.applied)
        renamed, restated, clashing = _promote_tier_one(args, model)
        outstanding = model.unapproved_elements()
        print(f"\nGraph updated — {model.id}: "
              f"{'approved' if not outstanding else f'{len(outstanding)} still outstanding'}")
        if promoted:
            print(f"  {promoted} criterion/criteria promoted to "
                  f"{HUMAN_CONFIRMED} — now readable from the graph (S-19)")
        if renamed or restated:
            print(f"  {renamed} transition(s) and {restated} state(s) raised to the "
                  f"acceptance criteria's own words (X-7 tier 1)")
        if clashing:
            print(f"  {clashing} left at tier 2 pending a human decision")
        if getattr(args, "resume", False):
            return _resume_after_decision(args, model, outstanding)
        return 0 if result.applied or not result.refused else 1

    # Human facts go to the review-state file. The model source is never written
    # by review (spec I-14) -- re-extraction owns it, and must not lose decisions.
    state_file = FsPath(args.state) if args.state else default_state_path(args.model)
    state = ReviewState.load(state_file)
    record(state, model, result.applied)
    state.save(state_file)

    outstanding = model.unapproved_elements()
    print(f"\nReview state → {state_file}")
    print(f"  {summarise(state)}")
    print(f"  {model.id}: "
          f"{'approved' if not outstanding else f'{len(outstanding)} element(s) still outstanding'}")
    return 0 if result.applied or not result.refused else 1


def cmd_workflow_list(args) -> int:
    """What workflows exist, and where each one stops for a human."""
    from metis_mcp.workflow import format_lint, format_workflows, lint_all

    print(format_workflows())
    errors = lint_all()
    if errors:
        print()
        print(format_lint(errors))
        return 1
    return 0


def _workflow_context(args):
    """Build the run context, loading a model only when one is already available.

    `model-build` starts by extracting, so at the start of that run there is
    nothing to load and that is not an error. Every other workflow needs an
    existing model, and a missing one is reported by the stage that wanted it
    rather than guessed at here.
    """
    from metis_mcp.workflow import Context

    context = Context(workflow=args.workflow, scope=args.scope, args=args,
                      allow_unverifiable=getattr(args, "allow_unverifiable", False))
    if getattr(args, "journey", None):
        try:
            context.model = _load_from_graph(args)
            context.inherited = _inherited_from_graph(args)
            context.criteria = _graph_criteria(args)
            context.confirmed = _graph_confirmed(args)
        except GraphNotConfigured:
            context.model = None
    elif getattr(args, "model", None):
        context.model = _load(args)
    return context


def _run_workflow(args, resume: bool) -> int:
    from metis_mcp.workflow import EXIT_HALTED, format_run, get as get_workflow, run

    workflow = get_workflow(args.workflow)
    if workflow is None:
        from metis_mcp.workflow import WORKFLOWS
        print(f"unknown workflow {args.workflow!r}. Known: "
              f"{', '.join(sorted(WORKFLOWS))}")
        return 1

    outcome = run(workflow, _workflow_context(args), resume=resume)
    print(format_run(outcome.record))
    if outcome.exit_code == EXIT_HALTED:
        # Distinct from failure on purpose: "a human has not decided yet" is the
        # designed outcome of a gate, not a broken pipeline (F-8).
        print(f"\n  exit {EXIT_HALTED}: blocked on a human decision, not a failure.")
    elif outcome.exit_code:
        print(f"\nFAILED: {outcome.message}")
    return outcome.exit_code


def cmd_workflow_run(args) -> int:
    return _run_workflow(args, resume=False)


def cmd_workflow_resume(args) -> int:
    return _run_workflow(args, resume=True)


def cmd_workflow_status(args) -> int:
    from metis_mcp.workflow import RunRecord, format_run, run_path

    record = RunRecord.load(run_path(args.run_id))
    if record is None:
        print(f"no run {args.run_id!r} (looked in {run_path(args.run_id)})")
        return 1
    print(format_run(record))
    return 0


def cmd_sources(args) -> int:
    """List what could produce a model, and why the rest cannot (spec S-17)."""
    print("Model sources:\n")
    for name, ok, why in availability():
        print(f"  {name:<10} {'available' if ok else 'unavailable'}")
        if why:
            print(f"             {why}")
    print("\n  A model is never derived silently — run one explicitly (spec S-18).")
    return 0


def cmd_land(args) -> int:
    """Source -> Episode + Quarantine elements in the graph."""
    source = get_source(args.source)
    if not source.available:
        print(f"BLOCKED: source {args.source!r} is unavailable — {source.why_unavailable()}")
        return 2
    result = source.produce(path=args.model, author=args.author)

    # **Human edits have to survive the graph boundary.** §17 makes an override a
    # layered fact rather than a mutation, and `load_model` applies the log for
    # every file-based command -- but landing read the raw source and dropped
    # them. So a correction recorded with `override edit` validated clean on the
    # file, reported "Landed N nodes", and reached the graph without the edit:
    # the guard was still empty and M-18 still blocked generation.
    #
    # Applied here, on the produced model, so the same three-owner split holds
    # (I-14, E-1): the source is machine facts, the log is human edits, and
    # re-extraction replaces the first without touching the second.
    if args.model:
        log = OverrideLog.load(
            FsPath(args.overrides) if getattr(args, "overrides", None)
            else default_log_path(args.model))
        if log.entries:
            result.model = apply_overrides(result.model, log).model
            print(f"  applied {len(log.entries)} override(s) from "
                  f"{default_log_path(args.model).name}")
    for element_id, reason in result.skipped:
        print(f"  skipped {element_id}: {reason}")

    plan = plan_landing(result, journey=args.journey, job_id=args.job_id)
    if not plan.is_legal:
        print(f"REFUSED: {len(plan.errors)} validation error(s) — nothing was written")
        for error in plan.errors[:8]:
            print(f"    {error}")
        return 1

    with session(args.uri, args.user) as s:
        outcome = land(s, plan)
    if not outcome.ok:
        print(f"REFUSED: {outcome.refused}")
        return 1
    print(f"Landed {outcome.nodes_written} nodes, {outcome.edges_written} edges")
    print(f"  episode:   {outcome.episode_id}")
    print("  lifecycle: Quarantine — authoring is not approving (spec S-4)")
    print(f"  next:      review export --journey {args.journey} --surface {args.surface}")
    return 0


def cmd_findings_land(args) -> int:
    """Validation findings and cross-surface divergences -> :Finding in the graph.

    Spec §8.2/F-12: the graph is the interface to consumers, so a divergence that
    exists only in this command's stdout has to be re-derived by everyone who
    wants it and cannot be linked to the element it concerns. Every writer this
    needed already existed and nothing called any of them.

    Lands at `Quarantine` like every other source (S-4). A finding is evidence
    for a decision, never the decision.
    """
    from metis_mcp.mbt.finding_writer import (
        from_divergences, from_validation, load, plan_load,
    )

    model = _load(args)
    result = validate(model, inherited=_inherited_from_graph(args))
    records = from_validation(result, model)

    if args.divergence_against:
        counterpart = read_source(args.divergence_against)
        ui, api = ((model, counterpart) if args.surface == "ui"
                   else (counterpart, model))
        found = divergences(ui, api, LinkSet(journey=args.journey or ""))
        records += from_divergences(found, model)

    if not records:
        print("No findings — nothing to land.")
        return 0

    plan = plan_load(
        model, journey=args.journey or model.id, surface=args.surface,
        version=args.version, commit=args.commit or "", episode=args.episode,
        findings=records, run_id=args.run_id, engine=GENERATOR_VERSION,
        source_fingerprint=source_fingerprint(model),
    )
    with session(args.uri, args.user) as s:
        written = load(s, plan)

    print(f"Landed {written['findings']} findings "
          f"({written['about']} attached to their element), "
          f"{written['versions']} component version, {written['runs']} run")
    print(f"  contains:  {written['contains']} of "
          f"{len(model.states) + len(model.transitions)} elements")
    print("  lifecycle: Quarantine — a finding is evidence, not a decision (S-4)")
    # A Finding whose ABOUT edge did not attach is in the graph and unreachable
    # from the thing it is about. That is worse than not landing it, so it is
    # reported as a failure rather than folded into the count above.
    if written["unmatched"]:
        print(f"\n  UNMATCHED — {len(written['unmatched'])} statement(s) matched "
              f"no node:")
        for item in written["unmatched"][:8]:
            print(f"    {item}")
        print("        the element was never landed, or its id is not namespaced "
              "as {model_id}::{element_id}")
        return 1
    return 0


def cmd_persist(args) -> int:
    # Routes through `_generate` like every other generating command. It used to
    # call `generate()` directly, which quietly skipped BOTH gates `_generate`
    # applies: M-18 validation (so an ill-formed model could be persisted, and
    # `--allow-unverifiable` here did nothing at all) and the existing-coverage
    # inventory (so `--inventory` was accepted and ignored). The command that
    # writes to the graph was the one command not being checked.
    model, result = _generate(args)
    rendered = render(model, result.paths)
    plan = plan_persist(model, result, rendered.cases, source_fingerprint(model),
                        args.episode, args.run_id, version=args.version,
                        commit_sha=args.commit)
    if not plan.is_legal:
        print(f"REFUSED: {len(plan.errors)} validation error(s) — nothing was written")
        for error in plan.errors[:8]:
            print(f"    {error}")
        return 1
    with session(args.uri, args.user) as s:
        outcome = persist(s, plan)
    if not outcome.ok:
        print(f"REFUSED: {outcome.refused}")
        return 1
    print(f"Persisted {outcome.nodes_written} nodes, {outcome.edges_written} edges "
          f"({len(result.paths)} paths, {len(rendered.cases)} cases)")
    # These counts now come back from Cypher, so they can disagree with the plan
    # -- and when they do, that difference is the whole finding. A broken
    # traceability chain reports as two stages that both "succeeded".
    if outcome.unmatched:
        print(f"\n  UNMATCHED — {len(outcome.unmatched)} edge group(s) planned but "
              f"not written:")
        for group, shortfall, why in outcome.unmatched:
            print(f"    {group}: {shortfall}")
            print(f"        {why}")
        return 1
    return 0


# ---------------------------------------------------------------------------
# knowledge — the knowledge-centre file (§4.5, §4.6; S-13, S-19)
# ---------------------------------------------------------------------------

def _read_knowledge(path: str):
    from metis_mcp.model_sources.knowledge import KnowledgeFileRefused, load
    try:
        return load(path), ""
    except (OSError, ValueError, KnowledgeFileRefused) as e:
        return None, f"{path}: {e}"


def cmd_knowledge_check(args) -> int:
    """Is this file atomic, parseable and grounded? Free: no graph, no model call."""
    from metis_mcp.model_sources.knowledge import format_problems
    from metis_mcp.model_sources.knowledge import validate as validate_knowledge

    knowledge, refused = _read_knowledge(args.knowledge)
    if knowledge is None:
        print(f"REFUSED: {refused}")
        return 1
    problems = validate_knowledge(knowledge)
    print(format_problems(problems, knowledge))
    return 1 if problems else 0


def cmd_knowledge_compare(args) -> int:
    """Already specified, contradicting, or new (I-5, I-8) — reported separately.

    Read-only. Nothing is written: this is what a person sees *before* deciding
    to land anything, and the three answers are never merged into one figure
    (F-5) because they have different causes and go to different people.
    """
    from metis_mcp.identity.matching import ADDED, MODIFIED, REMOVED, UNCHANGED, diff
    from metis_mcp.model_sources.knowledge import format_problems, to_criteria
    from metis_mcp.model_sources.knowledge import validate as validate_knowledge

    knowledge, refused = _read_knowledge(args.knowledge)
    if knowledge is None:
        print(f"REFUSED: {refused}")
        return 1

    problems = validate_knowledge(knowledge)
    if problems:
        print(format_problems(problems, knowledge))
        return 1

    source = get_source("ac-mined")
    try:
        candidate = source.produce(
            criteria=to_criteria(knowledge), model_id=knowledge.model_id,
            surface=knowledge.surface,
            initial_state=knowledge.initial_state or None).model
    except ValueError as e:
        print(f"REFUSED: {e}")
        return 1

    journey = args.journey or knowledge.model_id.rpartition("-")[0] or knowledge.model_id
    surface = args.surface or knowledge.surface
    try:
        with session(args.uri, args.user) as s:
            previous = load_from_graph(s, journey, surface).model
    except GraphNotConfigured as e:
        print(f"REFUSED: {e}")
        return 1

    delta = diff(previous, candidate)
    counts = delta.summary

    print(f"Knowledge — {knowledge.model_id} against {journey}-{surface}")
    print(f"  already in the model: {counts[UNCHANGED]}")
    print(f"  contradicting:        {counts[MODIFIED]}")
    print(f"  new:                  {counts[ADDED]}")
    if counts[REMOVED]:
        # Never called "removed". A knowledge file is partial by nature (§4.5);
        # what it does not mention, it does not propose to delete.
        print(f"  untouched by this statement: {counts[REMOVED]}")
    print()

    for change in delta.of(MODIFIED):
        print(f"  CONTRADICTION  {change.kind} {change.element_id}")
        print(f"      {change.detail}")
    for change in delta.of(ADDED):
        print(f"  NEW            {change.kind} {change.element_id}")

    if counts[MODIFIED]:
        print()
        print("  A contradiction is the finding, not an obstacle. Neither side wins")
        print("  automatically (S-10): the model may be recording a defect, or the")
        print("  statement may be out of date. A person decides, at G1.")
    print()
    print("  Nothing was written. To propose these:")
    print(f"    ... workflow run knowledge-capture --scope {journey} "
          f"--knowledge {args.knowledge} --journey {journey} --surface {surface}")
    return 0


# ---------------------------------------------------------------------------
# feature — the specification as Gherkin (§18; one Requirement, one Feature)
# ---------------------------------------------------------------------------

def _read_glossary(path: str):
    from metis_mcp.model_sources.glossary import GlossaryRefused, load, validate
    if not path:
        return None, ""
    try:
        glossary = load(path)
    except (OSError, ValueError, GlossaryRefused) as e:
        return None, f"{path}: {e}"
    problems = validate(glossary)
    if problems:
        return None, f"{path}: {len(problems)} problem(s); first: {problems[0].describe()}"
    return glossary, ""


def cmd_feature_render(args) -> int:
    """One Requirement, one Feature; one AcceptanceCriterion, one Scenario."""
    from metis_mcp.model_sources.knowledge import format_problems
    from metis_mcp.model_sources.knowledge import validate as validate_knowledge
    from metis_mcp.specgen.gherkin import build_feature, render_feature

    knowledge, refused = _read_knowledge(args.knowledge)
    if knowledge is None:
        print(f"REFUSED: {refused}")
        return 1
    problems = validate_knowledge(knowledge)
    if problems:
        print(format_problems(problems, knowledge))
        return 1

    glossary, glossary_refused = _read_glossary(args.glossary or "")
    if glossary_refused:
        print(f"REFUSED: {glossary_refused}")
        return 1

    entity_ids = {}
    if glossary is not None:
        # Which nouns each criterion mentions, by the entity's own name. A literal
        # match, never a guess: an entity absent from the glossary is simply not
        # tagged, and that omission is visible rather than approximated.
        for entry in knowledge.entries:
            lowered = entry.text.lower()
            entity_ids[entry.id] = [e.id for e in glossary.entities
                                    if e.name.lower() in lowered]

    feature = build_feature(
        knowledge.requirement.id, knowledge.requirement.text, knowledge.entries,
        area=args.area or "", glossary=glossary, entity_ids=entity_ids)
    text = render_feature(feature)
    if args.out:
        FsPath(args.out).write_text(text)
        print(f"Wrote {args.out} — 1 Feature, {len(feature.scenarios)} Scenario(s)")
    else:
        print(text, end="")
    return 0


def cmd_feature_read(args) -> int:
    """Read a `.feature` back as a requirement and its criteria (the round trip)."""
    from metis_mcp.model_sources.knowledge import format_problems
    from metis_mcp.model_sources.knowledge import validate as validate_knowledge
    from metis_mcp.specgen.gherkin import parse_feature, to_knowledge

    try:
        text = FsPath(args.feature).read_text()
    except OSError as e:
        print(f"REFUSED: {args.feature}: {e}")
        return 1

    parsed = parse_feature(text)
    if parsed.problems:
        print(f"REFUSED: {len(parsed.problems)} problem(s) reading {args.feature}:")
        for problem in parsed.problems:
            print(f"  {problem.describe()}")
        return 1

    knowledge = to_knowledge(parsed, model_id=args.model_id or parsed.requirement_id,
                             surface=args.surface)
    problems = validate_knowledge(knowledge)
    print(format_problems(problems, knowledge))
    if args.out:
        FsPath(args.out).write_text(knowledge.to_json())
        print(f"\nWrote {args.out}")
    return 1 if problems else 0


def cmd_structure_check(args) -> int:
    """Is the page tree legal and the data tree complete? Free: no graph."""
    from metis_mcp.model_sources.structure import (
        StructureRefused, format_problems, load, validate,
    )
    try:
        structure = load(args.structure)
    except (OSError, ValueError, StructureRefused) as e:
        print(f"REFUSED: {args.structure}: {e}")
        return 1
    problems = validate(structure)
    print(format_problems(problems, structure))
    return 1 if problems else 0


def cmd_glossary_check(args) -> int:
    """Is every business noun defined, with its impact stated? Free: no graph."""
    from metis_mcp.model_sources.glossary import format_problems, load, validate
    from metis_mcp.model_sources.glossary import GlossaryRefused
    try:
        glossary = load(args.glossary)
    except (OSError, ValueError, GlossaryRefused) as e:
        print(f"REFUSED: {args.glossary}: {e}")
        return 1
    problems = validate(glossary)
    print(format_problems(problems, glossary))
    return 1 if problems else 0


def cmd_glossary_land(args) -> int:
    """Areas and entities -> the graph (spec §4.6a, D-13).

    `plan_glossary` has existed and been correct since the glossary was written,
    and nothing called it -- so `BusinessArea` and `BusinessEntity` were defined,
    validated and referenced, and never landed. `knowledge land` plans
    `AcceptanceCriterion-[:REFERENCES]->BusinessEntity` and
    `Requirement-[:BELONGS_TO]->BusinessArea` against those nodes, so without
    this the edges matched nothing and were reported as `unmatched`.

    Land the glossary BEFORE the knowledge file that references it.
    """
    from metis_mcp.model_sources.glossary import (
        GlossaryRefused, format_problems, load, plan_glossary, validate,
    )
    from metis_mcp.model_sources.landing import land

    try:
        glossary = load(args.glossary)
    except (OSError, ValueError, GlossaryRefused) as e:
        print(f"REFUSED: {args.glossary}: {e}")
        return 1

    problems = validate(glossary)
    if problems:
        print(format_problems(problems, glossary))
        return 1

    plan = plan_glossary(glossary, job_id=args.job_id, proposed_by=args.author)
    if not plan.is_legal:
        print(f"REFUSED: {len(plan.errors)} validation error(s) — nothing was written")
        for error in plan.errors[:8]:
            print(f"    {error}")
        return 1

    with session(args.uri, args.user) as s:
        outcome = land(s, plan)
    if not outcome.ok:
        print(f"REFUSED: {outcome.refused}")
        return 1

    print(f"Landed {outcome.nodes_written} nodes, {outcome.edges_written} edges")
    print(f"  episode:   {outcome.episode_id}")
    print(f"  glossary:  {len(glossary.areas)} area(s), {len(glossary.entities)} entities")
    print("  lifecycle: Quarantine — a definition is authored, not approved (S-4)")
    if outcome.unmatched:
        print(f"\n  UNMATCHED — {len(outcome.unmatched)} edge group(s) planned but not written:")
        for group, shortfall, why in outcome.unmatched:
            print(f"    {group}: {shortfall}")
            print(f"        {why}")
        return 1
    return 0


def cmd_entity_render(args) -> int:
    """Render one business entity's specification, or every one (§4.6a, §18).

    Reads the graph and writes back a document node. The document is not a file:
    F-12 makes the graph the interface consumers query, and a `.md` beside the
    repo would be a second copy of facts the graph already holds, with no edge
    to the behaviour it describes.
    """
    from metis_mcp.mbt.graph_loader import (
        load_entities, load_entity, load_entity_criteria,
    )
    from metis_mcp.model_sources.landing import land
    from metis_mcp.specgen.entity import build, render_markdown
    from metis_mcp.specgen.documents import plan_entity_document

    with session(args.uri, args.user) as s:
        if args.entity:
            row = load_entity(s, args.entity)
            if row is None:
                print(f"No business entity {args.entity!r}. "
                      f"Land a glossary first: glossary land <file>")
                return 1
            rows = [row]
        else:
            rows = load_entities(s, area=args.area or "")
            if not rows:
                where = f" in area {args.area!r}" if args.area else ""
                print(f"No business entities{where}. "
                      f"Land a glossary first: glossary land <file>")
                return 1

        specs = []
        for row in rows:
            criteria = load_entity_criteria(s, row["id"])
            specs.append(build(row, criteria, area_name=row.get("area_name") or ""))

        if args.stdout:
            for spec in specs:
                print(render_markdown(spec))
                print()
            return 0

        written = errors = 0
        unmatched: list = []
        for spec in specs:
            plan = plan_entity_document(spec, episode_id=args.episode)
            if not plan.is_legal:
                print(f"REFUSED {spec.entity_id}: {plan.errors[0]}")
                errors += 1
                continue
            outcome = land(s, plan)
            if not outcome.ok:
                print(f"REFUSED {spec.entity_id}: {outcome.refused}")
                errors += 1
                continue
            written += outcome.nodes_written
            unmatched.extend(outcome.unmatched)

    print(f"Rendered {len(specs)} entity document(s), {written} node(s) written")
    for spec in specs:
        grade = (f"{len(spec.code_derived_rules)} code-derived"
                 if spec.code_derived_rules else "all intent")
        print(f"    {spec.name:<20} {len(spec.rules)} rule(s), {grade}")
    print("  lifecycle: Quarantine — generated is not agreed (S-4)")
    if unmatched:
        print(f"\n  UNMATCHED — {len(unmatched)} edge group(s) planned but not written:")
        for group, shortfall, why in unmatched:
            print(f"    {group}: {shortfall}")
            print(f"        {why}")
        return 1
    return 1 if errors else 0


def _report_landing(outcome, what: str) -> int:
    """One shape for every landing report, including the unmatched edges.

    Unmatched is printed because `land` does not fail on it: a plan whose edge
    endpoints were not both present writes nothing for that group and returns
    success, which is how two stages both report "landed" over a broken chain.
    """
    if not outcome.ok:
        print(f"\nREFUSED: {outcome.refused}")
        return 1
    print(f"\nLanded {outcome.nodes_written} nodes, {outcome.edges_written} "
          f"edges ({what})")
    print("  lifecycle: Quarantine — nothing here is agreement (S-4)")
    for group, shortfall, why in outcome.unmatched:
        print(f"  UNMATCHED {group}: {shortfall}\n      {why}")
    return 0


def cmd_guide(args) -> int:
    """Generate `docs/guide/` from the engine.

    `--check` regenerates into memory and diffs, which is what makes a stale
    guide a failing build rather than a surprise found by a reader.
    """
    from metis_mcp import guide

    pages = guide.generate()
    target = FsPath(args.directory)

    if args.check:
        stale = []
        for name, content in sorted(pages.items()):
            path = target / name
            if not path.exists():
                stale.append(f"{name}: missing")
            elif path.read_text() != content:
                stale.append(f"{name}: differs from what the engine generates")
        if stale:
            print("STALE — run `metis guide` and commit the result:")
            for line in stale:
                print(f"    {line}")
            return 1
        print(f"{len(pages)} page(s) up to date.")
        return 0

    written = guide.write(target)
    for path in written:
        print(f"  wrote {path}")
    print(f"\n{len(written)} page(s). Each states what it was generated from.")
    return 0


def cmd_data_catalogue(args) -> int:
    """A database catalogue -> Datasource/Database/Schema/Table/View/Column.

    **Structure only.** X-7a: Métis reads intake sources and never executes
    against the System Under Test, and the distinction that does the work is
    that a database read for its structure is an intake source while the same
    database reached to check a test's outcome is the SUT. There is no mode here
    that runs a query of the caller's choosing, and `assert_no_row_reads` holds
    the reader to the catalogue views it declares.
    """
    from code_analysis import db_catalogue
    from metis_mcp.model_sources.data_landing import plan_catalogue
    from metis_mcp.model_sources.landing import land

    try:
        if args.fixture:
            catalogue = db_catalogue.from_fixture(args.fixture)
        else:
            catalogue = db_catalogue.read(
                dialect=args.dialect, dsn=args.dsn,
                password_env=args.password_env, schemas=args.schema or None)
    except db_catalogue.CatalogueRefused as e:
        print(f"REFUSED: {e}")
        return 1

    tables = sorted(catalogue.table_names())
    print(f"Catalogue — {catalogue.dialect} {catalogue.database!r}: "
          f"{len(catalogue.schemas)} schema(s), "
          f"{len([t for t in tables if '.' not in t])} object(s)")

    plan = plan_catalogue(catalogue, journey=args.journey, repo=args.repo)
    if not plan.is_legal:
        print(f"REFUSED: {len(plan.errors)} validation error(s)")
        for error in plan.errors[:8]:
            print(f"    {error}")
        return 1
    print(f"  planned {len(plan.nodes)} nodes, {len(plan.edges)} edges")
    if args.dry_run:
        print("\nNothing was written (--dry-run).")
        return 0

    with session(args.uri, args.user) as s:
        return _report_landing(land(s, plan), "catalogue")


def cmd_data_queries(args) -> int:
    """Repository queries -> Method -[:ISSUES]-> Query -[:QUERIES]-> Table.

    A query whose table no catalogue confirms still lands — it is a real thing
    the application does — and what is missing is the edge, reported as a
    pending join rather than invented (X-19).
    """
    from code_analysis import db_catalogue
    from metis_mcp.model_sources.data_landing import plan_queries
    from metis_mcp.model_sources.landing import land
    from metis_mcp.resolution import findings_for, resolve

    # The STRUCTURAL pack's output, not a model file: `read_source` reads the
    # latter and dies on `data["states"]`.
    from metis_mcp.model_sources.sources import _report_from_dict

    report = _report_from_dict(json.loads(FsPath(args.report).read_text()))
    catalogue = (db_catalogue.from_fixture(args.catalogue)
                 if args.catalogue else None)

    plan, pending = plan_queries(
        report, journey=args.journey, repo=args.repo, dialect=args.dialect,
        catalogue=catalogue)
    if not plan.is_legal:
        print(f"REFUSED: {len(plan.errors)} validation error(s)")
        for error in plan.errors[:8]:
            print(f"    {error}")
        return 1

    by_label: dict[str, int] = {}
    for node in plan.nodes:
        by_label[node.label] = by_label.get(node.label, 0) + 1
    print("Queries — " + ", ".join(f"{n} {label}"
                                   for label, n in sorted(by_label.items())))
    print("  JpaQuery means no SQL could be produced: raw, reasoned, and "
          "waiting for a person (T-9d)")

    available = ({"database": catalogue.table_names()} if catalogue else {})
    resolution = resolve(pending, available)
    print(f"  joins: {resolution.describe()}")
    for _, _, detail in findings_for(resolution):
        print(f"    {detail}")

    if args.dry_run:
        print("\nNothing was written (--dry-run).")
        return 0
    with session(args.uri, args.user) as s:
        return _report_landing(land(s, plan), "queries")


def cmd_page_object(args) -> int:
    """A page's controls as a class, with the selectors the code names.

    The join between the authored element and the extracted selector runs here
    (X-19, `element_selector`), so what is printed is what the engine resolves —
    it used to be done by a dict in a test, which meant the Page Object under
    test was one Métis could not produce.
    """
    import json as _json

    from metis_mcp.model_sources.structure import (
        elements_for,
        load as load_structure,
        selector_resolution,
    )
    from metis_mcp.rendering.scaffold import page_object

    structure = load_structure(args.structure)
    extracted = (_json.loads(FsPath(args.selectors).read_text())
                 if args.selectors else None)
    resolution, selectors = selector_resolution(structure, extracted)

    print(f"# selectors: {resolution.describe()}", file=sys.stderr)
    if extracted is None:
        print("# the web intake has not run — every method is a stub (X-19: "
              "proposed, not refuted)", file=sys.stderr)

    pages = [args.page] if args.page else sorted(structure.pages)
    for page in pages:
        if page not in structure.pages:
            print(f"REFUSED: no page {page!r}. Known: "
                  f"{', '.join(sorted(structure.pages))}")
            return 1
        print(page_object(page, elements_for(structure, page, selectors)))
        print()
    return 0


def _tracker_get(token_env: str, system: str):
    """A GET callable for the tracker reader, from the stdlib.

    `urllib` rather than `requests` so no HTTP library becomes a dependency of
    Métis — the reader takes any callable, and the suite exercises the fixture
    path with none of this involved.

    **The token is read from the NAMED variable and never from an argument**
    (PLT-005): a secret on a command line is in the shell history, the process
    list and every CI log that echoes its commands.
    """
    import json as _json
    import os
    import urllib.request

    token = os.environ.get(token_env, "")
    if not token:
        raise SystemExit(
            f"REFUSED: ${token_env} is not set. Name the variable holding the "
            f"token with --token-env and export it; the value is never passed "
            f"as an argument (PLT-005).")

    # Jira Cloud and Zephyr Scale both accept a bearer token. Jira Cloud with an
    # API token also accepts Basic; that is the caller's to arrange by exporting
    # an already-encoded value, because guessing the scheme is how a 401 gets
    # reported as "no such issue".
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def get(url: str):
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=30) as response:
            return _json.loads(response.read().decode("utf-8"))

    return get


def cmd_intake_fetch(args) -> int:
    """A tracker item -> a UIF document, ready to land.

    The half that was missing: `ANCHORS` has mapped `jira -> JiraItem` and
    `scale -> ZephyrItem` since the evidence layer landed, `metis intake land`
    carries a UIF into the graph, and nothing produced the UIF.
    """
    from code_analysis import tracker

    try:
        if args.fixture:
            result = tracker.from_fixture(args.fixture)
        else:
            if not args.key:
                print("REFUSED: --key is required for a live read. This reads "
                      "named items; it does not crawl a tracker.")
                return 1
            result = tracker.read(args.system, args.base_url, args.key,
                                  _tracker_get(args.token_env, args.system))
    except tracker.TrackerRefused as e:
        print(f"REFUSED: {e}")
        return 1

    print(tracker.describe(result))

    out_dir = FsPath(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for item in result.items:
        document = tracker.to_uif(item)
        path = out_dir / f"{item.key}.uif.json"
        path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        written.append(path)

    # Conformance at the door, before anyone runs a landing that will refuse.
    from metis_mcp.model_sources.intake_landing import conformance

    print()
    for item, path in zip(result.items, written):
        outcome = conformance(tracker.to_uif(item))
        state = "conformant" if outcome.conformant else "WILL BE REFUSED"
        print(f"  {path}  {state}")
        for advisory in outcome.advisories:
            print(f"      advisory: {advisory[:150]}")
        for refusal in outcome.refusals:
            print(f"      refused:  {refusal[:150]}")

    print(f"\n{len(written)} UIF document(s). Land them with:")
    for path in written:
        print(f"  python3 -m metis_mcp.mbt.cli intake land {path}")
    return 0


def cmd_intake_land(args) -> int:
    """A UIF document -> Episode, anchor, and what can honestly be derived.

    Spec §3.2 stage 2. This is the half that has been missing since the v1
    engine: extraction was always real, and nothing carried its output into the
    graph.
    """
    from metis_mcp.model_sources import intake_landing as intake
    from metis_mcp.model_sources.landing import land

    try:
        document = intake.load(args.uif)
    except intake.IntakeRefused as e:
        print(f"REFUSED: {args.uif}: {e}")
        return 1

    try:
        plan = intake.plan_intake(document, job_id=args.job_id,
                                  proposed_by=args.author)
    except intake.IntakeRefused as e:
        print(f"REFUSED: {e}")
        return 1

    print(intake.describe(plan, document))
    if not plan.is_legal:
        print(f"\nREFUSED: {len(plan.errors)} validation error(s) — nothing was "
              f"written.")
        for error in plan.errors[:8]:
            print(f"    {error}")
        return 1

    if args.dry_run:
        print("\nNothing was written (--dry-run).")
        return 0

    with session(args.uri, args.user) as s:
        outcome = land(s, plan)
    if not outcome.ok:
        print(f"\nREFUSED: {outcome.refused}")
        return 1

    print(f"\nLanded {outcome.nodes_written} nodes, {outcome.edges_written} edges")
    print("  lifecycle: Quarantine — intake is not agreement (S-4)")
    if outcome.unmatched:
        print(f"\n  UNMATCHED — {len(outcome.unmatched)} edge group(s) planned but "
              f"not written:")
        for group, shortfall, why in outcome.unmatched:
            print(f"    {group}: {shortfall}")
            print(f"        {why}")
        return 1
    return 0


def cmd_spec_requirement(args) -> int:
    """A spec-document feature + its EARS statement -> a Requirement (§4.5).

    Lands through `knowledge.plan_documentation`, so there stays exactly one
    writer of `Requirement` and one set of rules about what reaches the graph.
    """
    from metis_mcp.model_sources.knowledge import format_problems, plan_documentation
    from metis_mcp.model_sources.knowledge import validate as validate_knowledge
    from metis_mcp.model_sources.landing import land
    from metis_mcp.model_sources.spec_kit import parse_spec, requirement_from_spec

    try:
        parsed = parse_spec(args.spec, feature=args.feature or "")
    except (OSError, ValueError) as e:
        print(f"REFUSED: {args.spec}: {e}")
        return 1

    if not parsed.behavioural:
        print(f"No behavioural criteria in {args.spec}. A requirement with no "
              f"atomic conditions is a scatter of prose (S-20).")
        return 1

    knowledge = requirement_from_spec(parsed, args.statement,
                                      requirement_id=args.requirement_id or "")
    problems = validate_knowledge(knowledge)
    if problems:
        print(format_problems(problems, knowledge))
        return 1

    plan = plan_documentation(knowledge, args.episode)
    if not plan.is_legal:
        print(f"REFUSED: {len(plan.errors)} validation error(s) — nothing was written.")
        for error in plan.errors[:8]:
            print(f"    {error}")
        return 1

    if args.dry_run:
        print(f"Would land: 1 Requirement, {len(knowledge.entries)} "
              f"AcceptanceCriterion, all at Quarantine.")
        print("Nothing was written (--dry-run).")
        return 0

    with session(args.uri, args.user) as s:
        outcome = land(s, plan)
    if not outcome.ok:
        print(f"REFUSED: {outcome.refused}")
        return 1

    print(f"Landed {outcome.nodes_written} nodes, {outcome.edges_written} edges")
    print(f"  requirement: {knowledge.requirement.id} "
          f"({knowledge.requirement.ears.pattern})")
    print(f"  criteria:    {len(knowledge.entries)}, all at provenance "
          f"`code_derived`")
    print("  lifecycle:   Quarantine — a criterion Métis formalised is not intent")
    print("               until a person edits or affirms it (S-19). A spec")
    print("               rendered from the code and used to check that code")
    print("               proves only that the code does what the code does (§4.1).")
    if outcome.unmatched:
        print(f"\n  UNMATCHED — {len(outcome.unmatched)} edge group(s):")
        for group, shortfall, why in outcome.unmatched:
            print(f"    {group}: {shortfall}")
            print(f"        {why}")
        return 1
    return 0


def _read_intent(path: str):
    from metis_mcp.model_sources.intent import IntentFileRefused, load
    try:
        return load(path), ""
    except (OSError, ValueError, IntentFileRefused) as e:
        return None, f"{path}: {e}"


def cmd_intent_check(args) -> int:
    """Is every need specified, and every specification checkable? Free: no graph."""
    from metis_mcp.model_sources.intent import format_problems, validate

    document, refused = _read_intent(args.file)
    if document is None:
        print(f"REFUSED: {refused}")
        return 1
    problems = validate(document)
    print(format_problems(problems, document))
    return 1 if problems else 0


def cmd_intent_land(args) -> int:
    """Intent + Specification -> the graph. Feature is NOT landed here.

    A feature is a grouping, and a grouping is a claim Métis derives from
    evidence (`feature derive`) rather than one an author restates by hand.
    """
    from metis_mcp.model_sources.intent import format_problems, plan_intent, validate
    from metis_mcp.model_sources.landing import land

    document, refused = _read_intent(args.file)
    if document is None:
        print(f"REFUSED: {refused}")
        return 1
    problems = validate(document)
    if problems:
        print(format_problems(problems, document))
        return 1

    plan = plan_intent(document, job_id=args.job_id, proposed_by=args.author)
    if not plan.is_legal:
        print(f"REFUSED: {len(plan.errors)} validation error(s) — nothing was written")
        for error in plan.errors[:8]:
            print(f"    {error}")
        return 1

    with session(args.uri, args.user) as s:
        outcome = land(s, plan)
    if not outcome.ok:
        print(f"REFUSED: {outcome.refused}")
        return 1

    print(f"Landed {outcome.nodes_written} nodes, {outcome.edges_written} edges")
    print(f"  episode: {outcome.episode_id}")
    print(f"  {len(document.intents)} need(s), {len(document.specifications)} "
          f"specification(s), at Quarantine (S-4)")
    print(f"  next:    feature derive — Métis groups these; it is not authored")
    if outcome.unmatched:
        print(f"\n  UNMATCHED — {len(outcome.unmatched)} edge group(s):")
        for group, shortfall, why in outcome.unmatched:
            print(f"    {group}: {shortfall}")
            print(f"        {why}")
        return 1
    return 0


def cmd_feature_derive(args) -> int:
    """Group specifications into features, from evidence rather than wording."""
    from metis_mcp.mbt.graph_loader import (
        load_known_entity_keys, load_spec_implementations, load_specifications,
    )
    from metis_mcp.model_sources.feature import derive, format_derivation, plan_features
    from metis_mcp.model_sources.landing import land

    with session(args.uri, args.user) as s:
        specifications = load_specifications(s)
        if not specifications:
            print("No specifications in the graph. Land some first: "
                  "intent land <file>")
            return 1
        known = load_known_entity_keys(s)
        implementations = load_spec_implementations(s)

        result = derive(specifications, known_entities=known,
                        implementations=implementations)
        print(format_derivation(result))

        if args.dry_run:
            print("\nNothing was written (--dry-run).")
            return 0
        if not result.features:
            print("\nNothing to land.")
            return 1

        plan = plan_features(result, args.episode)
        if not plan.is_legal:
            print(f"REFUSED: {len(plan.errors)} validation error(s). "
                  f"First: {plan.errors[0]}")
            return 1
        outcome = land(s, plan)

        # The last hop: which walks demonstrate each capability. Run after the
        # features land, because it reads them back -- a feature that does not
        # exist yet cannot be joined to anything.
        from metis_mcp.mbt.graph_loader import load_feature_scenarios, load_features
        from metis_mcp.model_sources.feature import (
            format_links, link_scenarios, plan_scenario_links,
        )

        by_criterion, by_implementation = load_feature_scenarios(s)
        links = link_scenarios(load_features(s), by_criterion, by_implementation)
        print()
        print(format_links(links))
        link_plan = plan_scenario_links(links, args.episode)
        if link_plan.edges:
            link_outcome = land(s, link_plan)
            if link_outcome.unmatched:
                for group, shortfall, why in link_outcome.unmatched:
                    print(f"    UNMATCHED {group}: {shortfall}")
                    print(f"        {why}")

    if not outcome.ok:
        print(f"REFUSED: {outcome.refused}")
        return 1
    print(f"\nLanded {outcome.nodes_written} feature(s), {outcome.edges_written} edge(s)")
    if outcome.unmatched:
        print(f"\n  UNMATCHED — {len(outcome.unmatched)} edge group(s) planned but "
              f"not written:")
        for group, shortfall, why in outcome.unmatched:
            print(f"    {group}: {shortfall}")
            print(f"        {why}")
        return 1
    return 0


def cmd_spec_build(args) -> int:
    """A specification's contracts -> the declared Endpoint / Page / Action layer.

    Closes the code side of §4.1's comparison: `IMPLEMENTS` is in the catalogue
    and nothing wrote it, so a `Specification` had intent arriving and nothing
    else. The specification names a published contract; the CONTRACT is parsed,
    never the specification's prose.
    """
    from metis_mcp.model_sources.intent import CONTRACT_KINDS
    from metis_mcp.model_sources.landing import land
    from metis_mcp.model_sources.spec_build import (
        CONTRACT_BUILDERS, BuildResult, contract_errors, format_build,
    )
    from metis_mcp.mbt.graph_loader import load_specifications

    result = BuildResult()
    with session(args.uri, args.user) as s:
        specifications = load_specifications(s)
        if not specifications:
            print("No specifications in the graph. Land some first: intent land <file>")
            return 1

        with_contracts = [s for s in specifications
                          if json.loads(s.get("contracts_json") or "[]")]
        if not with_contracts:
            # Said plainly. Reporting "0 endpoints built" here would read as a
            # result about the contracts rather than the absence of any.
            print(f"None of the {len(specifications)} specification(s) names a "
                  f"contract. Add `contracts: [{{kind, path}}]` to the intent "
                  f"file — a specification builds nothing from its own prose.")
            return 1

        plans = []
        for spec in specifications:
            if args.specification and spec["id"] != args.specification:
                continue
            contracts = json.loads(spec.get("contracts_json") or "[]")
            for contract in contracts:
                kind, path = contract.get("kind", ""), contract.get("path", "")
                builder = CONTRACT_BUILDERS.get(kind)
                if builder is None:
                    result.refused.append((spec["id"], path,
                                           f"no builder for contract kind {kind!r}"))
                    continue
                try:
                    plan, notes = builder(spec["id"], path,
                                          args.journey or "", args.episode)
                except contract_errors() as e:
                    # X-5: a contract that will not parse stops its own run
                    # rather than landing a partial endpoint set. Reported, not
                    # raised -- one bad document must not take the others down.
                    result.refused.append((spec["id"], path, str(e)))
                    continue
                result.notes.extend(notes)
                plans.append(plan)

        for plan in plans:
            result.endpoints += sum(1 for n in plan.nodes if n.label == "Endpoint")
            result.pages += sum(1 for n in plan.nodes if n.label == "Page")
            result.actions += sum(1 for n in plan.nodes if n.label == "Action")
            result.linked += sum(1 for e in plan.edges if e.rel_type == "IMPLEMENTS")

        print(format_build(result))
        if args.dry_run:
            print("\nNothing was written (--dry-run).")
            return 0 if result.ok else 1

        unmatched = []
        written = 0
        for plan in plans:
            if not plan.is_legal:
                print(f"REFUSED: {plan.errors[0]}")
                return 1
            outcome = land(s, plan)
            if not outcome.ok:
                print(f"REFUSED: {outcome.refused}")
                return 1
            written += outcome.nodes_written
            unmatched.extend(outcome.unmatched)

    print(f"\nLanded {written} node(s) across {len(plans)} contract(s)")
    if unmatched:
        print(f"\n  UNMATCHED — {len(unmatched)} edge group(s) planned but not written:")
        for group, shortfall, why in unmatched:
            print(f"    {group}: {shortfall}")
            print(f"        {why}")
        return 1
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metis-mbt", description=__doc__.split("\n")[1])
    sub = parser.add_subparsers(dest="command", required=True)
    def add_graph_args(parser):
        parser.add_argument("--uri", help=f"bolt URI (or $METIS_NEO4J_URI)")
        parser.add_argument("--user", help="graph user (or $METIS_NEO4J_USER)")

    for name, handler, help_text in (
        ("paths", cmd_paths, "generate covering paths"),
        ("render", cmd_render, "render paths as test cases"),
        ("report", cmd_report, "coverage report"),
        ("payload", cmd_payload, "machine-readable automation payload"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("model", nargs="?", help="model JSON file (omit to read the graph)")
        p.add_argument("--journey", help="read from the graph instead of a file")
        p.add_argument("--surface", default="api", choices=("api", "ui"))
        add_graph_args(p)
        p.add_argument("--criterion", default=DEFAULT_CRITERION, choices=criterion_names())
        p.add_argument("--max-setup", type=int, default=DEFAULT_SETUP_CAP,
                       help=f"maximum setup steps (default {DEFAULT_SETUP_CAP})")
        p.add_argument("--state", help="review-state file (default: <model>.review.json)")
        p.add_argument("--overrides", help="override log (default: <model>.overrides.json)")
        p.add_argument("--inventory",
                       help="jvm-test-inventory report; skips transitions an "
                            "existing test already covers (REQ-METIS-PG-01)")
        p.add_argument("--allow-unverifiable", action="store_true",
                       help="proceed despite guards this checker cannot verify (M-17). "
                            "Fail-closed is the default; this is recorded, not silent.")
        # P-16: a coverage figure names the version and commit it is about. With
        # --journey these come from the real Component; from a file there is no
        # such node, so they are given here or the report says they were not.
        p.add_argument("--version", default="",
                       help="model version this figure refers to (P-16)")
        p.add_argument("--commit", default="",
                       help="source commit this figure refers to (P-16)")
        p.set_defaults(handler=handler)

    knowledge_parser = sub.add_parser(
        "knowledge", help="the knowledge-centre file (§4.5): check it, compare it")
    knowledge_sub = knowledge_parser.add_subparsers(
        dest="knowledge_command", required=True)

    kcheck = knowledge_sub.add_parser(
        "check", help="atomic, parseable and grounded? (free — no graph)")
    kcheck.add_argument("knowledge", help="knowledge JSON file")
    kcheck.set_defaults(handler=cmd_knowledge_check)

    kcompare = knowledge_sub.add_parser(
        "compare", help="already specified, contradicting, or new (I-5)")
    kcompare.add_argument("knowledge", help="knowledge JSON file")
    kcompare.add_argument("--journey", default="",
                          help="defaults to the file's own model_id")
    kcompare.add_argument("--surface", default="", choices=("", "api", "ui"))
    add_graph_args(kcompare)
    kcompare.set_defaults(handler=cmd_knowledge_compare)

    feature_parser = sub.add_parser(
        "feature", help="the specification as Gherkin (one Requirement, one Feature)")
    feature_sub = feature_parser.add_subparsers(dest="feature_command", required=True)

    frender = feature_sub.add_parser("render", help="knowledge file -> .feature")
    frender.add_argument("knowledge", help="knowledge JSON file")
    frender.add_argument("--glossary", help="business glossary JSON file")
    frender.add_argument("--area", default="", help="business area tag")
    frender.add_argument("-o", "--out", help="output path (default: stdout)")
    frender.set_defaults(handler=cmd_feature_render)

    fread = feature_sub.add_parser("read", help=".feature -> knowledge file")
    fread.add_argument("feature", help=".feature file")
    fread.add_argument("--model-id", default="", dest="model_id")
    fread.add_argument("--surface", default="api", choices=("api", "ui"))
    fread.add_argument("-o", "--out", help="write the knowledge JSON")
    fread.set_defaults(handler=cmd_feature_read)

    glossary_parser = sub.add_parser(
        "glossary", help="the business glossary (§4.6a): areas and entities")
    glossary_sub = glossary_parser.add_subparsers(dest="glossary_command", required=True)
    gcheck = glossary_sub.add_parser("check", help="is every noun defined? (free)")
    gcheck.add_argument("glossary", help="glossary JSON file")
    gcheck.set_defaults(handler=cmd_glossary_check)
    gland = glossary_sub.add_parser(
        "land", help="write areas and entities to the graph")
    gland.add_argument("glossary", help="glossary JSON file")
    gland.add_argument("--job-id", dest="job_id", default="manual")
    gland.add_argument("--author", default="")
    add_graph_args(gland)
    gland.set_defaults(handler=cmd_glossary_land)

    specreq_parser = sub.add_parser(
        "spec-requirement",
        help="a spec-document feature + an EARS statement -> a Requirement")
    specreq_parser.add_argument("spec", help="a spec.md from a Spec Kit repo")
    specreq_parser.add_argument(
        "--statement", required=True,
        help="the requirement in EARS, e.g. 'When a user archives a record, "
             "the system shall hide it from search.' A feature NAME is not a "
             "requirement; composing one would be guessing (S-13)")
    specreq_parser.add_argument("--feature", default="")
    specreq_parser.add_argument("--requirement-id", dest="requirement_id", default="")
    specreq_parser.add_argument("--episode", default="manual")
    specreq_parser.add_argument("--dry-run", action="store_true")
    add_graph_args(specreq_parser)
    specreq_parser.set_defaults(handler=cmd_spec_requirement)

    intent_parser = sub.add_parser(
        "intent", help="the intent file: needs and how they behave (§4.1)")
    intent_sub = intent_parser.add_subparsers(dest="intent_command", required=True)
    icheck = intent_sub.add_parser("check", help="is every need specified? (free)")
    icheck.add_argument("file", help="intent JSON file")
    icheck.set_defaults(handler=cmd_intent_check)
    iland2 = intent_sub.add_parser("land", help="write Intent and Specification")
    iland2.add_argument("file", help="intent JSON file")
    iland2.add_argument("--job-id", dest="job_id", default="manual")
    iland2.add_argument("--author", default="")
    add_graph_args(iland2)
    iland2.set_defaults(handler=cmd_intent_land)

    # ---- the data layer (X-19a) -------------------------------------------
    # Built, tested, and until now unreachable: `data_landing`, `db_catalogue`
    # and `rendering/scaffold` had no CLI command and no workflow stage, so the
    # capability existed and nobody could run it.
    data = sub.add_parser("data", help="the database layer (catalogue, queries)")
    data_sub = data.add_subparsers(dest="data_command", required=True)

    dcat = data_sub.add_parser(
        "catalogue", help="read a database catalogue and land its structure")
    dcat.add_argument("--fixture", default="",
                      help="a catalogue JSON file; omit to read a live database")
    dcat.add_argument("--dialect", default="",
                      help="postgresql | oracle | mysql")
    dcat.add_argument("--dsn", default="", help="connection string, read-only")
    dcat.add_argument("--password-env", dest="password_env", default="",
                      help="NAME of the variable holding the password, never "
                           "the password itself (PLT-005)")
    dcat.add_argument("--schema", action="append", default=[],
                      help="restrict to a schema; repeatable")
    dcat.add_argument("--journey", default="")
    dcat.add_argument("--repo", default="")
    dcat.add_argument("--dry-run", action="store_true")
    add_graph_args(dcat)
    dcat.set_defaults(handler=cmd_data_catalogue)

    dqry = data_sub.add_parser(
        "queries", help="land repository queries, translated where possible")
    dqry.add_argument("report", help="a structural extraction report (JSON)")
    dqry.add_argument("--catalogue", default="",
                      help="catalogue JSON; without it every table is a proposal")
    dqry.add_argument("--dialect", default="")
    dqry.add_argument("--journey", default="")
    dqry.add_argument("--repo", default="")
    dqry.add_argument("--dry-run", action="store_true")
    add_graph_args(dqry)
    dqry.set_defaults(handler=cmd_data_queries)

    guide_p = sub.add_parser(
        "guide", help="generate docs/guide/ from the engine")
    guide_p.add_argument("--directory", default="../docs/guide",
                         help="where to write (default ../docs/guide)")
    guide_p.add_argument("--check", action="store_true",
                         help="regenerate and diff instead of writing; "
                              "non-zero if the guide has drifted")
    guide_p.set_defaults(handler=cmd_guide)

    pobj = sub.add_parser(
        "page-object", help="render a Page Object for an authored page")
    pobj.add_argument("structure", help="structure.json")
    pobj.add_argument("--page", default="", help="one page; omit for all")
    pobj.add_argument("--selectors", default="",
                      help="the web intake's {normalised name: selector} JSON; "
                           "omit and every method is a stub")
    pobj.set_defaults(handler=cmd_page_object)

    spec_build = sub.add_parser(
        "spec-build",
        help="build Endpoint / Page / Action from a specification's contracts")
    spec_build.add_argument("--specification", default="",
                            help="one specification id; omit for all")
    spec_build.add_argument("--journey", default="")
    spec_build.add_argument("--episode", default="manual")
    spec_build.add_argument("--dry-run", action="store_true")
    add_graph_args(spec_build)
    spec_build.set_defaults(handler=cmd_spec_build)

    feature_derive = sub.add_parser(
        "feature-derive", help="group specifications into features, from evidence")
    feature_derive.add_argument("--episode", default="manual")
    feature_derive.add_argument("--dry-run", action="store_true",
                                help="show the grouping and write nothing")
    add_graph_args(feature_derive)
    feature_derive.set_defaults(handler=cmd_feature_derive)

    intake_parser = sub.add_parser(
        "intake", help="land a UIF document (§3.2 stage 2)")
    intake_sub = intake_parser.add_subparsers(dest="intake_command", required=True)
    ifetch = intake_sub.add_parser(
        "fetch", help="Jira / Zephyr Scale item -> UIF document")
    ifetch.add_argument("--system", default="jira",
                        choices=["jira", "scale"],
                        help="scale is Zephyr Scale — the value `ANCHORS` "
                             "already keys ZephyrItem on")
    ifetch.add_argument("--key", action="append", default=[],
                        help="an item key; repeatable")
    ifetch.add_argument("--base-url", dest="base_url", default="",
                        help="the tracker's base URL")
    ifetch.add_argument("--token-env", dest="token_env", default="METIS_TRACKER_TOKEN",
                        help="NAME of the variable holding the token, never "
                             "the token itself (PLT-005)")
    ifetch.add_argument("--fixture", default="",
                        help="a captured tracker response; what the suite uses")
    ifetch.add_argument("--out", default=".",
                        help="directory for the UIF documents")
    ifetch.set_defaults(handler=cmd_intake_fetch)

    iland = intake_sub.add_parser("land", help="UIF -> Episode + anchor + findings")
    iland.add_argument("uif", help="UIF JSON file")
    iland.add_argument("--job-id", dest="job_id", default="manual")
    iland.add_argument("--author", default="")
    iland.add_argument("--dry-run", action="store_true",
                       help="show the plan and write nothing")
    add_graph_args(iland)
    iland.set_defaults(handler=cmd_intake_land)

    entity_parser = sub.add_parser(
        "entity", help="business-entity specifications (§4.6a)")
    entity_sub = entity_parser.add_subparsers(dest="entity_command", required=True)
    erender = entity_sub.add_parser(
        "render", help="render entity documents into the graph")
    erender.add_argument("entity", nargs="?", default="",
                         help="one entity by id or name; omit for all")
    erender.add_argument("--area", default="", help="only entities in this area")
    erender.add_argument("--episode", default="manual")
    erender.add_argument("--stdout", action="store_true",
                         help="print the markdown instead of landing it")
    add_graph_args(erender)
    erender.set_defaults(handler=cmd_entity_render)

    structure_parser = sub.add_parser(
        "structure", help="authored page and data structure (§5.2a, §5.2b)")
    structure_sub = structure_parser.add_subparsers(
        dest="structure_command", required=True)
    scheck = structure_sub.add_parser(
        "check", help="is the tree legal and complete? (free)")
    scheck.add_argument("structure", help="structure JSON file")
    scheck.set_defaults(handler=cmd_structure_check)

    review_parser = sub.add_parser("review", help="review-as-code decisions")
    review_sub = review_parser.add_subparsers(dest="review_command", required=True)

    queue_parser = review_sub.add_parser(
        "queue", help="everything awaiting a decision, across every label")
    queue_parser.add_argument("--journey", help="narrow to one journey")
    queue_parser.add_argument("--limit", type=int, default=25)
    add_graph_args(queue_parser)
    queue_parser.set_defaults(handler=cmd_review_queue)

    export_parser = review_sub.add_parser("export", help="write a decision file")
    export_parser.add_argument("model", nargs="?")
    export_parser.add_argument("--journey")
    export_parser.add_argument("--surface", default="api", choices=("api", "ui"))
    export_parser.add_argument("-o", "--out", help="output path (default: stdout)")
    export_parser.add_argument("--include-approved", action="store_true")
    export_parser.add_argument("--state", help="review-state file")
    export_parser.add_argument("--overrides", help="override log")
    add_graph_args(export_parser)
    export_parser.set_defaults(handler=cmd_review_export)

    apply_parser = review_sub.add_parser("apply", help="apply a decision file")
    apply_parser.add_argument(
        "--resume", action="store_true",
        help="continue the halted run this decision unblocks. Not an "
             "auto-promotion: the promotion was this apply (F-8)")
    apply_parser.add_argument("decisions")
    apply_parser.add_argument("--model")
    apply_parser.add_argument("--journey")
    apply_parser.add_argument("--surface", default="api", choices=("api", "ui"))
    apply_parser.add_argument("--state", help="review-state file")
    apply_parser.add_argument("--overrides", help="override log")
    add_graph_args(apply_parser)
    apply_parser.set_defaults(handler=cmd_review_apply)

    # Spec §17 -- model manipulation. Edits are recorded, never applied to the
    # source file: an override is a fact layered on an element (E-1).
    override_parser = sub.add_parser("override", help="edit a model (spec §17)")
    override_sub = override_parser.add_subparsers(dest="override_command", required=True)

    edit_parser = override_sub.add_parser("edit", help="record one edit")
    edit_parser.add_argument("model", help="model JSON file")
    edit_parser.add_argument("--kind", required=True, choices=(STATE, TRANSITION))
    edit_parser.add_argument("--element", required=True, help="element id")
    edit_parser.add_argument("--operation", required=True, choices=OPERATIONS)
    edit_parser.add_argument("--author", required=True, help="who is making this edit (E-2)")
    edit_parser.add_argument("--rationale", required=True,
                             help="why. Required, not optional (E-2)")
    edit_parser.add_argument("--classification", required=True, choices=CLASSIFICATIONS,
                             help="extraction_error = a finding against Métis; "
                                  "intended_divergence = a candidate product defect (E-4)")
    edit_parser.add_argument("--property", help="property to modify")
    edit_parser.add_argument("--value", help="new value")
    edit_parser.add_argument("--payload", help="JSON properties for an --operation add")
    edit_parser.add_argument("--overrides", help="override log")
    edit_parser.set_defaults(handler=cmd_override_edit)

    list_parser = override_sub.add_parser("list", help="findings and override density")
    list_parser.add_argument("model")
    list_parser.add_argument("--state", help="review-state file")
    list_parser.add_argument("--overrides", help="override log")
    list_parser.set_defaults(handler=cmd_override_list)

    stale_parser = override_sub.add_parser(
        "stale", help="overrides whose underlying value has moved (E-8)")
    stale_parser.add_argument("model")
    stale_parser.add_argument("--overrides", help="override log")
    stale_parser.set_defaults(handler=cmd_override_stale)

    gap_parser = sub.add_parser(
        "coverage-gap", help="what existing tests already cover (REQ-METIS-PG-01)")
    gap_parser.add_argument("model", nargs="?")
    gap_parser.add_argument("--journey")
    gap_parser.add_argument("--surface", default="api", choices=("api", "ui"))
    gap_parser.add_argument("--state", help="review-state file")
    gap_parser.add_argument("--overrides", help="override log")
    gap_parser.add_argument("--inventory", required=True,
                            help="jvm-test-inventory report")
    add_graph_args(gap_parser)
    gap_parser.set_defaults(handler=cmd_coverage_gap)

    validate_parser = sub.add_parser(
        "validate", help="check model well-formedness (spec §2.6, blocks generation)")
    validate_parser.add_argument("model", nargs="?")
    validate_parser.add_argument("--journey")
    validate_parser.add_argument("--surface", default="api", choices=("api", "ui"))
    validate_parser.add_argument("--state", help="review-state file")
    validate_parser.add_argument("--overrides", help="override log")
    validate_parser.add_argument("--allow-unverifiable", action="store_true")
    validate_parser.add_argument("--include-ac-coverage", action="store_true",
                                 help="also report transitions with no confirmed AC "
                                      "(advisory — see §2.6's fourth property)")
    add_graph_args(validate_parser)
    validate_parser.set_defaults(handler=cmd_validate)

    drift_parser = sub.add_parser("drift", help="three-way drift report (spec §7.6)")
    for pr, handler in ((drift_parser, cmd_drift),):
        pr.add_argument("model", nargs="?")
        pr.add_argument("--journey")
        pr.add_argument("--surface", default="api", choices=("api", "ui"))
        pr.add_argument("--criterion", default=DEFAULT_CRITERION, choices=criterion_names())
        pr.add_argument("--max-setup", type=int, default=DEFAULT_SETUP_CAP)
        pr.add_argument("--state", help="review-state file")
        pr.add_argument("--overrides", help="override log")
        pr.add_argument("--ledger", help="publication ledger (default: <model>.published.json)")
        pr.add_argument("--allow-unverifiable", action="store_true")
        add_graph_args(pr)
        pr.set_defaults(handler=handler)

    publish_parser = sub.add_parser(
        "publish", help="publish test cases — dry-run only, behind a literal gate")
    publish_parser.add_argument("model", nargs="?")
    publish_parser.add_argument("--journey")
    publish_parser.add_argument("--surface", default="api", choices=("api", "ui"))
    publish_parser.add_argument("--criterion", default=DEFAULT_CRITERION,
                                choices=criterion_names())
    publish_parser.add_argument("--max-setup", type=int, default=DEFAULT_SETUP_CAP)
    publish_parser.add_argument("--state", help="review-state file")
    publish_parser.add_argument("--overrides", help="override log")
    publish_parser.add_argument("--ledger", help="publication ledger")
    publish_parser.add_argument("--allow-unverifiable", action="store_true")
    publish_parser.add_argument("--confirm", default="",
                                help=f"the literal word {AFFIRMATIVE!r}. There is no "
                                     f"default-yes and no timeout-implies-yes (T-18)")
    publish_parser.add_argument("--batch-size", type=int, default=-1,
                                help="the batch size you were shown (T-19)")
    publish_parser.add_argument("--as", dest="as_identity", default="",
                                help="who is confirming (N-13)")
    publish_parser.add_argument("--role", default=PUBLISHER, choices=ROLES,
                                help="the confirming identity's role (N-9). "
                                     "Publication requires publisher or admin (N-12)")
    add_graph_args(publish_parser)
    publish_parser.set_defaults(handler=cmd_publish)

    mine_parser = sub.add_parser(
        "ac-mine", help="mine a model from acceptance criteria (spec §4.5)")
    mine_parser.add_argument("criteria", help="JSON array of acceptance criteria")
    mine_parser.add_argument("--model-id", default="ac-mined")
    mine_parser.add_argument("--surface", default="api", choices=("api", "ui"))
    mine_parser.add_argument("--initial-state", default=None)
    mine_parser.add_argument("-o", "--out", help="write the mined model")
    mine_parser.set_defaults(handler=cmd_ac_mine)

    doctor_parser = sub.add_parser(
        "doctor", help="is this machine ready to extract? (run this first)")
    doctor_parser.add_argument("repo", nargs="?", help="also validate this repo's profile")
    doctor_parser.add_argument("--project", help="profile name (default: directory name)")
    doctor_parser.add_argument("--fast", action="store_true",
                               help="skip the engine version probe (it starts a JVM)")
    doctor_parser.set_defaults(handler=cmd_doctor)

    init_parser = sub.add_parser(
        "init", help="scaffold .metis/project.json inside a repository")
    init_parser.add_argument("repo")
    init_parser.add_argument("--project", help="project name (default: directory name)")
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(handler=cmd_init)

    analyse_parser = sub.add_parser(
        "analyse", help="repository -> approval gate, in one command")
    analyse_parser.add_argument("repo")
    analyse_parser.add_argument("--project", help="profile name (default: directory name)")
    analyse_parser.add_argument("--journey", help="which declared journey")
    analyse_parser.add_argument("--surface", default="", choices=("", "api", "ui"))
    analyse_parser.add_argument("--scope", default="")
    analyse_parser.add_argument("--commit", default="", help="default: git HEAD")
    analyse_parser.add_argument("--refresh", action="store_true",
                                help="rebuild the CPG even if it is cached")
    analyse_parser.add_argument("--criterion", default=DEFAULT_CRITERION,
                                choices=criterion_names())
    analyse_parser.add_argument("--max-setup", type=int, default=DEFAULT_SETUP_CAP)
    add_graph_args(analyse_parser)
    analyse_parser.set_defaults(handler=cmd_analyse)

    frameworks_parser = sub.add_parser(
        "frameworks", help="what extraction is declared to support (X-4)")
    frameworks_parser.add_argument("--config", help="framework config JSON")
    frameworks_parser.set_defaults(handler=cmd_frameworks)

    ui_parser = sub.add_parser("ui", help="serve the review UI (spec §9.3)")
    ui_parser.add_argument("model", nargs="?")
    ui_parser.add_argument("--journey")
    ui_parser.add_argument("--surface", default="api", choices=("api", "ui"))
    ui_parser.add_argument("--state", help="review-state file")
    ui_parser.add_argument("--overrides", help="override log")
    ui_parser.add_argument("--criterion", default=DEFAULT_CRITERION,
                           choices=criterion_names())
    ui_parser.add_argument("--max-setup", type=int, default=DEFAULT_SETUP_CAP)
    ui_parser.add_argument("--host", default="127.0.0.1",
                           help="loopback by default; this server does NOT "
                                "authenticate (see server.serve)")
    ui_parser.add_argument("--port", type=int, default=8731)
    ui_parser.set_defaults(handler=cmd_ui)

    reconcile_parser = sub.add_parser(
        "reconcile", help="match acceptance criteria to transitions (spec §3.3)")
    reconcile_parser.add_argument("model", nargs="?")
    reconcile_parser.add_argument("--journey")
    reconcile_parser.add_argument("--surface", default="api", choices=("api", "ui"))
    reconcile_parser.add_argument("--state", help="review-state file")
    reconcile_parser.add_argument("--overrides", help="override log")
    reconcile_parser.add_argument("--criteria", help="JSON array of acceptance criteria")
    add_graph_args(reconcile_parser)
    reconcile_parser.set_defaults(handler=cmd_reconcile)

    divergence_parser = sub.add_parser(
        "divergence", help="cross-surface divergence report (spec M-5f)")
    divergence_parser.add_argument("ui_model", help="the ui-surface model JSON")
    divergence_parser.add_argument("api_model", help="the api-surface model JSON")
    divergence_parser.add_argument("--links", help="JSON array of INVOKES links")
    divergence_parser.add_argument("--journey", default="")
    divergence_parser.set_defaults(handler=cmd_divergence)

    spec_parser = sub.add_parser(
        "spec", help="generate the stakeholder specification (spec §18)")
    spec_parser.add_argument("model", nargs="?")
    spec_parser.add_argument("--journey")
    spec_parser.add_argument("--surface", default="api", choices=("api", "ui"))
    spec_parser.add_argument("--state", help="review-state file")
    spec_parser.add_argument("--overrides", help="override log")
    spec_parser.add_argument("-o", "--out", help="output path (default: stdout)")
    spec_parser.add_argument("--dated", action="store_true",
                             help="a frozen dated export for sign-off, rather than "
                                  "the always-current living page (SP-6)")
    spec_parser.add_argument("--version", default="", help="model version, recorded for SP-7")
    spec_parser.add_argument("--commit", default="", help="source commit, recorded for SP-7")
    spec_parser.add_argument("--write-back", metavar="REPO",
                             help="write into <REPO>/.specify/specs/<feature>/spec.md "
                                  "(an EXTERNAL write — gated by T-18)")
    spec_parser.add_argument("--feature", help="feature directory name (default: journey)")
    spec_parser.add_argument("--allow-unapproved", action="store_true",
                             help="write even when rules are unapproved (SP-5)")
    spec_parser.add_argument("--confirm", default="",
                             help=f"the literal word {AFFIRMATIVE!r} (T-18)")
    spec_parser.add_argument("--batch-size", type=int, default=-1)
    spec_parser.add_argument("--land", action="store_true",
                             help="land the rendered specification as a "
                                  "SpecDocument node (§18, F-12)")
    spec_parser.add_argument("--episode", default="manual")
    spec_parser.add_argument("--as", dest="as_identity", default="")
    add_graph_args(spec_parser)
    spec_parser.set_defaults(handler=cmd_spec)

    sources_parser = sub.add_parser("sources", help="list model sources and availability")
    sources_parser.set_defaults(handler=cmd_sources)

    land_parser = sub.add_parser("land", help="land a source's model into the graph")
    land_parser.add_argument("model", help="model JSON file")
    land_parser.add_argument("--journey", required=True)
    land_parser.add_argument("--surface", default="api", choices=("api", "ui"))
    land_parser.add_argument("--source", default="authored")
    land_parser.add_argument("--author", default="")
    land_parser.add_argument("--job-id", dest="job_id", default="manual")
    land_parser.add_argument("--overrides", help="override log (default: <model>.overrides.json)")
    add_graph_args(land_parser)
    land_parser.set_defaults(handler=cmd_land)

    findings_parser = sub.add_parser(
        "findings", help="land validation findings and divergences (spec §8.2)")
    findings_sub = findings_parser.add_subparsers(dest="findings_cmd", required=True)
    fland = findings_sub.add_parser(
        "land", help="write :Finding nodes for a model's validation output")
    fland.add_argument("model", nargs="?")
    fland.add_argument("--journey")
    fland.add_argument("--surface", default="api", choices=("api", "ui"))
    fland.add_argument("--episode", default="manual")
    fland.add_argument("--run-id", dest="run_id", default="")
    fland.add_argument("--version", type=int, default=1)
    fland.add_argument("--commit", default="")
    fland.add_argument("--divergence-against", dest="divergence_against", default="",
                       help="the counterpart surface's model, to add M-5f "
                            "cross-surface divergences")
    add_graph_args(fland)
    fland.set_defaults(handler=cmd_findings_land)

    persist_parser = sub.add_parser("persist", help="write paths and cases to the graph")
    persist_parser.add_argument("model", nargs="?")
    persist_parser.add_argument("--journey")
    persist_parser.add_argument("--surface", default="api", choices=("api", "ui"))
    persist_parser.add_argument("--criterion", default=DEFAULT_CRITERION,
                                choices=criterion_names())
    persist_parser.add_argument("--max-setup", type=int, default=DEFAULT_SETUP_CAP)
    persist_parser.add_argument("--episode", required=True,
                                help="the Episode these artefacts derive from")
    persist_parser.add_argument("--run-id", dest="run_id", default="run-1")
    persist_parser.add_argument("--version", type=int, default=1)
    persist_parser.add_argument("--commit", default=None)
    persist_parser.add_argument("--state", help="review-state file")
    add_graph_args(persist_parser)
    persist_parser.add_argument("--inventory",
                                help="jvm-test-inventory report (REQ-METIS-PG-01)")
    persist_parser.add_argument("--allow-unverifiable", action="store_true",
                                help="proceed despite guards this checker cannot "
                                     "verify (M-17). Fail-closed is the default; "
                                     "this is recorded, not silent.")
    persist_parser.set_defaults(handler=cmd_persist)

    # ---- workflow (spec §3.2) ----
    # The one entry point that knows the order. Every verb above stays, because
    # a stage has to be runnable on its own to be debuggable -- but nobody has
    # to remember the sequence any more.
    workflow_parser = sub.add_parser(
        "workflow", help="run a defined workflow with its gates (spec §3.2)")
    workflow_sub = workflow_parser.add_subparsers(dest="workflow_command",
                                                  required=True)

    list_wf = workflow_sub.add_parser("list", help="what workflows exist")
    list_wf.set_defaults(handler=cmd_workflow_list)

    for name, wf_handler, help_text in (
            ("run", cmd_workflow_run, "start a workflow"),
            ("resume", cmd_workflow_resume, "continue one that halted at a gate"),
    ):
        p = workflow_sub.add_parser(name, help=help_text)
        p.add_argument("workflow", help="workflow code (see `workflow list`)")
        p.add_argument("--scope", required=True,
                       help="what this run is about, e.g. the service name")
        p.add_argument("model", nargs="?", help="model JSON, for file-based runs")
        p.add_argument("--journey")
        p.add_argument("--surface", default="api", choices=("api", "ui"))
        p.add_argument("--source", default="authored",
                       help="authored | code | ac-mined (see `sources`)")
        p.add_argument("--author", default="")
        p.add_argument("--endpoints",
                       help="structural pack report, for --source code")
        p.add_argument("--service",
                       help="scope a multi-module pack report to one deployable. "
                            "Required when the report spans more than one, or the "
                            "whole estate lands wearing one service's name")
        p.add_argument("--glossary",
                       help="business glossary JSON file (§4.6a). Lands the "
                            "areas and entities, and links each criterion to the "
                            "nouns it acts on")
        p.add_argument("--knowledge",
                       help="knowledge-centre JSON file, for knowledge-capture "
                            "(§4.5). Named separately from `model` because it is "
                            "criteria, not a model — a source reads it, not the "
                            "model loader")
        p.add_argument("--job-id", default="workflow")
        p.add_argument("--state", help="review-state file")
        p.add_argument("--overrides", help="override log")
        p.add_argument("--criterion", default=DEFAULT_CRITERION,
                       choices=criterion_names())
        p.add_argument("--max-setup", type=int, default=DEFAULT_SETUP_CAP)
        p.add_argument("--confirm", default="",
                       help=f"the literal word {AFFIRMATIVE!r}, for a gate that "
                            f"writes externally (T-18)")
        p.add_argument("--as", dest="as_user", default="", help="acting identity")
        p.add_argument("--allow-unverifiable", action="store_true",
                       help="proceed despite guards this checker cannot verify "
                            "(M-17). Recorded, not silent.")
        add_graph_args(p)
        p.set_defaults(handler=wf_handler)

    status_wf = workflow_sub.add_parser("status", help="where a run got to")
    status_wf.add_argument("run_id")
    status_wf.set_defaults(handler=cmd_workflow_status)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except ValidationFailed as e:
        # Spec M-18 / stage 3. Distinct exit code from G1: "this model is not
        # well-formed" and "this model is not reviewed yet" need different actions.
        print(f"BLOCKED (M-18): {e}")
        return 4
    except ApprovalRequired as e:
        print(f"BLOCKED (G1): {e}")
        return 2
    except GraphNotConfigured as e:
        print(f"NOT CONFIGURED: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
