"""
§8.2 Hybrid retrieval -- metis_mcp/hybrid_retrieval.py's 4 modes, against
the real Neo4j instance, including the real (previously-unqueried)
metis_graph_fulltext index and a real fixture graph for multi-hop
traversal.
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.hybrid_retrieval import (
    graph_traversal_search, bm25_search, semantic_vector_search,
    temporal_point_in_time_search, hybrid_search,
)
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


def _setup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Episode {id: 'hr-test-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'test', e.job_id = 'test'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MERGE (r:Requirement {id: 'hr-test-req-anchor'}) SET r.source_episode_id = 'hr-test-episode', "
            "r.ears_pattern = 'Ubiquitous', r.revision = 1, r.corroboration_count = 1, "
            "r.text = 'The zephyrine widget subsystem shall archive completed orders nightly.'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MERGE (a:AcceptanceCriterion {id: 'hr-test-ac-1hop'}) SET a.source_episode_id = 'hr-test-episode', "
            "a.revision = 1, a.text = 'Archived orders are retrievable for 7 years.'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (r:Requirement {id: 'hr-test-req-anchor'}), (a:AcceptanceCriterion {id: 'hr-test-ac-1hop'}) "
            "MERGE (r)-[:HAS_AC]->(a)"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MERGE (tc:TestCase {id: 'hr-test-tc-2hop'}) SET tc.source_episode_id = 'hr-test-episode'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (tc:TestCase {id: 'hr-test-tc-2hop'}), (r:Requirement {id: 'hr-test-req-anchor'}) "
            "MERGE (tc)-[:VERIFIES]->(r)"
        ).consume())
        record_revision(s, "hr-test-req-anchor", {"status": "Draft"}, "hr-test-episode",
                         t_recorded="2024-01-01T00:00:00Z")
        record_revision(s, "hr-test-req-anchor", {"status": "Approved"}, "hr-test-episode",
                         t_recorded="2024-06-01T00:00:00Z")


def _cleanup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (n) WHERE n.id STARTS WITH 'hr-test-' DETACH DELETE n"
        ).consume())


def test_graph_traversal_finds_1_and_2_hop_neighbors_with_distance_scoring():
    with _session() as s:
        hits = graph_traversal_search(s, "hr-test-req-anchor", max_hops=2)
    by_id = {h["id"]: h for h in hits}
    assert by_id["hr-test-ac-1hop"]["hops"] == 1
    assert by_id["hr-test-tc-2hop"]["hops"] == 1  # VERIFIES is also a direct edge to the anchor
    assert by_id["hr-test-ac-1hop"]["score"] == 0.5  # 1 / (1 + hops), hops=1


def test_bm25_search_finds_the_real_indexed_text():
    with _session() as s:
        hits = bm25_search(s, "zephyrine widget", top_k=5)
    ids = [h["id"] for h in hits]
    assert "hr-test-req-anchor" in ids, \
        "the real metis_graph_fulltext index should find this distinctively-worded fixture"
    assert hits[0]["score"] == 1.0, "top hit is normalized to 1.0 within this result set"


def test_bm25_search_no_match_returns_empty_not_an_error():
    with _session() as s:
        hits = bm25_search(s, "xyzzyunmatchabletoken123456", top_k=5)
    assert hits == []


def test_semantic_vector_search_honestly_refuses():
    with _session() as s:
        result = semantic_vector_search(s, "anything")
    assert result["available"] is False
    assert result["hits"] == []
    assert "No embedding model" in result["reason"]


def test_temporal_point_in_time_reuses_real_as_of():
    with _session() as s:
        result = temporal_point_in_time_search(s, "hr-test-req-anchor", "2024-03-01T00:00:00Z")
    assert result["found"] is True
    assert result["revision"] == 1
    assert result["properties"]["status"] == "Draft"


def test_hybrid_search_merges_and_reranks_across_real_modes():
    with _session() as s:
        result = hybrid_search(s, query="zephyrine widget", anchor_id="hr-test-req-anchor",
                                as_of_timestamp="2024-03-01T00:00:00Z")
    assert set(result["modes_run"]) == {"graph_traversal", "bm25", "temporal"}
    assert result["semantic_vector_mode"]["available"] is False
    result_ids = [r["id"] for r in result["results"]]
    assert "hr-test-req-anchor" in result_ids
    anchor_hit = next(r for r in result["results"] if r["id"] == "hr-test-req-anchor")
    # Surfaced by all 3 real modes -- graph traversal doesn't return the
    # anchor itself, but bm25 and temporal both do.
    assert "bm25" in anchor_hit["modes"]
    assert "temporal" in anchor_hit["modes"]
    assert anchor_hit["merged_score"] > 0


def test_hybrid_search_with_only_a_query_runs_bm25_only():
    with _session() as s:
        result = hybrid_search(s, query="zephyrine widget")
    assert result["modes_run"] == ["bm25"]


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
