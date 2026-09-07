"""
The Risk Breakdown Structure: the categories a risk is filed under.

**A taxonomy, not a judgement.** Which category a risk belongs to is a decision
a person makes; whether the category they named EXISTS is a question with a
determinate answer, and that is the half this module holds. A free-text category
column is how a register ends up with `Tech`, `Technical` and `technical` as
three separate lines in a report nobody trusts.

**Ten categories, flat, and the source sheet is ambiguous about that.** It draws
them in two tiers -- Strategic / Financial / Technical / Operational / Schedule
above Cost / Quality / Resource / Procurement / External -- and then charts all
ten as peers in a single distribution. Peers is the reading taken here, because
it is the one the sheet's own numbers use, and because a two-tier RBS whose lower
tier is not actually a decomposition of the upper one would be a hierarchy in
appearance only: `Cost` is not a kind of `Strategic`.

**A deployment may replace this list and that is expected.** An RBS is
organisational: a regulated bank and a games studio genuinely have different
top-level risks. `validate_category` takes the taxonomy it checks against, so
the default here is a starting point rather than a rule, and a project that
narrows it says so in one place.
"""
from __future__ import annotations

# The ten, in the sheet's own order. Each carries what it is FOR, because a bare
# noun invites everything ambiguous into whichever column is nearest.
CATEGORIES: dict[str, str] = {
    "Strategic": "the project's fit with the goal it was funded for — a change "
                 "of direction, a competing initiative, a sponsor who leaves",
    "Financial": "funding and money movement — budget withdrawal, currency, "
                 "payment terms. NOT the cost of a specific overrun, which is "
                 "`Cost`",
    "Technical": "the solution itself — architecture, integration, performance, "
                 "technical debt, a dependency that does not do what it claims",
    "Operational": "running the thing once built — support, capacity, process, "
                   "handover to a team that was not consulted",
    "Schedule": "time — sequencing, dependency slippage, a fixed date somebody "
                "else set",
    "Cost": "the estimate for this work being wrong, as distinct from the "
            "funding for it disappearing (`Financial`)",
    "Quality": "the work meeting its stated criteria — defects, rework, an "
               "acceptance criterion nobody can test",
    "Resource": "people and equipment — availability, skills, contention with "
                "other projects",
    "Procurement": "third parties and contracts — vendor delivery, licensing, "
                   "terms that bind before anyone has read them",
    "External": "outside the project's control — regulation, market, weather, "
                "a supplier's own supplier",
}

#: **The product taxonomy, which is not the project one.** The ten categories
#: above classify risks to the *project* — a vendor, a sponsor, a date. A risk to
#: the *product* is "this endpoint's authorisation is asserted by nothing", and
#: the only entry above it could take is `Quality`, which would put every
#: software risk a team has in one bucket.
#:
#: These are ISO/IEC 25010's product quality characteristics, used as an RBS
#: rather than invented, for the reason `risk-breakdown-structure.md` gives for
#: having an RBS at all: it **prompts** (walking the characteristics finds what
#: unprompted recall misses) and it **reveals absence** (nobody has asked a
#: single question about portability is a finding).
#:
#: Kept separate from `CATEGORIES` and never merged into one distribution. A
#: chart mixing "Procurement" with "Security" describes no decision anybody
#: makes: they are rated by different people against different objectives, and
#: merging them is the same class of error as merging derivations.
PRODUCT_CATEGORIES: dict[str, str] = {
    "Functional suitability": "whether it does what it is supposed to — "
                              "completeness, correctness, appropriateness. The "
                              "default, and the one most registers stop at",
    "Performance efficiency": "time behaviour, resource use, capacity under the "
                              "load it will actually meet",
    "Compatibility": "co-existence and interoperability — the other system it "
                     "has to work beside, and the one it has to talk to",
    "Interaction capability": "usability — whether a person can operate it, "
                              "learn it, and recover from their own mistakes. "
                              "ISO 25010:2023's name for what 25010:2011 called "
                              "Usability",
    "Reliability": "maturity, availability, fault tolerance, recoverability — "
                   "behaviour when something it depends on is already broken",
    "Security": "confidentiality, integrity, non-repudiation, accountability, "
                "authenticity. Not a synonym for authentication",
    "Maintainability": "modularity, reusability, analysability, modifiability, "
                       "testability. **Testability belongs here**, which is why "
                       "an untestable requirement is a product risk and not only "
                       "a process complaint",
    "Flexibility": "adaptability, scalability, installability, replaceability — "
                   "what it costs to move it somewhere it was not built for",
    "Safety": "operational constraint, risk identification, fail-safe, hazard "
              "warning. Absent from 25010:2011 and added because software that "
              "can hurt somebody is not merely unreliable",
}

