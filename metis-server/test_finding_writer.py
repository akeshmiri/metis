"""
Finding landing (application spec §8.2, §8.3; D-6, D-8, F-12, TR-6).

This module had no test and no caller. Both facts were the same fact: nothing
exercised it because nothing used it, so `:Finding` existed in the ontology, in
the generated schema, and in a writer -- and never in the graph.

The live round trip (land a model, land its findings, query them back through
`ABOUT`) runs against a disposable container; what is here is everything that
can be proven without one.
"""
from metis_mcp.mbt import ALL_TRANSITIONS, generate  # noqa: F401  (parity with siblings)
from metis_mcp.mbt.finding_writer import (
    ABOUT_CYPHER,
    CONTAINS_CYPHER,
    FINDING_CYPHER,
    MODEL_VERSION_CYPHER,
    VALIDATION,
    FindingRecord,
    from_divergences,
    from_validation,
    load,
    plan_load,
)
from metis_mcp.mbt.validation import validate
from mbt_fixtures import login_model


class Matches:
    """A database in which every MATCH finds its node."""

    def run(self, cypher, **params):
        return [{"written": 1}]


class MatchesNothing:
    """A database in which no MATCH finds anything — every MERGE a no-op."""

    def run(self, cypher, **params):
        return [{"written": 0}]


def _plan(model=None, findings=None):
    model = model or login_model()
    return model, plan_load(
        model, journey="login", surface="api", version=1, commit="abc123",
        episode="ep-1", run_id="run-1", engine="mbt/1",
        findings=findings if findings is not None else from_validation(
            validate(model), model),
    )


# --------------------------------------------------------------------------
# The planner is pure (D-8b)
# --------------------------------------------------------------------------

def test_planning_touches_no_database():
    _, plan = _plan()
    assert plan.statements
    assert all(isinstance(k, str) and isinstance(c, str) and isinstance(p, dict)
               for k, c, p in plan.statements)


def test_the_same_model_plans_identically_twice():
    """P-7's determinism, applied here so a diff of two loads is meaningful."""
    _, first = _plan()
    _, second = _plan()
    assert [k for k, _, _ in first.statements] == [k for k, _, _ in second.statements]
    assert [p for _, _, p in first.statements] == [p for _, _, p in second.statements]


# --------------------------------------------------------------------------
# The namespacing trap (landing.namespaced_id)
# --------------------------------------------------------------------------

def test_about_ids_are_namespaced_so_the_edge_can_match():
    """A bare element id matches no node: landing writes `{model_id}::{id}`.

    An ABOUT edge that matches nothing is the worst outcome available here — the
    Finding is in the graph and unreachable from the one thing it is about.
    """
    from metis_mcp.model_sources.landing import graph_transition_id

    model, plan = _plan(findings=[FindingRecord(
        finding_type=VALIDATION, severity="advisory", detail="d",
        about_label="Transition", about_id="t01")])
    about = [p for k, _, p in plan.statements if k == "about"]
    assert len(about) == 1
    # **Asserted against what landing WRITES, not against a literal.** A
    # transition carries its natural key since I-2, and this writer composed
    # `{model}::{tid}` from the source's own id — 24 ABOUT edges pointing at
    # nodes that do not exist, reported by the stage as "24 unattached". A
    # literal here would have gone on passing while the edge matched nothing.
    assert about[0]["about_id"] == graph_transition_id(model, "t01")
    assert about[0]["about_id"].startswith(f"{model.id}::")


def test_an_already_namespaced_id_is_not_namespaced_twice():
    """Both forms reach this writer: a model read from a file has bare ids, one
    read from the graph has namespaced ones. Either must resolve to the one id
    the transition was written with."""
    from metis_mcp.model_sources.landing import graph_transition_id

    model, plan = _plan(findings=[FindingRecord(
        finding_type=VALIDATION, severity="advisory", detail="d",
        about_label="Transition", about_id="login-api::t01")])
    about = [p for k, _, p in plan.statements if k == "about"][0]
    assert about["about_id"] == graph_transition_id(model, "t01")
    assert "::login-api::" not in about["about_id"]


def test_contains_matches_the_specialisation_not_just_transition():
    """A classified transition carries :ApiCall INSTEAD of :Transition, so a
    plain `MATCH (n:Transition)` silently matches nothing (D-2)."""
    assert "n:ApiCall" in CONTAINS_CYPHER
    assert "n:UiAction" in CONTAINS_CYPHER


# --------------------------------------------------------------------------
# The counts come from the database, not from the plan
# --------------------------------------------------------------------------

def test_counts_are_read_back_not_returned_from_the_plan():
    _, plan = _plan()
    written = load(Matches(), plan)
    assert written["contains"] == len(login_model().states) + len(login_model().transitions)
    assert written["unmatched"] == []


