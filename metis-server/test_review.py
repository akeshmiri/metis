"""
Review-as-code tests (application spec N-7, N-10, N-13, N-14).

Free to run: no Neo4j, no model calls, no config.
"""
import sys

from metis_mcp.mbt import ALL_TRANSITIONS, generate
from metis_mcp.mbt.model import APPROVED, QUARANTINE, REJECTED
from metis_mcp.review import (
    APPROVE,
    DEFER,
    REJECT,
    ReviewFile,
    apply,
    export,
    format_audit,
    model_fingerprint,
)
from mbt_fixtures import login_model


def _reviewed(model, reviewer="alice", decision=APPROVE, rationale=""):
    review = export(model)
    review.reviewer = reviewer
    for item in review.items:
        item.decision = decision
        item.rationale = rationale
    return review


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------

def test_export_lists_everything_awaiting_a_decision():
    model = login_model(approved=False)
    review = export(model)
    # 10 states + 16 implemented transitions; the planned one has nothing to approve.
    assert len(review.items) == 26, f"expected 26 items, got {len(review.items)}"
    assert not any(i.id == "t17" for i in review.items), (
        "a planned transition is not a gap and needs no decision"
    )


def test_export_carries_the_evidence_needed_to_decide():
    """Spec N-3: a decision screen must show enough to decide without leaving it."""
    model = login_model(approved=False)
    review = export(model)
    transition_item = next(i for i in review.items if i.id == "t06")
    assert transition_item.evidence["from"] == "Failed4"
    assert transition_item.evidence["to"] == "AccountLocked"
    assert transition_item.evidence["trigger"] == "submit_invalid_credentials"
    assert transition_item.evidence["guard"] == "NOT credentials_valid"


def test_export_defaults_every_item_to_defer():
    """Nothing is approved by omission -- a decision must be made deliberately."""
    review = export(login_model(approved=False))
    assert all(i.decision == DEFER for i in review.items)


def test_export_round_trips_through_json():
    review = export(login_model(approved=False))
    restored = ReviewFile.from_json(review.to_json())
    assert restored.fingerprint == review.fingerprint
    assert len(restored.items) == len(review.items)
    assert restored.items[0].evidence == review.items[0].evidence


# --------------------------------------------------------------------------
# Apply
# --------------------------------------------------------------------------

def test_apply_approves_and_unblocks_generation():
    model = login_model(approved=False)
    assert generate(model, ALL_TRANSITIONS).paths == []

    result = apply(model, _reviewed(model))
    assert result.ok, result.blocked_reason
    assert len(result.applied) == 26
    assert model.is_approved
    assert len(generate(model, ALL_TRANSITIONS).paths) == 16


def test_apply_records_who_what_and_against_which_evidence():
    """Spec N-13/N-14: the audit records the evidence, not just the outcome."""
    model = login_model(approved=False)
    fingerprint = model_fingerprint(model)
    result = apply(model, _reviewed(model, reviewer="bob"))
    assert result.ok
    record = result.applied[0]
    assert record.reviewer == "bob"
    assert record.fingerprint == fingerprint
    assert record.from_state == QUARANTINE and record.to_state == APPROVED
    assert record.decided_at


def test_apply_refuses_without_a_reviewer_identity():
    model = login_model(approved=False)
    review = _reviewed(model, reviewer="")
    result = apply(model, review)
    assert not result.ok
    assert "reviewer identity" in result.blocked_reason


def test_apply_refuses_a_reject_without_rationale():
    model = login_model(approved=False)
    review = _reviewed(model, decision=REJECT, rationale="")
    result = apply(model, review)
    assert result.ok, "the file itself is valid; individual items are refused"
    assert len(result.applied) == 0
    assert all("rationale" in reason for _, reason in result.refused)


def test_apply_records_rejection_as_rejected():
    model = login_model(approved=False)
    review = _reviewed(model, decision=REJECT, rationale="guard is wrong")
    result = apply(model, review)
    assert result.ok
    assert model.transitions["t06"].lifecycle_state == REJECTED
    assert generate(model, ALL_TRANSITIONS).paths == []


def test_defer_leaves_the_element_untouched():
    model = login_model(approved=False)
    result = apply(model, _reviewed(model, decision=DEFER))
    assert result.ok
    assert result.applied == []
    assert model.transitions["t06"].lifecycle_state == QUARANTINE


# --------------------------------------------------------------------------
# N-14 : staleness refuses
# --------------------------------------------------------------------------

