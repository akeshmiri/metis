"""
Publication, and the gate in front of it (application spec §7.7; T-17..T-21,
A-22, A-23).

**T-20 -- one component owns external writes.** No other module calls the
test-management API. That single ownership is what makes T-18 *verifiable*: there
is exactly one place to assert against, and A-22's acceptance test ("withhold
confirmation, assert zero external calls were attempted, against a stub that
records every attempt") is meaningful only because of it.

**T-18 -- no external call without a literal affirmative confirmation in that
run.** No timeout-implies-yes. No default-yes. `Confirmation` cannot be
constructed from a falsy value, an empty string, or a "maybe" -- the type refuses
before the transport is ever reached.

**T-19 -- one decision covers a batch.** A gate per case produces reflexive
approval, which is worse than no gate: it manufactures a record of consent
without the attention that record implies.

**T-21 -- dry-run only in the first release (C3).** The real path is built and
gated; `DryRunTransport` is the only transport registered. A real transport is a
class implementing `Transport`, and the gate in front of it is identical -- which
is the point of building it now rather than bolting it on later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from metis_mcp.publishing.drift import (
    CHANGED,
    MANUALLY_EDITED,
    NEW,
    OBSOLETE,
    PROPOSE_CREATE,
    PROPOSE_DEPRECATE,
    PROPOSE_NOTHING,
    PROPOSE_UPDATE,
    DriftItem,
    DriftReport,
)
from metis_mcp.rendering.test_case import TestCase

# The literal a human must supply. Deliberately a whole word: a single keystroke
# is too easy to supply reflexively, which is what T-19's batch gate exists to
# avoid in the first place.
AFFIRMATIVE = "publish"

CREATE = "create"
UPDATE = "update"
DEPRECATE = "deprecate"

_ACTION_FOR = {PROPOSE_CREATE: CREATE, PROPOSE_UPDATE: UPDATE,
               PROPOSE_DEPRECATE: DEPRECATE}


class ConfirmationRefused(Exception):
    """Raised when publication is attempted without a literal confirmation (T-18)."""


@dataclass(frozen=True)
class Confirmation:
    """A literal affirmative, given in this run, by a named person (spec G2, T-18).

    There is no `Confirmation(True)` and no default instance. Every way of
    obtaining one goes through `confirm()`, which requires the exact word and an
    identity -- so "no timeout implies yes" is a property of the type rather than
    a rule someone has to remember at each call site.
    """

    confirmed_by: str
    literal: str
    at: str
    batch_size: int

    def __post_init__(self) -> None:
        if self.literal != AFFIRMATIVE:
            raise ConfirmationRefused(
                f"confirmation must be the literal word {AFFIRMATIVE!r}; "
                f"got {self.literal!r}. There is no default-yes (T-18)")
        if not self.confirmed_by.strip():
            raise ConfirmationRefused("a confirmation records who gave it (N-13)")


def confirm(literal: str, confirmed_by: str, batch_size: int) -> Confirmation:
    """The only way to obtain a `Confirmation`."""
    return Confirmation(
        confirmed_by=confirmed_by, literal=literal, batch_size=batch_size,
        at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


@dataclass(frozen=True)
class Operation:
    """One intended external write."""

    action: str
    case_id: str
    published_id: str
    payload: dict


@dataclass
class Batch:
    """What T-19's single decision covers. Shown in full before it is decided (T-17)."""

    model_id: str
    operations: list[Operation] = field(default_factory=list)
    withheld: list[tuple[str, str]] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.operations)


def plan_publication(report: DriftReport, cases: list[TestCase],
                     model_id: str = "") -> Batch:
    """Turn a drift report into intended writes. **Pure** -- nothing leaves here.

    Manually-edited cases are withheld with their reason rather than silently
    omitted: an operator must be able to see that four cases were held back and
    why, or the batch they approve is not the batch they think they approved.
    """
    batch = Batch(model_id=model_id or report.model_id)
    by_id = {c.id: c for c in cases}

    for item in report.items:
        if item.action == PROPOSE_NOTHING:
            batch.withheld.append((item.case_id, item.detail))
            continue
        action = _ACTION_FOR.get(item.action)
        if action is None:
            continue
        case = by_id.get(item.case_id)
        batch.operations.append(Operation(
            action=action, case_id=item.case_id,
            published_id=item.published_id,
            payload=_payload(case) if case else {"case_id": item.case_id},
        ))
    return batch


