"""
MBT engine tests (application spec §6) -- the acceptance criteria for path
generation, checked against real ground truth.

The fixture is a real recovered login model (`mbt_fixtures.login_model`): 10
states, 17 transitions of which 16 are `implemented` and 1 (2FA enrolment) is
`planned`. Its shape was extracted, not invented, so "covers every implemented
transition" is a checkable claim rather than a self-fulfilling one. It came from
`demo_data/login_example.py`, which went with the v1 engine.

Free to run: no Neo4j, no model calls, no config. That is the point of keeping
the engine database-free (metis_mcp/mbt/model.py).
"""
import sys

from metis_mcp.mbt import (
    ALL_STATES,
    ALL_TRANSITION_PAIRS,
    ALL_TRANSITIONS,
    GUARD_COVERAGE,
    IMPLEMENTED,
    PLANNED,
    Model,
    State,
    Transition,
    generate,
    targets_for,
)
from metis_mcp.mbt.criteria import atomic_conditions
from metis_mcp.mbt.model import APPROVED, QUARANTINE, REJECTED
from metis_mcp.mbt.path_generation import EXCEEDS_SETUP_CAP, UNREACHABLE
from mbt_fixtures import IMPLEMENTED_IDS, login_model

# --------------------------------------------------------------------------
# A-13 : all-transitions covers every implemented transition, planned excluded
# --------------------------------------------------------------------------

def test_a13_all_transitions_covers_every_implemented_transition():
    result = generate(login_model(), ALL_TRANSITIONS)
    assert result.covered_transition_ids == IMPLEMENTED_IDS, (
        f"expected exactly the 16 implemented transitions, "
        f"missing={IMPLEMENTED_IDS - result.covered_transition_ids} "
        f"extra={result.covered_transition_ids - IMPLEMENTED_IDS}"
    )
    assert len(IMPLEMENTED_IDS) == 16, "fixture drift: expected 16 implemented transitions"
    assert not result.uncoverable, f"unexpected uncoverable: {result.uncoverable}"


def test_a13_planned_transition_reported_excluded_not_silently_dropped():
    result = generate(login_model(), ALL_TRANSITIONS)
    assert ("t17", "excluded_planned") in result.excluded, (
        f"planned transition must be reported as excluded, got {result.excluded}"
    )
    assert "t17" not in result.covered_transition_ids


# --------------------------------------------------------------------------
# A-14 : byte-identical output across runs (spec P-7)
# --------------------------------------------------------------------------

def test_a14_generation_is_deterministic():
    a = generate(login_model(), ALL_TRANSITIONS)
    b = generate(login_model(), ALL_TRANSITIONS)
    assert a.paths == b.paths, "path list differs between identical runs"
    # Order matters too, not just membership -- a set-equal but reordered result
    # would still break run-to-run comparison.
    assert [p.target_key for p in a.paths] == [p.target_key for p in b.paths]


def test_a14_deterministic_across_all_criteria():
    for criterion in (ALL_STATES, ALL_TRANSITIONS, ALL_TRANSITION_PAIRS, GUARD_COVERAGE):
        a = generate(login_model(), criterion)
        b = generate(login_model(), criterion)
        assert a.paths == b.paths, f"{criterion} is not deterministic"


# --------------------------------------------------------------------------
# A-15 / A-37 : exactly one validated transition per path; setup not credited
# --------------------------------------------------------------------------

def test_a15_each_path_validates_exactly_one_transition():
    result = generate(login_model(), ALL_TRANSITIONS)
    for p in result.paths:
        assert p.validated_transition_id, "path has no validated transition"
        assert p.validated_transition_id not in p.setup_transition_ids, (
            f"{p.target_key}: validated transition also appears in setup"
        )


def test_a15_setup_transitions_are_not_credited_as_covered():
    """Spec P-5a. The deep-chain transitions t03-t06 appear in many setups; only
    their own paths may credit them."""
    result = generate(login_model(), ALL_TRANSITIONS)
    setup_only = set()
    for p in result.paths:
        setup_only.update(p.setup_transition_ids)
    # Every transition used as setup is also covered in its own right here, but
    # the credit must come from its own path, never from appearing in setup.
    for tid in setup_only:
        own = [p for p in result.paths if p.validated_transition_id == tid]
        assert own, f"{tid} appears only as setup and was never validated"