def test_apply_refuses_when_the_model_moved_since_export():
    """The central rule: decisions made against different evidence must not apply."""
    model = login_model(approved=False)
    review = _reviewed(model)

    # A guard changes after export -- exactly what a re-extraction would do.
    old = model.transitions["t06"]
    model.transitions["t06"] = type(old)(
        id=old.id, source=old.source, trigger=old.trigger, target=old.target,
        guard="NOT credentials_valid AND attempts >= 5",
        implementation_status=old.implementation_status,
        lifecycle_state=old.lifecycle_state,
    )

    result = apply(model, review)
    assert not result.ok
    assert "changed since this file was exported" in result.blocked_reason
    assert model.transitions["t06"].lifecycle_state == QUARANTINE, (
        "a refused apply must change nothing at all"
    )


def test_fingerprint_covers_reviewable_substance():
    model = login_model(approved=False)
    before = model_fingerprint(model)

    # A rename changes what a reviewer read, so it must move the fingerprint.
    old = model.states["Failed1"]
    model.states["Failed1"] = type(old)(
        id=old.id, name="FirstFailure", surface=old.surface,
        is_initial=old.is_initial, lifecycle_state=old.lifecycle_state,
    )
    assert model_fingerprint(model) != before


def test_apply_refuses_a_file_for_a_different_model():
    review = _reviewed(login_model(approved=False))
    review.model_id = "checkout-api"
    result = apply(login_model(approved=False), review)
    assert not result.ok
    assert "checkout-api" in result.blocked_reason


def test_apply_refuses_an_unknown_file_version():
    model = login_model(approved=False)
    review = _reviewed(model)
    review.version = "metis.review/99"
    result = apply(model, review)
    assert not result.ok
    assert "version" in result.blocked_reason


# --------------------------------------------------------------------------
# N-10 : the proposer may not approve their own element
# --------------------------------------------------------------------------

def test_n10_self_approval_is_refused_by_default():
    model = login_model(approved=False)
    review = _reviewed(model, reviewer="alice")
    for item in review.items:
        item.proposed_by = "alice"
    result = apply(model, review)
    assert result.ok
    assert result.applied == [], "alice proposed these; she may not approve them"
    assert all("may not approve" in reason for _, reason in result.refused)


def test_n10_a_different_approver_is_accepted():
    model = login_model(approved=False)
    review = _reviewed(model, reviewer="bob")
    for item in review.items:
        item.proposed_by = "alice"
    result = apply(model, review)
    assert result.ok
    assert len(result.applied) == 26
    assert not any(r.self_approval for r in result.applied)


def test_n11_self_approval_override_is_recorded_visibly():
    """Spec N-11: the override exists, and its use is never silent."""
    model = login_model(approved=False)
    review = _reviewed(model, reviewer="alice")
    review.allow_self_approval = True
    for item in review.items:
        item.proposed_by = "alice"
    result = apply(model, review)
    assert result.ok
    assert len(result.applied) == 26
    assert all(r.self_approval for r in result.applied)
    assert "[SELF-APPROVED]" in format_audit(result.applied)


# --------------------------------------------------------------------------
# Naming decisions
# --------------------------------------------------------------------------

def test_a_naming_decision_is_applied_with_the_approval():
    model = login_model(approved=False)
    review = _reviewed(model)
    for item in review.items:
        if item.id == "Failed1":
            item.name = "FirstFailedAttempt"
    result = apply(model, review)
    assert result.ok
    assert model.states["Failed1"].name == "FirstFailedAttempt"
    assert model.states["Failed1"].lifecycle_state == APPROVED


# --------------------------------------------------------------------------
# S-19 : approving a rule does not, on its own, create intent
# --------------------------------------------------------------------------

def _with_criterion(model, decision="approve", text=None, affirmed=False):
    from metis_mcp.review.decisions import export
    review = export(model)
    review.reviewer = "alice"
    item = next(i for i in review.items if i.kind == "transition")
    item.decision = decision
    item.rationale = "reviewed"
    item.criterion_id = "AC-1"
    item.criterion_text = text
    item.affirmed_as_intent = affirmed
    return review, item


def test_s19_approving_a_draft_unchanged_does_NOT_promote_it():
    """The rubber-stamp case. On the pilot estate every criterion was drafted
    from the code; promoting on approval alone would have graded all of them as
    intent at a stroke."""
    from metis_mcp.review.decisions import apply
    model = login_model(approved=False)
    review, _ = _with_criterion(model, text="Given X, when Y, then Z.")
    result = apply(model, review, drafted={"AC-1": "Given X, when Y, then Z."})
    promoted = [r for r in result.applied if r.criterion_promoted_to]
    assert promoted == [], "an untouched approval documents; it does not validate"