def _payload(case: TestCase) -> dict:
    """Exactly what would be sent. Shown in full before confirmation (T-17)."""
    return {
        "id": case.id,
        "name": case.name,
        "objective": case.objective,
        "labels": list(case.labels),
        "precondition": [
            {"description": s.description, "condition": s.guard_verbatim}
            for s in case.precondition_steps
        ],
        "steps": [{
            "description": case.act_step.description,
            "expected_result": case.act_step.expected_result,
            "condition": case.act_step.guard_verbatim,
        }],
        "data_requirements": [
            {"condition": d.condition, "steps": list(d.steps)}
            for d in case.data_requirements
        ],
    }


class Transport:
    """The only interface through which anything leaves Métis (spec T-20)."""

    name = "abstract"
    is_dry_run = True

    def send(self, operation: Operation) -> str:
        raise NotImplementedError


class DryRunTransport(Transport):
    """Builds and validates the real payload, and makes no network call (T-21, A-23).

    Not a stub standing in for missing work: C3 makes dry-run the *first release's*
    behaviour, and the payload it validates is the one a real transport would send.

    **One real consequence, stated rather than left to be discovered.** Because it
    sends nothing, it never learns a published id, so it cannot populate
    `PublicationLedger.published`. Until a real transport exists, the
    `MANUALLY_EDITED` and `OBSOLETE` drift classes have no live source of published
    content to compare against -- they are fully implemented and tested, but in a
    dry-run-only deployment they will always read zero. That is a property of C3,
    not a gap in §7.6.
    """

    name = "dry-run"
    is_dry_run = True

    def __init__(self) -> None:
        self.attempts: list[Operation] = []

    def send(self, operation: Operation) -> str:
        if not operation.payload.get("id"):
            raise ValueError(f"{operation.case_id}: payload has no id — refusing to send")
        if operation.action in (UPDATE, DEPRECATE) and not operation.published_id:
            raise ValueError(
                f"{operation.case_id}: {operation.action} needs a published id")
        self.attempts.append(operation)
        return f"dry-run:{operation.action}:{operation.case_id}"


@dataclass
class PublishResult:
    ok: bool
    transport: str
    dry_run: bool
    sent: list[str] = field(default_factory=list)
    refused: str = ""
    confirmed_by: str = ""
    withheld: list[tuple[str, str]] = field(default_factory=list)


def publish(batch: Batch, transport: Transport,
            confirmation: Confirmation | None = None) -> PublishResult:
    """The single external-write path (spec T-20).

    The confirmation check happens **before** the transport is touched at all, so
    a withheld confirmation produces zero attempts rather than an attempt that is
    later rolled back. A-22 asserts exactly this against a recording stub.

    A confirmation is also checked against the batch it was given for: approving
    a batch of 3 must not authorise a batch of 30 that was assembled afterwards.
    T-19 gives one decision per batch, not one decision per session.
    """
    if confirmation is None:
        return PublishResult(
            ok=False, transport=transport.name, dry_run=transport.is_dry_run,
            withheld=list(batch.withheld),
            refused=(f"no confirmation given — nothing was sent. Publication requires "
                     f"the literal word {AFFIRMATIVE!r} in this run (T-18, G2)"))

    if confirmation.batch_size != batch.size:
        return PublishResult(
            ok=False, transport=transport.name, dry_run=transport.is_dry_run,
            withheld=list(batch.withheld),
            refused=(f"confirmation was given for {confirmation.batch_size} "
                     f"operation(s), but this batch has {batch.size}. Re-confirm "
                     f"against what is actually being sent (T-19)"))

    sent = []
    for operation in batch.operations:
        sent.append(transport.send(operation))

    return PublishResult(ok=True, transport=transport.name, dry_run=transport.is_dry_run,
                         sent=sent, confirmed_by=confirmation.confirmed_by,
                         withheld=list(batch.withheld))


def format_batch(batch: Batch) -> str:
    """T-17: drafts are shown **in full** before any external action."""
    lines = [f"Publication batch — {batch.model_id}",
             f"  {batch.size} operation(s) would be sent:"]
    for op in batch.operations:
        target = f" -> {op.published_id}" if op.published_id else ""
        lines.append(f"    {op.action:<9} {op.case_id}{target}")
        lines.append(f"      name: {op.payload.get('name', '')}")
        for step in op.payload.get("steps", []):
            lines.append(f"      act:  {step['description']}")
            lines.append(f"      then: {step['expected_result']}")
            if step.get("condition"):
                lines.append(f"      when: {step['condition']}")
    if batch.withheld:
        lines += ["", f"  {len(batch.withheld)} case(s) WITHHELD — not in this batch:"]
        for case_id, reason in batch.withheld:
            lines.append(f"    {case_id}: {reason}")
    lines += ["",
              f"  Nothing has been sent. To send, confirm with the literal word "
              f"{AFFIRMATIVE!r}.",
              "  One decision covers this batch (T-19). There is no default-yes (T-18)."]
    return "\n".join(lines)
