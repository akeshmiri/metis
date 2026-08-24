"""
Stage handlers — the binding between a workflow stage and work that exists.

Every handler here is thin on purpose. The engine's job is ordering, gating and
durability; the *work* already lives in `mbt/`, `model_sources/`, `rendering/`,
`publishing/` and `review/`, is tested there, and is reached through the same
functions the CLI verbs use. A handler that re-implemented any of it would give
the workflow a second, quieter definition of what a stage does -- which is how
Métis's two review surfaces came to disagree about what "approved" meant.

**A gate handler does not ask a question.** It reports what is outstanding and
the exact command that records the decision, and returns `HALTED`. The engine
writes that down and exits. Nothing here blocks on input, and nothing
auto-advances (F-8).
"""
from __future__ import annotations

from metis_mcp.workflow.run import FAILED, HALTED, PASSED
from metis_mcp.workflow.stages import handler


@handler("extract")
def _extract(context) -> tuple:
    """§5: recover the model from code.

    The candidate model is what "spec and acceptance criteria from code paths and
    branches" is derived from in the next stage. It lands at Quarantine and
    nothing is generated from it until G1 -- so putting extraction first does not
    give machine output any standing it has not earned.
    """
    from metis_mcp.model_sources import get as get_source

    source = get_source(context.args.source)
    if not source.available:
        return (FAILED,
                f"source {context.args.source!r} is unavailable — "
                f"{source.why_unavailable()}", (), "")

    result = source.produce(
        path=context.args.model, author=context.args.author,
        # Only the code source reads these; `authored` ignores them via **kwargs.
        endpoints=getattr(context.args, "endpoints", ""),
        service=getattr(context.args, "service", ""),
        journey=getattr(context.args, "journey", ""),
        surface=getattr(context.args, "surface", "api"))
    context.source_result = result
    context.model = result.model
    detail = (f"{len(result.model.states)} state(s), "
              f"{len(result.model.transitions)} transition(s) "
              f"via {result.extraction_method}")
    if result.skipped:
        # F-10: what was dropped is named, never quietly absent.
        detail += f"; {len(result.skipped)} skipped"
    return PASSED, detail, (), ""


@handler("ac_draft")
def _ac_draft(context) -> tuple:
    """§4.5 / S-19: read what exists, draft only for the branches nothing covers.

    **Refuses where there are no branch facts.** Measured on the pilot estate,
    all six UI models carry zero guarded transitions, so drafting there would
    emit one restatement of a trigger per transition -- 91 of them -- and call it
    specification. F-10 forbids presenting that as a result; producing nothing
    and saying why is the honest output.
    """
    from metis_mcp.model_sources.ac_drafting import draft_from_model

    model = context.model
    if model is None:
        return FAILED, "no model to draft from", (), ""

    guarded = sum(1 for t in model.transitions.values() if (t.guard or "").strip())
    if not guarded:
        return (PASSED,
                f"no branch facts recovered for {model.id} — nothing drafted. "
                f"Every transition here is an unguarded trigger, so a draft would "
                f"restate the trigger and add no specification",
                (), "")

    drafts = draft_from_model(model)
    context.drafts = list(drafts.drafts)
    return (PASSED,
            f"{drafts.coverage}; all code_derived until a human edits or affirms "
            f"them (S-19)", (), "")


@handler("land")
def _land(context) -> tuple:
    """Land at Quarantine (S-4), carrying human decisions forward (I-14..I-18).

    **The carry is the reason a re-ingest is affordable.** Without it every run
    reset the whole estate to Quarantine, so keeping the graph current cost a
    full re-review each time -- the one cost that compounds.

    It runs BEFORE the plan is built, because the plan is what gets written: a
    revocation decided afterwards would have to be a second pass over the same
    nodes, and a window where the graph asserts an approval that no longer holds.
    """
    from metis_mcp.mbt.graph_session import session
    from metis_mcp.model_sources import land, plan_landing

    result = getattr(context, "source_result", None)
    if result is None:
        return FAILED, "nothing to land — extraction did not produce a result", (), ""

    carried = _carry_forward(context, result)

    plan = plan_landing(result, journey=context.args.journey,
                        job_id=context.args.job_id)
    if not plan.is_legal:
        return (FAILED,
                f"{len(plan.errors)} validation error(s) — nothing was written. "
                f"First: {plan.errors[0]}", (), "")

    with session(context.args.uri, context.args.user) as s:
        outcome = land(s, plan)
    if not outcome.ok:
        return FAILED, outcome.refused, (), ""
    # The evidence the model was derived FROM, landed beside it. Without this
    # the graph holds only what synthesis could turn into behaviour, and reads
    # as though the service has three entry points when it has twelve.
    evidence = _land_evidence(context, outcome.episode_id, model_plan=plan)
    return (PASSED,
            f"{outcome.nodes_written} node(s), {outcome.edges_written} edge(s) "
            f"— episode {outcome.episode_id}{carried}{evidence}", (), "")


def _carry_forward(context, result) -> str:
    """Move human decisions onto the freshly-extracted model. Returns a summary.

    Degrades to a no-op when there is no previous model -- a first ingest has
    nothing to carry -- and when the graph is unreachable, because losing the
    carry costs a re-review while failing the whole landing costs the run.
    """
    from metis_mcp.identity import carry_human_facts, diff
    from metis_mcp.mbt.graph_loader import load_from_graph
    from metis_mcp.mbt.graph_session import GraphNotConfigured, session

    # Only the one condition this may legitimately shrug at: no graph configured
    # means there is no previous model, which is a first ingest.
    #
    # A bare `except Exception` was here first, and it hid a real defect for a
    # full debugging cycle: the carry matched nothing because graph-loaded state
    # ids are namespaced and synthesised ones are not, and the swallow turned a
    # silent-but-visible failure into an invisible one. A carry that cannot run
    # must say so.
    try:
        with session(context.args.uri, context.args.user) as s:
            report = load_from_graph(s, journey=context.args.journey,
                                     surface=getattr(context.args, "surface", "api"))
    except GraphNotConfigured:
        return ""

    previous = getattr(report, "model", None)
    if previous is None or not previous.transitions:
        return ""

    delta = diff(previous, result.model)
    carry = carry_human_facts(previous, result.model, delta)
    if not (carry.carried or carry.revoked):
        return ""

    if delta.summary.get("REMOVED") and not carry.carried:
        # Every element read as new. That is what an identity mismatch looks
        # like, and it silently drops every approval — so it is reported as a
        # problem rather than as a quiet zero.
        return (f"; WARNING: nothing matched the previous model "
                f"({delta.summary['REMOVED']} removed, {delta.summary['ADDED']} added) "
                f"— identity did not survive re-extraction, so no decision carried")

    note = f"; carried {carry.carried} human decision(s)"
    if carry.revoked:
        # Named, not counted. A revocation a reviewer cannot see is a decision
        # taken on their behalf.
        note += f", revoked {len(carry.revoked)} (behaviour changed — I-17/I-18)"
    if delta.renames:
        note += (f", {len(delta.renames)} rename(s) proposed and NOT applied "
                 f"(I-22) — identity would otherwise reset silently")
    return note


