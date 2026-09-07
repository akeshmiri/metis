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

import json
from dataclasses import replace
from pathlib import Path

from metis_mcp.mbt.model import APPROVED
from metis_mcp.workflow.run import FAILED, HALTED, PASSED
from metis_mcp.workflow.stages import handler


def _land_stamped(session, plan, context):
    """Land a plan, stamped with the run's project.

    **One place, because there are six landing calls in this module** and a
    seventh would have to remember. `m_project` is what `storage export`
    selects on, so a plan that lands unstamped produces nodes no export can
    claim -- and an export that silently omits them is exactly the shape of
    failure the property was added to remove.

    A plan that already names a project keeps it: `lessons` sets its own from
    the corpus README, which is a better answer than the run's.
    """
    # Imported here, not at module scope: `land` is a local import in every
    # handler that uses it, and a module-level one would be the only path in
    # this file that pulls the graph writer in at import time.
    from metis_mcp.model_sources.landing import land

    if context is not None and getattr(context, "project", "") and not plan.project:
        plan.project = context.project
    return land(session, plan)


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
        # The divergence finding rides this path TOO. A model with no branch
        # facts and no requirements source is the least likely of all to produce
        # a disagreement, so staying quiet here would withhold the warning from
        # exactly the run that most needs it.
        return (PASSED,
                f"no branch facts recovered for {model.id} — nothing drafted. "
                f"Every transition here is an unguarded trigger, so a draft would "
                f"restate the trigger and add no specification",
                _no_independent_source(context), "")

    drafts = draft_from_model(model)
    context.drafts = list(drafts.drafts)
    return (PASSED,
            f"{drafts.coverage}; all code_derived until a human edits or affirms "
            f"them (S-19)", _no_independent_source(context), "")


def _no_independent_source(context) -> tuple:
    """Say so when this run structurally cannot find a divergence.

    **The failure this exists to stop, measured on a real estate.** Eight
    services were extracted, landed, validated and taken to the gate, and every
    one of them ended at `reconcile -> no acceptance criteria in scope`. The
    runs were clean. The models were sound. And the comparison that is the
    entire point of Metis -- *the code locks after 3 attempts, the criterion says
    5* -- had never once executed, because the profile declared no requirements
    source and so the only criteria in the graph were the ones drafted FROM the
    code they would be checked against.

    S-19 already labels those `code_derived`, and the provenance ladder already
    says a `code_derived` criterion agreeing with the code proves nothing. What
    was missing was anyone saying it at the point a person is reading the run.
    `reconcile` says it six stages later, phrased as a property of the scope
    rather than of the configuration, and by then the summary line reads like a
    clean result.

    A finding rather than a refusal, deliberately. Extracting a model before any
    requirement has been captured is a legitimate first move, and blocking it
    would break the order most projects actually work in. What is not legitimate
    is doing it and not knowing.
    """
    from code_analysis.project_profile import (
        ProfileInvalid,
        ProfileMissing,
        load_project,
    )

    project = getattr(context.args, "project", "") or ""
    if not project:
        return ()
    try:
        configured = load_project(project).requirements.is_configured
    except (ProfileInvalid, ProfileMissing, OSError):
        # A profile that cannot be read is a different problem, reported by
        # whatever needed it. Guessing here would add a second, wronger message.
        return ()
    if configured:
        return ()

    return (
        f"S-3/S-19: profile {project!r} declares no `requirements` source, so "
        f"every criterion this run produces is `code_derived` — written from the "
        f"code it would be checked against. This model can be COVERED and can "
        f"never be found to DIVERGE: reconcile will report `no acceptance "
        f"criteria in scope`. Add a `requirements` block naming the tracker, or "
        f"land criteria with knowledge-capture, before reading this run as "
        f"agreement between code and intent.",
    )


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
        outcome = _land_stamped(s, plan, context)
    if not outcome.ok:
        return FAILED, outcome.refused, (), ""
    # The evidence the model was derived FROM, landed beside it. Without this
    # the graph holds only what synthesis could turn into behaviour, and reads
    # as though the service has three entry points when it has twelve.
    # **The drafted criteria, which nothing landed.**
    #
    # `ac_draft` wrote them to `context.drafts`; one check read them and nothing
    # else did, so a run reported "13/13 implemented transitions drafted" and the
    # graph held zero `AcceptanceCriterion` nodes. That is half of why every real
    # run ended at `reconcile -> no acceptance criteria in scope`, and why
    # `AcceptanceCriterion-[:VALIDATES]->Transition` had zero instances — the
    # fact every generated agent reports as the reason `trace` cannot reach a
    # requirement.
    drafted = _land_drafts(context, outcome.episode_id)

    evidence = _land_evidence(context, outcome.episode_id, model_plan=plan)

    findings = carry_findings(context)
    return (PASSED,
            f"{outcome.nodes_written} node(s), {outcome.edges_written} edge(s) "
            f"— episode {outcome.episode_id}{carried}{drafted}{evidence}",
            findings, "")


def carry_findings(context) -> tuple:
    """Every approval this run took away, and every rename it declined to apply.

    A reviewer re-approving after a code change needs the LIST, not the count:
    "three approvals were revoked" is not something anybody can act on, and
    `carry_human_facts` builds the reasons precisely so they can be shown.

    **Named rather than inlined**, and that is not tidiness. This was three
    lines inside `_land`, so a test could only reach it by writing the same
    expression again — which is what the first test of it did: it rebuilt the
    tuple, asserted on its own copy, imported `handlers` without calling
    anything, and would have passed with the production code deleted. A test
    that cannot fail for the reason it claims is the failure mode this
    repository exists to hunt, and it was committed in the test written to
    prevent a silent failure.
    """
    return tuple(
        [f"approval revoked — {reason}"
         for reason in getattr(context, "carry_revocations", ())]
        + [f"rename proposed, NOT applied (I-22) — {pair}"
           for pair in getattr(context, "carry_renames", ())])


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

    # **S-4 and I-17 disagree about a re-ingest, and the flag that settles it
    # was never set.** `landed_at_quarantine` refuses a model carrying Approved
    # elements, because a source that approves its own output has bypassed G1.
    # I-17 says the opposite for an element whose behaviour did not change: its
    # approval is RETAINED, and dropping it would cost a full re-review of the
    # estate on every extraction -- the one cost that compounds.
    #
    # `Context.expect_prior_approval` exists for exactly this and **nothing ever
    # set it**, so the conflict was invisible only because nothing had been
    # approved yet: the pilot estate carried 430 elements, every one `defer`.
    # The first team to approve a model and re-extract would have hit a hard
    # FAIL at `land` with a message accusing their source of bypassing the gate.
    #
    # Set from the carry rather than from the workflow's name: what makes these
    # approvals legitimate is that they came from the GRAPH, on elements whose
    # behaviour is unchanged -- not that the operator ran a particular verb.
    approved_now = sum(1 for e in list(result.model.states.values())
                       + list(result.model.transitions.values())
                       if getattr(e, "lifecycle_state", "") == APPROVED)
    if approved_now:
        context.expect_prior_approval = True

    note = f"; carried {carry.carried} human decision(s)"
    if carry.revoked:
        note += f", revoked {len(carry.revoked)} (behaviour changed — I-17/I-18)"
    if delta.renames:
        note += (f", {len(delta.renames)} rename(s) proposed and NOT applied "
                 f"(I-22) — identity would otherwise reset silently")

    # **Named, not counted — which this said and did not do.**
    #
    # `carry_human_facts` builds `revoked` as a list of "<id>: <reason>" strings
    # precisely so a reviewer can see which approvals were taken away, and its
    # own comment says "a revocation a reviewer cannot see is a decision taken
    # on their behalf". The caller then printed `len(...)`. The intent was
    # written down and the code did the opposite, so the one thing the
    # mechanism exists to make visible was the one thing nobody could see.
    #
    # They ride out as stage findings rather than in the summary line: a run
    # that revoked forty approvals must not push its own outcome off the screen,
    # and `workflow status` is where a reviewer looks for detail.
    context.carry_revocations = list(carry.revoked)
    context.carry_renames = [
        f"{r.kind} {r.removed_id} -> {r.added_id} "
        f"({r.similarity:.0%} similar; confirm it to carry the approval across)"
        for r in delta.renames]
    return note


