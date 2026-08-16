"""
Equivalence partitioning and boundary value analysis tests
(ISO/IEC/IEEE 29119-4; spec M-9, M-17).

Free to run: analysis is pure.
"""
import re
import sys

from metis_mcp.mbt.model import IMPLEMENTED, PLANNED, Model, State, Transition
from metis_mcp.mbt.techniques import (
    ABOVE,
    AT,
    BELOW,
    FROM_PREDICATE,
    FROM_THRESHOLD,
    analyse_group,
    analyse_guard,
    analyse_transition,
    format_techniques,
)


# --------------------------------------------------------------------------
# Boundary value analysis — the three-point set
# --------------------------------------------------------------------------

def test_a_threshold_yields_exactly_the_three_point_set():
    r = analyse_guard("attempts >= 5")
    assert [b.condition for b in r.boundaries] == [
        "attempts = 4", "attempts = 5", "attempts = 6"]
    assert [b.position for b in r.boundaries] == [BELOW, AT, ABOVE]


def test_each_boundary_names_the_guard_it_came_from():
    for b in analyse_guard("attempts >= 5").boundaries:
        assert b.source_guard == "attempts >= 5"


def test_a_float_threshold_keeps_its_precision():
    r = analyse_guard("confidence >= 0.9")
    assert "confidence = 0.9" in [b.condition for b in r.boundaries]


def test_an_integer_threshold_is_not_rendered_as_a_float():
    """`attempts = 5`, never `attempts = 5.0` — a tester reads this."""
    for b in analyse_guard("attempts >= 5").boundaries:
        assert ".0" not in b.condition


# --------------------------------------------------------------------------
# Equivalence partitioning
# --------------------------------------------------------------------------

def test_a_threshold_partitions_the_domain_either_side():
    conditions = [p.condition for p in analyse_guard("attempts >= 5").partitions]
    assert conditions == ["attempts < 5", "attempts >= 5"]


def test_a_less_than_guard_partitions_the_other_way():
    conditions = [p.condition for p in analyse_guard("attempts < 5").partitions]
    assert conditions == ["attempts < 5", "attempts >= 5"]


def test_an_equality_guard_partitions_into_equal_and_not_equal():
    conditions = [p.condition for p in analyse_guard("status == 3").partitions]
    assert conditions == ["status == 3", "status != 3"]


def test_a_conjunction_is_analysed_atom_by_atom():
    r = analyse_guard("credentials_valid AND attempts >= 5")
    conditions = [p.condition for p in r.partitions]
    assert "credentials_valid" in conditions
    assert "NOT (credentials_valid)" in conditions
    assert "attempts >= 5" in conditions
    assert len(r.boundaries) == 3, "only the numeric atom has boundaries"


# --------------------------------------------------------------------------
# M-17 : fail-closed on anything not a numeric threshold
# --------------------------------------------------------------------------

def test_a_predicate_partitions_two_ways_and_yields_no_boundary():
    """`t.isEmpty()` has no boundary. Inventing one would be inventing data."""
    r = analyse_guard("t.isEmpty()")
    assert [p.condition for p in r.partitions] == ["t.isEmpty()", "NOT (t.isEmpty())"]
    assert r.boundaries == []
    assert r.unanalysable and "no boundary" in r.unanalysable[0][1]


def test_call_syntax_survives_the_atom_split():
    """A naive `.strip('()')` turned `t.isEmpty()` into `t.isEmpty` — a condition
    a tester cannot act on, and one that no longer matches its own guard."""
    assert analyse_guard("t.isEmpty()").partitions[0].condition == "t.isEmpty()"


def test_the_derivation_is_recorded_on_every_partition():
    assert analyse_guard("attempts >= 5").partitions[0].derived_from == FROM_THRESHOLD
    assert analyse_guard("t.isEmpty()").partitions[0].derived_from == FROM_PREDICATE


def test_an_empty_guard_yields_nothing_rather_than_guessing():
    r = analyse_guard("")
    assert r.partitions == [] and r.boundaries == []


def test_the_report_states_the_fail_closed_reason():
    text = format_techniques(analyse_guard("t.isEmpty()"))
    assert "NO BOUNDARY DERIVED" in text
    assert "M-17" in text


# --------------------------------------------------------------------------
# M-9 : conditions, never solved values — the load-bearing guarantee
# --------------------------------------------------------------------------

def test_m9_no_output_invents_a_value_outside_the_guards_own_vocabulary():
    """The numbers that appear must be the guard's own threshold or its
    neighbours. Nothing else — no usernames, no payloads, no invented data."""
    r = analyse_guard("attempts >= 5 AND credentials_valid")
    allowed = {"4", "5", "6"}
    for item in [*r.partitions, *r.boundaries]:
        for number in re.findall(r"\d+(?:\.\d+)?", item.condition):
            assert number in allowed, f"{number!r} was invented in {item.condition!r}"