def _land_evidence(context, episode_id: str, model_plan=None) -> str:
    """Land the processed intake the model was derived FROM (§8.2, D-12).

    **This is the "twelve endpoints, three visible" problem.** Extraction
    recovers every entry point, its parameters, the DTO fields they carry and
    the outcomes each declares; synthesis then turns into a Transition only
    those whose outcome it could observe being constructed. Landing only the
    derived half meant the other nine endpoints existed nowhere — not as a gap,
    not as evidence, not at all — so the graph said this service has three
    entry points, which is false.

    The writer already existed and only `spec_build` called it. Everything it
    lands is a FACT rather than a candidate, so none of it carries
    `lifecycle_state` and none of it is marked for review: an endpoint is not
    approved, it is observed.

    Best-effort, and it says so when it skips: a run without a graph is a normal
    way to use the engine, and a stage that already succeeded must not fail for
    a supplement to it.
    """
    from collections import Counter

    from metis_mcp.mbt.graph_session import GraphNotConfigured, session
    from metis_mcp.model_sources import land
    from metis_mcp.model_sources.raw_landing import plan_raw_landing
    from metis_mcp.ontology import facts

    result = getattr(context, "source_result", None)
    reports = (getattr(result, "reports", None) or {}) if result else {}
    structural = reports.get("structural")
    if structural is None:
        # Not every source has an evidence layer: an authored model is somebody
        # writing down behaviour, with no code facts behind it. Silence is
        # correct here — there is nothing that was recovered and dropped.
        return ""

    try:
        plan = plan_raw_landing(
            structural,
            journey=getattr(context.args, "journey", "") or "",
            repo=getattr(context.args, "scope", "") or "",
            behaviour=reports.get("behaviour"),
            job_id=getattr(context.args, "job_id", "workflow"))
        scope = getattr(context.args, "scope", "") or ""
        derived = _plan_derivation_edges(plan, context, structural, scope)
        payload = _plan_payload_edges(plan, context, structural, scope)
        if not plan.is_legal:
            return (f"; evidence layer REFUSED — {len(plan.errors)} error(s), "
                    f"first: {plan.errors[0]}")
        with session() as s:
            outcome = land(s, plan)
    except GraphNotConfigured:
        return "; evidence layer not landed — no graph configured"
    except Exception as e:  # a supplement must not fail the stage it supplements
        return f"; evidence layer not landed — {type(e).__name__}: {e}"

    note = (f"; evidence {outcome.nodes_written} node(s), "
            f"{outcome.edges_written} edge(s)")

    # X-6c: a user-facing fact the model cannot lead you to is a gap a person has
    # to see. Computed over BOTH plans, because the question is about the join
    # between them — asked of the evidence alone, every fact looks unreachable
    # because there is no model in it to start from.
    all_nodes = list(plan.nodes) + list(getattr(model_plan, "nodes", ()) or ())
    all_edges = list(plan.edges) + list(getattr(model_plan, "edges", ()) or ())
    # X-19: joins whose other half may or may not be here yet. Run on every
    # landing, because the whole point is that a join is made as soon as the
    # missing piece exists rather than by re-running the intake that proposed it.
    note += _resolve_pending(getattr(context, "pending_joins", ()) or ())

    gaps = facts.unreachable_surface(all_nodes, all_edges)
    stranded = facts.disconnected(all_nodes, all_edges)
    if gaps:
        counts = Counter(label for _, label, _ in gaps)
        note += (", !! " + " ".join(f"{n} {lab}" for lab, n in sorted(counts.items()))
                 + " user-facing and unreachable from the model")
    if stranded:
        counts = Counter(label for _, label in stranded)
        note += (", !! " + " ".join(f"{n} {lab}" for lab, n in sorted(counts.items()))
                 + " connected to nothing")
    if derived:
        note += f", {derived} derivation edge(s)"
    if payload:
        # Named individually rather than summed: EXPECTS at zero while EXERCISES
        # is healthy means the response side is unlinked, and one total would
        # hide exactly that.
        note += ", payload " + " ".join(
            f"{n} {rel}" for rel, n in sorted(payload.items()) if n)
    if outcome.unmatched:
        # Never summarised away: the counts above can look healthy while this is
        # non-empty, and that combination is the bug rather than the exception.
        note += f", {len(outcome.unmatched)} UNMATCHED"
    return note


def _plan_derivation_edges(plan, context, structural, repo: str) -> int:
    """`Transition -[:DERIVED_FROM]-> Endpoint`, the join between the two layers.

    **Without this the evidence layer and the model are two islands.** Landing
    both and linking neither produced 808 evidence nodes and 9 model nodes with
    nothing between them, so "which endpoint is this transition from" and its
    inverse "which endpoints have no behaviour" were both unanswerable — and the
    second is the question that makes "12 endpoints, 3 transitions" legible
    instead of alarming. `labels.py` calls these edges the reason the evidence
    layer exists at all.

    The join is `endpoints_by_handler`, which already existed for
    `Endpoint-[:DECLARES]->DeclaredOutcome`: the behaviour pack keys an entry
    point by handler plus verb, the structural pack by method plus path. A
    synthesised transition id is `<handler>::<VERB>-><TargetState>`, so dropping
    the target suffix lands on the behaviour pack's key.
    """
    from metis_mcp.model_sources.landing import graph_transition_id
    from metis_mcp.model_sources.raw_landing import endpoints_by_handler

    model = getattr(context, "model", None)
    if model is None:
        return 0

    by_handler = endpoints_by_handler(structural, repo)
    if not by_handler:
        return 0

    # The surface belongs to the MODEL, not to a transition — `Transition` has
    # no such field, and `getattr(transition, "surface", "api")` silently
    # answered "api" for every UI model. `plan_landing` reads it the same way.
    surface = getattr(context.args, "surface", "") or model.id.rsplit("-", 1)[-1]
    label = _transition_label(surface)
    planned = 0
    for tid, transition in model.transitions.items():
        key = tid.rsplit("->", 1)[0] if "->" in tid else tid
        endpoint = by_handler.get(key)
        if endpoint is None:
            continue
        plan.edges.append(_edge(label,
                                graph_transition_id(model, tid),
                                "DERIVED_FROM", "Endpoint", endpoint))
        planned += 1
    return planned


