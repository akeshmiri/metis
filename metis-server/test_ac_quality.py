"""Whether the acceptance-criterion checker names a real defect, and only real ones.

The rule the whole module has to hold to: it may report a criterion as unclear,
and it may never rewrite one to make it pass (S-13) or block it from landing
(S-4). Both are asserted here rather than left to the docstring.
"""
import json

from metis_mcp import ac_quality, server


def _rules(text: str) -> set:
    return {f.rule for f in ac_quality.assess(text)}


# --------------------------------------------------------------------------
# The port kept Atlas's rules. These are the ones it exists to catch.
# --------------------------------------------------------------------------

def test_a_vague_qualifier_is_named_not_just_reported():
    """"Is ambiguous" is a verdict nobody can act on; the WORD is actionable."""
    findings = ac_quality.assess("The system responds appropriately to a request.")
    vague = [f for f in findings if f.rule == "AC-VAGUE-TERM"]
    assert vague, "'appropriately' is the canonical unmeasurable qualifier"
    assert "appropriately" in vague[0].detail
    assert vague[0].suggestion, "a finding with no suggestion is half a finding"


def test_a_weak_modal_is_a_possibility_not_a_requirement():
    assert "AC-WEAK-MODAL" in _rules("The system should reject an empty name.")


def test_shall_is_not_a_weak_modal():
    """EARS's own required word. Flagging it would fight `check_ears`."""
    assert "AC-WEAK-MODAL" not in _rules(
        "The system shall reject a name longer than 40 characters.")


def test_an_unresolved_placeholder_cannot_be_tested():
    assert "AC-PLACEHOLDER" in _rules("The system rejects a name over TBD chars.")


def test_a_non_observable_predicate_names_no_result():
    assert "AC-NON-OBSERVABLE" in _rules(
        "The archive flag is respected during the nightly batch.")


def test_an_unquantified_change_claim_is_a_warning():
    assert "AC-UNQUANTIFIED-CHANGE" in _rules(
        "The endpoint responds faster after the index is added.")


def test_a_quantified_change_claim_is_not():
    """'two or more' is precise; flagging its 'more' would be wrong."""
    assert "AC-UNQUANTIFIED-CHANGE" not in _rules(
        "The endpoint rejects two or more consecutive spaces in a name.")


def test_an_empty_criterion_says_so_rather_than_passing_clean():
    assert _rules("") == {"AC-EMPTY"}
    assert _rules("   ") == {"AC-EMPTY"}


# --------------------------------------------------------------------------
# What did NOT cross from Atlas, and the reason it must not.
# --------------------------------------------------------------------------

def test_metis_own_drafted_criterion_is_clean():
    """**The porting decision, asserted.**

    Atlas's `AC-TITLE-IS-SCENARIO` fires on any Given/When/Then text, because in
    Atlas the statement and the scenario are separate artifacts. In Métis the
    criterion text IS the Given/When/Then sentence — `ac_drafting` renders
    exactly this shape. Porting that rule would have reported every criterion
    Métis drafts as defective, and a checker that flags its own system's correct
    output gets switched off.
    """
    from metis_mcp.mbt.model import Model, State, Transition
    from metis_mcp.model_sources.ac_drafting import draft_from_model

    drafted = draft_from_model(Model(
        id="records-api",
        states={"Draft": State(id="Draft", name="Draft", surface="api",
                               is_initial=True),
                "Submitted": State(id="Submitted", name="Submitted",
                                   surface="api")},
        transitions={"t1": Transition(
            id="t1", source="Draft", target="Submitted",
            trigger="POST /records/{id}/submit",
            guard="record is complete")},
    ))
    assert drafted.drafts, "the fixture must produce a draft or this proves nothing"
    for draft in drafted.drafts:
        assert _rules(draft.text) == set(), (
            f"Métis's own drafted criterion was reported as defective: "
            f"{draft.text!r} -> {_rules(draft.text)}")


def test_a_given_clause_may_carry_two_preconditions_without_being_non_atomic():
    """Atomicity is about assertions, not about the word 'and'."""
    text = ("Given a draft record and an authenticated owner, when the owner "
            "submits it, then the status becomes Submitted.")
    assert ac_quality.is_atomic(ac_quality.assess(text))


def test_two_assertions_in_one_clause_is_not_atomic():
    text = ("Given a draft record, when the owner submits it, then the status "
            "becomes Submitted and an email is sent and the log is written.")
    findings = ac_quality.assess(text)
    assert "AC-MULTI-ASSERT" in {f.rule for f in findings}
    assert not ac_quality.is_atomic(findings)


def test_atomicity_is_read_from_the_findings_not_recomputed():
    """The boolean and the finding explaining it cannot disagree."""
    for text in ("The system rejects an empty name.",
                 "It does a; and b; and c.",
                 ""):
        findings = ac_quality.assess(text)
        assert ac_quality.is_atomic(findings) == (
            "AC-MULTI-ASSERT" not in {f.rule for f in findings})


def test_a_quoted_literal_is_not_read_as_prose():
    """A criterion quoting the tokens under test must not have them counted."""
    text = "The parser rejects ' and ' and ' & ' in a record name."
    assert "AC-MULTI-ASSERT" not in _rules(text)


# --------------------------------------------------------------------------
# It is advisory. This is the part that must not quietly change.
# --------------------------------------------------------------------------

def test_nothing_here_rewrites_the_criterion():
    """S-13: mining never reshapes text to make it conform, and neither does this."""
    text = "The system responds appropriately."
    findings = ac_quality.assess(text)
    assert findings
    for f in findings:
        assert f.suggestion != text
        # A suggestion is guidance, never a replacement string to apply.
        assert not f.suggestion.startswith("The system")


def test_the_tool_says_it_blocks_nothing():
    payload = json.loads(server.ac_quality("The system responds appropriately."))
    assert payload["ok"] is True
    assert payload["errors"] >= 1
    assert "advisory" in payload
    assert "Quarantine" in payload["advisory"]


def test_the_tool_always_carries_atomic_even_when_false():
    """`_prune` deletes False. Without `atomic` in `_ALWAYS_KEPT` the answer
    would vanish exactly when it is 'no'."""
    payload = json.loads(server.ac_quality(
        "It does a; and b; and c; and d."))
    assert "atomic" in payload, "the field disappeared when it mattered"
    assert payload["atomic"] is False
