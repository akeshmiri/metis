"""
Roles and the audit record (application spec §9.6, §9.7; N-9..N-15, A-26, A-27).

Five roles, each a superset of the one before it -- except that **Publisher is not
above Reviewer by accident**. N-12 separates publication from review because it
writes to a system outside Métis's control and is the least reversible action.
In a small team one person may hold both, but the *actions* stay separately
logged, so "who approved this" and "who sent it" are always answerable
independently.

**N-10 is the load-bearing rule**, and O-4a settles it for this deployment:
enforced, not overridden. The identity that proposed a model element may not
approve it. N-11's override exists for a team with no second reviewer, and every
use of it is recorded as a self-approval and visible in the audit view (A-27) --
the override is visible, never silent.

**N-13/N-14 -- an audit record carries the evidence presented, not merely the
outcome.** Without it a later reader cannot distinguish a careless approval from
a reasonable decision made on then-available information. That is why every
record here stores the evidence fingerprint and the evidence itself.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

VIEWER = "viewer"
CONTRIBUTOR = "contributor"
REVIEWER = "reviewer"
PUBLISHER = "publisher"
ADMIN = "admin"

ROLES = (VIEWER, CONTRIBUTOR, REVIEWER, PUBLISHER, ADMIN)

# Capabilities, named after the six decision points of §9.1 plus the actions
# that produce material for them.
READ = "read"
PROPOSE = "propose"          # run extraction/mining, generate paths, render drafts
APPROVE_MODEL = "approve_model"
NAME_STATE = "name_state"
RESOLVE_DIVERGENCE = "resolve_divergence"
CONFIRM_MATCH = "confirm_match"
DECIDE_DRIFT = "decide_drift"
CONFIRM_PUBLICATION = "confirm_publication"
ADMINISTER = "administer"

_REVIEWER_CAPABILITIES = frozenset({
    APPROVE_MODEL, NAME_STATE, RESOLVE_DIVERGENCE, CONFIRM_MATCH, DECIDE_DRIFT,
})

CAPABILITIES: dict[str, frozenset[str]] = {
    VIEWER: frozenset({READ}),
    CONTRIBUTOR: frozenset({READ, PROPOSE}),
    REVIEWER: frozenset({READ, PROPOSE}) | _REVIEWER_CAPABILITIES,
    PUBLISHER: frozenset({READ, PROPOSE, CONFIRM_PUBLICATION}) | _REVIEWER_CAPABILITIES,
    ADMIN: frozenset({READ, PROPOSE, CONFIRM_PUBLICATION, ADMINISTER})
           | _REVIEWER_CAPABILITIES,
}


class NotPermitted(PermissionError):
    """Raised when an identity lacks the capability for an action."""


@dataclass(frozen=True)
class Identity:
    """Who is acting. Required from the first release (spec O-4c).

    Not deferrable: an audit trail cannot be reconstructed retrospectively, so a
    system that starts without identity can never acquire a truthful history of
    the period before it was added.
    """

    name: str
    role: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("an identity has a name (N-13)")
        if self.role not in ROLES:
            raise ValueError(f"unknown role {self.role!r}; expected one of {ROLES}")

    @property
    def capabilities(self) -> frozenset[str]:
        return CAPABILITIES[self.role]

    def can(self, capability: str) -> bool:
        return capability in self.capabilities


def require(identity: Identity, capability: str) -> None:
    """Refuse an action the role does not carry, naming who may do it."""
    if identity.can(capability):
        return
    permitted = sorted(r for r in ROLES if capability in CAPABILITIES[r])
    raise NotPermitted(
        f"{identity.name} is a {identity.role} and may not {capability}. "
        f"This action requires one of: {', '.join(permitted)}")


# --------------------------------------------------------------------------
# N-10 : proposal separated from approval
# --------------------------------------------------------------------------

@dataclass
class SelfApprovalOutcome:
    permitted: bool
    is_self_approval: bool
    reason: str = ""


def check_self_approval(reviewer: Identity, proposed_by: str | None,
                        allow_self_approval: bool = False) -> SelfApprovalOutcome:
    """Spec N-10/N-11, and O-4a's decision that it is enforced here.

    Returns rather than raises, because the caller needs the `is_self_approval`
    flag **even when it permits the action** -- A-27 requires a permitted
    self-approval to be recorded as one and to appear in the audit view. A bare
    raise-or-proceed would lose that fact exactly where it matters.
    """
    is_self = bool(proposed_by) and proposed_by == reviewer.name
    if not is_self:
        return SelfApprovalOutcome(permitted=True, is_self_approval=False)
    if allow_self_approval:
        return SelfApprovalOutcome(
            permitted=True, is_self_approval=True,
            reason=("self-approval permitted by an explicit override (N-11). "
                    "Recorded as such and visible in the audit view"))
    return SelfApprovalOutcome(
        permitted=False, is_self_approval=True,
        reason=(f"{reviewer.name} proposed this element and may not approve it "
                f"(N-10). The reviewer gate is meaningless if the proposer can "
                f"approve their own proposal"))


# --------------------------------------------------------------------------
# N-13..N-15 : the audit record
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Decision:
    """One recorded decision (spec N-13).

    `evidence` is what was **presented at the time**, not what the graph looks
    like today (N-14). It is stored rather than referenced for that reason: a
    reference would resolve to current state and quietly rewrite history.
    """

    actor: str
    role: str
    capability: str
    element_id: str
    outcome: str
    at: str
    evidence: dict = field(default_factory=dict)
    evidence_fingerprint: str = ""
    rationale: str = ""
    self_approval: bool = False
    surface: str = "cli"


@dataclass
class AuditLog:
    """Append-only (spec N-15). A decision may be superseded, never edited."""

    entries: list[Decision] = field(default_factory=list)

    def append(self, decision: Decision) -> None:
        self.entries.append(decision)

    def for_element(self, element_id: str) -> list[Decision]:
        return [d for d in self.entries if d.element_id == element_id]

    def self_approvals(self) -> list[Decision]:
        """A-27: visible in the audit view, never merely tolerated."""
        return [d for d in self.entries if d.self_approval]

    def by(self, actor: str) -> list[Decision]:
        return [d for d in self.entries if d.actor == actor]

    def to_json_ready(self) -> list[dict]:
        return [asdict(d) for d in self.entries]


def record_decision(log: AuditLog, identity: Identity, capability: str,
                    element_id: str, outcome: str, evidence: dict,
                    evidence_fingerprint: str = "", rationale: str = "",
                    self_approval: bool = False, surface: str = "cli") -> Decision:
    """Record a decision with the evidence presented (spec N-13, N-14, A-26).

    **N-1: every surface produces the same record.** `surface` is recorded so a
    decision can be traced to where it was made, but it grants nothing and
    changes nothing -- no surface has a privileged or unlogged path.
    """
    decision = Decision(
        actor=identity.name, role=identity.role, capability=capability,
        element_id=element_id, outcome=outcome,
        at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        evidence=dict(evidence), evidence_fingerprint=evidence_fingerprint,
        rationale=rationale, self_approval=self_approval, surface=surface,
    )
    log.append(decision)
    return decision


def format_audit(log: AuditLog) -> str:
    lines = [f"Audit — {len(log.entries)} decision(s)"]
    for d in log.entries[:20]:
        flag = "  [SELF-APPROVED]" if d.self_approval else ""
        lines.append(f"  {d.at}  {d.actor} ({d.role})  {d.capability}  "
                     f"{d.element_id} -> {d.outcome}{flag}")
        if d.evidence_fingerprint:
            lines.append(f"      evidence presented: {d.evidence_fingerprint}")
        if d.rationale:
            lines.append(f"      {d.rationale}")
    self_approved = log.self_approvals()
    if self_approved:
        lines += ["", f"  {len(self_approved)} SELF-APPROVAL(S) — N-10 was overridden:"]
        for d in self_approved:
            lines.append(f"    {d.actor} approved {d.element_id}, which they proposed")
        lines.append("  The override is visible, not silent (N-11, A-27).")
    return "\n".join(lines)
