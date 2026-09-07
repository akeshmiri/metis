"""
Review-as-code: decisions in a diffable file (application spec N-7, §9.4).

The escape hatch for volume, and the way the six human decision points (§9.1)
become usable before a web UI exists (N-16 stage 2).

    metis review export <model>          -> a decision file
    ...a human edits it...
    metis review apply <model> <file>    -> decisions applied, audit recorded

Three rules make this a real gate rather than a formality:

  * **N-13/N-14** a decision records what evidence was presented, not just the
    outcome. Here that is the exported file's own fingerprint: a decision is
    bound to the model state it was made against.
  * **Staleness refuses.** If the model moved after export, `apply` stops. Applying
    decisions made against different evidence is exactly what N-14 exists to
    prevent, and detecting it is cheap.
  * **N-10** the identity that proposed an element may not approve it. Enforced
    here, overridable only with the override recorded visibly (N-11).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from metis_mcp.mbt.model import (
    APPROVED,
    PLANNED,
    QUARANTINE,
    REJECTED,
    Model,
)

APPROVE = "approve"
REJECT = "reject"
DEFER = "defer"
_VALID_DECISIONS = {APPROVE, REJECT, DEFER}

FILE_VERSION = "metis.review/1"


from metis_mcp.review.state import source_fingerprint

# The evidence a decision binds to is the model's **source substance**, not its
# lifecycle (see review/state.py). Lifecycle is the human fact being decided;
# including it would mean applying a decision invalidated the file that made it.
model_fingerprint = source_fingerprint


@dataclass
class ReviewItem:
    kind: str            # "state" | "transition"
    id: str
    decision: str        # approve | reject | defer
    current_state: str
    evidence: dict = field(default_factory=dict)
    rationale: str = ""
    name: str | None = None      # a naming decision, where the reviewer supplies one
    proposed_by: str | None = None
    # Spec S-19. A rule may carry a drafted acceptance criterion; the reviewer
    # either leaves it alone, edits it, or affirms it as genuinely intended.
    # Only the last two create INTENT -- approving a draft unchanged documents
    # the system, it does not validate it.
    criterion_id: str | None = None
    criterion_text: str | None = None
    affirmed_as_intent: bool = False


@dataclass
class ReviewFile:
    version: str
    model_id: str
    fingerprint: str
    exported_at: str
    items: list[ReviewItem] = field(default_factory=list)
    reviewer: str = ""
    allow_self_approval: bool = False

    def to_json(self) -> str:
        return json.dumps({
            "version": self.version,
            "model_id": self.model_id,
            "fingerprint": self.fingerprint,
            "exported_at": self.exported_at,
            "reviewer": self.reviewer,
            "allow_self_approval": self.allow_self_approval,
            "_instructions": [
                "Set 'reviewer' to your identity before applying.",
                "For each item set 'decision' to approve | reject | defer.",
                "'rationale' is required for reject.",
                "'evidence' is what you were shown -- do not edit it.",
                "'criterion_text' IS editable. Editing it, or setting",
                "'affirmed_as_intent': true, promotes the criterion from",
                "code_derived to human_confirmed (S-19). Approving it unchanged",
                "documents the system; it does not validate it.",
                "Do not edit 'fingerprint': apply refuses if the model has moved.",
            ],
            "items": [
                {
                    "kind": i.kind, "id": i.id, "decision": i.decision,
                    "current_state": i.current_state, "evidence": i.evidence,
                    "rationale": i.rationale, "name": i.name,
                    "proposed_by": i.proposed_by,
                    # S-19: the criterion this rule carries. `criterion_text` is
                    # EDITABLE -- editing it is one of the two acts that promote
                    # the grade to intent; the other is `affirmed_as_intent`.
                    "criterion_id": i.criterion_id,
                    "criterion_text": i.criterion_text,
                    "affirmed_as_intent": i.affirmed_as_intent,
                }
                for i in self.items
            ],
        }, indent=2)

    @staticmethod
    def from_json(text: str) -> "ReviewFile":
        data = json.loads(text)
        return ReviewFile(
            version=data["version"], model_id=data["model_id"],
            fingerprint=data["fingerprint"], exported_at=data["exported_at"],
            reviewer=data.get("reviewer", ""),
            allow_self_approval=bool(data.get("allow_self_approval", False)),
            items=[ReviewItem(**{k: v for k, v in i.items()}) for i in data["items"]],
        )


def export(model: Model, include_approved: bool = False,
           authors: dict[str, str] | None = None,
           criteria: dict[str, tuple[str, str]] | None = None) -> ReviewFile:
    """Build a decision file for everything awaiting review.

    `evidence` carries what the reviewer needs to decide without leaving the file
    (spec N-3): for a transition, its full tuple and guard; for a state, its
    surface and whether it is initial.

    `criteria` maps a transition id to `(criterion_id, criterion_text)` for the
    acceptance criterion that validates it. Attaching it is what lets a reviewer
    read the rule as a criterion and, by editing or affirming it, promote its
    grade (S-19). Without it the promotion path exists and can never fire.

    `authors` maps element id -> the identity that proposed it, and is what makes
    N-10's separation of proposal and approval real rather than latent. The gate
    was implemented from the start but nothing populated the field, so no
    self-approval was ever detectable in the live flow; `overrides.apply_overrides`
    now supplies it for edited elements (spec E-12).
    """
    proposers = authors or {}
    review = ReviewFile(
        version=FILE_VERSION,
        model_id=model.id,
        fingerprint=model_fingerprint(model),
        exported_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    for sid in model.state_ids():
        state = model.states[sid]
        if state.lifecycle_state == APPROVED and not include_approved:
            continue
        review.items.append(ReviewItem(
            kind="state", id=sid, decision=DEFER, current_state=state.lifecycle_state,
            evidence={"name": state.name, "surface": state.surface,
                      "is_initial": state.is_initial},
            name=state.name,
            proposed_by=proposers.get(sid),
        ))

    for tid in model.transition_ids():
        transition = model.transitions[tid]
        if transition.implementation_status == PLANNED:
            continue  # nothing to approve; it does not exist yet (spec P-11)
        if transition.lifecycle_state == APPROVED and not include_approved:
            continue
        review.items.append(ReviewItem(
            kind="transition", id=tid, decision=DEFER,
            current_state=transition.lifecycle_state,
            evidence={
                # G1 asks a person whether this behaviour is right. Presenting it
                # as `Ready / GET /{id} / NoContent204` asks them to judge an
                # implementation detail; `rule` states the same fact in the
                # Given/When/Then a reviewer can actually assess (SP-3, R11).
                # The tuple is kept beside it -- the exact recovered condition
                # stays authoritative (T-5).
                # State NAMES, never ids: a landed id carries its model
                # namespace (`records-api::Ready`), which is storage
                # bookkeeping and has no business meaning.
                "rule": (
                    f"Given the system is "
                    f"{model.states[transition.source].name if transition.source in model.states else transition.source}"
                    f", when {transition.trigger}"
                    + (f", and {transition.guard}" if transition.guard else "")
                    + f", then the result is "
                    f"{model.states[transition.target].name if transition.target in model.states else transition.target}"),
                "from": transition.source, "trigger": transition.trigger,
                "to": transition.target, "guard": transition.guard or None,
                "implementation_status": transition.implementation_status,
            },
            proposed_by=proposers.get(tid),
            criterion_id=(criteria or {}).get(tid, (None, None))[0],
            criterion_text=(criteria or {}).get(tid, (None, None))[1],
        ))
    return review


def promotion_for(item: "ReviewItem", drafted_text: str | None) -> str | None:
    """What grade this decision moves the item's criterion to (spec S-19).

    **Approving a rule is not the same as vouching for it.** A reviewer who reads
    a drafted criterion, agrees it describes the code, and clicks approve has
    confirmed a *match*; they have not said the behaviour is what the business
    wants. Treating that as intent would let a rubber-stamp manufacture the very
    thing S-19 exists to protect -- and on the pilot estate, where every criterion
    was drafted from the code, it would have promoted all of them at a stroke.

    Two things promote, and both require the reviewer to have done something a
    rubber-stamp does not:

      * **an edit** -- the text differs from what was drafted, so a person put
        their own words in;
      * **an explicit affirmation** -- `affirmed_as_intent`, a separate act from
        approving, meaning "I have checked this against what we intend".

    Returns None when nothing changes, which is the common and correct case.
    """
    from metis_mcp.reconciliation.matching import HUMAN_CONFIRMED

    if item.decision != APPROVE or not item.criterion_id:
        return None
    edited = (item.criterion_text is not None
              and drafted_text is not None
              and item.criterion_text.strip() != drafted_text.strip())
    if edited or item.affirmed_as_intent:
        return HUMAN_CONFIRMED
    return None


@dataclass
class AuditRecord:
    """What was decided, by whom, and against which evidence (spec N-13)."""

    model_id: str
    fingerprint: str
    reviewer: str
    decided_at: str
    kind: str
    element_id: str
    decision: str
    from_state: str
    to_state: str
    rationale: str = ""
    self_approval: bool = False
    # S-19: which grade this decision moved a criterion to, if any.
    criterion_id: str | None = None
    criterion_promoted_to: str | None = None
    # The reviewer's own text. An edit is what EARNS `human_confirmed`, so the
    # record has to carry the words that earned it -- otherwise the promotion is
    # unauditable against its own cause (N-14), and a caller wanting to persist
    # the new text has to reach back into the review file to find it.
    criterion_text: str | None = None


@dataclass
class ApplyResult:
    applied: list[AuditRecord] = field(default_factory=list)
    refused: list[tuple[str, str]] = field(default_factory=list)  # (element id, reason)
    blocked_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.blocked_reason is None


def apply(model: Model, review: ReviewFile,
          require_distinct_approver: bool = True,
          drafted: dict[str, str] | None = None) -> ApplyResult:
    """Apply decisions to the model in place, refusing on stale or unsafe input.

    Blocks the whole file rather than partially applying when the evidence no
    longer matches: a half-applied review leaves nobody able to say what was
    actually decided.
    """
    result = ApplyResult()

    if review.version != FILE_VERSION:
        result.blocked_reason = (
            f"unknown review-file version {review.version!r}; expected {FILE_VERSION}"
        )
        return result

    if review.model_id != model.id:
        result.blocked_reason = (
            f"review file is for model {review.model_id!r}, not {model.id!r}"
        )
        return result

    current = model_fingerprint(model)
    if review.fingerprint != current:
        # Spec N-14: an approval must be auditable against what the reviewer saw.
        result.blocked_reason = (
            f"the model has changed since this file was exported "
            f"(exported against {review.fingerprint}, now {current}). "
            f"Re-export and review again — decisions made against different "
            f"evidence must not be applied."
        )
        return result

    if not review.reviewer.strip():
        result.blocked_reason = "no reviewer identity set; every decision records who made it"
        return result

    decided_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # What was DRAFTED, so an edit can be told from an untouched approval (S-19).
    drafted = drafted or {}

    for item in review.items:
        if item.decision not in _VALID_DECISIONS:
            result.refused.append((item.id, f"unknown decision {item.decision!r}"))
            continue
        if item.decision == DEFER:
            continue
        if item.decision == REJECT and not item.rationale.strip():
            result.refused.append((item.id, "reject requires a rationale"))
            continue

        self_approval = bool(item.proposed_by) and item.proposed_by == review.reviewer
        if self_approval and item.decision == APPROVE:
            if require_distinct_approver and not review.allow_self_approval:
                # Spec N-10: the reviewer gate is meaningless if the proposer can
                # approve their own proposal.
                result.refused.append((
                    item.id,
                    f"{review.reviewer} proposed this element and may not approve it "
                    f"(set allow_self_approval to override; the override is recorded)",
                ))
                continue

        target = APPROVED if item.decision == APPROVE else REJECTED
        before = _apply_one(model, item, target)
        if before is None:
            result.refused.append((item.id, f"no such {item.kind} in the model"))
            continue

        promoted = promotion_for(item, drafted.get(item.criterion_id or ""))
        result.applied.append(AuditRecord(
            model_id=model.id, fingerprint=review.fingerprint, reviewer=review.reviewer,
            decided_at=decided_at, kind=item.kind, element_id=item.id,
            decision=item.decision, from_state=before, to_state=target,
            rationale=item.rationale, self_approval=self_approval,
            criterion_id=item.criterion_id, criterion_promoted_to=promoted,
            criterion_text=item.criterion_text,
        ))

    return result


def _apply_one(model: Model, item: ReviewItem, target: str) -> str | None:
    """Mutate one element's lifecycle. Returns its previous state, or None."""
    if item.kind == "state":
        state = model.states.get(item.id)
        if state is None:
            return None
        before = state.lifecycle_state
        # State is frozen; `replace` it. A naming decision applies here too.
        #
        # **Never a re-construction naming fields one by one** — see the same
        # note in `review/state.py:overlay`. Enumerating the fields dropped every
        # one not named, so deciding on an element destroyed its recovered facts:
        # `outcome_status=200` came back `None`. It was invisible while the
        # approval fingerprint hashed exactly the fields the enumeration happened
        # to name; widening it to cover what a generated test asserts made
        # `review apply` record a hash taken from a mutilated model that no
        # loader could reproduce, staling every approval permanently.
        model.states[item.id] = replace(
            state, name=item.name or state.name, lifecycle_state=target)
        return before

    if item.kind == "transition":
        transition = model.transitions.get(item.id)
        if transition is None:
            return None
        before = transition.lifecycle_state
        model.transitions[item.id] = replace(transition, lifecycle_state=target)
        return before

    return None


