"""
Writing a requirement back to the tracker it came from (§3.2 stage 1, T-20).

**The half that made requirement management one-directional.** Intake reads a
tracker item and lands a `Requirement`; `metis requirement` states and revises
one. Neither could put a corrected wording back where the team reads it, so the
rewriting work lesson 14 identifies as the largest single piece of first-pass
effort landed somewhere only Métis could see.

**It reuses `drift.classify`, and that is the point.** T-13's reasoning — that a
two-way diff conflates a model change with a human edit, and that the edit must
decide because overwriting it is the irreversible outcome — is about three
hashes, not about test cases. A second three-way rule here would agree with the
first today and drift from it later; `classify` is the one rule, and this
supplies the requirement-shaped hash.

**A hand-edited ticket is never overwritten** (T-15). Somebody rewording a Jira
summary is doing exactly the work Métis asked them to do, and silently
destroying it teaches people not to trust the tool — which costs far more than a
missed update.

**Two keys, as every outward write has.** `Transport.check_permitted` requires
`METIS_ALLOW_EXTERNAL_WRITES=yes` on the installation, and the caller supplies a
G2 literal in the run. The first can be produced by whatever drives the run,
including an agent; the second cannot be set by one.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from metis_mcp.publishing.drift import (
    CHANGED,
    MANUALLY_EDITED,
    NEW,
    NO_ACTION,
    PROPOSE_CREATE,
    PROPOSE_NOTHING,
    PROPOSE_UPDATE,
    UNCHANGED,
    classify,
)


def requirement_hash(text: str) -> str:
    """What a reader of the ticket would see, normalised the way claims are.

    `identity.normalise_claim` collapses whitespace and nothing else —
    deliberately, because case, punctuation and word order all carry meaning in a
    requirement. *shall* and *shall not* differ by three characters, and anything
    that folded them would decide two different claims were one.
    """
    from metis_mcp.identity.keys import normalise_claim

    return hashlib.sha256(normalise_claim(text).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class WritebackItem:
    """One requirement, and what should happen to its ticket."""

    requirement_id: str
    anchor_id: str                  # `jira:PROJ-14` — the ticket it came from
    drift_class: str
    action: str
    detail: str
    metis_text: str = ""
    tracker_text: str = ""


@dataclass
class WritebackPlan:
    """What a write-back would do. **Pure** — nothing here sends anything."""

    items: list = field(default_factory=list)

    @property
    def to_send(self) -> list:
        return [i for i in self.items
                if i.action in (PROPOSE_CREATE, PROPOSE_UPDATE)]

    @property
    def blocked(self) -> list:
        return [i for i in self.items if i.action == PROPOSE_NOTHING]

    def describe(self) -> str:
        if not self.items:
            return "  nothing in scope"
        lines = []
        for item in sorted(self.items, key=lambda i: i.requirement_id):
            lines.append(f"  [{item.drift_class:<16}] {item.anchor_id} "
                         f"-> {item.action}")
            lines.append(f"      {item.detail}")
        return "\n".join(lines)


def plan_writeback(requirements, tracker_text: dict, last_written: dict,
                   *, can_see_tracker: bool = True) -> WritebackPlan:
    """Which requirements differ from their tickets, and what to do. **Pure.**

    `requirements` is `[(requirement_id, anchor_id, text)]` from the graph.
    `tracker_text` maps an anchor id to what the ticket says NOW.
    `last_written` maps an anchor id to the hash Métis last wrote.

    **`can_see_tracker=False` is not "no ticket exists".** With no read of the
    tracker, whether an item is there is unknown — and reporting unknown as
    absence is how a second ticket gets created for a requirement that already
    has one. It is the same distinction `PublicationLedger.can_see_published_content`
    draws, for the same reason.
    """
    plan = WritebackPlan()
    for requirement_id, anchor_id, text in requirements:
        new_hash = requirement_hash(text)
        current = tracker_text.get(anchor_id)
        current_hash = requirement_hash(current) if current is not None else None
        last = last_written.get(anchor_id)

        drift_class, action = classify(last, current_hash, new_hash,
                                       can_see_published=can_see_tracker)

        if drift_class == NEW:
            detail = (f"no ticket recorded for this requirement"
                      if can_see_tracker else
                      "the tracker has not been read, so whether a ticket "
                      "exists is UNKNOWN, not no. Verify before creating")
        elif drift_class == MANUALLY_EDITED:
            detail = ("the ticket differs from what Métis last wrote — somebody "
                      "edited it by hand. Proposing nothing; a human decides "
                      "which wording is right (T-15)")
        elif drift_class == CHANGED:
            detail = "the requirement was revised in Métis; the ticket is stale"
        else:
            detail = "the ticket already says this"

        plan.items.append(WritebackItem(
            requirement_id=requirement_id, anchor_id=anchor_id,
            drift_class=drift_class, action=action, detail=detail,
            metis_text=text, tracker_text=current or ""))
    return plan


def apply_writeback(plan: WritebackPlan, writer, confirmation) -> dict:
    """Send what the plan proposes. **Refuses without a G2 confirmation.**

    `writer` is a `JiraWriter`; `confirmation` is the literal the run supplied.
    Nothing here decides whether a write is allowed — `check_permitted` does that
    on the installation, and the confirmation does it for the run.
    """
    from metis_mcp.publishing.publish import ConfirmationRefused

    if confirmation is None:
        raise ConfirmationRefused(
            "a write-back needs a confirmation in this run. Nothing was sent")

    sent, refused = [], []
    for item in plan.to_send:
        try:
            # The ticket key out of the anchor: `jira:PROJ-14` -> `PROJ-14`.
            key = item.anchor_id.split(":", 1)[-1]
            result = writer.update_issue_summary(key, item.metis_text)
            sent.append({"anchor": item.anchor_id, "key": key,
                         "url": result.get("url", "")})
        except Exception as e:                     # noqa: BLE001 - reported
            refused.append({"anchor": item.anchor_id, "reason": str(e)})

    return {
        "ok": not refused,
        "sent": sent,
        "refused": refused,
        # Named, never counted: a requirement Métis declined to write back is
        # one somebody has to look at.
        "not_sent": [{"anchor": i.anchor_id, "why": i.detail}
                     for i in plan.blocked],
        "means": ("what left Métis. A hand-edited ticket was never overwritten "
                  "(T-15), and nothing was deleted"),
    }
