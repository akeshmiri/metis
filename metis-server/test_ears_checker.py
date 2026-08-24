"""
EARS conformance (spec §4.3, §9's code-vs-LLM allocation, S-13).

**Three modules import this and nothing tested it.** `ac_mining`,
`knowledge` and `intake_landing` all gate on it: a Requirement is created only
from EARS-conformant text, and free prose lands as a `Finding` pointing at
knowledge-capture instead. So this function decides whether a sentence becomes a
requirement or a note — and it did so untested.

Deterministic regex on purpose. §9 lists the EARS check as code rather than
judgement, and S-13's refusal to guess an `ears_pattern` depends on the check
being reproducible rather than a model's opinion.

Free to run: pure.
"""
import pytest

from metis_mcp.ears_checker import _PATTERNS, check_ears_conformance

CONFORMANT = [
    ("Ubiquitous", "The system shall log every request."),
    ("EventDriven", "When a code expires, the RECORDS service shall reject the attempt."),
    ("StateDriven", "While a session is locked, the system shall refuse authentication."),
    ("UnwantedBehavior", "If a provider is unavailable, then the system shall fall back to SMS."),
    ("Optional", "Where RECORDS is enabled, the system shall require a challenge."),
]


@pytest.mark.parametrize("pattern,text", CONFORMANT)
def test_each_of_the_five_patterns_is_recognised(pattern, text):
    result = check_ears_conformance(text)
    assert result.conformant, result.reason
    assert result.pattern == pattern


def test_the_five_are_all_of_them():
    """§4.3 names five. A sixth appearing here without the spec moving is drift."""
    assert [name for name, _ in _PATTERNS] == [
        "EventDriven", "StateDriven", "UnwantedBehavior", "Optional", "Ubiquitous"]


def test_ubiquitous_is_checked_last_and_the_order_is_load_bearing():
    """Its shape is a strict subset of the other four's tail clause.

    Checked first, every Event/State/Unwanted/Optional sentence would match it
    and be misclassified — the requirement would exist but with the wrong
    pattern, which is worse than being refused.
    """
    assert [n for n, _ in _PATTERNS][-1] == "Ubiquitous"
    event = check_ears_conformance(
        "When a code expires, the RECORDS service shall reject the attempt.")
    assert event.pattern == "EventDriven", "not Ubiquitous, despite containing one"


@pytest.mark.parametrize("text", [
    "we should probably validate the input",
    "RECORDS is important to the business",
    "",
    "   ",
    "The system logs every request.",          # no `shall`
])
def test_prose_is_refused_with_a_reason(text):
    """S-13: `ears_pattern` has no empty form, so free prose must fail here
    rather than be guessed into a shape. This is the gate that sends most Jira
    titles to a Finding instead of a Requirement."""
    result = check_ears_conformance(text)
    assert not result.conformant
    assert result.pattern is None
    assert result.reason, "a refusal that says nothing cannot be acted on"


def test_the_matched_clauses_come_back():
    """The groups are what a caller uses to build the criterion; a bare
    true/false would make the check unusable for anything but filtering."""
    result = check_ears_conformance(
        "When a code expires, the RECORDS service shall reject the attempt.")
    assert result.groups
    assert any("code expires" in str(v) for v in result.groups.values())


def test_surrounding_whitespace_does_not_change_the_answer():
    assert check_ears_conformance(
        "\n  The system shall log every request.  \n").conformant
