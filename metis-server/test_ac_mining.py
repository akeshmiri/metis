"""
AC-mined model source tests (application spec §4.5; S-3, S-12, S-13, S-14).

Free to run: mining is deterministic and makes no model call.
"""
import json
import sys
import tempfile
from pathlib import Path

from metis_mcp.mbt.model import QUARANTINE
from metis_mcp.mbt.validation import REACHABILITY, validate
from metis_mcp.model_sources import get as get_source
from metis_mcp.model_sources.ac_mining import (
    BLOCKED_INCOMPLETE,
    BLOCKED_UNGROUNDED,
    BLOCKED_UNPARSEABLE,
    Criterion,
    format_mining,
    mine,
    slug,
)

GWT = [
    Criterion("AC-1", "Given the user is Logged Out, when they submit valid "
                      "credentials and the account is not locked, then they are Logged In."),
    Criterion("AC-2", "Given the user is Logged Out, when they submit invalid "
                      "credentials, then they are Login Failed."),
    Criterion("AC-3", "Given the user is Login Failed, when they submit valid "
                      "credentials, then they are Logged In."),
]


# --------------------------------------------------------------------------
# S-12 : deterministic, staged extraction
# --------------------------------------------------------------------------

def test_a_given_when_then_criterion_becomes_a_transition():
    result = mine(GWT, model_id="login-ac")
    assert result.ok
    t = result.model.transitions["ac::LoggedOut::SubmitValidCredentials::LoggedIn"]
    assert t.source == "LoggedOut"
    assert t.trigger == "submit valid credentials"
    assert t.target == "LoggedIn"
    assert t.guard == "the account is not locked"


def test_states_are_shared_across_criteria():
    """Two criteria naming one situation describe one state, not two."""
    result = mine(GWT, model_id="login-ac")
    assert set(result.model.states) == {"LoggedOut", "LoggedIn", "LoginFailed"}
    assert len(result.model.transitions) == 3


def test_an_ears_state_plus_event_criterion_is_recognised():
    criteria = [Criterion(
        "AC-9", "While Account Locked, when an administrator unlocks the account, "
                "the system shall return them to Logged Out.")]
    result = mine(criteria, model_id="login-ac")
    assert result.ok
    t = next(iter(result.model.transitions.values()))
    assert t.source == "AccountLocked"
    assert t.target == "ReturnThemToLoggedOut" or "LoggedOut" in t.target


def test_mining_is_deterministic():
    a = mine(GWT, model_id="login-ac")
    b = mine(GWT, model_id="login-ac")
    assert sorted(a.model.transitions) == sorted(b.model.transitions)
    assert [e.element_id for e in a.elements] == [e.element_id for e in b.elements]


def test_slug_only_recases_and_never_paraphrases():
    assert slug("Logged Out") == "LoggedOut"
    assert slug("logged out") == "LoggedOut", "one situation, not two states"
    assert slug("") == "Unnamed"


def test_the_display_name_keeps_the_criterions_own_words():
    result = mine(GWT, model_id="login-ac")
    assert result.model.states["LoggedOut"].name == "Logged Out"


# --------------------------------------------------------------------------
# S-4 : everything lands at Quarantine
# --------------------------------------------------------------------------

def test_s4_every_mined_element_lands_at_quarantine():
    result = mine(GWT, model_id="login-ac")
    assert all(s.lifecycle_state == QUARANTINE for s in result.model.states.values())
    assert all(t.lifecycle_state == QUARANTINE for t in result.model.transitions.values())


# --------------------------------------------------------------------------
# S-13 : ungrounded proposals are blocked, not written
# --------------------------------------------------------------------------

def test_s13_free_prose_is_blocked_rather_than_guessed_at():
    criteria = [Criterion("AC-7", "The login page should be nice and fast.")]
    result = mine(criteria, model_id="x")
    assert not result.ok
    assert result.blocked[0].reason == BLOCKED_UNPARSEABLE


def test_s13_an_ears_response_without_a_situation_is_blocked_with_the_reason():
    """"The system shall log the user in." states a response but not the
    situation it applies from — a transition needs both."""
    criteria = [Criterion("AC-8", "The system shall lock the account.")]
    result = mine(criteria, model_id="x")
    blocked = result.blocked[0]
    assert blocked.reason == BLOCKED_UNPARSEABLE
    assert "Ubiquitous" in blocked.detail
    assert "needs both" in blocked.detail


def test_s13_nothing_is_written_when_nothing_can_be_mined():
    result = mine([Criterion("AC-7", "It should be fast.")], model_id="x")
    assert result.model is None
    assert any(b.reason == BLOCKED_INCOMPLETE for b in result.blocked)


