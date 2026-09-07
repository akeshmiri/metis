"""
Detectability — would we find out if this broke? (FMEA's third axis.)

**The axis a probability × impact grid cannot express.** The 5x5 in
`exposure.py` answers *how likely* and *how bad*. Neither question asks whether
anybody would notice, and in software that is the difference between a defect
that costs an hour and the same defect that costs a quarter. FMEA has carried
the third axis since the 1960s — RPN is Severity x Occurrence x **Detection**,
where detection is the chance the controls catch the failure — and it is missing
from the project-management risk reference this family was built from.

Métis is unusually well placed to compute it. Detection is normally judged by a
person the way probability is; here the coverage ledger and the execution
results answer it directly, for every transition, without asking anybody.

**This is not C-11, and the line matters more than anything else in this
module.** C-11 says a coverage figure answers *is this tested* and never
*does this work*, and `metis-risk-manager-quantitative` puts it at its
sharpest: never derive a probability from coverage, because that is "C-11 with a
currency symbol on it". Nothing here does.

    "this transition is untested, so a regression would ship unnoticed"
        -- what the ledger says. Detectability. Supported completely.

    "this transition is untested, so it is 40% likely to be broken"
        -- a failure rate. Forbidden, and not computed anywhere here.

Detection is a property of the *safety net*, not of the code under it. An
untested transition is not more likely to be wrong; it is less likely to be
found out. Those are different claims with different owners, and keeping them
apart is what lets coverage inform risk at all. `test_risk.py` asserts no
detection value ever reaches a `probability` field.

**A failing test scores best, not worst.** This inverts on first reading and is
the correct way round: detection asks whether the net would catch it, and a red
test is the net catching it. A covered-and-failing transition has *maximum*
detectability and a live defect, which are two findings, not one. Merging them
would rate a caught failure as dangerous-because-hidden — precisely backwards,
and it would push effort away from the failures nobody can see. The live defect
is returned beside the score, never folded into it.

**`unmeasured` is not a detection value.** Where coverage could not be measured
at all there is no answer to give, and the honest output is the absence.
Returning 5 ("nothing would notice") would report a measurement gap as a safety
gap; returning 1 would report it as safety. Both are lies of a kind this
codebase already refuses elsewhere, so `detection_for` raises and
`detection_over` collects those transitions separately.

Pure: a ledger, a mapping of executions, and nothing else. No session, no graph.
"""
from __future__ import annotations

from dataclasses import dataclass

from metis_mcp.mbt.coverage import DIRECT, INDIRECT, INITIATED

#: The scale, worst-detected last. Deliberately the same 1..5 shape as
#: `exposure.SCALE` so a reader carries one mental model, and deliberately NOT
#: multiplied into the exposure score -- see `MEANS` and `prioritisation.order`.
CAUGHT = 1
TESTED_UNOBSERVED = 2
INDIRECT_ONLY = 3
EXERCISED_NO_ORACLE = 4
UNNOTICED = 5

LABELS: dict[int, str] = {
    CAUGHT: "a failing change fails a test that has actually run",
    TESTED_UNOBSERVED: "a test asserts it; nobody has observed that test run",
    INDIRECT_ONLY: "asserted only through another path",
    EXERCISED_NO_ORACLE: "exercised, but nothing asserts the outcome",
    UNNOTICED: "nothing would notice",
}

#: Outcomes that mean the test genuinely ran and reported on the behaviour.
_RAN = ("passed", "failed")

MEANS = (
    "detectability, not probability: it says whether a break here would be "
    "found, never how likely one is (C-11). It is an ordinal like the 5x5 and "
    "is never multiplied into an exposure score -- three ordinals multiplied is "
    "an RPN, and an RPN hides which of its three axes is the bad one"
)


class Unmeasured(Exception):
    """Coverage could not be measured here, so detectability has no value.

    Raised rather than defaulted. Every default available is a false statement:
    `UNNOTICED` reports a measurement gap as a safety gap, and `CAUGHT` reports
    it as safety.
    """


@dataclass(frozen=True)
class Detection:
    """One transition's detectability, and the live defect if there is one."""

    transition_id: str
    score: int
    label: str
    #: True when a test covering this transition was observed failing. A finding
    #: in its own right, reported beside the score and never folded into it.
    failing: bool = False
    #: The cases that produced the reading, so a reader can disagree with the
    #: input rather than only with the conclusion.
    test_case_ids: tuple[str, ...] = ()

    @property
    def is_blind_spot(self) -> bool:
        """Nothing asserts the outcome, whatever else is true of it."""
        return self.score >= EXERCISED_NO_ORACLE


def _mechanism_floor(mechanism: str) -> int:
    """The best detectability a mechanism can support, before executions."""
    if mechanism == DIRECT:
        return TESTED_UNOBSERVED
    if mechanism == INDIRECT:
        return INDIRECT_ONLY
    if mechanism == INITIATED:
        # M-5a: a UI path started the call and observed no outcome. Real
        # information, and not an oracle -- firing a request proves neither
        # which outcome occurred nor that anybody asserted it.
        return EXERCISED_NO_ORACLE
    return UNNOTICED


def detection_for(transition_id: str, rows, executions=None,
                  unmeasured=()) -> Detection:
    """Detectability for one transition.

    `rows` are the ledger rows for this transition (`LedgerRow`), `executions`
    maps a test-case id to an outcome from `execution_intake.OUTCOMES`.
    """
    if transition_id in set(unmeasured or ()):
        raise Unmeasured(
            f"coverage for {transition_id} was not measured, so whether a break "
            f"here would be noticed is unknown -- which is neither a blind spot "
            f"nor a safety net, and reporting it as either would be a claim "
            f"nobody made")

    mine = [r for r in rows if r.transition_id == transition_id]
    if not mine:
        return Detection(transition_id, UNNOTICED, LABELS[UNNOTICED])

    outcomes = dict(executions or {})
    best = UNNOTICED
    failing = False
    cases: list[str] = []

    for row in mine:
        floor = _mechanism_floor(row.mechanism)
        case = getattr(row, "test_case_id", None)
        if case:
            cases.append(case)
        outcome = outcomes.get(case) if case else None
        if outcome in _RAN and floor <= TESTED_UNOBSERVED:
            # Observed running against this behaviour: the net demonstrably
            # covers it. `failed` scores the same as `passed` on purpose -- the
            # break WAS caught, which is what this axis measures.
            floor = CAUGHT
        if outcome == "failed":
            failing = True
        best = min(best, floor)

    return Detection(transition_id, best, LABELS[best], failing,
                     tuple(dict.fromkeys(cases)))


def detection_over(transition_ids, rows, executions=None, unmeasured=()) -> dict:
    """Every transition's detectability, with the unmeasurable ones kept apart.

    The separation is the output's whole shape: `scores` is what can be read as
    a risk signal, `unmeasured` is what nothing may be concluded about, and a
    caller cannot accidentally average the second into the first.
    """
    scores: dict[str, Detection] = {}
    could_not_measure: list[str] = []

    for tid in transition_ids:
        try:
            scores[tid] = detection_for(tid, rows, executions, unmeasured)
        except Unmeasured:
            could_not_measure.append(tid)

    failing = sorted(d.transition_id for d in scores.values() if d.failing)
    return {
        "scores": scores,
        "unmeasured": sorted(could_not_measure),
        # Reported separately and named, because it is the one thing here that
        # is about correctness rather than about the safety net.
        "failing": failing,
        "blind_spots": sorted(d.transition_id for d in scores.values()
                              if d.is_blind_spot),
        "means": MEANS,
    }
