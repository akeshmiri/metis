"""
Tests for Layer 3 confidence tiering (REQ-METIS-GRD-03) -- the state
machine only, no judge-call/LLM logic (deferred, needs a real model call).
Each test targets one specific branch of the spec's rule.
"""
from metis_mcp.confidence_tiering import ConfidenceTiering, ConfidenceTier


def test_high_confidence_single_source_passes_l2_is_auto_write():
    tiering = ConfidenceTiering()
    result = tiering.evaluate(confidence=0.95, structural_valid=True,
                               has_contradiction=False, source_count=1)
    assert result.tier == ConfidenceTier.AUTO_WRITE
    assert result.lifecycle_state == "Draft"
    assert result.written_to_graph


def test_mid_confidence_is_quarantine():
    tiering = ConfidenceTiering()
    result = tiering.evaluate(confidence=0.75, structural_valid=True, has_contradiction=False)
    assert result.tier == ConfidenceTier.QUARANTINE
    assert result.lifecycle_state == "Quarantine"
    assert result.written_to_graph


def test_low_confidence_is_rejected():
    tiering = ConfidenceTiering()
    result = tiering.evaluate(confidence=0.4, structural_valid=True, has_contradiction=False)
    assert result.tier == ConfidenceTier.REJECTED
    assert result.lifecycle_state == "Rejected"
    assert not result.written_to_graph


def test_l2_failure_is_rejected_regardless_of_high_confidence():
    """A structural-validation failure overrides even a 0.99 confidence
    score -- the spec's '<0.6 or L2-fail or contradiction -> Rejected'
    clause, tested specifically for the L2-fail branch."""
    tiering = ConfidenceTiering()
    result = tiering.evaluate(confidence=0.99, structural_valid=False, has_contradiction=False)
    assert result.tier == ConfidenceTier.REJECTED
    assert "structural validation" in result.reason.lower()


def test_contradiction_is_rejected_regardless_of_high_confidence():
    tiering = ConfidenceTiering()
    result = tiering.evaluate(confidence=0.99, structural_valid=True, has_contradiction=True)
    assert result.tier == ConfidenceTier.REJECTED
    assert "contradict" in result.reason.lower()


def test_boundary_exactly_0_9_is_auto_write():
    tiering = ConfidenceTiering()
    result = tiering.evaluate(confidence=0.9, structural_valid=True, has_contradiction=False)
    assert result.tier == ConfidenceTier.AUTO_WRITE


def test_boundary_exactly_0_6_is_quarantine():
    tiering = ConfidenceTiering()
    result = tiering.evaluate(confidence=0.6, structural_valid=True, has_contradiction=False)
    assert result.tier == ConfidenceTier.QUARANTINE


def test_boundary_just_below_0_6_is_rejected():
    tiering = ConfidenceTiering()
    result = tiering.evaluate(confidence=0.5999, structural_valid=True, has_contradiction=False)
    assert result.tier == ConfidenceTier.REJECTED


def test_rejected_items_are_never_marked_written_to_graph():
    tiering = ConfidenceTiering()
    result = tiering.evaluate(confidence=0.1, structural_valid=True, has_contradiction=False)
    assert result.written_to_graph is False


if __name__ == "__main__":
    import sys
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
