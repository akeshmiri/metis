"""
AC drafting tests (application spec §4.5, S-19; R5).

Free to run: drafting is pure.
"""
import sys

from metis_mcp.mbt.model import IMPLEMENTED, PLANNED, Model, State, Transition
from metis_mcp.model_sources.ac_drafting import (
    REVIEW_PROMPT,
    draft_from_model,
    format_drafts,
)
from metis_mcp.reconciliation import CODE_DERIVED, HUMAN_CONFIRMED
from mbt_fixtures import login_model


# --------------------------------------------------------------------------
# S-19 : every draft is documentation until a person touches it
# --------------------------------------------------------------------------

def test_s19_every_draft_is_code_derived():
    drafts = draft_from_model(login_model())
    assert drafts.drafts
    assert all(d.provenance == CODE_DERIVED for d in drafts.drafts)
    assert all(not d.to_criterion().is_intent for d in drafts.drafts)


def test_s19_a_draft_cannot_support_a_correctness_claim():
    """The whole point: it was written FROM the behaviour it describes."""
    from metis_mcp.reconciliation import confirm, prefilter, reconcile
    model = login_model()
    drafts = draft_from_model(model)
    criteria = [d.to_criterion() for d in drafts.drafts]

    confirmed = []
    for ac, d in zip(criteria, drafts.drafts):
        p = prefilter(ac, model, {})
        if p.candidates:
            confirmed.append(confirm(p, d.transition_id, "bob",
                                     provenance=ac.provenance))
    result = reconcile(model, criteria, confirmed)
    assert result.summary["matched_by_intent"] == 0
    assert not result.supports_a_correctness_claim


def test_s19_the_output_says_so_plainly():
    text = format_drafts(draft_from_model(login_model()))
    assert "code_derived" in text
    assert "does not validate it" in text
    assert REVIEW_PROMPT in text


def test_s19_a_human_edit_is_what_creates_intent():
    """Grade is upgraded by a person, never by the drafter."""
    draft = draft_from_model(login_model()).drafts[0]
    edited = draft.to_criterion()
    assert edited.provenance == CODE_DERIVED
    from metis_mcp.reconciliation import AcceptanceCriterion
    promoted = AcceptanceCriterion(id=edited.id, text="a person rewrote this",
                                   provenance=HUMAN_CONFIRMED)
    assert promoted.is_intent


# --------------------------------------------------------------------------
# What is drafted
# --------------------------------------------------------------------------

def test_one_draft_per_implemented_transition():
    model = login_model()
    drafts = draft_from_model(model)
    implemented = [t for t in model.transitions.values()
                   if t.implementation_status == IMPLEMENTED]
    assert len(drafts.drafts) == len(implemented) == 16


def test_planned_transitions_are_skipped_not_drafted():
    """Drafting one would invite a reviewer to confirm behaviour that does not
    exist (P-11)."""
    drafts = draft_from_model(login_model())
    assert len(drafts.skipped) == 1
    assert "planned" in drafts.skipped[0][1]
    assert "t17" not in {d.transition_id for d in drafts.drafts}


def test_a_draft_reads_as_given_when_then():
    model = login_model()
    draft = next(d for d in draft_from_model(model).drafts
                 if d.transition_id == "t01")
    assert draft.text.startswith("Given the system is LoggedOut")
    assert "when submit valid credentials" in draft.text
    assert "then the result is LoggedIn" in draft.text


def test_the_guard_is_carried_verbatim_though_placed_by_role():
    """Every word of the guard survives; none is paraphrased.

    It is no longer one contiguous span, and that is the point: a criterion is
    atomic (one condition, one action, one validation), so GD-2's prefix
    dimensions render into the Given as context and only the deciding condition
    is the criterion's condition. Nothing is dropped or reworded -- the parts are
    placed by the role they actually play.
    """
    model = login_model()
    draft = next(d for d in draft_from_model(model).drafts if d.transition_id == "t01")
    assert draft.preconditions == ("credentials_valid",)
    assert draft.and_guard == "NOT account_locked"
    assert "credentials_valid" in draft.text
    assert "NOT account_locked" in draft.text
    assert draft.is_atomic


