"""
Real tests for MicroRequirement decomposition -- makes REAL, costed calls
to a real Claude model (metis_mcp/llm_client.py). Same convention as
test_llm_judge.py: NOT part of routine regression testing, run
deliberately when verifying this module changed.

Uses the exact bundled-requirement example metis-specification.md §7 and
metis-standards-integration.md §1 cite as the canonical illustration of a
29148 'singular'-characteristic failure: "the system shall reject the
refund and notify the customer" -- real project text, not invented for
this test.

All three assertions share ONE real call (module-level, computed once) --
each is a real, separate API call otherwise, and three checks on the exact
same decomposition don't need three separate real model round-trips.
"""
import sys

from metis_mcp.microrequirement import decompose_requirement

REAL_BUNDLED_REQUIREMENT = "The system shall reject the refund and notify the customer."
_result = None


def _get_result():
    global _result
    if _result is None:
        _result = decompose_requirement(REAL_BUNDLED_REQUIREMENT)
    return _result


def test_decomposes_real_bundled_requirement_into_multiple_atomic_pieces():
    assert len(_get_result().micro_requirements) >= 2


def test_every_micro_requirement_is_ears_conformant():
    """The LLM proposes the split; the deterministic EARS checker verifies
    it -- per §9, the judgment step doesn't get to self-certify structure."""
    for m in _get_result().micro_requirements:
        assert m.ears_conformant, f"non-conformant MicroRequirement produced: {m.text!r}"


def test_no_behavior_is_dropped_refund_and_notification_both_present():
    combined = " ".join(m.text.lower() for m in _get_result().micro_requirements)
    assert "refund" in combined
    assert "notif" in combined  # notify/notification


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
