"""
Risks Métis can observe rather than be told: the optional half of the register.

**Everything else in `risk/` works with no graph.** This module is the one that
does not, and keeping it separate is what lets the rest be a generic toolkit: a
project with no behaviour model still gets exposure, EMV, PERT and register
validation, and simply never calls this.

**It invents no risk model.** Every candidate here is something Métis already
computes for another purpose, restated in the register's vocabulary:

    change_review `critical`   behaviour a diff touches that NOTHING validates
    change_review `major`      covered on the positive path only — the
                               complement has no oracle
    coverage_report `unmeasured`  a figure that could not be produced at all

The severity grading is `change_review`'s, unchanged. Re-deriving it here would
be a second opinion from a module with less information, and the two would drift.

**Every candidate is `derived_from: model`, and that is not a formality.** A risk
raised from a coverage gap says *this behaviour is untested*. It does not say the
behaviour is likely to fail, and nothing here estimates a probability -- the
`probability` field comes back absent rather than guessed, because a number
invented to fill a column is the confident-wrong output this whole system
refuses. A person rates it, and the rating becomes theirs.

**`unmeasured` keeps its structural/operational split.** `coverage_report`
separates "the data genuinely does not exist" from "something that should have
answered did not", and flattening that into one candidate would send somebody to
restart a service over a permanent gap, or to redesign a model over an outage.
The distinction survives into `detail`.
"""
from __future__ import annotations

from metis_mcp.risk.register import MODEL, OPEN, THREAT

# `change_review`'s grades, mapped to the impact a register uses. Probability is
# deliberately absent from every one: see the module docstring.
IMPACT_FOR_SEVERITY = {
    "critical": 5,
    "major": 4,
    "minor": 2,
    "question": 2,
}

# Which category each kind of observation files under, stated once so the same
# observation never lands in two columns across two runs.
#
# **These are process categories, not the project ones.** Every observation here
# is about the quality work rather than about the project or the product: a
# change that reached behaviour nothing re-checks is a `Regression` risk, and a
# criterion written from the code it validates is a `Test design` one. They used
# to file as `Quality` and `Technical` — the two nearest entries in a
# ten-category *project* taxonomy — which put every software observation Métis
# can make into one of two buckets, neither addressable by anybody in particular.
#
# `rbs.taxonomy_of` reports the family, so a register holding all three kinds can
# still be routed.
CATEGORY_FOR = {
    # A change touched behaviour nothing validates: the tests were adequate and
    # the change moved out from under them. That is regression, precisely.
    "critical": "Regression",
    # Covered on the positive path only, so the complement has no oracle.
    "major": "Test design",
    # Validated only by criteria written from the code, which is coverage and
    # never correctness — a test design that confirms itself.
    "minor": "Test design",
    # A changed file matched nothing. The model cannot speak for it, which is a
    # statement about reach and not about the file.
    "question": "Regression",
    # The coverage figure itself could not be produced.
    "unmeasured": "Test design",
}


def _candidate(rid, description, category, impact, detail, derived_by) -> dict:
    return {
        "id": rid,
        "description": description,
        "category": category,
        "polarity": THREAT,
        # **Absent, not guessed.** Métis observed the gap; it did not forecast
        # a failure, and a filled-in probability would read as though it had.
        "probability": None,
        "impact": impact,
        "score": None,
        "owner": "",
        "response": "",
        "status": OPEN,
        "derived_from": MODEL,
        "derived_by": derived_by,
        "detail": detail,
        "needs": ("a person rates the probability and takes ownership. Until "
                  "then this is an observation, not a risk assessment"),
    }


def from_change_review(findings) -> list[dict]:
    """`change_review.findings_for` output as register candidates."""
    out = []
    for index, finding in enumerate(findings or (), start=1):
        severity = str(finding.get("severity", "question"))
        subject = finding.get("transition_id") or finding.get("file") or "?"
        out.append(_candidate(
            rid=f"RM-CR-{index:03d}",
            description=f"{finding.get('what', 'change-review finding')} ({subject})",
            category=CATEGORY_FOR.get(severity, "Test design"),
            impact=IMPACT_FOR_SEVERITY.get(severity, 2),
            detail=(f"graded `{severity}` by change_review. The grade is that "
                    f"tool's and is not re-derived here"),
            derived_by="change_review"))
    return out


def from_unmeasured(unmeasured) -> list[dict]:
    """`coverage_report`'s `unmeasured` entries as candidates.

    A figure that could not be produced is a risk about the REPORT, not about
    the behaviour, and the candidate says so — otherwise it reads as a defect in
    a system that may be perfectly healthy and merely unmeasured.
    """
    out = []
    for index, entry in enumerate(unmeasured or (), start=1):
        kind = str(entry.get("kind", "structural"))
        out.append(_candidate(
            rid=f"RM-UM-{index:03d}",
            description=(f"{entry.get('figure', 'a figure')} could not be "
                         f"measured: {entry.get('cause', 'unstated')}"),
            category=CATEGORY_FOR["unmeasured"],
            # An outage is recoverable and a structural gap is not, so they are
            # not the same impact even when they hide the same figure.
            impact=3 if kind == "structural" else 2,
            detail=(f"{kind}: "
                    + ("the data genuinely does not exist — this is a gap in "
                       "what is modelled" if kind == "structural" else
                       "something that should have answered did not — this is "
                       "an outage, not a gap")),
            derived_by="coverage_report"))
    return out


def describe(candidates) -> str:
    """What a reviewer needs before any of these become register rows."""
    if not candidates:
        return ("  no model-derived candidates. That is an answer only if a "
                "model was read — with no graph, nothing was looked at")
    lines = [f"  {len(candidates)} candidate(s), all `derived_from: model`:"]
    for c in candidates:
        lines.append(f"    {c['id']}  impact {c['impact']}  {c['category']:<12} "
                     f"{c['description'][:56]}")
    lines.append("  Probability is absent on every one. Métis observed a gap; "
                 "it did not forecast a failure.")
    return "\n".join(lines)
