"""
Session 10: real assertions against the live graph for demo_data/
login_example.py -- the concrete proof of the Intent/TestDesign backbone
(State/Transition -> Intent -> {Requirement, AcceptanceCriterion},
Intent -> TestDesign -> TestCase).

Uses the full demo generator (not a standalone fixture) since
login_example.py is wired into generate_demo_data.py as an additive
phase and depends on its episode/helper plumbing -- same integration-test
posture as test_demo_data.py's own tests.
"""
import os
import sys

from neo4j import GraphDatabase

from demo_data.generate_demo_data import generate, wipe_demo_data, Scale
from metis_mcp.temporal import history
from metis_mcp.pyramid_gap_check import check_pyramid_gaps

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

T1 = "demo:login:transition:t1-valid-login"
T3 = "demo:login:transition:t3-lockout"
T10_PLANNED = "demo:login:transition:t10-2fa-enrollment"


def _generate_once():
    wipe_demo_data(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    return generate(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, scale=Scale(factor=0.05), seed=7)


def test_full_chain_resolves_for_a_known_implemented_transition():
    _generate_once()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            rec = s.run(
                """
                MATCH (ac:AcceptanceCriterion)-[:VALIDATES]->(t:Transition {id: $tid})
                MATCH (ac)-[:TRACES_TO]->(i:Intent)
                MATCH (req:Requirement)-[:HAS_AC]->(ac)
                MATCH (req)-[:TRACES_TO]->(i)
                MATCH (td:TestDesign)-[:TRACES_TO]->(i)
                MATCH (td)-[:COVERS]->(ac)
                MATCH (td)-[:PRODUCES]->(tc:TestCase)-[:VERIFIES]->(ac)
                RETURN i.text AS intent, req.text AS req_text, req.ears_pattern AS pattern,
                       count(DISTINCT ac) AS ac_count, count(DISTINCT tc) AS tc_count
                """,
                tid=T1,
            ).single()
        assert rec is not None, "full chain did not resolve for t1-valid-login"
        assert rec["intent"] and rec["req_text"]
        assert rec["pattern"] in ("Ubiquitous", "EventDriven", "StateDriven", "UnwantedBehavior", "Optional")
        assert rec["ac_count"] >= 1
        assert rec["tc_count"] >= 1
    finally:
        driver.close()


def test_planned_transition_has_intent_and_requirement_but_no_test_design():
    """A planned Transition has NO live graph path to its own Intent/
    Requirement -- AcceptanceCriterion-[:VALIDATES]->Transition is the
    only bridge from the backbone to real behavior, and planned
    Transitions correctly have no AcceptanceCriterion yet (nothing to
    validate). So the Intent/Requirement pair is looked up by its own
    known id (login_example.py's own id convention), not by traversing
    from the Transition -- this is the deliberate consequence, not a bug."""
    _generate_once()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        tid_suffix = T10_PLANNED.rsplit(":", 1)[-1]
        with driver.session() as s:
            rec = s.run(
                """
                MATCH (t:Transition {id: $tid})
                OPTIONAL MATCH (i:Intent {id: $intent_id})
                OPTIONAL MATCH (req:Requirement {id: $req_id})
                OPTIONAL MATCH (ac:AcceptanceCriterion)-[:VALIDATES]->(t)
                OPTIONAL MATCH (td:TestDesign)-[:COVERS]->(ac)
                RETURN t.implementation_status AS status, i.text AS intent, req.text AS req,
                       count(DISTINCT ac) AS ac_count, count(DISTINCT td) AS td_count
                """,
                tid=T10_PLANNED, intent_id=f"demo:login:intent:{tid_suffix}",
                req_id=f"demo:login:requirement:{tid_suffix}",
            ).single()
        assert rec["status"] == "planned"
        assert rec["intent"] is not None
        assert rec["req"] is not None
        assert rec["ac_count"] == 0, "planned transitions get no AcceptanceCriterion -- nothing to test yet"
        assert rec["td_count"] == 0, "planned transitions get no TestDesign"
    finally:
        driver.close()


def test_all_requirements_in_example_are_real_ears_conformant():
    _generate_once()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            rec = s.run(
                "MATCH (r:Requirement {source_kind: 'behavior_example'}) "
                "RETURN count(r) AS total, "
                "count(CASE WHEN r.ears_pattern IS NULL THEN 1 END) AS missing_pattern"
            ).single()
        assert rec["total"] == 17  # 16 implemented + 1 planned, all real EARS-conformant
        assert rec["missing_pattern"] == 0
    finally:
        driver.close()


def test_testcase_types_are_all_in_the_new_six_value_taxonomy():
    _generate_once()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            rows = s.run(
                "MATCH (tc:TestCase {source_kind: 'behavior_example'}) RETURN DISTINCT tc.type AS t"
            ).data()
        types = {row["t"] for row in rows}
        assert types, "no TestCase nodes found for the login example"
        assert types <= {"unit", "integration", "api_functional", "web_functional", "e2e", "performance"}
    finally:
        driver.close()


def test_pyramid_gap_check_shows_real_coverage_for_the_login_success_transition():
    _generate_once()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            result = check_pyramid_gaps(s, T1)
        assert result.determinable
        # login-success is the deliberate hot path -- unit/api_functional/
        # web_functional/e2e/performance all real; only integration is a
        # genuine, disclosed gap (no integration-level TestCase exists
        # anywhere in this illustrative example).
        for layer in ("unit", "api_functional", "web_functional", "e2e", "performance"):
            assert result.coverage[layer] is True, f"expected real {layer} coverage for t1"
        assert "integration" in result.gaps
    finally:
        driver.close()


def test_lockout_transition_test_design_names_boundary_value_analysis():
    _generate_once()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            rec = s.run(
                "MATCH (td:TestDesign {id: 'demo:login:testdesign:t3-lockout'}) RETURN td.techniques AS t"
            ).single()
        assert rec is not None
        assert "Boundary Value Analysis" in rec["t"]
    finally:
        driver.close()


def test_real_revision_history_exists_for_login_example_nodes():
    _generate_once()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            chain = history(s, "demo:login:intent:t1-valid-login")
    finally:
        driver.close()
    assert len(chain) >= 1
    assert chain[0].source_episode_id


def test_functional_areas_one_line_query_finds_the_right_transitions():
    """Real, requested extension: a one-line query by functional area must
    find exactly the right Transitions -- login-successful (t1, t1b-e) and
    login-failed (t2a-d, t3) are disjoint, real sets, not overlapping."""
    _generate_once()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            successful = {r["id"] for r in s.run(
                "MATCH (t:Transition) WHERE 'login-successful' IN t.functional_areas "
                "RETURN t.id AS id"
            ).data()}
            failed = {r["id"] for r in s.run(
                "MATCH (t:Transition) WHERE 'login-failed' IN t.functional_areas "
                "RETURN t.id AS id"
            ).data()}
    finally:
        driver.close()
    assert successful == {
        "demo:login:transition:t1-valid-login",
        "demo:login:transition:t1b-valid-login-after-1-failure",
        "demo:login:transition:t1c-valid-login-after-2-failures",
        "demo:login:transition:t1d-valid-login-after-3-failures",
        "demo:login:transition:t1e-valid-login-after-4-failures",
    }
    assert failed == {
        "demo:login:transition:t2a-invalid-login-attempt-1",
        "demo:login:transition:t2b-invalid-login-attempt-2",
        "demo:login:transition:t2c-invalid-login-attempt-3",
        "demo:login:transition:t2d-invalid-login-attempt-4",
        "demo:login:transition:t3-lockout",
    }
    assert successful.isdisjoint(failed)


def test_functional_areas_on_a_shared_state_is_a_real_union():
    """LoggedOut is touched by 5 different Transitions across 5 different
    sub-flows (login-successful via t1, login-failed via t2a, password-reset
    via t4, session-management via t7, account-recovery via t8) -- its
    functional_areas must be the real union of all of them, not just
    whichever Transition happened to write last."""
    _generate_once()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            rec = s.run(
                "MATCH (s:State {id: 'demo:login:state:LoggedOut'}) RETURN s.functional_areas AS areas"
            ).single()
    finally:
        driver.close()
    assert set(rec["areas"]) == {
        "login", "login-successful", "login-failed",
        "password-reset", "session-management", "account-recovery",
    }


if __name__ == "__main__":
    if not NEO4J_PASSWORD:
        print("METIS_NEO4J_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)
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
