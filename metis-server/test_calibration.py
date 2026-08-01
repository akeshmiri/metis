"""
Real test for the CONST-036 calibration batch (guardrails/calibration.py)
-- makes REAL, costed calls to a real Claude model. Same convention as
test_llm_judge.py/test_microrequirement.py: not part of routine regression
testing, run deliberately.
"""
import os
import sys

from neo4j import GraphDatabase

from guardrails.calibration import run_calibration_batch
from metis_mcp.cost_gate import BatchNotConfirmedError, TYPICAL_BATCH_SIZE

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")


def test_calibration_batch_produces_a_real_distribution_over_real_entities():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            result = run_calibration_batch(s, sample_size=4, confirmed=True)
        assert result["sample_size"] == 4
        assert result["spec_required_sample_size"] == 500  # disclosed gap from the real spec requirement
        assert sum(result["distribution"].values()) == 4
        assert all(c.tier in ("auto_write", "quarantine", "rejected") for c in result["cases"])
        assert all(0.0 <= c.confidence <= 1.0 for c in result["cases"])
    finally:
        driver.close()


def test_large_batch_without_confirmation_raises_before_any_real_llm_call():
    """REQ-METIS-COST-08 -- zero cost by construction: gate_batch() fires
    inside run_calibration_batch() before the loop that makes real LLM
    calls even starts, so this test proves the gate without spending
    anything, regardless of the real available pool's actual size."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            try:
                run_calibration_batch(s, sample_size=TYPICAL_BATCH_SIZE + 1, confirmed=False)
                assert False, "must raise BatchNotConfirmedError, never silently proceed"
            except BatchNotConfirmedError as e:
                assert "Confirm to proceed?" in str(e)
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
