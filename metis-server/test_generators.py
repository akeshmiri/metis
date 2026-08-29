"""
Automation emitters (`rendering/generators`).

**The rule every test here defends: an emitter may not invent a value.** A field
the payload still marks `__unrecoverable__` must reach the output as a visible
TODO, never as a plausible locator or a default status code. Filling one in
would move the fabrication one layer further from where anybody looks for it —
into a generated file that reads like working test code.

The second rule is X-4, borrowed from extraction: a runner Métis has not been
verified against is REFUSED, not approximated.

Free to run: emitters are pure string rendering over a dict.
"""
from __future__ import annotations

import re

import pytest

from metis_mcp.rendering.generators import (
    DECLARED, KNOWN_UNSUPPORTED, TargetUnsupported, describe, emit, emit_files,
    get, select_for, surface_of)
from metis_mcp.rendering.payload import UNRECOVERABLE

UI_CASE = {
    "resolved": {
        "case_id": "tc-1", "model_id": "records-ui", "criterion": "all-transitions",
        "setup": [], "data_requirements": [],
        "act": {"transition_id": "t1", "surface": "ui", "is_assertion": True,
                "guard": "record is not locked",
                "act": {"kind": "ui_action", "action": "click",
                        "element": "[data-testid=export]",
                        "element_hint": "exportButton",
                        "expected_condition": "the export starts"},
                "assert": {"expected_state": "Exported",
                           "observable": UNRECOVERABLE}},
    },
    "unresolved": ["act.assert.observable"], "supplied": {}, "unused": [],
}

API_CASE = {
    "resolved": {
        "case_id": "tc-2", "model_id": "records-api", "criterion": "all-transitions",
        "setup": [], "data_requirements": [],
        "act": {"transition_id": "t2", "surface": "api", "is_assertion": True,
                "guard": "", "assert": {},
                "act": {"kind": "api_call", "method": "GET", "path": "/record/{id}",
                        "expected_status": 200, "security": [], "inputs": []}},
    },
    "unresolved": [], "supplied": {}, "unused": [],
}


# ---------------------------------------------------------------------------
# X-4: declared, or refused
# ---------------------------------------------------------------------------

def test_a_declared_target_resolves():
    assert get("playwright").language == "typescript"
    assert get("rest-assured").surface == "api"


@pytest.mark.parametrize("target", sorted(KNOWN_UNSUPPORTED))
def test_a_real_but_unverified_runner_is_refused_by_name(target):
    """Refused, and the refusal says what WOULD be accepted — a bare
    'unsupported' sends the reader to the source to find out."""
    with pytest.raises(TargetUnsupported) as e:
        get(target)
    assert "Declared:" in str(e.value)


def test_an_unknown_target_is_refused_too():
    with pytest.raises(TargetUnsupported):
        get("nonsense")


def test_the_declared_set_is_not_silently_empty():
    assert DECLARED and {g.surface for g in DECLARED} == {"api", "ui"}


def test_describe_names_both_what_works_and_what_does_not():
    text = describe()
    assert "playwright" in text and "selenium" in text and "X-4" in text


# ---------------------------------------------------------------------------
# The rule: nothing invented
# ---------------------------------------------------------------------------

def test_a_resolved_selector_is_emitted_as_a_real_locator():
    out = emit("playwright", UI_CASE)
    assert "page.click('[data-testid=export]')" in out


def test_an_unresolved_selector_becomes_a_TODO_carrying_its_hint():
    case = {**UI_CASE, "resolved": {**UI_CASE["resolved"]}}
    case["resolved"]["act"] = {**UI_CASE["resolved"]["act"],
                               "act": {**UI_CASE["resolved"]["act"]["act"],
                                       "element": UNRECOVERABLE}}
    out = emit("playwright", case)
    assert "TODO" in out and "exportButton" in out
    assert "page.click('__unrecoverable__')" not in out, "emitted the marker as a locator"


def test_a_missing_status_is_not_asserted_as_200():
    """The failure this prevents: a generated test that passes for the wrong
    reason because the emitter supplied a default nobody recovered."""
    case = {**API_CASE, "resolved": {**API_CASE["resolved"]}}
    case["resolved"]["act"] = {**API_CASE["resolved"]["act"],
                               "act": {**API_CASE["resolved"]["act"]["act"],
                                       "expected_status": None}}
    out = emit("rest-assured", case)
    assert "statusCode" not in out
    assert "TODO" in out


def test_a_recovered_status_IS_asserted():
    assert ".statusCode(200)" in emit("rest-assured", API_CASE)


