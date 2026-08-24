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
    ComponentRef,
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
from metis_mcp.rendering.test_case import render_path
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


def test_t10_the_criterion_is_metadata_not_identity():
    """T-10's actual claim: two criteria selecting the same walk **with the same
    data** yield one case.

    It is asserted per-criterion-pair rather than globally because of T-10a. When
    this was written no criterion varied data, so "same walk" and "same case"
    coincided. Boundary analysis and pairwise both produce several cases over ONE
    walk — `attempts = 4`, `= 5`, `= 6` — and under the global form all five
    boundary cases hashed to a single id, so publishing them wrote one and
    silently discarded four. The technique appeared to run and produced one test.
    """
    model = login_model()
    by_walk: dict[tuple, set[str]] = {}
    for criterion in ("all-states", "all-transitions"):
        for path in generate(model, criterion, 10).paths:
            key = (path.validated_transition_id, tuple(path.setup_transition_ids),
                   path.data_note or "")
            by_walk.setdefault(key, set()).add(render_path(model, path).id)

    clashes = {k: v for k, v in by_walk.items() if len(v) > 1}
    assert not clashes, f"same walk and data produced differing ids: {clashes}"


def test_t10a_a_data_varying_technique_gets_one_id_per_case():
    """The case T-10 did not anticipate, and the reason it needed T-10a.

    Five boundary cases over one transition are five tests. Sharing an id makes
    four of them unpublishable and untrackable — `TestCase` merges on it.
    """
    model = login_model()
    paths = [p for p in generate(model, "boundary-coverage", 10).paths]
    over_one_walk: dict[tuple, list] = {}
    for path in paths:
        over_one_walk.setdefault(
            (path.validated_transition_id, tuple(path.setup_transition_ids)), []).append(path)

    varied = max(over_one_walk.values(), key=len)
    assert len(varied) > 1, "no walk carried several boundary cases to check"
    ids = {render_path(model, p).id for p in varied}
    assert len(ids) == len(varied), (
        f"{len(varied)} cases over one walk share {len(ids)} id(s) — "
        f"publishing would write one and discard the rest")


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
# P-16 -- the version a coverage figure is about
# --------------------------------------------------------------------------

_COMPONENT = ComponentRef(id="cmp-abc", component="login-api",
                          version="3", commit_sha="a3f21c9")


def test_p16_report_states_the_version_and_commit_it_refers_to():
    model, result, _ = _rendered()
    text = format_report(build_ledger(model, result, component=_COMPONENT))
    assert "login-api v3 @ a3f21c9" in text, (
        "spec P-16: a coverage report states the model version and commit"
    )


def test_p16_a_ledger_with_no_component_says_so_rather_than_omitting_it():
    """The failure this replaces: a figure that quietly named no version at all.

    Printing the number and staying silent about the missing version reads as
    though the omission were not there. Naming it is the whole point.
    """
    model, result, _ = _rendered()
    text = format_report(build_ledger(model, result))
    assert "not recorded for this run (P-16)" in text
    summary = build_ledger(model, result).summary()
    assert summary["version"] is None and summary["commit"] is None


def test_summary_carries_component_version_and_commit():
    model, result, _ = _rendered()
    summary = build_ledger(model, result, component=_COMPONENT).summary()
    assert summary["component"] == "login-api"
    assert summary["version"] == "3"
    assert summary["commit"] == "a3f21c9"


# --------------------------------------------------------------------------
# Criterion coverage, without any execution result (C-10)
# --------------------------------------------------------------------------

def test_criteria_coverage_counts_acs_on_covered_transitions():
    model, result, rendered = _rendered()
    ids = {c.target_key: c.id for c in rendered.cases}
    ledger = build_ledger(model, result, ids,
                          validating_criteria={"t01": ["AC-001", "AC-002"],
                                               "t02": ["AC-003"]})
    assert ledger.criteria_covered() == ["AC-001", "AC-002", "AC-003"]
    assert ledger.criteria_uncovered() == []
    row = next(r for r in ledger.rows if r.transition_id == "t01")
    assert row.criterion_ids == ("AC-001", "AC-002")


def test_an_ac_on_an_uncovered_transition_counts_against_the_figure():
    """The denominator must not shrink to what was covered.

    `t17` is `planned` and therefore excluded from generation (P-11). An AC
    validating it is real and uncovered; deriving the criteria denominator from
    the ledger's rows would drop it, and the figure would rise by ignoring what
    it missed.
    """
    model, result, _ = _rendered()
    ledger = build_ledger(model, result,
                          validating_criteria={"t01": ["AC-001"], "t17": ["AC-099"]})
    assert ledger.criteria_covered() == ["AC-001"]
    assert ledger.criteria_uncovered() == ["AC-099"]
    assert ledger.summary()["criteria_uncovered"] == 1


