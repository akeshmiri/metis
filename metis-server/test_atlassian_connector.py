"""
Tests for the atlassian-prod connector -- against
connectors/mock_jira_server.py (a real, disclosed mock; no real Atlassian
instance available) and a real Neo4j instance.
"""
import os
import subprocess
import sys
import time
import urllib.request

from neo4j import GraphDatabase

from connectors.atlassian_connector import run

PORT = 8425
BASE_URL = f"http://127.0.0.1:{PORT}"
NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

_proc = None


def _start_mock():
    global _proc
    env = os.environ.copy()
    env["METIS_MOCK_JIRA_PORT"] = str(PORT)
    _proc = subprocess.Popen(
        [sys.executable, "-m", "connectors.mock_jira_server"],
        cwd=os.path.dirname(os.path.abspath(__file__)), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{BASE_URL}/rest/api/2/search", timeout=1)
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("mock_jira_server did not start in time")


def _stop_mock():
    if _proc:
        _proc.kill()
        _proc.wait(timeout=10)


def _cleanup(driver):
    with driver.session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (n) WHERE n.id STARTS WITH 'atlassian-prod:' DETACH DELETE n"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (e:Episode {id: 'atlassian-test-episode'}) DETACH DELETE e"
        ).consume())


def test_real_run_lands_story_as_requirement_and_bug_as_defect():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        _cleanup(driver)
        with driver.session() as s:
            s.execute_write(lambda tx: tx.run(
                "MERGE (e:Episode {id: 'atlassian-test-episode'}) "
                "SET e.t_recorded = datetime(), e.source_connector = 'atlassian-prod', e.job_id = 'test'"
            ).consume())
            landed = run(BASE_URL, s, "atlassian-test-episode")
        assert landed["requirements"] == 1
        assert landed["defects"] == 2, "1 Jira Bug + 1 JSM Service Management request"
        assert landed["confluence_pages"] == 1
        assert landed["compass_services"] == 1
        assert landed["skipped_non_ears"] == 0

        with driver.session() as s:
            req = s.run(
                "MATCH (r:Requirement {id: 'atlassian-prod:PROJ-101'}) RETURN r.ears_pattern AS pattern"
            ).single()
            defect = s.run(
                "MATCH (d:Defect {id: 'atlassian-prod:PROJ-102'}) RETURN d.summary AS summary"
            ).single()
            jsm_defect = s.run(
                "MATCH (d:Defect {id: 'atlassian-prod:SD-55'}) RETURN d.source AS source, d.summary AS summary"
            ).single()
            page = s.run(
                "MATCH (e:Episode {id: 'atlassian-prod:confluence:98765'}) "
                "RETURN e.episode_type AS episode_type, e.title AS title, e.confluence_version AS version"
            ).single()
            service = s.run(
                "MATCH (svc:Service {id: 'atlassian-prod:compass:comp-billing-api'}) RETURN svc.name AS name"
            ).single()
        assert req["pattern"] == "Ubiquitous"
        assert "500" in defect["summary"]
        assert jsm_defect["source"] == "jsm"
        assert "invoice" in jsm_defect["summary"]
        assert page["episode_type"] == "DocumentIngested"
        assert page["title"] == "Billing Service — Refund Policy"
        assert page["version"] == 3
        assert service["name"] == "billing-api"
    finally:
        _cleanup(driver)
        driver.close()


def test_rerun_updates_confluence_episode_in_place_not_a_duplicate():
    """Real proof the (source_connector, unit_id) uniqueness constraint
    fix holds: landing the same page twice must not attempt to create a
    second Episode for the same real Confluence page."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        _cleanup(driver)
        with driver.session() as s:
            s.execute_write(lambda tx: tx.run(
                "MERGE (e:Episode {id: 'atlassian-test-episode'}) "
                "SET e.t_recorded = datetime(), e.source_connector = 'atlassian-prod', e.job_id = 'test'"
            ).consume())
            run(BASE_URL, s, "atlassian-test-episode")
            run(BASE_URL, s, "atlassian-test-episode")  # real second run, same mock data

            count = s.run(
                "MATCH (e:Episode {episode_type: 'DocumentIngested'}) "
                "WHERE e.confluence_page_id = '98765' RETURN count(e) AS c"
            ).single()["c"]
        assert count == 1
    finally:
        _cleanup(driver)
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
