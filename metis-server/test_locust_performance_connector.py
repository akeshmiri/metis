"""
Tests for the locust-performance connector -- against the real
perf/locustfile.py (a genuine Locust script, not synthetic) and a real
Neo4j instance.
"""
import os
import sys

from neo4j import GraphDatabase

from connectors.locust_performance_connector import _extract_tasks, run

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")
LOCUSTFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "perf", "locustfile.py")


def test_extracts_real_tasks_with_correct_weights_and_targets():
    tasks = _extract_tasks(open(LOCUSTFILE).read())
    by_name = {t["task_name"]: t for t in tasks}
    assert by_name["list_quarantine_queue"]["weight"] == 3
    assert by_name["list_quarantine_queue"]["target"] == "/api/quarantine"
    assert by_name["submit_decision"]["weight"] == 1
    assert by_name["submit_decision"]["target"] == "/api/decision"


def test_real_run_reports_unresolved_targets_honestly_not_fabricated():
    """No :Endpoint entities exist in this graph (no API-spec connector
    built) -- every real target must be reported unresolved, never
    silently linked to a fabricated Endpoint node."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            s.execute_write(lambda tx: tx.run(
                "MERGE (e:Episode {id: 'locust-performance:test'}) "
                "SET e.t_recorded = datetime(), e.source_connector = 'locust-performance', e.job_id = 'test'"
            ).consume())
            result = run(LOCUSTFILE, s, episode_id="locust-performance:test")
        assert result["total_tasks"] == 2
        assert result["unresolved"] == 2
        assert result["resolved"] == 0

        with driver.session() as s:
            rec = s.run(
                "MATCH (tc:TestCase) WHERE tc.id CONTAINS 'ReviewApiUser' "
                "RETURN tc.triage_reason AS reason, tc.type AS type LIMIT 1"
            ).single()
        assert rec["reason"] == "unresolved_performance_target"
        assert rec["type"] == "performance", \
            "manifest specifies TestCase(type=performance) -- Pyramid-Gap Check keys off this"
    finally:
        driver.close()


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