def test_an_unrecoverable_request_does_not_emit_a_call():
    case = {**API_CASE, "resolved": {**API_CASE["resolved"]}}
    case["resolved"]["act"] = {**API_CASE["resolved"]["act"],
                               "act": {"kind": "api_call", "method": UNRECOVERABLE,
                                       "path": UNRECOVERABLE,
                                       "derived_from_trigger": "submit_credentials"}}
    out = emit("rest-assured", case)
    assert "given()" not in out and "submit_credentials" in out


def test_a_guard_is_a_comment_not_an_assertion():
    """T-9c: the condition is a precondition on the WORLD, which the runner
    cannot assert — emitting it as one would fail for the wrong reason."""
    out = emit("playwright", UI_CASE)
    assert "// precondition: record is not locked" in out


def test_the_marker_never_reaches_the_output_as_a_value():
    """Belt and braces across both emitters: whatever else happens, the literal
    sentinel must not appear inside a call."""
    for target, case in (("playwright", UI_CASE), ("rest-assured", API_CASE)):
        out = emit(target, case)
        for line in out.splitlines():
            if UNRECOVERABLE in line:
                assert line.strip().startswith("//"), f"{target}: {line}"


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------

def test_output_says_it_is_generated_and_names_the_model():
    out = emit("playwright", UI_CASE)
    assert "GENERATED by" in out and "records-ui" in out


def test_java_identifiers_are_legal():
    """A case id is a hash with hyphens; a Java method name may not be."""
    out = emit("rest-assured", API_CASE)
    assert "public void tc_2()" in out


def test_strings_are_escaped_for_their_language():
    case = {**UI_CASE, "resolved": {**UI_CASE["resolved"]}}
    case["resolved"]["act"] = {**UI_CASE["resolved"]["act"],
                               "act": {**UI_CASE["resolved"]["act"]["act"],
                                       "element": "[data-id='it\\'s']"}}
    out = emit("playwright", case)
    assert "\\'" in out


# ---------------------------------------------------------------------------
# The artefact has to be well-formed for its language
# ---------------------------------------------------------------------------
#
# Every test above checks that nothing is INVENTED, and all of them passed while
# `metis generate --target rest-assured` wrote sixteen files that `javac`
# rejects on their first line: each was named `tc-<hash>.java` and each declared
# `public class LoginApiTest`. An artefact that reads like working test code and
# cannot compile is the same failure as a fabricated value, one layer down — so
# the shape of the output is asserted here, not just its content.

def _case(case_id: str, model_id: str = "records-api", **act) -> dict:
    detail = {"kind": "api_call", "method": "GET", "path": "/record/{id}",
              "expected_status": 200}
    detail.update(act)
    return {"resolved": {"case_id": case_id, "model_id": model_id,
                         "criterion": "all-transitions", "setup": [],
                         "act": {"surface": "api", "guard": "", "act": detail}},
            "unresolved": [], "supplied": {}, "unused": []}


def test_a_java_file_is_named_after_the_class_it_declares():
    """javac: `class X is public, should be declared in a file named X.java`.

    This is not a style point — it is the compiler's rule, and breaking it makes
    every generated file unusable while the suite stays green.
    """
    files = emit_files("rest-assured", [_case("tc-1"), _case("tc-2")])
    for filename, text in files.items():
        declared = re.findall(r"^public class (\w+)", text, re.M)
        assert declared == [filename[:-len(".java")]], (filename, declared)


def test_every_case_of_one_model_lands_in_ONE_class():
    """A JUnit `test` is a method; the class is the model. Sixteen classes of
    the same name in one package is the other half of the compile error."""
    files = emit_files("rest-assured", [_case(f"tc-{i}") for i in range(16)])
    assert len(files) == 1, sorted(files)
    assert list(files)[0] == "RecordsApiTest.java"
    assert files["RecordsApiTest.java"].count("@Test") == 16


def test_two_models_get_two_classes():
    files = emit_files("rest-assured",
                       [_case("tc-1", "records-api"), _case("tc-2", "login-api")])
    assert sorted(files) == ["LoginApiTest.java", "RecordsApiTest.java"]


def test_case_ids_that_sanitise_alike_get_distinct_method_names():
    """`tc-1` and `tc_1` are different cases and the same Java identifier.
    Aggregating into one class made that a duplicate-method compile error for
    the first time; separate files had hidden it."""
    text = emit_files("rest-assured", [_case("tc-1"), _case("tc_1")])["RecordsApiTest.java"]
    names = re.findall(r"public void (\w+)\(", text)
    assert len(names) == 2 and len(set(names)) == 2, names


