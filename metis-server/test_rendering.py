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
    format_case,
    humanise,
    render,
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


def test_a42_what_was_not_recovered_is_not_invented():
    """T-9d, checked against prose now that the payload is gone.

    The payload marked an unrecovered method as `__unrecoverable__`; prose has no
    sentinel and does not need one — it renders what the model holds and stays
    silent about the rest. The guarantee is the same and the failure would be the
    same: an HTTP verb or path appearing in a case built from a model that holds
    neither.
    """
    import re

    _, _, rendered = _rendered()
    text = "\n".join(format_case(c) for c in rendered.cases)

    assert not re.search(r"\b(GET|POST|PUT|DELETE|PATCH) /", text), (
        "the login fixture declares no HTTP surface; a verb and path in its "
        "rendered case would have been invented")
    assert ":line" not in text and "@commit" not in text, (
        "no fabricated evidence anchor")


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
    assert "Then LoggedOut" in text
    assert "Given " in text
    # t15 needs the whole failure chain. Five setup steps, each an And-clause,
    # plus the And that names the state they establish.
    clauses = [ln.strip() for ln in text.splitlines()
               if ln.strip().startswith(("Given ", "And "))]
    assert len(clauses) == 6, f"expected 5 setup steps + the state, got {clauses}"


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


def test_a_case_reports_the_method_and_path_it_actually_holds():
    """The mirror of A-42: omitting a fact we DO hold says the wrong thing too.

    Without this, "never invent" is satisfiable by rendering nothing.
    """
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
            id="t", source="Ready", trigger="GET /thing/{id}", target="Ok200",
            lifecycle_state=APPROVED, outcome_status=200,
            guard_anchor="Thing.java:12@abc")},
    )
    case = render(model, generate(model, "all-transitions", 5).paths).cases[0]
    text = format_case(case)
    assert "GET /thing/{id}" in text
    assert "200" in text


# --------------------------------------------------------------------------
# A rendered case reads as Given / When / Then
# --------------------------------------------------------------------------

def _case_named(model, fragment):
    from metis_mcp.mbt import ALL_TRANSITIONS, generate
    from metis_mcp.rendering import render
    rendered = render(model, generate(model, ALL_TRANSITIONS).paths)
    for case in rendered.cases:
        if fragment in case.name:
            return case
    raise AssertionError(f"no case named like {fragment!r}")


def test_a_case_with_no_setup_reads_as_given_when_then():
    """**The model has been Given/When/Then all along; the artefact was not.**

    SP-3 says so of the specification, `precondition_of` produces the Given
    clause, and `behavior_model` calls the source state "the implicit Given" --
    but the thing a QA engineer actually executes said Precondition / Step /
    Expected result. One vocabulary from the spec through to the case.
    """
    from metis_mcp.rendering import format_case

    text = format_case(_case_named(login_model(approved=True), "LoggedOut → LoggedIn"))

    assert "Given the system is in LoggedOut" in text
    assert "When Submit valid credentials" in text
    assert "Then LoggedIn" in text
    assert "Precondition:" not in text
    assert "Expected result:" not in text
    assert "  Step:" not in text


def test_setup_steps_are_and_clauses_before_the_state_they_establish():
    """Order carries the meaning: the steps come first, then the state they
    leave the system in, which is what the `When` acts from. Naming the state
    before the steps that produce it would read backwards."""
    from metis_mcp.rendering import format_case

    text = format_case(_case_named(login_model(approved=True), "Failed1 → Failed2"))
    # Clause lines only: the Objective sentence repeats the Given wording, and
    # matching it would test the prose rather than the structure.
    lines = [ln.strip() for ln in text.splitlines()
             if ln.strip().startswith(("Given ", "And ", "When ", "Then "))]

    given = next(i for i, ln in enumerate(lines) if ln.startswith("Given "))
    state = next(i for i, ln in enumerate(lines) if "the system is in Failed1" in ln)
    when = next(i for i, ln in enumerate(lines) if ln.startswith("When "))

    assert lines[given].startswith("Given Submit invalid credentials"), (
        f"the first Given must be the setup step, got {lines[given]!r}")
    assert lines[state].startswith("And "), (
        "the established state is an And-clause, not a second Given")
    assert given < state < when, (
        f"expected setup → state → When, got {lines[given:when + 1]}")


def test_a_guard_stays_attached_to_the_clause_it_constrains():
    """A guard is a condition on one step. Aggregated into the data
    requirements it loses which step needs it, so it is shown in both places
    -- that split is T-8/T-9 and predates this change."""
    from metis_mcp.rendering import format_case

    text = format_case(_case_named(login_model(approved=True), "LoggedOut → LoggedIn"))
    assert "credentials_valid AND NOT account_locked" in text


# --------------------------------------------------------------------------
# Gherkin: the feature file, and the line Métis does not cross
# --------------------------------------------------------------------------