def test_a_compound_guard_yields_one_condition_not_a_bundle():
    """The defect this replaces: a whole compound guard in one `and` clause.

    `authenticated AND NOT authorized -> 403` drafted as a single criterion said
    "when a request is made, and authenticated AND NOT authorized, then 403" --
    several criteria wearing one id, which a reviewer can only approve or reject
    as a bundle. Splitting it per conjunct would be worse: "when a request is
    made, and authenticated, then 403" is simply false.
    """
    model = Model(
        id="perm-api",
        states={"Ready": State(id="Ready", name="Ready", surface="api", is_initial=True),
                "Forbidden403": State(id="Forbidden403", name="Forbidden403", surface="api")},
        transitions={"t": Transition(
            id="t", source="Ready", trigger="POST /admin/action", target="Forbidden403",
            guard="authenticated AND NOT authorized")},
    )
    draft = draft_from_model(model).drafts[0]
    assert draft.and_guard == "NOT authorized", "one condition under test"
    assert draft.preconditions == ("authenticated",), "the prefix is context"
    assert draft.is_atomic
    given, _, rest = draft.text.partition(", when ")
    assert "authenticated" in given, "the prefix belongs to the Given, as context"
    assert "NOT authorized" in rest and "authenticated" not in rest.replace(
        "NOT authorized", ""), (
        "only the deciding condition may follow the When"
    )


def test_a_disjunction_is_reported_not_split_on_a_guess():
    """M-17 fail-closed: deciding which branch of an OR decides needs real
    boolean reasoning, so the guard is kept whole and the draft is marked."""
    model = Model(
        id="unlock-api",
        states={"Locked": State(id="Locked", name="Locked", surface="api", is_initial=True),
                "Unlocked": State(id="Unlocked", name="Unlocked", surface="api")},
        transitions={"t": Transition(
            id="t", source="Locked", trigger="unlock", target="Unlocked",
            guard="admin_unlocked OR lockout_elapsed")},
    )
    drafts = draft_from_model(model)
    assert not drafts.drafts[0].is_atomic
    assert drafts.drafts[0].and_guard == "admin_unlocked OR lockout_elapsed"
    assert [tid for tid, _ in drafts.not_atomic] == ["t"]
    assert drafts.skipped == [], (
        "a non-atomic draft was still written; 'not drafted' and 'drafted and "
        "compound' are different facts and must not share a list"
    )


def test_an_http_trigger_is_phrased_as_a_request():
    model = Model(
        id="m",
        states={"Ready": State(id="Ready", name="Ready", surface="api", is_initial=True),
                "Ok200": State(id="Ok200", name="Ok200", surface="api")},
        transitions={"t": Transition(id="t", source="Ready", trigger="GET /metric/{id}",
                                     target="Ok200")})
    model.reindex()
    draft = draft_from_model(model).drafts[0]
    assert "a GET request is made to /metric/{id}" in draft.text


def test_a_state_name_is_not_rewritten_by_the_drafter():
    """A business name comes from X-7's cascade. Rewriting `NoContent204` into
    prose here would put words in the reviewer's mouth and make the draft read
    as more settled than it is."""
    model = Model(
        id="m",
        states={"Ready": State(id="Ready", name="Ready", surface="api", is_initial=True),
                "NoContent204": State(id="NoContent204", name="NoContent204", surface="api")},
        transitions={"t": Transition(id="t", source="Ready", trigger="GET /x",
                                     target="NoContent204")})
    model.reindex()
    assert "NoContent204" in draft_from_model(model).drafts[0].text


def test_a_draft_adds_no_justification():
    """S-13: fluent justification is what makes a fabrication persuasive, and a
    draft that argues for itself is harder to disagree with."""
    for d in draft_from_model(login_model()).drafts:
        lowered = d.text.lower()
        for word in ("because", "correct", "should be", "ensures", "guarantees"):
            assert word not in lowered, f"{word!r} in {d.text!r}"


def test_drafting_is_deterministic_so_a_review_is_not_invalidated():
    a = draft_from_model(login_model())
    b = draft_from_model(login_model())
    assert [(d.id, d.transition_id, d.text) for d in a.drafts] == \
           [(d.id, d.transition_id, d.text) for d in b.drafts]


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
