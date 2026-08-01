"""
Phase 4 end-to-end acceptance test: Layer 2 + Layer 3 wired together
against a real Neo4j instance, not mocked. This is the specific acceptance
bar PLAN.md states for Phase 4: "Feed a deliberately malformed entity
through and confirm it's rejected with the specific reason, not a generic
failure" -- tested here against the real graph, not just the unit-level
StructuralValidator tests in test_structural_validation.py.
"""
import os
import sys

from neo4j import GraphDatabase

from guardrails.pipeline import submit_candidate

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")


def _session():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return driver, driver.session()


def _real_episode_id() -> str:
    """A real Episode id already in the graph, from Phase 2's connector run
    -- using a genuinely real reference, not a fabricated one, for the
    'valid entity' side of these tests."""
    driver, session = _session()
    try:
        rec = session.run("MATCH (e:Episode) RETURN e.id AS id LIMIT 1").single()
        assert rec is not None, "no real Episode exists -- run the Phase 2 connector first"
        return rec["id"]
    finally:
        session.close()
        driver.close()


def _cleanup(node_id: str):
    driver, session = _session()
    try:
        session.run("MATCH (n {id: $id}) WHERE NOT n:Episode DETACH DELETE n", id=node_id)
    finally:
        session.close()
        driver.close()


def test_malformed_entity_dangling_episode_rejected_with_specific_reason_not_written():
    driver, session = _session()
    try:
        entity = {"id": "test-malformed-dangling-episode", "source_episode_id": "does-not-exist"}
        result = submit_candidate(session, "Class", entity, confidence=0.95)
        assert not result.written
        assert not result.validation.valid
        assert any("does not reference an existing Episode" in r for r in result.validation.reasons)

        check = session.run("MATCH (n {id: $id}) RETURN n", id=entity["id"]).single()
        assert check is None, "malformed entity must not be written to the graph at all"
    finally:
        _cleanup("test-malformed-dangling-episode")
        session.close()
        driver.close()


def test_malformed_entity_missing_required_field_rejected_with_specific_reason():
    driver, session = _session()
    try:
        episode_id = _real_episode_id()
        entity = {"id": "test-malformed-no-ears", "source_episode_id": episode_id}
        result = submit_candidate(session, "Requirement", entity, confidence=0.95)
        assert not result.written
        assert any("Missing required property 'ears_pattern'" in r for r in result.validation.reasons)
    finally:
        _cleanup("test-malformed-no-ears")
        session.close()
        driver.close()


def test_valid_high_confidence_entity_is_written_with_draft_lifecycle_state():
    driver, session = _session()
    try:
        episode_id = _real_episode_id()
        entity = {"id": "test-valid-high-confidence", "source_episode_id": episode_id}
        result = submit_candidate(session, "Class", entity, confidence=0.95, risk_tag="Low")
        assert result.written
        assert result.tiering.lifecycle_state == "Draft"

        rec = session.run(
            "MATCH (n:Class {id: $id}) RETURN n.lifecycle_state AS ls, n.risk_tag AS rt",
            id=entity["id"],
        ).single()
        assert rec["ls"] == "Draft"
        assert rec["rt"] == "Low"
    finally:
        _cleanup("test-valid-high-confidence")
        session.close()
        driver.close()


def test_valid_mid_confidence_entity_is_written_with_quarantine_lifecycle_state():
    driver, session = _session()
    try:
        episode_id = _real_episode_id()
        entity = {"id": "test-valid-mid-confidence", "source_episode_id": episode_id}
        result = submit_candidate(session, "Class", entity, confidence=0.7)
        assert result.written
        assert result.tiering.lifecycle_state == "Quarantine"

        rec = session.run(
            "MATCH (n:Class {id: $id}) RETURN n.lifecycle_state AS ls", id=entity["id"],
        ).single()
        assert rec["ls"] == "Quarantine"
    finally:
        _cleanup("test-valid-mid-confidence")
        session.close()
        driver.close()


def test_valid_entity_low_confidence_rejected_and_never_written():
    driver, session = _session()
    try:
        episode_id = _real_episode_id()
        entity = {"id": "test-valid-low-confidence", "source_episode_id": episode_id}
        result = submit_candidate(session, "Class", entity, confidence=0.2)
        assert not result.written
        assert result.validation.valid  # structurally fine, just low confidence

        check = session.run("MATCH (n {id: $id}) RETURN n", id=entity["id"]).single()
        assert check is None
    finally:
        _cleanup("test-valid-low-confidence")
        session.close()
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
