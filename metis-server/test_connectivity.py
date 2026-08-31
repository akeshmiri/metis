"""
What the model can lead you to (spec X-6d, A-6d).

**"Has an edge" is the wrong question and this file exists because of it.** A
method fifteen `CALLS` deep has plenty of edges; five `ExceptionMapping` nodes
that produce a 400 a caller sees had none. Asserted on the landing plans, which
are pure, so the invariant costs no database.

Every claim here was measured on a real twelve-endpoint service first and then
reproduced in `demo_project/` — the conditions are named in each test, and
deleting one silently turns its test into a tautology.
"""
from __future__ import annotations

import json

from metis_mcp.model_sources.raw_landing import plan_raw_landing
from metis_mcp.model_sources.sources import _report_from_dict
from metis_mcp.ontology import facts
from metis_mcp.ontology.labels import ALLOWED_RELATIONSHIPS, KNOWN_LABELS


def _plan(demo_structural, demo_behaviour, **kw):
    return plan_raw_landing(
        _report_from_dict(demo_structural), journey="records", repo="demo-records",
        behaviour=_report_from_dict(demo_behaviour), job_id="connectivity", **kw)


# --------------------------------------------------------------------------
# Nothing lands connected to nothing
# --------------------------------------------------------------------------

def test_no_fact_lands_connected_to_nothing(demo_structural, demo_behaviour):
    """Nine nodes on a real service, of which seven were not supposed to be:
    five `ExceptionMapping`, whose catalogued reader nothing wrote, and two
    `Check` emitted for a branch whose outcome could not be recovered.

    **`ExceptionMapping` is the one exception, and it is connected one step
    later.** Its edge inside this plan was `HANDLED_BY -> Method`, which went
    with `Method` in the 2026-08-31 re-baseline. What reaches it now is
    `Transition -[:DERIVED_FROM]-> ExceptionMapping`, planned by
    `handlers._plan_derivation_edges` once the model exists — a rejection path
    is behaviour, so the transition is the right thing to reach it from. That
    the mechanism exists is asserted below rather than assumed.
    """
    plan = _plan(demo_structural, demo_behaviour)
    stranded = facts.disconnected(plan.nodes, plan.edges)
    assert {label for _, label in stranded} <= {"ExceptionMapping"}, stranded

    from metis_mcp.model_sources.landing import EVIDENCE_RELATIONSHIPS

    assert EVIDENCE_RELATIONSHIPS["ExceptionMapping"] == "DERIVED_FROM", (
        "nothing would connect an ExceptionMapping once the model lands")


def test_the_edge_free_allowance_is_checked_against_the_catalogue():
    """`Episode` is allowed no edges because nothing in the catalogue points at
    it and 690 of 692 nodes reference it by property. An allowance nobody
    rechecks is how the writer/reader claims decayed in the first place, so
    gaining a relationship must fail this rather than pass unnoticed."""
    catalogued = {r.from_label for r in ALLOWED_RELATIONSHIPS}
    catalogued |= {r.to_label for r in ALLOWED_RELATIONSHIPS}
    for label, why in facts.EDGE_FREE.items():
        assert label in KNOWN_LABELS, label
        assert label not in catalogued, (
            f"{label} is allowed to be edge-free because {why} — it now has a "
            f"catalogued relationship, so the allowance is wrong")


# --------------------------------------------------------------------------
# A user-facing fact the model cannot reach is a gap, not a node
# --------------------------------------------------------------------------

def _both_plans(demo_api):
    """Evidence and model together.

    The question is about the JOIN between the two halves, so it can only be
    asked of both: put to the evidence plan alone every fact looks unreachable,
    because there is no model in it to start from. That mistake is why the land
    stage computes this over the union rather than inside `_land_evidence`.
    """
    from metis_mcp.model_sources import get, plan_landing

    result = get("code").produce(
        path=str(demo_api.behaviour), endpoints=str(demo_api.structural),
        journey="records", surface="api")
    model = plan_landing(result, journey="records", job_id="connectivity")
    evidence = plan_raw_landing(
        _report_from_dict(json.loads(demo_api.structural.read_text())),
        journey="records", repo="demo-records",
        behaviour=_report_from_dict(json.loads(demo_api.behaviour.read_text())),
        job_id="connectivity")
    # The edges the workflow plans across the two halves. Without them the union
    # is not what the pipeline actually builds: `Transition -[:DERIVED_FROM]->
    # ExceptionMapping` lives here, and it is the edge that makes a rejection
    # reachable from the behaviour that produces it.
    from types import SimpleNamespace

    from metis_mcp.workflow.handlers import (_plan_derivation_edges,
                                             _plan_payload_edges)

    structural = _report_from_dict(json.loads(demo_api.structural.read_text()))
    context = SimpleNamespace(
        model=result.model,
        args=SimpleNamespace(surface="api", scope="demo-records"))
    _plan_derivation_edges(evidence, context, structural, "demo-records")
    _plan_payload_edges(evidence, context, structural, "demo-records")

    return (list(model.nodes) + list(evidence.nodes),
            list(model.edges) + list(evidence.edges))