def test_s19_an_EDIT_promotes_it():
    from metis_mcp.reconciliation import HUMAN_CONFIRMED
    from metis_mcp.review.decisions import apply
    model = login_model(approved=False)
    review, _ = _with_criterion(model, text="Given X, when Y, then something else.")
    result = apply(model, review, drafted={"AC-1": "Given X, when Y, then Z."})
    promoted = [r for r in result.applied if r.criterion_promoted_to]
    assert len(promoted) == 1
    assert promoted[0].criterion_promoted_to == HUMAN_CONFIRMED
    assert promoted[0].criterion_id == "AC-1"


def test_s19_an_explicit_affirmation_promotes_it():
    """A separate act from approving: 'I checked this against what we intend'."""
    from metis_mcp.reconciliation import HUMAN_CONFIRMED
    from metis_mcp.review.decisions import apply
    model = login_model(approved=False)
    review, _ = _with_criterion(model, text="Given X, when Y, then Z.", affirmed=True)
    result = apply(model, review, drafted={"AC-1": "Given X, when Y, then Z."})
    promoted = [r for r in result.applied if r.criterion_promoted_to]
    assert promoted and promoted[0].criterion_promoted_to == HUMAN_CONFIRMED


def test_s19_a_rejection_never_promotes():
    from metis_mcp.review.decisions import apply
    model = login_model(approved=False)
    review, _ = _with_criterion(model, decision="reject", text="totally different",
                                affirmed=True)
    result = apply(model, review, drafted={"AC-1": "Given X, when Y, then Z."})
    assert all(not r.criterion_promoted_to for r in result.applied)


def test_s19_an_item_with_no_criterion_is_unaffected():
    from metis_mcp.review.decisions import apply, export
    model = login_model(approved=False)
    review = export(model)
    review.reviewer = "alice"
    for i in review.items:
        i.decision = "approve"; i.rationale = "ok"
    result = apply(model, review)
    assert all(r.criterion_promoted_to is None for r in result.applied)


def test_s19_the_promotion_is_recorded_for_audit():
    """N-13: who, when, what — and now, what grade it moved."""
    from metis_mcp.review.decisions import apply
    model = login_model(approved=False)
    review, _ = _with_criterion(model, text="a person rewrote this")
    record = next(r for r in apply(model, review, drafted={"AC-1": "draft"}).applied
                  if r.criterion_promoted_to)
    assert record.reviewer == "alice" and record.decided_at


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


def test_printed_next_step_commands_carry_the_scope_they_need():
    """An instruction the tool tells you to run has to run.

    `review export --journey X --surface ui` printed
    `review apply --journey X <file>` — no `--surface`. `apply` defaults to
    `api` and refused with "review file is for model 'archive-ui', not
    'archive-api'". The refusal was honest; the instruction that produced it
    was not runnable.

    The sibling defect: `publish` printed `publish None --confirm publish`,
    because `args.model` is None when the scope came from the graph.
    """
    import pathlib
    import re

    from metis_mcp.mbt import cli

    source = pathlib.Path(cli.__file__).read_text()

    # Join implicit string concatenation first. These prints span two lines, and
    # matching one literal at a time captured `"review apply "` — which has no
    # `--journey`, so every assertion below was skipped and this test passed
    # with the bug deliberately re-injected. A regex over source has to account
    # for how the source is actually written.
    joined = re.sub(r'"\s*\n\s*f?"', "", source)

    printed = re.findall(r'print\(f?"[^"]*metis_mcp\.mbt\.cli ([^"]*)"', joined)
    assert printed, "no next-step instructions found — the parser missed them"
    assert any("--journey" in c for c in printed), (
        "no journey-scoped instruction was found; the parser is not seeing the "
        "commands this test exists to check"
    )

    for command in printed:
        assert "{args.model}" not in command or "--model" in command, (
            f"instruction interpolates a possibly-None model: {command!r}")
        # A journey-scoped command is always surface-scoped too: the two
        # together name one model, and journey alone names two.
        if "--journey" in command:
            assert "--surface" in command, (
                f"journey-scoped instruction omits --surface, so it resolves to "
                f"the wrong model on a ui scope: {command!r}")