def evidence_repo(structural, context) -> str:
    """The id namespace for the evidence layer: the REPOSITORY, not the scope.

    **The defect this is named for.** `_land_evidence` passed
    `context.args.scope`. A monorepo is extracted once and landed once per
    deployable, so the same report is landed several times under different
    scopes — and `repo` namespaces every content-derived id in
    `raw_landing`. Six service-scoped runs of one Athena report therefore
    produced six disjoint copies of the whole evidence layer: 870 Endpoint nodes
    for 87 routes, `GET /version` six times with identical anchors, one Class
    name under six `cls:` ids. Nothing reported it, because each run MERGEd
    cleanly onto ids no other run had used.

    The report already carries the answer. `repo` is a field of the pack
    contract, set by the extractor from the checkout it parsed, which is exactly
    the "one repository" the namespacing comment in `raw_landing` describes.

    The scope is the fallback only when the report does not say, so a report
    predating the field still lands somewhere deterministic rather than under
    the empty string.
    """
    return (getattr(structural, "repo", "") or ""
            or getattr(context.args, "scope", "") or "")


def _belongs_to(node, service: str) -> bool:
    """Is this recovered fact part of the deployable the run is modelling?

    By its anchor path, which is the only thing a fact carries that says where
    in the tree it came from — the same basis `raw_landing.service_of` uses, so
    the two cannot disagree about which service a file belongs to.
    """
    if node is None:
        return False
    anchor = (node.properties.get("anchor_file") or "")
    return anchor.split("/", 1)[0] == service


def _land_unmodelled(context, gaps, nodes_by_id) -> str:
    """One `Finding` per user-facing fact the model cannot reach (X-6c).

    **The inversion this makes.** The evidence layer used to justify itself as
    the denominator — "these 34 endpoints exist and 20 have no transition" was
    a question only the graph could answer. That is true, and it is the wrong
    shape: an endpoint with no behavioural model is a DEFECT to close, not a
    fact to keep. As a finding it enters the review queue, carries a remedy, and
    stops existing when somebody models the behaviour.

    `unmodelled` is not a new type — it already means "the source could not
    model this" and was used only for `@ControllerAdvice` mappings, whose
    findings pointed at nothing. These carry an `ABOUT` edge.

    Best-effort, like everything else this function supplements: a run without a
    graph reports nothing rather than failing the stage that succeeded.
    """
    from metis_mcp.mbt.finding_writer import FindingRecord, load, plan_findings
    from metis_mcp.mbt.graph_session import GraphNotConfigured, session

    # **Scoped to the service this run models, and that is not a detail.**
    # `_land_evidence` lands the WHOLE report — every service's endpoints —
    # while the model it is landed beside covers one. Asked unscoped, "nothing
    # reaches this from the model" is trivially true of the other five services
    # and produced 475 findings for 14 real gaps on Athena. An endpoint is only
    # a gap for the run that was supposed to model it.
    service = getattr(context.args, "service", "") or ""
    if service:
        gaps = [g for g in gaps if _belongs_to(nodes_by_id.get(g[0]), service)]

    # `unreachable_surface` returns `(id, label, reason)` — the reason is the
    # sentence it already composed about why nothing reaches this node, so it is
    # carried verbatim rather than re-worded here.
    records = [
        FindingRecord(
            finding_type="unmodelled", severity="advisory", detail=reason,
            remedy="model the behaviour, or record why this entry point is out "
                   "of scope",
            about_label=label, about_id=node_id)
        for node_id, label, reason in gaps]
    if not records:
        return ""
    try:
        with session() as s:
            written = load(s, plan_findings(
                records, project=getattr(context, "project", "") or "",
                job_id=getattr(context.args, "job_id", "workflow"),
                source_connector="evidence"))
    except GraphNotConfigured:
        return "; unmodelled findings not landed — no graph configured"
    except Exception as e:      # a supplement must not fail the stage it serves
        return f"; unmodelled findings not landed — {type(e).__name__}: {e}"
    return f", {written['findings']} unmodelled finding(s)"


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
        # **One namespace, computed once.** The nodes and the edges that point at
        # them must agree about `repo` or the edges MATCH nothing: the planner
        # looked up `ep:e00b38ab…` (repo = the scope) while landing had written
        # `ep:04bc259f…` (repo = the report), so 20 routes ended up with
        # transitions and an Endpoint and no `DERIVED_FROM` between them.
        # `land` reports that as UNMATCHED and does not fail, which is why a
        # single local is the fix rather than remembering to pass the same thing
        # three times.
        repo = evidence_repo(structural, context)
        plan = plan_raw_landing(
            structural,
            journey=getattr(context.args, "journey", "") or "",
            repo=repo,
            behaviour=reports.get("behaviour"),
            job_id=getattr(context.args, "job_id", "workflow"))
        derived = _plan_derivation_edges(plan, context, structural, repo)
        payload = _plan_payload_edges(plan, context, structural, repo)
        # The two kinds the model plan could not land, because their nodes are
        # created by the plan being built right here.
        deferred = _plan_outcome_edges(plan, context, repo)
        if not plan.is_legal:
            return (f"; evidence layer REFUSED — {len(plan.errors)} error(s), "
                    f"first: {plan.errors[0]}")
        with session() as s:
            outcome = _land_stamped(s, plan, context)
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
    # `_resolve_pending` was here — X-19's deferred joins. All four `JoinKind`s
    # joined labels that the 2026-08-31 re-baseline staged out (Table, Query,
    # Route, Page, UiElement), so the mechanism had no subject left. The
    # principle it served survives as `Finding`: a join that cannot be made is
    # recorded as work, not dropped and not invented.

    gaps = facts.unreachable_surface(all_nodes, all_edges)
    stranded = facts.disconnected(all_nodes, all_edges)
    if gaps:
        counts = Counter(label for _, label, _ in gaps)
        note += (", !! " + " ".join(f"{n} {lab}" for lab, n in sorted(counts.items()))
                 + " user-facing and unreachable from the model")
        # **Landed, not just printed.** This count was a line in a log: an
        # endpoint recovered from code that no transition explains is work
        # somebody has to do, and a number in a run note is not a work item —
        # it is gone the moment the terminal scrolls. It lands as a `Finding`
        # of the type that already means "the source could not model this",
        # pointing AT the fact it is about, so it appears in the same review
        # queue as everything else and closes when the behaviour is modelled.
        note += _land_unmodelled(
            context, gaps, {n.properties["id"]: n for n in all_nodes})
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
    if deferred:
        # Named for the same reason, and this one is load-bearing: `Check` at
        # zero is what starves `mbt/dimensions.py`, and it looks identical to a
        # service that genuinely has no recovered guard.
        note += ", evidence " + " ".join(
            f"{n} {label}" for label, n in sorted(deferred.items()) if n)
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


#: Evidence labels whose nodes are written by `plan_raw_landing`, and which the
#: MODEL plan therefore cannot land: it runs first, so a `MERGE` against one of
#: these matches nothing and is reported as `unmatched` rather than failing.
#:
#: `Endpoint`, `Class` and `ExceptionMapping` are absent because the two
#: planners above already re-plan them in this second pass.
#: `test_workflow.py::test_every_evidence_label_written_by_the_raw_layer_has_a_second_pass`
#: asserts this set stays complete, which is what stops a new evidence label
#: being added and silently never landing.
DEFERRED_EVIDENCE_LABELS = ("DeclaredOutcome", "Check")


