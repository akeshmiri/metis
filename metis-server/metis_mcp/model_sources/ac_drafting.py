"""
Drafting acceptance criteria from an extracted model (spec §4.5, S-19; R5).

**The problem this exists for.** A real estate frequently has no acceptance
criteria at all. The the pilot estate estate has 145 API transitions and 8 criteria that
validate anything — and even those were written after the code. S-3 says a
deployment running only code extraction gets coverage, not correctness, so
without criteria the chain stops permanently at coverage.

Waiting for someone to write 145 criteria from nothing is not a plan. Drafting
them from the extracted behaviour is cheap, complete, and — handled correctly —
the right starting point: it is far easier to disagree with a sentence than to
compose one from a blank page.

**The trap, and the rule that defuses it.** A criterion written from the code,
used to check the code, can only ever report agreement. §4.1 says so; the pilot estate
demonstrates it. So every draft this module produces is stamped `CODE_DERIVED`,
and S-19 keeps that grade out of every correctness claim until a **human edits or
affirms it**. The draft is a prompt for disagreement, not evidence.

That is the whole design:

    drafted here          CODE_DERIVED           documentation; coverage only
    a person edits it     HUMAN_CONFIRMED        intent; may support correctness
    written blind         INDEPENDENTLY_AUTHORED strongest intent

**A draft is deliberately plain.** It states the behaviour in Given/When/Then and
adds nothing — no rationale, no justification, no "this is correct because".
Fluent justification is what makes a fabrication persuasive (S-13), and a draft
that argues for itself is harder to disagree with, which defeats the point.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from metis_mcp.behavior_model import split_conjuncts
from metis_mcp.mbt.model import IMPLEMENTED, Model
from metis_mcp.reconciliation.matching import CODE_DERIVED, AcceptanceCriterion

# The reviewer's job, stated on every draft. Confirming a draft that merely
# restates the code adds nothing; the value is in the edits.
REVIEW_PROMPT = ("Is this what the system SHOULD do? Edit it if not. "
                 "Confirming it unchanged leaves it code_derived (S-19).")

# An acceptance criterion is **atomic**: one condition, one action, one
# validation. A drafted criterion that carried a whole compound guard in its
# `and` clause was not one criterion -- it was several wearing one id, and a
# reviewer could only approve or reject the bundle.
ATOMIC = "atomic"
NOT_DECOMPOSABLE = "not_decomposable"


def decompose_guard(guard: str) -> tuple[tuple[str, ...], str, str]:
    """`(preconditions, deciding_condition, atomicity)` -- GD-2's own split.

    **Not one criterion per conjunct.** That reading is false: from
    `authenticated AND !authorized -> 403`, "when a request is made, and
    authenticated, then 403" claims something the system does not do. Being
    authenticated alone produces no rejection.

    GD-2 already says what the parts mean. A rejection guard is
    `(dimensions 1..k-1 all pass) AND (dimension k fails)`: the prefix is the
    **context the interaction happens in**, and only the last dimension is the
    **condition under test**. So the prefix belongs in the Given, where context
    belongs, and the deciding condition is the criterion's single condition.
    Nothing is dropped -- each part is placed by the role it actually plays.

    Order comes from `split_conjuncts`, which preserves source order, and source
    order is precedence order for a recovered guard (§5.4a).

    Fails closed. A guard containing an `OR` is a disjunction, and deciding which
    branch is the deciding one needs real boolean reasoning (M-17). It is
    returned whole and marked `NOT_DECOMPOSABLE` rather than split on a guess.
    """
    parts = split_conjuncts(guard)
    if parts is None:
        # Either empty -- an unguarded transition, which is atomic already -- or
        # a disjunction this cannot honestly take apart.
        return (), guard.strip(), ATOMIC if not guard.strip() else NOT_DECOMPOSABLE
    return tuple(parts[:-1]), parts[-1], ATOMIC


def _humanise_trigger(trigger: str) -> str:
    """`GET /metric/{id}` -> `a GET request is made to /metric/{id}`.

    Deterministic, and it introduces no word that is not already in the trigger
    or in this template (T-6). Where the trigger is not HTTP-shaped it is used
    verbatim rather than guessed at.
    """
    parts = trigger.split(None, 1)
    if len(parts) == 2 and parts[0].isupper():
        verb, path = parts
        return f"a {verb} request is made to {path}"
    return re.sub(r"[_\-]+", " ", trigger).strip() or "the interaction occurs"


def _humanise_state(name: str) -> str:
    """`NoContent204` -> `NoContent204`. Left alone on purpose.

    A state's business name comes from X-7's cascade, not from a guess made here.
    Rewriting `NoContent204` into "no content is returned" would put words in the
    reviewer's mouth and make the draft read as more settled than it is.
    """
    return name


@dataclass(frozen=True)
class DraftCriterion:
    """One drafted criterion, always `CODE_DERIVED` (spec S-19), and atomic.

    `and_guard` holds the **single** condition under test. Everything the guard
    required in order to reach that condition sits in `preconditions`, rendered
    into the Given where context belongs (GD-2, `decompose_guard`).
    """

    id: str
    transition_id: str
    given: str
    when: str
    and_guard: str
    then: str
    model_id: str
    anchor: str = ""
    preconditions: tuple[str, ...] = ()
    atomicity: str = ATOMIC

    @property
    def provenance(self) -> str:
        return CODE_DERIVED

    @property
    def is_atomic(self) -> bool:
        return self.atomicity == ATOMIC

    @property
    def text(self) -> str:
        context = "".join(f" and {p}" for p in self.preconditions)
        middle = f", and {self.and_guard}" if self.and_guard else ""
        return f"Given {self.given}{context}, when {self.when}{middle}, then {self.then}."

    def to_criterion(self) -> AcceptanceCriterion:
        return AcceptanceCriterion(id=self.id, text=self.text,
                                   requirement_id=self.model_id,
                                   provenance=CODE_DERIVED)


@dataclass
class DraftSet:
    model_id: str
    drafts: list[DraftCriterion] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    # Drafted, but carrying more than one condition. **Deliberately not in
    # `skipped`**: "nothing was written for this transition" and "something was
    # written and it is not atomic" have different causes and different fixes,
    # and one list holding both makes the coverage figure mean two things.
    not_atomic: list[tuple[str, str]] = field(default_factory=list)

    @property
    def coverage(self) -> str:
        total = len(self.drafts) + len(self.skipped)
        return f"{len(self.drafts)}/{total} implemented transitions drafted"


def draft_from_model(model: Model, prefix: str = "DRAFT") -> DraftSet:
    """One draft criterion per implemented transition (spec §4.5).

    `planned` transitions are skipped: drafting a criterion for behaviour nobody
    has built would invite a reviewer to confirm something that does not exist
    (P-11).

    Ordering is deterministic, so re-drafting an unchanged model produces the
    same ids and a review already done is not invalidated (TR-6).
    """
    out = DraftSet(model_id=model.id)
    n = 0
    for tid in model.transition_ids():
        t = model.transitions[tid]
        if t.implementation_status != IMPLEMENTED:
            out.skipped.append((tid, "planned — not built yet (P-11)"))
            continue
        source = model.states.get(t.source)
        target = model.states.get(t.target)
        n += 1
        preconditions, deciding, atomicity = decompose_guard(t.guard)
        out.drafts.append(DraftCriterion(
            id=f"{prefix}-{n:03d}",
            transition_id=tid,
            given=f"the system is {_humanise_state(source.name) if source else t.source}",
            when=_humanise_trigger(t.trigger),
            and_guard=deciding,
            then=f"the result is {_humanise_state(target.name) if target else t.target}",
            model_id=model.id,
            preconditions=preconditions,
            atomicity=atomicity,
        ))
        if atomicity == NOT_DECOMPOSABLE:
            # Reported, not hidden. The draft is still emitted -- a reviewer
            # disagreeing with a compound sentence is more use than no sentence --
            # but it is not presented as though it were atomic.
            out.not_atomic.append(
                (tid, f"guard is a disjunction and was not split; the criterion "
                      f"carries more than one condition: {t.guard}"))
    return out


def format_drafts(drafts: DraftSet) -> str:
    lines = [f"Draft acceptance criteria — {drafts.model_id}",
             f"  {drafts.coverage}", "",
             f"  {REVIEW_PROMPT}", ""]
    for d in drafts.drafts[:12]:
        lines.append(f"  {d.id}  [{d.provenance}]")
        lines.append(f"      {d.text}")
    if len(drafts.drafts) > 12:
        lines.append(f"  ... and {len(drafts.drafts) - 12} more")
    if drafts.not_atomic:
        lines += ["",
                  "  Not atomic — these carry more than one condition, because "
                  "their guard is a",
                  "  disjunction and splitting it would require guessing which "
                  "branch decides (M-17):"]
        for tid, reason in drafts.not_atomic:
            lines.append(f"    {tid:<12} {reason}")
    lines += ["",
              "  EVERY draft above is code_derived: it was written FROM the",
              "  behaviour it describes. None of it can support a correctness",
              "  claim until a person edits or affirms it (S-19). Confirming a",
              "  draft unchanged documents the system; it does not validate it."]
    return "\n".join(lines)
