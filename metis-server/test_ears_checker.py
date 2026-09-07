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


# --------------------------------------------------------------------------
# The MCP tool over the same function.
#
# The check was pure, tested and load-bearing — it decides whether intake writes
# a `Requirement` or a `Finding` — and reachable from nowhere a caller could
# stand. So `knowledge-capture`, whose whole job is turning prose into criteria,
# judged conformance by eye and discovered the answer at landing time.
# --------------------------------------------------------------------------

def test_the_tool_reports_what_free_prose_would_land_as():
    """The fact a caller actually needs, and the most surprising thing intake does.

    Most Jira titles look like this. S-13: they become a `Finding` pointing at
    knowledge-capture, never a `Requirement`, because `ears_pattern` has no empty
    form and guessing one is what `ac_mining` refuses to do.
    """
    import json

    from metis_mcp import server

    payload = json.loads(server.check_ears("Fix the broken export button"))
    assert payload["conforms"] is False
    assert payload["would_land_as"] == "Finding"
    assert payload["why"], "a refusal that says nothing cannot be acted on"


def test_the_tool_reports_a_conformant_sentence_as_a_requirement():
    import json

    from metis_mcp import server

    payload = json.loads(server.check_ears(
        "When a code expires, the RECORDS service shall reject the attempt."))
    assert payload["conforms"] is True
    assert payload["would_land_as"] == "Requirement"
    assert payload["pattern"] == "EventDriven"
    assert payload["parts"], "the clauses are what a caller builds from"


def test_conforms_survives_pruning_when_it_is_false():
    """`_prune` deletes False. Without `conforms` in `_ALWAYS_KEPT` the answer
    would vanish exactly when it is 'no' — the one case worth asking about."""
    import json

    from metis_mcp import server

    payload = json.loads(server.check_ears("not a requirement"))
    assert "conforms" in payload, "the field disappeared when it mattered"
    assert payload["conforms"] is False


def test_the_tool_does_not_claim_to_judge_substantive_quality():
    """§2.6 draws the line; conflating the two is what `ac_quality` is for."""
    import json

    from metis_mcp import server

    # Structurally perfect EARS, and unmeasurable.
    payload = json.loads(server.check_ears(
        "The system shall respond appropriately."))
    assert payload["conforms"] is True
    assert "not_checked" in payload
    assert "ac_quality" in payload["not_checked"]


# ---------------------------------------------------------------------------
# Terminal punctuation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "When a record has been archived, the system shall reject an update with 409",
    "While an import is running, the system shall reject a second import",
    "If the payload exceeds 1 MB, then the system shall respond with 413",
    "Where premium billing is enabled, the system shall apply the discount",
    "The system shall retain audit records for seven years",
])
def test_a_requirement_without_a_full_stop_is_still_conformant(text):
    """**The measurement that forced this.**

    Every pattern required `\\.$`, transcribed from a v1 document that no longer
    exists. Six well-formed EARS requirements scored **0/6** against it, because
    a Jira summary does not end with a full stop — and each was reported as "not
    EARS-conformant", which is the most misleading possible way to be right.

    On a real backlog that is the difference between most stated requirements
    arriving as a `Requirement` and almost none of them doing so.
    """
    assert check_ears_conformance(text).conformant, text


@pytest.mark.parametrize("text", [
    "When a record has been archived, the system shall reject an update with 409.",
    "The system shall retain audit records for seven years.",
])
def test_a_requirement_written_properly_is_unaffected(text):
    assert check_ears_conformance(text).conformant, text


def test_the_punctuation_is_the_only_thing_that_became_optional():
    """Structure still gates. A sentence missing the comma, the `shall`, or the
    response is not a requirement however it is punctuated."""
    for text in ("When something happens the system shall respond",   # no comma
                 "When something happens, the system responds",       # no shall
                 "The system shall",                                  # no response
                 "Archive is broken again"):                          # prose
        assert not check_ears_conformance(text).conformant, text


def test_the_clauses_are_identical_with_and_without_the_stop():
    """A lazy quantifier before an optional terminator can silently truncate the
    last word of the response — which would be invisible in a true/false check
    and wrong in every criterion built from the groups."""
    without = check_ears_conformance(
        "When a record has been archived, the system shall reject an update with 409")
    with_stop = check_ears_conformance(
        "When a record has been archived, the system shall reject an update with 409.")
    assert without.groups == with_stop.groups
    assert without.groups["response"] == "reject an update with 409"