def _plan_outcome_edges(plan, context, repo: str) -> dict:
    """The transition's own evidence edges into nodes the raw layer writes.

    **The defect this is named for, and it is the silent kind.** `plan_landing`
    walks `EVIDENCE_RELATIONSHIPS` over every transition's `evidence` tuple and
    plans all five kinds, including `-[:DERIVED_FROM]->DeclaredOutcome` and
    `-[:CONSTRAINED_BY]->Check`. But the model plan is landed BEFORE
    `_land_evidence` creates those nodes, so both edges MERGE against a node that
    does not exist yet: `land` reports them as `unmatched` and does not fail.

    `Endpoint`, `Class` and `ExceptionMapping` survived only because
    `_plan_derivation_edges` and `_plan_payload_edges` re-plan them here, after
    the evidence layer exists. `DeclaredOutcome` and `Check` had no such pass, so
    on a real estate the result was **0 of 176 transitions carrying a check**
    while 47 `Check` nodes and 88 `GUARDED_BY` edges sat in the same graph.

    What that cost: `graph_loader.CHECKS_CYPHER` walks
    `Transition -[:DERIVED_FROM]-> DeclaredOutcome -[:GUARDED_BY]-> Check`, so
    `Transition.checks` came back empty for every transition — and
    `mbt/dimensions.py`, four hundred lines implementing §2.4a's whole
    combinatorial reduction, was left with nothing to build a `Chain` from.

    **Ids are read from the evidence tuple, never re-derived.** `_evidence_for`
    computes them with `raw_landing`'s own functions precisely so the two halves
    cannot disagree about what "the id of this outcome" is; re-deriving them here
    would reintroduce the second definition that `evidence_repo` documents.
    """
    from metis_mcp.model_sources.landing import (
        EVIDENCE_RELATIONSHIPS, graph_transition_id,
    )

    model = getattr(context, "model", None)
    if model is None:
        return {}

    surface = getattr(context.args, "surface", "") or model.id.rsplit("-", 1)[-1]
    label = _transition_label(surface)
    planned: dict[str, int] = {}

    for tid, transition in model.transitions.items():
        for evidence_label, node_id in (getattr(transition, "evidence", ()) or ()):
            if evidence_label not in DEFERRED_EVIDENCE_LABELS:
                continue
            relationship = EVIDENCE_RELATIONSHIPS.get(evidence_label)
            if not relationship:
                continue
            plan.edges.append(_edge(label, graph_transition_id(model, tid),
                                    relationship, evidence_label, node_id))
            planned[evidence_label] = planned.get(evidence_label, 0) + 1
    return planned


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

    `test_ontology.EVIDENCE_LAYER` named `-[:REQUIRES]->Field` as `Field`'s
    reader and `-[:EXPECTS]->Class` as `Class`'s — and both were **zero** in a
    real graph. (`-[:EXERCISES]->Parameter` was the third; `Parameter` has since
    been staged out, its content being the transition's own `c_inputs`.) The catalogue documented readers that did not exist, so the payload a
    generated case has to build was reachable from the endpoint and not from the
    behaviour that exercises it.

    Each edge is a join that already exists rather than a new inference:

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
        )

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
    counts = {"REQUIRES": 0, "EXPECTS": 0, "DERIVED_FROM": 0}

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

        # **The loop stays; the `EXERCISES` edge does not.** It pointed at a
        # `Parameter` node carrying the same five values as this parameter's
        # entry in the transition's `c_inputs`, and the label was staged out for
        # exactly that. What the loop is still for is the edge below: the TYPE a
        # parameter carries is on `Class`, which no property duplicates.
        for parameter in getattr(endpoint, "parameters", ()) or ():
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


