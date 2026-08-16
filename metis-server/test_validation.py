"""
Model well-formedness tests (application spec §2.6, M-17, M-18; A-1..A-4).

Free to run: validation is pure.
"""
import sys

from metis_mcp.mbt.model import IMPLEMENTED, PLANNED, Model, State, Transition
from metis_mcp.mbt.validation import (
    ADVISORY,
    BLOCKING,
    DETERMINISM,
    GUARD_COMPLETENESS,
    OBSERVABILITY,
    REACHABILITY,
    UNVERIFIABLE,
    ValidationFailed,
    check_ac_coverage,
    check_determinism,
    check_guard_completeness,
    check_observability,
    check_reachability,
    format_validation,
    require_valid,
    validate,
)
from mbt_fixtures import login_model


def _model(states, transitions) -> Model:
    m = Model(
        id="t",
        states={s[0]: State(id=s[0], name=s[0], surface="api", is_initial=s[1])
                for s in states},
        transitions={t[0]: Transition(id=t[0], source=t[1], trigger=t[2], target=t[3],
                                      guard=t[4],
                                      implementation_status=(t[5] if len(t) > 5
                                                             else IMPLEMENTED))
                     for t in transitions},
    )
    m.reindex()
    return m


# --------------------------------------------------------------------------
# The real model must pass — the chain stays working
# --------------------------------------------------------------------------

def test_the_real_login_model_is_well_formed():
    result = validate(login_model())
    assert result.is_valid(), format_validation(result)
    assert result.checked == 16, "16 implemented transitions; the planned one is excluded"


def test_planned_transitions_are_excluded_from_every_check():
    """P-11: behaviour nobody has built cannot conflict with anything."""
    model = _model(
        [("A", True), ("B", False)],
        [("t1", "A", "go", "B", "x >= 5"),
         ("t2", "A", "go", "B", "x >= 1", PLANNED)],
    )
    assert check_determinism(model) == []


# --------------------------------------------------------------------------
# A-1 : determinism blocks
# --------------------------------------------------------------------------

def test_a1_overlapping_guards_block():
    model = _model(
        [("A", True), ("B", False)],
        [("t1", "A", "go", "B", "attempts >= 3"),
         ("t2", "A", "go", "B", "attempts >= 5")],
    )
    findings = check_determinism(model)
    assert len(findings) == 1
    assert findings[0].severity == BLOCKING
    assert set(findings[0].element_ids) == {"t1", "t2"}
    assert not validate(model).is_valid()


def test_a1_a_clean_partition_is_not_flagged():
    """'< 5' and '>= 5' partition exactly at the boundary."""
    model = _model(
        [("A", True), ("B", False)],
        [("t1", "A", "go", "B", "attempts < 5"),
         ("t2", "A", "go", "B", "attempts >= 5")],
    )
    assert check_determinism(model) == []


def test_an_unguarded_sibling_is_named_as_certain_not_unverifiable():
    """An empty guard means *always*; the conflict is certain, so saying
    'unverifiable' would be true but useless."""
    model = _model(
        [("A", True), ("B", False)],
        [("t1", "A", "go", "B", ""),
         ("t2", "A", "go", "B", "attempts >= 5")],
    )
    findings = check_determinism(model)
    assert len(findings) == 1
    assert findings[0].severity == BLOCKING
    assert "unguarded" in findings[0].detail


def test_a_group_of_one_is_never_flagged():
    model = _model([("A", True), ("B", False)], [("t1", "A", "go", "B", "anything")])
    assert check_determinism(model) == []
    assert check_guard_completeness(model) == []


def test_different_triggers_are_different_groups():
    model = _model(
        [("A", True), ("B", False)],
        [("t1", "A", "go", "B", "x >= 3"), ("t2", "A", "stop", "B", "x >= 3")],
    )
    assert check_determinism(model) == []


# --------------------------------------------------------------------------
# A-2 : unparseable guards are unverifiable, never assumed true (M-17)
# --------------------------------------------------------------------------

def test_a2_an_unparseable_guard_is_unverifiable_not_a_pass():
    """The pair must be genuinely undecidable. `credentials_valid AND NOT locked`
    vs `NOT credentials_valid` was used here originally and is NOT: one atom
    appears positive in one and negated in the other, so they are provably
    exclusive. Two guards over unrelated atoms are the real case."""
    model = _model(
        [("A", True), ("B", False)],
        [("t1", "A", "go", "B", "account.balance > threshold"),
         ("t2", "A", "go", "B", "user.isPremium()")],
    )
    findings = check_determinism(model)
    assert len(findings) == 1
    assert findings[0].severity == UNVERIFIABLE
    assert "not assumed" in findings[0].remedy


def test_a2_unverifiable_blocks_by_default_and_yields_only_to_an_explicit_flag():
    model = _model(
        [("A", True), ("B", False)],
        [("t1", "A", "go", "B", "account.balance > threshold"),
         ("t2", "A", "go", "B", "user.isPremium()")],
    )
    result = validate(model)
    assert not result.is_valid(), "fail-closed is the default (M-17)"
    assert result.is_valid(allow_unverifiable=True), "the operator may accept the risk"
    assert result.blocking == [], "it is unverifiable, not proven wrong"


