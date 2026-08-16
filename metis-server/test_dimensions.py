"""
Guard dimension and precedence tests (application spec §2.4a, §5.4a, §6.2;
GD-1..GD-9, A-44..A-51).

Free to run: everything here is pure.
"""
import sys

from metis_mcp.mbt.dimensions import (
    AUTHENTICATION,
    AUTHORIZATION,
    BUSINESS,
    PRECEDENCE_UNRESOLVED,
    VALIDATION,
    Chain,
    Dimension,
    EquivalenceClass,
    build_chain,
    class_credit,
    classify,
    cost,
    equivalence_classes,
    format_dimensions,
    prefix_guard,
    success_guard,
    variation_scope,
)


class _Check:
    """Shaped like `code_analysis.contract.CheckFact`."""

    def __init__(self, id, expression, order, dimension_class=None, anchor=""):
        self.id, self.expression, self.order = id, expression, order
        self.dimension_class, self.anchor = dimension_class, anchor


def _chain():
    """The spec's own worked example (GD-3)."""
    return build_chain("POST /commit", [
        _Check("c1", "isAuthenticated()", 1, anchor="SecurityConfig.java:44@a3f21c"),
        _Check("c2", "hasRole('WRITER')", 2, anchor="CommitController.java:31@a3f21c"),
        _Check("c3", "payload.isValid()", 3, anchor="CommitController.java:58@a3f21c"),
    ])


# --------------------------------------------------------------------------
# X-10b / X-10c : classification is configuration, and absence is not a guess
# --------------------------------------------------------------------------

def test_checks_are_classified_from_declared_vocabulary():
    assert classify("isAuthenticated()") == AUTHENTICATION
    assert classify("hasRole('WRITER')") == AUTHORIZATION
    assert classify("payload.isValid()") == VALIDATION


def test_an_unrecognised_check_is_unclassified_not_guessed():
    assert classify("account.balance > threshold") is None


def test_x10c_an_unclassified_check_still_holds_its_position():
    """GD-3's scope rule works on order alone, so an unclassified check still
    participates in the chain — it merely cannot be marked cross-cutting."""
    chain = build_chain("GET /x", [
        _Check("c1", "isAuthenticated()", 1),
        _Check("c2", "account.balance > threshold", 2),
    ])
    assert chain.is_resolved
    second = chain.ordered()[1]
    assert second.dimension_class is None
    assert not second.is_cross_cutting
    assert chain.index_of("c2") == 1


def test_an_explicit_class_from_configuration_wins_over_matching():
    chain = build_chain("GET /x", [_Check("c1", "opaque()", 1, dimension_class=BUSINESS)])
    assert chain.ordered()[0].dimension_class == BUSINESS


# --------------------------------------------------------------------------
# A-44 : a rejection's guard is prefix-determined
# --------------------------------------------------------------------------

def test_a44_earlier_dimensions_pass_and_its_own_fails():
    chain = _chain()
    assert prefix_guard(chain, "c1") == "NOT (isAuthenticated())"
    assert prefix_guard(chain, "c2") == "isAuthenticated() AND NOT (hasRole('WRITER'))"
    assert prefix_guard(chain, "c3") == (
        "isAuthenticated() AND hasRole('WRITER') AND NOT (payload.isValid())")


def test_a44_downstream_dimensions_appear_nowhere_in_the_guard():
    """Naming them would imply a constraint the code never evaluates (GD-3)."""
    guard = prefix_guard(_chain(), "c1")
    assert "hasRole" not in guard and "payload" not in guard


def test_the_success_path_requires_every_dimension():
    assert success_guard(_chain()) == (
        "isAuthenticated() AND hasRole('WRITER') AND payload.isValid()")


# --------------------------------------------------------------------------
# A-45 : guard coverage varies only the failing dimension
# --------------------------------------------------------------------------

def test_a45_only_the_failing_dimension_is_varied():
    scope = variation_scope(_chain(), "c2")
    assert scope.held_pass == ("c1",)
    assert scope.varied == "c2"
    assert scope.not_varied == ("c3",)
    assert scope.is_bounded


def test_a45_the_first_dimension_holds_nothing_and_skips_everything_after():
    scope = variation_scope(_chain(), "c1")
    assert scope.held_pass == ()
    assert scope.not_varied == ("c2", "c3")


def test_a45_the_last_dimension_holds_all_and_skips_nothing():
    scope = variation_scope(_chain(), "c3")
    assert scope.held_pass == ("c1", "c2")
    assert scope.not_varied == ()


# --------------------------------------------------------------------------
# A-46 : the worked example, computed rather than asserted
# --------------------------------------------------------------------------