def _land_drafts(context, episode_id: str) -> str:
    """Land what `ac_draft` produced. Returns a summary, or "" when there is none.

    Separate from the model plan because the two have different shapes and
    different failure modes: a model that will not land is a blocked run, and a
    criterion that will not land is a reported gap. Merging them would make the
    second able to stop the first.
    """
    drafts = list(getattr(context, "drafts", ()) or ())
    if not drafts or context.model is None:
        return ""

    from metis_mcp.mbt.graph_session import GraphNotConfigured, session
    from metis_mcp.model_sources import land
    from metis_mcp.model_sources.ac_drafting import plan_drafts

    plan = plan_drafts(drafts, context.model,
                       surface=getattr(context.args, "surface", "api"),
                       episode_id=episode_id)
    try:
        with session(context.args.uri, context.args.user) as s:
            result = land(s, plan)
    except GraphNotConfigured:
        return ""

    note = (f"; {result.nodes_written} drafted criterion node(s), "
            f"{result.edges_written} VALIDATES edge(s)")
    if result.unmatched:
        # The failure mode this edge is famous for: planned against the generic
        # label, merged against nothing, reported as unmatched and not as an
        # error. Named here so it cannot pass as a clean landing.
        note += (f", !! {len(result.unmatched)} unmatched — a VALIDATES edge "
                 f"that matched no transition means the criteria are in the "
                 f"graph and joined to nothing")
    return note


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
    # `_corroboration_findings` was here. It asked whether a transition's claimed
    # method really calls what the model says, and it was the only reader of the
    # `Method`/`CALLS` layer — a layer the live graph held zero `CALLS` edges of.
    # Both went in the 2026-08-31 re-baseline: a requirement is not stated about
    # a method, and code-versus-model disagreement is what `drift` and
    # `divergence` report, from facts the model actually carries.
    if not records:
        return ""
    try:
        plan = plan_load(
            context.model, project=getattr(context, "project", "") or "",
            journey=getattr(context, "journey", "") or context.model.id,
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


# ---------------------------------------------------------------------------
# change-approval: what a change touched, and which approvals it cost
# ---------------------------------------------------------------------------
#
# **Every part of this existed and none of it was reachable in order.** The carry
# runs inside `land` (`_carry_forward`), the grading lives in `change_review`,
# the file->transition join lives in `impact`, and `engine.changed_files` turns
# two commits into the list `impact` asks for. What was missing was a workflow:
# somebody wanting to approve a change re-ran `model-build` and read a summary
# line, and I-17/I-18's revocations -- the whole point -- arrived as stage
# findings on a run whose name said nothing about change.


@handler("change_impact")
def _change_impact(context) -> tuple:
    """Which recovered behaviour the diff touches, graded by what validates it.

    **Never blocking, and `question` is not `no impact`.** A changed file that
    matched no recovered behaviour is a file the model does not cover, which is
    exactly when a reviewer should look harder -- so it is reported as a finding
    rather than as silence. F-4's rule: the findings ARE the output.
    """
    from metis_mcp import change_review
    from metis_mcp.impact import impact

    since = getattr(context.args, "since", "") or ""
    if not since:
        return (FAILED,
                "no --since given. change-approval compares two commits: pass "
                "--since <commit> (and optionally --until, default HEAD)", (), "")

    repo = getattr(context.args, "repo", "") or getattr(context.args, "path", "")
    if not repo:
        return FAILED, "no repository to diff — pass --repo", (), ""

    from code_analysis.engine import changed_files

    files = changed_files(repo, since, getattr(context.args, "until", "HEAD"))
    if not files:
        return (PASSED,
                f"no files differ between {since} and "
                f"{getattr(context.args, 'until', 'HEAD')} — nothing to review",
                (), "")

    report = impact(files)
    if not report.get("ok"):
        # A graph that cannot be read is not "no impact". Failing here rather
        # than reporting an empty result is the difference between "nothing is
        # affected" and "I could not tell", which C-11 exists to keep apart.
        return FAILED, report.get("reason", "impact could not be computed"), (), ""

    context.impact = report

    depth = None
    if context.model is not None:
        from metis_mcp.viability import classify_depth
        depth = classify_depth(context.model)

    findings = change_review.findings_for(report, depth=depth)
    summary = change_review.summarise(findings)
    context.change_findings = findings

    detail = (f"{len(files)} changed file(s); "
              f"{len(report['impacted_transitions'])} transition(s) touched, "
              f"{report['files_matched']} file(s) matched. {summary['verdict']}")
    if report["files_unmatched"]:
        detail += (f"; {len(report['files_unmatched'])} matched no recovered "
                   f"behaviour")

    outstanding = tuple(
        f"{f['severity']}: {f['what']} "
        f"({f.get('transition_id') or f.get('file')})" for f in findings)
    return PASSED, detail, outstanding, ""


@handler("change_review")
def _change_review(context) -> tuple:
    """The approvals this run took away, and what a reviewer must look at again.

    **Named, never counted.** `carry_human_facts` builds `revoked` as a list of
    "<id>: <reason>" strings precisely so a reviewer can see which approvals went,
    and the first caller of it printed `len(...)`. A revocation a reviewer cannot
    see is a decision taken on their behalf.

    Non-blocking: a change that revokes forty approvals has not failed, it has
    produced forty things to re-decide, and G1 below is where they are decided.
    """
    revocations = list(getattr(context, "carry_revocations", ()) or ())
    renames = list(getattr(context, "carry_renames", ()) or ())
    findings = list(getattr(context, "change_findings", ()) or ())

    # **The consumer these findings already had and never reached.**
    # `risk.candidates.from_change_review` exists for exactly this shape and was
    # wired only into the `risk_candidates` tool, so the workflow that produces
    # the findings and the function that turns them into risk rows ran in
    # separate worlds. Seeding a register from a review is the case
    # `specialists/register/steps/01-shape.md` names -- "an empty register
    # invites an empty identification pass".
    #
    # They stay candidates. Every one carries `derived_from: model` and
    # `probability: None`: Métis observed that a change left behaviour
    # unasserted, which is not a forecast that it will break.
    from metis_mcp.risk.candidates import from_change_review

    context.risk_candidates = from_change_review(findings)

    blocking = [f for f in findings if f["severity"] in change_review_blocking()]

    if not (revocations or renames or blocking):
        return (PASSED,
                "no approval was revoked, no rename was proposed, and nothing "
                "the model can establish blocks this change. That is not a "
                "statement that the change is good (C-11)", (), "")

    detail_parts = []
    if revocations:
        detail_parts.append(f"{len(revocations)} approval(s) revoked (I-17/I-18)")
    if renames:
        detail_parts.append(f"{len(renames)} rename(s) proposed, NOT applied (I-22)")
    if blocking:
        detail_parts.append(f"{len(blocking)} blocking finding(s)")
    if context.risk_candidates:
        detail_parts.append(
            f"{len(context.risk_candidates)} risk candidate(s) for the register")

    outstanding = tuple(
        [f"approval revoked — {r}" for r in revocations]
        + [f"rename proposed, NOT applied (I-22) — {r}" for r in renames]
        + [f"{f['severity']}: {f['what']} "
           f"({f.get('transition_id') or f.get('file')})" for f in blocking])

    return PASSED, "; ".join(detail_parts), outstanding, ""


def change_review_blocking():
    """Imported lazily so `handlers` stays importable with no graph configured."""
    from metis_mcp.change_review import BLOCKING

    return BLOCKING


def _criteria_in_scope(context) -> list:
    """Criteria already in the graph for this journey, as `reconcile` wants them.

    Returns `[]` when there is no graph or no journey — the same shape as "none
    landed", which is correct: a run that cannot look and a run that looked and
    found nothing both yield coverage rather than correctness, and neither should
    claim the comparison ran.
    """
    from metis_mcp.reconciliation import AcceptanceCriterion

    journey = getattr(context.args, "journey", "")
    if not journey:
        return []
    try:
        from metis_mcp.mbt.cli import _criteria_from_graph
    except Exception:                              # noqa: BLE001
        return []

    rows = _criteria_from_graph(context.args) or {}
    return [AcceptanceCriterion(id=criterion_id, text=text)
            for _, (criterion_id, text) in sorted(rows.items())]


def _confirmed_in_scope(context) -> list:
    """VALIDATES edges for this journey, as `reconcile`'s confirmed matches."""
    journey = getattr(context.args, "journey", "")
    if not journey:
        return []
    from metis_mcp.mbt.graph_loader import load_confirmed_matches
    from metis_mcp.mbt.graph_session import GraphNotConfigured, session

    try:
        with session(getattr(context.args, "uri", None),
                     getattr(context.args, "user", None)) as s:
            return load_confirmed_matches(s, journey)
    except GraphNotConfigured:
        return []


@handler("reconcile")
def _reconcile(context) -> tuple:
    """§3.3. Never blocks — the two gap reports ARE the output (F-4, F-5)."""
    from metis_mcp.reconciliation import reconcile

    if context.model is None:
        return FAILED, "no model in scope", (), ""
    criteria = list(getattr(context, "criteria", ()) or ())
    if not criteria:
        # **Read from the graph when the context has none, which model-build
        # always did.** `_reconcile` only ever looked at `context.criteria`, and
        # nothing in `model-build` set it — so the stage reported "no acceptance
        # criteria in scope" whatever the graph held, and reported it as a
        # property of the SCOPE rather than of the workflow. Eight real services
        # ended there, and the cause was read as a missing requirements source.
        criteria = _criteria_in_scope(context)

    if not criteria:
        return (PASSED,
                "no acceptance criteria in scope — S-3: this run yields coverage, "
                "not correctness", (), "")

    # The graph's VALIDATES edges ARE the confirmed matches (X-18). Passing an
    # empty list would report every already-matched criterion as unimplemented
    # and every covered transition as unspecified -- contradicting the graph it
    # just read, in the alarming direction.
    confirmed = list(getattr(context, "confirmed", ()) or ())
    if not confirmed:
        # **`load_confirmed_matches` existed and nothing called it** — the third
        # dead loader in this one chain, after the drafts nothing landed and the
        # criteria nothing read. Without it every VALIDATES edge in the graph was
        # invisible here, so a criterion already joined to its transition was
        # reported as implementing nothing.
        #
        # Provenance rides along, which is what keeps this honest: a
        # `code_derived` draft confirming its own transition is reported as
        # "documentation only", never as "backed by intent" (S-19, C-11).
        confirmed = _confirmed_in_scope(context)

    result = reconcile(context.model, criteria, confirmed)
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

# ---------------------------------------------------------------------------
# Intake -- requirement ingestion as a workflow (§3.2 stages 1 and 2)
# ---------------------------------------------------------------------------

@handler("intake_fetch")
def _intake_fetch(context) -> tuple:
    """Tracker or wiki -> UIF documents on disk.

    Where they come from is CONFIGURATION: the project profile's `requirements`
    block names the system, the items and either a captured response or a base
    URL. That is what makes the scope of a backlog a deployment decision rather
    than an argument somebody has to remember.
    """
    from code_analysis import tracker
    from code_analysis.project_profile import load_project

    project = getattr(context.args, "project", "")
    if not project:
        return FAILED, "intake needs --project naming a profile", (), ""

    try:
        source = load_project(project).requirements
    except Exception as e:                     # ProfileInvalid, or no such file
        return FAILED, f"{project}: {e}", (), ""
    if not source.is_configured:
        return (FAILED,
                f"profile {project!r} declares no `requirements` block, so there "
                f"is nothing to fetch. Add one naming the system, the items, and "
                f"either a fixture_dir or a base_url", (), "")

    out = Path(getattr(context.args, "out", "") or f"tmp/intake/{project}")
    out.mkdir(parents=True, exist_ok=True)

    # **The live path, which this workflow used to refuse.**
    #
    # It returned "a live tracker read needs a transport this workflow does not
    # open. Configure `fixture_dir`, or run `metis intake fetch` directly" — so
    # the flagship requirement-capture workflow was fixture-only while the bare
    # CLI verb had the real thing. The transport is four lines of stdlib
    # (`cli._tracker_get`) and there was never a reason for the split.
    #
    # A profile naming a `fixture_dir` still uses it, and still wins: that is
    # what makes this path testable without anyone having a Jira.
    discovered: list[str] = []
    try:
        if source.fixture_dir:
            read = tracker.from_fixture(
                Path(source.fixture_dir) / f"{source.system}.tracker.json")
        else:
            from metis_mcp.mbt.cli import _tracker_get

            get = _tracker_get(source.token_env, source.system)

            # A query names the items; `read` then fetches each one through the
            # path it always used. "Named items only" still describes every
            # fetch — see `tracker.search`.
            keys = list(source.keys)
            query = (source.query or {}).get("jql") or \
                    (source.query or {}).get("cql") or \
                    (source.query or {}).get("project") or ""
            if query:
                discovered = tracker.search(source.system, source.base_url,
                                            query, get)
                keys = discovered
            if not keys:
                return (FAILED,
                        f"profile {project!r} names neither `requirements.keys` "
                        f"nor a `requirements.query`, so there is nothing to "
                        f"fetch. This reads named items; it does not read a "
                        f"whole tracker by default", (), "")
            read = tracker.read(source.system, source.base_url, keys, get)
    except (tracker.TrackerRefused, OSError, SystemExit) as e:
        return FAILED, f"{source.system}: {e}", (), ""

    # A query has already selected; filtering again by `keys` would intersect
    # two selections and quietly return fewer items than either asked for.
    wanted = set() if discovered else set(source.keys)
    items = [i for i in read.items if not wanted or i.key in wanted]
    # **A key that matched nothing is named, not silently dropped.** "This
    # ticket does not exist" and "I did not look for it" are different answers
    # and only one of them is safe before a review.
    missing = sorted(wanted - {i.key for i in items})

    written = []
    for item in items:
        path = out / f"{item.key}.uif.json"
        path.write_text(json.dumps(tracker.to_uif(item), indent=2,
                                   ensure_ascii=False) + "\n")
        written.append(str(path))

    context.intake_documents = written
    detail = f"{len(written)} UIF document(s) from {source.system} into {out}"
    if discovered:
        detail += f" (query matched {len(discovered)} item(s))"
    if missing:
        detail += f"; {len(missing)} key(s) matched nothing: {', '.join(missing[:5])}"
    return PASSED, detail, (), ""


@handler("intake_validate")
def _intake_validate(context) -> tuple:
    """Every fetched document against the UIF schema, before anything lands.

    `validate_intake` opens the schema the intake skill has always pointed
    producers at and which nothing ever read -- so a document could be malformed
    in five ways and still land. Non-blocking (F-4): a document that fails is
    reported, and landing still refuses it individually.
    """
    from metis_mcp.intakes import SchemaUnavailable, uif_schema_available, validate_uif

    documents = getattr(context, "intake_documents", [])
    if not documents:
        return FAILED, "nothing to validate — fetch produced no documents", (), ""

    available, why = uif_schema_available()
    if not available:
        # F-10: a check that could not run says so rather than passing quietly.
        # "No errors found" and "nothing looked" are different claims.
        return (PASSED, f"{len(documents)} document(s); schema NOT checked — {why}",
                (f"UIF schema unavailable: {why}",), "")

    problems = []
    for path in documents:
        try:
            # Returns a LIST of departures, and raises rather than returning an
            # empty one when it cannot read the schema -- so an empty list here
            # means "checked, and conformant", never "did not look".
            errors = validate_uif(json.loads(Path(path).read_text()))
        except (OSError, ValueError, SchemaUnavailable) as e:
            problems.append(f"{Path(path).name}: {e}")
            continue
        for error in errors[:3]:
            problems.append(f"{Path(path).name}: {error['path']}: {error['message']}")

    detail = f"{len(documents)} document(s) checked"
    if problems:
        detail += f"; {len(problems)} schema problem(s)"
    return PASSED, detail, tuple(problems), ""


@handler("intake_land")
def _intake_land(context) -> tuple:
    """Each document into the graph, at Quarantine.

    One at a time and independently: a single non-conformant ticket is the
    normal case, not a reason to abandon the rest of a backlog.
    """
    from metis_mcp.mbt.graph_session import session
    from metis_mcp.model_sources import intake_landing as intake
    from metis_mcp.model_sources.landing import land

    documents = getattr(context, "intake_documents", [])
    if not documents:
        return FAILED, "nothing to land — fetch produced no documents", (), ""

    landed = requirements = findings = 0
    refused = []
    try:
        return _land_documents(context, documents)
    except Exception as e:                     # driver failures, chiefly
        # The same class of defect as the CLI's bare traceback: a database that
        # is not running is the commonest failure on a new machine, and the
        # workflow reported it as forty lines of neo4j stack. `F-9` already says
        # nothing is retried; what it needed was to say WHAT failed in one line.
        from metis_mcp.mbt.cli import _driver_failures, _graph_failure_message

        if isinstance(e, _driver_failures()):
            return FAILED, f"no graph — {_graph_failure_message(e)}", (), ""
        raise


def _land_documents(context, documents) -> tuple:
    from metis_mcp.mbt.graph_session import session
    from metis_mcp.model_sources import intake_landing as intake
    from metis_mcp.model_sources.landing import land

    landed = requirements = findings = links = 0
    refused = []
    with session(getattr(context.args, "uri", None),
                 getattr(context.args, "user", None)) as s:
        for path in documents:
            try:
                document = intake.load(path)
                plan = intake.plan_intake(
                    document, job_id=getattr(context.args, "run_id", "workflow"),
                    proposed_by=getattr(context.args, "author", ""))
            except intake.IntakeRefused as e:
                refused.append(f"{Path(path).name}: {e}")
                continue
            outcome = land(s, plan)
            if not outcome.ok:
                refused.append(f"{Path(path).name}: {outcome.refused}")
                continue
            landed += 1
            requirements += len(plan.by_label("Requirement"))
            findings += len(plan.by_label("Finding"))
            # Kept so the risk stage below can assess what this run actually
            # landed, rather than re-reading the whole graph and assessing
            # requirements somebody else's run put there.
            context.landed_requirements.extend(
                node.properties["id"] for node in plan.by_label("Requirement")
                if node.properties.get("id"))
            links += len([e for e in plan.edges if e.rel_type == "LINKS_TO"])

    detail = (f"{landed} document(s) landed at Quarantine — "
              f"{requirements} Requirement(s), {findings} Finding(s)")
    if links:
        detail += f", {links} tracker link(s)"
    if refused:
        detail += f"; {len(refused)} refused"
    # Findings from this stage are the refusals: named, because a backlog that
    # half-landed must say which half.
    return PASSED, detail, tuple(refused), ""


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
            glossary_result = _land_stamped(s, glossary_plan, context)
            if not glossary_result.ok:
                return FAILED, glossary_result.refused, (), ""
        behaviour_result = _land_stamped(s, behaviour, context)
        if not behaviour_result.ok:
            return FAILED, behaviour_result.refused, (), ""
        documentation_result = _land_stamped(s, documentation, context)
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
                f"item), then:\n      metis review apply "
                f"{scope_flags} --resume {written}")

    return (HALTED,
            f"{model.id} is not approved — {len(outstanding)} element(s) awaiting "
            f"review. Generating from an unreviewed model would produce "
            f"confidently wrong tests",
            evidence,
            f"metis review export {scope_flags} -o review.json"
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


@handler("prioritise")
def _prioritise(context) -> tuple:
    """Order the generated paths by what a break would go unnoticed on.

    **Risk-based testing's central act, and the one Métis could not perform.**
    ISO/IEC/IEEE 29119-2 defines the approach as test activities *selected and
    prioritised* by risk; `path_generation` is deterministic BFS in id order and
    has no notion of priority, so a batch came out in whatever order the model
    happened to be in.

    **Deterministic, and that is a constraint not a nicety.** P-7 makes path
    generation byte-identical run to run so a regenerated suite diffs cleanly.
    `prioritisation.order` sorts by detectability, then defect-proneness, then
    id -- the last key makes the order total, so two paths alike on both axes
    never swap between runs.

    Ordering only. No path is dropped: risk decides what is tested *first*, and
    dropping the tail would turn a priority into a scope cut nobody approved.
    """
    from metis_mcp.risk import detection, prioritisation, product

    if context.model is None or context.paths is None:
        return FAILED, "no paths in scope — `generate-paths` did not run", (), ""

    model = context.model
    ledger = getattr(context, "ledger", None)
    rows = ledger.rows if ledger is not None else []
    found = detection.detection_over(model.transition_ids(), rows)
    unverifiable = product.unverifiable_ids(model)
    technical = {tid: product.technical_profile(model, tid, unverifiable)
                 for tid in found["scores"]}
    rank = {row["transition_id"]: row["rank"]
            for row in prioritisation.order(found["scores"], technical)}

    unranked = len(rank) + 1

    def key(path):
        # **The transition the path VALIDATES, not the ones it passes through.**
        # A `Path` is setup plus a single validated transition, and the setup is
        # incidental -- it is how the path reaches the behaviour, not what the
        # test is about. Ranking on the setup would order the suite by how it
        # gets somewhere rather than by what it checks when it arrives.
        #
        # `target_key` breaks ties and makes the order total (P-7).
        return (rank.get(path.validated_transition_id, unranked), path.target_key)

    ordered = sorted(context.paths.paths, key=key)
    context.paths = replace(context.paths, paths=ordered)

    top = ordered[0] if ordered else None
    return (PASSED,
            f"{len(ordered)} path(s) ordered by detectability, then "
            f"defect-proneness, then id",
            (f"first: {getattr(top, 'id', '—')}",) if top else (),
            "")


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
            f"metis workflow resume {context.workflow} "
            f"--scope {context.scope} --confirm {AFFIRMATIVE}")


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

    # **Dry-run is the default and selecting anything else is explicit**, the
    # same way `cmd_publish` does it. This handler used to hardcode
    # `DryRunTransport()`, which meant a live transport existed that the MCP
    # surface could not reach at all: `run_workflow` built and validated a real
    # payload and could never send it, while the CLI could. That is not a policy
    # difference, it was an omission — and it made "the CLI is the fullest
    # surface" true for a reason nobody chose.
    #
    # A live transport still needs `METIS_ALLOW_EXTERNAL_WRITES=yes` on the
    # installation, checked inside `publish` before the first send.
    transport = DryRunTransport()
    if getattr(context.args, "transport", "dry-run") == "zephyr-scale":
        from metis_mcp.publishing.zephyr import ZephyrScaleTransport
        transport = ZephyrScaleTransport()

    result = publish(batch, transport, confirmation=confirmation)
    if not result.ok:
        return FAILED, result.refused or "publication refused", (), ""

    # What actually left Métis. A dry run records nothing: it learns no
    # published id, and the next drift comparison reads this ledger.
    from metis_mcp.publishing.drift import record_publication

    recorded = record_publication(ledger, batch.operations, result.sent,
                                  context.cases, dry_run=result.dry_run)
    if recorded:
        ledger.save(default_ledger_path(context.model.id))

    detail = (f"{len(result.sent)} case(s) sent via {result.transport}"
              + (" (dry run — payload built and validated, no network call)"
                 if result.dry_run else f"; {recorded} published id(s) recorded"))
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