def test_unverifiable_and_blocking_are_never_collapsed():
    """'This is wrong' and 'this cannot be shown right' are different facts."""
    model = _model(
        [("A", True), ("B", False)],
        [("t1", "A", "go", "B", "x >= 3"), ("t2", "A", "go", "B", "x >= 5"),
         ("t3", "A", "stop", "B", "opaque one"), ("t4", "A", "stop", "B", "opaque two")],
    )
    result = validate(model)
    # Both checks fire on both groups: `x >= 3`/`x >= 5` overlap AND leave
    # everything below 3 uncovered, which is two real findings, not one repeated.
    assert {f.element_ids for f in result.blocking} == {("t1", "t2")}
    assert {f.element_ids for f in result.unverifiable} == {("t3", "t4")}
    assert {f.check for f in result.blocking} == {DETERMINISM, GUARD_COMPLETENESS}
    assert not (set(result.blocking) & set(result.unverifiable))


# --------------------------------------------------------------------------
# Syntactic complementarity — the other half of M-17
# --------------------------------------------------------------------------

def test_x_and_not_x_are_provably_exclusive_without_interpretation():
    """`t.isEmpty()` vs `NOT (t.isEmpty())` is propositional structure. The
    checker never has to know what `isEmpty` means. 135 findings on the athena
    estate were filed unverifiable for want of this."""
    model = _model(
        [("A", True), ("B", False), ("C", False)],
        [("t1", "A", "go", "B", "t.isEmpty()"),
         ("t2", "A", "go", "C", "NOT (t.isEmpty())")],
    )
    assert check_determinism(model) == []
    assert check_guard_completeness(model) == [], "and jointly exhaustive"
    assert validate(model).is_valid()


def test_identical_guards_are_CERTAINLY_ambiguous_not_merely_unverifiable():
    model = _model(
        [("A", True), ("B", False), ("C", False)],
        [("t1", "A", "go", "B", "t.isEmpty()"), ("t2", "A", "go", "C", "t.isEmpty()")],
    )
    findings = check_determinism(model)
    assert len(findings) == 1
    assert findings[0].severity == BLOCKING, "the same condition always overlaps itself"


def test_exclusivity_needs_one_opposing_atom_exhaustiveness_needs_sole_difference():
    """Two guards differing in TWO literals, one of them opposed, cannot both
    hold — that is exclusivity. They need not cover the domain between them."""
    a = "thrown AND NOT (isConstraint) AND NOT (found)"
    b = "thrown AND isConstraint AND found"
    model = _model([("A", True), ("B", False), ("C", False)],
                   [("t1", "A", "go", "B", a), ("t2", "A", "go", "C", b)])
    assert check_determinism(model) == [], "exclusive"
    assert check_guard_completeness(model), "but NOT shown exhaustive — reported"


def test_an_or_is_not_decided_by_structure():
    """Deciding complementarity over disjunctions needs real boolean reasoning;
    pretending otherwise is what M-17 forbids."""
    from metis_mcp.behavior_model import syntactic_relation
    assert syntactic_relation("x OR y", "NOT (x OR y)") is None


def test_unrelated_atoms_remain_unverifiable():
    from metis_mcp.behavior_model import syntactic_relation
    assert syntactic_relation("a AND b", "c AND d") is None


# --------------------------------------------------------------------------
# Guard completeness
# --------------------------------------------------------------------------

def test_a_gap_between_guards_blocks():
    """severity >= 0.9 and severity < 0.5 leave [0.5, 0.9) matching nothing."""
    model = _model(
        [("A", True), ("B", False)],
        [("t1", "A", "go", "B", "severity >= 0.9"),
         ("t2", "A", "go", "B", "severity < 0.5")],
    )
    findings = check_guard_completeness(model)
    assert len(findings) == 1
    assert findings[0].severity == BLOCKING
    assert "gap in guard coverage" in findings[0].detail


def test_a_jointly_exhaustive_group_is_not_flagged():
    model = _model(
        [("A", True), ("B", False)],
        [("t1", "A", "go", "B", "severity >= 0.5"),
         ("t2", "A", "go", "B", "severity < 0.5")],
    )
    assert check_guard_completeness(model) == []


def test_an_unguarded_member_makes_the_group_complete_by_construction():
    """It fires for every input. It is still ambiguous — reported by determinism,
    not duplicated here."""
    model = _model(
        [("A", True), ("B", False)],
        [("t1", "A", "go", "B", ""), ("t2", "A", "go", "B", "x >= 5")],
    )
    assert check_guard_completeness(model) == []
    assert check_determinism(model)


# --------------------------------------------------------------------------
# Reachability
# --------------------------------------------------------------------------

def test_an_unreachable_state_blocks():
    model = _model(
        [("A", True), ("B", False), ("Orphan", False)],
        [("t1", "A", "go", "B", "")],
    )
    findings = [f for f in check_reachability(model) if f.severity == BLOCKING]
    assert len(findings) == 1 and findings[0].element_ids == ("Orphan",)