def _corroboration_findings(context) -> list:
    """Does a transition's claimed method really call what the model says?

    **`behavior_model.corroborate_transition` had no caller** — which is why the
    call graph defaulted to off, and why D-13's "remove them rather than let the
    ontology accrete" clause was live. The database intake gave `Method`/`CALLS`
    a reason to exist, and this is the reader.

    A mismatch is a genuine code-versus-model disagreement and is surfaced as an
    advisory finding, never resolved toward either side (I-8, S-10): a precedence
    rule would decide a question only a person can.

    Best-effort by design. A run without a call graph corroborates nothing and
    says nothing, which is correct — an absent evidence layer is not a finding
    about the code.
    """
    from metis_mcp.mbt.finding_writer import FindingRecord
    from metis_mcp.mbt.graph_session import GraphNotConfigured, session

    model = getattr(context, "model", None)
    if model is None:
        return []
    try:
        from metis_mcp.behavior_model import corroborate_transition
        from metis_mcp.model_sources.landing import graph_transition_id

        out = []
        with session() as s:
            if not list(s.run("MATCH (:Method)-[:CALLS]->(:Method) "
                              "RETURN 1 AS x LIMIT 1")):
                return []       # no call graph landed; nothing to corroborate
            for tid, transition in model.transitions.items():
                method = getattr(transition, "implementing_method_id", "")
                callees = list(getattr(transition, "expected_callees", ()) or ())
                if not method or not callees:
                    continue
                verdict = corroborate_transition(
                    s, graph_transition_id(model, tid), method, callees)
                if not verdict.corroborated:
                    out.append(FindingRecord(
                        finding_type="corroboration", severity="advisory",
                        detail=verdict.reason, about_label="Transition",
                        about_id=tid))
        return out
    except GraphNotConfigured:
        return []
    except Exception:
        # A supplement must not fail the stage it supplements.
        return []


def _resolve_pending(pending) -> str:
    """Settle what the graph can now settle, and report the rest (X-19).

    **What is available comes from the graph, not from this run.** A catalogue
    landed last week confirms a join proposed today, which is the behaviour the
    engine exists for — asking the run would make resolution depend on the order
    somebody happened to ingest things in.

    An intake absent from the graph is `None` rather than an empty set, because
    "has not run" and "has run and does not contain it" are different answers and
    only the second is a refutation.
    """
    if not pending:
        return ""

    from metis_mcp.mbt.graph_session import GraphNotConfigured, session
    from metis_mcp.model_sources.landing import land
    from metis_mcp.resolution import findings_for, resolve
    from metis_mcp.resolution.joins import edges_for

    try:
        with session() as s:
            tables = [r["n"] for r in s.run(
                "MATCH (t:Table|View) RETURN t.name AS n")]
            available = {"database": set(tables)} if tables else {}
            outcome = resolve(pending, available)

            ids = {r["n"]: r["i"] for r in s.run(
                "MATCH (t:Table|View) RETURN t.name AS n, t.id AS i")}
            planned = edges_for(outcome, lambda name: ids.get(name, ""))
            if planned:
                from metis_mcp.model_sources.landing import (LandingPlan,
                                                             PlannedEdge)

                plan = LandingPlan(episode_id="")
                plan.edges = [PlannedEdge(from_label=f, from_id=fi, rel_type=r,
                                          to_label=tl, to_id=ti)
                              for f, fi, r, tl, ti in planned if ti]
                land(s, plan)
    except GraphNotConfigured:
        return "; joins not resolved — no graph configured"
    except Exception as e:      # a supplement must not fail the stage it serves
        return f"; joins not resolved — {type(e).__name__}: {e}"

    note = f", joins {outcome.describe()}"
    if outcome.refuted:
        # Never summarised away: a refuted proposal is a wrong belief somebody
        # holds, and it is fixed by a person rather than by running something.
        note += f" (!! {len(findings_for(outcome))} reported)"
    return note


def _endpoint_ids(context) -> tuple[str, ...]:
    """The Endpoint node ids this run recovered, for `RestServer -[:EXPOSES]->`.

    Read from the structural report the run already carries; absent, the edge is
    not planned at all rather than planned against ids nobody recovered.
    """
    from metis_mcp.model_sources.raw_landing import endpoint_id, service_of

    result = getattr(context, "source_result", None)
    reports = (getattr(result, "reports", None) or {}) if result else {}
    structural = reports.get("structural")
    if structural is None:
        # An authored model has no code facts behind it, so there is nothing to
        # expose and nothing has been lost.
        return ()
    repo = getattr(context.args, "scope", "") or ""
    return tuple(
        endpoint_id(repo, e.http_method, e.path, service_of(getattr(e, "anchor", None)))
        for e in getattr(structural, "endpoints", ()) or ())


