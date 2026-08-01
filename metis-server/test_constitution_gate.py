"""
REQ-METIS-GRD-11 (§7.2 Constitution-gated validation) -- metis_mcp/
constitution_gate.py, against a real Neo4j instance. Tests both real
pieces: loading the real 64 Constitution rules from the real docs corpus,
and the CONST-047 hard-block demonstration wired into
guardrails/pipeline.py's submit_candidate.
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.constitution_gate import load_constitution_rules, check_constitution_hard_blocks
from guardrails.pipeline import submit_candidate

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")
CORPUS_GLOB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus", "*.md")

_driver = None


def _session():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver.session()


def _setup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Episode {id: 'cgate-test-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'test', e.job_id = 'test'"
        ).consume())


def _cleanup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (n) WHERE n.id STARTS WITH 'cgate-test-' DETACH DELETE n"
        ).consume())


def test_load_constitution_rules_populates_real_production_nodes():
    with _session() as s:
        result = load_constitution_rules(s, CORPUS_GLOB, "cgate-test-episode")
        assert result["total"] > 30, "the real Constitution has dozens of real, definitionally-tagged rules"
        assert result["changed"] >= 0

        rec = s.run("MATCH (c:Constitution {id: 'CONST-047'}) RETURN c.text AS text").single()
    assert rec is not None, "CONST-047 must be one of the real, definitionally-parsed rules"
    assert "29148" in rec["text"]


def test_load_constitution_rules_is_idempotent_no_spurious_revisions_on_rerun():
    """REQ-METIS-ACD-05's changelog must reflect REAL changes, not noise
    from re-running the loader against unchanged content."""
    with _session() as s:
        load_constitution_rules(s, CORPUS_GLOB, "cgate-test-episode")  # ensure at least one prior run
        second_run = load_constitution_rules(s, CORPUS_GLOB, "cgate-test-episode")
    assert second_run["changed"] == 0, "re-running against unchanged real content must create no new revisions"


def test_vague_requirement_is_blocked_by_const047():
    with _session() as s:
        result = check_constitution_hard_blocks(
            s, "Requirement", {"id": "x", "text": "The system shall provide a user-friendly experience."},
        )
    assert result.blocked
    assert result.rule_id == "CONST-047"
    assert "unambiguous" in result.reason


def test_good_requirement_is_not_blocked():
    with _session() as s:
        result = check_constitution_hard_blocks(
            s, "Requirement",
            {"id": "y", "text": "When a subscription renews, the payment service shall charge the customer."},
        )
    assert not result.blocked


def test_non_requirement_labels_are_never_checked():
    with _session() as s:
        result = check_constitution_hard_blocks(s, "Defect", {"id": "z", "text": "vague and user-friendly"})
    assert not result.blocked


def test_submit_candidate_hard_rejects_a_bad_requirement_even_at_high_confidence():
    """The whole point of GRD-11: 'always a hard block, never a
    Quarantine-tier soft flag' -- confidence=0.99 must not matter."""
    with _session() as s:
        entity = {
            "id": "cgate-test-bad-requirement", "source_episode_id": "cgate-test-episode",
            "ears_pattern": "Ubiquitous", "revision": 1, "corroboration_count": 1,
            "text": "The system shall provide a user-friendly experience.",
        }
        result = submit_candidate(s, "Requirement", entity, confidence=0.99)
        assert not result.written
        assert result.tiering.lifecycle_state == "Rejected"
        assert result.constitution.blocked
        assert result.constitution.rule_id == "CONST-047"

        check = s.run("MATCH (n {id: $id}) RETURN n", id=entity["id"]).single()
    assert check is None, "must never be written to the graph, not even at Quarantine tier"


def test_submit_candidate_allows_a_good_requirement_through_normally():
    with _session() as s:
        entity = {
            "id": "cgate-test-good-requirement", "source_episode_id": "cgate-test-episode",
            "ears_pattern": "EventDriven", "revision": 1, "corroboration_count": 1,
            "text": "When a subscription renews, the payment service shall charge the customer.",
        }
        result = submit_candidate(s, "Requirement", entity, confidence=0.95)
    assert result.written
    assert result.constitution is None, "Constitution check isn't even consulted once it passes -- " \
                                         "only populated on a hard-block hit"


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