def test_a46_auth_authz_and_ten_payload_variants_yield_13_not_60():
    """The spec's own worked example: 3 auth x 2 authz x 10 payload.

    Bounded counts failure modes, not variants: (3-1) + (2-1) + (10-1) + 1 = 13.
    """
    c = cost(_chain(), variants={"c1": 3, "c2": 2, "c3": 10})
    assert c.bounded_total == 13, c.per_dimension
    assert c.product_total == 60
    assert c.saved == 47
    assert not c.exploded


def test_bounded_can_never_exceed_the_product():
    """The invariant an earlier formula violated — caught by the report reading
    as nonsense, so it is asserted here directly."""
    for variants in ({"c1": 2, "c2": 2, "c3": 2}, {"c1": 3, "c2": 2, "c3": 10},
                     {"c1": 2, "c2": 2, "c3": 50}, {}):
        c = cost(_chain(), variants=variants)
        assert c.bounded_total <= c.product_total, (variants, c)
        assert c.saved >= 0


def test_a_two_way_dimension_is_the_floor_not_a_one_way_one():
    """A dimension with no failure mode is not a dimension: it never branches."""
    c = cost(_chain(), variants={"c1": 1, "c2": 1, "c3": 1})
    assert all(n == 2 for n in c.per_dimension.values())
    assert c.bounded_total == 4, "one failure each, plus the success path"
    assert c.product_total == 8


# --------------------------------------------------------------------------
# A-47 : determinism comes free from precedence
# --------------------------------------------------------------------------

def test_a47_precedence_ordered_guards_are_mutually_exclusive_structurally():
    """Each rejection's guard asserts the negation of a check every later guard
    asserts positively, so no two can hold at once — by construction, not luck."""
    chain = _chain()
    from metis_mcp.mbt.validation import check_determinism
    from metis_mcp.mbt.model import Model, State, Transition

    transitions = {}
    for i, (dim, target) in enumerate(
            [("c1", "Unauthorized401"), ("c2", "Forbidden403"), ("c3", "BadRequest400")]):
        transitions[f"t{i}"] = Transition(
            id=f"t{i}", source="Ready", trigger="POST /commit", target=target,
            guard=prefix_guard(chain, dim))
    transitions["t3"] = Transition(id="t3", source="Ready", trigger="POST /commit",
                                   target="Created201", guard=success_guard(chain))

    model = Model(
        id="m",
        states={s: State(id=s, name=s, surface="api", is_initial=(s == "Ready"))
                for s in ("Ready", "Unauthorized401", "Forbidden403",
                          "BadRequest400", "Created201")},
        transitions=transitions)
    model.reindex()

    findings = check_determinism(model)
    # These guards are not simple numeric thresholds, so the interval checker
    # cannot *prove* exclusivity and fails closed (M-17) — reported unverifiable,
    # never asserted as safe. The structural property is what A-47 claims, and it
    # is checked directly here rather than through a checker built for numbers.
    assert all(f.severity == "unverifiable" for f in findings)
    guards = [t.guard for t in transitions.values()]
    assert len(set(guards)) == 4, "each rejection has its own distinct prefix"
    for i, dim in enumerate(("c1", "c2", "c3")):
        expression = chain.ordered()[i].expression
        assert f"NOT ({expression})" in guards[i]
        for later in guards[i + 1:]:
            assert f"NOT ({expression})" not in later, (
                "a later guard asserts this check positively, so the two cannot "
                "both hold — that is the structural exclusivity GD-4 claims")


# --------------------------------------------------------------------------
# A-48 / A-49 : equivalence is anchor-gated
# --------------------------------------------------------------------------

def test_a48_identical_anchors_form_one_class_credited_once():
    entries = [(f"t{i}", AUTHENTICATION, "SecurityConfig.java:44@a3f21c")
               for i in range(25)]
    classes, separate = equivalence_classes(entries)
    assert len(classes) == 1
    assert len(classes[0].transition_ids) == 25
    assert classes[0].credits_once
    assert separate == []

    credited = class_credit(classes, covered={"t0"})
    assert len(credited) == 24
    assert all(v == "t0" for v in credited.values())


def test_a49_a_differing_anchor_is_covered_separately():
    """A per-endpoint deviation in an auth check is where a real vulnerability
    hides, and must never be credited away."""
    entries = [(f"t{i}", AUTHENTICATION, "SecurityConfig.java:44@a3f21c")
               for i in range(24)]
    entries.append(("t-odd", AUTHENTICATION, "LegacyController.java:88@a3f21c"))

    classes, separate = equivalence_classes(entries)
    assert len(classes) == 2
    assert any(t == "t-odd" for t, _ in separate), separate

    credited = class_credit(classes, covered={"t0"})
    assert "t-odd" not in credited, "the odd one out is never credited by a peer"


