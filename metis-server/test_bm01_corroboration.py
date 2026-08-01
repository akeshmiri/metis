"""
Tests for REQ-METIS-BM-01's code-graph corroboration
(metis_mcp/behavior_model.py's corroborate_transition) -- against the real
Neo4j graph and the real CALLS edges cognify/code_graph_archaeology.py
extracted from this project's own actual code
(ClassificationGate.check -> ClassificationGate._effective_classification
is a real, existing call in metis_mcp/classification_gate.py).
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.behavior_model import load_transition, corroborate_transition

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

METHOD_ID = "metis-server:metis_mcp/classification_gate.py:ClassificationGate.check"
REAL_CALLEE = "metis-server:metis_mcp/classification_gate.py:ClassificationGate._effective_classification"
FAKE_CALLEE = "metis-server:metis_mcp/classification_gate.py:ClassificationGate.zdr_confirmed_directly"

_driver = None


def _session():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver.session()


def _setup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Episode {id: 'bm01-test-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'test', e.job_id = 'test'"
        ).consume())
        load_transition(s, "bm01-test-transition", "bm01-test-episode",
                         "bm01-test-Checking", "bm01-test-Decided", "bm01-test-check_called", "true")


def _cleanup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (n) WHERE n.id STARTS WITH 'bm01-test-' DETACH DELETE n"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (e:Episode {id: 'bm01-test-episode'}) DETACH DELETE e"
        ).consume())


def test_real_call_edge_is_corroborated():
    with _session() as s:
        result = corroborate_transition(s, "bm01-test-transition", METHOD_ID, [REAL_CALLEE])
    assert result.corroborated
    assert result.missing_callees == []


def test_nonexistent_call_edge_is_not_corroborated_and_marks_disputed():
    with _session() as s:
        result = corroborate_transition(s, "bm01-test-transition", METHOD_ID, [FAKE_CALLEE])
        assert not result.corroborated
        assert FAKE_CALLEE in result.missing_callees

        check = s.run(
            "MATCH (t:Transition {id: 'bm01-test-transition'}) RETURN t.lifecycle_state AS ls",
        ).single()
        assert check["ls"] == "Disputed"


def test_nonexistent_implementing_method_reported_specifically():
    with _session() as s:
        result = corroborate_transition(s, "bm01-test-transition", "does-not-exist:at-all", [REAL_CALLEE])
    assert not result.corroborated
    assert "does not exist in the code graph" in result.reason


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