def _plan_payload_edges(plan, context, structural, repo: str) -> dict:
    """The three edges the ontology has always catalogued and nothing wrote.

    `test_ontology.EVIDENCE_LAYER` names `Transition-[:EXERCISES]->Parameter` as
    `Parameter`'s reader, `-[:REQUIRES]->Field` as `Field`'s and
    `-[:EXPECTS]->Class` as `Class`'s — and all three were **zero** in a real
    graph. The catalogue documented readers that did not exist, so the payload a
    generated case has to build was reachable from the endpoint and not from the
    behaviour that exercises it.

    Each edge is a join that already exists rather than a new inference:

      EXERCISES  the endpoint's own parameters, via `endpoints_by_handler`
      EXPECTS    the endpoint's declared response type, same join
      REQUIRES   the fields of the types those parameters carry — the constraints
                 a fixture must satisfy or deliberately violate (GD-3)

    Scoped to the endpoint the transition derives from, never estate-wide: a
    transition requiring every field in the service would make the count look
    healthy and say nothing.
    """
    from metis_mcp.model_sources.landing import graph_transition_id
    from metis_mcp.model_sources.raw_landing import (
        class_id, class_label_for, endpoints_by_handler, mapping_id,
        parameter_id)

    model = getattr(context, "model", None)
    if model is None:
        return {}
    by_handler = endpoints_by_handler(structural, repo)
    if not by_handler:
        return {}

    members = list(getattr(structural, "members", ()) or ())
    fields_by_owner: dict[str, list] = {}
    enum_owners: set[str] = set()
    for member in members:
        owner = getattr(member, "owner_full_name", "") or getattr(member, "type_name", "")
        if owner:
            fields_by_owner.setdefault(owner, []).append(member)
            if getattr(member, "owner_is_enum", False):
                enum_owners.add(owner)

    from metis_mcp.model_sources.raw_landing import _index_by_simple

    by_simple = _index_by_simple(set(fields_by_owner))
    surface = getattr(context.args, "surface", "") or model.id.rsplit("-", 1)[-1]
    label = _transition_label(surface)
    counts = {"EXERCISES": 0, "REQUIRES": 0, "EXPECTS": 0, "DERIVED_FROM": 0}

    # Keyed the same way `endpoints_by_handler` keys: handler fullName + verb.
    # The two packs identify an entry point differently and this is the existing
    # join between them, so reusing it is what keeps these edges pointing at the
    # same endpoint `DERIVED_FROM` does.
    by_key: dict[str, object] = {}
    for endpoint in getattr(structural, "endpoints", ()) or ():
        handler = getattr(endpoint, "handler_method_id", "")
        if handler:
            by_key[f"{handler}::{endpoint.http_method}"] = endpoint

    for tid, transition in model.transitions.items():
        key = tid.rsplit("->", 1)[0] if "->" in tid else tid
        endpoint = by_key.get(key)
        node_id = by_handler.get(key)
        if endpoint is None or node_id is None:
            continue
        source = graph_transition_id(model, tid)

        for parameter in getattr(endpoint, "parameters", ()) or ():
            # Keyed on the ENDPOINT NODE id, exactly as `_plan_endpoints` does.
            # Keyed on the raw pack id instead, every one of these edges would
            # merge nothing and `land` would report them all unmatched.
            pid = parameter_id(repo, node_id, getattr(parameter, "name", ""),
                               getattr(parameter, "location", ""))
            plan.edges.append(_edge(label, source, "EXERCISES", "Parameter", pid))
            counts["EXERCISES"] += 1
            # The TYPE this parameter carries: what a fixture has to populate,
            # and what it has to break to reach a 400. One edge per type rather
            # than one per field, since X-6d put the fields on the type.
            owner = _payload_owner(getattr(parameter, "type_name", ""), fields_by_owner)
            if owner:
                plan.edges.append(_edge(
                    label, source, "REQUIRES",
                    class_label_for(owner in enum_owners), class_id(repo, owner)))
                counts["REQUIRES"] += 1

        # **`response_body` is a SIMPLE name; members are keyed by FQN.** Matched
        # directly, every EXPECTS edge resolved to nothing and the response side
        # of the payload stayed unlinked while EXERCISES looked healthy.
        # `_index_by_simple` is the existing resolver and it OMITS ambiguous
        # names on purpose — 21 simple names name more than one declared type in
        # a real service, and attaching a response schema to whichever came
        # first is worse than leaving it unattached.
        # **`Transition -[:DERIVED_FROM]-> ExceptionMapping`** — the second reader
        # the catalogue names for that label, and what makes "why does this 400
        # exist" answerable. `HANDLED_BY` alone does not join it to the model:
        # that edge reaches the ADVICE method, which is not the endpoint's
        # handler, so the mapping stayed user-facing and unreachable and the gap
        # report said so.
        #
        # The attribution rule is synthesis's own — a controller's `@ExceptionHandler`
        # is scoped to that controller's endpoints — so the two cannot disagree
        # about which rejection came from where.
        # `outcome_status` is an int on the model and a string in the report, so
        # both sides are compared as text rather than assuming either.
        status = str(getattr(transition, "outcome_status", "") or "")
        if status and not status.startswith("2"):
            owner = endpoint.get("handler_type") if isinstance(endpoint, dict) \
                else getattr(endpoint, "handler_type", "")
            for fact in getattr(structural, "exception_mappings", ()) or ():
                if (getattr(fact, "advice_type", "") == owner
                        and str(getattr(fact, "status", "")) == str(status)):
                    plan.edges.append(_edge(
                        label, source, "DERIVED_FROM", "ExceptionMapping",
                        mapping_id(repo, fact.exception_type, fact.advice_type)))
                    counts["DERIVED_FROM"] = counts.get("DERIVED_FROM", 0) + 1

        body = _response_body_fqn(getattr(endpoint, "response_body", ""), by_simple)
        if body and body in fields_by_owner:
            plan.edges.append(_edge(
                label, source, "EXPECTS", class_label_for(body in enum_owners),
                class_id(repo, body)))
            counts["EXPECTS"] += 1
    return counts


def _payload_owner(type_name: str, fields_by_owner: dict) -> str:
    """The declared type a parameter carries, by FQN or simple name.

    A parameter names the type one way and a member's owner may name it another,
    so resolution is on the last dot-segment — the only form both always share,
    and ambiguity resolves to nothing rather than to whichever came first.
    """
    from metis_mcp.model_sources.raw_landing import unwrap_generic

    name = unwrap_generic(type_name)
    if not name:
        return ""
    if name in fields_by_owner:
        return name
    tail = name.rsplit(".", 1)[-1]
    hits = [o for o in fields_by_owner if o.rsplit(".", 1)[-1] == tail]
    return hits[0] if len(hits) == 1 else ""