def test_s13_one_bad_criterion_does_not_cost_the_whole_model():
    criteria = GWT + [Criterion("AC-7", "It should be fast.")]
    result = mine(criteria, model_id="login-ac")
    assert result.ok and len(result.model.transitions) == 3
    assert len(result.blocked) == 1


def test_s13_the_blocked_list_rides_out_with_the_result():
    source = get_source("ac-mined")
    produced = source.produce(criteria=GWT + [Criterion("AC-7", "It should be fast.")],
                              model_id="login-ac")
    assert len(produced.skipped) == 1
    assert produced.skipped[0][0] == "AC-7"
    assert BLOCKED_UNPARSEABLE in produced.skipped[0][1]


# --------------------------------------------------------------------------
# S-14 : the exact criterion and text span are recorded
# --------------------------------------------------------------------------

def test_s14_every_element_records_its_criterion_and_span():
    result = mine(GWT, model_id="login-ac")
    spans = result.spans_for("LoggedOut")
    assert spans, "the state must be grounded"
    span = spans[0]
    assert span.criterion_id == "AC-1"
    assert GWT[0].text[span.start:span.end].lower() == "logged out"


def test_s14_a_transitions_span_locates_its_trigger():
    result = mine(GWT, model_id="login-ac")
    element = next(e for e in result.elements
                   if e.kind == "transition" and e.span.criterion_id == "AC-2")
    assert element.span.text.lower() == "submit invalid credentials"


def test_s14_the_span_is_a_literal_offset_not_a_restatement():
    result = mine(GWT, model_id="login-ac")
    for element in result.elements:
        original = next(c.text for c in GWT if c.id == element.span.criterion_id)
        assert original[element.span.start:element.span.end] == element.span.text


# --------------------------------------------------------------------------
# §4.5's honest limitation, asserted rather than only documented
# --------------------------------------------------------------------------

def test_an_ac_mined_model_is_partial_and_says_so():
    result = mine(GWT, model_id="login-ac")
    assert any("typically partial" in n for n in result.notes)
    assert "typically PARTIAL" in format_mining(result)


def test_no_initial_state_is_elected_and_validation_correctly_objects():
    """Electing one would invent a precondition nobody can establish (P-8)."""
    result = mine(GWT, model_id="login-ac")
    assert result.model.initial_state_ids() == []
    findings = validate(result.model).blocking
    assert any(f.check == REACHABILITY and "no initial state" in f.detail
               for f in findings)


def test_a_named_initial_state_is_honoured():
    result = mine(GWT, model_id="login-ac", initial_state="LoggedOut")
    assert result.model.initial_state_ids() == ["LoggedOut"]
    assert not any("no initial state named" in n for n in result.notes)


# --------------------------------------------------------------------------
# S-3 : the source is genuinely available, and costs nothing
# --------------------------------------------------------------------------

def test_s3_the_ac_mined_source_is_available_without_a_model_call():
    source = get_source("ac-mined")
    assert source.available
    assert source.why_unavailable() == ""


def test_the_source_reads_criteria_from_a_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "acs.json"
        path.write_text(json.dumps([{"id": c.id, "text": c.text} for c in GWT]))
        produced = get_source("ac-mined").produce(path=path, model_id="login-ac")
    assert len(produced.model.transitions) == 3
    assert produced.extraction_method == "ac_mined"
    assert produced.evidence["criteria"] == 3
    assert produced.evidence["grounded_spans"] > 0


def test_producing_nothing_raises_rather_than_returning_an_empty_model():
    try:
        get_source("ac-mined").produce(criteria=[Criterion("AC-7", "It should be fast.")],
                                       model_id="x")
    except ValueError as e:
        assert "nothing is written" in str(e)
        return
    raise AssertionError("an empty model is not a model (S-17)")


# --------------------------------------------------------------------------
# The comparison this source exists to enable (§4.4, S-5)
# --------------------------------------------------------------------------

def test_an_ac_mined_model_can_be_compared_with_a_code_model_by_natural_key():
    """S-5's "sources agree on an element" is defined by I-2's natural key, so a
    mined transition and a code-derived one must be comparable despite differing
    ids."""
    from metis_mcp.identity import transition_key

    mined = mine(GWT, model_id="login-ac").model
    mined_transition = mined.transitions["ac::LoggedOut::SubmitValidCredentials::LoggedIn"]
    key = transition_key("login-ac", mined_transition, mined)
    assert "LoggedOut" in key and "LoggedIn" in key
    assert "ac::" not in key, "identity is over meaning, not over the id a source minted"


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
