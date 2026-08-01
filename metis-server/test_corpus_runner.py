"""
Tests for the guardrail-corpus-runner (Phase 9, CONST-057/058) -- against
the real adversarial corpus file, not a synthetic stand-in.
"""
import os

from guardrails.corpus_runner import run, record_run_episode

CORPUS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "mcp-contracts",
    "metis-adversarial-injection-corpus.json",
)
NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")


def test_all_real_cases_pass_at_min_pass_rate_1_0():
    summary = run(CORPUS_PATH)
    assert summary["total"] == 12
    assert summary["pass_rate"] == 1.0
    assert summary["failed"] == 0


def test_no_case_ever_reaches_auto_write_tier():
    summary = run(CORPUS_PATH)
    for r in summary["results"]:
        assert r["tier"] != "auto_write", f"{r['id']} reached auto_write -- BS-001 violation"


def test_record_run_episode_writes_a_real_queryable_episode():
    """DQ-022 (metis_mcp/dq_metrics.py) queries exactly this shape --
    verifying it here, not just trusting the write succeeded."""
    from neo4j import GraphDatabase
    summary = run(CORPUS_PATH)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            episode_id = record_run_episode(s, summary, min_pass_rate=1.0)
            rec = s.run(
                "MATCH (e:Episode {id: $id}) RETURN e.episode_type AS t, e.pass_rate AS pr, "
                "e.min_pass_rate AS mpr, e.source_connector AS sc",
                id=episode_id,
            ).single()
            assert rec["t"] == "AdversarialCorpusRun"
            assert rec["pr"] == summary["pass_rate"]
            assert rec["mpr"] == 1.0
            assert rec["sc"] == "guardrail-corpus-runner"
            s.execute_write(lambda tx: tx.run("MATCH (e:Episode {id: $id}) DETACH DELETE e", id=episode_id).consume())
    finally:
        driver.close()


if __name__ == "__main__":
    import sys
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    if not NEO4J_PASSWORD:
        tests = [t for t in tests if t.__name__ != "test_record_run_episode_writes_a_real_queryable_episode"]
        print("METIS_NEO4J_PASSWORD not set -- skipping test_record_run_episode_writes_a_real_queryable_episode",
              file=sys.stderr)
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