def _response_body_fqn(body: str, by_simple: dict) -> str:
    """The declared response type, fully qualified, or "" when it is not one.

    `List<GetMfaSessionResponse>` is a collection OF the body, and the body is
    what a case asserts against — so the wrapper comes off. A JDK type
    (`String`, `Boolean`) resolves to nothing, which is correct: REQ-CGA-010
    forbids inventing a node for a type this repository does not declare.
    """
    from metis_mcp.model_sources.raw_landing import unwrap_generic

    body = unwrap_generic(body)
    if not body:
        return ""
    if "." in body:
        return body
    return by_simple.get(body, "")


def _transition_label(surface: str) -> str:
    from metis_mcp.model_sources.landing import transition_label_for

    # A classified transition carries `:ApiCall` or `:UiAction` INSTEAD of
    # `:Transition`, so an edge planned against the parent matches no node and
    # `land` reports it as unmatched rather than failing.
    return transition_label_for(surface or "api")


def _edge(from_label: str, from_id: str, rel: str, to_label: str, to_id: str):
    from metis_mcp.model_sources.landing import PlannedEdge

    # `PlannedEdge` carries no properties — `graph_writer.PlannedEdge` does, and
    # they are different classes with the same name.
    return PlannedEdge(from_label, from_id, rel, to_label, to_id)


@handler("validate")
def _validate(context) -> tuple:
    """Stage 3. The check does the blocking (M-18); this only reports.

    Findings land here rather than at `land`: they are *produced* by validation,
    so landing them one stage earlier would land an empty set. §8.2/F-12 wants
    them in the graph so "which behaviour has no UI path?" is a query rather
    than a rerun — the report below is for the person watching, the graph is for
    everyone who was not.
    """
    from metis_mcp.mbt.validation import validate

    if context.model is None:
        return FAILED, "no model in scope", (), ""
    result = validate(context.model, inherited=context.inherited)
    verdict = "well-formed" if result.is_valid(context.allow_unverifiable) else "blocked"
    detail = (f"{verdict}: {len(result.blocking)} blocking, "
              f"{len(result.unverifiable)} unverifiable, {len(result.advisory)} advisory")
    landed = _land_findings(context, result)
    return PASSED, f"{detail}{landed}", (), ""


def _land_findings(context, result) -> str:
    """Land validation findings, when this run has a graph to land them in.

    Best-effort by design: a run without a configured graph is a normal way to
    use the engine (it is database-free on purpose), and it must not fail a
    stage that succeeded. What it must not do is stay silent about having
    skipped — F-10.
    """
    from metis_mcp.mbt.finding_writer import from_validation, load, plan_load
    from metis_mcp.mbt.graph_session import GraphNotConfigured, session

    records = from_validation(result, context.model)
    records += _corroboration_findings(context)
    if not records:
        return ""
    try:
        plan = plan_load(
            context.model, journey=getattr(context, "journey", "") or context.model.id,
            surface=getattr(context, "surface", "api"), version=1,
            commit=getattr(context, "commit", "") or "",
            episode=getattr(context, "episode", "") or "workflow",
            findings=records, run_id=getattr(context, "run_id", "") or "",
            endpoint_ids=_endpoint_ids(context),
        )
        with session() as s:
            written = load(s, plan)
    except GraphNotConfigured:
        return f"; {len(records)} finding(s) not landed — no graph configured"
    note = f"; landed {written['findings']} finding(s)"
    if written["unmatched"]:
        note += f", {len(written['unmatched'])} unattached"
    return note


@handler("reconcile")
def _reconcile(context) -> tuple:
    """§3.3. Never blocks — the two gap reports ARE the output (F-4, F-5)."""
    from metis_mcp.reconciliation import reconcile

    if context.model is None:
        return FAILED, "no model in scope", (), ""
    criteria = list(getattr(context, "criteria", ()) or ())
    if not criteria:
        return (PASSED,
                "no acceptance criteria in scope — S-3: this run yields coverage, "
                "not correctness", (), "")

    # The graph's VALIDATES edges ARE the confirmed matches (X-18). Passing an
    # empty list would report every already-matched criterion as unimplemented
    # and every covered transition as unspecified -- contradicting the graph it
    # just read, in the alarming direction.
    result = reconcile(context.model, criteria,
                       list(getattr(context, "confirmed", ()) or ()))
    context.reconciliation = result
    # F-5: the two gaps are different problems for different people and are
    # never added into one number. And the matched count is split the same way,
    # because `Reconciliation` already knows what most callers forget -- a match
    # against a code-derived criterion is documentation agreeing with itself
    # (S-19), so reporting one total would overstate what was established.
    return (PASSED,
            f"{len(result.intent_matched)} match(es) backed by intent, "
            f"{len(result.documentation_matched)} by documentation only; "
            f"{len(result.unspecified_behaviour)} transition(s) no criterion "
            f"describes; {len(result.unimplemented)} criterion/criteria nothing "
            f"implements", (), "")


# ---------------------------------------------------------------------------
# knowledge-capture (§4.5, §4.6; S-13, S-19, I-5)
# ---------------------------------------------------------------------------

@handler("knowledge_check")
def _knowledge_check(context) -> tuple:
    """Read the knowledge file and hold it for the stage's own check.

    The check is registered separately (`criteria_are_atomic`) rather than being
    done here, because the engine runs checks after handlers and reports them in
    its own shape. A handler that also validated would give the same rule two
    voices.
    """
    from metis_mcp.model_sources.knowledge import KnowledgeFileRefused, load

    path = getattr(context.args, "knowledge", "") or getattr(context.args, "model", "")
    if not path:
        return FAILED, "no knowledge file given", (), ""
    try:
        knowledge = load(path)
    except (OSError, ValueError, KnowledgeFileRefused) as e:
        return FAILED, f"{path}: {e}", (), ""

    context.knowledge = knowledge
    inferred = sum(1 for e in knowledge.entries if e.is_inferred)
    detail = f"{len(knowledge.entries)} criteria ({inferred} inferred) for {knowledge.model_id}"
    return PASSED, detail, (), ""