@handler("requirement_risk")
def _requirement_risk(context) -> tuple:
    """Assess the risk in what was just landed, before anybody approves it.

    **Requirements management goes through risk management.** A requirement with
    no criteria, wording no two readers satisfy alike, or criteria written from
    the code they check is a risk to the product before it is a documentation
    problem — and the gate that follows is where somebody decides whether to
    accept it. Reporting it after approval would be telling them what they
    should have known.

    Reporting and non-blocking. Landing a risky requirement is not a failed run;
    it is a run whose output needs a decision, which is what the gate is for.

    The assessment is `incomplete` by construction here — business criticality
    and volatility are asked, not gathered — and that word is the finding, not a
    defect in this stage.
    """
    import json

    from metis_mcp import server as tools

    landed = list(getattr(context, "landed_requirements", ()) or ())
    if not landed:
        return PASSED, "no requirement was landed, so none was assessed", (), ""

    outstanding, assessed = [], 0
    for requirement_id in landed[:25]:
        payload = json.loads(tools.requirement_risk(requirement_id))
        if not payload.get("ok"):
            continue
        assessed += 1
        for candidate in payload.get("candidates") or ():
            outstanding.append(
                f"{requirement_id} — {candidate['category']}: "
                f"{candidate['description']}")

    if not assessed:
        return (PASSED,
                "no requirement could be read back — the graph has them, or the "
                "assessment would have run", (), "")
    return (PASSED,
            f"{assessed} requirement(s) assessed, {len(outstanding)} risk(s) "
            f"observed. Every one is `derived_from: model` and carries no "
            f"probability — a person rates them",
            tuple(outstanding[:20]), "")


