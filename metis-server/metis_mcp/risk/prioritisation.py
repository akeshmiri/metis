"""
Risk-based test prioritisation, risk-weighted coverage, and residual risk.

**What risk-based testing actually asks for.** ISO/IEC/IEEE 29119-2 and ISTQB
both define the approach the same way: test activities are *selected, prioritised
and managed* by risk, and testing stops against a **residual risk** threshold
rather than a coverage percentage. Métis had every input for that and no module
that did it — risk consumed coverage, and coverage never consumed risk.

Three things live here, and they are the three the standards name.

**1. Ordering, by a tuple and never by a product.** `detection.MEANS` refuses to
be multiplied into an exposure score, and this module is where that refusal is
kept. Three ordinals multiplied is an RPN, and an RPN's flaw is well documented:
1x5x5 and 5x5x1 both read as 25, so the number hides which axis is the bad one
and therefore what to do about it. Ordering is lexicographic instead — the axis
priority is stated, visible, and reversible:

    detectability first   a behaviour nothing would notice breaking is where a
                          new test buys the most, which is the whole premise of
                          risk-based testing
    then defect-proneness more branching and more coupling means more to get
                          wrong, per the defect-prediction literature
    then id               so the order is byte-identical run to run (P-7)

The third key is not decoration. `path_generation` is deterministic BFS in id
order precisely so a regenerated suite diffs cleanly, and an ordering that broke
that would make every run's output look changed.

**2. Risk-weighted coverage, as a pivot and never as an average.**
`exposure.ORDINAL_BASIS` says the 5x5 score "cannot be summed, averaged, or
compared across projects", and a "risk-weighted coverage percentage" would do all
three at once. What is honest is a cross-tabulation: *of the N Very-High-band
behaviours, k are uncovered*. That answers the question a percentage pretends to
— is the uncovered part the part that matters — without inventing a quantity.

**3. Residual risk, which is what an exit decision is made against.** Two
populations, kept apart because they need different actions: uncovered-and-risky
(nobody would notice) and covered-and-failing (somebody did notice, and it is
still broken). A single "residual risk" number merging them would let a rising
failure count be cancelled by rising coverage.

**This module sets no probability and computes no verdict.** `exit_criteria`
reports evidence against a threshold a person supplied at planning time; it
never decides to ship. `steps/01-plan.md` is where the threshold comes from, and
`specialists/release-risk` states the rule this obeys: never compute a verdict
from coverage, because covered-and-failing is real.

Pure: ledgers, scores and thresholds in, dictionaries out.
"""
from __future__ import annotations

from metis_mcp.risk.detection import UNNOTICED, Detection

#: Bands that a residual-risk threshold defaults to caring about. Named, not
#: hardcoded into the logic, so a project can widen or narrow it in one place.
ATTENTION_BANDS = ("High", "Very High")

ORDER_MEANS = (
    "ordered by detectability first and defect-proneness second, then by id so "
    "the order is stable. It is a lexicographic sort, NOT a product: three "
    "ordinals multiplied give an RPN, and 1x5x5 and 5x5x1 both read as 25, "
    "which hides which axis is the bad one and therefore what to do"
)

COVERAGE_MEANS = (
    "a cross-tabulation, not a weighted percentage. An ordinal band cannot be "
    "averaged (exposure.ORDINAL_BASIS), so this reports how many items in each "
    "band are uncovered rather than folding band and coverage into one figure"
)

RESIDUAL_MEANS = (
    "two populations, deliberately not summed: behaviour nothing would notice "
    "breaking, and behaviour something noticed IS broken. They need different "
    "actions -- a test, and a fix -- and one total would let a rising failure "
    "count be cancelled by rising coverage"
)


def order(detections: dict[str, Detection],
          technical: dict[str, dict] | None = None) -> list[dict]:
    """Risk order for test selection. Deterministic, and says what it sorted by.

    `detections` maps a transition id to a `Detection`; `technical` maps one to a
    `product.technical_profile` result. A transition missing from `technical` is
    ordered on detectability alone rather than dropped — an item nobody profiled
    is not an item at low risk.
    """
    profiles = technical or {}
    rows = []
    for tid, found in detections.items():
        profile = profiles.get(tid) or {}
        rows.append({
            "transition_id": tid,
            "detection": found.score,
            "detection_label": found.label,
            "failing": found.failing,
            "technical_score": profile.get("score"),
            "technical_band": profile.get("band"),
        })

    # `-detection` and `-technical` put the worst first; `tid` last makes the
    # whole order total, so two items alike on both axes never swap between runs.
    rows.sort(key=lambda r: (-r["detection"], -(r["technical_score"] or 0),
                             r["transition_id"]))
    for position, row in enumerate(rows, start=1):
        row["rank"] = position
    return rows


def weighted_coverage(detections: dict[str, Detection],
                      technical: dict[str, dict],
                      unmeasured=()) -> dict:
    """Is the uncovered part the part that matters? Reported as a pivot.

    The question a coverage percentage is usually asked to answer and cannot:
    80% covered is a different fact depending on which 20% is missing.
    """
    bands: dict[str, dict] = {}
    for tid, found in detections.items():
        band = (technical.get(tid) or {}).get("band") or "unprofiled"
        cell = bands.setdefault(band, {"total": 0, "uncovered": 0,
                                       "failing": 0, "transitions": []})
        cell["total"] += 1
        if found.score == UNNOTICED:
            cell["uncovered"] += 1
            cell["transitions"].append(tid)
        if found.failing:
            cell["failing"] += 1

    for cell in bands.values():
        cell["transitions"].sort()

    return {
        "by_band": bands,
        # Never merged into the pivot: an unmeasured item belongs to no band's
        # covered or uncovered count, and putting it in either is a claim.
        "unmeasured": sorted(unmeasured),
        "means": COVERAGE_MEANS,
    }