# --------------------------------------------------------------------------
# A-38 : transitions sharing a source state share a precondition group
# --------------------------------------------------------------------------

def test_a38_shared_source_state_yields_shared_precondition_group():
    """t01, t02 and t11 all leave LoggedOut, the initial state: same (empty)
    setup, therefore one precondition group -- the 'open the login page' case."""
    result = generate(login_model(), ALL_TRANSITIONS)
    by_id = {p.validated_transition_id: p for p in result.paths}
    groups = {by_id[t].precondition_group for t in ("t01", "t02", "t11")}
    assert len(groups) == 1, f"expected one shared precondition group, got {groups}"
    assert groups == {()}, "transitions from the initial state need no setup"


def test_a38_precondition_groups_are_queryable():
    result = generate(login_model(), ALL_TRANSITIONS)
    groups = result.precondition_groups()
    assert () in groups, "the no-setup group must exist"
    assert len(groups[()]) == 3, (
        f"three transitions leave the initial state, got {len(groups[()])}"
    )
    # Failed2 is reached one way; t04 and t08 both leave it and share setup.
    shared = [g for g, paths in groups.items() if len(paths) > 1 and g != ()]
    assert shared, "expected at least one non-trivial shared precondition group"


# --------------------------------------------------------------------------
# A-43 : setup exceeding the cap is reported with its required length
# --------------------------------------------------------------------------

def test_a43_setup_cap_breach_reports_required_length():
    # t06 (Failed4 -> AccountLocked) needs 4 setup steps: t02,t03,t04,t05.
    result = generate(login_model(), ALL_TRANSITIONS, setup_cap=2)
    breaches = [u for u in result.uncoverable if u.reason == EXCEEDS_SETUP_CAP]
    assert breaches, "expected setup-cap breaches at cap=2"
    for u in breaches:
        assert "requires" in u.detail and "cap is 2" in u.detail, (
            f"breach must state the required length, got {u.detail!r}"
        )
    assert any(u.validated_transition_id == "t06" for u in breaches)


def test_a43_default_cap_covers_the_whole_login_model():
    """The measured longest required setup is 5 -- t15 (AccountLocked ->
    LoggedOut) needs the whole failure chain t02..t06 to reach its source state.
    Total path length is therefore 6, which is the figure quoted in spec §11.1;
    the *setup* is one shorter. The default cap of 10 must leave real headroom
    (spec P-8a)."""
    result = generate(login_model(), ALL_TRANSITIONS)
    assert not result.uncoverable, f"default cap should cover everything: {result.uncoverable}"
    by_id = {p.validated_transition_id: p for p in result.paths}
    longest = max(p.setup_length for p in result.paths)
    assert longest == 5, f"expected measured longest setup of 5, got {longest}"
    assert by_id["t15"].setup_length == 5, "t15 should be the longest-setup transition"
    assert by_id["t15"].setup_transition_ids == ("t02", "t03", "t04", "t05", "t06")
    assert longest < 10, "the default cap must leave headroom, not just fit"


# --------------------------------------------------------------------------
# P-6a : shortest setup, not fewest paths
# --------------------------------------------------------------------------

def test_p6a_setup_is_the_shortest_route():
    result = generate(login_model(), ALL_TRANSITIONS)
    by_id = {p.validated_transition_id: p for p in result.paths}
    # Failed4 is reachable only via the failure chain: t02,t03,t04,t05.
    assert by_id["t06"].setup_transition_ids == ("t02", "t03", "t04", "t05")
    # LoggedIn is reachable in one step from the initial state, so t13's setup
    # must take that route rather than a longer one through the failure chain.
    assert by_id["t13"].setup_transition_ids == ("t01",)


def test_p8_paths_start_only_at_an_initial_state():
    model = login_model()
    result = generate(model, ALL_TRANSITIONS)
    initial = set(model.initial_state_ids())
    for p in result.paths:
        first = p.setup_transition_ids[0] if p.setup_transition_ids else p.validated_transition_id
        assert model.transitions[first].source in initial, (
            f"{p.target_key} starts at {model.transitions[first].source}, not an initial state"
        )


