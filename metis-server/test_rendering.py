"""
Rendering and coverage-ledger tests (application spec §7, §6.8).

Uses the same real login-model fixture as test_mbt.py. Free to run: no Neo4j,
no model calls, no config.
"""
import json
import sys

from metis_mcp.mbt import ALL_TRANSITIONS, GUARD_COVERAGE, generate
from metis_mcp.mbt.coverage import (
    DIRECT,
    INDIRECT,
    build_ledger,
    credit_indirect,
    format_report,
)
from metis_mcp.rendering import (
    TIER_ACCEPTANCE_CRITERION,
    TIER_GENERATED_PROSE,
    UNRECOVERABLE,
    build_payload,
    format_case,
    humanise,
    render,
    unrecoverable_fields,
)
from mbt_fixtures import login_model


def _rendered(criterion=ALL_TRANSITIONS):
    model = login_model()
    result = generate(model, criterion)
    return model, result, render(model, result.paths)


# --------------------------------------------------------------------------
# A-37 : a test case asserts exactly one expected result
# --------------------------------------------------------------------------

def test_a37_exactly_one_assertion_per_case():
    _, _, rendered = _rendered()
    assert rendered.cases, "expected rendered cases"
    for case in rendered.cases:
        assert case.assertion_count == 1, (
            f"{case.id} has {case.assertion_count} assertions, must have exactly 1"
        )


def test_a37_setup_steps_carry_no_assertions():
    """Spec T-1a: a failure during setup is *blocked*, not failed."""
    _, _, rendered = _rendered()
    for case in rendered.cases:
        for step in case.precondition_steps:
            assert not step.is_assertion, f"{case.id}: setup step {step.transition_id} asserts"
            assert step.expected_result == "", (
                f"{case.id}: setup step has an expected result, implying an assertion"
            )


# --------------------------------------------------------------------------
# T-2 / T-3 : every step maps to a real transition; expected to a real state
# --------------------------------------------------------------------------

def test_t2_every_step_maps_to_a_real_transition():
    model, _, rendered = _rendered()
    for case in rendered.cases:
        for step in (*case.precondition_steps, case.act_step):
            assert step.transition_id in model.transitions, (
                f"{case.id}: step references unknown transition {step.transition_id}"
            )


def test_t3_expected_result_is_a_real_state():
    model, _, rendered = _rendered()
    names = {s.name for s in model.states.values()}
    for case in rendered.cases:
        assert case.act_step.expected_result in names, (
            f"{case.id}: expected result {case.act_step.expected_result!r} is not a state"
        )


# --------------------------------------------------------------------------
# T-5 : the verbatim guard is always attached, whatever produced the wording
# --------------------------------------------------------------------------

def test_t5_verbatim_guard_attached_regardless_of_wording_tier():
    model, _, rendered = _rendered()
    for case in rendered.cases:
        transition = model.transitions[case.act_step.transition_id]
        assert case.act_step.guard_verbatim == transition.guard, (
            f"{case.id}: guard not carried verbatim"
        )


def test_t4_acceptance_criterion_wording_takes_precedence():
    model = login_model()
    result = generate(model, ALL_TRANSITIONS)
    wording = {"t01": "Sign in with a valid account"}
    rendered = render(model, result.paths, ac_wording=wording)
    case = next(c for c in rendered.cases if c.act_step.transition_id == "t01")
    assert case.act_step.description == "Sign in with a valid account"
    assert case.act_step.wording_tier == TIER_ACCEPTANCE_CRITERION
    # ...and the verbatim guard survives the substitution (T-5).
    assert case.act_step.guard_verbatim == model.transitions["t01"].guard


def test_t4_falls_back_to_generated_prose_without_acceptance_criteria():
    _, _, rendered = _rendered()
    case = next(c for c in rendered.cases if c.act_step.transition_id == "t02")
    assert case.act_step.wording_tier == TIER_GENERATED_PROSE
    assert case.act_step.description == "Submit invalid credentials"