def test_a_match_that_finds_nothing_is_reported_not_counted():
    """`plan.findings` is the size of what was asked for — identical whether the
    database did the work or not."""
    _, plan = _plan()
    written = load(MatchesNothing(), plan)
    assert written["contains"] == 0
    assert written["about"] == 0
    assert written["unmatched"], "a statement that matched nothing was not reported"
    assert any(item.startswith("CONTAINS -> ") for item in written["unmatched"])


def test_unconditional_merges_still_count_when_nothing_matches():
    """MODEL_VERSION / RUN / FINDING have no MATCH, so they always write. Only
    the two MATCH-first statements can come up empty."""
    _, plan = _plan()
    written = load(MatchesNothing(), plan)
    assert written["versions"] == 1
    assert written["runs"] == 0, "Run is staged out; nothing plans one"
    assert written["findings"] == len([k for k, _, _ in plan.statements
                                       if k == "finding"])


# --------------------------------------------------------------------------
# The adapters (the wiring that did not exist)
# --------------------------------------------------------------------------

def test_validation_findings_keep_their_severity():
    """M-17: `unverifiable` is a third outcome. Folding it into pass or fail
    here would undo the one distinction validation exists to preserve."""
    model = login_model()
    result = validate(model)
    records = from_validation(result, model)
    assert {r.severity for r in records} <= {"blocking", "unverifiable", "advisory"}
    for finding in result.findings:
        for element_id in finding.element_ids:
            # Namespaced at build time: the record id hashes `about_id`, and a
            # bare element id is identical across models.
            match = [r for r in records
                     if r.about_id == f"{model.id}::{element_id}"]
            assert match, f"no record for {element_id}"
            assert any(r.severity == finding.severity for r in match)


def test_divergence_kinds_are_already_finding_types():
    """`Divergence.kind` and `finding_writer`'s constants were written against
    the same rule ids and never connected."""
    from metis_mcp.mbt import cross_surface
    from metis_mcp.mbt import finding_writer

    for name in ("API_ONLY", "UNHANDLED_OUTCOME", "DANGLING_INVOKES",
                 "RESTATED_GUARD"):
        assert getattr(cross_surface, name) == getattr(finding_writer, name)


def test_divergences_land_as_advisory_records():
    class D:
        kind = "api_only"
        element_id = "t01"
        counterpart_id = ""
        detail = "no UI path reaches this"
        remedy = "confirm this is API-only"

    model = login_model()
    records = from_divergences([D()], model)
    assert len(records) == 1
    assert records[0].finding_type == "api_only"
    assert records[0].severity == "advisory"
    assert records[0].model_id == model.id


# --------------------------------------------------------------------------
# D-8 / TR-6 : re-running an extraction is a no-op, not a duplicate
# --------------------------------------------------------------------------

def test_every_statement_is_merge_based():
    _, plan = _plan()
    for _, cypher, _ in plan.statements:
        assert "MERGE" in cypher
        assert not cypher.strip().startswith("CREATE")


def test_the_component_id_is_shared_with_plan_persist():
    """Two Component nodes for one extraction was the bug that made this
    function mint `f"{model.id}@{version}"` a defect rather than a detail."""
    from metis_mcp.mbt.graph_writer import component_id

    model, plan = _plan()
    version_id = [p for k, _, p in plan.statements if k == "version"][0]["id"]
    assert version_id == component_id(model.id, "abc123")


def test_findings_land_at_quarantine():
    """S-4: no source writes Approved, and a finding is evidence for a decision
    rather than the decision."""
    assert "'Quarantine'" in FINDING_CYPHER
    assert "'Quarantine'" in MODEL_VERSION_CYPHER


# --------------------------------------------------------------------------
# Collisions across models — what only a real, multi-service estate shows
# --------------------------------------------------------------------------

def test_the_same_element_name_in_two_models_makes_two_findings():
    """`FindingRecord.id` hashes `about_id`. A bare id like "NoContent204" is
    identical across every service, so seven Example models produced ONE Finding
    node with seven ABOUT edges, carrying whichever model landed last.

    `ABOUT_CYPHER` matches without a label and the uniqueness constraint is
    per-label, so nothing in the database prevented it.
    """
    import dataclasses

    model_a = login_model()
    model_b = dataclasses.replace(login_model(), id="other-api")
    result_a, result_b = validate(model_a), validate(model_b)

    records_a = from_validation(result_a, model_a)
    records_b = from_validation(result_b, model_b)
    assert records_a and records_b

    ids_a = {r.id for r in records_a}
    ids_b = {r.id for r in records_b}
    assert not (ids_a & ids_b), (
        "findings from two models collapsed onto the same node — the id must "
        "distinguish the model, not just the element name"
    )