def residual(detections: dict[str, Detection],
             technical: dict[str, dict],
             attention_bands=ATTENTION_BANDS,
             unmeasured=()) -> dict:
    """What is left un-mitigated, as two populations that need different work."""
    attention = set(attention_bands)
    unnoticed, broken = [], []

    for tid, found in detections.items():
        band = (technical.get(tid) or {}).get("band")
        if found.score == UNNOTICED and band in attention:
            unnoticed.append({"transition_id": tid, "band": band,
                              "needs": "a test — nothing would notice a break here"})
        if found.failing:
            broken.append({"transition_id": tid, "band": band,
                           "needs": "a fix — a test that ran reported this failing"})

    unnoticed.sort(key=lambda r: r["transition_id"])
    broken.sort(key=lambda r: r["transition_id"])
    return {
        "unnoticed": unnoticed,
        "failing": broken,
        "attention_bands": sorted(attention),
        "unmeasured": sorted(unmeasured),
        "means": RESIDUAL_MEANS,
    }


#: PRISMA's product risk matrix exists to produce *differentiated* test
#: approaches — not one approach applied harder. The band decides how many of
#: the techniques `test_design` offers are worth applying.
#:
#: A starting point a person adjusts, not an allocation. The bands come from
#: thresholds somebody chose in `product.THRESHOLDS`; a project that disagrees
#: changes them there rather than arguing case by case.
DEPTH_FOR_BAND: dict[str, str] = {
    "Very High": "every technique — boundaries, each partition, the negative cases",
    "High": "boundaries and partitions; negatives on the paths that carry data",
    "Medium": "one case per partition",
    "Low": "one positive case, and say that is what it is",
}

DEPTH_MEANS = (
    "what the risk band WARRANTS, which is a different question from what "
    "`classify_depth` reports about what is achievable. A behaviour that cannot "
    "be tested deeply and warrants deep testing is the interesting case, and "
    "neither figure finds it alone"
)


def warranted_depth(band: str | None) -> dict:
    """How much testing this band justifies, and the caveat that goes with it."""
    if not band:
        return {"band": None, "approach": None,
                "means": "unprofiled — no band, so no warrant either way"}
    return {"band": band, "approach": DEPTH_FOR_BAND.get(band),
            "means": DEPTH_MEANS}


def depth_gaps(warranted: dict[str, str], achievable: dict[str, str]) -> list[dict]:
    """Behaviour that warrants deep testing and cannot receive it.

    The join neither figure makes alone. `classify_depth` says a transition is
    `partial` because its deeper targets do not all generate; the risk band says
    it is where a defect would go unnoticed. Together they name the behaviour a
    person has to cover another way, which is exactly what an unverifiable guard
    or an unreachable partition leaves behind.
    """
    gaps = []
    for tid, band in sorted(warranted.items()):
        if band not in ("High", "Very High"):
            continue
        reached = achievable.get(tid)
        # `viability.PARTIAL` and `POSITIVE_ONLY` are the two that mean "a case
        # exists for the path and not for its conditions". `FULL` warrants
        # nothing further and an absent verdict means the transition did not
        # generate at all, which `coverage` already reports.
        if reached in ("partial", "positive-only"):
            gaps.append({"transition_id": tid, "band": band,
                         "achievable_depth": reached,
                         "needs": "warrants deeper testing than the model can "
                                  "generate — cover it another way, and say so"})
    return gaps


def exit_criteria(residual_report: dict, thresholds: dict | None = None) -> dict:
    """Evidence against a threshold. **Never a verdict.**

    ISO 29119's exit decision is made against residual risk, and the threshold
    is a person's — `steps/01-plan.md` settles it before the first risk is
    written. With no threshold supplied this reports what there is and says
    plainly that nothing here can judge it, which is the same shape
    `release_risk` uses for a missing appetite.
    """
    limits = thresholds or {}
    unnoticed = len(residual_report.get("unnoticed") or [])
    failing = len(residual_report.get("failing") or [])
    unmeasured = len(residual_report.get("unmeasured") or [])

    if not limits:
        return {
            "decidable": False,
            "unnoticed": unnoticed,
            "failing": failing,
            "unmeasured": unmeasured,
            "means": "NO THRESHOLD — nothing here can say whether this is "
                     "acceptable, only what it is. The threshold is set at "
                     "planning time and belongs to a person",
        }

    breaches = []
    for name, count in (("unnoticed", unnoticed), ("failing", failing),
                        ("unmeasured", unmeasured)):
        limit = limits.get(name)
        if limit is not None and count > limit:
            breaches.append(f"{name}: {count} exceeds the agreed {limit}")

    return {
        "decidable": True,
        "unnoticed": unnoticed,
        "failing": failing,
        "unmeasured": unmeasured,
        "thresholds": dict(limits),
        "breaches": breaches,
        "within_threshold": not breaches,
        "means": "evidence against the threshold somebody agreed, not a "
                 "recommendation to ship. Coverage supports no verdict on its "
                 "own (C-11) and this does not become one by being compared",
    }
