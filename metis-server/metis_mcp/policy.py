"""
The write policy: the single place a write through the agent surface is
permitted, refused, or recorded (spec N-1, N-9..N-15, O-4c).

**The write half of the agent surface, and the change to N-8.** N-8 said no
decision may be taken here, because a decision needs the evidence presentation
N-3 specifies and a chat session cannot provide it. That prohibition is lifted
by an explicit product decision; what it was protecting is not.

    policy.py   this module — the one place a write is permitted or refused
    write.py    authoring; everything it writes lands at Quarantine (S-4)
    decide.py   the two gates, and the only module that may write Approved
    flow.py     workflow runs, which halt at those gates as the CLI does
    read.py     queries the read surface did not have

The rule the split exists to keep: **a tool may write, and a tool may not decide
quietly.** Authoring is cheap, reversible, and lands unapproved. Deciding is
none of those, so it costs an identity, the evidence that identity was shown,
and a literal word — the same three things the CLI and the review UI cost.

**Every write tool calls `authorise()` first and `record()` after.** Not by
convention — `test_mcp_write_policy.py` asserts it over the module source, the
same way `test_mcp_server.py` used to assert that no write path was importable
at all. A rule swapped for a weaker rule with no test is how this becomes an
ordinary tool.

Three things this enforces, and one it deliberately does not:

  * **Mode.** `METIS_MCP_WRITE` is `off` (today's read-only surface, and the
    default), `author` (may land at Quarantine, may not decide), or `full`
    (may also pass the gates). Off is the default because a surface that starts
    able to write is one nobody chose to make writable.
  * **Capability.** Checked against `review.roles`, the same table the CLI and
    the review UI use. No surface has a privileged path (N-1).
  * **Audit.** `roles.record_decision(..., surface="mcp")` — the parameter has
    existed since the audit record was written, and its docstring already
    promised that every surface produces the same record. This is the surface
    it was promising for.

**What it does not do is authenticate.** `actor` and `role` are asserted by the
caller. That is the same trust the review UI places in its identity header, and
it is honest for a localhost tool and wrong for anything else — `describe_policy`
says so to any agent that asks, rather than leaving it to be discovered.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# **Imported inside the functions, not here, and it is load-bearing.**
# `from metis_mcp.review.roles import ...` executes `metis_mcp/review/__init__.py`
# first, which re-exports `review.decisions` -- a write path. `server.py` calls
# `mode()` at import time to decide whether to register anything, so a top-level
# import here would drag a write path into the read-only deployment and turn
# `test_mcp_server.py`'s "no write path is reachable" proof into a lie, for a
# server that cannot write.
#
# The names this module uses from there: APPROVE_MODEL, CONFIRM_PUBLICATION,
# Identity, NotPermitted, ROLES, record_decision, require -- and ReviewState
# plus default_state_path from `review.state`.

WRITE_ENV = "METIS_MCP_WRITE"
IDENTITY_ENV = "METIS_MCP_IDENTITY"      # "name:role"

OFF, AUTHOR, FULL = "off", "author", "full"
MODES = (OFF, AUTHOR, FULL)

# The literal a gate costs. Distinct from publication's own word, on purpose:
# `publish.AFFIRMATIVE` is "publish", and a confirmation typed for one gate must
# not satisfy the other.
APPROVE_LITERAL = "approve"


class WriteDisabled(Exception):
    """Raised when a write is attempted on a surface not configured for it."""


class ConfirmationRefused(Exception):
    """Raised when a gated action is attempted without its literal (G1/G2)."""


def mode() -> str:
    """The configured write mode. An unknown value is a halt, not a default.

    Falling back to `off` would be the safe-looking choice and the wrong one:
    an operator who typed `METIS_MCP_WRITE=ful` would get a surface that refuses
    every write for a reason nothing states.
    """
    value = os.environ.get(WRITE_ENV, OFF).strip().lower() or OFF
    if value not in MODES:
        raise WriteDisabled(
            f"{WRITE_ENV}={value!r} is not one of {', '.join(MODES)}.")
    return value


def may_author() -> bool:
    return mode() in (AUTHOR, FULL)


def may_decide() -> bool:
    return mode() == FULL


@dataclass
class Grant:
    """Permission to perform one write, and the receipt it must produce."""

    identity: "Identity"
    capability: str
    mode: str
    # Populated by `record`; kept so a tool can return what it wrote down.
    recorded: list = field(default_factory=list)


def resolve_identity(actor: str = "", role: str = "") -> "Identity":
    """Who is acting. Explicit arguments beat `METIS_MCP_IDENTITY`.

    There is no anonymous default. O-4c makes identity non-deferrable because an
    audit trail cannot be reconstructed retrospectively: a system that starts
    without one can never acquire a truthful history of the period before it was
    added.
    """
    from metis_mcp.review.roles import ROLES, Identity, NotPermitted

    if not actor:
        configured = os.environ.get(IDENTITY_ENV, "").strip()
        if configured:
            name, _, configured_role = configured.partition(":")
            actor, role = name.strip(), role or configured_role.strip()
    if not actor:
        raise NotPermitted(
            f"this action needs an identity. Pass `actor` and `role`, or set "
            f"{IDENTITY_ENV}=name:role. Roles: {', '.join(ROLES)} (N-13, O-4c).")
    if not role:
        raise NotPermitted(
            f"{actor!r} has no role. Pass `role`, one of: {', '.join(ROLES)}.")
    return Identity(name=actor, role=role)


def authorise(capability: str, actor: str = "", role: str = "") -> Grant:
    """Refuse unless the mode allows it AND the role carries the capability.

    Both checks, in that order, because they fail for different reasons and the
    caller needs to know which: a deployment that is read-only by configuration
    is a different problem from a person who is not a reviewer.
    """
    from metis_mcp.review.roles import APPROVE_MODEL, CONFIRM_PUBLICATION, require

    current = mode()
    gated = capability in (APPROVE_MODEL, CONFIRM_PUBLICATION)

    if current == OFF:
        raise WriteDisabled(
            f"this surface is read-only: {WRITE_ENV} is {OFF!r}. Set it to "
            f"{AUTHOR!r} to land candidates at Quarantine, or {FULL!r} to also "
            f"pass the approval and publication gates.")
    if gated and current != FULL:
        raise WriteDisabled(
            f"{capability} is a gate and {WRITE_ENV} is {current!r}. Authoring "
            f"is permitted; deciding is not. Set {WRITE_ENV}={FULL!r}, or take "
            f"the decision through the review UI or `review apply`.")

    identity = resolve_identity(actor, role)
    require(identity, capability)          # raises NotPermitted, naming who may
    return Grant(identity=identity, capability=capability, mode=current)


def require_confirmation(literal: str, expected: str, action: str) -> None:
    """A gate costs the exact word, in this call (G1/G2, T-18).

    No timeout implies yes, no default yes, and no truthy value: `True`, `"y"`
    and `"yes"` are all refused, because a caller that can pass any of them by
    accident is a caller that can pass them by accident.
    """
    if literal != expected:
        raise ConfirmationRefused(
            f"{action} needs the literal word {expected!r} in this call; got "
            f"{literal!r}. There is no default and no timeout (G1/G2, T-18).")


def record(grant: Grant, state: "ReviewState", element_id: str, outcome: str,
           evidence: dict, fingerprint: str = "", rationale: str = "",
           self_approval: bool = False) -> dict:
    """Append the audit entry, through the function every other surface uses.

    Written into `ReviewState.audit`, which is the durable, append-only home the
    CLI already keeps beside the model (N-15). An in-memory `AuditLog` that
    nothing saves is what `cli ui` shipped with once, and it made every decision
    taken through that surface unauditable.
    """
    from metis_mcp.review.roles import AuditLog, record_decision

    log = AuditLog()
    decision = record_decision(
        log, grant.identity, grant.capability, element_id, outcome,
        evidence=evidence, evidence_fingerprint=fingerprint,
        rationale=rationale, self_approval=self_approval, surface="mcp")
    entry = {
        "actor": decision.actor, "role": decision.role,
        "capability": decision.capability, "element_id": decision.element_id,
        "outcome": decision.outcome, "at": decision.at,
        "evidence_fingerprint": decision.evidence_fingerprint,
        "rationale": decision.rationale,
        "self_approval": decision.self_approval, "surface": decision.surface,
    }
    state.audit.append(entry)
    grant.recorded.append(entry)
    return entry


def audit_state(model_id: str, model_path: str = "") -> tuple["ReviewState", "Path"]:
    """The durable, append-only place this surface writes its audit (N-15).

    Beside the model file when there is one, so the CLI, the review UI and this
    surface all append to the SAME `<model>.review.json` -- N-1 is about one
    record per decision, and two audit files for one model is two histories.
    With no file (a graph-only run) it falls back to `.metis/<model>.review.json`,
    which is where `workflow status` already keeps run records.
    """
    from pathlib import Path

    from metis_mcp.review.state import ReviewState, default_state_path

    path = (default_state_path(model_path) if model_path
            else Path(".metis") / f"{model_id}.review.json")
    state = ReviewState.load(path)
    if not state.model_id:
        state.model_id = model_id
    return state, path


def save_audit(state: "ReviewState", path) -> None:
    from pathlib import Path

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    state.save(path)


def describe() -> dict:
    """What this surface may and may not do, for `describe_policy`."""
    current = mode()
    return {
        "mode": current,
        "may_author": may_author(),
        "may_decide": may_decide(),
        "everything_lands_at": "Quarantine (S-4) — authoring is not approving",
        "gates": {
            "G1": f"approval needs the literal {APPROVE_LITERAL!r}, an identity, "
                  f"and the evidence fingerprint it was decided against",
            "G2": "publication needs the literal 'publish' in the same call; "
                  "the only transport registered is dry-run (C3)",
        },
        "n10": "the identity that proposed an element may not approve it",
        "identity_is_asserted_not_authenticated": (
            "`actor` and `role` are taken from the caller and trusted, exactly "
            "as the review UI trusts its identity header. Honest for a "
            "localhost tool; unacceptable for anything reachable by others."),
        "audit": "every write is recorded with surface='mcp' (N-1)",
    }
