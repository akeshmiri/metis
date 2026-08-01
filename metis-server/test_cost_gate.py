"""
REQ-METIS-COST-08 -- metis_mcp/cost_gate.py. Pure unit tests, no external
dependency (no Neo4j, no LLM call -- the whole point of this gate is to
fire BEFORE any real cost is incurred).
"""
import sys

from metis_mcp.cost_gate import plan_batch, gate_batch, BatchNotConfirmedError, TYPICAL_BATCH_SIZE


def test_typical_sized_batch_needs_no_confirmation():
    plan = plan_batch(item_count=TYPICAL_BATCH_SIZE, stage_count=1)
    assert plan.requires_confirmation is False
    assert plan.prompt == ""


def test_larger_than_typical_batch_requires_confirmation():
    plan = plan_batch(item_count=TYPICAL_BATCH_SIZE + 1, stage_count=1)
    assert plan.requires_confirmation is True
    assert "Confirm to proceed? [yes/no]" in plan.prompt
    assert str(TYPICAL_BATCH_SIZE + 1) in plan.prompt


def test_gate_batch_raises_without_confirmation():
    try:
        gate_batch(item_count=TYPICAL_BATCH_SIZE + 50, confirmed=False)
        assert False, "must raise, never silently proceed"
    except BatchNotConfirmedError as e:
        assert "Confirm to proceed?" in str(e)


def test_gate_batch_proceeds_once_confirmed():
    plan = gate_batch(item_count=TYPICAL_BATCH_SIZE + 50, confirmed=True)
    assert plan.item_count == TYPICAL_BATCH_SIZE + 50


def test_gate_batch_never_raises_for_a_routine_sized_batch_even_unconfirmed():
    plan = gate_batch(item_count=5, confirmed=False)
    assert plan.item_count == 5


def test_estimated_cost_scales_with_item_count():
    small = plan_batch(item_count=10, cost_per_item_usd=0.05)
    large = plan_batch(item_count=100, cost_per_item_usd=0.05)
    assert large.estimated_cost_usd > small.estimated_cost_usd
    assert large.estimated_cost_usd == 5.0


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
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