def test_typescript_keeps_a_file_per_case():
    """The default layout, and the right one where a filename is not also a
    declaration — the Java rule must not leak into every target."""
    files = emit_files("playwright", [UI_CASE])
    assert list(files) == ["tc-1.spec.ts"]


# ---------------------------------------------------------------------------
# A target generates for one surface (the `surface` field, finally read)
# ---------------------------------------------------------------------------

def test_surface_is_read_from_the_act_step():
    assert surface_of(UI_CASE) == "ui"
    assert surface_of(API_CASE) == "api"


def test_a_ui_target_takes_no_api_cases():
    """`--target playwright` on an API model emitted a browser test whose every
    step was a TODO. That reads as a modelling gap and is a target mismatch."""
    matching, skipped = select_for(get("playwright"), [API_CASE])
    assert matching == [] and skipped == [API_CASE]


def test_a_mixed_model_is_split_not_refused():
    """A model may legitimately hold both surfaces; each target takes its half."""
    ui, ui_skipped = select_for(get("playwright"), [UI_CASE, API_CASE])
    api, api_skipped = select_for(get("rest-assured"), [UI_CASE, API_CASE])
    assert ui == [UI_CASE] and ui_skipped == [API_CASE]
    assert api == [API_CASE] and api_skipped == [UI_CASE]


# ---------------------------------------------------------------------------
# The value a person authored has to arrive
# ---------------------------------------------------------------------------
#
# `resolve_payload` joins a fixture value onto the requirement whose condition
# it is keyed by and reports it as `supplied`. Both emitters then dropped it:
# `metis generate --fixtures ...` produced output BYTE-IDENTICAL to the run
# without them. Every assertion above still passed, because they all check that
# nothing is invented and nothing was — the value simply never arrived.

def _with_data(*requirements, target_surface: str = "api") -> dict:
    act = ({"kind": "api_call", "method": "GET", "path": "/r", "expected_status": 200}
           if target_surface == "api"
           else {"kind": "ui_action", "action": "click", "element": "#go"})
    return {"resolved": {"case_id": "tc-1", "model_id": "records", "criterion": "c",
                         "setup": [], "data_requirements": list(requirements),
                         "act": {"surface": target_surface, "guard": "",
                                 "is_assertion": False, "act": act}},
            "unresolved": [], "supplied": {}, "unused": []}


SUPPLIED = {"condition": "credentials_valid", "steps": [0], "kind": "guard",
            "value": "alice / correct-horse"}
UNSUPPLIED = {"condition": "title length 3..40", "steps": [0, 1], "kind": "input"}


@pytest.mark.parametrize("target,surface",
                         [("rest-assured", "api"), ("playwright", "ui")])
def test_an_authored_value_reaches_the_artefact(target, surface):
    out = emit(target, _with_data(SUPPLIED, target_surface=surface))
    assert "alice / correct-horse" in out
    assert "authored fixture" in out, "the reader cannot tell it from a recovered fact"


@pytest.mark.parametrize("target,surface",
                         [("rest-assured", "api"), ("playwright", "ui")])
def test_a_condition_with_no_fixture_is_a_TODO_not_a_guess(target, surface):
    out = emit(target, _with_data(UNSUPPLIED, target_surface=surface))
    assert "title length 3..40" in out and "TODO" in out


@pytest.mark.parametrize("target,surface",
                         [("rest-assured", "api"), ("playwright", "ui")])
def test_supplying_a_fixture_CHANGES_the_artefact(target, surface):
    """The regression this section exists for. If these two are equal, the join
    ran, reported success, and produced nothing."""
    without = emit(target, _with_data(UNSUPPLIED, target_surface=surface))
    with_one = emit(target, _with_data({**UNSUPPLIED, "value": "Quarterly report"},
                                       target_surface=surface))
    assert without != with_one
    assert "Quarterly report" in with_one


@pytest.mark.parametrize("target,surface",
                         [("rest-assured", "api"), ("playwright", "ui")])
def test_a_multiline_value_cannot_escape_its_comment(target, surface):
    """A value with a newline in it would put its own tail on a line that is no
    longer a comment — source that looks valid and is not."""
    out = emit(target, _with_data({**UNSUPPLIED, "value": "one\ntwo"},
                                  target_surface=surface))
    for line in out.splitlines():
        if "two" in line:
            assert line.strip().startswith("//"), line


def test_a_case_with_no_data_requirements_emits_no_block():
    """Silence where there is nothing to say — an empty header would be noise
    on every case that states no condition."""
    assert "data requirements" not in emit("rest-assured", _with_data())