@handler("risk_weighted")
def _risk_weighted(context) -> tuple:
    """Is the uncovered part the part that matters?

    **The question a coverage figure is asked to answer and cannot.** "80%
    covered" is a different fact depending on which 20% is missing, and until
    now nothing in this workflow could tell the two apart -- `coverage_report`
    produced `unmeasured` entries that `risk.candidates.from_unmeasured` was
    written to consume, and no caller joined them.

    Reporting only, and non-blocking. A concentration of uncovered
    behaviour in the high-band is a finding to act on, not a failed run; the
    gates in this engine are deliberately two and this is not a third.

    Reports a pivot, never a weighted percentage: an ordinal band cannot be
    summed or averaged (`exposure.ORDINAL_BASIS`).
    """
    from metis_mcp.risk import detection, prioritisation, product

    if context.model is None:
        return FAILED, "no model in scope", (), ""
    ledger = getattr(context, "ledger", None)
    if ledger is None:
        return FAILED, "no ledger — `report` did not run", (), ""

    model = context.model
    found = detection.detection_over(model.transition_ids(), ledger.rows)
    unverifiable = product.unverifiable_ids(model)
    technical = {tid: product.technical_profile(model, tid, unverifiable)
                 for tid in found["scores"]}
    report = prioritisation.weighted_coverage(found["scores"], technical,
                                              found["unmeasured"])
    context.risk_coverage = report

    outstanding = tuple(
        f"{band}: {cell['uncovered']} of {cell['total']} uncovered"
        for band, cell in sorted(report["by_band"].items())
        if cell["uncovered"])
    if not outstanding:
        return PASSED, "every profiled behaviour is covered", (), ""
    return (PASSED,
            f"{len(found['blind_spots'])} behaviour(s) nothing would notice "
            f"breaking, by defect-proneness band",
            outstanding, "")


@handler("spec")
def _spec(context) -> tuple:
    from metis_mcp.specgen import build as build_spec

    if context.model is None:
        return FAILED, "no model in scope", (), ""
    context.specification = build_spec(context.model)
    return PASSED, f"specification built for {context.model.id}", (), ""


@handler("writeback")
def _writeback(context) -> tuple:
    """§18.4 / T-15: a hand-edited spec is never overwritten by regeneration.

    **This used to return `PASSED, "written back"` and write nothing.**
    `specgen.writeback.plan_writeback` and `.apply` both existed, were fully
    tested, and were reachable only from `metis spec --write-back` -- so the
    workflow's terminal stage reported a write it had never performed, which is
    the exact failure this codebase treats as worse than an admitted gap. It now
    calls the same two functions the CLI does; there is one writer, not two.
    """
    from metis_mcp.publishing import AFFIRMATIVE
    from metis_mcp.publishing.publish import ConfirmationRefused, confirm
    from metis_mcp.specgen import writeback as spec_writeback
    from metis_mcp.specgen.specification import living_page

    confirmation_word = getattr(context.args, "confirm", None)
    repo = getattr(context.args, "repo", "") or getattr(context.args, "write_back", "")

    if confirmation_word != AFFIRMATIVE:
        return (HALTED,
                f"writing into a product repository needs the literal word "
                f"{AFFIRMATIVE!r} in this run (T-18). A file the team has edited "
                f"is never overwritten (T-15)",
                (),
                f"metis workflow resume {context.workflow} "
                f"--scope {context.scope} --confirm {AFFIRMATIVE} "
                f"--repo <path> --as <your-identity>")

    # Refused rather than skipped: the previous behaviour was to report success
    # with no destination, and "written back" with nowhere to write is the
    # sentence this whole handler exists to stop producing.
    if not repo:
        return (FAILED,
                "no destination: pass --repo <path to the product repository>. "
                "Nothing was written",
                (), "")

    spec = getattr(context, "specification", None)
    if spec is None:
        return FAILED, "no specification in scope — the `spec` stage did not run", (), ""

    feature = getattr(context.args, "feature", "") or spec.journey
    document = living_page(spec, "")
    plan = spec_writeback.plan_writeback(
        repo, {feature: document},
        allow_unapproved=getattr(context.args, "allow_unapproved", False),
        specs={feature: spec})

    try:
        confirmation = confirm(confirmation_word,
                               getattr(context.args, "as_identity", "") or "unknown",
                               getattr(context.args, "batch_size", plan.size))
    except (ConfirmationRefused, ValueError) as e:
        return FAILED, f"refused: {e}", (), ""

    result = spec_writeback.apply(plan, confirmation)
    if not result["ok"]:
        return FAILED, f"refused: {result['refused']}", (), ""

    written = result["written"]
    if not written:
        # A plan that withheld everything is not a successful write, and saying
        # "written back" here would be the original bug in a new place.
        return (PASSED,
                f"nothing written — every document was withheld "
                f"({len(getattr(plan, 'withheld', ()))} withheld)", (), "")
    return PASSED, f"{len(written)} file(s) written back", (), ""


# ---------------------------------------------------------------------------
# risk-review (§ the risk lifecycle).
#
# The shape of this workflow is decided by one fact: **Métis can supply about
# half of what a risk assessment needs, and the half it cannot supply is the
# half that decides the answer.** Business criticality, volatility, regulatory
# exposure, release appetite and rollback are not in any code, graph or test
# run. So `gather` and `open-questions` are two stages rather than one, and the
# gate sits between the machine's half and a person's.
#
# Without the gate the run would compute an assessment from what was reachable
# and present it as whole — which is the failure `inputs.py` exists to prevent,
# expressed as a stage ordering.
# ---------------------------------------------------------------------------

#: The literal that accepts a risk assessment. A person types it; nothing
#: defaults to it, and no timeout supplies it.
RISK_ACCEPTED = "accept-risk"


def _risk_subject(context) -> tuple[str, str, str, str]:
    """`(assessment, subject, journey, surface)` for this run.

    A requirement id and a journey are different scopes, and the run has to know
    which it holds before it can gather anything.
    """
    args = context.args
    requirement = getattr(args, "requirement", "") or ""
    journey = getattr(args, "journey", "") or ""
    surface = getattr(args, "surface", "api") or "api"
    if requirement:
        return "requirement", requirement, journey, surface
    return "release", f"{journey} ({surface})", journey, surface


