"""
CONST-047's 4 judgment ISO/IEC/IEEE 29148 characteristics (verifiable/
feasible/correct/necessary) -- metis_mcp/requirement_quality.py's
score_judgment(). REAL, COSTED model calls via the `claude` CLI (no
ANTHROPIC_API_KEY needed -- llm_client.py). Deliberately excluded from
routine regression, same convention as test_llm_judge.py/
test_microrequirement.py/test_calibration.py -- run explicitly when you
want to spend the real (small) cost this incurs.
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.requirement_quality import score_deterministic, score_judgment, write_checklist
from metis_mcp.ears_checker import check_ears_conformance
import json

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

GOOD_TEXT = "When a subscription renews, the payment service shall charge the customer within 2 seconds."
INFEASIBLE_TEXT = "The system shall guarantee zero downtime forever under any possible failure condition."

_driver = None


def _session():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver.session()


def _setup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Episode {id: 'reqqllm-test-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'test', e.job_id = 'test'"
        ).consume())
        for rid, text in (("reqqllm-test-good", GOOD_TEXT), ("reqqllm-test-infeasible", INFEASIBLE_TEXT)):
            pattern = check_ears_conformance(text).pattern or "NonConformant"
            s.execute_write(lambda tx, rid=rid, text=text, pattern=pattern: tx.run(
                "MERGE (r:Requirement {id: $id}) SET r.source_episode_id = 'reqqllm-test-episode', "
                "r.ears_pattern = $pattern, r.revision = 1, r.corroboration_count = 1, r.text = $text",
                id=rid, text=text, pattern=pattern,
            ).consume())


def _cleanup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (n) WHERE n.id STARTS WITH 'reqqllm-test-' DETACH DELETE n"
        ).consume())


def test_real_llm_call_scores_all_four_judgment_characteristics():
    with _session() as s:
        result = score_deterministic(s, "reqqllm-test-good", GOOD_TEXT)
        result = score_judgment(result)
    assert result.judgment_scored
    assert result.judgment_cost_usd > 0, "a real model call must report a real nonzero cost"
    assert result.verifiable is not None
    assert result.feasible is not None
    assert result.correct is not None
    assert result.necessary is not None


def test_real_llm_flags_an_unfeasible_absolute_guarantee():
    """'guarantee zero downtime forever under any possible failure
    condition' is a real, recognizable infeasible/unverifiable absolute --
    a genuine judgment call, not something the deterministic checks catch."""
    with _session() as s:
        result = score_deterministic(s, "reqqllm-test-infeasible", INFEASIBLE_TEXT)
        result = score_judgment(result)
    assert result.feasible is False or result.verifiable is False, result.reasons.get("judgment")


def test_checklist_write_reflects_full_eight_characteristic_result():
    with _session() as s:
        result = score_deterministic(s, "reqqllm-test-good", GOOD_TEXT)
        result = score_judgment(result)
        write_checklist(s, result)
        rec = s.run(
            "MATCH (r:Requirement {id: 'reqqllm-test-good'}) RETURN r.iso29148_checklist AS c, "
            "r.iso29148_checklist_pass AS p",
        ).single()
    checklist = json.loads(rec["c"])
    assert checklist["judgment_scored"] is True
    assert checklist["judgment_model"] == "sonnet"
    assert rec["p"] == (checklist["unambiguous"] and checklist["complete"] and checklist["singular"]
                         and checklist["consistent"] and checklist["verifiable"] and checklist["feasible"]
                         and checklist["correct"] and checklist["necessary"])


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
