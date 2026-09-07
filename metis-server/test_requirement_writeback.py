"""
Writing a requirement back to the tracker it came from.

**The half that made requirement management one-directional.** Intake reads a
tracker item and lands a `Requirement`; `metis requirement` states and revises
one. Neither could put a corrected wording back where the team reads it, so the
rewriting work lesson 14 calls the largest single piece of first-pass effort
landed somewhere only Métis could see.
"""
from __future__ import annotations

import pytest

from metis_mcp.publishing import drift
from metis_mcp.publishing.publish import ConfirmationRefused
from metis_mcp.publishing.requirement_writeback import (
    apply_writeback,
    plan_writeback,
    requirement_hash,
)

TEXT = "When a record has been archived, the system shall reject an update with 409"
REVISED = "When a record has been archived, the system shall reject an update with 423"


class _Writer:
    """Records what it was asked to send. Sends nothing."""

    def __init__(self, fail_on: str = ""):
        self.calls: list = []
        self.fail_on = fail_on

    def update_issue_summary(self, key, summary):
        if key == self.fail_on:
            raise RuntimeError("the tracker refused")
        self.calls.append((key, summary))
        return {"url": f"https://tracker.example/browse/{key}"}


def _plan(reqs, tracker, last, **kw):
    return plan_writeback(reqs, tracker, last, **kw)


# ---------------------------------------------------------------------------
# One decision, not two
# ---------------------------------------------------------------------------


def test_the_three_way_decision_is_the_one_drift_already_makes():
    """**T-13's reasoning is about three hashes, not about test cases.**

    A second three-way rule here would agree with `drift.compare` today and come
    to disagree later about what a manual edit is. `classify` is the one rule;
    this supplies the requirement-shaped hash.
    """
    assert drift.classify(None, None, "h") == (drift.NEW, drift.PROPOSE_CREATE)
    assert drift.classify("a", "b", "a") == (drift.MANUALLY_EDITED,
                                             drift.PROPOSE_NOTHING)
    assert drift.classify("a", "a", "b") == (drift.CHANGED, drift.PROPOSE_UPDATE)
    assert drift.classify("a", "a", "a") == (drift.UNCHANGED, drift.NO_ACTION)


def test_an_edited_and_changed_ticket_is_decided_by_the_edit():
    """The edit is the fact that decides, because overwriting it is the
    irreversible outcome."""
    assert drift.classify("a", "b", "c")[0] == drift.MANUALLY_EDITED


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


def test_a_revised_requirement_proposes_an_update():
    plan = _plan([("R", "jira:D-1", REVISED)], {"jira:D-1": TEXT},
                 {"jira:D-1": requirement_hash(TEXT)})
    assert plan.items[0].drift_class == drift.CHANGED
    assert plan.to_send


def test_a_ticket_that_already_says_it_proposes_nothing():
    plan = _plan([("R", "jira:D-1", TEXT)], {"jira:D-1": TEXT},
                 {"jira:D-1": requirement_hash(TEXT)})
    assert plan.items[0].drift_class == drift.UNCHANGED
    assert not plan.to_send


def test_a_hand_edited_ticket_is_never_proposed_for_update():
    """**T-15.** Somebody rewording a ticket is doing exactly the work Métis
    asked them to do. Silently destroying it teaches people not to trust the
    tool, which costs far more than a missed update."""
    plan = _plan([("R", "jira:D-1", REVISED)],
                 {"jira:D-1": "somebody rewrote this by hand"},
                 {"jira:D-1": requirement_hash(TEXT)})
    assert plan.items[0].drift_class == drift.MANUALLY_EDITED
    assert plan.items[0].action == drift.PROPOSE_NOTHING
    assert not plan.to_send
    assert plan.blocked


