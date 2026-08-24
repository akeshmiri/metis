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
    component_id,
    persist,
    PersistPlan,
    PlannedEdge,
    PlannedNode,
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
    # `RestServer` on the api surface: a specialisation is written INSTEAD of
    # its parent, so `:Component` here would mean the surface was unknown.
    assert plan.by_label("RestServer"), "a version node must be planned"
    assert not plan.by_label("Component"), (
        "the surface is known, so the specialisation should carry it")
    assert len(plan.by_label("Scenario")) == 16
    assert len(plan.by_label("TestCase")) == 16
    assert not plan.by_label("Run"), (
        "Run was staged out (§8.7): it had a writer here and no reader anywhere")


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
    """Ids are namespaced, because that is what `landing` wrote. This test used
    to assert on bare ids and so encoded the bug: a bare `t06` matches no node."""
    model, result, plan = _plan()
    target = next(p for p in result.paths if p.validated_transition_id == "t06")
    ns = lambda tid: f"{model.id}::{tid}"  # noqa: E731
    pid = next(e.from_id for e in plan.edges
               if e.rel_type == "COVERS" and e.to_id == ns("t06")
               and e.properties["is_validated"])
    setup = sorted(
        (e for e in plan.edges
         if e.rel_type == "COVERS" and e.from_id == pid and not e.properties["is_validated"]),
        key=lambda e: e.properties["sequence"],
    )
    assert [e.to_id for e in setup] == [ns(t) for t in target.setup_transition_ids]
    assert [e.properties["sequence"] for e in setup] == [1, 2, 3, 4]


# --------------------------------------------------------------------------
# The plan must target what `landing` actually wrote
# --------------------------------------------------------------------------

def test_edges_target_the_specialised_label_not_the_parent():
    """A classified transition carries `:ApiCall` INSTEAD of `:Transition`. The
    plan is legal either way — `is_allowed` walks the specialisation chain — and
    then merges nothing. Every CONTAINS and COVERS edge for all thirteen Example
    models came back `unmatched` before this."""
    _, _, plan = _plan()
    targets = {e.to_label for e in plan.edges if e.rel_type in ("CONTAINS", "COVERS")}
    assert "Transition" not in targets, (
        f"an edge is planned against the generic label: {targets}")
    assert "ApiCall" in targets


def test_edges_target_namespaced_ids():
    """Landing writes `{model_id}::{id}`; a bare id is just a string the plan
    accepts and the database cannot find."""
    model, _, plan = _plan()
    for edge in plan.edges:
        if edge.rel_type in ("CONTAINS", "COVERS"):
            assert edge.to_id.startswith(f"{model.id}::"), (
                f"{edge.rel_type} -> {edge.to_id} is not namespaced")


def test_the_ui_surface_gets_uiaction():
    import dataclasses

    model = dataclasses.replace(login_model(), id="login-ui")
    result = generate(model, ALL_TRANSITIONS)
    cases = render(model, result.paths).cases
    plan = plan_persist(model, result, cases, source_fingerprint(model),
                        "ep1", "run-1", commit_sha="a3f21c")
    targets = {e.to_label for e in plan.edges if e.rel_type == "CONTAINS"}
    assert "UiAction" in targets and "ApiCall" not in targets


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

def test_component_id_is_content_derived():
    model = login_model()
    fingerprint = source_fingerprint(model)
    assert component_id(model.id, fingerprint) == component_id(model.id, fingerprint)


def test_same_model_plans_identical_ids_across_runs():
    _, _, first = _plan()
    _, _, second = _plan()
    assert ({n.properties["id"] for n in first.nodes if n.label == "Scenario"}
            == {n.properties["id"] for n in second.nodes if n.label == "Scenario"})


def test_a_changed_model_yields_a_different_version_id():
    model = login_model()
    before = component_id(model.id, source_fingerprint(model))
    old = model.transitions["t06"]
    model.transitions["t06"] = type(old)(
        id=old.id, source=old.source, trigger=old.trigger, target=old.target,
        guard="NOT credentials_valid AND attempts >= 5",
        implementation_status=old.implementation_status, lifecycle_state=old.lifecycle_state,
    )
    assert component_id(model.id, source_fingerprint(model)) != before


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
            written.extend(kwargs["rows"])

    persist(Recorder(), plan)
    assert written, "the recorder saw no rows at all — this assertion was vacuous"
    node_rows = [r for r in written if "props" not in r]
    assert node_rows, "no node rows were written"
    assert all(None not in row.values() for row in node_rows), (
        "a null property should be omitted, not written as null"
    )


# --------------------------------------------------------------------------
# The counts are the database's, not the loop's
# --------------------------------------------------------------------------

def test_counts_come_from_the_database_not_the_plan():
    """`written_edges += 1` after a `session.run` reports a number that cannot
    be wrong, and is therefore worthless. A `MATCH` that finds nothing makes the
    `MERGE` a no-op, and the old writer still claimed the edge."""
    plan = PersistPlan()
    plan.nodes.append(PlannedNode(label="Scenario", properties={"id": "p1"}))
    plan.edges.append(
        PlannedEdge("Scenario", "p1", "COVERS", "Transition", "absent", {}))

    class MergesNothing:
        def run(self, cypher, **kwargs):
            return []

    outcome = persist(MergesNothing(), plan)
    assert outcome.ok
    assert outcome.nodes_written == 0
    assert outcome.edges_written == 0, (
        "an edge whose endpoint is absent was reported as written"
    )