@handler("risk_gather")
def _risk_gather(context) -> tuple:
    """Read every input Métis can supply, and record which tool supplied each.

    `durable=False`: this reads and writes nothing outside the process, so a
    resumed run may safely repeat it — which is what lets the later stages have
    a populated context without replaying anything that writes.
    """
    from metis_mcp import server

    assessment, subject, journey, surface = _risk_subject(context)
    if assessment == "requirement":
        raw = server.requirement_risk(subject, journey=journey, surface=surface)
    elif journey:
        raw = server.release_risk(journey, surface)
    else:
        return FAILED, "no scope: pass --requirement or --journey", (), ""

    payload = json.loads(raw)
    if not payload.get("ok"):
        return FAILED, payload.get("reason", "the assessment could not run"), (), ""

    context.risk = payload
    gathered = payload.get("gathered") or {}
    return (PASSED,
            f"{len(gathered)} input(s) gathered for {subject}",
            [f"{name} — via the tool that owns it" for name in sorted(gathered)],
            "")


@handler("risk_questions")
def _risk_questions(context) -> tuple:
    """What no tool can answer, in the words to ask.

    **Never blocking** (F-4): the questions are this stage's product, not a
    failure. A run that stopped here would deny the reader the very list they
    need in order to answer.
    """
    payload = context.risk or {}
    missing = payload.get("missing_inputs") or []
    asked = [m for m in missing if m.get("question")]
    if not asked:
        return PASSED, "every input a person owns has an answer", (), ""

    required = [m for m in asked if m.get("required")]
    return (PASSED,
            f"{len(asked)} question(s) for a person, {len(required)} of them "
            f"required — until they are answered this assessment is unfinished, "
            f"which is not the same as low-risk",
            [f"{m['name']}: {m['question']}" for m in asked],
            "")


@handler("risk_assess")
def _risk_assess(context) -> tuple:
    """Candidates from the gathered half only.

    Nothing is invented for an input nobody supplied: a missing input produces
    an entry in `missing_inputs`, never a risk and never silence.
    """
    payload = context.risk or {}
    if not payload:
        return FAILED, "nothing was gathered", (), ""

    candidates = payload.get("candidates") or []
    status = payload.get("status", "incomplete")
    return (PASSED,
            f"{len(candidates)} candidate risk(s); assessment is {status}. "
            f"Every one carries probability: null — Métis observed a gap and "
            f"did not forecast a failure",
            [f"{c['id']}  impact {c['impact']}  {c['description'][:70]}"
             for c in candidates[:20]],
            "")


@handler("risk_gate")
def _risk_gate(context) -> tuple:
    """A person accepts the assessment and owns the ratings. Halts; never decides.

    Mirrors G1 and G2 in refusing a default: there is no accept-on-timeout and
    no accept-because-nothing-was-found. An assessment with **no** candidates
    still needs accepting, because "Métis observed nothing" is a statement about
    Métis, not about the risk.
    """
    payload = context.risk or {}
    given = getattr(context.args, "accept", None)
    who = getattr(context.args, "as_user", "") or ""

    if given == RISK_ACCEPTED and who:
        context.risk_answers = {"accepted_by": who}
        return PASSED, f"assessment accepted by {who}", (), ""

    status = payload.get("status", "incomplete")
    missing = [m["name"] for m in payload.get("missing_inputs") or []
               if m.get("required")]
    detail = [f"{len(payload.get('candidates') or [])} candidate(s) observed"]
    if missing:
        detail.append(f"UNANSWERED, and required: {', '.join(missing)}")
    detail.append("accepting means the ratings become yours, not Métis's")

    return (HALTED,
            f"the assessment is {status} and needs a person. Accepting it takes "
            f"ownership of every probability in it — Métis set none",
            detail,
            f"metis workflow resume {context.workflow} "
            f"--scope {context.scope} --accept {RISK_ACCEPTED} --as <you>")


@handler("risk_document")
def _risk_document(context) -> tuple:
    """Write the Markdown, preserving every edit already in it.

    `durable=True` because it writes. Regeneration goes through
    `document.merge`, so a resumed run cannot delete the probabilities somebody
    set between the first run and this one.
    """
    from metis_mcp.risk import document, inputs

    payload = context.risk or {}
    assessment, subject, _, _ = _risk_subject(context)
    out = getattr(context.args, "out", "") or ""

    doc = document.build(
        assessment, subject,
        gathered=payload.get("gathered") or {},
        answers=context.risk_answers or {},
        candidates=payload.get("candidates") or [])

    if not out:
        return (PASSED,
                "no --out given, so nothing was written. The document is what "
                "this workflow produces; pass --out to keep it",
                (), "")

    target = Path(out)
    existing = target.read_text() if target.exists() else ""
    if existing:
        doc = document.merge(doc, existing)

    # **Recomputed here, after the merge, and not taken from the payload.**
    # `server.requirement_risk` and `server.release_risk` compute completeness
    # with a hardcoded empty answers dict, because at tool-call time no answer
    # has been supplied yet -- correct there, and wrong to carry into a document
    # that has just merged the answers somebody wrote in the file. Passing the
    # payload's status through meant the "Incomplete" banner survived every
    # answer anyone gave, which is the one thing that status must not do.
    doc["completeness"] = inputs.completeness(
        assessment, doc["gathered"], doc["answers"])

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document.render_markdown(doc))

    carried = doc.get("carried_over") or []
    note = (f", keeping {len(carried)} row(s) you added" if carried else "")
    return (PASSED, f"wrote {target}{note}",
            [f"{len(doc['candidates'])} risk(s) in the document"], "")


# ---------------------------------------------------------------------------
# test-design
#
# **A design is a proposal until somebody signs it**, which is why this
# workflow has a gate at all. Métis derives conditions, techniques, levels and
# risk bands; it decides none of them, and a run that stopped after `sections`
# would hand a reader nine tables of proposals with nothing recording that they
# are proposals.
#
# `DESIGN_ACCEPTED` is its own literal rather than a second use of
# `RISK_ACCEPTED`, for the reason the CLI's `--accept` comment already gives
# about `--confirm`: one word that passes two different gates is a word that has
# stopped meaning either.
# ---------------------------------------------------------------------------

DESIGN_ACCEPTED = "accept-design"


def _design_scope(context) -> tuple[str, str, str]:
    """`(journey, surface, requirement_id)` for this run."""
    args = context.args
    journey = getattr(args, "journey", "") or context.scope or ""
    surface = getattr(args, "surface", "api") or "api"
    return journey, surface, getattr(args, "requirement", "") or ""


@handler("design_gather")
def _design_gather(context) -> tuple:
    """Read every input Métis can supply, and record which tool supplied each.

    `durable=False`: this reads and writes nothing outside the process, so a
    resumed run may repeat it safely -- which is what lets the later stages have
    a populated context without replaying anything that writes.
    """
    from metis_mcp import server

    journey, surface, requirement = _design_scope(context)
    if not journey:
        return FAILED, "no scope: pass --journey", (), ""

    payload = json.loads(server.design_report(
        journey=journey, surface=surface, requirement_id=requirement))
    if not payload.get("ok"):
        return FAILED, payload.get("reason", "the design could not be built"), (), ""

    context.design = payload
    gathered = payload.get("gathered") or []
    return (PASSED,
            f"{len(gathered)} input(s) gathered for {journey} ({surface})",
            [f"{name} — via the tool that owns it" for name in gathered],
            "")


@handler("design_sections_build")
def _design_sections(context) -> tuple:
    """Build each section, and say which ones could not be stated.

    **Blocking, unlike `open-questions` beside it.** A section that raised is a
    defect in the design engine and the run should stop; a section that could not
    be *stated* is a reported outcome and passes. Collapsing the two would make a
    broken builder look like a missing answer.
    """
    payload = context.design or {}
    built = payload.get("sections") or []
    if not built:
        return FAILED, "no section was built — `gather` did not run", (), ""

    silent = [s["key"] for s in built
              if not s.get("rows") and s.get("unstatable_because")]
    partial = [s["key"] for s in built
               if s.get("rows") and s.get("unstatable_because")]
    detail = [f"{s['key']}: {s.get('rows', 0)} row(s)" for s in built]
    if silent:
        detail.append(f"could not be stated at all: {', '.join(silent)}")
    if partial:
        detail.append(f"built without some of their inputs: {', '.join(partial)}")
    return (PASSED,
            f"{sum(s.get('rows', 0) for s in built)} row(s) across "
            f"{len(built)} section(s)",
            detail, "")


