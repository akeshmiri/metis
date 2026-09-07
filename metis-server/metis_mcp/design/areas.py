"""The areas of test design practice, and the skill that owns each.

**This exists so that "the design family is complete" is a claim a test can
check rather than one somebody asserts.** It is `risk/areas.py` one domain over,
and it was written for the same reason: a family of nine sections and eight
skills with nothing recording which skill covers which activity is a family
where a reader cannot tell whether `technique` covers data conditions without
opening it, and neither can a test.

So the mapping is data. `test_design_areas.py` asserts both directions: every
area names a skill that exists on disk, and every skill in the family claims an
area. A new specialist with no area fails; an area whose skill is renamed or
deleted fails.

**Two references, because two things are being mapped.**

`AREAS` is the test design and implementation process -- the activity sequence
whose named outputs are the test basis, the feature sets, the test conditions,
the coverage items, the test cases, the test sets and the test procedures. That
sequence is the spine of ISO/IEC/IEEE 29119-2's dynamic test processes, and it
crosses this family's boundary on purpose: **the last three belong to
`metis-test-generate`**, because that is where the procedure actually runs.
Design derives conditions and coverage items; generation turns them into cases,
sets and procedures. Recording the crossing here is what makes the hand-off
checkable rather than implied.

`ATTRIBUTE_AREAS` is what the process does not enumerate. A quality attribute --
authorisation, load -- and an interface boundary -- a contract, a cross-surface
journey -- are designed by different people reading different evidence, and the
activity sequence above has nowhere to put them. Kept separate rather than
appended, for the reason `risk/areas.py` gives about its own second tuple:
giving them a position in the first would say the process contained something it
does not.

**One area does not get a specialist, and the reason is the placement rule**
(`docs/academy/10-where-a-thing-belongs.md`): the uncertainty ledger is the
parent's own job. Consolidating what every section could not state *is* running
the design, so a specialist for it would be a skill that only calls its caller.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Area:
    """One activity of test design, and the skill responsible for it."""

    ordinal: int
    name: str
    #: The skill that carries the procedure.
    skill: str
    #: The design section it produces, where it produces one. Empty for the
    #: three that cross into generation: those produce test cases, not sections.
    section: str
    #: What a reader gets there that they would not get from the definition.
    covers: str


AREAS: tuple[Area, ...] = (
    Area(1, "Test basis identification", "metis-test-design", "basis",
         "which requirement, criteria and specification this design "
         "demonstrates, quoted rather than paraphrased, with the provenance "
         "that says whether they are independent of the code"),
    Area(2, "Feature set derivation", "metis-test-design", "basis",
         "grouping the behaviour into what will be designed together. Métis "
         "derives features from evidence rather than accepting an authored "
         "grouping, so this is read from the model and not restated"),
    Area(3, "Test condition derivation", "metis-test-design-technique",
         "technique",
         "the conditions each behaviour puts on its inputs, taken from the "
         "guard itself — and the refusal where a guard cannot be partitioned"),
    Area(4, "Test coverage item derivation", "metis-test-design-technique",
         "technique",
         "how many distinct things a chosen technique asks for: partitions, "
         "boundaries, decision table rules, pairs"),
    Area(5, "Test data requirements", "metis-test-design-data", "data",
         "what the data must satisfy, as a condition on the accepted space. "
         "Never a value, and never a fixture (M-9)"),
    Area(6, "Test level and environment assignment",
         "metis-test-design-levels", "levels",
         "where each condition is asserted, what already reaches it, and what "
         "cannot be automated at all — assignment, which is not execution"),
    Area(7, "Defect-proneness profiling", "metis-test-design-levels", "profile",
         "the factors behind the band — branching, coupling, size, repair "
         "history — and the design response each one asks for, which is never "
         "the same as 'test it more'"),
    Area(8, "Setup and data requirements", "metis-test-design-levels", "setup",
         "what reaching each behaviour costs, computed from the setup chain "
         "rather than guessed from a business verb — and the pattern choice "
         "left to whoever knows the environment"),
    # The crossing. These three run in generation, and saying so here is what
    # makes the hand-off a checked fact rather than an assumption.
    Area(9, "Test case derivation", "metis-test-generate", "",
         "one path, one case, one assertion (T-1a) — rendered from an approved "
         "model rather than from this document"),
    Area(10, "Test set assembly", "metis-test-generate", "",
         "the batch, ordered by the same risk keys this design is ordered by, "
         "and shown in full before the G2 gate"),
    Area(11, "Test procedure derivation", "metis-test-generate", "",
         "the executable form — a `.feature` file as specification, never step "
         "definitions binding it to a system"),
)


#: What the design process does not enumerate, and Métis designs anyway.
ATTRIBUTE_AREAS: tuple[Area, ...] = (
    Area(1, "Authorisation and authentication", "metis-test-design-security",
         "security",
         "the identity and authority each call requires, from what was "
         "recovered — and the negative condition beside it, which is the half "
         "an API suite usually lacks"),
    Area(2, "Load and performance candidacy", "metis-test-design-performance",
         "performance",
         "which calls are worth driving under load, and the `no-basis` refusal "
         "where nobody has sized them"),
    Area(3, "Contract and interface design", "metis-test-design-contract",
         "contract",
         "what an endpoint declares against what its code does, with a "
         "deviation reported as a case and a question rather than a defect"),
    Area(4, "Cross-surface journey design", "metis-test-design-journey",
         "journey",
         "which UI action invokes which call, and the guard a UI action "
         "inherits from the API beneath it (M-5c)"),
)


#: Carried by the parent, and in neither reference. The uncertainty ledger is
#: what this system adds to test design practice: a design that declares what it
#: could not state, rather than one whose gaps read as decisions.
BEYOND_THE_REFERENCE: tuple[tuple[str, str, str], ...] = (
    # **Not an activity of the design process either, and it is the one Métis
    # adds that changes what every other section means.** A positive case says
    # what the system does; counted as coverage for what it must reject, bound
    # or refuse, it excuses the gaps somebody is paying for tests to find. The
    # eight classes come from `shared/knowledge/requirement-condition-coverage.md`
    # — a rule that was applied by a model and checked by nothing until it
    # became a section.
    # **The endpoint-shaped half of the same completeness question**, and it is
    # the one the design process has no activity for: the eight classes ask
    # whether a decision was made, this asks whether the model carries the
    # behaviour a specific endpoint's own shape obliges it to have. It stays
    # with the parent because it crosses three specialists' territories —
    # authorisation, contract and data — and belongs to none of them.
    # **The only section Métis draws rather than tabulates.** The practice this
    # family was compared against mandates a use-case diagram and a flow chart
    # on every design, drawn by hand; Métis has the machine already, so it
    # renders what it recovered and draws nothing it did not — no actors, no
    # inferred grouping. It belongs to the parent because it is the whole scope
    # rather than any one specialist's slice of it.
    # **A statement about the document rather than about the system**, which is
    # why it belongs to the parent: it says which named work product each
    # section answers, and where the answer is partial, what is missing. No
    # specialist owns it because it is about all of them at once.
    ("metis-test-design", "compliance",
     "which ISO/IEC/IEEE 29119-3 and IEEE 829 work product each section "
     "answers, and the three that are out of scope with the reason — an "
     "execution artefact is not a design's to produce"),
    ("metis-test-design", "machine",
     "the state machine in scope, drawn from the recovered states and "
     "transitions — or a stated count of how many were left out, because a "
     "diagram showing some of them with no note looks complete"),
    ("metis-test-design", "obligations",
     "the negative behaviour a path parameter, a security requirement, a body "
     "or an enumerated input obliges an endpoint to have — judged against the "
     "outcomes actually recovered, and reported as a question where none is"),
    ("metis-test-design", "conditions",
     "every behaviour against the eight condition classes, each with an "
     "explicit decision and a reason — including the classes that do not apply, "
     "which is the half that must not silently disappear"),
    ("metis-test-design", "uncertainty",
     "every input nobody supplied, what its absence means, and which section it "
     "silenced — the section that makes the rest safe to read"),
    # **Not an activity of the design process, and giving it a number there
    # would say the process contained it.** The short-circuit reduction is
    # Métis's own (spec §2.4a, GD-1..GD-9): a request that fails authentication
    # never reaches authorisation, so varying authorisation underneath it is
    # unobservable — which is what collapses the product. It is owned by
    # `technique` because it bounds the coverage items that specialist derives,
    # rather than being a second specialist asking half the same question.
    ("metis-test-design-technique", "dimensions",
     "the evaluation chain each behaviour is guarded by, what covering it costs "
     "bounded against the full product, and GD-9's refusal where precedence "
     "could not be recovered"),
)


def area_for(skill: str) -> Area | None:
    return next((a for a in AREAS if a.skill == skill), None)


def attribute_area_for(skill: str) -> Area | None:
    return next((a for a in ATTRIBUTE_AREAS if a.skill == skill), None)


def owner_of(section: str) -> str:
    """The skill that owns one design section.

    Read from the areas rather than from `sections.py`, so the two have to agree
    — `test_design_areas.py` asserts they do, in both directions.
    """
    for area in AREAS + ATTRIBUTE_AREAS:
        if area.section == section:
            return area.skill
    for skill, owned, _covers in BEYOND_THE_REFERENCE:
        if owned == section:
            return skill
    return ""


def describe() -> dict:
    """The map, for a tool and for a test."""
    return {
        "areas": [{"ordinal": a.ordinal, "name": a.name, "skill": a.skill,
                   "section": a.section, "covers": a.covers} for a in AREAS],
        "attribute_areas": [
            {"ordinal": a.ordinal, "name": a.name, "skill": a.skill,
             "section": a.section, "covers": a.covers}
            for a in ATTRIBUTE_AREAS],
        "beyond_the_reference": [
            {"skill": skill, "section": section, "covers": covers}
            for skill, section, covers in BEYOND_THE_REFERENCE],
        "means": (
            "two maps, not one. `areas` is the test design and implementation "
            "process, and its last three activities are owned by "
            "`metis-test-generate` because that is where they run — design "
            "derives conditions, generation derives cases. `attribute_areas` is "
            "what that process does not enumerate: a quality attribute and an "
            "interface boundary are designed by different people reading "
            "different evidence"),
    }
