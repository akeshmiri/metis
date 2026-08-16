"""
Identity, deduplication and incremental-update tests
(application spec §14; R12, R13; A-29..A-36).

Free to run: matching is pure.
"""
import sys

from metis_mcp.identity import (
    ADDED,
    MODIFIED,
    REMOVED,
    UNCHANGED,
    carry_human_facts,
    diff,
    normalise_guard,
    state_key,
    transition_key,
)
from metis_mcp.mbt.model import APPROVED, QUARANTINE, Model, State, Transition
from mbt_fixtures import login_model


def _swap_guard(model, tid, guard):
    old = model.transitions[tid]
    model.transitions[tid] = Transition(
        id=old.id, source=old.source, trigger=old.trigger, target=old.target,
        guard=guard, implementation_status=old.implementation_status,
        lifecycle_state=old.lifecycle_state)
    model.reindex()
    return model


# --------------------------------------------------------------------------
# I-2 : keys are over meaning, not representation
# --------------------------------------------------------------------------

def test_guard_is_an_attribute_not_identity():
    """A guard edit is the commonest change; if it moved identity, nothing would
    survive a code tweak."""
    a = login_model()
    b = _swap_guard(login_model(), "t06", "NOT credentials_valid AND attempts >= 5")
    assert (transition_key(a.id, a.transitions["t06"], a)
            == transition_key(b.id, b.transitions["t06"], b))


def test_a_rename_does_not_change_state_identity():
    model = login_model()
    original = state_key(model.id, model.states["Failed1"])
    renamed = State(id="Failed1", name="FirstFailure", surface="api",
                    lifecycle_state=APPROVED)
    assert state_key(model.id, renamed) == original


def test_changing_the_target_changes_transition_identity():
    """Source, trigger and target ARE the transition."""
    a = login_model()
    b = login_model()
    old = b.transitions["t06"]
    b.transitions["t06"] = Transition(id=old.id, source=old.source, trigger=old.trigger,
                                      target="LoggedIn", guard=old.guard)
    b.reindex()
    assert (transition_key(a.id, a.transitions["t06"], a)
            != transition_key(b.id, b.transitions["t06"], b))


def test_guard_normalisation_is_minimal_and_does_not_interpret():
    assert normalise_guard("  a   AND  b ") == "a AND b"
    assert normalise_guard("((x))") == "x"
    # Commutativity is NOT assumed — deciding these are equal is an interpretation.
    assert normalise_guard("a AND b") != normalise_guard("b AND a")


# --------------------------------------------------------------------------
# R13 / A-30, A-31 : incremental, not reset
# --------------------------------------------------------------------------

def test_a30_identical_re_extraction_produces_zero_deltas():
    delta = diff(login_model(), login_model())
    assert delta.summary[UNCHANGED] == 27, delta.summary
    for kind in (ADDED, MODIFIED, REMOVED):
        assert delta.summary[kind] == 0, f"{kind}: {[c.detail for c in delta.of(kind)]}"


def test_a31_a_guard_change_yields_exactly_one_modified():
    previous = login_model()
    candidate = _swap_guard(login_model(), "t06", "NOT credentials_valid AND attempts >= 5")
    delta = diff(previous, candidate)
    modified = delta.of(MODIFIED)
    assert len(modified) == 1, [c.detail for c in modified]
    assert modified[0].element_id == "t06"
    assert "guard changed" in modified[0].detail
    assert delta.summary[ADDED] == 0 and delta.summary[REMOVED] == 0


def test_added_and_removed_are_detected():
    previous = login_model()
    candidate = login_model()
    del candidate.transitions["t11"]
    candidate.transitions["tNew"] = Transition(
        id="tNew", source="LoggedIn", trigger="download_data", target="LoggedIn",
        lifecycle_state=QUARANTINE)
    candidate.reindex()
    delta = diff(previous, candidate)
    assert any(c.element_id == "t11" for c in delta.of(REMOVED))
    assert any(c.element_id == "tNew" for c in delta.of(ADDED))


def test_removed_never_deletes_from_the_prior_model():
    """Spec I-12: removed means 'not a member of this version'."""
    previous = login_model()
    candidate = login_model()
    del candidate.transitions["t11"]
    candidate.reindex()
    diff(previous, candidate)
    assert "t11" in previous.transitions, "the prior model must be untouched"


# --------------------------------------------------------------------------
# I-14, I-16 : human facts survive re-extraction
# --------------------------------------------------------------------------

def test_a32_resolved_names_and_approvals_survive():
    previous = login_model(approved=True)
    previous.states["Failed1"] = State(id="Failed1", name="FirstFailedAttempt",
                                       surface="api", lifecycle_state=APPROVED)
    candidate = login_model(approved=False)          # a fresh extraction
    candidate.states["Failed1"] = State(id="Failed1", name="Failed1", surface="api",
                                        lifecycle_state=QUARANTINE)

    result = carry_human_facts(previous, candidate, diff(previous, candidate))
    assert result.model.states["Failed1"].name == "FirstFailedAttempt", (
        "extraction may propose a name, never overwrite a resolved one (I-15)"
    )
    assert result.model.states["Failed1"].lifecycle_state == APPROVED
    assert result.model.transitions["t01"].lifecycle_state == APPROVED


