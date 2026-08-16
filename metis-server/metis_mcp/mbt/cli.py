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

from metis_mcp.mbt.coverage import build_ledger, format_report
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
from metis_mcp.mbt.graph_loader import load_from_graph, load_inherited_guards
from metis_mcp.mbt.graph_session import GraphNotConfigured, session
from metis_mcp.mbt.graph_writer import persist, plan_persist
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
MATCH (a:AcceptanceCriterion)-[:VALIDATES]->(t:Transition)
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
WHERE ($journey IN n.functional_areas) AND (n:State OR n:Transition)
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
        print("\nNothing was sent. Re-run with:")
        print(f"  ... publish {args.model} --confirm {AFFIRMATIVE} "
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
        summary = build_ledger(model, result).summary()
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

    if not criteria:
        print("No acceptance criteria supplied — nothing to reconcile against.\n"
              "S-3: a deployment running only code extraction gets coverage, not\n"
              "correctness. Pass --criteria <file.json> to compare against intent.")
        return 0

    routes = {tid: model.transitions[tid].trigger.split()[-1]
              for tid in model.transition_ids() if model.transitions[tid].trigger}
    print(format_reconciliation(reconcile(model, criteria, confirmed=[])))
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
    print(format_report(build_ledger(model, result, ids)))
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
    with session(args.uri, args.user) as s:
        for sid, state in model.states.items():
            s.run("MATCH (n:State {id:$i}) SET n.lifecycle_state=$l, n.name=$n",
                  i=sid, l=state.lifecycle_state, n=state.name)
        for tid, transition in model.transitions.items():
            s.run("MATCH (n:Transition {id:$i}) SET n.lifecycle_state=$l",
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
            print(f"  python3 -m metis_mcp.mbt.cli review apply --journey {args.journey} {args.out}")
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
        outstanding = model.unapproved_elements()
        print(f"\nGraph updated — {model.id}: "
              f"{'approved' if not outstanding else f'{len(outstanding)} still outstanding'}")
        if promoted:
            print(f"  {promoted} criterion/criteria promoted to "
                  f"{HUMAN_CONFIRMED} — now readable from the graph (S-19)")
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
    return 0


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
        p.set_defaults(handler=handler)

    review_parser = sub.add_parser("review", help="review-as-code decisions")
    review_sub = review_parser.add_subparsers(dest="review_command", required=True)

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
    add_graph_args(land_parser)
    land_parser.set_defaults(handler=cmd_land)

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
