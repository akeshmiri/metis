"""
CONST-047's 4 deterministic ISO/IEC/IEEE 29148 characteristics
(unambiguous/complete/singular/consistent) -- metis_mcp/requirement_quality.py.
No LLM calls, no cost -- the 4 judgment characteristics (verifiable/
feasible/correct/necessary) are tested separately in
test_requirement_quality_llm.py (real, costed, deliberately excluded from
routine regression, same convention as test_llm_judge.py).
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.requirement_quality import score_deterministic, write_checklist
from metis_mcp.ears_checker import check_ears_conformance
import json

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

_driver = None


def _session():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver.session()


REQUIREMENTS = {
    "reqq-test-good": "When a subscription renews, the payment service shall charge the customer within 2 seconds.",
    "reqq-test-vague": "The system shall provide a user-friendly experience.",
    "reqq-test-placeholder": "The system shall support TBD authentication.",
    "reqq-test-bundled": "When a subscription renews, the payment service shall charge the customer "
                          "and shall send a confirmation email.",
    "reqq-test-nonconformant": "Users should probably be able to cancel orders sometimes.",
    "reqq-test-conflict-a": "When an order is placed, the system shall respond within 2 seconds.",
    "reqq-test-conflict-b": "When an order is placed, the system shall respond within 5 seconds.",
}


def _setup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Episode {id: 'reqq-test-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'test', e.job_id = 'test'"
        ).consume())
        for rid, text in REQUIREMENTS.items():
            # Real ears_pattern, not a placeholder -- score_deterministic's
            # consistency check queries siblings by this stored property, so
            # it must reflect the same pattern check_ears_conformance() would
            # compute, not an arbitrary fixture value.
            pattern = check_ears_conformance(text).pattern or "NonConformant"
            s.execute_write(lambda tx, rid=rid, text=text, pattern=pattern: tx.run(
                "MERGE (r:Requirement {id: $id}) SET r.source_episode_id = 'reqq-test-episode', "
                "r.ears_pattern = $pattern, r.revision = 1, r.corroboration_count = 1, r.text = $text",
                id=rid, text=text, pattern=pattern,
            ).consume())


def _cleanup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (n) WHERE n.id STARTS WITH 'reqq-test-' DETACH DELETE n"
        ).consume())


def test_good_requirement_passes_all_four_deterministic_checks():
    with _session() as s:
        result = score_deterministic(s, "reqq-test-good", REQUIREMENTS["reqq-test-good"])
    assert result.unambiguous, result.reasons["unambiguous"]
    assert result.complete, result.reasons["complete"]
    assert result.singular, result.reasons["singular"]
    assert result.consistent, result.reasons["consistent"]


def test_vague_language_fails_unambiguous():
    with _session() as s:
        result = score_deterministic(s, "reqq-test-vague", REQUIREMENTS["reqq-test-vague"])
    assert not result.unambiguous
    assert "user-friendly" in result.reasons["unambiguous"] or "user friendly" in result.reasons["unambiguous"]


def test_placeholder_marker_fails_complete():
    with _session() as s:
        result = score_deterministic(s, "reqq-test-placeholder", REQUIREMENTS["reqq-test-placeholder"])
    assert not result.complete
    assert "placeholder" in result.reasons["complete"]


def test_bundled_shall_clauses_fails_singular():
    with _session() as s:
        result = score_deterministic(s, "reqq-test-bundled", REQUIREMENTS["reqq-test-bundled"])
    assert not result.singular
    assert "2 'shall'" in result.reasons["singular"]


def test_non_ears_text_fails_complete():
    with _session() as s:
        result = score_deterministic(s, "reqq-test-nonconformant", REQUIREMENTS["reqq-test-nonconformant"])
    assert not result.complete
    assert "Not EARS-conformant" in result.reasons["complete"]


def test_conflicting_numeric_threshold_fails_consistent():
    """reqq-test-conflict-a/-b share the identical response shape
    ('respond within <N> seconds') but disagree on the threshold (2 vs 5) --
    a real, specific spec-vs-spec disagreement, both fixtures already
    written to the graph by _setup()."""
    with _session() as s:
        result = score_deterministic(s, "reqq-test-conflict-a", REQUIREMENTS["reqq-test-conflict-a"])
    assert not result.consistent
    assert "reqq-test-conflict-b" in result.reasons["consistent"]


def test_checklist_writes_as_structured_property_not_free_text():
    with _session() as s:
        result = score_deterministic(s, "reqq-test-good", REQUIREMENTS["reqq-test-good"])
        write_checklist(s, result)
        rec = s.run(
            "MATCH (r:Requirement {id: 'reqq-test-good'}) RETURN r.iso29148_checklist AS c, "
            "r.iso29148_checklist_pass AS p",
        ).single()
    checklist = json.loads(rec["c"])
    assert checklist["unambiguous"] is True
    assert checklist["complete"] is True
    assert checklist["judgment_scored"] is False, "no LLM call made in this deterministic-only test"
    assert rec["p"] is False, "all_pass must be False while the 4 judgment characteristics are unscored"


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
