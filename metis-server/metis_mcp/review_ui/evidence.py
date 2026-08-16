"""
Per-decision evidence assembly (application spec §9.1, §9.3; N-3, N-4, N-5).

**§9.1 is the risk this module addresses.** The specification contains six human
decision points, and because nothing auto-promotes (F-8), a stalled gate means no
output at all. The interface is therefore not presentation; it is throughput.

**N-3** states, per decision, what must be on screen to decide without leaving it.
**N-4** is the rule that makes N-3 more than a wish: *a decision screen that
cannot show its required evidence blocks the decision* rather than presenting a
partial view. Approving without evidence is the failure the gate exists to
prevent, so an incomplete screen is a refusal, not a degraded experience.

This module is pure. It assembles what a screen must show and reports what it
cannot, leaving rendering to `view.py` and transport to `server.py` -- the same
planner/writer split the rest of the codebase uses, and for the same reason: the
interesting rule (N-4) becomes provable without a browser.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from metis_mcp.mbt.model import APPROVED, PLANNED, Model
from metis_mcp.mbt.validation import ValidationResult
from metis_mcp.review.roles import (
    APPROVE_MODEL,
    CONFIRM_MATCH,
    CONFIRM_PUBLICATION,
    DECIDE_DRIFT,
    NAME_STATE,
    RESOLVE_DIVERGENCE,
    Identity,
)

# The six decision points of §9.1, in that order.
DECISIONS = (APPROVE_MODEL, NAME_STATE, RESOLVE_DIVERGENCE, CONFIRM_MATCH,
             DECIDE_DRIFT, CONFIRM_PUBLICATION)

# N-3's table, as data. Each entry is what the screen MUST show; anything absent
# blocks the decision (N-4).
REQUIRED_EVIDENCE: dict[str, tuple[str, ...]] = {
    APPROVE_MODEL: ("machine", "validation_findings", "reconciliation_gaps",
                    "element_sources", "unnamed_states"),
    NAME_STATE: ("observable_signature", "ac_candidates", "code_candidates",
                 "sibling_names"),
    RESOLVE_DIVERGENCE: ("code_side", "ac_side", "blocked_paths", "implications"),
    CONFIRM_MATCH: ("ac_text", "transition_tuple", "code_anchor", "why_proposed"),
    DECIDE_DRIFT: ("three_way_comparison", "drift_class", "what_would_change"),
    CONFIRM_PUBLICATION: ("draft_content", "target", "dry_run_payload"),
}


class EvidenceMissing(Exception):
    """Raised when a decision is attempted without its required evidence (N-4)."""


@dataclass
class Screen:
    """One decision screen's assembled evidence."""

    decision: str
    element_id: str
    evidence: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def can_decide(self) -> bool:
        """N-4. False means the screen refuses the decision, not that it degrades."""
        return not self.missing

    @property
    def blocked_reason(self) -> str:
        if self.can_decide:
            return ""
        return (f"cannot decide {self.decision} for {self.element_id}: missing "
                f"{', '.join(sorted(self.missing))}. A decision screen that cannot "
                f"show its evidence blocks the decision rather than presenting a "
                f"partial view — approving without evidence is the failure the gate "
                f"exists to prevent (N-4)")

    def require(self) -> None:
        if not self.can_decide:
            raise EvidenceMissing(self.blocked_reason)


def _screen(decision: str, element_id: str, provided: dict,
            notes: list[str] | None = None) -> Screen:
    required = REQUIRED_EVIDENCE[decision]
    # Present-but-empty is NOT missing: "no validation findings" and "findings not
    # computed" are different facts, and conflating them would block a clean model.
    missing = [name for name in required if name not in provided]
    return Screen(decision=decision, element_id=element_id,
                  evidence={k: provided[k] for k in required if k in provided},
                  missing=missing, notes=list(notes or ()))


# --------------------------------------------------------------------------
# 1. Approve a model
# --------------------------------------------------------------------------