# ---------------------------------------------------------------------------
# The other three decisions (§9.1 points 3, 4 and 5)
# ---------------------------------------------------------------------------
#
# **These had a screen and no way to record an answer.** `evidence.py` builds
# `resolve_divergence_screen`, `confirm_match_screen` and `decide_drift_screen`,
# each refusing to render without its evidence (N-4); `roles.py` declares a
# capability for each. What did not exist was anywhere to put the outcome, so
# `metis divergence` reported and nothing accepted a resolution, matching
# proposed and nothing accepted a confirmation, and drift classified and nothing
# accepted a decision.
#
# They live here rather than in the UI for N-1's reason, which the approval path
# already demonstrates: `review_ui` calls `apply` rather than mutating the model
# itself, precisely so no surface has its own weaker definition of what a
# decision does. A second implementation behind the web handler is how two
# surfaces drift into disagreeing.
#
# Each returns the same `ApplyResult` the approval path does, so a caller
# handles one shape, and each **refuses rather than guesses** on unknown input.

ACCEPT_CODE = "accept_code"
ACCEPT_AC = "accept_ac"
DIVERGENCE_CHOICES = (ACCEPT_CODE, ACCEPT_AC)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stamp(actor: str, fingerprint: str) -> dict:
    return {"decided_by": actor, "decided_at": _now(),
            "evidence_fingerprint": fingerprint}


