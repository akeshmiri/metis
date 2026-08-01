"""
Real integration test for Neo4jGraphStore -- runs against an actual Neo4j
instance (see PLAN.md Phase 1's acceptance criteria: "not mocked"), assuming
load_dogfooding_corpus.py has already loaded the real dogfooding corpus into
it. Each test checks a specific, known value from that real corpus (e.g.
CONST-047's actual defining text, DQ-002 as one of its real citations) --
not a synthetic fixture, per this project's working style.

Requires:
  - A reachable Neo4j instance (see .metis/config.yaml's graph.neo4j section
    for uri/user/password_env).
  - load_dogfooding_corpus.py already run against it.
If the instance isn't reachable, every test fails loudly rather than being
silently skipped -- a real backend that can't be reached is a real problem,
not something to paper over.
"""
import os

from metis_mcp.config_manager import ConfigManager
from metis_mcp.neo4j_graph_store import Neo4jGraphStore

_config = ConfigManager()
_neo4j_cfg = _config.get_neo4j_config()
_password = os.environ.get(_neo4j_cfg.get("password_env", ""))
store = Neo4jGraphStore(_neo4j_cfg["uri"], _neo4j_cfg["user"], _password)


def test_get_node_returns_real_const_047():
    node = store.get_node("CONST-047")
    assert node is not None
    assert node.kind == "ConstitutionRule"
    assert node.text.startswith("**CONST-047.**")
    assert node.source_file  # a real filename, not empty


def test_get_node_missing_id_returns_none():
    assert store.get_node("CONST-99999") is None


def test_neighbors_const_047_cites_dq_002():
    """DQ-002 is a real, known citation inside CONST-047's actual defining
    text (it extends DQ-002's EARS Conformance dimension) -- same specific
    value test_e2e.py already checks against LocalGraphStore."""
    n = store.neighbors("CONST-047")
    assert n is not None
    assert "DQ-002" in n["references"]


def test_traceability_chain_upstream_matches_neighbors():
    chain = store.traceability_chain("CONST-047", max_hops=1)
    assert chain is not None
    hop1_ids = {row["id"] for row in chain["upstream"] if row["hop"] == 1}
    assert "DQ-002" in hop1_ids


def test_traceability_chain_missing_node_returns_none():
    assert store.traceability_chain("CONST-99999") is None


def test_traceability_chain_never_revisits_start_node():
    """Real bug caught while running this against the actual citation graph:
    the corpus has real citation cycles (some node's chain of citations
    eventually cites back to CONST-047 within 3 hops), and Neo4j's
    variable-length path matching allows a path to revisit the start node
    unless explicitly excluded -- LocalGraphStore's BFS never does this
    (its visited-set is seeded with the start id), so this store must match
    that, not silently include the node in its own upstream/downstream."""
    chain = store.traceability_chain("CONST-047", max_hops=3)
    upstream_ids = {row["id"] for row in chain["upstream"]}
    downstream_ids = {row["id"] for row in chain["downstream"]}
    assert "CONST-047" not in upstream_ids
    assert "CONST-047" not in downstream_ids


def test_impact_analysis_dq_002_is_affected_by_const_047():
    """CONST-047 cites DQ-002, so DQ-002 is affected if CONST-047 changes --
    the reverse direction of the citation edge."""
    result = store.impact_analysis("DQ-002")
    assert result is not None
    affected_ids = {row["id"] for row in result["affects"]}
    assert "CONST-047" in affected_ids


def test_orphan_rate_is_a_real_computed_fraction():
    result = store.orphan_rate("ConstitutionRule")
    assert result["total"] > 0
    assert 0.0 <= result["orphan_rate"] <= 1.0
    assert result["orphans"] == len(result["orphan_ids"])


def test_search_finds_const_047_by_id():
    hits = store.search("CONST-047")
    assert any(h["id"] == "CONST-047" for h in hits)


def test_node_count_matches_real_load():
    assert store.node_count == 177  # actual count load_dogfooding_corpus.py reported


if __name__ == "__main__":
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
    store.close()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