def test_a33_an_anchor_move_with_an_identical_guard_retains_approval():
    """A refactor is not a behaviour change (spec I-17)."""
    previous = login_model(approved=True)
    candidate = login_model(approved=False)
    result = carry_human_facts(previous, candidate, diff(previous, candidate))
    assert result.revoked == []
    assert all(t.lifecycle_state == APPROVED for t in result.model.transitions.values())


def test_a_guard_change_revokes_approval_for_that_transition():
    previous = login_model(approved=True)
    candidate = _swap_guard(login_model(approved=False), "t12", "email_registered AND verified")
    result = carry_human_facts(previous, candidate, diff(previous, candidate))
    assert any("t12" in r for r in result.revoked), result.revoked
    assert result.model.transitions["t12"].lifecycle_state == QUARANTINE


# --------------------------------------------------------------------------
# A-34 / I-18 : group revalidation
# --------------------------------------------------------------------------

def test_a34_adding_to_a_group_revalidates_its_siblings():
    """Determinism and guard completeness are properties of a (state, trigger)
    group, so a new member can break an approved sibling that did not change."""
    previous = login_model(approved=True)
    candidate = login_model(approved=False)
    candidate.transitions["t02b"] = Transition(
        id="t02b", source="LoggedOut", trigger="submit_invalid_credentials",
        target="AccountLocked", guard="ip_blocklisted", lifecycle_state=QUARANTINE)
    candidate.reindex()

    result = carry_human_facts(previous, candidate, diff(previous, candidate))
    # t02 shares (LoggedOut, submit_invalid_credentials) with the new t02b.
    assert any("t02" in r and "group" in r for r in result.revoked), result.revoked
    assert result.model.transitions["t02"].lifecycle_state == QUARANTINE
    # An unrelated group is untouched.
    assert result.model.transitions["t11"].lifecycle_state == APPROVED


# --------------------------------------------------------------------------
# A-36 / I-21 : renames are proposed, never assumed
# --------------------------------------------------------------------------

def test_a36_a_similar_removed_added_pair_is_proposed_as_a_rename():
    previous = login_model()
    candidate = login_model()
    # A state's observable signature changes: 401 -> 403, say.
    old = candidate.states.pop("SessionExpired")
    candidate.states["SessionExpiredNow"] = State(
        id="SessionExpiredNow", name=old.name, surface=old.surface,
        lifecycle_state=old.lifecycle_state)
    for tid, t in list(candidate.transitions.items()):
        if t.source == "SessionExpired" or t.target == "SessionExpired":
            candidate.transitions[tid] = Transition(
                id=t.id,
                source="SessionExpiredNow" if t.source == "SessionExpired" else t.source,
                trigger=t.trigger,
                target="SessionExpiredNow" if t.target == "SessionExpired" else t.target,
                guard=t.guard, lifecycle_state=t.lifecycle_state)
    candidate.reindex()

    delta = diff(previous, candidate)
    assert delta.renames, "a similar removed/added pair must be proposed"
    proposal = next(r for r in delta.renames if r.kind == "state")
    assert "SessionExpired" in proposal.removed_key
    assert "SessionExpiredNow" in proposal.added_key
    assert proposal.similarity >= 0.6


def test_a36_an_unconfirmed_rename_stays_removed_plus_added():
    """Spec I-22: proposed, never applied."""
    previous = login_model()
    candidate = login_model()
    old = candidate.states.pop("PasswordResetSent")
    candidate.states["PasswordResetSentX"] = State(id="PasswordResetSentX", name=old.name,
                                                   surface=old.surface)
    for tid, t in list(candidate.transitions.items()):
        if t.target == "PasswordResetSent":
            candidate.transitions[tid] = Transition(
                id=t.id, source=t.source, trigger=t.trigger, target="PasswordResetSentX",
                guard=t.guard, lifecycle_state=t.lifecycle_state)
    candidate.reindex()

    delta = diff(previous, candidate)
    assert delta.renames
    assert any(c.delta == REMOVED for c in delta.changes)
    assert any(c.delta == ADDED for c in delta.changes)
    result = carry_human_facts(previous, candidate, delta)
    assert any("NOT applied" in n for n in result.notes)


# --------------------------------------------------------------------------
# R12 : one element, several attributions
# --------------------------------------------------------------------------

def test_a29_the_same_natural_key_from_two_sources_is_one_element():
    """Two sources proposing the same (source, trigger, target) are proposing the
    same element, whatever ids they happened to mint."""
    from_code = login_model()
    from_author = login_model()
    old = from_author.transitions.pop("t06")
    from_author.transitions["authored-lockout"] = Transition(
        id="authored-lockout", source=old.source, trigger=old.trigger,
        target=old.target, guard=old.guard, lifecycle_state=old.lifecycle_state)
    from_author.reindex()

    assert (transition_key(from_code.id, from_code.transitions["t06"], from_code)
            == transition_key(from_author.id,
                              from_author.transitions["authored-lockout"], from_author))
    delta = diff(from_code, from_author)
    assert delta.summary[ADDED] == 0 and delta.summary[REMOVED] == 0, (
        "differing ids for the same meaning must not read as add + remove"
    )


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