def test_a49_covering_the_odd_one_does_not_credit_the_main_class():
    entries = [(f"t{i}", AUTHENTICATION, "SecurityConfig.java:44@a3f21c") for i in range(3)]
    entries.append(("t-odd", AUTHENTICATION, "LegacyController.java:88@a3f21c"))
    classes, _ = equivalence_classes(entries)
    credited = class_credit(classes, covered={"t-odd"})
    assert credited == {}


def test_a_non_cross_cutting_class_never_credits_a_peer():
    """GD-8 gates class credit on cross-cutting, not merely on a shared anchor:
    two validation checks at one line are still two behaviours."""
    entries = [("t1", VALIDATION, "X.java:1@c"), ("t2", VALIDATION, "X.java:1@c")]
    classes, separate = equivalence_classes(entries)
    assert classes == []
    assert len(separate) == 2
    assert all("not cross-cutting" in reason for _, reason in separate)


def test_an_unanchored_cross_cutting_transition_is_covered_separately():
    """GD-8 is anchor-gated: without an anchor nothing can be shown identical."""
    classes, separate = equivalence_classes([("t1", AUTHENTICATION, "")])
    assert classes == []
    assert "no code anchor" in separate[0][1]


# --------------------------------------------------------------------------
# A-50 : unresolvable precedence fails closed and reports the explosion
# --------------------------------------------------------------------------

def test_a50_a_shared_order_makes_the_chain_unresolved():
    chain = build_chain("GET /x", [
        _Check("c1", "isAuthenticated()", 1),
        _Check("c2", "hasRole('X')", 1),
    ])
    assert not chain.is_resolved
    assert PRECEDENCE_UNRESOLVED in chain.unresolved_reason


def test_a50_it_is_not_tie_broken_by_id():
    """A tie-break would be the guess GD-9 forbids, dressed as determinism."""
    chain = build_chain("GET /x", [
        _Check("aaa", "isAuthenticated()", 1),
        _Check("zzz", "hasRole('X')", 1),
    ])
    assert not chain.is_resolved


def test_a50_the_bound_does_not_apply_and_the_product_is_reported():
    chain = build_chain("GET /x", [
        _Check("c1", "isAuthenticated()", 1),
        _Check("c2", "hasRole('X')", 1),
        _Check("c3", "payload.isValid()", 1),
    ])
    c = cost(chain, variants={"c1": 3, "c2": 2, "c3": 10})
    assert c.exploded
    assert c.bounded_total == c.product_total == 60
    assert "reported, not generated" in c.reason
    assert "60 cases" in c.reason


def test_a50_variation_scope_reports_rather_than_bounding():
    chain = build_chain("GET /x", [
        _Check("c1", "isAuthenticated()", 1), _Check("c2", "hasRole('X')", 1)])
    scope = variation_scope(chain, "c1")
    assert not scope.is_bounded
    assert PRECEDENCE_UNRESOLVED in scope.reason


# --------------------------------------------------------------------------
# A-51 : order is a code fact, never source line position
# --------------------------------------------------------------------------

def test_a51_order_comes_from_the_recovered_field_not_the_input_sequence():
    """A filter declared last in a file may run first in the chain."""
    chain = build_chain("GET /x", [
        _Check("in_body", "payload.isValid()", 3, anchor="C.java:12@c"),
        _Check("filter", "isAuthenticated()", 1, anchor="SecurityConfig.java:200@c"),
        _Check("annotation", "hasRole('X')", 2, anchor="C.java:8@c"),
    ])
    assert [d.id for d in chain.ordered()] == ["filter", "annotation", "in_body"]


def test_a51_a_later_source_line_can_be_an_earlier_dimension():
    chain = build_chain("GET /x", [
        _Check("early_line", "payload.isValid()", 2, anchor="C.java:10@c"),
        _Check("late_line", "isAuthenticated()", 1, anchor="C.java:999@c"),
    ])
    assert chain.ordered()[0].id == "late_line"
    assert prefix_guard(chain, "early_line").startswith("isAuthenticated()")


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def test_the_report_names_the_saving_and_the_rule_behind_it():
    text = format_dimensions(_chain(), variants={"c1": 3, "c2": 2, "c3": 10})
    assert "bounded:  13" in text
    assert "product:  60" in text
    assert "cross-cutting" in text
    assert "assert nothing observable" in text


def test_the_report_states_an_explosion_rather_than_hiding_it():
    chain = build_chain("GET /x", [
        _Check("c1", "isAuthenticated()", 1), _Check("c2", "hasRole('X')", 1)])
    text = format_dimensions(chain, variants={"c1": 3, "c2": 10})
    assert PRECEDENCE_UNRESOLVED in text
    assert "EXPLOSION REPORTED" in text


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