# --------------------------------------------------------------------------
# P-1a : deeper criteria add tests, never assertions
# --------------------------------------------------------------------------

def test_p1a_every_criterion_produces_single_assertion_paths():
    for criterion in (ALL_STATES, ALL_TRANSITIONS, ALL_TRANSITION_PAIRS, GUARD_COVERAGE):
        result = generate(login_model(), criterion)
        for p in result.paths:
            assert p.validated_transition_id, f"{criterion}: path without a validation"


def test_p1a_deeper_criteria_produce_more_tests():
    transitions = generate(login_model(), ALL_TRANSITIONS)
    pairs = generate(login_model(), ALL_TRANSITION_PAIRS)
    assert len(pairs.paths) > len(transitions.paths), (
        "transition-pair coverage must produce more tests, not richer ones"
    )


# --------------------------------------------------------------------------
# P-3 : unsatisfiable requirements are reported, never dropped
# --------------------------------------------------------------------------

def test_p3_unsatisfiable_guard_targets_are_reported():
    result = generate(login_model(), GUARD_COVERAGE)
    assert result.uncoverable, (
        "guards with no complementary sibling must be reported unsatisfiable"
    )
    reasons = {u.reason for u in result.uncoverable}
    assert "unsatisfiable" in reasons, f"got reasons {reasons}"


def _terminal_outcomes_model() -> Model:
    """The shape every recovered API model has: a call, and an outcome state
    that nothing leaves.

    `login_model` is not this shape -- its states lead on to one another, which
    is why it never exercised the branch below.
    """
    return Model(
        id="records-api",
        states={
            "Record": State(id="Record", name="Record", is_initial=True,
                            lifecycle_state=APPROVED),
            "Ok200": State(id="Ok200", name="GetRecord200",
                           lifecycle_state=APPROVED),
            "NoContent204": State(id="NoContent204", name="DeleteRecordId204",
                                  lifecycle_state=APPROVED),
        },
        transitions={
            "t1": Transition(id="t1", source="Record", trigger="GET /record",
                             target="Ok200", lifecycle_state=APPROVED),
            "t2": Transition(id="t2", source="Record",
                             trigger="DELETE /record/{id}",
                             target="NoContent204", lifecycle_state=APPROVED),
        },
    )


def test_p3_a_pair_with_no_follower_is_reported_not_silently_dropped():
    """**The silent success this project hunts for.** `_all_transition_pairs`
    `continue`d past a terminal state, producing no target and no reason -- so a
    model whose states are all terminal reported `covered: 0, uncovered: 0`, and
    full coverage of nothing was indistinguishable from no coverage at all. It
    was the only criterion in the module that dropped a target without saying
    why. Measured on the live `records-api`: 13 transitions, 13 silent drops.
    """
    result = generate(_terminal_outcomes_model(), ALL_TRANSITION_PAIRS)

    assert not result.paths, "a terminal-only model has no pair to cover"
    assert len(result.uncoverable) == 2, (
        f"every dropped pair must be reported, got {result.uncoverable}"
    )
    assert {u.target_key for u in result.uncoverable} == {"t1", "t2"}
    for u in result.uncoverable:
        assert "terminal" in u.detail and "no pair to cover" in u.detail, (
            f"the reason must say why, got {u.detail!r}"
        )


def test_guard_splitting_is_minimal_and_does_not_interpret():
    assert atomic_conditions("credentials_valid AND NOT account_locked") == [
        "credentials_valid", "NOT account_locked",
    ]
    # OR is deliberately not decomposed -- its branches are not independently
    # controllable from one transition.
    assert atomic_conditions("admin_unlocked OR lockout_elapsed") == [
        "admin_unlocked OR lockout_elapsed",
    ]
    assert atomic_conditions("") == []


# --------------------------------------------------------------------------
# Model integrity
# --------------------------------------------------------------------------

def test_g1_unapproved_elements_are_reported_not_generated_from():
    """Spec G1 / D-10: generation reads only Approved elements."""
    model = login_model(approved=False)
    assert not model.is_approved
    outstanding = model.unapproved_elements()
    # 10 states + 16 implemented transitions; the planned one is not a gap.
    assert len(outstanding) == 26, f"expected 26 outstanding, got {len(outstanding)}"
    assert all(state == QUARANTINE for _, _, state in outstanding)

    result = generate(model, ALL_TRANSITIONS)
    assert result.paths == [], "an unapproved model must yield no paths"
    reasons = {reason for _, reason in result.excluded}
    assert "excluded_unapproved" in reasons, (
        f"unapproved transitions need their own distinct reason, got {reasons}"
    )


