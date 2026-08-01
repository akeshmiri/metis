"""
Real integration test for the application-code connector (Phase 2) --
against a real mock Athena Postgres and a real Neo4j instance, not mocked.
Each test cleans the connector's own Episode/Repository nodes first so runs
are independent, then re-seeds the mock Athena tables (idempotent upsert,
see seed_mock_athena.py) so the expected counts are known and stable.

Requires: metis-athena-mock (Postgres) and metis-neo4j (Neo4j) containers
running, and METIS_ATHENA_DSN / METIS_NEO4J_PASSWORD set.
"""
import os
import subprocess
import sys

from neo4j import GraphDatabase

from connectors import application_code_connector as connector
from connectors.seed_mock_athena import seed as seed_mock_athena

PG_DSN = os.environ.get("METIS_ATHENA_DSN", "postgresql://athena:athena-mock-pass@localhost:5432/athena_mock")
NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

def _expected_source_file_count() -> int:
    """Computed fresh, not hardcoded -- a hardcoded count already went stale
    once this session (metis_mcp/*.py legitimately gained files between
    Phase 2 and Phase 4), which is exactly the kind of drift a hardcoded
    'known' number can't detect on its own."""
    src_dir = os.path.join(os.path.dirname(__file__), "metis_mcp")
    return sum(
        1 for f in os.listdir(src_dir)
        if f.endswith(".py") and os.path.getsize(os.path.join(src_dir, f)) > 0
    )


EXPECTED_REPOSITORY_UNITS = 1
EXPECTED_SOURCE_FILE_UNITS = _expected_source_file_count()


def _clean_graph():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            s.run("MATCH (e:Episode {source_connector: 'application-code'}) DETACH DELETE e")
            s.run("MATCH (r:Repository) DETACH DELETE r")
    finally:
        driver.close()


def _episode_count() -> int:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            rec = s.run(
                "MATCH (e:Episode {source_connector: 'application-code'}) RETURN count(e) AS c"
            ).single()
            return rec["c"]
    finally:
        driver.close()


def test_first_run_lands_exact_known_unit_counts():
    """Real node count against a known input size, per Phase 2's acceptance
    bar -- not just 'the log said success'."""
    _clean_graph()
    seed_mock_athena(PG_DSN)
    landed = connector.run(PG_DSN, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, job_id="test-first-run")
    assert landed["repository"] == EXPECTED_REPOSITORY_UNITS
    assert landed["source_file"] == EXPECTED_SOURCE_FILE_UNITS
    assert _episode_count() == EXPECTED_REPOSITORY_UNITS + EXPECTED_SOURCE_FILE_UNITS


def test_second_run_with_nothing_changed_lands_zero():
    """Idempotency: running twice in a row with no source changes produces
    zero new episodes the second time."""
    _clean_graph()
    seed_mock_athena(PG_DSN)
    connector.run(PG_DSN, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, job_id="test-idempotency-1")
    landed_second = connector.run(PG_DSN, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, job_id="test-idempotency-2")
    assert landed_second["repository"] == 0
    assert landed_second["source_file"] == 0
    assert _episode_count() == EXPECTED_REPOSITORY_UNITS + EXPECTED_SOURCE_FILE_UNITS


def test_killed_mid_run_then_restarted_resumes_without_loss_or_duplication():
    """Real process kill, not simulated: spawns the connector as an actual
    subprocess, kills it (SIGKILL) after it has durably landed some but not
    all units, then re-runs it to completion and checks the final state is
    exactly correct -- proves resumability for real, matching Phase 2's
    explicit acceptance bar."""
    _clean_graph()
    seed_mock_athena(PG_DSN)

    # main() resolves connection details through ConfigManager (.metis/config.yaml),
    # not raw env vars -- only the password_env-indirected secrets need to be
    # exported, matching how a real user would actually run this.
    env = os.environ.copy()
    env["METIS_ATHENA_PASSWORD"] = "athena-mock-pass"
    env["METIS_NEO4J_PASSWORD"] = NEO4J_PASSWORD

    proc = subprocess.Popen(
        [sys.executable, "-m", "connectors.application_code_connector"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    processed_lines = []
    kill_after = 3  # repository unit + 2 of 6 source_file units
    try:
        for line in proc.stdout:
            if line.startswith("PROCESSED"):
                processed_lines.append(line.strip())
                if len(processed_lines) >= kill_after:
                    proc.kill()
                    break
    finally:
        proc.wait(timeout=10)

    assert len(processed_lines) == kill_after
    partial_count = _episode_count()
    assert partial_count == kill_after, (
        f"expected exactly {kill_after} durably-landed episodes after the kill, got {partial_count} "
        f"-- either the kill landed a partial/corrupt unit, or didn't actually interrupt mid-run"
    )

    # Restart: should resume from the checkpoint, not reprocess from scratch
    # and not skip the remaining units.
    landed_resume = connector.run(PG_DSN, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, job_id="test-resume")
    total_expected = EXPECTED_REPOSITORY_UNITS + EXPECTED_SOURCE_FILE_UNITS
    assert landed_resume["repository"] + landed_resume["source_file"] == total_expected - kill_after
    assert _episode_count() == total_expected


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