def test_m9_the_output_is_phrased_as_a_requirement_not_a_fixture():
    for b in analyse_guard("attempts >= 5").boundaries:
        assert b.condition.startswith("attempts ")
        assert "=" in b.condition


def test_m9_the_report_says_solving_is_out_of_scope():
    text = format_techniques(analyse_guard("attempts >= 5"))
    assert "never" in text and "invented" in text
    assert "out of scope" in text


# --------------------------------------------------------------------------
# Groups — the right unit of analysis
# --------------------------------------------------------------------------

def _model(guards) -> Model:
    m = Model(
        id="m",
        states={"A": State(id="A", name="A", surface="api", is_initial=True),
                "B": State(id="B", name="B", surface="api")},
        transitions={f"t{i}": Transition(id=f"t{i}", source="A", trigger="go",
                                         target="B", guard=g)
                     for i, g in enumerate(guards)})
    m.reindex()
    return m


def test_a_group_reports_one_boundary_set_not_one_per_guard():
    """`attempts < 5` and `attempts >= 5` describe ONE partitioning of
    `attempts`; analysing them separately would double-report it."""
    r = analyse_group(_model(["attempts < 5", "attempts >= 5"]), "A", "go")
    assert [b.condition for b in r.boundaries] == [
        "attempts = 4", "attempts = 5", "attempts = 6"]
    assert len(r.partitions) == 2


def test_a_planned_transition_contributes_nothing():
    m = _model(["attempts >= 5"])
    m.transitions["future"] = Transition(id="future", source="A", trigger="go",
                                         target="B", guard="attempts >= 99",
                                         implementation_status=PLANNED)
    m.reindex()
    r = analyse_group(m, "A", "go")
    assert not any("99" in b.condition for b in r.boundaries)
    assert analyse_transition(m, "future").boundaries == []


def test_polarity_is_normalised_rather_than_double_negated():
    """`NOT account_locked` partitions into `account_locked` / `NOT (account_locked)`,
    not the unreadable `NOT (NOT account_locked)`."""
    conditions = [p.condition for p in analyse_guard("NOT account_locked").partitions]
    assert conditions == ["account_locked", "NOT (account_locked)"]


# --------------------------------------------------------------------------
# The criterion — P-1a, M-9 and P-3 through the real registry
# --------------------------------------------------------------------------

def test_boundary_coverage_is_registered_alongside_guard_coverage():
    from metis_mcp.mbt.criteria import BOUNDARY_COVERAGE, GUARD_COVERAGE, criterion_names
    names = criterion_names()
    assert BOUNDARY_COVERAGE in names and GUARD_COVERAGE in names, \
        "it sits ALONGSIDE guard coverage, it does not replace it"


def test_p1a_each_boundary_is_its_own_target_not_an_extra_assertion():
    """Deeper criteria add more TESTS, never more assertions per test."""
    from metis_mcp.mbt.criteria import BOUNDARY_COVERAGE, targets_for
    m = _model(["attempts >= 5"])
    for t in m.transitions.values():
        object.__setattr__(t, "lifecycle_state", "Approved")
    r = targets_for(m, BOUNDARY_COVERAGE)
    boundaries = [t for t in r.targets if t.kind == "boundary"]
    assert len(boundaries) == 3
    assert len({t.key for t in boundaries}) == 3, "three separate targets"
    assert all(t.validated_transition_id == "t0" for t in boundaries)


def test_m9_the_criterion_carries_conditions_not_values():
    from metis_mcp.mbt.criteria import BOUNDARY_COVERAGE, targets_for
    m = _model(["attempts >= 5"])
    for t in m.transitions.values():
        object.__setattr__(t, "lifecycle_state", "Approved")
    notes = [t.data_note for t in targets_for(m, BOUNDARY_COVERAGE).targets]
    assert any("attempts = 4" in n for n in notes)
    for n in notes:
        for number in re.findall(r"\d+(?:\.\d+)?", n):
            assert number in {"4", "5", "6"}, f"{number!r} invented in {n!r}"


def test_p3_a_guard_with_no_boundary_is_reported_not_skipped():
    """A criterion that quietly reduces its own requirements reports success it
    did not achieve."""
    from metis_mcp.mbt.criteria import BOUNDARY_COVERAGE, targets_for
    m = _model(["t.isEmpty()"])
    for t in m.transitions.values():
        object.__setattr__(t, "lifecycle_state", "Approved")
    r = targets_for(m, BOUNDARY_COVERAGE)
    assert r.unsatisfiable, "the missing boundary is reported"
    assert any("no boundary" in reason for _, reason in r.unsatisfiable)
    assert [t for t in r.targets if t.kind == "partition"], "partitions still emitted"


def test_analysis_is_deterministic():
    a = analyse_group(_model(["attempts >= 5", "attempts < 5"]), "A", "go")
    b = analyse_group(_model(["attempts >= 5", "attempts < 5"]), "A", "go")
    assert [x.condition for x in a.boundaries] == [x.condition for x in b.boundaries]
    assert [x.condition for x in a.partitions] == [x.condition for x in b.partitions]


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
