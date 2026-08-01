"""
metis_mcp/quality_report.py -- against real Neo4j fixtures, not the
stochastic demo dataset (whose service_id/release_id linkage is real but
random per run, not deterministic enough to assert exact scope-resolution
counts against). Same fixture/cleanup pattern as test_dq_metrics.py.

Proves the actual gap this module fixes: metis_quality_score's `scope`
parameter used to be accepted by every layer down to dq_metrics.py and
filtered nothing. These tests assert the resolved Requirement set (and
therefore the computed metrics) genuinely differs across scopes.
"""
import os

from neo4j import GraphDatabase

from metis_mcp.quality_report import resolve_scope, build_report, build_release_report
from metis_mcp.behavior_model import load_transition
from metis_mcp.temporal import record_revision

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

_driver = None


def _session():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver.session()


def _run(s, query, **kwargs):
    s.execute_write(lambda tx: tx.run(query, **kwargs).consume())


def _setup():
    with _session() as s:
        _run(s, "MERGE (e:Episode {id: 'qr-test-episode'}) "
                "SET e.t_recorded = datetime(), e.source_connector = 'test', e.job_id = 'test'")

        # A real Service -> Goal -> Capability -> Epic -> Feature -> Requirement
        # chain -- what service_id scoping actually resolves through.
        _run(s, "MERGE (svc:Service {id: 'qr-test-service'}) SET svc.owner_team = 'qrtest', "
                "svc.source_episode_id = 'qr-test-episode'")
        _run(s, "MERGE (g:Goal {id: 'qr-test-goal'}) SET g.domain = 'qrtest', "
                "g.source_episode_id = 'qr-test-episode', g.lifecycle_state = 'Approved'")
        _run(s, "MERGE (c:Capability {id: 'qr-test-cap'}) SET c.source_episode_id = 'qr-test-episode'")
        _run(s, "MERGE (ep:Epic {id: 'qr-test-epic'}) SET ep.source_episode_id = 'qr-test-episode'")
        _run(s, "MERGE (f:Feature {id: 'qr-test-feature'}) SET f.source_episode_id = 'qr-test-episode'")
        _run(s, "MATCH (c:Capability {id: 'qr-test-cap'}), (g:Goal {id: 'qr-test-goal'}) MERGE (c)-[:TRACES_TO]->(g)")
        _run(s, "MATCH (ep:Epic {id: 'qr-test-epic'}), (c:Capability {id: 'qr-test-cap'}) MERGE (ep)-[:TRACES_TO]->(c)")
        _run(s, "MATCH (f:Feature {id: 'qr-test-feature'}), (ep:Epic {id: 'qr-test-epic'}) MERGE (f)-[:TRACES_TO]->(ep)")

        # Requirement A: High-risk, well-corroborated, real AC/Test/Implements
        # coverage, and TRACES_TO a real Release -- the "everything real,
        # everything passes" case.
        _run(s, "MERGE (r:Requirement {id: 'qr-test-req-a'}) SET r.source_episode_id = 'qr-test-episode', "
                "r.ears_pattern = 'EventDriven', r.revision = 1, r.corroboration_count = 2, "
                "r.risk_tag = 'High', r.lifecycle_state = 'Draft', "
                "r.text = 'When an order ships, the system shall notify the customer.'")
        _run(s, "MATCH (r:Requirement {id: 'qr-test-req-a'}), (f:Feature {id: 'qr-test-feature'}) "
                "MERGE (r)-[:TRACES_TO]->(f)")
        _run(s, "MERGE (a:AcceptanceCriterion {id: 'qr-test-ac-a'}) SET a.source_episode_id = 'qr-test-episode', a.revision = 1")
        _run(s, "MATCH (r:Requirement {id: 'qr-test-req-a'}), (a:AcceptanceCriterion {id: 'qr-test-ac-a'}) "
                "MERGE (r)-[:HAS_AC]->(a)")
        _run(s, "MERGE (t:TestCase {id: 'qr-test-tc-a'}) SET t.source_episode_id = 'qr-test-episode'")
        # VERIFIES targets AcceptanceCriterion, never Requirement directly.
        _run(s, "MATCH (t:TestCase {id: 'qr-test-tc-a'}), (a:AcceptanceCriterion {id: 'qr-test-ac-a'}) "
                "MERGE (t)-[:VERIFIES]->(a)")
        _run(s, "MERGE (m:Method {id: 'qr-test-repo:qr/path.py:Impl.method'}) SET m.source_episode_id = 'qr-test-episode'")
        _run(s, "MATCH (m:Method {id: 'qr-test-repo:qr/path.py:Impl.method'}), (r:Requirement {id: 'qr-test-req-a'}) "
                "MERGE (m)-[:IMPLEMENTS]->(r)")
        _run(s, "MERGE (rel:Release {id: 'qr-test-release'}) SET rel.source_episode_id = 'qr-test-episode'")
        _run(s, "MATCH (r:Requirement {id: 'qr-test-req-a'}), (rel:Release {id: 'qr-test-release'}) "
                "MERGE (r)-[:TRACES_TO]->(rel)")
        record_revision(s, "qr-test-req-a", {"lifecycle_state": "Draft"}, "qr-test-episode")

        # A real performance-type TestCase in the same repo, and an
        # SLA-critical Transition implemented by the same Method -- PERF-01's
        # real signal.
        _run(s, "MERGE (pt:TestCase {id: 'qr-test-repo:qr/path.py:perf_test'}) "
                "SET pt.source_episode_id = 'qr-test-episode', pt.type = 'performance'")
        load_transition(s, "qr-test-transition", "qr-test-episode", "qr-test-A", "qr-test-B",
                         "qr-test-trig", "true", implementing_method_id="qr-test-repo:qr/path.py:Impl.method",
                         performance_sla_critical=True)

        # Requirement B: High-risk but UNDER-corroborated (1 source) -- the
        # real SEC-01 hard-gate failure case, NOT traced to the release.
        _run(s, "MERGE (r:Requirement {id: 'qr-test-req-b'}) SET r.source_episode_id = 'qr-test-episode', "
                "r.ears_pattern = 'Ubiquitous', r.revision = 1, r.corroboration_count = 1, "
                "r.risk_tag = 'High', r.lifecycle_state = 'Draft', "
                "r.text = 'The system shall enforce access control.'")
        _run(s, "MATCH (r:Requirement {id: 'qr-test-req-b'}), (f:Feature {id: 'qr-test-feature'}) "
                "MERGE (r)-[:TRACES_TO]->(f)")