def _record(state, kind: str, element_id: str, outcome: str, rationale: str,
            actor: str, fingerprint: str) -> AuditRecord:
    """One `AuditRecord`, shaped as the approval path shapes them.

    `from_state`/`to_state` carry the decision itself rather than a lifecycle:
    these three decisions do not move an element between lifecycle states, and
    leaving the fields empty would make the record unreadable beside the
    approvals it sits with in one audit list.
    """
    return AuditRecord(
        model_id=getattr(state, "model_id", ""),
        fingerprint=fingerprint,
        reviewer=actor,
        decided_at=_now(),
        kind=kind,
        element_id=element_id,
        decision=outcome,
        from_state="proposed",
        to_state=outcome,
        rationale=rationale,
    )


def resolve_divergence(state, element_id: str, choice: str, rationale: str,
                       actor: str = "", fingerprint: str = "") -> ApplyResult:
    """Record which side of a divergence a human accepted (S-11).

    **A rationale is required**, and that is not politeness. S-10 says neither
    side wins automatically: one of "the code is wrong" and "the requirement is
    stale" is right, and no rule Métis could apply decides which. A resolution
    with no reason recorded is that precedence rule, written down after the fact
    and attributed to a person who never gave one.
    """
    from metis_mcp.review.state import DivergenceResolution

    result = ApplyResult()
    if choice not in DIVERGENCE_CHOICES:
        result.blocked_reason = (
            f"unknown resolution {choice!r}; expected one of "
            f"{', '.join(DIVERGENCE_CHOICES)}. Neither side wins automatically "
            f"(S-10), so there is no default to fall back on.")
        return result
    if not rationale.strip():
        result.blocked_reason = (
            "a divergence resolution needs a reason (S-11). Recording only the "
            "outcome makes the choice indistinguishable from a precedence rule "
            "S-10 forbids.")
        return result

    state.divergences[element_id] = DivergenceResolution(
        choice=choice, rationale=rationale.strip(), **_stamp(actor, fingerprint))
    result.applied.append(_record(state, "divergence", element_id, choice,
                                  rationale.strip(), actor, fingerprint))
    return result