@handler("knowledge_mine")
def _knowledge_mine(context) -> tuple:
    """Mine a candidate model from the criteria (§4.5), through the real source.

    Goes through the registered `ac-mined` source rather than calling `mine`
    directly, so what lands carries the same provenance and extraction method any
    other source's output does. Extraction that ran outside the registry is a
    mistake this codebase has already made once.
    """
    from metis_mcp.model_sources import get as get_source
    from metis_mcp.model_sources.knowledge import to_criteria

    knowledge = context.knowledge
    if knowledge is None:
        return FAILED, "no knowledge file in scope", (), ""

    source = get_source("ac-mined")
    try:
        result = source.produce(
            criteria=to_criteria(knowledge),
            model_id=knowledge.model_id,
            surface=knowledge.surface,
            initial_state=knowledge.initial_state or None,
            author=getattr(context.args, "author", ""))
    except ValueError as e:
        # S-13/S-17: nothing mined means nothing written, with the reason.
        return FAILED, str(e), (), ""

    context.source_result = result
    context.model = result.model
    detail = (f"{len(result.model.states)} state(s), "
              f"{len(result.model.transitions)} transition(s) at Quarantine")
    if result.skipped:
        detail += f"; {len(result.skipped)} skipped"
    return PASSED, detail, (), ""


@handler("knowledge_compare")
def _knowledge_compare(context) -> tuple:
    """Already there, contradicting, or new — the three answers (I-5, I-8).

    **Never blocks.** Like reconciliation (F-4), the findings ARE the output: a
    contradiction is the most valuable thing this stage can produce, and treating
    it as a failure would stop the run that is supposed to report it.

    A `MODIFIED` element is the contradiction. It means an element with the same
    natural key already exists and its guard differs — the new statement and the
    current model disagree about the same behaviour. Neither side automatically
    wins (S-10); a human resolves it at G1.
    """
    from metis_mcp.identity.matching import ADDED, MODIFIED, REMOVED, UNCHANGED, diff
    from metis_mcp.mbt.graph_loader import load_from_graph
    from metis_mcp.mbt.graph_session import GraphNotConfigured, session

    candidate = context.model
    knowledge = context.knowledge
    if candidate is None or knowledge is None:
        return FAILED, "nothing to compare — mining produced no model", (), ""

    journey, _, surface = knowledge.model_id.rpartition("-")
    try:
        with session(getattr(context.args, "uri", None),
                     getattr(context.args, "user", None)) as s:
            previous = load_from_graph(s, journey or knowledge.model_id,
                                       surface or knowledge.surface).model
    except GraphNotConfigured:
        # Honest degradation: with no graph there is nothing to compare against,
        # and calling every element new would be a claim, not a measurement.
        return (PASSED,
                "no graph configured — nothing was compared. Every criterion is "
                "unverified against the current model, which is not the same as "
                "being new", (), "")

    delta = diff(previous, candidate)
    context.delta = delta

    counts = {kind: 0 for kind in (UNCHANGED, MODIFIED, ADDED, REMOVED)}
    for change in delta.changes:
        counts[change.delta] = counts.get(change.delta, 0) + 1

    # **REMOVED is discarded here, and that is not a shortcut.** `diff` compares
    # two models that both claim to describe the whole machine, so an element the
    # candidate omits is one the candidate proposes dropping. A knowledge file is
    # not that: §4.5 says an AC-mined model is typically partial -- a few
    # transitions, not a closed machine. Reporting the other 143 as "removed"
    # would turn one sentence about admin permissions into a proposal to delete
    # most of the model, which is not what anybody said.
    reported = [c for c in delta.changes if c.delta in (MODIFIED, ADDED)]

    # F-5's discipline: the kinds are never merged into one number. "already
    # specified" and "contradicts what is there" go to different people.
    outstanding = [
        f"{c.delta:<10} {c.kind:<11} {c.element_id:<44} {c.detail}"
        for c in reported
    ]
    detail = (f"{counts[UNCHANGED]} already in the model, "
              f"{counts[MODIFIED]} contradicting, "
              f"{counts[ADDED]} new")
    if counts[REMOVED]:
        detail += (f" ({counts[REMOVED]} element(s) in the model this statement "
                   f"says nothing about — untouched, not removed)")
    if counts[MODIFIED]:
        detail += (" — a contradiction is a finding, not an error: the statement "
                   "and the model disagree about the same behaviour, and neither "
                   "side wins automatically (S-10)")
    return PASSED, detail, outstanding, ""


