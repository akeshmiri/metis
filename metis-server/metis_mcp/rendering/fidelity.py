"""What to do about behaviour an existing test already reaches.

**Ported as a set of verdicts, not as a rewriter.** The practice this comes from
states the rule plainly: a generated test must reconcile to a verified source —
preserve its actions, expected results, preconditions, data and scope exactly;
never invent detail to fill a gap; never split or rewrite a source case
automatically. What it adds beyond that rule is three verdicts, and those are
what Métis lacked.

Métis already had the *measurement*. `mbt/test_levels.py` grades every transition
against the tests that exist, and its middle grade is the honest one: a test
reaches the endpoint and this outcome is not evidenced. What it did not have was
a decision attached to that grade — so `should_generate` said yes and nothing
recorded that an existing test was *nearly* right, which is a different situation
from nothing existing at all.

    covered                            -> continue_as_is
    endpoint_covered_outcome_unproven  -> improvement_needed
    uncovered                          -> generate; there is no source to be
                                          faithful to

**`improvement_needed` recommends and never edits.** The existing test belongs to
whoever wrote it. A recommendation that quietly rewrote it would destroy the one
thing source fidelity is for, and the person who owns that test would find their
assertions changed by a run they did not read.

**`split_requested` blocks.** One existing test covering several outcomes cannot
be made faithful to any of them by a machine deciding where to cut. It escalates
and stops, and an unresolved split is a blocked batch rather than a smaller one.

Pure: grades in, verdicts out. Nothing here reads a graph or writes a file.
"""
from __future__ import annotations

from dataclasses import dataclass

from metis_mcp.mbt.test_levels import COVERED, OUTCOME_UNPROVEN, UNCOVERED

#: The three verdicts. `generate` is Métis's own fourth: the practice this came
#: from always has a source case in hand, and Métis frequently has none — and
#: "there is nothing to be faithful to" is a different answer from "the existing
#: one is sufficient".
CONTINUE_AS_IS = "continue_as_is"
IMPROVEMENT_NEEDED = "improvement_needed"
SPLIT_REQUESTED = "split_requested"
GENERATE = "generate"
VERDICTS = (CONTINUE_AS_IS, IMPROVEMENT_NEEDED, SPLIT_REQUESTED, GENERATE)

#: Verdicts that stop a batch. Only one, and narrowly: a split is the single case
#: where continuing would mean a machine deciding where to cut somebody's test.
BLOCKING = (SPLIT_REQUESTED,)


@dataclass(frozen=True)
class Fidelity:
    """One transition's verdict against the tests that already exist."""

    transition_id: str
    verdict: str
    #: The existing tests this is about. Empty exactly when `generate`.
    existing: tuple[str, ...] = ()
    #: Why. A verdict a reader cannot audit is one they must take on trust.
    because: str = ""

    @property
    def blocks(self) -> bool:
        return self.verdict in BLOCKING

    @property
    def may_generate(self) -> bool:
        """Whether generation should fire.

        `improvement_needed` generates: the outcome is not evidenced, and
        treating unproven as proven is how a real gap gets excused
        (REQ-METIS-PG-01). What changes is that the run now also says an
        existing test was close, so a reviewer can improve that one instead of
        accepting a second.
        """
        return self.verdict in (GENERATE, IMPROVEMENT_NEEDED)

    def describe(self) -> str:
        return f"[{self.verdict}] {self.transition_id}: {self.because}"


def verdict_for(grade, splits: dict[str, str] | None = None) -> Fidelity:
    """One grade, as a verdict.

    `splits` maps a transition id to the reason a person said its existing test
    would have to be split. **Supplied, never inferred** — deciding that one
    test covers two things and should become two is a judgement about somebody
    else's test, and a heuristic that got it wrong would block a batch over a
    test that was fine.
    """
    tid = grade.transition_id
    reason = (splits or {}).get(tid)
    if reason:
        return Fidelity(
            tid, SPLIT_REQUESTED, existing=tuple(grade.evidence),
            because=(f"a split was requested and nobody has directed it: "
                     f"{reason}. Métis will not choose where to cut a test it "
                     f"did not write"))

    if grade.grade == COVERED:
        return Fidelity(
            tid, CONTINUE_AS_IS, existing=tuple(grade.evidence),
            because=(grade.detail or
                     "an existing test reaches this and asserts its outcome"))

    if grade.grade == OUTCOME_UNPROVEN:
        return Fidelity(
            tid, IMPROVEMENT_NEEDED, existing=tuple(grade.evidence),
            because=(f"{grade.detail or 'the endpoint is reached'} — the "
                     f"outcome is not evidenced. Improving the existing test is "
                     f"usually better than adding a second, and that is a "
                     f"recommendation: nothing here edits it"))

    return Fidelity(
        tid, GENERATE,
        because=(grade.detail or
                 "nothing reaches this, so there is no source to be faithful to"))


def review(grades: dict, splits: dict[str, str] | None = None) -> dict:
    """Every grade as a verdict, with the counts and what blocks.

    Reports `blocked` separately from the counts, deliberately: a batch with one
    split request and forty clean verdicts is a blocked batch, and a distribution
    that buried the one would read as healthy.
    """
    verdicts = {tid: verdict_for(grade, splits)
                for tid, grade in sorted(grades.items())}
    counts = {name: 0 for name in VERDICTS}
    for fidelity in verdicts.values():
        counts[fidelity.verdict] += 1

    blocked = [f.describe() for f in verdicts.values() if f.blocks]
    return {
        "verdicts": {tid: {"verdict": f.verdict, "existing": list(f.existing),
                           "because": f.because}
                     for tid, f in verdicts.items()},
        "counts": counts,
        "blocked": blocked,
        "may_generate": [tid for tid, f in verdicts.items() if f.may_generate],
        "means": (
            "A SPLIT IS UNRESOLVED and the batch is blocked. Splitting somebody "
            "else's test is a direction a person gives, not one Métis takes"
            if blocked else
            "no split is outstanding. `improvement_needed` still generates — an "
            "unevidenced outcome is a real gap — and it also says which existing "
            "test was close, because improving that one is usually better than "
            "adding a second"),
    }