@handler("design_questions")
def _design_questions(context) -> tuple:
    """What no tool can answer, in the words to ask.

    **Never blocking** (F-4): the questions are this stage's product, not a
    failure. A run that stopped here would withhold the very list somebody needs
    in order to answer.
    """
    payload = context.design or {}
    missing = payload.get("missing_inputs") or []
    asked = [m for m in missing if m.get("question")]
    ungathered = [m for m in missing if not m.get("question")]

    detail = [f"{m['name']}: {m['question']}" for m in asked]
    detail += [f"{m['name']} — not gathered; `{m.get('tool')}` supplies it"
               for m in ungathered]
    return (PASSED,
            f"{len(asked)} question(s) nobody has answered, "
            f"{len(ungathered)} input(s) not gathered",
            detail, "")


@handler("design_gate")
def _design_gate(context) -> tuple:
    """A person accepts the design and owns its decisions. Halts; never decides.

    Refuses a default the way G1 and G2 do: no accept-on-timeout, and no
    accept-because-every-section-built. A design whose sections are all full
    still needs accepting, because "Métis derived this" is a statement about
    Métis rather than a decision about testing.
    """
    payload = context.design or {}
    given = getattr(context.args, "accept", None)
    who = getattr(context.args, "as_user", "") or ""

    if given == DESIGN_ACCEPTED and who:
        context.design_answers = {"accepted_by": who}
        return PASSED, f"design accepted by {who}", (), ""

    status = payload.get("status", "incomplete")
    missing = [m["name"] for m in payload.get("missing_inputs") or []
               if m.get("required")]
    detail = [f"{sum(s.get('rows', 0) for s in payload.get('sections') or [])} "
              f"row(s) proposed"]
    if missing:
        detail.append(f"UNANSWERED, and required: {', '.join(missing)}")
    detail.append("accepting means the decisions become yours, not Métis's")

    return (HALTED,
            f"the design is {status} and needs a person. Métis proposed every "
            f"row in it and decided none of them",
            detail,
            f"metis workflow resume {context.workflow} "
            f"--scope {context.scope} --accept {DESIGN_ACCEPTED} --as <you>")


@handler("design_document")
def _design_document(context) -> tuple:
    """Write the Markdown, preserving every edit already in it.

    `durable=True` because it writes. Regeneration goes through
    `document.merge`, so a resumed run cannot delete a decision somebody
    recorded between the first run and this one.
    """
    from metis_mcp import server
    from metis_mcp.design import document

    journey, surface, requirement = _design_scope(context)
    out = getattr(context.args, "out", "") or ""
    if not out:
        return (PASSED,
                "no --out given, so nothing was written. The document is what "
                "this workflow produces; pass --out to keep it",
                (), "")

    rendered = server.design_report(journey=journey, surface=surface,
                                    requirement_id=requirement,
                                    as_markdown=True)
    target = Path(out)
    existing = target.read_text() if target.exists() else ""
    if existing:
        from metis_mcp.mbt.cli import _merge_rendered

        lost = document.parse_problems(existing)
        rendered = _merge_rendered(rendered, existing)
        if lost:
            # Reported, never dropped silently: a row that lost its shape is an
            # edit somebody made, and losing it is the same defect as
            # overwriting one.
            return (PASSED, f"wrote {target}",
                    [f"{len(lost)} row(s) could not be read and were lost: "
                     f"{', '.join(lost)}"], "")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered)
    findings = document.verify(rendered)
    detail = [f"{len(findings)} structural finding(s)"] if findings else []
    return PASSED, f"wrote {target}", detail, ""


# ---------------------------------------------------------------------------
# intent-review, and the two stages `intake` now runs before it lands anything
#
# **Intent is a pre-processor.** These handlers are shared between the two
# workflows on purpose: a claim from a tracker and a claim somebody authored
# have the same four questions to answer, and two copies of the reading would
# eventually give two answers.
# ---------------------------------------------------------------------------

def _analysis_documents(context) -> list:
    """The documents this run should read, from either workflow's context.

    `intake` fetched files; `intent-review` was given one. Both end up as paths,
    and neither handler needs to know which workflow it is in.
    """
    fetched = getattr(context, "intake_documents", None) or []
    if fetched:
        return list(fetched)
    named = getattr(context.args, "source", "") or ""
    return [Path(named)] if named else []


@handler("intent_analysis")
def _intent_analysis(context) -> tuple:
    """The four readings, consolidated. Never blocking (F-4).

    The gaps are this stage's product, not a failure. A run that stopped here
    would withhold exactly the list somebody needs in order to close them —
    which is the same argument `knowledge_compare` and `risk_questions` make.
    """
    from metis_mcp import server

    documents = _analysis_documents(context)
    if not documents:
        return (FAILED,
                "nothing to read — `fetch` produced no document, and no "
                "--source was named", (), "")

    journey = getattr(context.args, "journey", "") or ""
    surface = getattr(context.args, "surface", "api") or "api"

    combined: list[dict] = []
    blocking: list[str] = []
    subjects: list[dict] = []
    for path in documents:
        target = Path(path)
        if not target.exists():
            return FAILED, f"{target}: no such file", (), ""
        payload = json.loads(server.analysis_report(
            target.read_text(), journey=journey, surface=surface))
        if not payload.get("ok"):
            return FAILED, payload.get("refused", f"{target} could not be read"), (), ""
        combined += payload.get("gaps") or []
        blocking += payload.get("blocking") or []
        subjects += payload.get("subjects") or []

    # **One verdict over every document, and it is the strictest one.** A batch
    # in which one document cannot be represented is a batch that must not land
    # wholesale: `land` writes them together, so a per-document verdict here
    # would be a verdict nothing acts on.
    context.analysis = {
        "status": "not-ready" if blocking else "ready",
        "gaps": combined,
        "blocking": blocking,
        "subjects": subjects,
        "counts": {aspect: len([g for g in combined if g.get("aspect") == aspect])
                   for aspect in ("intent", "requirement", "design", "risk")},
    }

    counts = context.analysis["counts"]
    return (PASSED,
            f"{len(combined)} gap(s) across {len(documents)} document(s): "
            + ", ".join(f"{n} {aspect}" for aspect, n in counts.items()),
            [f"[{g['aspect']}] {g['subject']}: {g['what']}" for g in combined],
            "")


@handler("intent_readiness")
def _intent_readiness(context) -> tuple:
    """Whether this may be imported at all. Halts when it may not.

    **Narrow, deliberately.** It refuses on `not-ready` — a claim that cannot be
    represented honestly, such as a need nobody has specified, which would land
    as a node nothing can ever be checked against (D-1). A claim nobody has
    costed is `ready` and lands with that gap recorded beside it. Refusing those
    too would mean Métis only accepted claims that were already finished, which
    is not what intake is for.
    """
    analysis = getattr(context, "analysis", None)
    if analysis is None:
        return FAILED, "no analysis in scope — the `analysis` stage did not run", (), ""

    if analysis["status"] != "not-ready":
        reported = sum(analysis["counts"].values())
        return (PASSED,
                f"ready to import — {reported} gap(s) recorded, none of them "
                f"blocking",
                ["`ready` means representable, not agreed. It lands at "
                 "Quarantine and a person decides at G1 (S-4)"],
                "")

    # **FAILED, not HALTED, and the difference is the whole point.** A halt
    # waits for a person to decide something. Nobody can decide this: a need
    # with no specification is fixed by specifying it. F-9 requires a failed
    # stage to report what failed AND the explicit action required, which is
    # what the two lists below are.
    return (FAILED,
            f"{len(analysis['blocking'])} gap(s) mean this cannot be "
            f"represented in the graph as it stands. Nothing was landed",
            analysis["blocking"] + [
                "there is no literal that passes this: the claim itself is "
                "what has to change"],
            f"metis intent review <file> -o review.md   # fix the source, then "
            f"metis workflow run {context.workflow} --scope {context.scope}")


@handler("intent_document")
def _intent_document(context) -> tuple:
    """Write the Markdown, preserving every edit already in it."""
    from metis_mcp.analysis import document

    analysis = getattr(context, "analysis", None)
    if analysis is None:
        return FAILED, "no analysis in scope", (), ""

    out = getattr(context.args, "out", "") or ""
    if not out:
        return (PASSED,
                "no --out given, so nothing was written. The document is what "
                "this workflow produces; pass --out to keep it",
                (), "")

    doc = document.build(context.scope, analysis)
    target = Path(out)
    existing = target.read_text() if target.exists() else ""
    if existing:
        doc = document.merge(doc, existing)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document.render_markdown(doc))

    carried = doc.get("carried_over") or []
    note = f", keeping {len(carried)} gap(s) you added" if carried else ""
    return (PASSED, f"wrote {target}{note}",
            [f"{len(doc['gaps'])} gap(s) in the document"], "")