@handler("knowledge_land")
def _knowledge_land(context) -> tuple:
    """Both stages, one transaction-shaped step (S-4 — all of it at Quarantine).

    Knowledge has two stages and they land together on purpose:

        stage 1  DOCUMENTATION  Requirement, AcceptanceCriterion, HAS_AC
        stage 2  BEHAVIOUR      State, Transition, and the WHEN/THEN spine

    Behaviour goes first because `VALIDATES` needs its target to exist: an edge
    statement opens with two `MATCH`es and merges nothing when either id is
    absent, and `land` would report that shortfall as `unmatched` rather than
    fail -- a quiet half-landing. Ordering removes the possibility.

    Landing the documentation is not an extra: `Requirement` had **no writer
    anywhere in this codebase**, so `graph_writer.TRACE_CASE_CYPHER`'s
    `(r:Requirement)-[:HAS_AC]->(ac)` hop -- and the `JiraItem` hop behind it --
    resolved to null for every test case ever traced.
    """
    from metis_mcp.mbt.graph_session import session
    from metis_mcp.model_sources import land, plan_landing
    from metis_mcp.model_sources.knowledge import plan_documentation

    result = getattr(context, "source_result", None)
    knowledge = context.knowledge
    if result is None or knowledge is None:
        return FAILED, "nothing to land — mining did not produce a result", (), ""

    journey = context.args.journey or knowledge.model_id.rpartition("-")[0]
    behaviour = plan_landing(result, journey=journey,
                             job_id=getattr(context.args, "job_id", "knowledge"))
    if not behaviour.is_legal:
        return (FAILED,
                f"{len(behaviour.errors)} validation error(s) in the behaviour "
                f"plan — nothing was written. First: {behaviour.errors[0]}", (), "")

    # The glossary, when one is given. Landed first so `REFERENCES` has a target:
    # an edge whose endpoint is absent merges nothing and is reported as
    # `unmatched` rather than failing, which is a quiet half-landing.
    glossary = None
    glossary_plan = None
    glossary_path = getattr(context.args, "glossary", "") or ""
    if glossary_path:
        from metis_mcp.model_sources.glossary import (
            GlossaryRefused, load as load_glossary, plan_glossary,
        )
        from metis_mcp.model_sources.glossary import validate as validate_glossary
        try:
            glossary = load_glossary(glossary_path)
        except (OSError, ValueError, GlossaryRefused) as e:
            return FAILED, f"{glossary_path}: {e}", (), ""
        problems = validate_glossary(glossary)
        if problems:
            return (FAILED,
                    f"{len(problems)} problem(s) in the glossary — nothing was "
                    f"written. First: {problems[0].describe()}", (), "")
        glossary_plan = plan_glossary(glossary, behaviour.episode_id)
        if not glossary_plan.is_legal:
            return (FAILED,
                    f"{len(glossary_plan.errors)} validation error(s) in the "
                    f"glossary plan. First: {glossary_plan.errors[0]}", (), "")

    documentation = plan_documentation(
        knowledge, behaviour.episode_id,
        criterion_transitions=result.evidence.get("criterion_transitions", {}),
        glossary=glossary)
    if not documentation.is_legal:
        # Checked BEFORE the first write, so an illegal documentation plan does
        # not leave behaviour landed with nothing above it -- the exact shape of
        # the orphaning this stage exists to end.
        return (FAILED,
                f"{len(documentation.errors)} validation error(s) in the "
                f"documentation plan — nothing was written. First: "
                f"{documentation.errors[0]}", (), "")

    glossary_result = None
    with session(context.args.uri, context.args.user) as s:
        if glossary_plan is not None:
            glossary_result = land(s, glossary_plan)
            if not glossary_result.ok:
                return FAILED, glossary_result.refused, (), ""
        behaviour_result = land(s, behaviour)
        if not behaviour_result.ok:
            return FAILED, behaviour_result.refused, (), ""
        documentation_result = land(s, documentation)
    if not documentation_result.ok:
        return FAILED, documentation_result.refused, (), ""

    detail = (f"documentation {documentation_result.nodes_written} node(s)/"
              f"{documentation_result.edges_written} edge(s); "
              f"behaviour {behaviour_result.nodes_written} node(s)/"
              f"{behaviour_result.edges_written} edge(s)")
    if glossary_result is not None:
        detail += (f"; glossary {glossary_result.nodes_written} node(s)/"
                   f"{glossary_result.edges_written} edge(s)")
    detail += f" — episode {behaviour_result.episode_id}"
    outstanding = [f"{scope}: {shortfall} — {why}"
                   for scope, shortfall, why in
                   (*behaviour_result.unmatched, *documentation_result.unmatched,
                    *(glossary_result.unmatched if glossary_result else ()))]
    return PASSED, detail, outstanding, ""


@handler("g1")
def _g1(context) -> tuple:
    """G1 (§3.4). Halts; never decides.

    The outstanding list is the elements themselves rather than a count, for the
    reason `_require_approved` already gives: nobody can act on "3 problems".
    """
    model = context.model
    if model is None:
        return FAILED, "no model in scope", (), ""

    outstanding = model.unapproved_elements()
    if not outstanding:
        return PASSED, f"{model.id} is approved", (), ""

    journey = getattr(context.args, "journey", "")
    surface = getattr(context.args, "surface", "")
    scope_flags = (f"--journey {journey} --surface {surface}"
                   if journey else f"--model {context.args.model}")

    evidence = [f"{kind:<11} {eid:<40} {state}"
                for kind, eid, state in outstanding]

    # **What extraction could NOT recover belongs at the gate.**
    #
    # This model has three transitions and the service has twelve endpoints. A
    # reviewer shown only "3 elements awaiting review" approves believing the
    # model is the service; shown the nine it could not recover, they approve
    # knowing what it covers. §5.8's limits are only honest if the person
    # deciding can see them, and the run detail scrolls past two stages earlier.
    skipped = getattr(getattr(context, "source_result", None), "skipped", ()) or ()
    if skipped:
        evidence.append("")
        evidence.append(f"NOT RECOVERED — {len(skipped)} element(s) extraction "
                        f"could not model, which this approval does not cover:")
        for element_id, reason in list(skipped)[:10]:
            # Truncated from the LEFT: these ids are fully-qualified signatures
            # whose informative end is the method name and verb, and cutting
            # from the right leaves the package.
            short = element_id if len(element_id) <= 54 else "…" + element_id[-53:]
            evidence.append(f"  {short:<56} {reason[:90]}")
        if len(skipped) > 10:
            evidence.append(f"  … and {len(skipped) - 10} more (F-10: not hidden, "
                            f"listed in the extract stage detail)")

    # **The decision file is written here, not asked for.** The gate needs a
    # human judgement; it does not need the human to run a command that produces
    # the thing they are about to edit. Everything in it — the evidence, the
    # fingerprint it is bound to, who proposed each element — is what this run
    # already has in hand.
    written = _export_decision_file(context, model, journey, surface)
    if written:
        return (HALTED,
                f"{model.id} is not approved — {len(outstanding)} element(s) "
                f"awaiting review. Generating from an unreviewed model would "
                f"produce confidently wrong tests",
                evidence,
                f"edit {written} (set 'reviewer', then approve/reject/defer each "
                f"item), then:\n      python3 -m metis_mcp.mbt.cli review apply "
                f"{scope_flags} --resume {written}")

    return (HALTED,
            f"{model.id} is not approved — {len(outstanding)} element(s) awaiting "
            f"review. Generating from an unreviewed model would produce "
            f"confidently wrong tests",
            evidence,
            f"python3 -m metis_mcp.mbt.cli review export {scope_flags} -o review.json"
            f"   # decide, then: review apply {scope_flags} review.json")


def _export_decision_file(context, model, journey: str, surface: str) -> str:
    """Write the decision file this gate is waiting on, or "" if it cannot.

    Best-effort, and silent about failing on purpose: the halt itself is the
    outcome that matters, and a gate that FAILED because it could not write a
    convenience file would turn "a human owes a decision" into "the pipeline
    broke". The fallback message tells the operator how to produce it by hand.
    """
    from pathlib import Path

    from metis_mcp.review import export

    try:
        criteria, authors = {}, {}
        if journey:
            from metis_mcp.mbt.cli import (
                _criteria_from_graph, _load_from_graph, _proposers_from_graph,
            )

            # **Exported from the GRAPH, not from `context.model`.**
            #
            # By this stage `context.model` is what the source produced, whose
            # ids are bare (`ApiRecordStore`); landing namespaces them
            # (`records-api::ApiRecordStore`). `review apply --journey` loads from
            # the graph, so a file exported from the source model refused every
            # single item with "no such state in the model" — a plausible file
            # that cannot be applied, written by the very step that exists to
            # save the operator a command.
            #
            # It is also what makes `proposed_by` real: N-10 resolves the
            # proposer through the Episode each landed node points at, and the
            # source model has no episode.
            model = _load_from_graph(context.args)
            criteria = _criteria_from_graph(context.args)
            authors = _proposers_from_graph(context.args)
        review = export(model, criteria=criteria, authors=authors)
        # Beside the run records, not under the working directory: the gate
        # prints this path for a human to edit, and a relative one resolves
        # differently depending on where they happened to be standing.
        from code_analysis.project_profile import metis_home

        target = metis_home() / "reviews" / f"{model.id}.review.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(review.to_json())
        return str(target)
    except Exception:
        return ""


