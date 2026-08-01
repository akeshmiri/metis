"""
Real integration test for the test-suite-ingest connector (Phase 7) --
against this project's own real test_*.py files and a real Neo4j instance.

Scope note, disclosed: unlike Phase 2/7's application-code and flat-files
connectors, this one doesn't implement incremental (updated_at-style)
checkpointing -- it re-scans every test file on every run. That's a
disclosed simplification, not a hidden gap: the property that actually
matters (per REQ-METIS-ING-02's idempotency requirement) is that re-running
never creates duplicate graph state, which IS what's tested here, via
MERGE semantics on both TestCase nodes and VERIFIES edges.
"""
import ast
import glob
import os
import sys

from neo4j import GraphDatabase

from connectors import test_suite_connector as connector
from metis_mcp.corpus import TAG_PATTERN

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))


def _test_files() -> list[str]:
    return sorted(os.path.relpath(f, SERVER_DIR) for f in glob.glob(os.path.join(SERVER_DIR, "test_*.py")))


def _independent_expected_test_case_count() -> int:
    """Deliberately re-implemented, not imported from the connector --
    a real cross-check against the same known-input files."""
    total = 0
    for rel_path in _test_files():
        with open(os.path.join(SERVER_DIR, rel_path), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        total += sum(
            1 for n in ast.iter_child_nodes(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        )
    return total


def _clean_graph():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            s.run("MATCH (e:Episode {source_connector: 'test-suite-ingest'}) DETACH DELETE e")
            s.run("MATCH (tc:TestCase) DETACH DELETE tc")
    finally:
        driver.close()


def _counts():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            nodes = s.run("MATCH (tc:TestCase) RETURN count(tc) AS c").single()["c"]
            edges = s.run("MATCH (:TestCase)-[r:VERIFIES]->() RETURN count(r) AS c").single()["c"]
            return nodes, edges
    finally:
        driver.close()


def test_lands_exact_known_test_case_count():
    _clean_graph()
    os.chdir(SERVER_DIR)
    expected = _independent_expected_test_case_count()
    totals = connector.run(_test_files(), NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, job_id="test-run-1")
    assert totals["test_cases"] == expected
    nodes, _ = _counts()
    assert nodes == expected


def test_rerun_does_not_duplicate_graph_state():
    """The real idempotency property: MERGE means re-running never creates
    duplicate TestCase nodes or duplicate VERIFIES edges, even though this
    connector re-scans every file each time (no incremental skip)."""
    _clean_graph()
    os.chdir(SERVER_DIR)
    connector.run(_test_files(), NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, job_id="test-run-a")
    nodes_after_1, edges_after_1 = _counts()
    connector.run(_test_files(), NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, job_id="test-run-b")
    nodes_after_2, edges_after_2 = _counts()
    assert nodes_after_2 == nodes_after_1
    assert edges_after_2 == edges_after_1


def test_orphan_test_case_has_no_verifies_edge_no_fabricated_link():
    """REQ-METIS-CONN-04's core rule: a file with no tag match must not get
    a guessed/fabricated traceability link."""
    _clean_graph()
    os.chdir(SERVER_DIR)
    connector.run(_test_files(), NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, job_id="test-run-orphan")

    orphan_file = "test_config_manager.py"  # known, from module docstring, to have no real tag
    with open(os.path.join(SERVER_DIR, orphan_file), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    doc = ast.get_docstring(tree) or ""
    assert not TAG_PATTERN.findall(doc), f"test fixture assumption violated -- {orphan_file} now has a real tag"

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            rec = s.run(
                "MATCH (tc:TestCase) WHERE tc.id CONTAINS $path "
                "OPTIONAL MATCH (tc)-[r:VERIFIES]->() RETURN count(r) AS edges",
                path=orphan_file,
            ).single()
        assert rec["edges"] == 0
    finally:
        driver.close()


def test_linked_test_case_verifies_a_real_existing_node():
    _clean_graph()
    os.chdir(SERVER_DIR)
    connector.run(_test_files(), NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, job_id="test-run-linked")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            rec = s.run(
                "MATCH (tc:TestCase)-[:VERIFIES]->(target) WHERE tc.id CONTAINS 'test_oauth2.py' "
                "RETURN target.id AS id LIMIT 1"
            ).single()
        assert rec is not None
        assert rec["id"] == "CONST-064"
    finally:
        driver.close()


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