def approve_model_screen(model: Model, validation: ValidationResult | None = None,
                         reconciliation=None, element_sources: dict | None = None
                         ) -> Screen:
    """N-3: the machine, all validation findings, reconciliation gaps **both
    directions**, per-element source, and every unnamed state."""
    provided: dict = {"machine": {
        "id": model.id,
        "states": [{"id": s.id, "name": s.name, "surface": s.surface,
                    "is_initial": s.is_initial, "lifecycle_state": s.lifecycle_state}
                   for s in (model.states[i] for i in model.state_ids())],
        "transitions": [{"id": t.id, "from": t.source, "trigger": t.trigger,
                         "to": t.target, "guard": t.guard,
                         "implementation_status": t.implementation_status,
                         "lifecycle_state": t.lifecycle_state}
                        for t in (model.transitions[i] for i in model.transition_ids())],
    }}

    if validation is not None:
        provided["validation_findings"] = [
            {"check": f.check, "severity": f.severity,
             "elements": list(f.element_ids), "detail": f.detail, "remedy": f.remedy}
            for f in validation.findings]

    if reconciliation is not None:
        # F-5: both directions, never merged into one number.
        provided["reconciliation_gaps"] = {
            "unspecified_behaviour": [g.detail for g in reconciliation.unspecified_behaviour],
            "unimplemented_or_unmodelled": [g.detail for g in reconciliation.unimplemented],
            "note": "two gap types, never one number (F-5)",
        }

    if element_sources is not None:
        provided["element_sources"] = dict(element_sources)

    # Always computable from the model itself, so never a reason to block.
    provided["unnamed_states"] = [
        s.id for s in model.states.values() if not s.name.strip() or s.name == s.id]

    notes = []
    if validation is not None and not validation.is_valid():
        notes.append("M-18: this model is not well-formed. Approving it will not "
                     "make generation succeed — the validation gate is separate.")
    return _screen(APPROVE_MODEL, model.id, provided, notes)


# --------------------------------------------------------------------------
# 2. Name a state
# --------------------------------------------------------------------------

def name_state_screen(model: Model, state_id: str, ac_candidates: list | None = None,
                      code_candidates: list | None = None) -> Screen:
    """N-3: the raw observable signature, tier-1 and tier-2 candidates, and the
    names already used by sibling states.

    **X-11's circularity guard applies here, and the screen says so.** Picking a
    name from the AC vocabulary is tier 1 of X-7 and is *not* evidence that the
    two models agree.
    """
    state = model.states.get(state_id)
    if state is None:
        return Screen(decision=NAME_STATE, element_id=state_id,
                      missing=list(REQUIRED_EVIDENCE[NAME_STATE]),
                      notes=[f"{state_id} is not in this model"])

    provided = {
        "observable_signature": {"id": state.id, "surface": state.surface,
                                 "current_name": state.name},
        "sibling_names": sorted(s.name for s in model.states.values()
                                if s.id != state_id and s.surface == state.surface),
    }
    if ac_candidates is not None:
        provided["ac_candidates"] = list(ac_candidates)
    if code_candidates is not None:
        provided["code_candidates"] = list(code_candidates)

    return _screen(NAME_STATE, state_id, provided, notes=[
        "X-11: naming this state from the AC vocabulary is NOT evidence that the "
        "code model and the AC model agree. Naming alignment and semantic "
        "agreement are recorded as separate facts (X-12)."])


# --------------------------------------------------------------------------
# 3. Resolve a divergence
# --------------------------------------------------------------------------

def resolve_divergence_screen(element_id: str, code_side: dict | None,
                              ac_side: dict | None, blocked_paths: list | None) -> Screen:
    """N-3: both sides with full anchors, the paths currently blocked, and what
    each choice implies.

    S-10: neither side wins automatically. The screen presents both and states the
    implication of each; it never marks one as recommended, because a precedence
    rule would silently decide which of a defect and a stale requirement is right.
    """
    provided: dict = {}
    if code_side is not None:
        provided["code_side"] = dict(code_side)
    if ac_side is not None:
        provided["ac_side"] = dict(ac_side)
    if blocked_paths is not None:
        provided["blocked_paths"] = list(blocked_paths)
        provided["implications"] = {
            "accept_code": "the criterion is stale; update the requirement",
            "accept_ac": "the implementation is wrong; this is a defect",
            "note": "neither side wins automatically (S-10); the resolution is "
                    "recorded with who and why (S-11)",
        }
    return _screen(RESOLVE_DIVERGENCE, element_id, provided)


# --------------------------------------------------------------------------
# 4. Confirm a match
# --------------------------------------------------------------------------

def confirm_match_screen(model: Model, ac_id: str, ac_text: str, transition_id: str,
                         proposal=None, code_anchor: str = "") -> Screen:
    """N-3: the AC text, the transition's full tuple, the code anchor, and **why
    it was proposed** — which pre-filter evidence matched.

    X-17: the pre-filter narrows without deciding. `why_proposed` is shown so a
    reviewer can see that a match rests on, say, a route and a status rather than
    on wording similarity — which is never sufficient.
    """
    transition = model.transitions.get(transition_id)
    provided: dict = {"ac_text": ac_text}
    if transition is not None:
        provided["transition_tuple"] = {
            "id": transition.id, "from": transition.source, "trigger": transition.trigger,
            "to": transition.target, "guard": transition.guard or None}
    if code_anchor:
        provided["code_anchor"] = code_anchor
    if proposal is not None:
        candidate = next((c for c in proposal.candidates
                          if c.transition_id == transition_id), None)
        provided["why_proposed"] = {
            "evidence": dict(candidate.evidence) if candidate else {},
            "strength": candidate.strength if candidate else 0,
            "ambiguous": proposal.is_ambiguous,
            "note": proposal.note or "",
        }
    notes = []
    if proposal is not None and proposal.is_ambiguous:
        notes.append("candidates tie on evidence — a human decides (X-17)")
    return _screen(CONFIRM_MATCH, f"{ac_id}->{transition_id}", provided, notes)


