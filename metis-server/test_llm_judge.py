"""
Real tests for Layer 6 LLM-as-judge -- makes REAL, costed calls to a real
Claude model via the `claude` CLI (metis_mcp/llm_client.py). Unlike every
other test file in this project, this one is NOT run as part of routine
regression testing (no `.venv/bin/python3 test_llm_judge.py` in CLAUDE.md's
standard command list) -- each run costs real money (~$0.05-0.15 per test
here) and takes real wall-clock time for a real model round-trip. Run it
deliberately, not automatically, when verifying Layer 6 itself changed.

Uses real text from this project's own corpus (CONST-047's actual defining
sentence), not synthetic examples -- matching this project's established
testing discipline.
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.llm_judge import judge_claim, apply_judge_to_quarantine_item

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

REAL_SOURCE = (
    "**CONST-047.** Every Requirement/MicroRequirement reaching Approved MUST "
    "be scored against ISO/IEC/IEEE 29148 requirement quality characteristics "
    "(unambiguous, complete, singular, feasible, verifiable, correct, "
    "necessary, consistent) as a structured checklist attached to the entity, "
    "not a free-text judgment call."
)


def test_judge_supports_a_claim_the_real_text_actually_makes():
    result = judge_claim(
        REAL_SOURCE,
        "CONST-047 requires scoring requirements against ISO/IEC/IEEE 29148 "
        "quality characteristics before they reach Approved status.",
    )
    assert result.supported is True


def test_judge_rejects_a_claim_the_real_text_does_not_make():
    result = judge_claim(
        REAL_SOURCE,
        "CONST-047 requires every requirement to be reviewed by at least "
        "three human reviewers before approval.",
    )
    assert result.supported is False


def test_disagreement_marks_real_node_disputed_with_specific_reason():
    """Real end-to-end: judge disagreement must be recorded on the graph
    itself (CONST-049's 'surfaced, never silently resolved'), not just
    returned to the caller and forgotten. Requires a real :Class node
    already in the graph with a real source_episode_id (from Phase 3's
    Cognify run) -- uses whatever real one exists rather than fabricating a
    fixture, since this is specifically testing the real write path."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            rec = s.run(
                "MATCH (c:Class) MATCH (e:Episode {id: c.source_episode_id}) "
                "RETURN c.id AS id, e.raw_content AS content LIMIT 1"
            ).single()
            assert rec is not None, "no real Class entity with a real Episode exists -- run Phase 3 first"
            node_id, content = rec["id"], rec["content"]

            false_claim = "This code establishes a direct TCP socket connection to a remote SMTP mail server."
            result = apply_judge_to_quarantine_item(s, node_id, content[:2000], false_claim)
            assert result.supported is False

            check = s.run(
                "MATCH (n {id: $id}) RETURN n.lifecycle_state AS ls, n.dispute_reason AS dr", id=node_id
            ).single()
            assert check["ls"] == "Disputed"
            assert check["dr"] is not None and len(check["dr"]) > 0
    finally:
        driver.close()


if __name__ == "__main__":
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