def test_the_only_unreachable_surface_facts_are_the_ones_nothing_can_attribute(
        demo_api):
    """**The gap report is the product here, not an empty list.**

    An `@ExceptionHandler` inside a controller is scoped by Spring to that
    controller, so its rejection attaches to known endpoints. A
    `@ControllerAdvice` bean applies to every controller and nothing in the
    annotations says which endpoints can reach the throw — synthesis refuses to
    guess and says so, and the graph must agree rather than quietly attaching it
    to all of them.

    So four of the demo's five mappings are user-facing facts the model cannot
    account for, and that is the answer. On the real service all five were
    in-controller, all five attached, and this list was empty — both outcomes are
    correct and the difference is a property of the code, not of Métis.

    **`GET /json/{id}` joined the list when `Parameter` was staged out, and that
    is a fix rather than a regression.** `_adjacency` walks edges in BOTH
    directions, so the endpoint used to be "reached" backwards through a
    parameter it shares with a modelled one:

        model -> Transition -[EXERCISES]-> Parameter <-[ACCEPTS]- Endpoint

    Sharing the name `id` with another endpoint is not the model accounting for
    it. `demo_project/README.md` declares this endpoint as the **silent
    under-extraction** condition — a mapping stereotype meta-annotated
    `@RequestMapping`, which the pack's literal verb lookup misses, so nothing
    is synthesised. It is no longer silent.
    """
    nodes, edges = _both_plans(demo_api)
    gaps = facts.unreachable_surface(nodes, edges)
    assert {label for _, label, _ in gaps} == {"ExceptionMapping", "Endpoint"}

    endpoints = [g for g in gaps if g[1] == "Endpoint"]
    assert len(endpoints) == 1, endpoints
    by_id = {n.properties["id"]: n for n in nodes}
    assert by_id[endpoints[0][0]].properties["name"] == "GET /json/{id}", (
        "the demo's declared under-extraction condition is what should surface")
    assert len([g for g in gaps if g[1] == "ExceptionMapping"]) == 4


def test_the_graph_gap_and_the_synthesis_finding_agree(demo_api, demo_structural,
                                                       demo_behaviour):
    """Two representations of one fact is where this codebase's real defects come
    from, so the count the graph reports and the count synthesis reports must be
    the same number.

    **Compared per KIND, not as one total.** Synthesis reports what it refused
    to attribute — the estate-wide `@ControllerAdvice` mappings. The graph
    reports that plus anything else the model cannot reach, and since `Parameter`
    was staged out that includes `GET /json/{id}`, whose verb the pack never
    recovered so synthesis had nothing to refuse. Comparing the totals would
    make the two disagree about a fact they are not both describing.
    """
    from code_analysis import synthesis

    nodes, edges = _both_plans(demo_api)
    gaps = facts.unreachable_surface(nodes, edges)
    result = synthesis.synthesise(
        _report_from_dict(demo_behaviour), demo_structural["endpoints"],
        journey="records", surface="api",
        structural=_report_from_dict(demo_structural))
    estate_wide = [f for f in result.findings if "estate-wide @ControllerAdvice" in f]
    mapping_gaps = [g for g in gaps if g[1] == "ExceptionMapping"]
    assert len(estate_wide) == len(mapping_gaps), (
        f"synthesis refused {len(estate_wide)} and the graph reports "
        f"{len(mapping_gaps)} unreachable mapping(s)")


