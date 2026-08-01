"""
Real integration test for the flat-files connector (Phase 7) -- against
this project's actual corpus/*.md files and a real Neo4j instance, no mocks.
Same acceptance bar as Phase 2 (test_application_code_connector.py):
idempotent, resumable via a real process kill, exact known node count.
"""
import glob
import os
import subprocess
import sys

from neo4j import GraphDatabase

from connectors import flatfiles_connector as connector

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")
CORPUS_GLOB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus", "*.md")


def _expected_count() -> int:
    return len(glob.glob(CORPUS_GLOB))


def _clean_graph():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            s.run("MATCH (e:Episode {source_connector: 'flat-files'}) DETACH DELETE e")
    finally:
        driver.close()


def _episode_count() -> int:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            return s.run(
                "MATCH (e:Episode {source_connector: 'flat-files'}) RETURN count(e) AS c"
            ).single()["c"]
    finally:
        driver.close()


def test_first_run_lands_exact_known_count():
    _clean_graph()
    landed = connector.run(CORPUS_GLOB, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, job_id="test-first-run")
    expected = _expected_count()
    assert landed["landed"] == expected
    assert _episode_count() == expected


def test_second_run_lands_zero():
    _clean_graph()
    connector.run(CORPUS_GLOB, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, job_id="test-idempotency-1")
    landed_second = connector.run(CORPUS_GLOB, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, job_id="test-idempotency-2")
    assert landed_second["landed"] == 0


def test_killed_mid_run_then_restarted_resumes_without_loss_or_duplication():
    _clean_graph()
    env = os.environ.copy()
    env["METIS_FLATFILES_GLOB"] = CORPUS_GLOB

    proc = subprocess.Popen(
        [sys.executable, "-m", "connectors.flatfiles_connector"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    processed = []
    kill_after = 5
    try:
        for line in proc.stdout:
            if line.startswith("PROCESSED"):
                processed.append(line.strip())
                if len(processed) >= kill_after:
                    proc.kill()
                    break
    finally:
        proc.wait(timeout=10)

    assert len(processed) == kill_after
    assert _episode_count() == kill_after

    expected_total = _expected_count()
    landed_resume = connector.run(CORPUS_GLOB, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, job_id="test-resume")
    assert landed_resume["landed"] == expected_total - kill_after
    assert _episode_count() == expected_total


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
