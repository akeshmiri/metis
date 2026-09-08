"""The aspects a stated intent is read from, and the skill that owns each.

Same shape and same purpose as `risk/areas.py` and `design/areas.py`: a family
with nothing recording which skill covers which reading is a family where a
reader cannot tell whether `scope` covers the wording without opening it, and
neither can a test. `test_analysis.py` asserts both directions.

**Two of the four aspects are owned outside this family, and that is the design.**
The requirement reading is `metis-knowledge-capture`'s -- it already turns prose
into atomic criteria and reconciles them, and a second copy here would drift from
it. The design and risk readings belong to `metis-test-design` and
`metis-risk-manager-requirement-risk` for the same reason. The business analyst
**consults** them; it does not reimplement them.

That is what "pass it to test designer and risk manager for a more detailed
review" means concretely, and recording it here is what makes the hand-off a
checked fact rather than a sentence in a prompt.
"""
from __future__ import annotations

from dataclasses import dataclass

from metis_mcp.analysis.gaps import CONSUMER, DESIGN, INTENT, REQUIREMENT, RISK


@dataclass(frozen=True)
class Aspect:
    """One reading of a stated intent, and who performs it."""

    key: str
    name: str
    skill: str
    #: What this reading sees that none of the others can.
    sees: str
    #: Whether the skill is inside the business-analyst family.
    local: bool


ASPECT_OWNERS: tuple[Aspect, ...] = (
    Aspect(INTENT, "Is there a need here, and did anybody say how it behaves?",
           "metis-business-analyst-intent",
           "a need with no statement, a specification belonging to no need, a "
           "term nobody has defined — the claims that cannot be represented at "
           "all", local=True),
    Aspect(REQUIREMENT, "Can two people satisfy this the same way?",
           "metis-knowledge-capture",
           "wording that is not EARS-conformant and criteria that are "
           "unmeasurable or non-atomic — already this skill's whole job, so a "
           "second copy here would drift from it", local=False),
    Aspect(DESIGN, "Could anything ever test this?",
           "metis-test-design",
           "a claim that is well worded, agreed, and impossible to verify. "
           "Asking before the work starts costs one question; asking after "
           "costs the build", local=False),
    Aspect(CONSUMER, "Who reads what this produces?",
           "metis-business-analyst-scope",
           "a behaviour feeding a report is tested differently from one feeding "
           "another system — different levels, different data conditions, "
           "different obligations. Classified from recovered facts (a media "
           "type, a paging parameter, a collection shape) and `unknown` "
           "wherever none of them fires, because a stated consumer is a better "
           "fact than an inferred one", local=True),
    Aspect(RISK, "What does being wrong cost?",
           "metis-risk-manager-requirement-risk",
           "business criticality and volatility — the impact and probability "
           "ratings, neither of which any amount of analysis produces",
           local=False),
)

#: Owned by the parent rather than by an aspect, for the placement rule's
#: reason: consolidating the four readings IS the analysis, so a specialist for
#: it would be a skill that only calls its caller.
CONSOLIDATION = "metis-business-analyst"

#: The second local reading, which is not one of the four gap aspects: scope,
#: actors, entities and what is deliberately out of scope. It produces context
#: rather than gaps, which is why it has no entry above.
SCOPE_SKILL = "metis-business-analyst-scope"


def owner_of(aspect: str) -> str:
    return next((a.skill for a in ASPECT_OWNERS if a.key == aspect), "")


def consulted() -> tuple[str, ...]:
    """The skills outside this family that the analysis consults."""
    return tuple(a.skill for a in ASPECT_OWNERS if not a.local)


def describe() -> dict:
    """The map, for a tool and for a test."""
    return {
        "aspects": [{"key": a.key, "name": a.name, "skill": a.skill,
                     "sees": a.sees, "local": a.local} for a in ASPECT_OWNERS],
        "consolidation": CONSOLIDATION,
        "scope_skill": SCOPE_SKILL,
        "consulted": list(consulted()),
        "means": (
            "two of the four readings are owned outside this family on purpose. "
            "The business analyst consults `metis-knowledge-capture`, "
            "`metis-test-design` and `metis-risk-manager-requirement-risk` "
            "rather than reimplementing what they already do — a second copy of "
            "any of the three would drift from the one that runs"),
    }