def test_unmatched_edges_are_reported_not_folded_into_the_success():
    """S-4's discipline applied to a write: the gap between what was planned and
    what the database holds is a reported fact, not a rounding error."""
    plan = PersistPlan()
    plan.edges.append(
        PlannedEdge("Scenario", "p1", "COVERS", "Transition", "absent", {}))

    class MergesNothing:
        def run(self, cypher, **kwargs):
            return []

    outcome = persist(MergesNothing(), plan)
    assert len(outcome.unmatched) == 1
    group, shortfall, why = outcome.unmatched[0]
    assert group == "Scenario-[:COVERS]->Transition"
    assert shortfall == "1 of 1"
    # The specialisation trap is the reason this happens in practice, so the
    # message has to name it -- a reader who hits this needs the cause, not the
    # count.
    assert ":ApiCall" in why


def test_writes_are_batched_by_group_not_issued_per_row():
    """One statement per (label) and per (from, rel, to), not per row. At the
    ~23,000 writes an evidence layer produces the difference is not cosmetic."""
    _, _, plan = _plan()
    statements = []

    class Recorder:
        def run(self, cypher, **kwargs):
            statements.append(cypher)

    persist(Recorder(), plan)
    node_labels = {n.label for n in plan.nodes}
    edge_groups = {(e.from_label, e.rel_type, e.to_label) for e in plan.edges}
    assert len(statements) == len(node_labels) + len(edge_groups)
    assert len(statements) < len(plan.nodes) + len(plan.edges), (
        "the writer is still issuing one round trip per row"
    )
    assert all("UNWIND" in s for s in statements)


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


# --------------------------------------------------------------------------
# F-12 : a case in the graph carries what a person executes
# --------------------------------------------------------------------------

def _a_case_with_setup(plan):
    import json

    cases = [n for n in plan.nodes if n.label == "TestCase"]
    for node in cases:
        if node.properties["precondition_count"] > 0:
            return node, json.loads(node.properties["steps_json"])
    raise AssertionError("no case with preconditions was planned")


def test_a_test_case_lands_its_steps():
    """It used to land `id`, `name`, `objective`, `content_hash` — so the node
    was a `Scenario` with an objective, and the steps a tester needs lived only
    in the renderer's dataclass. F-12 makes the graph the interface consumers
    query; a case without its steps forces every reader to re-render it."""
    _, _, plan = _plan()
    node, steps = _a_case_with_setup(plan)
    assert steps, "the case landed with no steps"
    assert all(s["description"] for s in steps)
    assert node.properties["expected_result"], "nothing says what the case claims"


def test_exactly_one_step_asserts():
    """T-1a. Lifted into its own property so a reader can check the invariant
    without parsing JSON."""
    _, _, plan = _plan()
    for node in [n for n in plan.nodes if n.label == "TestCase"]:
        import json
        steps = json.loads(node.properties["steps_json"])
        assert sum(1 for s in steps if s["is_assertion"]) == 1
        assert node.properties["step_count"] == len(steps)
        assert node.properties["precondition_count"] == len(steps) - 1


def test_every_step_traces_to_a_transition():
    """A case traces to the model element by element, not only as a whole."""
    model, _, plan = _plan()
    _, steps = _a_case_with_setup(plan)
    for step in steps:
        assert step["transition_id"] in model.transitions, (
            f"step cites {step['transition_id']!r}, which is not in the model")


def test_the_asserting_step_is_last_and_numbered_zero():
    """Setup steps are 1..n; the act step is 0, matching `COVERS.sequence` so
    the two representations of one walk cannot disagree."""
    _, _, plan = _plan()
    _, steps = _a_case_with_setup(plan)
    assert steps[-1]["is_assertion"] and steps[-1]["n"] == 0
    assert [s["n"] for s in steps[:-1]] == list(range(1, len(steps)))


def test_data_requirements_survive_into_the_graph():
    """T-9: grouped per condition, with the steps each bites on. A tester
    preparing a fixture needs them; re-deriving them means re-rendering."""
    import json

    _, _, plan = _plan()
    cases = [n for n in plan.nodes if n.label == "TestCase"]
    with_data = [json.loads(n.properties["data_requirements_json"]) for n in cases]
    assert any(d for d in with_data), "no case landed any data requirement"
    for requirements in with_data:
        for requirement in requirements:
            assert requirement["condition"]
            assert requirement["kind"]


def test_the_component_specialisation_follows_the_surface():
    """`RestServer` and `WebServer` were declared, catalogued, and written by
    nothing, while `graph_loader` carried a comment asserting they were."""
    import dataclasses

    from metis_mcp.model_sources.landing import component_label_for

    assert component_label_for("api") == "RestServer"
    assert component_label_for("ui") == "WebServer"
    assert component_label_for("") == "Component"

    model = dataclasses.replace(login_model(), id="login-ui")
    result = generate(model, ALL_TRANSITIONS)
    cases = render(model, result.paths).cases
    plan = plan_persist(model, result, cases, source_fingerprint(model),
                        "ep1", "run-1", commit_sha="a3f21c")
    assert plan.by_label("WebServer") and not plan.by_label("RestServer")


def test_every_edge_from_the_component_uses_its_actual_label():
    """An edge planned against `:Component` when the node carries `:RestServer`
    matches nothing and reports no error — the specialisation trap, one level up
    from transitions."""
    _, _, plan = _plan()
    froms = {e.from_label for e in plan.edges if e.rel_type in ("CONTAINS", "HAS_PAGE")}
    assert "Component" not in froms, froms
    assert "RestServer" in froms
