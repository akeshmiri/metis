"""
Behaviour mined from acceptance-criteria prose (application spec §4.5;
S-12, S-13, S-14).

**Why this source matters more than its size suggests.** §4.1 established that a
model extracted from code, used to generate tests, is circular -- it proves the
code does what the code does. Its worth comes from comparison against *intent*,
and **S-3** is explicit that a deployment running only code extraction gets
coverage, not correctness. This module is one of the two sources that can supply
the intent side. Without it, "the code locks after 3 attempts, the criterion says
5" is not a finding anything can produce.

**Deterministic, not generated.** S-12 asks for staged extraction with
deterministic verification of every proposal, and TR-4 prefers deterministic code
to generated judgement wherever it will do. Acceptance criteria written to a
known shape -- EARS, or the Given/When/Then §18 itself emits -- are parseable
without a model call, so no model call is made. That also means this source costs
nothing to run and cannot hallucinate: the failure mode of a regex is a *miss*,
which is reported, not a confident invention.

**S-13 -- a proposal that cannot be grounded in the source text is blocked, not
written**, however well-formed it appears. Fluent well-formedness is what a
fabrication looks like. Grounding here is literal: every element must be locatable
as a span of the criterion it came from, and the span is recorded (S-14).

**The honest limitation, restated where it will be read.** Acceptance criteria
rarely describe a complete state machine. AC-mined models are typically partial --
a few transitions, not a closed machine -- and §2.6's checks will correctly report
them incomplete. That is the tool working, not failing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from metis_mcp.ears_checker import check_ears_conformance
from metis_mcp.mbt.model import IMPLEMENTED, QUARANTINE, Model, State, Transition

# Stage 1 shapes. Ordered: the most explicit is tried first, so a criterion that
# states its source state is never read as one that does not.
_GWT = re.compile(
    r"given\s+(?:the\s+)?(?:user\s+is\s+)?(?P<given>.+?)[,\s]*"
    r"when\s+(?:they\s+)?(?P<when>.+?)"
    r"(?:[,\s]*and\s+(?P<and_guard>.+?))?"
    r"[,\s]*then\s+(?:they\s+are\s+)?(?P<then>.+?)\.?$",
    re.IGNORECASE | re.DOTALL)

_WHILE_WHEN = re.compile(
    r"^while\s+(?P<given>.+?),\s*when\s+(?P<when>.+?),\s*"
    r"the\s+(?P<system>.+?)\s+shall\s+(?P<then>.+?)\.?$",
    re.IGNORECASE)

BLOCKED_UNPARSEABLE = "unparseable"
BLOCKED_UNGROUNDED = "ungrounded"
BLOCKED_INCOMPLETE = "incomplete"


def slug(text: str) -> str:
    """`Logged Out` -> `LoggedOut`. Deterministic, and only ever a re-casing.

    Never a paraphrase: the display name keeps the criterion's own words, and
    this produces only the identifier. Two criteria saying "logged out" and
    "Logged Out" describe one situation and must not become two states.
    """
    parts = re.findall(r"[A-Za-z0-9]+", text)
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Unnamed"


@dataclass(frozen=True)
class Span:
    """Where in the criterion an element came from (spec S-14)."""

    criterion_id: str
    start: int
    end: int
    text: str

    def describe(self) -> str:
        return f"{self.criterion_id}[{self.start}:{self.end}] {self.text!r}"


@dataclass(frozen=True)
class MinedElement:
    kind: str                    # "state" | "transition"
    element_id: str
    display: str
    span: Span


@dataclass
class Blocked:
    criterion_id: str
    reason: str
    detail: str

    def describe(self) -> str:
        return f"[{self.reason}] {self.criterion_id}: {self.detail}"


@dataclass
class MiningResult:
    model: Model | None = None
    elements: list[MinedElement] = field(default_factory=list)
    blocked: list[Blocked] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.model is not None and bool(self.model.transitions)

    def spans_for(self, element_id: str) -> list[Span]:
        return [e.span for e in self.elements if e.element_id == element_id]


def _span(criterion_id: str, text: str, fragment: str) -> Span | None:
    """Locate a fragment literally. Returns None rather than approximating.

    This is the whole of S-13's enforcement: an element whose words are not
    actually present in the criterion cannot be grounded, and an ungrounded
    proposal is blocked rather than written.
    """
    if not fragment:
        return None
    index = text.lower().find(fragment.strip().lower())
    if index < 0:
        return None
    return Span(criterion_id=criterion_id, start=index,
                end=index + len(fragment.strip()), text=text[index:index + len(fragment.strip())])


@dataclass
class Criterion:
    id: str
    text: str
    requirement_id: str | None = None


def _parse(text: str) -> dict | None:
    """Stage 1: recognise a known shape. No interpretation beyond the pattern."""
    stripped = " ".join(text.split())
    for pattern in (_WHILE_WHEN, _GWT):
        m = pattern.search(stripped)
        if m:
            groups = m.groupdict()
            if groups.get("given") and groups.get("when") and groups.get("then"):
                return groups
    return None


def mine(criteria: list[Criterion], model_id: str, surface: str = "api",
         initial_state: str | None = None) -> MiningResult:
    """Stage 1 parse, stage 2 ground, stage 3 emit (spec S-12).

    Every element lands at `Quarantine` (S-4), like every source's output. The
    result is deliberately allowed to be partial: an unparseable criterion is
    reported and the rest are still mined, because a single prose sentence in an
    otherwise structured set should not cost the whole model.
    """
    result = MiningResult()
    states: dict[str, State] = {}
    transitions: dict[str, Transition] = {}

    for criterion in criteria:
        parsed = _parse(criterion.text)
        if parsed is None:
            ears = check_ears_conformance(criterion.text.strip())
            detail = (
                f"no source state, trigger and outcome could be read from this "
                f"criterion. "
                + (f"It matches the {ears.pattern} EARS pattern, which states a "
                   f"response but not the situation it applies from — a transition "
                   f"needs both (M-1)."
                   if ears.conformant else
                   "It matches no EARS pattern and no Given/When/Then shape.")
            )
            result.blocked.append(Blocked(criterion.id, BLOCKED_UNPARSEABLE, detail))
            continue

        given, when = parsed["given"].strip(), parsed["when"].strip()
        then, guard = parsed["then"].strip(), (parsed.get("and_guard") or "").strip()

        # Stage 2: ground every fragment literally, before anything is written.
        spans = {
            "given": _span(criterion.id, criterion.text, given),
            "when": _span(criterion.id, criterion.text, when),
            "then": _span(criterion.id, criterion.text, then),
        }
        ungrounded = [name for name, span in spans.items() if span is None]
        if ungrounded:
            result.blocked.append(Blocked(
                criterion.id, BLOCKED_UNGROUNDED,
                f"could not locate {ungrounded} in the criterion's own text. "
                f"A proposal that cannot be grounded is blocked, not written "
                f"(S-13) — however well-formed it looks"))
            continue

        source_id, target_id = slug(given), slug(then)
        if source_id == target_id and not guard:
            result.notes.append(
                f"{criterion.id}: source and target are the same situation "
                f"({source_id!r}) with no distinguishing condition — kept as a "
                f"self-loop, which is what the criterion says")

        for element_id, display, span in (
                (source_id, given, spans["given"]), (target_id, then, spans["then"])):
            if element_id not in states:
                states[element_id] = State(
                    id=element_id, name=display, surface=surface,
                    is_initial=(initial_state == element_id), lifecycle_state=QUARANTINE)
                result.elements.append(MinedElement("state", element_id, display, span))

        transition_id = f"ac::{source_id}::{slug(when)}::{target_id}"
        transitions[transition_id] = Transition(
            id=transition_id, source=source_id, trigger=when, target=target_id,
            guard=guard, implementation_status=IMPLEMENTED, lifecycle_state=QUARANTINE)
        result.elements.append(
            MinedElement("transition", transition_id, when, spans["when"]))

    if not transitions:
        result.blocked.append(Blocked(
            model_id, BLOCKED_INCOMPLETE,
            "no transition could be mined from any criterion — nothing is written. "
            "An empty model is not a model (S-17)"))
        return result

    # S-4: if no initial state was named, say so rather than electing one. A
    # guessed starting point produces preconditions nobody can establish (P-8).
    if initial_state is None or initial_state not in states:
        result.notes.append(
            "no initial state named: AC-mined models are typically partial (§4.5), "
            "and electing one would invent a precondition. Reachability will "
            "correctly report this until a reviewer marks it")

    model = Model(id=model_id, states=states, transitions=transitions)
    model.reindex()
    result.model = model
    return result


def format_mining(result: MiningResult) -> str:
    lines = ["AC mining"]
    if result.model:
        lines.append(f"  mined: {len(result.model.states)} state(s), "
                     f"{len(result.model.transitions)} transition(s), all at Quarantine")
    else:
        lines.append("  mined: nothing")
    if result.blocked:
        lines += ["", f"  BLOCKED ({len(result.blocked)}) — not written (S-13):"]
        lines += [f"    {b.describe()}" for b in result.blocked[:8]]
    if result.notes:
        lines += ["", "  NOTES:"] + [f"    {n}" for n in result.notes[:8]]
    lines += ["",
              "  AC-mined models are typically PARTIAL (§4.5). §2.6's checks will",
              "  report them incomplete, and that is the tool working, not failing.",
              "  They are the intent side of a comparison (S-3), rarely a generation",
              "  source on their own."]
    return "\n".join(lines)