#: **The process and delivery taxonomy — how the work of assuring quality
#: fails, as opposed to how the product does.**
#:
#: `PRODUCT_CATEGORIES` classifies what the software can be wrong about.
#: `CATEGORIES` classifies what can go wrong with the project as a project — a
#: sponsor, a vendor, a currency. Neither has anywhere to put "the test
#: environment drifts from production" or "the suite is so flaky nobody reads
#: it", and those are the risks a quality engineer actually carries.
#:
#: Drawn from the test process ISO/IEC/IEEE 29119-2 defines and from what
#: delivery practice has learned since: every entry names something that makes a
#: quality signal wrong, absent, or too late to act on.
#:
#: **Why these are separate from the other two rather than folded in.** A
#: process risk is owned by the people who build the pipeline, a product risk by
#: the people who build the feature, and a project risk by the people who fund
#: it. Merging them produces a chart in which no row is addressable by anyone.
PROCESS_CATEGORIES: dict[str, str] = {
    "Requirements": "what the system is supposed to do being ambiguous, "
                    "untestable, contradictory or absent — a requirement no "
                    "criterion can validate is a defect nobody can find",
    "Test design": "the tests that exist not asserting what matters — positive "
                   "paths only, no oracle for the complement, a guard nobody "
                   "can verify",
    "Test data": "data that is unavailable, unrepresentative, or cannot legally "
                 "be used. A correct test on the wrong data passes and proves "
                 "nothing",
    "Test environment": "an environment that is missing, shared, contended, or "
                        "drifted from production. The commonest reason a green "
                        "suite and a broken release coexist",
    "Automation": "the suite itself — flakiness, runtime, maintenance debt. A "
                  "suite people rerun until it passes has become a source of "
                  "false confidence rather than of evidence",
    "Regression": "change reaching behaviour nothing re-checks. Distinct from "
                  "`Test design`: the tests were adequate, and the change moved "
                  "out from under them",
    "Release and deployment": "getting it out and getting it back — rollback "
                              "capability and time, migration, cadence, feature "
                              "flags left on",
    "Observability": "not being able to tell, in production, that something is "
                     "wrong. The last line when every earlier one has been "
                     "crossed",
    "Technical debt": "the code becoming harder to change or to test. It is a "
                      "risk rather than an inconvenience because it raises the "
                      "cost of every future response",
    "Capability": "the people and skills the quality work needs — review "
                  "bandwidth, domain knowledge, who can write the test that is "
                  "missing",
}

# The pairs most often confused, and the question that separates them. Named
# because a taxonomy that only lists its terms leaves the boundaries to be
# rediscovered in every review meeting.
BOUNDARIES = (
    ("Financial", "Cost",
     "is the MONEY at risk, or the ESTIMATE? Funding withdrawn is Financial; "
     "the work costing more than stated is Cost"),
    ("Technical", "Quality",
     "would it be wrong even if built perfectly to spec? That is Technical. "
     "Built badly against a good spec is Quality"),
    ("Operational", "Resource",
     "is the problem the PROCESS or the PEOPLE? Contention for a specialist is "
     "Resource; nobody owning the runbook is Operational"),
    ("Procurement", "External",
     "is there a contract? A vendor you have terms with is Procurement; a "
     "regulator you do not is External"),
)