def test_an_exception_mapping_reaches_the_handler_that_maps_it(
        demo_structural, demo_behaviour):
    """`advice_type` is a simple class name that joins to nothing, so the pack
    emits the handler's method id. Five mappings landed connected to nothing
    while `EVIDENCE_LAYER` named `HANDLED_BY` as the reason the label exists.

    `Method` was staged out in the 2026-08-31 re-baseline, so that edge is gone
    and the label's reader is now the transition it explains: a rejection path
    is behaviour, and `ApiCall-[:DERIVED_FROM]->ExceptionMapping` is what makes
    it reachable from the model.
    """
    plan = _plan(demo_structural, demo_behaviour)
    mappings = [n for n in plan.nodes if n.label == "ExceptionMapping"]
    assert mappings, "the demo maps five exceptions"
    for node in mappings:
        assert node.properties.get("exception_type"), (
            "a mapping that does not name its exception explains no rejection")
        assert node.properties.get("status"), "nor its status"


def test_a_guard_no_outcome_references_is_attached_to_its_endpoint(
        demo_structural, demo_behaviour):
    """**The stranded-check condition**, which the demo did not reproduce until
    `RecordResponses.labelFor` existed: a ternary branching to two helpers that
    name no status. The check is real code, so it is attached to the endpoint it
    was found in rather than dropped or left floating.

    `RecordResponses.listOrEmpty` is the counterpart — both branches resolve, an
    outcome references the check, and `GUARDED_BY` is written instead.
    """
    plan = _plan(demo_structural, demo_behaviour)
    edges = [(e.from_label, e.rel_type, e.to_label) for e in plan.edges]
    assert ("Endpoint", "CONSTRAINED_BY", "Check") in edges, "the stranded one"
    assert ("DeclaredOutcome", "GUARDED_BY", "Check") in edges, "the resolved one"


# --------------------------------------------------------------------------
# Compactness — the facts layer serves the model, so it stays small
# --------------------------------------------------------------------------

def test_an_internal_type_is_not_landed(demo_structural, demo_behaviour):
    """`InternalAudit` is reached by no parameter, no response body and no nested
    payload field. On a real service 29 such classes and 126 such fields landed,
    and the model could lead you to none of them."""
    plan = _plan(demo_structural, demo_behaviour)
    names = {n.properties.get("name") for n in plan.nodes}
    assert "InternalAudit" not in names
    assert "RecordDto" in names, "a payload type is not collateral damage"


def test_every_reduction_is_reported(demo_structural, demo_behaviour):
    """X-5a, applied to the whole fact layer: a graph that quietly lost its
    internal types looks exactly like a service that has none."""
    plan = _plan(demo_structural, demo_behaviour)
    reasons = " ".join(why for _, why in plan.skipped)
    assert "no parameter, response body or nested payload field" in reasons


# --------------------------------------------------------------------------
# The catalogue must describe the graph Métis actually builds
# --------------------------------------------------------------------------

# Catalogued, and written by nothing. Each needs a reason and an intended writer;
# a relationship that starts being written must be deleted from here, and one
# that stops appearing must be added deliberately.
UNWRITTEN = {
    # **Corrected estimate.** I judged this "~20 lines" because `intake_landing`
    # already reads a UIF's `scope` block — and `scope` carries `source_system`
    # and `primary_id` and no links at all. A UIF has no field for them, and the
    # extractors that PRODUCE a UIF are not part of Métis, so this is blocked on
    # the document shape rather than on a writer.
    "LINKS_TO": "a UIF carries no links: `scope` has `source_system` and "
                "`primary_id` only. Blocked on the UIF shape, and the extractors "
                "that produce one are not Métis",
    # `ON_EVENT` left this registry when `structure` began writing it. `RENDERS`
    # left it in the 2026-08-31 re-baseline along with `Route` and `Page`: the
    # join it was waiting for cannot be needed by a label that no longer exists.
}


