"""
§8.4 Memify feedback loop -- metis_mcp/memify.py's real Beta-Bernoulli
confidence-adjustment mechanism, against real Neo4j ExtractionCorrected
episodes.
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.memify import (
    record_extraction_correction, compute_confidence_adjustment, apply_confidence_adjustment,
    get_adjusted_confidence_default, run_nightly_memify_job,
)

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

RULE = "memify-test-rule"
ETYPE = "memify-test-entity-type"
CONNECTOR = "memify-test-connector"

_driver = None


def _session():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver.session()


def _cleanup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (e:Episode {episode_type: 'ExtractionCorrected', extraction_rule: $rule}) DETACH DELETE e",
            rule=RULE,
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (ca:ConfidenceAdjustment) WHERE ca.extraction_rule = $rule DETACH DELETE ca",
            rule=RULE,
        ).consume())


def test_no_corrections_yields_uniform_prior():
    with _session() as s:
        adjustment = compute_confidence_adjustment(s, RULE, ETYPE, CONNECTOR)
    assert adjustment.alpha == 1
    assert adjustment.beta == 1
    assert adjustment.adjusted_default == 0.5
    assert adjustment.correction_count == 0


def test_corrections_that_consistently_raise_confidence_shift_the_default_up():
    with _session() as s:
        for _ in range(4):
            record_extraction_correction(
                s, entity_id="memify-test-entity-1", extraction_rule=RULE, entity_type=ETYPE,
                connector=CONNECTOR, original_confidence=0.5, corrected_confidence=0.9,
                corrected_by="test-human",
            )
        adjustment = compute_confidence_adjustment(s, RULE, ETYPE, CONNECTOR)
    assert adjustment.alpha == 5  # 1 prior + 4 real increases
    assert adjustment.beta == 1   # 1 prior, 0 decreases
    assert adjustment.adjusted_default > 0.5
    assert adjustment.correction_count == 4


def test_apply_and_lookup_real_round_trip():
    with _session() as s:
        adjustment = compute_confidence_adjustment(s, RULE, ETYPE, CONNECTOR)
        apply_confidence_adjustment(s, adjustment)
        looked_up = get_adjusted_confidence_default(s, RULE, ETYPE, CONNECTOR, fallback_default=0.42)
    assert looked_up == adjustment.adjusted_default
    assert looked_up != 0.42


def test_unknown_triple_returns_the_fallback_not_a_fabricated_midpoint():
    with _session() as s:
        looked_up = get_adjusted_confidence_default(
            s, "never-corrected-rule", "never-corrected-type", "never-corrected-connector",
            fallback_default=0.42,
        )
    assert looked_up == 0.42


def test_reversibility_recomputation_reflects_a_deleted_correction():
    """'Reversible ... not model retraining': deleting a bad correction and
    recomputing must change the adjustment -- no state was baked in that
    survives the correction's removal."""
    with _session() as s:
        record_extraction_correction(
            s, entity_id="memify-test-entity-2", extraction_rule=RULE, entity_type=ETYPE,
            connector=CONNECTOR, original_confidence=0.5, corrected_confidence=0.1,
            corrected_by="test-human-mistake",
        )
        before = compute_confidence_adjustment(s, RULE, ETYPE, CONNECTOR)
        assert before.beta > 1

        s.execute_write(lambda tx: tx.run(
            "MATCH (e:Episode {episode_type: 'ExtractionCorrected', extraction_rule: $rule, "
            "corrected_by: 'test-human-mistake'}) DETACH DELETE e", rule=RULE,
        ).consume())
        after = compute_confidence_adjustment(s, RULE, ETYPE, CONNECTOR)
    assert after.beta == before.beta - 1


def test_run_nightly_memify_job_discovers_and_applies_all_real_triples():
    with _session() as s:
        record_extraction_correction(
            s, entity_id="memify-test-entity-3", extraction_rule=RULE, entity_type=ETYPE,
            connector=CONNECTOR, original_confidence=0.5, corrected_confidence=0.9,
            corrected_by="test-human",
        )
        updated_keys = run_nightly_memify_job(s)
        expected_key = f"{RULE}::{ETYPE}::{CONNECTOR}"
        assert expected_key in updated_keys

        rec = s.run("MATCH (ca:ConfidenceAdjustment {id: $id}) RETURN ca.adjusted_default AS v",
                     id=expected_key).single()
    assert rec is not None
    assert rec["v"] is not None


if __name__ == "__main__":
    if not NEO4J_PASSWORD:
        print("METIS_NEO4J_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    try:
        for t in tests:
            _cleanup()
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