def test_t6_humanise_does_not_paraphrase():
    """Only re-spacing and capitalisation, so no behaviour can be introduced."""
    assert humanise("submit_invalid_credentials") == "Submit invalid credentials"
    assert humanise("admin_unlock_or_lockout_elapsed") == "Admin unlock or lockout elapsed"
    assert humanise("") == ""


# --------------------------------------------------------------------------
# T-8 / T-9 : guards appear as aggregated data requirements, not values
# --------------------------------------------------------------------------

def test_t9_data_requirements_grouped_by_condition_not_repeated_per_step():
    """t06's setup (t02..t05) and its own guard all require the same condition.

    That is one thing to satisfy, not five -- but which steps need it is retained,
    because dropping that loses where a failure would surface.
    """
    _, _, rendered = _rendered()
    case = next(c for c in rendered.cases if c.act_step.transition_id == "t06")
    assert len(case.data_requirements) == 1, (
        f"identical conditions must group, got {case.data_requirements}"
    )
    requirement = case.data_requirements[0]
    assert requirement.condition == "NOT credentials_valid"
    # Setup steps 1-4, plus 0 meaning the step under test.
    assert requirement.steps == (1, 2, 3, 4, 0)
    assert "setup steps 1, 2, 3, 4" in requirement.where
    assert "the step under test" in requirement.where


def test_t9_distinct_conditions_stay_distinct():
    _, _, rendered = _rendered()
    case = next(c for c in rendered.cases if c.act_step.transition_id == "t15")
    conditions = [r.condition for r in case.data_requirements]
    assert conditions == ["NOT credentials_valid", "admin_unlocked OR lockout_elapsed"], (
        f"grouping must not merge different conditions, got {conditions}"
    )
    assert case.data_requirements[-1].steps == (0,)
    assert case.data_requirements[-1].where == "the step under test"


# --------------------------------------------------------------------------
# T-10 : identity is content-derived from the path, criterion is metadata
# --------------------------------------------------------------------------

def test_t10_case_id_is_stable_across_runs():
    a = _rendered()[2].by_target()
    b = _rendered()[2].by_target()
    assert {k: v.id for k, v in a.items()} == {k: v.id for k, v in b.items()}


def test_t10_same_walk_under_two_criteria_yields_the_same_case_id():
    """The criterion is metadata, not identity."""
    model = login_model()
    by_transition = {}
    for criterion in (ALL_TRANSITIONS, GUARD_COVERAGE):
        result = generate(model, criterion)
        for case in render(model, result.paths).cases:
            key = (case.act_step.transition_id, case.precondition_group)
            by_transition.setdefault(key, set()).add(case.id)
    collisions = {k: v for k, v in by_transition.items() if len(v) > 1}
    assert not collisions, f"same walk produced differing ids: {collisions}"


# --------------------------------------------------------------------------
# A-38 : shared preconditions survive into rendering
# --------------------------------------------------------------------------

def test_a38_precondition_group_carried_into_cases():
    _, _, rendered = _rendered()
    from_initial = [c for c in rendered.cases if c.precondition_group == ()]
    assert len(from_initial) == 3, (
        f"three transitions leave the initial state, got {len(from_initial)}"
    )
    for case in from_initial:
        assert case.precondition_steps == (), "no-setup group must render no precondition steps"


# --------------------------------------------------------------------------
# A-41 / A-42 : the automation payload restates model facts; unknowns are marked
# --------------------------------------------------------------------------

def test_a41_payload_restates_only_model_facts():
    model, _, rendered = _rendered()
    case = next(c for c in rendered.cases if c.act_step.transition_id == "t06")
    payload = build_payload(model, case)
    assert payload["act"]["transition_id"] == "t06"
    assert payload["act"]["guard"] == model.transitions["t06"].guard
    assert payload["act"]["from_state"] == "Failed4"
    assert payload["act"]["to_state"] == "AccountLocked"
    assert [s["transition_id"] for s in payload["setup"]] == ["t02", "t03", "t04", "t05"]
    assert payload["act"]["is_assertion"] is True
    assert all(s["is_assertion"] is False for s in payload["setup"])


