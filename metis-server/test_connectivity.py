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
    `Check` emitted for a branch whose outcome could not be recovered."""
    plan = _plan(demo_structural, demo_behaviour)
    assert facts.disconnected(plan.nodes, plan.edges) == []


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
    """
    nodes, edges = _both_plans(demo_api)
    gaps = facts.unreachable_surface(nodes, edges)
    assert {label for _, label, _ in gaps} == {"ExceptionMapping"}
    assert len(gaps) == 4, [g[2][:40] for g in gaps]


def test_the_graph_gap_and_the_synthesis_finding_agree(demo_api, demo_structural,
                                                       demo_behaviour):
    """Two representations of one fact is where this codebase's real defects come
    from, so the count the graph reports and the count synthesis reports must be
    the same number."""
    from code_analysis import synthesis

    nodes, edges = _both_plans(demo_api)
    gaps = facts.unreachable_surface(nodes, edges)
    result = synthesis.synthesise(
        _report_from_dict(demo_behaviour), demo_structural["endpoints"],
        journey="records", surface="api",
        structural=_report_from_dict(demo_structural))
    estate_wide = [f for f in result.findings if "estate-wide @ControllerAdvice" in f]
    assert len(estate_wide) == len(gaps)


def test_an_exception_mapping_reaches_the_handler_that_maps_it(
        demo_structural, demo_behaviour):
    """`advice_type` is a simple class name that joins to nothing, so the pack
    now emits the handler's method id. Five mappings landed connected to nothing
    while `EVIDENCE_LAYER` named this edge as the reason the label exists."""
    plan = _plan(demo_structural, demo_behaviour)
    edges = {(e.from_label, e.rel_type, e.to_label) for e in plan.edges}
    assert ("ExceptionMapping", "HANDLED_BY", "Method") in edges


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


def test_the_call_graph_is_bounded_to_what_points_at_it(
        demo_structural, demo_behaviour):
    """Its only reader, `behavior_model.corroborate`, is called by nothing. What
    stays is every method something points at — on a real service 17 of 199."""
    plan = _plan(demo_structural, demo_behaviour)
    methods = [n for n in plan.nodes if n.label == "Method"]
    handled = {e.to_id for e in plan.edges if e.rel_type == "HANDLED_BY"}
    assert methods, "the handlers stay"
    assert all(n.properties["id"] in handled for n in methods), (
        "a landed method is one something points at")


def test_every_reduction_is_reported(demo_structural, demo_behaviour):
    """X-5a, applied to the whole fact layer: a graph that quietly lost its
    internal types looks exactly like a service that has none."""
    plan = _plan(demo_structural, demo_behaviour)
    reasons = " ".join(why for _, why in plan.skipped)
    assert "no parameter, response body or nested payload field" in reasons
    assert "call graph is not landed" in reasons


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
    # `ON_EVENT` left this registry when `structure` began writing it: `on_event`
    # had been read out of the file into `Element.on_event` and never turned into
    # an edge, so the graph held the button and not the click.
    "RENDERS": "Route -> Page needs the route/page join, which belongs on the "
               "resolution engine (X-19) rather than in a writer",
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