def test_a_terminal_state_is_advisory_not_blocking():
    """A machine legitimately ends somewhere."""
    model = _model([("A", True), ("B", False)], [("t1", "A", "go", "B", "")])
    findings = check_reachability(model)
    assert [f.severity for f in findings] == [ADVISORY]
    assert findings[0].element_ids == ("B",)
    assert validate(model).is_valid()


def test_no_initial_state_blocks():
    model = _model([("A", False), ("B", False)], [("t1", "A", "go", "B", "")])
    findings = check_reachability(model)
    assert findings[0].severity == BLOCKING
    assert "no initial state" in findings[0].detail


def test_reachability_follows_chains():
    model = _model(
        [("A", True), ("B", False), ("C", False), ("D", False)],
        [("t1", "A", "go", "B", ""), ("t2", "B", "go", "C", ""), ("t3", "C", "go", "D", "")],
    )
    assert [f.severity for f in check_reachability(model)] == [ADVISORY]


def test_a_state_reachable_only_by_a_planned_transition_is_unreachable():
    """P-11 again: planned behaviour cannot be the thing that makes a state real."""
    model = _model(
        [("A", True), ("B", False)],
        [("t1", "A", "go", "B", "", PLANNED)],
    )
    assert any(f.severity == BLOCKING and f.element_ids == ("B",)
               for f in check_reachability(model))


# --------------------------------------------------------------------------
# A-4 : observability
# --------------------------------------------------------------------------

def test_a4_two_states_presenting_identically_block():
    model = Model(id="t", states={
        "s1": State(id="s1", name="Locked", surface="api", is_initial=True),
        "s2": State(id="s2", name="locked", surface="api"),
    }, transitions={})
    model.reindex()
    findings = check_observability(model)
    assert len(findings) == 1 and findings[0].severity == BLOCKING
    assert findings[0].element_ids == ("s1", "s2")


def test_a4_the_same_name_on_different_surfaces_is_fine():
    """A screen is not a status code; M-3 is per-surface."""
    model = Model(id="t", states={
        "ui": State(id="ui", name="Locked", surface="ui", is_initial=True),
        "api": State(id="api", name="Locked", surface="api"),
    }, transitions={})
    model.reindex()
    assert check_observability(model) == []


def test_a_placeholder_name_never_persists():
    model = Model(id="t", states={
        "s1": State(id="s1", name="  ", surface="api", is_initial=True),
    }, transitions={})
    model.reindex()
    findings = check_observability(model)
    assert findings[0].severity == BLOCKING and "no name" in findings[0].detail


# --------------------------------------------------------------------------
# AC coverage is advisory — and why
# --------------------------------------------------------------------------

def test_ac_coverage_is_advisory_because_it_depends_on_a_later_stage():
    """Blocking here would make stage 3 depend on stage 4's output and deadlock."""
    model = login_model()
    findings = check_ac_coverage(model, validated_transition_ids=set())
    assert len(findings) == 16
    assert all(f.severity == ADVISORY for f in findings)
    assert validate(model, include_ac_coverage=True).is_valid()


def test_confirmed_matches_clear_the_ac_finding():
    model = login_model()
    findings = check_ac_coverage(model, validated_transition_ids={"t01", "t02"})
    assert len(findings) == 14


# --------------------------------------------------------------------------
# M-18 : the gate
# --------------------------------------------------------------------------

def test_m18_require_valid_blocks_and_shows_the_findings():
    model = _model(
        [("A", True), ("B", False)],
        [("t1", "A", "go", "B", "x >= 3"), ("t2", "A", "go", "B", "x >= 5")],
    )
    try:
        require_valid(model)
    except ValidationFailed as e:
        text = str(e)
        assert "generation blocked (M-18)" in text
        assert "t1" in text and "t2" in text, "a reviewer cannot act on a count"
        return
    raise AssertionError("a non-deterministic model must not generate")


def test_m18_the_real_model_passes_the_gate():
    assert require_valid(login_model()).is_valid()


def test_the_unverifiable_override_is_offered_but_not_taken_silently():
    model = _model(
        [("A", True), ("B", False)],
        [("t1", "A", "go", "B", "opaque one"), ("t2", "A", "go", "B", "opaque two")],
    )
    try:
        require_valid(model)
    except ValidationFailed as e:
        assert "--allow-unverifiable" in str(e)
        assert "recorded, not silent" in str(e)
    else:
        raise AssertionError("fail-closed by default")
    assert require_valid(model, allow_unverifiable=True) is not None


def test_findings_are_deterministic_across_runs():
    """P-7's discipline applied to validation: two runs must be comparable."""
    model = _model(
        [("A", True), ("B", False), ("Orphan", False)],
        [("t1", "A", "go", "B", "x >= 3"), ("t2", "A", "go", "B", "x >= 5")],
    )
    first = [f.describe() for f in validate(model).findings]
    second = [f.describe() for f in validate(model).findings]
    assert first == second and first


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