#: Every category, across all three taxonomies, for **validation only**.
#:
#: A register holds all three kinds of risk and a row is legal if its category
#: exists somewhere. That is a different question from what a distribution may
#: be drawn over, and the separation is deliberate: `validate_category` asks
#: "is this a real category", `distribution` asks "how are risks spread across
#: ONE taxonomy". Merging the second is the error C-11 is one instance of;
#: merging the first is what lets one register hold a vendor delay, an
#: untestable requirement and a flaky suite without needing three registers.
#:
#: Asserted disjoint in `test_risk.py`: one name meaning two things in two
#: taxonomies would make `taxonomy_of` a coin toss.
ALL_CATEGORIES: dict[str, str] = {
    **CATEGORIES, **PRODUCT_CATEGORIES, **PROCESS_CATEGORIES,
}

TAXONOMIES: dict[str, dict[str, str]] = {
    "project": CATEGORIES,
    "product": PRODUCT_CATEGORIES,
    "process": PROCESS_CATEGORIES,
}


def taxonomy_of(name: str) -> str | None:
    """Which family a category belongs to, so a reader knows who owns the row.

    A process risk is owned by the people who build the pipeline, a product risk
    by the people who build the feature, and a project risk by the people who
    fund it. A register that cannot say which is one nobody can route.
    """
    for family, categories in TAXONOMIES.items():
        if name in categories:
            return family
    return None


class UnknownCategory(ValueError):
    """A category outside the taxonomy. Named, never silently accepted."""


def validate_category(name: str, taxonomy: dict | None = None) -> str:
    """The canonical category, or a refusal naming the nearest real ones.

    Case-insensitive on the way in and canonical on the way out, so `technical`
    and `Technical` cannot become two rows in a distribution. It does NOT guess
    past that: `Tech` is refused rather than resolved, because a taxonomy that
    accepts abbreviations accepts the next one too and the column stops meaning
    anything.
    """
    # Defaults to EVERY taxonomy: a register legitimately holds project,
    # product and process risks, and a row is legal if its category exists in
    # any of them. `distribution` below keeps the project default, because a
    # chart is drawn over one family or it describes no decision anybody makes.
    known = taxonomy or ALL_CATEGORIES
    if name is not None and not isinstance(name, str):
        # `distribution` takes category NAMES, and a caller holding a register
        # naturally passes the risk dicts instead. Saying so beats
        # `'dict' object has no attribute 'strip'` three frames down.
        raise UnknownCategory(
            f"expected a category name and got {type(name).__name__}. If you "
            f"have a register, pass `[r['category'] for r in register]`.")
    wanted = (name or "").strip()
    if not wanted:
        raise UnknownCategory(
            f"no category given. One of: {', '.join(sorted(known))}")

    for candidate in known:
        if candidate.lower() == wanted.lower():
            return candidate

    near = sorted(c for c in known if c.lower().startswith(wanted[:3].lower()))
    hint = f" Did you mean {' or '.join(near)}?" if near else ""
    raise UnknownCategory(
        f"{wanted!r} is not in the risk breakdown structure.{hint} "
        f"One of: {', '.join(sorted(known))}. Adding a category is a change to "
        f"the taxonomy, not to one risk")


def distribution(categories, taxonomy: dict | None = None) -> dict:
    """How a register spreads across the RBS, with the empty ones named.

    **A category with no risks is reported, not omitted.** An RBS exists to
    prompt "have we looked here?", and a chart that silently drops `External`
    because nobody raised one looks identical to a project that considered it
    and found nothing.
    """
    known = taxonomy or CATEGORIES
    counts = {name: 0 for name in known}
    unknown: list[str] = []
    for raw in categories or ():
        try:
            counts[validate_category(raw, known)] += 1
        except UnknownCategory:
            unknown.append(str(raw))

    total = sum(counts.values())
    return {
        "counts": counts,
        "empty": sorted(n for n, c in counts.items() if c == 0),
        "unknown": sorted(set(unknown)),
        "total": total,
        "means": ("an empty category is listed rather than dropped: 'nobody "
                  "raised one' and 'we considered it and found nothing' look "
                  "the same on a chart that omits it"),
    }
