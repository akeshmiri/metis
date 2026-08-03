"""
metis_mcp/graph_sync.py -- real staleness + drift detection, against the
live Neo4j instance and a real temp test file run through the real
connectors/test_suite_connector.py entrypoint (not a mock).

Drift scenario used: a real temp test file whose module docstring cites
CONST-047 (a real, already-loaded Constitution rule) on the first sync
run -- gets linked, no `triage_reason`. The docstring is then edited to
cite a tag that does not exist, and re-synced -- the TestCase becomes an
orphan and gets a real `triage_reason` property for the first time. That
property ADD is real, detectable drift (record_revision's own diff, no
new logic) -- chosen over an edit that would need Cypher's `SET n += `
to *remove* a property, which it structurally cannot do.
"""
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

from neo4j import GraphDatabase

from metis_mcp.graph_sync import check_staleness, sync_and_detect_drift
from connectors import test_suite_connector as suite_connector
from connectors import atlassian_connector

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

MOCK_PORT = 8426
MOCK_BASE_URL = f"http://127.0.0.1:{MOCK_PORT}"

_driver = None
_mock_proc = None


def _session():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver.session()


def _start_mock(extra_env: dict | None = None):
    global _mock_proc
    env = os.environ.copy()
    env["METIS_MOCK_JIRA_PORT"] = str(MOCK_PORT)
    if extra_env:
        env.update(extra_env)
    _mock_proc = subprocess.Popen(
        [sys.executable, "-m", "connectors.mock_jira_server"],
        cwd=os.path.dirname(os.path.abspath(__file__)), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{MOCK_BASE_URL}/wiki/rest/api/content", timeout=1)
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("mock_jira_server did not start in time")


def _stop_mock():
    global _mock_proc
    if _mock_proc:
        _mock_proc.kill()
        _mock_proc.wait(timeout=10)
        _mock_proc = None


def _cleanup_synced_entities(connector_name: str):
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (ep:Episode {source_connector: $c}) "
            "OPTIONAL MATCH (n {source_episode_id: ep.id}) "
            "DETACH DELETE n, ep",
            c=connector_name,
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (e:Episode {source_connector: 'graph-sync'}) DETACH DELETE e"
        ).consume())


def test_check_staleness_reflects_real_episode_ages():
    with _session() as s:
        rows = check_staleness(s)
    assert isinstance(rows, list)
    for row in rows:
        assert row["days_since_last_update"] >= 0
        assert row["connector"]


def test_sync_and_detect_drift_finds_a_real_property_change_on_the_second_run():
    connector_name = "gsync-test-connector"
    _cleanup_synced_entities(connector_name)
    try:
        with tempfile.TemporaryDirectory() as d:
            test_file = os.path.join(d, "test_gsync_fixture.py")

            # Round 1: docstring cites a real, existing tag -- gets linked.
            with open(test_file, "w", encoding="utf-8") as f:
                f.write(
                    '"""References CONST-047."""\n'
                    "def test_something():\n    assert True\n"
                )

            def rerun():
                suite_connector.run(
                    [test_file], NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
                    job_id="gsync-test-run-1", repo="gsync-test-repo",
                )
                # test_suite_connector.py hardcodes SOURCE_CONNECTOR = 'test-suite-ingest'
                # on the Episode it lands -- retag it under our own test-only
                # connector name afterward so this test's snapshots never
                # touch the real repo's own test-suite-ingest data.
                with _session() as s2:
                    s2.execute_write(lambda tx: tx.run(
                        "MATCH (ep:Episode {unit_id: $path}) SET ep.source_connector = $c",
                        path=test_file, c=connector_name,
                    ).consume())

            with _session() as s:
                result1 = sync_and_detect_drift(s, connector_name, "TestCase", rerun)
            assert result1["entities_checked"] == 1
            assert result1["drifted"] == [], "first sync of a brand-new entity is never 'drift'"

            with _session() as s:
                rec = s.run(
                    "MATCH (ep:Episode {source_connector: $c}) MATCH (tc:TestCase {source_episode_id: ep.id}) "
                    "RETURN tc.triage_reason AS reason", c=connector_name,
                ).single()
            assert rec["reason"] is None, "cites a real known tag -- should be linked, not orphaned"

            # Round 2: same file, docstring now cites a tag that doesn't exist.
            with open(test_file, "w", encoding="utf-8") as f:
                f.write(
                    '"""References CONST-999999 (does not exist)."""\n'
                    "def test_something():\n    assert True\n"
                )

            with _session() as s:
                result2 = sync_and_detect_drift(s, connector_name, "TestCase", rerun)
            assert len(result2["drifted"]) == 1, "citing a nonexistent tag should flip it to orphan -- real drift"
            drifted_entry = result2["drifted"][0]
            assert "triage_reason" in drifted_entry["changed_fields"]
            assert drifted_entry["changed_fields"]["triage_reason"]["from"] is None
            assert drifted_entry["changed_fields"]["triage_reason"]["to"] == "no_traceability_match"

            with _session() as s:
                drift_episode = s.run(
                    "MATCH (e:Episode {episode_type: 'SpecDriftDetected', drifted_connector: $c}) "
                    "RETURN e.drifted_entity_count AS count", c=connector_name,
                ).single()
            assert drift_episode is not None, "a real SpecDriftDetected Episode must exist after real drift"
            assert drift_episode["count"] == 1
    finally:
        _cleanup_synced_entities(connector_name)


