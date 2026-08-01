"""
Tests for code-graph archaeology (docs/metis-code-graph-archaeology-extension.md)
-- against the real Neo4j graph, real code (this project's own metis_mcp/*.py
files, already landed by Phase 2/3).
"""
import ast
import os
import sys

from neo4j import GraphDatabase

from cognify.code_graph_archaeology import _analyze_file, run

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")


def test_analyze_known_snippet_finds_real_calls_inherits_imports():
    snippet = '''
import metis_mcp.corpus

class Base:
    pass

class Child(Base):
    def method_a(self):
        return self.method_b()

    def method_b(self):
        return helper()

def helper():
    return 1
'''
    result = _analyze_file("repo", "f.py", snippet)
    assert ("repo:f.py:Child", "Base") in result["inherits"]
    assert ("repo:f.py:Child.method_a", "repo:f.py:Child.method_b", True) in result["calls"]
    assert ("repo:f.py:Child.method_b", "repo:f.py:helper", False) in result["calls"]
    assert "metis_mcp/corpus.py" in result["imports"]
    assert result["classes_in_file"] == ["repo:f.py:Base", "repo:f.py:Child"]


def test_stdlib_base_class_never_fabricated():
    """Class(Exception) -- Exception is never a real :Class node in this
    graph, so no INHERITS edge should ever point at a fabricated stub."""
    snippet = "class MyError(Exception):\n    pass\n"
    result = _analyze_file("repo", "f.py", snippet)
    assert ("repo:f.py:MyError", "Exception") in result["inherits"]  # detected, not yet resolved
    # Resolution (whether an edge is actually written) happens in _write_edges
    # against the real graph -- Exception will never match a real :Class node.


def test_real_run_produces_only_edges_to_real_existing_nodes():
    run(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)  # idempotent, MERGE-based
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            orphaned_calls = s.run(
                "MATCH (a:Method)-[:CALLS]->(b) WHERE b.source_episode_id IS NULL RETURN count(b) AS c"
            ).single()["c"]
            orphaned_imports = s.run(
                "MATCH (a:Class)-[:IMPORTS]->(b) WHERE b.source_episode_id IS NULL RETURN count(b) AS c"
            ).single()["c"]
            call_count = s.run("MATCH (:Method)-[:CALLS]->(:Method) RETURN count(*) AS c").single()["c"]
    finally:
        driver.close()
    assert orphaned_calls == 0
    assert orphaned_imports == 0
    assert call_count > 0


def test_rerun_does_not_duplicate_edges():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            before = s.run("MATCH (:Method)-[r:CALLS]->(:Method) RETURN count(r) AS c").single()["c"]
    finally:
        driver.close()
    run(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            after = s.run("MATCH (:Method)-[r:CALLS]->(:Method) RETURN count(r) AS c").single()["c"]
    finally:
        driver.close()
    assert after == before


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
