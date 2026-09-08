"""The words a release recommendation is allowed to use, and what each rests on.

**Why a vocabulary at all.** `metis-release-readiness` already had the hard part:
an evidence ladder saying when a verdict may be given, and a confidence axis
capped by the weakest input actually used. What it had no words for was the
recommendation itself, so every run phrased its conclusion differently and two
readers of two reports could not tell whether they had been told the same thing.

Three words, closed. They are the sibling project's, kept identical because a
recommendation is read by people who move between both systems and a synonym
would read as a different claim.

**This does not weaken C-11 and the rule is enforced here rather than trusted.**
Coverage says a behaviour is tested; it says nothing about whether it works, and
covered-and-failing is a real state — precisely the state a coverage-derived
`Go` would call ready. So `permitted_by` refuses `Go` for anything resting on
coverage alone, and `test_verdict.py` asserts it. The ladder was prose that a
skill was asked to follow; it is a function now.

**Métis does not choose.** `permitted_by` says which recommendations the evidence
*can* support. Which one to give is a person's call about what they are willing
to ship, and `risk/prioritisation.exit_criteria` already refuses to make it.
"""
from __future__ import annotations

#: The recommendation. `Go with Conditions` is the one that earns its place:
#: without it a reviewer with real reservations has to choose between blocking a
#: release and pretending they have none.
GO = "Go"
GO_WITH_CONDITIONS = "Go with Conditions"
NO_GO = "No-Go"
RECOMMENDATIONS = (GO, GO_WITH_CONDITIONS, NO_GO)

#: Confidence, capped by the weakest input actually used. These four already
#: existed in the skill's prose; naming them here is what lets the cap be
#: checked rather than remembered.
CONFIRMED = "confirmed"
INFERRED = "inferred"
ESTIMATED = "estimated"
UNKNOWN = "unknown"
CONFIDENCE = (CONFIRMED, INFERRED, ESTIMATED, UNKNOWN)

#: What each level of confidence rests on.
RESTS_ON = {
    CONFIRMED: "execution evidence for the behaviour in question, recent",
    INFERRED: "execution evidence for some of it",
    ESTIMATED: "coverage and validation only — no run was observed",
    UNKNOWN: "the data does not exist",
}

#: **The rule this module exists to enforce.** `Go` requires an observed run.
#: Everything else may be recommended at any confidence, because saying *do not
#: ship* or *ship with these conditions* on weak evidence is a cautious call a
#: person is entitled to make — while saying *ship* on it is a claim the
#: evidence cannot support.
_PERMITTED = {
    CONFIRMED: (GO, GO_WITH_CONDITIONS, NO_GO),
    INFERRED: (GO, GO_WITH_CONDITIONS, NO_GO),
    ESTIMATED: (GO_WITH_CONDITIONS, NO_GO),
    UNKNOWN: (NO_GO,),
}


class UnknownConfidence(Exception):
    """Raised for a confidence level that is not one of the four."""


def permitted_by(confidence: str) -> tuple[str, ...]:
    """Which recommendations this evidence can support.

    Refuses an unrecognised level rather than defaulting: a typo that silently
    became `confirmed` would widen the ladder at exactly the point it exists to
    narrow it.
    """
    try:
        return _PERMITTED[confidence]
    except KeyError:
        raise UnknownConfidence(
            f"{confidence!r} is not a confidence level. Known: "
            f"{', '.join(CONFIDENCE)}") from None


def confidence_from(execution_records: int, stale: bool = False,
                    measurable: bool = True) -> str:
    """The confidence a body of evidence supports, capped by its weakest part.

    `execution_records` is how many observed runs back the scope. Zero is the
    common case and it is `estimated`, never `inferred`: a coverage figure with
    no run behind it is an estimate of quality, and calling it an inference
    would let it climb one rung it did not earn.
    """
    if not measurable:
        return UNKNOWN
    if execution_records <= 0:
        return ESTIMATED
    # Stale evidence is still evidence, and it is not evidence about today.
    return INFERRED if stale or execution_records < 2 else CONFIRMED


def check(recommendation: str, confidence: str) -> dict:
    """Whether the evidence supports the recommendation somebody wants to give.

    Returns the verdict on the *pairing*, never on the release. A refusal here
    says the words do not match the evidence — not that the release is unsafe,
    which is a different question with a different owner.
    """
    if recommendation not in RECOMMENDATIONS:
        return {"ok": False,
                "reason": (f"{recommendation!r} is not a recommendation. "
                           f"Known: {', '.join(RECOMMENDATIONS)}")}
    allowed = permitted_by(confidence)
    if recommendation in allowed:
        return {"ok": True, "recommendation": recommendation,
                "confidence": confidence, "rests_on": RESTS_ON[confidence]}
    return {
        "ok": False,
        "recommendation": recommendation,
        "confidence": confidence,
        "rests_on": RESTS_ON[confidence],
        "permitted": list(allowed),
        "reason": (
            f"{recommendation!r} rests on {RESTS_ON[confidence]}, which cannot "
            f"support it. Coverage says a behaviour is tested and nothing about "
            f"whether it works — covered-and-failing is a real state, and it is "
            f"the state a coverage-derived Go would call ready (C-11)"),
    }


def describe() -> dict:
    """The ladder, for a tool and for a test."""
    return {
        "recommendations": list(RECOMMENDATIONS),
        "confidence": list(CONFIDENCE),
        "rests_on": dict(RESTS_ON),
        "permitted": {level: list(allowed)
                      for level, allowed in _PERMITTED.items()},
        "means": (
            "which recommendations a body of evidence can support. Métis does "
            "not choose one: what you are willing to ship is a person's call, "
            "and `risk.prioritisation.exit_criteria` already refuses to make "
            "it. What is enforced here is that `Go` needs an observed run"),
    }
