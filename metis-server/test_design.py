"""
Test design — choosing a technique, not just a path (ISO/IEC/IEEE 29119-4).

**Step 5 of the journey, and it did not exist.** Métis had five *coverage
criteria*, and those answer "which walks through the machine" — path selection.
Test design is the prior question: given this behaviour, which technique finds
its defects? Two were missing, and both turned out computable from what the
graph already holds.

The rule every test here enforces is **M-9**: a technique states a *condition on
the data* and never solves it. "this parameter is omitted", "this field violates
`@NotNull`" — conditions. A username, a payload, a number — values, and none is
produced.

The second rule is **fail-closed (M-17)**: a table that cannot be built says so
rather than emitting a partial one, because a missing row reads exactly like a
covered one.
"""
from __future__ import annotations

import sys

from metis_mcp.mbt.design import (
    Factor,
    all_pairs,
    decision_table,
    factors_for,
)
from metis_mcp.mbt.model import APPROVED, Model, State, Transition


def _model(*guards: str) -> Model:
    states = {"S": State(id="S", name="S", surface="api", is_initial=True,
                         lifecycle_state=APPROVED),
              "T": State(id="T", name="T", surface="api", lifecycle_state=APPROVED)}
    transitions = {
        f"t{i}": Transition(id=f"t{i}", source="S", trigger="POST /x", target="T",
                            guard=g, lifecycle_state=APPROVED)
        for i, g in enumerate(guards)}
    m = Model(id="m-api", states=states, transitions=transitions)
    m.reindex()
    return m


# --------------------------------------------------------------------------
# Decision table
# --------------------------------------------------------------------------

def test_a_group_becomes_a_table_of_combinations():
    """Guard coverage varies each condition independently; a table asks what the
    COMBINATIONS produce, which is where a missing rule hides."""
    table = decision_table(_model("a AND b", "a AND NOT (b)", "NOT (a)"), "S", "POST /x")
    assert table.is_available, table.reason_unavailable
    assert table.conditions == ("a", "b")
    assert len(table.rules) == 4, "two conditions is four rows"
    assert all(r.is_covered for r in table.rules)


def test_a_combination_no_transition_covers_is_reported_not_invented():
    """Not necessarily a defect — the conditions may be unable to hold together,
    which is not decidable from the text. Reported for a human either way."""
    table = decision_table(_model("a AND b", "NOT (a)"), "S", "POST /x")
    uncovered = table.uncovered
    assert len(uncovered) == 1
    assert uncovered[0].describe() == "a and NOT (b)"
    assert "cannot hold together" in uncovered[0].unreachable_note


def test_a_disjunction_makes_the_table_unavailable():
    """M-17. Half a table is worse than none: a missing row reads as covered."""
    table = decision_table(_model("a OR b", "NOT (a)"), "S", "POST /x")
    assert not table.is_available
    assert "OR" in table.reason_unavailable


def test_a_numeric_condition_is_left_to_boundary_analysis():
    """Treating `attempts >= 5` as a boolean invents rows that cannot occur —
    the same defect `_boolean_coverage_gap` refuses for the same reason."""
    table = decision_table(_model("attempts >= 5", "attempts < 5"), "S", "POST /x")
    assert not table.is_available
    assert "boundary" in table.reason_unavailable


def test_a_group_of_one_yields_no_table():
    table = decision_table(_model("a"), "S", "POST /x")
    assert not table.is_available
    assert "one row states nothing" in table.reason_unavailable


def test_an_explosive_group_is_reported_rather_than_generated():
    """P-3b: the cost is reported, never silently produced."""
    guards = [" AND ".join(f"c{i}" for i in range(8)), "NOT (c0)"]
    table = decision_table(_model(*guards), "S", "POST /x")
    assert not table.is_available
    assert "rows" in table.reason_unavailable


# --------------------------------------------------------------------------
# Pairwise
# --------------------------------------------------------------------------

def _transition(*parameters) -> Transition:
    return Transition(id="t", source="S", trigger="POST /x", target="T",
                      inputs=tuple(parameters), lifecycle_state=APPROVED)


def test_an_optional_parameter_varies_as_supplied_or_omitted():
    factors = factors_for(_transition(
        {"name": "page", "required": False, "constraints": []}))
    assert factors[0].levels == ("supplied", "omitted")


def test_a_constrained_parameter_varies_against_its_own_constraint():
    """M-9: the constraint is quoted from the model. Nothing invents what a
    violating value would BE."""
    factors = factors_for(_transition(
        {"name": "dto", "required": True, "constraints": ["@NotNull"]}))
    assert factors[0].levels == ("satisfies @NotNull", "violates @NotNull")


def test_no_output_names_anything_outside_the_models_vocabulary():
    """The M-9 assertion, stated directly."""
    factors = factors_for(_transition(
        {"name": "size", "required": True, "constraints": ["@Size(max=64)"]}))
    for level in factors[0].levels:
        assert "@Size(max=64)" in level
        assert not any(ch.isdigit() for ch in level.replace("@Size(max=64)", "")), (
            "a digit outside the quoted constraint would be an invented value")


def test_all_pairs_covers_every_pair_at_a_fraction_of_the_product():
    factors = [Factor(f"f{i}", ("on", "off")) for i in range(5)]
    cases = all_pairs(factors)
    exhaustive = 2 ** 5
    assert len(cases) < exhaustive / 2, f"{len(cases)} is no saving over {exhaustive}"

    for i, a in enumerate(factors):
        for b in factors[i + 1:]:
            for la in a.levels:
                for lb in b.levels:
                    assert any(c[a.name] == la and c[b.name] == lb for c in cases), (
                        f"pair ({a.name}={la}, {b.name}={lb}) uncovered")


def test_generation_is_deterministic():
    """P-7. A suite built from a non-deterministic generator cannot be reviewed,
    because the thing reviewed is not the thing regenerated."""
    factors = [Factor(f"f{i}", ("on", "off")) for i in range(4)]
    assert all_pairs(factors) == all_pairs(factors)


def test_one_factor_still_yields_its_levels():
    """No pair to cover, but one varying input still varies — returning nothing
    would silently drop it from coverage."""
    assert len(all_pairs([Factor("only", ("on", "off"))])) == 2


def test_no_factors_yields_nothing_rather_than_a_placeholder():
    assert all_pairs([]) == []


# --------------------------------------------------------------------------
# Registered as real criteria, so the whole chain can use them.
# --------------------------------------------------------------------------

def test_both_techniques_are_selectable_criteria():
    from metis_mcp.mbt.criteria import criterion_names

    names = criterion_names()
    assert "decision-table" in names
    assert "pairwise" in names


def test_a_decision_table_target_carries_its_row_as_a_data_requirement():
    from metis_mcp.mbt.criteria import targets_for

    result = targets_for(_model("a AND b", "a AND NOT (b)", "NOT (a)"), "decision-table")
    assert result.targets
    for target in result.targets:
        assert target.data_note, "a row with no stated condition is not a design"
        assert target.validated_transition_id


def test_an_uncovered_row_is_unsatisfiable_never_a_target():
    """A target that can never pass is worse than an admitted gap."""
    from metis_mcp.mbt.criteria import targets_for

    result = targets_for(_model("a AND b", "NOT (a)"), "decision-table")
    assert result.unsatisfiable
    assert all(t.validated_transition_id for t in result.targets)


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
        except Exception as e:                                    # noqa: BLE001
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
