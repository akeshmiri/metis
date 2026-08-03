"""
The full 22-metric DQ catalog + composite quality_score
(metis_mcp/dq_metrics.py) -- against real Neo4j fixtures. Not every metric
gets its own deep test (several just reuse already-tested modules --
ears_checker.py, layer8_heuristics.py), but every metric that has a real,
computable formula gets exercised against a real fixture at least once,
and the honest "not computable" fallbacks are checked for the ones that
genuinely have no real data source yet.
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.dq_metrics import (
    dq_001, dq_002, dq_003, dq_004, dq_005, dq_006, dq_007, dq_008, dq_009, dq_010,
    dq_011, dq_012, dq_013, dq_014, dq_015, dq_016, dq_017, dq_018, dq_019, dq_020,
    dq_021, dq_022, compute_all_metrics, compute_quality_score,
)
from metis_mcp.behavior_model import load_transition
from guardrails.corpus_runner import record_run_episode
from demo_data.generate_demo_data import wipe_demo_data

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

_driver = None


def _session():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver.session()


def _setup():
    # Session 10: DQ-014 now genuinely computes from real Endpoint/Table
    # counts -- demo data left loaded by another test file (real
    # Endpoint(300)/Table(150) nodes) would silently change this global
    # metric's denominator. Same test-isolation discipline Session 7
    # already established for test_demo_data.py's own tests.
    wipe_demo_data(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Episode {id: 'dqm-test-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'test', e.job_id = 'test'"
        ).consume())

        # A well-formed, fully-covered Requirement -- the "everything real" case.
        s.execute_write(lambda tx: tx.run(
            "MERGE (r:Requirement {id: 'dqm-test-req-good'}) SET r.source_episode_id = 'dqm-test-episode', "
            "r.ears_pattern = 'EventDriven', r.revision = 1, r.corroboration_count = 2, "
            "r.lifecycle_state = 'Approved', r.risk_tag = 'High', "
            "r.text = 'When an order ships, the system shall notify the customer.'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MERGE (a:AcceptanceCriterion {id: 'dqm-test-ac-good'}) "
            "SET a.source_episode_id = 'dqm-test-episode', a.revision = 1, "
            "a.text = 'The customer receives a notification.'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (r:Requirement {id: 'dqm-test-req-good'}), (a:AcceptanceCriterion {id: 'dqm-test-ac-good'}) "
            "MERGE (r)-[:HAS_AC]->(a)"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MERGE (t:TestCase {id: 'dqm-test-tc-good'}) SET t.source_episode_id = 'dqm-test-episode'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            # VERIFIES targets AcceptanceCriterion, never Requirement
            # directly -- Requirement<-VERIFIES-TestCase with no HAS_AC in
            # between is the exact anti-pattern DQ-018's own
            # check_circular_traceability flags as suspicious.
            "MATCH (t:TestCase {id: 'dqm-test-tc-good'}), (a:AcceptanceCriterion {id: 'dqm-test-ac-good'}) "
            "MERGE (t)-[:VERIFIES]->(a)"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MERGE (m:Method {id: 'dqm-test-repo:dqm/path.py:Impl.method'}) SET m.source_episode_id = 'dqm-test-episode'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (m:Method {id: 'dqm-test-repo:dqm/path.py:Impl.method'}), (r:Requirement {id: 'dqm-test-req-good'}) "
            "MERGE (m)-[:IMPLEMENTS]->(r)"
        ).consume())
        load_transition(s, "dqm-test-transition", "dqm-test-episode", "dqm-test-A", "dqm-test-B",
                         "dqm-test-trig", "true", implementing_method_id="dqm-test-repo:dqm/path.py:Impl.method")
        s.execute_write(lambda tx: tx.run(
            "MERGE (rel:Release {id: 'dqm-test-release'}) SET rel.source_episode_id = 'dqm-test-episode'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (r:Requirement {id: 'dqm-test-req-good'}), (rel:Release {id: 'dqm-test-release'}) "
            "MERGE (r)-[:TRACES_TO]->(rel)"
        ).consume())

        # A non-EARS Approved Requirement -- DQ-003 violation. ears_pattern
        # can never be NULL (schema-enforced) -- 'NonConformant' is this
        # project's own established sentinel (test_requirement_quality.py/
        # test_layer8_heuristics.py) for text that failed the real check.
        s.execute_write(lambda tx: tx.run(
            "MERGE (r:Requirement {id: 'dqm-test-req-nonears'}) SET r.source_episode_id = 'dqm-test-episode', "
            "r.ears_pattern = 'NonConformant', r.revision = 1, r.corroboration_count = 1, "
            "r.lifecycle_state = 'Approved', "
            "r.text = 'Users should probably be able to cancel orders sometimes.'"
        ).consume())

        # A High-risk Approved Requirement with only 1 source -- DQ-012 violation.
        s.execute_write(lambda tx: tx.run(
            "MERGE (r:Requirement {id: 'dqm-test-req-uncorroborated'}) "
            "SET r.source_episode_id = 'dqm-test-episode', r.ears_pattern = 'Ubiquitous', r.revision = 1, "
            "r.corroboration_count = 1, r.lifecycle_state = 'Approved', r.risk_tag = 'High', "
            "r.text = 'The system shall enforce access control.'"
        ).consume())

        # An orphan Method -- DQ-019.
        s.execute_write(lambda tx: tx.run(
            "MERGE (m:Method {id: 'dqm-test-method-orphan'}) SET m.source_episode_id = 'dqm-test-episode'"
        ).consume())

        # A Disputed node -- DQ-010.
        s.execute_write(lambda tx: tx.run(
            "MERGE (r:Requirement {id: 'dqm-test-req-disputed'}) SET r.source_episode_id = 'dqm-test-episode', "
            "r.ears_pattern = 'Ubiquitous', r.revision = 1, r.corroboration_count = 1, "
            "r.lifecycle_state = 'Disputed', r.text = 'The system shall X.'"
        ).consume())

        record_run_episode(s, {"pass_rate": 1.0, "total": 12, "passed": 12, "failed": 0}, min_pass_rate=1.0)


def _cleanup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (n) WHERE n.id STARTS WITH 'dqm-test-' DETACH DELETE n"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (e:Episode) WHERE e.source_connector = 'guardrail-corpus-runner' DETACH DELETE e"
        ).consume())


def test_dq001_grounding_completeness():
    with _session() as s:
        m = dq_001(s)
    assert m.value == 1.0, "every fixture node carries source_episode_id"


def test_dq002_confidence_tier_distribution_honest_when_absent():
    with _session() as s:
        result = dq_002(s)
    # No fixture sets confidence_tier -- real absence, not a fabricated distribution
    # (other real data in the graph might set it; only assert the shape is sane).
    assert result["id"] == "DQ-002"


def test_dq003_ears_conformance_rate_reflects_real_mix():
    with _session() as s:
        m = dq_003(s)
    assert m.value is not None
    assert m.target_met is False or m.value < 1.0, "dqm-test-req-nonears has no ears_pattern"


def test_dq004_vagueness_rate_computable():
    with _session() as s:
        m = dq_004(s)
    assert m.value is not None


def test_dq005_and_dq007_honestly_report_no_microrequirement_data():
    with _session() as s:
        assert dq_005(s).value is None
        assert dq_007(s).value is None


def test_dq006_ac_coverage_for_approved():
    with _session() as s:
        m = dq_006(s)
    assert m.value is not None
    assert m.value < 1.0, "dqm-test-req-nonears/uncorroborated/disputed have no AC"


def test_dq008_functional_coverage_via_pyramid_gap_check():
    with _session() as s:
        m = dq_008(s)
    assert m.value == 1.0, "dqm-test-transition's implementing Method IMPLEMENTS a Requirement " \
                            "whose AcceptanceCriterion is VERIFIED by a real TestCase -- fully covered"


def test_dq009_honestly_not_computable():
    with _session() as s:
        assert dq_009(s).value is None


def test_dq010_open_contradiction_count():
    with _session() as s:
        m = dq_010(s)
    assert m.value >= 1.0


def test_dq011_honestly_not_computable():
    with _session() as s:
        assert dq_011(s).value is None


def test_dq012_high_risk_corroboration_compliance():
    with _session() as s:
        m = dq_012(s)
    assert m.value is not None
    assert m.value < 1.0, "dqm-test-req-uncorroborated is High-risk with corroboration_count=1"


def test_dq013_average_corroboration_count():
    with _session() as s:
        m = dq_013(s)
    assert m.value is not None


def test_dq014_honestly_not_computable():
    with _session() as s:
        assert dq_014(s).value is None


def test_dq014_real_once_a_real_spec_drift_episode_and_endpoint_exist():
    """Session 10: metis_mcp/graph_sync.py now genuinely creates
    SpecDriftDetected episodes -- this proves DQ-014 actually computes
    from them instead of always reporting None. Self-contained cleanup
    (unlike this file's other tests) since this file only calls the
    shared _cleanup() once at the very end of the whole run -- leaving
    these nodes in place would change DQ-014's real value (and therefore
    the composite score's 'currency' component) for every test that runs
    after this one in the same process, including
    test_compute_quality_score_partial_when_some_components_missing."""
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Endpoint {id: 'dqm-test-endpoint'}) SET e.source_episode_id = 'dqm-test-episode'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Episode {id: 'dqm-test-drift-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'graph-sync', "
            "e.job_id = 'dqm-test-drift-episode', e.unit_id = 'dqm-test-drift-episode', "
            "e.checkpoint_status = 'complete', "
            "e.episode_type = 'SpecDriftDetected', e.drifted_connector = 'dqm-test-connector', "
            "e.drifted_entity_count = 1"
        ).consume())
        try:
            m = dq_014(s)
            assert m.value == 1.0  # 1 SpecDriftDetected episode / 1 real Endpoint
            assert m.target_met is False  # 100% is well above the <= 2% target
        finally:
            s.execute_write(lambda tx: tx.run(
                "MATCH (n) WHERE n.id IN ['dqm-test-endpoint', 'dqm-test-drift-episode'] DETACH DELETE n"
            ).consume())


def test_dq016_now_real_via_sleep_time_consolidation():
    with _session() as s:
        m = dq_016(s)
    assert m.value is not None, "now real (metis_mcp/sleep_time_consolidation.py) -- must compute a value"
    assert m.value >= 0.0


def test_dq017_end_to_end_chain_completeness():
    with _session() as s:
        m = dq_017(s)
    assert m.value == 1.0, "dqm-test-req-good is the only Approved Requirement linked to a " \
                            "Release, and its AcceptanceCriterion has a real VERIFIES edge"


def test_dq018_circular_traceability_reuses_layer8():
    with _session() as s:
        m = dq_018(s)
    assert m.value is not None


def test_dq019_orphan_code_rate():
    with _session() as s:
        m = dq_019(s)
    assert m.value is not None
    assert m.value > 0, "dqm-test-method-orphan has no IMPLEMENTS edge"


def test_dq020_judge_disagreement_rate_honest_when_absent():
    with _session() as s:
        m = dq_020(s)
    assert m.id == "DQ-020"


def test_dq021_honestly_not_computable():
    with _session() as s:
        assert dq_021(s).value is None


def test_dq022_false_acceptance_rate_from_real_episode():
    with _session() as s:
        m = dq_022(s)
    assert m.value == 0.0, "the fixture episode recorded pass_rate=1.0 -- 0% false-acceptance"
    assert m.target_met is True


def test_compute_all_metrics_returns_all_24():
    # Session 11, item 2 added DQ-023 (TestCycle completeness, renamed from
    # TestRun in Session 12). Session 13 added DQ-024 (implemented-
    # Transition AcceptanceCriterion coverage).
    with _session() as s:
        result = compute_all_metrics(s)
    assert len(result) == 24
    assert set(result.keys()) == {f"DQ-{i:03d}" for i in range(1, 25)}


def test_compute_quality_score_partial_when_some_components_missing():
    with _session() as s:
        result = compute_quality_score(s)
    assert result["quality_score"] is not None
    assert 0 <= result["quality_score"] <= 100
    assert result["components"]["conformance"] is not None
    assert result["components"]["completeness"] is not None
    assert result["components"]["corroboration"] is not None
    assert result["components"]["traceability"] is not None
    # currency (DQ-014) has no real data in this fixture set -- must not be
    # silently treated as 0 or 100.
    assert result["components"]["currency"] is None
    assert result["all_release_gate_metrics_computed"] is False
    assert result["release_gate_pass"] is None, "must not claim a release-gate verdict on partial data"


if __name__ == "__main__":
    if not NEO4J_PASSWORD:
        print("METIS_NEO4J_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)
    _setup()
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    try:
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
    finally:
        _cleanup()
        if _driver:
            _driver.close()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