# --------------------------------------------------------------------------
# 5. Decide a drift item
# --------------------------------------------------------------------------

def decide_drift_screen(item, published_content: str = "",
                        last_generated: str = "", newly_generated: str = "") -> Screen:
    """N-3: the three-way comparison with its class, and exactly what would change.

    T-15: a `manually_edited` item proposes nothing. The screen carries that as a
    note so a reviewer is not offered an update that would destroy real work.
    """
    provided = {
        "drift_class": item.drift_class,
        "what_would_change": {"action": item.action, "diff": list(item.diff),
                              "detail": item.detail},
        "three_way_comparison": {
            "last_generated": last_generated,
            "currently_published": published_content,
            "newly_generated": newly_generated,
        },
    }
    notes = []
    if item.drift_class == "manually_edited":
        notes.append("T-15: this case was edited by hand. Nothing is proposed, and "
                     "regeneration will never overwrite it. Decide it explicitly.")
    return _screen(DECIDE_DRIFT, item.case_id, provided, notes)


# --------------------------------------------------------------------------
# 6. Confirm publication
# --------------------------------------------------------------------------

def confirm_publication_screen(batch, dry_run_payload: list | None = None,
                               target: str = "") -> Screen:
    """N-3: the full draft content for the whole batch, the target, and the payload.

    N-5: batch operations are supported, **batch blindness is not** — the screen
    enumerates every operation. An "approve all" that does not list its contents
    is prohibited.
    """
    provided = {
        "draft_content": [
            {"action": op.action, "case_id": op.case_id,
             "published_id": op.published_id or None,
             "name": op.payload.get("name", ""),
             "steps": op.payload.get("steps", [])}
            for op in batch.operations],
        "target": target or "dry-run (no external call — C3, T-21)",
    }
    if dry_run_payload is not None:
        provided["dry_run_payload"] = list(dry_run_payload)

    notes = [f"one decision covers all {batch.size} operation(s) (T-19), and every "
             f"one is listed above (N-5)"]
    if batch.withheld:
        notes.append(f"{len(batch.withheld)} case(s) WITHHELD and not in this batch — "
                     f"see the withheld list; the batch you approve is only what is "
                     f"shown")
    return _screen(CONFIRM_PUBLICATION, batch.model_id, provided, notes)


# --------------------------------------------------------------------------
# N-5 : batch decisions, without batch blindness
# --------------------------------------------------------------------------

@dataclass
class BatchDecision:
    decision: str
    screens: list[Screen]

    @property
    def enumerated(self) -> list[str]:
        return [s.element_id for s in self.screens]

    @property
    def blocked(self) -> list[Screen]:
        return [s for s in self.screens if not s.can_decide]

    @property
    def can_decide(self) -> bool:
        return bool(self.screens) and not self.blocked


def batch(decision: str, screens: list[Screen]) -> BatchDecision:
    """Group screens for one decision (spec N-5, T-19).

    Every member is enumerable, and **one blocked member blocks the batch**. A
    batch that silently dropped its unshowable members would be exactly the
    "approve all" N-5 prohibits, with the evidence gap hidden rather than fixed.
    """
    return BatchDecision(decision=decision, screens=list(screens))


def permitted(identity: Identity, decision: str) -> bool:
    """Whether this identity may take this decision at all (spec N-9)."""
    return identity.can(decision)


def format_screen(screen: Screen) -> str:
    lines = [f"{screen.decision} — {screen.element_id}"]
    if not screen.can_decide:
        lines += ["", f"  BLOCKED: {screen.blocked_reason}"]
        return "\n".join(lines)
    for name in REQUIRED_EVIDENCE[screen.decision]:
        value = screen.evidence.get(name)
        summary = (f"{len(value)} item(s)" if isinstance(value, (list, dict))
                   else str(value))
        lines.append(f"  {name:<24} {summary}")
    for note in screen.notes:
        lines.append(f"  ! {note}")
    return "\n".join(lines)