def test_a_rejected_transition_is_a_settled_decision_not_an_open_review():
    """G1 must not describe a *decided* element as awaiting review.

    Rejecting an extraction artefact is the correct action for it, and until
    now it locked the gate permanently: no decision cleared it (approving
    contradicts the review, deferring leaves it), so the only escape was
    re-extraction. Measured on Athena: 75 of 76 elements approved, one
    rejected, and the whole journey blocked.

    `exclusion_reason` already knew this -- it returns `excluded_rejected`
    beside `excluded_planned`. `unapproved_elements` skipped PLANNED and not
    REJECTED, so one file read the same fact two opposite ways.
    """
    model = login_model(approved=True)
    model.transitions["t16"] = Transition(
        id="t16", source="LoggedIn", trigger="click_logout", target="LoggedOut",
        lifecycle_state=REJECTED,
    )

    assert model.unapproved_elements() == [], (
        "a rejected transition is decided; it must not sit in the review queue")
    assert model.is_approved, "one rejection must not block the whole journey"

    # Decided is not the same as generated from: it stays excluded (D-10).
    result = generate(model, ALL_TRANSITIONS)
    assert dict(result.excluded)["t16"] == "excluded_rejected"


def test_a_rejected_state_still_blocks_because_nothing_else_excludes_it():
    """The asymmetry is deliberate, not an oversight in the fix above.

    `exclusion_reason` and `is_generatable` are properties of `Transition`;
    `State` has neither, and `is_generatable` never checks a transition's
    endpoints. So an approved transition into a rejected state would generate
    a path running through it. G1 is the only thing standing there.
    """
    model = login_model(approved=True)
    model.states["LoggedIn"] = State(
        id="LoggedIn", name="LoggedIn", lifecycle_state=REJECTED)

    outstanding = model.unapproved_elements()
    assert outstanding == [("state", "LoggedIn", REJECTED)], (
        f"a rejected state has no exclusion machinery and must keep blocking, "
        f"got {outstanding}")


def test_g1_reasons_are_distinct_not_collapsed():
    """'not reviewed', 'sources disagree' and 'not built' are different facts."""
    model = login_model(approved=True)
    model.transitions["t13"] = Transition(
        id="t13", source="LoggedIn", trigger="session_idle_timeout", target="SessionExpired",
        guard="idle_exceeds_timeout", lifecycle_state="Disputed",
    )
    model.transitions["t16"] = Transition(
        id="t16", source="LoggedIn", trigger="click_logout", target="LoggedOut",
        lifecycle_state=QUARANTINE,
    )
    result = generate(model, ALL_TRANSITIONS)
    by_id = dict(result.excluded)
    assert by_id["t13"] == "excluded_disputed"
    assert by_id["t16"] == "excluded_unapproved"
    assert by_id["t17"] == "excluded_planned"


def test_model_rejects_dangling_transition():
    try:
        Model(
            id="broken",
            states={"A": State(id="A", name="A", is_initial=True)},
            transitions={"x": Transition(id="x", source="A", trigger="go", target="Nowhere")},
        )
    except ValueError as e:
        assert "Nowhere" in str(e)
        return
    raise AssertionError("a transition to an unknown state must be rejected")


def test_unreachable_state_reported_not_silently_skipped():
    model = Model(
        id="island",
        states={
            "A": State(id="A", name="A", is_initial=True, lifecycle_state=APPROVED),
            "B": State(id="B", name="B", lifecycle_state=APPROVED),
            "C": State(id="C", name="C", lifecycle_state=APPROVED),
        },
        transitions={
            "ab": Transition(id="ab", source="A", trigger="go", target="B",
                             lifecycle_state=APPROVED),
            "cc": Transition(id="cc", source="C", trigger="loop", target="C",
                             lifecycle_state=APPROVED),
        },
    )
    result = generate(model, ALL_TRANSITIONS)
    unreachable = [u for u in result.uncoverable if u.reason == UNREACHABLE]
    assert any(u.validated_transition_id == "cc" for u in unreachable), (
        f"transition from an unreachable state must be reported, got {result.uncoverable}"
    )


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


