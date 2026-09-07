"""The twelve areas of risk practice, and the skill that owns each.

**This exists so that "the cheat sheet is fully implemented" is a claim a test
can check rather than one somebody asserts.** The risk family was built from a
twelve-section reference; four sections had a skill and eight did not, and
nothing in the tree recorded which was which. A reader could not tell whether
`response` covered opportunities or only threats without opening it, and neither
could a test.

So the mapping is data. `test_risk.py` asserts both directions: every area names
a skill that exists on disk, and every skill in the family claims an area. A new
specialist with no area fails; an area whose skill is renamed or deleted fails.

**Two areas do not get a specialist of their own, and the reason is the placement
rule** (`docs/academy/10-where-a-thing-belongs.md`):

- **§2, the lifecycle**, is the parent. Routing between the other eleven *is*
  running the lifecycle, so a specialist for it would be a skill that does
  nothing but call the skill that called it.
- Definitions never become a skill for their own sake. §1 and §4 have specialists
  because *framing a statement* and *tailoring a taxonomy* are procedures a
  person performs; the definitions they use sit in `references/` and the
  categories in `rbs.py`. Where an area is only a definition, its `skill` names
  the skill that USES it rather than inventing a holder for a paragraph.

The two Métis-specific specialists — `requirement-risk` and `release-risk` —
deliberately carry **no** area. They are not part of the general practice; they
are what this system adds to it, and giving them a fake section number would say
the reference contained something it does not.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Area:
    """One section of the reference, and the skill responsible for it."""

    section: int
    name: str
    #: The skill that carries the procedure. `metis-risk-manager` for the
    #: lifecycle, which is the parent's own job.
    skill: str
    #: What a reader gets there that they would not get from the definition.
    covers: str


AREAS: tuple[Area, ...] = (
    Area(1, "Fundamentals", "metis-risk-manager-framing",
         "telling a risk from an issue, an assumption and a constraint, and "
         "writing it as cause -> event -> effect so it can be responded to"),
    Area(2, "The risk lifecycle", "metis-risk-manager",
         "the order the steps run in, and which specialist owns each — the "
         "parent's own job, because routing between them is running it"),
    Area(3, "Risk identification", "metis-risk-manager-identification",
         "choosing an elicitation technique, naming what it will miss, and "
         "producing candidates without rating any of them"),
    Area(4, "Risk breakdown structure", "metis-risk-manager-categorisation",
         "tailoring the taxonomy to one organisation and reading a "
         "distribution, including the categories nothing was recorded under"),
    Area(5, "Qualitative analysis", "metis-risk-manager-qualitative",
         "rating probability and impact independently and ranking on the 5x5, "
         "with no financial input"),
    Area(6, "Quantitative analysis", "metis-risk-manager-quantitative",
         "EMV, PERT with its spread, decision trees and sensitivity — and "
         "deciding the far more common case that none of them is worth it"),
    Area(7, "Threat responses", "metis-risk-manager-threat-response",
         "avoid, mitigate, transfer, accept, escalate — and the residual and "
         "secondary risk each one leaves behind"),
    Area(8, "Opportunity responses", "metis-risk-manager-opportunity-response",
         "exploit, enhance, share, accept, escalate — kept separate because a "
         "register that never records an opportunity is the normal failure"),
    Area(9, "The risk register", "metis-risk-manager-register",
         "the fields, what makes a row actionable, and keeping the register "
         "self-consistent as it is edited"),
    Area(10, "Response planning", "metis-risk-manager-response-planning",
         "turning a chosen strategy into something executable: owner, trigger, "
         "fallback, reserve"),
    Area(11, "Monitoring and control", "metis-risk-manager-monitoring",
         "indicators, review cadence, reporting, closure with a reason, and "
         "comparing the forecast against what happened"),
    Area(12, "Governance and roles", "metis-risk-manager-governance",
         "who owns a risk, who may accept one, escalation thresholds and the "
         "audit trail that makes an accepted risk a decision rather than a drift"),
)

#: **A second reference, because a second discipline governs this.** The twelve
#: areas above are general project risk management. Risk-based testing is its
#: own body of practice — ISO/IEC/IEEE 29119-2 makes risk the basis of the whole
#: test process, and the RBT taxonomy (Felderer & Ramler) sets out its stages —
#: and none of its sections exist in the project reference.
#:
#: Kept as a separate tuple rather than appended to `AREAS`, for the reason this
#: module's docstring already gives about the two Métis-specific specialists:
#: giving them a section number in the first reference "would say the reference
#: contained something it does not".
#:
#: **These cross the family boundary on purpose.** Risk-based testing is risk
#: work done by the test skills; prioritisation belongs to `metis-test-generate`
#: and coverage measurement to `metis-coverage-report`, because that is where the
#: procedure actually runs. Recording it here is what makes the wiring
#: checkable — a test asserts each named skill exists, so a renamed or deleted
#: one fails rather than quietly leaving an area unowned.
TESTING_AREAS: tuple[Area, ...] = (
    Area(1, "Product risk assessment", "metis-risk-manager-product-risk",
         "typing a risk item, gathering the technical factors from the model "
         "and asking for the business ones — PRISMA's split"),
    Area(2, "Risk-based test prioritisation", "metis-test-generate",
         "ordering what to test by what would go unnoticed, rather than by the "
         "order the model happens to be in"),
    Area(3, "Risk-based coverage measurement", "metis-coverage-report",
         "whether the uncovered part is the part that matters, reported as a "
         "pivot rather than as a weighted percentage"),
    Area(4, "Residual risk and the exit decision",
         "metis-risk-manager-release-risk",
         "what is left un-mitigated, as evidence against a threshold somebody "
         "set — never as a verdict"),
    Area(5, "Risk re-assessment from execution",
         "metis-risk-manager-monitoring",
         "comparing what was assessed against what actually happened, which is "
         "the step the lifecycle names and nobody performs"),
)

#: Specialists that carry no area in the PROJECT reference. `release-risk` now
#: owns a testing area, and is kept here too: it is beyond the twelve either way.
BEYOND_THE_REFERENCE: tuple[str, ...] = (
    "metis-risk-manager-requirement-risk",
    "metis-risk-manager-release-risk",
    "metis-risk-manager-product-risk",
)


def area_for(skill: str) -> Area | None:
    return next((a for a in AREAS if a.skill == skill), None)


def testing_area_for(skill: str) -> Area | None:
    return next((a for a in TESTING_AREAS if a.skill == skill), None)


def describe() -> dict:
    """The map, for a tool and for a test."""
    return {
        "areas": [{"section": a.section, "name": a.name, "skill": a.skill,
                   "covers": a.covers} for a in AREAS],
        "testing_areas": [{"section": a.section, "name": a.name,
                           "skill": a.skill, "covers": a.covers}
                          for a in TESTING_AREAS],
        "beyond_the_reference": list(BEYOND_THE_REFERENCE),
        "means": (
            "two references, not one. `areas` is the twelve areas of general "
            "project risk practice, each owned by one skill. `testing_areas` is "
            "risk-based testing (ISO/IEC/IEEE 29119-2), which the project "
            "reference does not contain and which is where a quality engineer "
            "spends their time — some of it owned by the test skills, because "
            "that is where the procedure runs"),
    }
