"""
Risk arithmetic: exposure, the 5x5 band, EMV and PERT.

**These are tools because a unit test can assert their output**, which is the
placement rule's question. Prose restating `Exposure = Probability x Impact` is
the failure mode here -- it reads as guidance and computes nothing, and two
people applying it by hand produce two answers.

**The honest caveat, stated once and carried into every answer.** A 5x5 matrix
scores probability and impact on an ORDINAL scale: `3` means "Medium", not three
of anything. Multiplying two ordinals is not a defined operation, so `3 x 4 = 12`
is a sorting key and not a quantity. It cannot be compared across projects, it
cannot be averaged, and a risk scoring 12 is not "twice" one scoring 6.

That is a well-known criticism of risk matrices and it is not a reason to refuse
them -- ranking is genuinely useful and the sheet is the industry's common
language. It is a reason to return the band WITH what it rests on, so nobody
builds a budget on a rank. Every function here reports its own basis.

**EMV is the opposite and the two must never be mixed.** `emv` takes a real
probability in `0..1` and a financial impact in currency, and its output IS a
quantity: it can be summed across a portfolio, which is the entire point of it.
Passing an ordinal `1..5` where a probability belongs yields a number 100x too
large and looks perfectly plausible, so `emv` refuses a value above 1 rather
than computing it.

**PERT weights the most likely estimate four times** -- `(O + 4M + P) / 6`. It
is a beta-distribution approximation, so it is a smoothing of three guesses and
not a measurement, and `pert` says so in its answer for the same reason `exposure`
does.
"""
from __future__ import annotations

from dataclasses import dataclass

# The five ordinal points, lowest first. Index + 1 is the score, so the labels
# and the arithmetic cannot disagree about what `3` means.
SCALE = ("Very Low", "Low", "Medium", "High", "Very High")
MIN_POINT, MAX_POINT = 1, len(SCALE)

# **Band boundaries are a CONVENTION, not a fact**, and different organisations
# draw them differently. They are named here so a deployment can see what it is
# getting rather than discovering it from a colour, and every answer reports
# which set produced it.
#
# These are the common PMI-style cuts over a 1..25 product.
BANDS = (
    (1, 5, "Low"),
    (6, 11, "Medium"),
    (12, 19, "High"),
    (20, 25, "Very High"),
)

ORDINAL_BASIS = (
    "an ordinal rank, not a quantity: probability and impact are 1..5 labels, "
    "so the product orders risks and does not measure them. It cannot be "
    "summed, averaged, or compared across projects"
)


class RiskInputRefused(ValueError):
    """An input that cannot be scored, and why. Nothing is computed."""


@dataclass(frozen=True)
class Exposure:
    probability: int
    impact: int
    score: int
    band: str
    basis: str = ORDINAL_BASIS


def _point(name: str, value) -> int:
    """One 1..5 ordinal, or a refusal naming what was expected."""
    try:
        point = int(value)
    except (TypeError, ValueError):
        raise RiskInputRefused(
            f"{name} must be a whole number {MIN_POINT}..{MAX_POINT} "
            f"({', '.join(SCALE)}); got {value!r}") from None
    if not MIN_POINT <= point <= MAX_POINT:
        raise RiskInputRefused(
            f"{name} must be {MIN_POINT}..{MAX_POINT} ({', '.join(SCALE)}); "
            f"got {point}. A 0..1 probability belongs in `emv`, not here")
    return point


def band_for(score: int) -> str:
    """The band one score falls in. Raises rather than guessing off the end."""
    for low, high, name in BANDS:
        if low <= score <= high:
            return name
    raise RiskInputRefused(
        f"score {score} is outside {BANDS[0][0]}..{BANDS[-1][1]}, so no band "
        f"covers it. The bands are a convention and this one does not stretch")


def exposure(probability, impact) -> Exposure:
    """`Exposure = Probability x Impact` on the 5x5, with what it rests on."""
    p, i = _point("probability", probability), _point("impact", impact)
    score = p * i
    return Exposure(probability=p, impact=i, score=score, band=band_for(score))


def heat_map_cell(probability, impact) -> dict:
    """One cell of the 5x5, as a reviewer reads it off the sheet."""
    scored = exposure(probability, impact)
    return {
        "cell": f"P{scored.probability}xI{scored.impact}",
        "probability": SCALE[scored.probability - 1],
        "impact": SCALE[scored.impact - 1],
        "score": scored.score,
        "band": scored.band,
        "basis": scored.basis,
        "bands_used": [{"from": lo, "to": hi, "band": name}
                       for lo, hi, name in BANDS],
    }


def emv(probability, financial_impact) -> dict:
    """Expected Monetary Value: a real probability times a real amount.

    **Refuses an ordinal.** A `1..5` rank passed here where `0..1` belongs
    produces a figure up to five times too large and entirely plausible-looking,
    and EMV is exactly the number somebody puts in a budget.
    """
    try:
        p = float(probability)
    except (TypeError, ValueError):
        raise RiskInputRefused(
            f"probability must be a number 0..1; got {probability!r}") from None
    if not 0.0 <= p <= 1.0:
        raise RiskInputRefused(
            f"probability must be 0..1 and is {p}. A 1..5 ordinal belongs in "
            f"`exposure`; EMV is a quantity and needs a real probability")
    try:
        amount = float(financial_impact)
    except (TypeError, ValueError):
        raise RiskInputRefused(
            f"financial_impact must be a number; got {financial_impact!r}") from None

    return {
        "emv": round(p * amount, 2),
        "probability": p,
        "financial_impact": amount,
        "basis": ("a quantity, unlike the 5x5 score: it may be summed across a "
                  "portfolio. It is only as good as the probability it was "
                  "given, which is usually somebody's judgement"),
    }


def pert(optimistic, most_likely, pessimistic) -> dict:
    """`(O + 4M + P) / 6`, the beta approximation the sheet names.

    The standard deviation comes back too: an estimate without a spread invites
    the mean to be read as a commitment, which is the specific harm here.
    """
    try:
        o, m, p = (float(optimistic), float(most_likely), float(pessimistic))
    except (TypeError, ValueError):
        raise RiskInputRefused(
            "optimistic, most_likely and pessimistic must all be numbers; got "
            f"{optimistic!r}, {most_likely!r}, {pessimistic!r}") from None
    if not o <= m <= p:
        raise RiskInputRefused(
            f"expected optimistic <= most_likely <= pessimistic and got "
            f"{o} / {m} / {p}. Reordering them silently would compute a "
            f"confident answer from an estimate somebody stated wrongly")

    return {
        "estimate": round((o + 4 * m + p) / 6, 4),
        "standard_deviation": round((p - o) / 6, 4),
        "inputs": {"optimistic": o, "most_likely": m, "pessimistic": p},
        "basis": ("a weighted smoothing of three estimates, not a measurement. "
                  "The spread is reported so the mean is not read as a "
                  "commitment"),
    }