def test_the_catalogue_describes_a_graph_that_is_actually_built(
        demo_structural, demo_behaviour):
    """**This replaces a test that grepped `labels.py` for a comment.**

    `EVIDENCE_LAYER` names a writer and a reader for every evidence label (D-1),
    and it named `Transition-[:EXERCISES]->Parameter` as `Parameter`'s reader
    while nothing wrote it. Prose checked against prose cannot catch that; a plan
    can.

    Relationships reachable only from the model half — the ones `plan_landing`
    and the workflow's own planners write — are out of scope here and covered by
    `test_extraction.py`; this asserts the evidence half, which is where the
    unwritten ones were.
    """
    plan = _plan(demo_structural, demo_behaviour, include_call_graph=True)
    produced = {e.rel_type for e in plan.edges}
    for rel in sorted(produced):
        assert rel not in UNWRITTEN, (
            f"{rel} is produced but still registered as unwritten — delete it "
            f"from UNWRITTEN")
    for rel, why in UNWRITTEN.items():
        assert rel in {r.rel_type for r in ALLOWED_RELATIONSHIPS}, (
            f"{rel} is registered as unwritten and is not in the catalogue")
        assert why, rel


def test_the_evidence_layer_writes_what_the_catalogue_claims_for_it(
        demo_structural, demo_behaviour):
    """Every relationship whose source AND target are evidence labels must appear,
    or be registered. This is the assertion whose absence let four catalogued
    edges go unwritten."""
    EVIDENCE = {"Endpoint", "Parameter", "Class", "Enum", "Field", "Method",
                "DeclaredOutcome", "Check", "ExceptionMapping"}
    plan = _plan(demo_structural, demo_behaviour, include_call_graph=True)
    produced = {e.rel_type for e in plan.edges}
    for spec in ALLOWED_RELATIONSHIPS:
        if spec.from_label in EVIDENCE and spec.to_label in EVIDENCE:
            assert spec.rel_type in produced or spec.rel_type in UNWRITTEN, (
                f"{spec.from_label}-[:{spec.rel_type}]->{spec.to_label} is "
                f"catalogued, both ends are evidence, and the demo corpus "
                f"produces no such edge")


# --------------------------------------------------------------------------
# An unmodelled entry point is a work item, not a line in a log (X-6c)
# --------------------------------------------------------------------------

def test_an_unmodelled_fact_becomes_a_finding_scoped_to_its_own_service():
    """**Zero findings must mean zero gaps, not a broken filter.**

    `_land_evidence` lands the WHOLE report — every service's endpoints — beside
    a model covering one. Asked unscoped, "nothing reaches this from the model"
    is trivially true of the other services: on Athena that produced 475
    findings for 14 real gaps. Scoped, it produced none, which is the right
    answer for that graph and is also what a broken filter looks like — so the
    filter is exercised here directly.
    """
    from types import SimpleNamespace

    from metis_mcp.workflow.handlers import _belongs_to

    mine = SimpleNamespace(properties={
        "id": "ep:1", "anchor_file": "athena-boot-core/src/main/java/X.java"})
    theirs = SimpleNamespace(properties={
        "id": "ep:2", "anchor_file": "athena-boot-tms/src/main/java/Y.java"})

    assert _belongs_to(mine, "athena-boot-core"), (
        "an endpoint in the service being modelled IS that run's gap to close")
    assert not _belongs_to(theirs, "athena-boot-core"), (
        "another service's endpoint is not this run's gap — it is modelled by "
        "its own run")
    assert not _belongs_to(None, "athena-boot-core")
    assert not _belongs_to(
        SimpleNamespace(properties={"id": "ep:3"}), "athena-boot-core"), (
        "a fact with no anchor cannot be attributed to a service")


def test_the_unmodelled_finding_carries_the_reason_and_points_at_the_fact():
    """Today's `unmodelled` findings point at nothing, which is why the count
    was invisible. These carry an ABOUT edge and the reason `unreachable_surface`
    already composed, rather than a re-worded one."""
    from metis_mcp.ontology import facts

    nodes, edges = _plan_nodes_with_a_stranded_endpoint()
    gaps = facts.unreachable_surface(nodes, edges)
    assert gaps, "the fixture must produce a gap or this checks nothing"
    node_id, label, reason = gaps[0]
    assert label == "Endpoint"
    assert "no path of meaningful edges" in reason
    assert node_id


def _plan_nodes_with_a_stranded_endpoint():
    """One Endpoint nothing reaches, plus a State so there is a model to start
    from — `unreachable_surface` seeds its walk on model labels."""
    from types import SimpleNamespace

    node = lambda label, nid, **p: SimpleNamespace(
        label=label, properties={"id": nid, **p})
    return ([node("State", "m::Ready"),
             node("Endpoint", "ep:stranded", anchor_file="svc/src/main/A.java")],
            [])