# ---------------------------------------------------------------------------
# `GUARDED_BY` — the checks are read, not merely stored
# ---------------------------------------------------------------------------
#
# The edge was written by landing and read by NOTHING: `guard_expression` had
# six production readers, the `Check` node had zero. What the string cannot
# carry is the evaluation order, and the order is a data requirement — a fixture
# aimed at the third condition never reaches it if the first short-circuits.

def _guarded(checks, guard="a AND b"):
    from metis_mcp.mbt.model import GuardCheck, Model, State, Transition
    return Model(
        id="g-api",
        states={"A": State(id="A", name="A", is_initial=True),
                "B": State(id="B", name="B"), "C": State(id="C", name="C")},
        transitions={
            "ok": Transition(id="ok", source="A", trigger="POST /x", target="B",
                             guard=guard, lifecycle_state=APPROVED,
                             checks=tuple(GuardCheck(*c) for c in checks)),
            "no": Transition(id="no", source="A", trigger="POST /x", target="C",
                             guard=f"NOT ({guard})", lifecycle_state=APPROVED),
        })


def _guard_notes(model):
    from metis_mcp.mbt.criteria import targets_for
    return {t.key: t.data_note
            for t in targets_for(model, "guard-coverage").targets
            if t.key.startswith("ok::")}


def test_a_landed_check_supplies_the_condition_instead_of_the_split_string():
    """One check, one condition — and the guard string is not consulted."""
    notes = _guard_notes(_guarded(
        [("payload is present", 1, "structural", "Ctl.java:38@c0ffee")],
        guard="this AND that AND theother"))
    assert any("payload is present must hold" in n for n in notes.values())
    assert not any("theother" in n for n in notes.values()), (
        "the guard string was split anyway — the checks were ignored")


def test_a_targets_note_carries_the_line_the_condition_came_from():
    """T-9a. A condition a reviewer cannot trace is one they take on trust, and
    the anchor is the single thing a split string can never recover."""
    notes = _guard_notes(_guarded(
        [("accepted", 1, "business", "ScopedController.java:41@c0ffee")]))
    assert any("[ScopedController.java:41@c0ffee]" in n for n in notes.values())


def test_a_later_check_states_what_must_already_hold_to_reach_it():
    """**The fact that only `GUARDED_BY` holds.**

    Checks short-circuit. A fixture built to exercise the third condition never
    reaches it unless the first two are already satisfied, so "vary condition 3"
    is not an executable instruction on its own. Splitting `a AND b AND c` gives
    three conditions and no such statement.
    """
    notes = _guard_notes(_guarded([
        ("present", 1, "structural", ""),
        ("owned", 2, "business", ""),
        ("summarisable", 3, "business", "")]))
    third = [n for k, n in notes.items() if "summarisable" in k]
    assert third, "no target for the third condition"
    assert all("present and owned already hold" in n for n in third)

    first = [n for k, n in notes.items() if k.startswith("ok::present::")]
    assert all("already hold" not in n for n in first), (
        "the first check requires nothing before it")


def test_the_note_states_a_condition_and_never_a_value(_=None):
    """M-9 survives the change: the model says what must be true, never what to
    send. A precedence note that named a value would be solving the guard."""
    notes = _guard_notes(_guarded([("attempts < 3", 1, "business", "")]))
    for note in notes.values():
        assert "=" not in note.replace("<=", "").replace(">=", "").replace("!=", "")


def test_a_transition_with_no_landed_check_is_covered_exactly_as_before():
    """The fallback is most of the estate. `GUARDED_BY` is written only where
    dimension recovery resolved the checks, and mfa has none at all — so a
    regression here would be invisible on the live graph and total."""
    from metis_mcp.mbt.criteria import atomic_conditions, guard_conditions
    from metis_mcp.mbt.model import Transition

    t = Transition(id="t", source="A", trigger="go", target="B",
                   guard="alpha AND beta")
    assert guard_conditions(t) == [(c, "") for c in atomic_conditions(t.guard)]
