"""
Layer 8 (REQ-METIS-GRD-08) -- metis_mcp/layer8_heuristics.py's 4 real
checks (EARS non-conformance, vagueness/DQ-004, circular traceability/
DQ-018, orphan-claim detection) against a real Neo4j fixture set.
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.layer8_heuristics import (
    check_ears_nonconformance, check_vagueness, check_circular_traceability,
    check_orphan_claims, run_layer8,
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
            "MERGE (e:Episode {id: 'l8-test-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'test', e.job_id = 'test'"
        ).consume())

        def req(rid, text):
            s.execute_write(lambda tx: tx.run(
                "MERGE (r:Requirement {id: $id}) SET r.source_episode_id = 'l8-test-episode', "
                "r.ears_pattern = 'Unscored', r.revision = 1, r.corroboration_count = 1, r.text = $text",
                id=rid, text=text,
            ).consume())

        def ac(acid, text):
            s.execute_write(lambda tx: tx.run(
                "MERGE (a:AcceptanceCriterion {id: $id}) SET a.source_episode_id = 'l8-test-episode', "
                "a.text = $text, a.revision = 1",
                id=acid, text=text,
            ).consume())

        def tc(tcid):
            s.execute_write(lambda tx: tx.run(
                "MERGE (t:TestCase {id: $id}) SET t.source_episode_id = 'l8-test-episode'", id=tcid,
            ).consume())

        def has_ac(rid, acid):
            s.execute_write(lambda tx: tx.run(
                "MATCH (r:Requirement {id: $rid}), (a:AcceptanceCriterion {id: $acid}) "
                "MERGE (r)-[:HAS_AC]->(a)", rid=rid, acid=acid,
            ).consume())

        def verifies(tcid, rid):
            s.execute_write(lambda tx: tx.run(
                "MATCH (t:TestCase {id: $tcid}), (r:Requirement {id: $rid}) "
                "MERGE (t)-[:VERIFIES]->(r)", tcid=tcid, rid=rid,
            ).consume())

        req("l8-test-req-good", "When a subscription renews, the payment service shall charge the customer.")
        ac("l8-test-ac-good", "The customer is charged the correct amount.")
        tc("l8-test-tc-good")
        has_ac("l8-test-req-good", "l8-test-ac-good")
        verifies("l8-test-tc-good", "l8-test-req-good")

        req("l8-test-req-nonconformant", "Users should probably be able to cancel orders sometimes.")

        req("l8-test-req-circular", "When an order ships, the system shall notify the customer.")
        tc("l8-test-tc-circular")
        verifies("l8-test-tc-circular", "l8-test-req-circular")
        # deliberately no HAS_AC edge -- this is the circular-traceability fixture

        ac("l8-test-ac-vague", "The response shall be fast and user-friendly.")
        has_ac("l8-test-req-good", "l8-test-ac-vague")  # attached, but its text is vague

        ac("l8-test-ac-orphan", "Some orphaned claim with no parent Requirement.")
        # deliberately no HAS_AC edge from anything -- this is the orphan-claim fixture


def _cleanup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (n) WHERE n.id STARTS WITH 'l8-test-' DETACH DELETE n"
        ).consume())


def test_ears_nonconformance_flags_the_real_non_ears_requirement():
    with _session() as s:
        result = check_ears_nonconformance(s)
    assert "l8-test-req-nonconformant" in result.flagged_ids
    assert "l8-test-req-good" not in result.flagged_ids
    assert "l8-test-req-circular" not in result.flagged_ids


def test_vagueness_flags_the_vague_acceptance_criterion_only():
    with _session() as s:
        result = check_vagueness(s)
    assert "l8-test-ac-vague" in result.flagged_ids
    assert "l8-test-ac-good" not in result.flagged_ids


def test_vagueness_can_persist_flags_on_the_real_node():
    with _session() as s:
        check_vagueness(s, write_flags=True)
        rec = s.run(
            "MATCH (a:AcceptanceCriterion {id: 'l8-test-ac-vague'}) RETURN a.vagueness_flagged AS f"
        ).single()
        clean = s.run(
            "MATCH (a:AcceptanceCriterion {id: 'l8-test-ac-good'}) RETURN a.vagueness_flagged AS f"
        ).single()
    assert rec["f"] is True
    assert clean["f"] is False


def test_circular_traceability_flags_sole_test_with_no_independent_ac():
    with _session() as s:
        result = check_circular_traceability(s)
    assert "l8-test-req-circular" in result.flagged_ids
    assert "l8-test-req-good" not in result.flagged_ids, "has its own AC -- not circular"


def test_orphan_claims_flags_ac_with_no_parent_requirement():
    with _session() as s:
        result = check_orphan_claims(s)
    assert "l8-test-ac-orphan" in result.flagged_ids
    assert "l8-test-ac-good" not in result.flagged_ids
    assert "l8-test-ac-vague" not in result.flagged_ids, "has a real HAS_AC parent"


def test_run_layer8_aggregates_all_four_checks():
    with _session() as s:
        result = run_layer8(s)
    assert set(result.keys()) == {"ears_nonconformance", "vagueness", "circular_traceability", "orphan_claims"}
    assert result["ears_nonconformance"]["flagged_count"] >= 1
    assert result["vagueness"]["flagged_count"] >= 1
    assert result["circular_traceability"]["flagged_count"] >= 1
    assert result["orphan_claims"]["flagged_count"] >= 1


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