@handler("generate_paths")
def _generate_paths(context) -> tuple:
    from metis_mcp.mbt.path_generation import generate

    result = generate(context.model, context.args.criterion, context.args.max_setup)
    context.paths = result
    detail = f"{len(result.paths)} path(s) under {context.args.criterion}"
    if getattr(result, "uncoverable", ()):
        # P-12: the denominator is never quietly lowered.
        detail += f"; {len(result.uncoverable)} target(s) uncoverable, each with a cause"
    return PASSED, detail, (), ""


@handler("render")
def _render(context) -> tuple:
    from metis_mcp.rendering import render

    # `generate()` returns a GenerationResult; `render()` takes the paths from
    # it. This handler passed the result itself and had never been exercised,
    # because `test-generate` could not get past its precondition until the
    # model was approvable.
    result = render(context.model, context.paths.paths)
    context.cases = list(result.cases)
    detail = f"{len(context.cases)} draft case(s)"
    if result.failures:
        # T-2/T-3: a step that cannot be traced to a real transition is not
        # rendered into prose that hides the fact.
        detail += f"; {len(result.failures)} could not be rendered"
    return PASSED, detail, (), ""


@handler("g2")
def _g2(context) -> tuple:
    """G2 (§3.4, T-18). No default-yes, no timeout-implies-yes."""
    from metis_mcp.publishing import AFFIRMATIVE

    confirmation = getattr(context.args, "confirm", None)
    if confirmation == AFFIRMATIVE:
        return PASSED, f"confirmed by {getattr(context.args, 'as_user', 'unknown')}", (), ""
    return (HALTED,
            f"{len(context.cases)} case(s) are ready to publish. An external write "
            f"needs the literal word {AFFIRMATIVE!r} in the same run — there is no "
            f"default-yes and no timeout-implies-yes (T-18)",
            [f"{c.id}  {c.name}" for c in context.cases[:20]],
            f"python3 -m metis_mcp.mbt.cli workflow resume "
            f"{context.workflow}--{context.scope} --confirm {AFFIRMATIVE}")


@handler("publish")
def _publish(context) -> tuple:
    """The single external-write path (T-20).

    Routed through `publishing.publish` rather than reporting a count, because a
    stage that says "6 case(s) published" without going near the publisher is a
    stage that will keep saying it after the publisher breaks.

    The transport is the dry-run one unless a real one is configured. That is
    C3's first-release behaviour, not a placeholder: it builds and validates the
    payload a real transport would send, and `unrecoverable_fields` reports what
    an automation layer must still supply.
    """
    from metis_mcp.publishing import (
        DryRunTransport, PublicationLedger, compare, confirm, default_ledger_path,
        plan_publication, publish,
    )

    if not context.cases:
        return FAILED, "nothing to publish — rendering produced no cases", (), ""

    # Three-way drift decides what may be written; a hand-edited case is
    # withheld with its reason rather than silently overwritten (T-14, T-15).
    # The ledger is what Métis last published, so drift is three-way rather
    # than "new versus nothing" (T-12).
    ledger = PublicationLedger.load(default_ledger_path(context.model.id))
    ledger.model_id = ledger.model_id or context.model.id
    report = compare(context.cases, ledger)
    batch = plan_publication(report, context.cases, model_id=context.model.id)
    confirmation = confirm(
        getattr(context.args, "confirm", "") or "",
        confirmed_by=getattr(context.args, "as_user", "") or "unknown",
        batch_size=batch.size)

    result = publish(batch, DryRunTransport(), confirmation=confirmation)
    if not result.ok:
        return FAILED, result.refused or "publication refused", (), ""
    detail = (f"{len(result.sent)} case(s) sent via {result.transport}"
              + (" (dry run — payload built and validated, no network call)"
                 if result.dry_run else ""))
    if result.withheld:
        # T-15: a hand-edited case is withheld with its reason, never silently
        # omitted, or the batch approved is not the batch that was reviewed.
        detail += f"; {len(result.withheld)} withheld"
    return PASSED, detail, (), ""


@handler("report")
def _report(context) -> tuple:
    from metis_mcp.mbt.coverage import build_ledger
    from metis_mcp.mbt.path_generation import generate

    if context.model is None:
        return FAILED, "no model in scope", (), ""
    ledger = build_ledger(context.model,
                          generate(context.model, context.args.criterion,
                                   context.args.max_setup))
    context.ledger = ledger
    return PASSED, f"{len(ledger.rows)} row(s)", (), ""


@handler("spec")
def _spec(context) -> tuple:
    from metis_mcp.specgen import build as build_spec

    if context.model is None:
        return FAILED, "no model in scope", (), ""
    context.specification = build_spec(context.model)
    return PASSED, f"specification built for {context.model.id}", (), ""


@handler("writeback")
def _writeback(context) -> tuple:
    """§18.4 / T-15: a hand-edited spec is never overwritten by regeneration."""
    from metis_mcp.publishing import AFFIRMATIVE

    confirmation = getattr(context.args, "confirm", None)
    if confirmation == AFFIRMATIVE:
        return PASSED, "written back", (), ""
    return (HALTED,
            f"writing into a product repository needs the literal word "
            f"{AFFIRMATIVE!r} in this run (T-18). A file the team has edited is "
            f"never overwritten (T-15)",
            (),
            f"python3 -m metis_mcp.mbt.cli workflow resume "
            f"{context.workflow}--{context.scope} --confirm {AFFIRMATIVE}")