def test_the_report_never_mentions_execution_results():
    """C-10/C-11: the ledger records coverage, not outcome."""
    model, result, _ = _rendered()
    text = format_report(build_ledger(model, result, component=_COMPONENT,
                                      validating_criteria={"t01": ["AC-001"]}))
    lowered = text.lower()
    for forbidden in ("passed", "failed", "execution", "test run"):
        assert forbidden not in lowered, (
            f"{forbidden!r} implies an outcome; coverage is not an outcome (C-11)"
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


# --------------------------------------------------------------------------
# Request data (spec §7.4, T-9c). Until the pack recovered parameters, a case
# for `POST /metric` printed no data requirements at all -- readable, unrunnable.
# --------------------------------------------------------------------------

def test_an_input_is_rendered_as_a_condition_never_a_value():
    """M-9: Métis states what the data must satisfy; it does not invent data."""
    from metis_mcp.rendering.test_case import input_condition

    text = input_condition({"name": "metricDto", "location": "body",
                            "type_name": "org.example.records.dto.RecordDto",
                            "required": True, "constraints": []})
    assert text == "body.metricDto is a required RecordDto"
    # Nothing that looks like a value.
    assert "=" not in text and "{" not in text


def test_an_optional_input_says_so():
    from metis_mcp.rendering.test_case import input_condition

    text = input_condition({"name": "page", "location": "query",
                            "type_name": "int", "required": False, "constraints": []})
    assert "optional" in text and "query.page" in text


def test_declared_constraints_are_quoted_not_interpreted():
    from metis_mcp.rendering.test_case import input_condition

    text = input_condition({"name": "code", "location": "body", "type_name": "String",
                            "required": True, "constraints": ["@Size(max = 15)"]})
    assert "@Size(max = 15)" in text, "carried verbatim (M-8)"


def test_inputs_and_guards_are_reported_separately():
    """"What you must send" and "what must already be true" are prepared
    differently; one undifferentiated list hides that."""
    from metis_mcp.mbt.model import APPROVED, Model, State, Transition
    from metis_mcp.mbt.path_generation import generate
    from metis_mcp.rendering import format_case, render

    model = Model(
        id="p-api",
        states={"Ready": State(id="Ready", name="Ready", surface="api",
                               is_initial=True, lifecycle_state=APPROVED),
                "Ok200": State(id="Ok200", name="Ok200", surface="api",
                               lifecycle_state=APPROVED)},
        transitions={"t": Transition(
            id="t", source="Ready", trigger="POST /thing", target="Ok200",
            guard="caller.isKnown()", lifecycle_state=APPROVED, outcome_status=200,
            inputs=({"name": "body", "location": "body", "type_name": "ThingDto",
                     "required": True, "constraints": []},))},
    )
    text = format_case(render(model, generate(model, "all-transitions", 5).paths).cases[0])
    assert "Request data required:" in text
    assert "body.body is a required ThingDto" in text
    assert "Test data requirements:" in text
    assert "caller.isKnown()" in text


def test_the_payload_reports_method_and_path_it_actually_holds():
    """T-9d marks what is unknown. Marking a field we hold says the wrong thing."""
    from metis_mcp.mbt.model import APPROVED, Model, State, Transition
    from metis_mcp.mbt.path_generation import generate
    from metis_mcp.rendering import build_payload, render
    from metis_mcp.rendering.payload import UNRECOVERABLE

    model = Model(
        id="p-api",
        states={"Ready": State(id="Ready", name="Ready", surface="api",
                               is_initial=True, lifecycle_state=APPROVED),
                "Ok200": State(id="Ok200", name="Ok200", surface="api",
                               lifecycle_state=APPROVED)},
        transitions={"t": Transition(
            id="t", source="Ready", trigger="GET /thing/{id}", target="Ok200",
            lifecycle_state=APPROVED, outcome_status=200,
            guard_anchor="Thing.java:12@abc")},
    )
    case = render(model, generate(model, "all-transitions", 5).paths).cases[0]
    act = build_payload(model, case)["act"]["act"]
    assert act["method"] == "GET" and act["path"] == "/thing/{id}"
    assert act["expected_status"] == 200
    assert build_payload(model, case)["act"]["anchor"] == "Thing.java:12@abc"
    assert UNRECOVERABLE not in (act["method"], act["path"])
