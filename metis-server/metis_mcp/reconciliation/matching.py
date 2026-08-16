"""
Matching acceptance criteria to transitions (application spec §3.3, §5.7; R5).

The mechanism §4.1 identifies as the only place real defects surface: a model
extracted from code tells you what the system *does*; an acceptance criterion
says what it *should* do. Comparing them is where "the code locks after 3
attempts, the criterion says 5" becomes visible.

Three stages (X-15), and the ordering is the point:

    1. deterministic pre-filter   narrow candidates by real evidence
    2. judgement                  decide, over a BOUNDED candidate list
    3. human confirmation         a match is proposed, never asserted

**X-16** stage 1 always runs first. A judgement step over an unfiltered candidate
set is both more expensive and less accurate.

**X-17** name similarity is never sufficient. An endpoint called `/password-reset`
and a criterion mentioning "password reset" is a *candidate for review*, not
evidence of a match. That shortcut is how a coverage number becomes meaningless
while appearing to solve the matching problem, so the pre-filter deliberately
**narrows without deciding** -- it emits evidence, and evidence is not a verdict.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from metis_mcp.mbt.model import Model, Transition
from metis_mcp.ontology.labels import (
    CODE_DERIVED,
    HUMAN_CONFIRMED,
    INDEPENDENTLY_AUTHORED,
    PROVENANCE_GRADES,
)

# Evidence kinds a deterministic pre-filter can establish. Each is a fact about
# the text, never an inference about meaning.
EV_PATH = "path"
EV_VERB = "verb"
EV_STATUS = "status"
EV_STATE = "state"
EV_AREA = "functional_area"
EV_TRIGGER_WORDS = "trigger_words"

# `_` is a SEPARATOR, not a word character. Including it tokenised
# `submit_valid_credentials` as one word, so EV_TRIGGER_WORDS could never fire
# for a snake_case trigger -- the dominant trigger form this system produces.
# The pre-filter silently returned no candidates for every hand-authored model,
# which reads identically to "this criterion describes nothing" (X-15). Caught by
# running `reconcile` against the real login model, not by a test: the fixture
# here uses space-separated HTTP triggers, which happen to tokenise correctly.
# Matches `humanise()`'s existing `[_\-.]` separator set.
_WORD = re.compile(r"[a-z0-9]+")
_STATUS = re.compile(r"\b([1-5]\d{2})\b")
_STOP = {"the", "a", "an", "and", "or", "of", "to", "is", "be", "shall", "when",
         "then", "if", "given", "that", "it", "for", "with", "system", "user"}


# Spec S-19 -- the three grades of an acceptance criterion.
#
# **A criterion derived from code is documentation, not intent.** Comparing a
# code-extracted model against criteria that were themselves written from that
# code is circular: it can only ever report agreement, and §4.1 says so plainly.
# This was not hypothetical -- the athena estate's specs are marked IMPLEMENTED
# and their own plan says "documents what was built", so all eight confirmed
# matches there were documentation agreeing with itself.
#
# The grade is what stops that from being counted as correctness.
#
# **Defined in `ontology.labels`, re-exported here.** The grade used to live at
# this line only, which is exactly why it was unstorable: `AcceptanceCriterion`
# carried no `provenance` property, so `promotion_for` computed a grade that had
# nowhere to go. One definition, owned by the layer that decides what the graph
# can hold.
from metis_mcp.ontology.labels import (  # noqa: E402
    CODE_DERIVED,
    HUMAN_CONFIRMED,
    INDEPENDENTLY_AUTHORED,
    PROVENANCE_GRADES,
)

# Only these two are INTENT. Everything else gives coverage, never correctness.
INTENT_GRADES = frozenset({HUMAN_CONFIRMED, INDEPENDENTLY_AUTHORED})


@dataclass(frozen=True)
class AcceptanceCriterion:
    """The AC side of a match. Text plus whatever tags it carries.

    `provenance` defaults to `code_derived` -- the weakest grade -- deliberately.
    A criterion whose origin nobody recorded must not be assumed to be intent,
    for the same fail-closed reason a model source lands at Quarantine (S-4).
    """

    id: str
    text: str
    functional_areas: tuple[str, ...] = ()
    requirement_id: str | None = None
    provenance: str = CODE_DERIVED

    @property
    def is_intent(self) -> bool:
        """Whether this criterion may serve as the intent side of §4.4 (S-19)."""
        return self.provenance in INTENT_GRADES


@dataclass
class Candidate:
    transition_id: str
    evidence: dict[str, str] = field(default_factory=dict)

    @property
    def strength(self) -> int:
        """How many independent kinds of evidence, NOT a probability.

        Deliberately an integer count rather than a score: a score invites a
        threshold, and a threshold invites deciding without a human -- which X-17
        prohibits.
        """
        return len(self.evidence)


@dataclass
class MatchProposal:
    ac_id: str
    candidates: list[Candidate] = field(default_factory=list)
    note: str = ""

    @property
    def is_ambiguous(self) -> bool:
        if len(self.candidates) < 2:
            return False
        top = self.candidates[0].strength
        return sum(1 for c in self.candidates if c.strength == top) > 1


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


def prefilter(ac: AcceptanceCriterion, model: Model,
              endpoint_paths: dict[str, str] | None = None) -> MatchProposal:
    """Stage 1: narrow by evidence present in the text (spec X-15, X-16).

    `endpoint_paths` maps transition id -> route, so a criterion naming `/commit`
    can be tied to the transitions that trigger it. Every signal here is a
    literal occurrence; none is an inference.
    """
    proposal = MatchProposal(ac_id=ac.id)
    text = ac.text.lower()
    ac_words = _words(ac.text)
    statuses = set(_STATUS.findall(ac.text))
    paths = endpoint_paths or {}

    for tid in model.transition_ids():
        transition = model.transitions[tid]
        evidence: dict[str, str] = {}

        route = paths.get(tid, "")
        if route and route.lower() in text:
            evidence[EV_PATH] = route

        verb = transition.trigger.split()[0].upper() if transition.trigger else ""
        if verb and verb.lower() in text and len(verb) > 2:
            evidence[EV_VERB] = verb

        for status in statuses:
            if status in transition.target or status in transition.id:
                evidence[EV_STATUS] = status
                break

        target_state = model.states.get(transition.target)
        if target_state:
            state_words = _words(target_state.name)
            if state_words and state_words <= ac_words:
                evidence[EV_STATE] = target_state.name

        overlap = set(ac.functional_areas) & set(getattr(transition, "functional_areas", ()) or ())
        if overlap:
            evidence[EV_AREA] = ",".join(sorted(overlap))

        trigger_words = _words(transition.trigger)
        shared = trigger_words & ac_words
        if len(shared) >= 2:
            evidence[EV_TRIGGER_WORDS] = ",".join(sorted(shared))

        if evidence:
            proposal.candidates.append(Candidate(transition_id=tid, evidence=evidence))

    proposal.candidates.sort(key=lambda c: (-c.strength, c.transition_id))

    if not proposal.candidates:
        proposal.note = (
            "no candidates: nothing in this criterion's text refers to any "
            "transition's route, verb, status or target state"
        )
    elif proposal.is_ambiguous:
        proposal.note = (
            f"{len([c for c in proposal.candidates if c.strength == proposal.candidates[0].strength])}"
            f" candidates tie on evidence — a human decides (X-17)"
        )
    return proposal


class JudgementUnavailable(NotImplementedError):
    """Raised when stage 2 is requested but no judge is configured."""


def judge(proposal: MatchProposal, ac: AcceptanceCriterion, model: Model,
          judge_fn=None) -> MatchProposal:
    """Stage 2: decide over the bounded candidate list (spec X-15).

    A judge is **injected**, never constructed here: it costs money, and spec
    MIN-010 requires the cost gate to be consulted before any model call. With no
    judge configured this raises rather than silently falling back to the
    pre-filter's top candidate -- because falling back would turn evidence into a
    verdict, which is exactly X-17's prohibition.
    """
    if judge_fn is None:
        raise JudgementUnavailable(
            "no judge configured. Stage 1's candidates are available and a human "
            "may confirm one directly (stage 3); the pre-filter must not be "
            "treated as a decision (spec X-17)."
        )
    return judge_fn(proposal, ac, model)


@dataclass
class ConfirmedMatch:
    """Stage 3's output. Only this counts as a match (spec F-7, X-18).

    `provenance` carries the criterion's grade through to the gap report, so a
    match backed by documentation is never silently counted alongside one backed
    by intent (S-19).
    """

    ac_id: str
    transition_id: str
    confirmed_by: str
    evidence: dict[str, str] = field(default_factory=dict)
    rationale: str = ""
    provenance: str = CODE_DERIVED

    @property
    def is_intent(self) -> bool:
        return self.provenance in INTENT_GRADES


def confirm(proposal: MatchProposal, transition_id: str, confirmed_by: str,
            rationale: str = "", provenance: str = CODE_DERIVED) -> ConfirmedMatch:
    """Record a human decision. Nothing else produces a match.

    Confirming the MATCH does not upgrade the criterion's provenance: a person
    agreeing that AC-4 describes this transition says nothing about whether AC-4
    was written from the code. Those are separate facts, and conflating them
    would let a match confirmation quietly manufacture intent (S-19, cf. X-12).
    """
    if not confirmed_by.strip():
        raise ValueError("a confirmation records who made it")
    if provenance not in PROVENANCE_GRADES:
        raise ValueError(f"unknown provenance {provenance!r}; expected one of "
                         f"{PROVENANCE_GRADES}")
    candidate = next((c for c in proposal.candidates if c.transition_id == transition_id), None)
    return ConfirmedMatch(
        ac_id=proposal.ac_id, transition_id=transition_id, confirmed_by=confirmed_by,
        evidence=dict(candidate.evidence) if candidate else {},
        rationale=rationale, provenance=provenance,
    )