def confirm_match(state, ac_id: str, transition_id: str, confirmed: bool,
                  rationale: str = "", actor: str = "",
                  fingerprint: str = "") -> ApplyResult:
    """Confirm or reject a proposed AC-to-transition match (X-18).

    **A rejection is stored, not deleted.** An unconfirmed proposal and one a
    human considered and refused are different states, and collapsing them means
    the same rejected candidate returns looking new on every subsequent run --
    which trains a reviewer to stop reading them.
    """
    from metis_mcp.review.state import MatchConfirmation

    result = ApplyResult()
    if not ac_id or not transition_id:
        result.blocked_reason = "a match needs both an acceptance criterion and a transition"
        return result

    key = f"{ac_id}->{transition_id}"
    state.matches[key] = MatchConfirmation(
        ac_id=ac_id, transition_id=transition_id, confirmed=bool(confirmed),
        rationale=rationale.strip(), **_stamp(actor, fingerprint))
    result.applied.append(_record(
        state, "match", key, "confirmed" if confirmed else "rejected",
        rationale.strip(), actor, fingerprint))
    return result


def decide_drift(state, case_id: str, resolution: str, rationale: str = "",
                 actor: str = "", fingerprint: str = "") -> ApplyResult:
    """Record what to do about one drifted published case (T-14).

    `resolution` is validated against drift's own action vocabulary, so this
    cannot record a verb the publisher does not implement -- a decision nothing
    can carry out is worse than no decision, because it reads as settled.

    **T-16: `obsolete` deprecates and never deletes.** That is enforced by the
    action set rather than restated here: there is no delete action to choose.
    """
    from metis_mcp.publishing.drift import (
        NO_ACTION,
        PROPOSE_CREATE,
        PROPOSE_DEPRECATE,
        PROPOSE_NOTHING,
        PROPOSE_UPDATE,
    )
    from metis_mcp.review.state import DriftDecision

    # The publisher's own vocabulary, imported by name rather than read out of
    # its private default map: what a reviewer may CHOOSE and what drift
    # proposes by default are different questions, and coupling them would mean
    # a change to one silently changed the other.
    permitted = (NO_ACTION, PROPOSE_CREATE, PROPOSE_UPDATE,
                 PROPOSE_DEPRECATE, PROPOSE_NOTHING)
    result = ApplyResult()
    if resolution not in permitted:
        result.blocked_reason = (
            f"unknown drift resolution {resolution!r}; expected one of "
            f"{', '.join(permitted)}")
        return result
    if not case_id:
        result.blocked_reason = "a drift decision needs the case it is about"
        return result

    state.drift[case_id] = DriftDecision(
        case_id=case_id, resolution=resolution, rationale=rationale.strip(),
        **_stamp(actor, fingerprint))
    result.applied.append(_record(state, "drift", case_id, resolution,
                                  rationale.strip(), actor, fingerprint))
    return result


def format_audit(records: list[AuditRecord]) -> str:
    if not records:
        return "No decisions applied."
    lines = [f"{len(records)} decision(s) applied:"]
    for r in records:
        flag = "  [SELF-APPROVED]" if r.self_approval else ""
        lines.append(
            f"  {r.decided_at}  {r.reviewer}  {r.kind} {r.element_id}: "
            f"{r.from_state} -> {r.to_state}{flag}"
        )
        if r.rationale:
            lines.append(f"      rationale: {r.rationale}")
    lines.append("")
    lines.append(f"  evidence fingerprint: {records[0].fingerprint}")
    return "\n".join(lines)
