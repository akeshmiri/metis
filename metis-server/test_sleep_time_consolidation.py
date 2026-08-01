"""
§8.3 Sleep-time consolidation -- metis_mcp/sleep_time_consolidation.py's 2
real mechanisms (near-duplicate merge proposals via real Jaccard
similarity, and non-lossy rollup summarization with a real resumable
checkpoint), against real Neo4j fixtures.
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.sleep_time_consolidation import (
    jaccard_similarity, find_near_duplicates, write_merge_proposals,
    summarize_low_signal_episodes, default_summary_text_fn,
)

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
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Episode {id: 'stc-test-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'test', e.job_id = 'test'"
        ).consume())

        # Two near-duplicate Requirements (high word overlap).
        s.execute_write(lambda tx: tx.run(
            "MERGE (r:Requirement {id: 'stc-test-req-dup-a'}) SET r.source_episode_id = 'stc-test-episode', "
            "r.ears_pattern = 'Ubiquitous', r.revision = 1, r.corroboration_count = 1, "
            "r.text = 'The system shall archive completed orders every night at midnight.'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MERGE (r:Requirement {id: 'stc-test-req-dup-b'}) SET r.source_episode_id = 'stc-test-episode', "
            "r.ears_pattern = 'Ubiquitous', r.revision = 1, r.corroboration_count = 1, "
            "r.text = 'The system shall archive completed orders every night around midnight.'"
        ).consume())
        # An unrelated Requirement -- must not be proposed as a duplicate.
        s.execute_write(lambda tx: tx.run(
            "MERGE (r:Requirement {id: 'stc-test-req-unrelated'}) SET r.source_episode_id = 'stc-test-episode', "
            "r.ears_pattern = 'Ubiquitous', r.revision = 1, r.corroboration_count = 1, "
            "r.text = 'The billing service shall reject expired payment cards immediately.'"
        ).consume())

        # Old, low-signal Episodes for rollup.
        for i in range(3):
            s.execute_write(lambda tx, i=i: tx.run(
                "CREATE (e:Episode {id: 'stc-test-old-episode-' + toString($i), "
                "source_connector: 'test-old-source', source_kind: 'x', job_id: 'x', "
                "t_recorded: datetime('2020-01-0' + toString($i + 1) + 'T00:00:00Z'), "
                "episode_type: 'LowSignalThing'})",
                i=i,
            ).consume())


def _cleanup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (n) WHERE n.id STARTS WITH 'stc-test-' DETACH DELETE n"
        ).consume())
        # RollupEpisode/checkpoint ids are derived from covered episode ids
        # (rollup:<first>:<last>:<n>), not prefixed 'stc-test-' themselves --
        # real gap found running this test twice in a row: stale rollup/
        # checkpoint nodes from a prior run silently advanced the
        # checkpoint past this run's fixtures, making the test flake based
        # on execution history. Clean up by source_connector instead.
        s.execute_write(lambda tx: tx.run(
            "MATCH (e:Episode) WHERE e.source_connector IN ['sleep-time-consolidation', 'test-old-source'] "
            "DETACH DELETE e"
        ).consume())


def test_jaccard_similarity_real_values():
    assert jaccard_similarity("the cat sat", "the cat sat") == 1.0
    assert jaccard_similarity("the cat sat", "a dog ran") == 0.0
    sim = jaccard_similarity("the quick brown fox", "the quick brown dog")
    assert 0 < sim < 1


def test_find_near_duplicates_flags_the_real_similar_pair_only():
    with _session() as s:
        proposals = find_near_duplicates(s, "Requirement", threshold=0.7)
    pairs = {(p.id_a, p.id_b) for p in proposals} | {(p.id_b, p.id_a) for p in proposals}
    assert ("stc-test-req-dup-a", "stc-test-req-dup-b") in pairs
    assert not any("stc-test-req-unrelated" in pair for pair in pairs)


def test_write_merge_proposals_creates_real_pending_review_nodes_idempotently():
    with _session() as s:
        proposals = find_near_duplicates(s, "Requirement", threshold=0.7)
        ids_1 = write_merge_proposals(s, proposals, "stc-test-episode")
        ids_2 = write_merge_proposals(s, proposals, "stc-test-episode")
        assert ids_1 == ids_2, "re-running the detector must not create duplicate proposals"

        rec = s.run(
            "MATCH (mp:MergeProposal {id: $id}) RETURN mp.status AS status, mp.similarity AS sim",
            id=ids_1[0],
        ).single()
        assert rec["status"] == "PendingReview"
        assert rec["sim"] >= 0.7

        # Neither original candidate was touched/merged/deleted.
        still_exist = s.run(
            "MATCH (r:Requirement) WHERE r.id IN ['stc-test-req-dup-a', 'stc-test-req-dup-b'] "
            "RETURN count(r) AS c"
        ).single()["c"]
        assert still_exist == 2


def test_summarize_low_signal_episodes_is_non_lossy_and_resumable():
    """This project's real Neo4j instance already carries other real, older
    Episodes from earlier connector runs this session -- the job is
    genuinely graph-wide (a real nightly job over the whole graph, not
    scoped to a test's own fixtures), so this asserts the 3 fixtures are a
    SUBSET of what's covered, not that they're the only thing covered."""
    with _session() as s:
        result = summarize_low_signal_episodes(
            s, older_than_days=1, summary_text_fn=default_summary_text_fn, batch_size=500,
        )
    assert result["rolled_up"] >= 3
    fixture_ids = {"stc-test-old-episode-0", "stc-test-old-episode-1", "stc-test-old-episode-2"}
    assert fixture_ids <= set(result["covered_episode_ids"])

    with _session() as s:
        # Raw episodes still exist, untouched -- non-lossy.
        still_there = s.run(
            "MATCH (e:Episode) WHERE e.id STARTS WITH 'stc-test-old-episode-' RETURN count(e) AS c"
        ).single()["c"]
        assert still_there == 3

        rollup = s.run(
            "MATCH (ru:RollupEpisode {id: $id})-[:SUMMARIZES]->(raw:Episode) "
            "RETURN collect(raw.id) AS covered_ids, ru.summary AS summary",
            id=result["rollup_episode_id"],
        ).single()
        assert fixture_ids <= set(rollup["covered_ids"])
        assert "LowSignalThing" in rollup["summary"]

        # Resumability: running again must not re-roll-up the same episodes
        # (checkpoint moved past them) -- specifically, the 3 fixtures must
        # never appear in a second run's covered set.
        second_run = summarize_low_signal_episodes(
            s, older_than_days=1, summary_text_fn=default_summary_text_fn, batch_size=500,
        )
    assert not (fixture_ids & set(second_run["covered_episode_ids"]))


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