def test_sync_and_detect_drift_finds_a_real_confluence_page_edit_on_the_second_run():
    """Session 11, item 4 -- the concrete 'document management' proof
    connector. Confluence pages land as bare Episode nodes with no
    downstream typed entity (Session 4's disclosed ontology gap), unlike
    the TestCase-typed-node shape the test above proves -- this exercises
    sync_and_detect_drift's entity_label='Episode' path for real, on a
    genuinely different connector shape, not just a second copy of the
    same proof."""
    connector_name = "gsync-confluence-test"

    def _cleanup():
        with _session() as s:
            s.execute_write(lambda tx: tx.run(
                "MATCH (ep:Episode {source_connector: $c}) DETACH DELETE ep", c=connector_name,
            ).consume())
            s.execute_write(lambda tx: tx.run(
                "MATCH (e:Episode {source_connector: 'graph-sync', drifted_connector: $c}) DETACH DELETE e",
                c=connector_name,
            ).consume())
            s.execute_write(lambda tx: tx.run(
                "MATCH (e:Episode {id: 'gsync-confluence-wrapper'}) DETACH DELETE e"
            ).consume())

    def rerun():
        with _session() as s2:
            s2.execute_write(lambda tx: tx.run(
                "MERGE (e:Episode {id: 'gsync-confluence-wrapper'}) "
                "SET e.t_recorded = datetime(), e.source_connector = 'gsync-confluence-driver', "
                "e.job_id = 'gsync-confluence-driver'"
            ).consume())
            atlassian_connector._land_confluence_pages(MOCK_BASE_URL, s2, "gsync-confluence-wrapper")
            # atlassian_connector.py hardcodes SOURCE_CONNECTOR = 'atlassian-prod' on
            # the Episode it lands -- retag under our own test-only connector name,
            # same pattern the test-suite-connector proof above already uses.
            s2.execute_write(lambda tx: tx.run(
                "MATCH (e:Episode {confluence_page_id: '98765'}) SET e.source_connector = $c",
                c=connector_name,
            ).consume())

    _cleanup()
    try:
        _start_mock()
        try:
            with _session() as s:
                result1 = sync_and_detect_drift(s, connector_name, "Episode", rerun,
                                                 episode_type="DocumentIngested")
            assert result1["entities_checked"] == 1
            assert result1["drifted"] == [], "first sync of a brand-new Episode is never 'drift'"
        finally:
            _stop_mock()

        # Round 2: a real page edit -- new body content, bumped version.
        _start_mock(extra_env={
            "METIS_MOCK_CONFLUENCE_BODY": "<p>Refunds are issued within 14 business days of approval.</p>",
            "METIS_MOCK_CONFLUENCE_VERSION": "4",
            "METIS_MOCK_CONFLUENCE_UPDATED": "2026-07-25T09:00:00Z",
        })
        try:
            with _session() as s:
                result2 = sync_and_detect_drift(s, connector_name, "Episode", rerun,
                                                 episode_type="DocumentIngested")
            assert len(result2["drifted"]) == 1, "a real page-content edit should be detected as drift"
            changed = result2["drifted"][0]["changed_fields"]
            assert changed["raw_content"]["to"] == "<p>Refunds are issued within 14 business days of approval.</p>"
            assert changed["confluence_version"]["to"] == 4

            with _session() as s:
                drift_episode = s.run(
                    "MATCH (e:Episode {episode_type: 'SpecDriftDetected', drifted_connector: $c}) "
                    "RETURN e.drifted_entity_count AS count", c=connector_name,
                ).single()
            assert drift_episode is not None, "a real SpecDriftDetected Episode must exist after real drift"
            assert drift_episode["count"] == 1
        finally:
            _stop_mock()
    finally:
        _cleanup()


if __name__ == "__main__":
    if not NEO4J_PASSWORD:
        print("METIS_NEO4J_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)
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
        if _driver:
            _driver.close()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