def _cleanup():
    with _session() as s:
        _run(s, "MATCH (n) WHERE n.id STARTS WITH 'qr-test-' DETACH DELETE n")


def test_resolve_scope_each_kind_returns_the_real_expected_set():
    _cleanup()
    _setup()
    try:
        with _session() as s:
            req = resolve_scope(s, {"requirement_id": "qr-test-req-a"})
            assert req.requirement_ids == ["qr-test-req-a"]

            svc = resolve_scope(s, {"service_id": "qr-test-service"})
            assert set(svc.requirement_ids) == {"qr-test-req-a", "qr-test-req-b"}

            rel = resolve_scope(s, {"release_id": "qr-test-release"})
            assert rel.requirement_ids == ["qr-test-req-a"]  # only A is traced to the release

            proj = resolve_scope(s, {"project_wide": True})
            assert proj.requirement_ids is None  # unscoped sentinel, not an enumerated list

            missing = resolve_scope(s, {"requirement_id": "qr-test-does-not-exist"})
            assert missing.requirement_ids == []
    finally:
        _cleanup()


def test_functional_score_scoped_to_a_single_requirement_reflects_only_that_one():
    _cleanup()
    _setup()
    try:
        with _session() as s:
            report = build_report(s, {"requirement_id": "qr-test-req-a"}, attributes=["functional"])
        functional = [m for m in report["detail"]["dimension_breakdown"] if m["dimension"] == "functional"]
        by_id = {m["metric_id"]: m for m in functional}
        assert by_id["DQ-003"]["value"] == 1.0  # req-a's ears_pattern is EventDriven, real conformance
        assert by_id["DQ-006"]["value"] is None  # req-a's lifecycle_state is Draft, not Approved -- honest, not fabricated
        assert by_id["DQ-008"]["value"] == 1.0  # real VERIFIES+IMPLEMENTS chain exists for req-a
    finally:
        _cleanup()


def test_security_gate_fails_when_scope_includes_an_undercorroborated_high_risk_requirement():
    _cleanup()
    _setup()
    try:
        with _session() as s:
            single = build_report(s, {"requirement_id": "qr-test-req-a"}, attributes=["security"])
            assert single["gate_status"] == "clear"  # req-a alone: corroboration_count=2, compliant

            both = build_report(s, {"service_id": "qr-test-service"}, attributes=["security"])
            assert both["gate_status"] == "blocked_individual_gate"  # req-b drags SEC-01 below 100%
            assert any("SEC-01" in reason for reason in both["blocking_reasons"])
    finally:
        _cleanup()


def test_performance_score_reflects_real_pyramid_gap_signal():
    _cleanup()
    _setup()
    try:
        with _session() as s:
            report = build_report(s, {"requirement_id": "qr-test-req-a"}, attributes=["performance"])
        perf = report["detail"]["dimension_breakdown"][0]
        assert perf["metric_id"] == "PERF-01"
        # Real repo-prefix match: the performance TestCase lives in the same
        # repo as the SLA-critical Transition's implementing Method.
        assert perf["value"] == 1.0
    finally:
        _cleanup()


def test_release_report_has_a_real_changelog_and_a_gate_consistent_recommendation():
    _cleanup()
    _setup()
    try:
        with _session() as s:
            report = build_release_report(s, "qr-test-release")
        assert report["release_id"] == "qr-test-release"
        assert report["changelog"] != "No tracked changes in this range."
        assert "qr-test-req-a" in report["changelog"]
        if report["gate_status"] == "clear":
            assert report["recommendation"].startswith("Ship it")
        else:
            assert not report["recommendation"].startswith("Ship it")
    finally:
        _cleanup()


if __name__ == "__main__":
    if not NEO4J_PASSWORD:
        import sys
        print("METIS_NEO4J_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)
    import sys
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