def test_a_feature_file_carries_one_scenario_per_case():
    from metis_mcp.rendering import feature_for

    model = login_model(approved=True)
    from metis_mcp.mbt import ALL_TRANSITIONS, generate
    from metis_mcp.rendering import render
    rendered = render(model, generate(model, ALL_TRANSITIONS).paths)

    text = feature_for(model, rendered.cases, criterion=ALL_TRANSITIONS)

    assert text.startswith("@") or text.startswith("Feature:")
    assert f"Feature: {model.id}" in text
    assert text.count("Scenario: ") == len(rendered.cases)
    assert text.endswith("\n")


def test_a_scenario_is_given_when_then_with_setup_as_and_clauses():
    from metis_mcp.mbt import ALL_TRANSITIONS, generate
    from metis_mcp.rendering import feature_for, render

    model = login_model(approved=True)
    rendered = render(model, generate(model, ALL_TRANSITIONS).paths)
    case = next(c for c in rendered.cases if "Failed1 → Failed2" in c.name)

    block = _scenario_block(feature_for(model, [case], criterion=ALL_TRANSITIONS),
                            case.name)
    keywords = [ln.split()[0] for ln in block if ln and not ln.startswith("#")]

    assert keywords[0] == "Scenario:"
    assert keywords[1] == "Given"
    assert "And" in keywords[2:], "a setup step must become an And-clause"
    assert keywords.index("When") > keywords.index("Given")
    assert keywords[-1] == "Then" or "Then" in keywords


def test_a_guard_is_a_comment_not_a_step():
    """T-5: a recovered condition is evidence. Rendered as a step, a reader
    would hand it to a framework as something to *perform*, and no step
    definition exists for `NOT credentials_valid`."""
    from metis_mcp.mbt import ALL_TRANSITIONS, generate
    from metis_mcp.rendering import feature_for, render

    model = login_model(approved=True)
    rendered = render(model, generate(model, ALL_TRANSITIONS).paths)
    text = feature_for(model, rendered.cases, criterion=ALL_TRANSITIONS)

    for line in text.splitlines():
        stripped = line.strip()
        if "credentials_valid" in stripped and not stripped.startswith("#"):
            # It may legitimately appear inside a step's prose description;
            # what must never happen is a bare guard expression as a step.
            assert not stripped.startswith(("Given NOT ", "And NOT ",
                                            "When NOT ", "Then NOT ")), (
                f"a guard expression became an executable step: {stripped!r}")


def test_the_feature_says_the_step_code_is_not_metis_s_job():
    """The boundary is stated in the artefact, not only in our documentation:
    somebody opening this file in a Cucumber project has to know Métis wrote
    the specification and not the glue."""
    from metis_mcp.mbt import ALL_TRANSITIONS, generate
    from metis_mcp.rendering import feature_for, render

    model = login_model(approved=True)
    rendered = render(model, generate(model, ALL_TRANSITIONS).paths)
    text = feature_for(model, rendered.cases, criterion=ALL_TRANSITIONS).lower()

    assert "step definition" in text
    assert "framework" in text


def test_the_feature_file_is_byte_identical_across_runs():
    """TR-6/P-7, the same guarantee `render_feature` carries."""
    from metis_mcp.mbt import ALL_TRANSITIONS, generate
    from metis_mcp.rendering import feature_for, render

    model = login_model(approved=True)
    first = feature_for(model, render(model, generate(model, ALL_TRANSITIONS).paths).cases,
                        criterion=ALL_TRANSITIONS)
    second = feature_for(model, render(model, generate(model, ALL_TRANSITIONS).paths).cases,
                         criterion=ALL_TRANSITIONS)
    assert first == second


def test_no_cases_is_said_rather_than_left_as_an_empty_file():
    from metis_mcp.rendering import feature_for

    text = feature_for(login_model(approved=True), [], criterion="all-transitions")
    assert "no scenarios" in text.lower()


def _scenario_block(text: str, name: str) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines()]
    start = next(i for i, ln in enumerate(lines) if ln.startswith(f"Scenario: {name}"))
    block = []
    for ln in lines[start:]:
        if block and ln.startswith(("Scenario:", "@", "Feature:")):
            break
        if ln:
            block.append(ln)
    return block


def test_a_rendered_feature_is_not_readable_as_stated_intent():
    """**The boundary that justified a separate emitter.**

    `feature read` turns a `.feature` into acceptance criteria — somebody's
    *stated* requirement. These scenarios are *recovered* paths, and filing
    them as intent would let the model corroborate itself: extraction proposes
    a behaviour, it is read back as a requirement, and the two then agree
    because they came from the same place.

    The parser also cannot represent these faithfully — it keeps one `given`
    and one `and` per scenario, so a five-step setup would lose four of them.
    A refusal is the honest outcome, and it is checked here rather than left to
    the absence of a tag nobody wrote on purpose.
    """
    from metis_mcp.mbt import ALL_TRANSITIONS, generate
    from metis_mcp.rendering import feature_for, render
    from metis_mcp.specgen.gherkin import parse_feature

    model = login_model(approved=True)
    rendered = render(model, generate(model, ALL_TRANSITIONS).paths)
    text = feature_for(model, rendered.cases, criterion=ALL_TRANSITIONS)

    parsed = parse_feature(text)
    assert parsed.problems, (
        "a rendered feature must not read cleanly as stated intent")
    assert any(p.kind == "no_feature" for p in parsed.problems)
