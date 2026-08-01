"""
Tests for the grafana-metrics connector -- against
connectors/mock_grafana_server.py (a real, disclosed mock; no real Grafana
instance available) and a real Neo4j instance. Spawns the mock server as a
real subprocess, same pattern as test_review_api_server.py.
"""
import os
import subprocess
import sys
import time
import urllib.request

from neo4j import GraphDatabase

from connectors.grafana_connector import run

PORT = 8423
BASE_URL = f"http://127.0.0.1:{PORT}"
NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

_proc = None


def _start_mock():
    global _proc
    env = os.environ.copy()
    env["METIS_MOCK_GRAFANA_PORT"] = str(PORT)
    _proc = subprocess.Popen(
        [sys.executable, "-m", "connectors.mock_grafana_server"],
        cwd=os.path.dirname(os.path.abspath(__file__)), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{BASE_URL}/api/alerts", timeout=1)
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("mock_grafana_server did not start in time")


def _stop_mock():
    if _proc:
        _proc.kill()
        _proc.wait(timeout=10)


def test_real_run_lands_real_alerts_and_incidents():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            s.execute_write(lambda tx: tx.run(
                "MERGE (e:Episode {id: 'grafana-test-episode'}) "
                "SET e.t_recorded = datetime(), e.source_connector = 'grafana-metrics', e.job_id = 'test'"
            ).consume())
            landed = run(BASE_URL, s, "grafana-test-episode")
            assert landed["alerts"] == 2
            assert landed["incidents"] == 1

            rec = s.run(
                "MATCH (a:Alert {id: 'grafana:alert:alert-001'}) RETURN a.title AS title, a.state AS state"
            ).single()
            assert rec["title"] == "Neo4j bolt connection latency high"
            assert rec["state"] == "alerting"
    finally:
        with driver.session() as s:
            s.execute_write(lambda tx: tx.run(
                "MATCH (n) WHERE n.id STARTS WITH 'grafana:' DETACH DELETE n"
            ).consume())
            s.execute_write(lambda tx: tx.run(
                "MATCH (e:Episode {id: 'grafana-test-episode'}) DETACH DELETE e"
            ).consume())
        driver.close()


if __name__ == "__main__":
    if not NEO4J_PASSWORD:
        print("METIS_NEO4J_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)
    _start_mock()
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
        _stop_mock()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
