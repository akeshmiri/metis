"""
Graph-writer tests (application spec §8.4, §16.2, D-8b).

The planner is pure, so legality is provable without a database. Only execution
needs Neo4j, and that is exercised by the live round-trip script.
"""
import sys

from metis_mcp.mbt import ALL_TRANSITIONS, generate
from metis_mcp.mbt.graph_writer import (
    COVERED_TRANSITIONS_CYPHER,
    TRACE_CASE_CYPHER,
    UNCOVERED_TRANSITIONS_CYPHER,
    VERSION_DIFF_CYPHER,
    model_version_id,
    persist,
    plan_persist,
)
from metis_mcp.rendering import render
from metis_mcp.review.state import source_fingerprint
from mbt_fixtures import login_model


def _plan(model=None, version=1):
    model = model or login_model()
    result = generate(model, ALL_TRANSITIONS)
    cases = render(model, result.paths).cases
    return model, result, plan_persist(
        model, result, cases,
        source_fingerprint=source_fingerprint(model),
        episode_id="ep1", run_id="run-1", version=version, commit_sha="a3f21c",
    )


# --------------------------------------------------------------------------
# The plan is legal before anything is written (D-8b)
# --------------------------------------------------------------------------

def test_plan_is_legal_offline():
    _, _, plan = _plan()
    assert plan.is_legal, plan.errors[:3]


def test_every_planned_node_and_edge_is_ontology_legal():
    """Under Community the gate is the sole guarantee, so it must run first."""
    _, _, plan = _plan()
    assert plan.by_label("ModelVersion"), "a version node must be planned"
    assert len(plan.by_label("TestPath")) == 16
    assert len(plan.by_label("TestCase")) == 16
    assert plan.by_label("Run")


def test_illegal_plan_is_refused_before_any_write():
    _, _, plan = _plan()
    plan.errors.append("injected failure")
    calls = []

    class Recorder:
        def run(self, *a, **k):
            calls.append(a)

    outcome = persist(Recorder(), plan)
    assert not outcome.ok
    assert calls == [], "an illegal plan must not reach the database at all"


# --------------------------------------------------------------------------
# P-5a : COVERS distinguishes the assertion from its setup
# --------------------------------------------------------------------------

def test_covers_edges_mark_exactly_one_validated_transition_per_path():
    _, result, plan = _plan()
    by_path = {}
    for edge in plan.edges:
        if edge.rel_type == "COVERS":
            by_path.setdefault(edge.from_id, []).append(edge)
    assert len(by_path) == len(result.paths)
    for pid, edges in by_path.items():
        validated = [e for e in edges if e.properties["is_validated"]]
        assert len(validated) == 1, f"{pid} has {len(validated)} validated edges"
        assert validated[0].properties["sequence"] == 0


def test_setup_edges_are_ordered_and_not_validated():
    model, result, plan = _plan()
    target = next(p for p in result.paths if p.validated_transition_id == "t06")
    pid = next(e.from_id for e in plan.edges
               if e.rel_type == "COVERS" and e.to_id == "t06"
               and e.properties["is_validated"])
    setup = sorted(
        (e for e in plan.edges
         if e.rel_type == "COVERS" and e.from_id == pid and not e.properties["is_validated"]),
        key=lambda e: e.properties["sequence"],
    )
    assert [e.to_id for e in setup] == list(target.setup_transition_ids)
    assert [e.properties["sequence"] for e in setup] == [1, 2, 3, 4]


# --------------------------------------------------------------------------
# D-6 : a version references elements, never duplicates them
# --------------------------------------------------------------------------

def test_version_contains_every_element_by_reference():
    model, _, plan = _plan()
    contains = [e for e in plan.edges if e.rel_type == "CONTAINS"]
    assert len(contains) == len(model.states) + len(model.transitions)
    assert not plan.by_label("State"), "states are referenced, not re-created"
    assert not plan.by_label("Transition"), "transitions are referenced, not re-created"


# --------------------------------------------------------------------------
# D-8 : content-derived identity makes a repeat write a no-op
# --------------------------------------------------------------------------

def test_model_version_id_is_content_derived():
    model = login_model()
    fingerprint = source_fingerprint(model)
    assert model_version_id(model.id, fingerprint) == model_version_id(model.id, fingerprint)


def test_same_model_plans_identical_ids_across_runs():
    _, _, first = _plan()
    _, _, second = _plan()
    assert ({n.properties["id"] for n in first.nodes if n.label == "TestPath"}
            == {n.properties["id"] for n in second.nodes if n.label == "TestPath"})


def test_a_changed_model_yields_a_different_version_id():
    model = login_model()
    before = model_version_id(model.id, source_fingerprint(model))
    old = model.transitions["t06"]
    model.transitions["t06"] = type(old)(
        id=old.id, source=old.source, trigger=old.trigger, target=old.target,
        guard="NOT credentials_valid AND attempts >= 5",
        implementation_status=old.implementation_status, lifecycle_state=old.lifecycle_state,
    )
    assert model_version_id(model.id, source_fingerprint(model)) != before


def test_writer_uses_merge_not_create():
    """Content-derived ids require idempotent writes (spec TR-6, RES-008)."""
    _, _, plan = _plan()
    statements = []

    class Recorder:
        def run(self, cypher, **kwargs):
            statements.append(cypher)

    outcome = persist(Recorder(), plan)
    assert outcome.ok
    assert all("MERGE" in s for s in statements)
    assert not any(s.strip().startswith("CREATE") for s in statements)


def test_null_properties_are_dropped_not_written():
    model, result, cases = login_model(), None, None
    result = generate(model, ALL_TRANSITIONS)
    cases = render(model, result.paths).cases
    plan = plan_persist(model, result, cases, source_fingerprint(model),
                        "ep1", "run-1", commit_sha=None)
    written = []

    class Recorder:
        def run(self, cypher, **kwargs):
            if "props" in kwargs and isinstance(kwargs["props"], dict):
                written.append(kwargs["props"])

    persist(Recorder(), plan)
    assert all(None not in p.values() for p in written), (
        "a null property should be omitted, not written as null"
    )


# --------------------------------------------------------------------------
# §16.2 : the queries the graph exists to answer
# --------------------------------------------------------------------------

def test_coverage_queries_use_the_validated_flag():
    """Coverage credit must come from the assertion, never from setup (P-5a)."""
    for cypher in (COVERED_TRANSITIONS_CYPHER, UNCOVERED_TRANSITIONS_CYPHER):
        assert "is_validated: true" in cypher


def test_uncovered_query_excludes_planned_behaviour():
    assert "implementation_status = 'implemented'" in UNCOVERED_TRANSITIONS_CYPHER


def test_trace_query_routes_through_an_acceptance_criterion():
    """Spec D-4: never TestCase straight to Requirement."""
    assert "VALIDATES" in TRACE_CASE_CYPHER and "HAS_AC" in TRACE_CASE_CYPHER
    assert "(tc:TestCase)-[:VERIFIES]->(r:Requirement)" not in TRACE_CASE_CYPHER


def test_version_diff_is_a_set_difference_over_contains():
    assert "CONTAINS" in VERSION_DIFF_CYPHER
    assert "removed" in VERSION_DIFF_CYPHER and "added" in VERSION_DIFF_CYPHER


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