def test_an_unread_tracker_is_unknown_rather_than_absent():
    """**Reporting unknown as absence is how a second ticket gets created** for
    a requirement that already has one. The same distinction
    `PublicationLedger.can_see_published_content` draws."""
    plan = _plan([("R", "jira:D-1", TEXT)], {}, {}, can_see_tracker=False)
    assert "UNKNOWN, not no" in plan.items[0].detail

    seen = _plan([("R", "jira:D-1", TEXT)], {}, {}, can_see_tracker=True)
    assert "UNKNOWN" not in seen.items[0].detail


def test_whitespace_is_not_a_revision_and_wording_is():
    """`normalise_claim` collapses whitespace and nothing else — case,
    punctuation and word order all carry meaning. *shall* and *shall not* differ
    by three characters."""
    assert requirement_hash(TEXT) == requirement_hash("  " + TEXT.replace(" ", "  "))
    assert requirement_hash("The system shall do it.") != \
           requirement_hash("The system shall not do it.")


# ---------------------------------------------------------------------------
# Applying it
# ---------------------------------------------------------------------------


def test_nothing_is_sent_without_a_confirmation_in_the_run():
    plan = _plan([("R", "jira:D-1", REVISED)], {"jira:D-1": TEXT},
                 {"jira:D-1": requirement_hash(TEXT)})
    writer = _Writer()
    with pytest.raises(ConfirmationRefused):
        apply_writeback(plan, writer, None)
    assert writer.calls == [], "a write happened without a confirmation"


def test_a_blocked_item_never_reaches_the_writer():
    """The guard that matters: `to_send` excludes it, so the transport is never
    given the chance to overwrite somebody's work."""
    plan = _plan(
        [("R1", "jira:D-1", REVISED), ("R2", "jira:D-3", REVISED)],
        {"jira:D-1": TEXT, "jira:D-3": "hand edited"},
        {"jira:D-1": requirement_hash(TEXT), "jira:D-3": requirement_hash(TEXT)})
    writer = _Writer()
    out = apply_writeback(plan, writer, "publish")

    assert [k for k, _ in writer.calls] == ["D-1"]
    assert [n["anchor"] for n in out["not_sent"]] == ["jira:D-3"]


def test_what_was_not_sent_is_named_rather_than_counted():
    """A requirement Métis declined to write back is one somebody has to look
    at. A count is not something anybody can act on."""
    plan = _plan([("R", "jira:D-3", REVISED)], {"jira:D-3": "hand edited"},
                 {"jira:D-3": requirement_hash(TEXT)})
    out = apply_writeback(plan, _Writer(), "publish")
    assert out["not_sent"][0]["anchor"] == "jira:D-3"
    assert out["not_sent"][0]["why"]


def test_a_refusal_from_the_tracker_is_reported_not_swallowed():
    plan = _plan([("R", "jira:D-1", REVISED)], {"jira:D-1": TEXT},
                 {"jira:D-1": requirement_hash(TEXT)})
    out = apply_writeback(plan, _Writer(fail_on="D-1"), "publish")
    assert out["ok"] is False
    assert out["refused"][0]["anchor"] == "jira:D-1"


# ---------------------------------------------------------------------------
# The write itself
# ---------------------------------------------------------------------------


def test_the_write_touches_the_summary_and_nothing_else():
    """**Deliberately the narrowest possible write.** A description carries a
    tester's notes and links; a status is somebody's workflow. Métis has an
    opinion about exactly one of the three, and a PUT sending all of them would
    destroy the other two while looking like a wording fix.
    """
    import inspect

    from metis_mcp.publishing.tracker_write import JiraWriter

    body = inspect.getsource(JiraWriter.update_issue_summary)
    assert '"summary": summary' in body
    assert "description" not in body.split('"""')[-1]
    assert "issuetype" not in body


def test_an_empty_summary_is_refused():
    from metis_mcp.publishing.tracker_write import JiraWriter
    from metis_mcp.publishing.outward import OutwardWriteFailed

    writer = JiraWriter.__new__(JiraWriter)
    writer.check_permitted = lambda: None
    with pytest.raises(OutwardWriteFailed):
        writer.update_issue_summary("D-1", "   ")
    with pytest.raises(OutwardWriteFailed):
        writer.update_issue_summary("", "text")