def test_a_web_element_id_is_still_namespaced():
    """`ui::ApiSpecDetailPage::/spec/::Ok200` already contains `::` while being
    entirely un-namespaced. A containment test concludes it is done and leaves
    it bare, and the ABOUT edge then matches nothing."""
    model = login_model()
    web_id = "ui::ApiSpecDetailPage::/spec/::Ok200"
    _, plan = _plan(model, findings=[FindingRecord(
        finding_type=VALIDATION, severity="blocking", detail="d",
        about_label="Transition", about_id=web_id)])
    about = [p for k, _, p in plan.statements if k == "about"][0]
    assert about["about_id"] == f"{model.id}::{web_id}"


def test_the_component_label_matches_what_plan_persist_writes():
    """Two writers touch one Component node. If they disagree about its label,
    `MERGE` creates a second node rather than updating the first — and the
    dispatch that used to tell these statements apart compared object identity,
    which silently stopped matching the moment the statement was templated."""
    from metis_mcp.model_sources.landing import component_label_for

    _, plan = _plan()
    version = next(c for k, c, _ in plan.statements if k == "version")
    assert component_label_for("api") in version
    assert "MERGE (mv:Component " not in version


def test_the_component_node_carries_every_required_property():
    """Two writers for one label, and they used to disagree.

    `Component` requires `component` (D-6's stable identity half).
    `graph_writer` set it; this module did not. Community edition has no
    property-existence constraints, so nothing complained for as long as the
    only deployment was Community — against Enterprise the validate stage died
    with "Node(53) with label `RestServer` must have the property `component`".

    Asserted against the ontology rather than a hand-written list, so a new
    required property fails here instead of in a database somebody else runs.
    """
    from metis_mcp.mbt.finding_writer import plan_load
    from metis_mcp.mbt.model import Model, State
    from metis_mcp.ontology.labels import LABELS

    model = Model(
        id="records-api",
        states={"Ready": State(id="Ready", name="Ready", surface="api",
                               is_initial=True)},
        transitions={})
    model.reindex()
    plan = plan_load(model, journey="records", surface="api", version=1,
                     commit="abc1234", episode="ep-1", findings=[])

    version = [(cypher, params) for kind, cypher, params in plan.statements
               if kind == "version"]
    assert len(version) == 1
    cypher, params = version[0]
    assert "RestServer" in cypher, "the api surface writes the specialisation"

    required = set(LABELS["Component"].all_required)
    written = {name for name in required if f"mv.{name}" in cypher}
    written |= {"id"} if "{id: $id}" in cypher else set()
    missing = required - written
    assert not missing, f"Component requires {sorted(missing)}, and none is set"
    assert params["component"] == "records-api"


def test_a_plan_missing_a_required_property_is_refused_before_writing():
    """The guard Community edition does not provide.

    Property-existence constraints are Enterprise-only. The community schema's
    own header says required-property enforcement "lives in
    metis_mcp/ontology/validation.py instead" — and only `landing` was calling
    it. This module writes `Component` and `Finding` through its own Cypher, and
    that is exactly where the missing `component` property lived: caught by an
    Enterprise constraint the spec (C1) says we should not have been relying on,
    and by nothing else.
    """
    from metis_mcp.mbt.finding_writer import plan_load, validate_plan
    from metis_mcp.mbt.model import Model, State

    model = Model(
        id="records-api",
        states={"Ready": State(id="Ready", name="Ready", surface="api",
                               is_initial=True)},
        transitions={})
    model.reindex()
    plan = plan_load(model, journey="records", surface="api", version=1,
                     commit="abc1234", episode="ep-1", findings=[])
    assert validate_plan(plan) == [], "the real plan is well-formed"

    # Re-introduce the exact defect, and require it to be caught without a database.
    plan.statements = [
        (kind, cypher.replace("mv.component = $component,\n    ", ""),
         {k: v for k, v in params.items() if k != "component"})
        for kind, cypher, params in plan.statements
    ]
    errors = validate_plan(plan)
    assert errors and "component" in errors[0], errors
    assert "RestServer" in errors[0], "the specialisation is named, not the parent"


def test_load_refuses_the_whole_plan_rather_than_writing_part_of_it():
    """A half-landed finding set is worse than none: the counts look plausible
    and the gap is invisible."""
    import pytest

    from metis_mcp.mbt.finding_writer import LoadPlan, load

    plan = LoadPlan()
    plan.statements = [("finding", "MERGE (f:Finding {id: $id}) SET f.name = $name",
                        {"id": "f1"})]  # no finding_type, which Finding requires

    class Boom:
        def run(self, *a, **k):
            raise AssertionError("nothing may reach the database")

    with pytest.raises(ValueError) as e:
        load(Boom(), plan)
    assert "nothing was written" in str(e.value)