def test_a42_unrecoverable_details_are_marked_not_guessed():
    model, _, rendered = _rendered()
    payload = build_payload(model, rendered.cases[0])
    marked = unrecoverable_fields(payload)
    assert marked, "payload must mark what it cannot recover"
    # Specifically: no fabricated HTTP method, path or anchor.
    assert any("method" in f for f in marked)
    assert any("path" in f for f in marked)
    assert any("anchor" in f for f in marked)
    assert payload["act"]["act"]["method"] == UNRECOVERABLE


def test_payload_is_json_serialisable():
    model, _, rendered = _rendered()
    blob = json.dumps([build_payload(model, c) for c in rendered.cases])
    assert len(blob) > 0


# --------------------------------------------------------------------------
# Coverage ledger (§6.8b)
# --------------------------------------------------------------------------

def test_ledger_records_direct_coverage_with_test_case_ids():
    model, result, rendered = _rendered()
    ids = {c.target_key: c.id for c in rendered.cases}
    ledger = build_ledger(model, result, ids)
    assert len(ledger.rows) == 16, f"expected 16 direct rows, got {len(ledger.rows)}"
    assert all(r.mechanism == DIRECT for r in ledger.rows)
    assert all(r.test_case_id for r in ledger.rows), "every row should name its case"


def test_ledger_reports_excluded_planned_transition():
    model, result, _ = _rendered()
    ledger = build_ledger(model, result)
    assert any(tid == "t17" for tid, _ in ledger.uncovered), (
        "the planned transition must appear as uncovered with its reason"
    )


def test_c2_indirect_credit_never_applies_to_guard_coverage():
    """Spec C-2: a UI path cannot exercise combinations the UI cannot submit."""
    model, result, _ = _rendered(GUARD_COVERAGE)
    ledger = build_ledger(model, result)
    credited = credit_indirect(ledger, model, {"ui-x": "t13"}, covered_elsewhere={"ui-x"})
    assert credited == [], "guard coverage must never receive indirect credit"
    assert INDIRECT not in {r.mechanism for r in ledger.rows}


def test_c8_indirect_only_transitions_reported_separately():
    model = login_model()
    # Drop t13 from direct coverage so it can only be credited indirectly.
    result = generate(model, ALL_TRANSITIONS)
    result.paths = [p for p in result.paths if p.validated_transition_id != "t13"]
    ledger = build_ledger(model, result)
    credited = credit_indirect(ledger, model, {"ui-timeout": "t13"},
                               covered_elsewhere={"ui-timeout"})
    assert credited == ["t13"]
    assert ledger.indirect_only() == ["t13"], (
        "a transition covered only indirectly must be reported as such"
    )


def test_report_always_states_its_criterion_and_the_tested_not_working_caveat():
    model, result, _ = _rendered()
    text = format_report(build_ledger(model, result))
    assert "criterion:      all-transitions" in text
    assert "TESTED" in text and "WORKING" in text, (
        "spec C-11: the report must not imply coverage means working"
    )


# --------------------------------------------------------------------------
# End-to-end shape
# --------------------------------------------------------------------------

def test_end_to_end_model_to_formatted_case():
    model, result, rendered = _rendered()
    case = next(c for c in rendered.cases if c.act_step.transition_id == "t15")
    text = format_case(case)
    assert "AccountLocked → LoggedOut" in text
    assert "Expected result: LoggedOut" in text
    assert "Precondition:" in text
    # t15 needs the whole failure chain; five setup steps must be listed.
    assert all(f"{n}." in text for n in range(1, 6))


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
