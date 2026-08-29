"""
Authored fixtures, and the join that fills what extraction could not recover.

`rendering/payload.py` marks unknowns rather than inventing them — a UI step
carries `element: UNRECOVERABLE` because `js-ui` refuses to guess a selector, and
`data_requirements` carry a condition, never a value (T-9c, X-6e). That is right
for a model recovered from code and insufficient to drive a browser. Fixtures are
the authored half.

**The rule these tests exist to hold: nothing is guessed.** A field with no
fixture stays unrecovered and is reported. The failure being prevented is
automation that looks correct and binds to the wrong element.

Free to run: loading and resolving are pure.
"""
from __future__ import annotations

import pytest

from metis_mcp.rendering.fixtures import (
    EMPTY, FIXTURES_VERSION, Fixtures, FixturesInvalid, load, load_file)
from metis_mcp.rendering.payload import UNRECOVERABLE, resolve_payload


def _ui_payload():
    return {"act": {"kind": "ui_action", "action": "click",
                    "element": UNRECOVERABLE, "element_hint": "exportButton"},
            "data_requirements": [
                {"condition": "title length 3..40", "steps": [0], "kind": "input"}]}


# ---------------------------------------------------------------------------
# Loading: refused, never degraded
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad,because", [
    ({"version": "metis.fixtures/9"}, "a version from another format"),
    ({"selectors": {"a": ""}}, "an empty selector binds to nothing"),
    ({"typo": 1}, "a misspelled key would be silently ignored"),
    ({"values": {"a": {"b": 1}}}, "nesting is structure this format lacks"),
    ({"selectors": {"": "x"}}, "an entry with no name"),
    ({"selectors": []}, "not a mapping"),
])
def test_a_malformed_file_is_refused_with_a_reason(bad, because):
    with pytest.raises(FixturesInvalid):
        load(bad)


def test_a_missing_file_is_an_error_not_an_empty_set():
    """`--fixtures typo.yaml` meaning 'no fixtures' is how a typo becomes a
    script full of TODOs that reads as a modelling gap."""
    with pytest.raises(FixturesInvalid):
        load_file("/nonexistent/fixtures.yaml")


def test_an_absent_optional_section_is_fine():
    assert load({"selectors": {"a": "#a"}}).values == {}
    assert load({}).is_empty


def test_the_default_version_is_the_current_one():
    assert load({}).version == FIXTURES_VERSION


# ---------------------------------------------------------------------------
# Resolving: fills what was authored, guesses nothing
# ---------------------------------------------------------------------------

def test_a_selector_is_filled_from_the_element_hint():
    fixtures = load({"selectors": {"exportButton": "[data-testid=export]"}})
    out = resolve_payload(_ui_payload(), fixtures)
    assert out["resolved"]["act"]["element"] == "[data-testid=export]"
    assert out["supplied"]["act.element"] == "selectors.exportButton"


def test_a_value_is_filled_from_the_condition_the_payload_states():
    fixtures = load({"values": {"title length 3..40": "Quarterly report"}})
    out = resolve_payload(_ui_payload(), fixtures)
    assert out["resolved"]["data_requirements"][0]["value"] == "Quarterly report"


def test_a_field_with_no_fixture_stays_unrecovered():
    """The whole point. Not a plausible default, not the element hint as if it
    were a selector — the marker stays and the field is reported."""
    out = resolve_payload(_ui_payload(), load({"selectors": {"other": "#o"}}))
    assert out["resolved"]["act"]["element"] == UNRECOVERABLE
    assert "act.element" in out["unresolved"]


def test_with_no_fixtures_at_all_nothing_changes():
    out = resolve_payload(_ui_payload(), EMPTY)
    assert out["resolved"]["act"]["element"] == UNRECOVERABLE
    assert out["supplied"] == {}


def test_a_fixture_that_matched_nothing_is_reported():
    """A rename or a typo is invisible unless something says so — the same
    'report which side missed' rule `mbt.link_proposals` follows."""
    fixtures = load({"selectors": {"renamedAway": "#gone"}})
    assert resolve_payload(_ui_payload(), fixtures)["unused"] == ["renamedAway"]


def test_the_original_payload_is_not_mutated():
    """The unresolved payload is the honest record of what the CODE says; a
    reader must be able to tell it from a value somebody chose."""
    original = _ui_payload()
    resolve_payload(original, load({"selectors": {"exportButton": "#e"}}))
    assert original["act"]["element"] == UNRECOVERABLE


def test_supplied_names_the_fixture_key_so_a_reviewer_can_trace_it():
    fixtures = load({"selectors": {"exportButton": "#e"},
                     "values": {"title length 3..40": "Q"}})
    supplied = resolve_payload(_ui_payload(), fixtures)["supplied"]
    assert set(supplied) == {"act.element", "data_requirements.title length 3..40"}
    assert all(v.split(".")[0] in {"selectors", "values"} for v in supplied.values())


def test_a_selector_is_never_read_from_the_values_map():
    """Two maps, not one: a generator that confused them would put a CSS
    selector into a request body."""
    fixtures = Fixtures(values={"exportButton": "[data-testid=export]"})
    out = resolve_payload(_ui_payload(), fixtures)
    assert out["resolved"]["act"]["element"] == UNRECOVERABLE
