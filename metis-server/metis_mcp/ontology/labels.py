"""
The twelve-label ontology (application spec §8.2, §8.3).

**This module is the single source for two of the four governance places** the
spec's D-2 rule names: the structural validator reads it directly, and the Cypher
schema is *generated* from it (see schema.py). Two places that cannot drift is
strictly better than two places kept in step by discipline.

The remaining two -- the catalogue in §8.2/§8.3 of the specification, and this
docstring -- are human-readable and are checked against this module by
test_ontology.py.

Why twelve and not forty-five: D-1. A label is included only when something in
§§2-7 writes it and something reads it. The other thirty-three would advertise
capability that does not exist, which is the failure this whole specification
corrects. §8.7 lists them with the trigger that would bring each back.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Spec D-8: every node carries these. `name` is display data, not identity.
BASELINE_REQUIRED = ("id", "source_episode_id", "name")

# The one exception, and it is structural rather than a concession: an Episode is
# the provenance record every other node points at, so it cannot point at one.
BASELINE_EXEMPT = {"Episode"}

# Lifecycle values (spec §8.6). Generation reads only `Approved` (D-10).
LIFECYCLE_STATES = ("Quarantine", "Approved", "Disputed", "Rejected", "Deprecated")

# Acceptance-criterion provenance (spec S-19). Defined here, in the ontology,
# rather than beside the matching logic that reads it: a grade the graph cannot
# store is a grade that does not exist. `reconciliation.matching` imports these.
#
# Only the last two are INTENT. A criterion written FROM the code and used to
# check that code can only ever report agreement (§4.1), so `code_derived` gives
# coverage and never correctness. The default is the weakest grade, for the same
# fail-closed reason a model source lands at Quarantine (S-4).
CODE_DERIVED = "code_derived"
HUMAN_CONFIRMED = "human_confirmed"
INDEPENDENTLY_AUTHORED = "independently_authored"
PROVENANCE_GRADES = (CODE_DERIVED, HUMAN_CONFIRMED, INDEPENDENTLY_AUTHORED)

# A target of `*` means the relationship is deliberately not scoped to a fixed
# label. Only two are: revision history applies to every label, and a finding can
# concern anything. Both are documented exceptions, not unenforced holes.
ANY_LABEL = "*"


@dataclass(frozen=True)
class LabelSpec:
    name: str
    purpose: str
    required: tuple[str, ...] = ()          # beyond BASELINE_REQUIRED
    # Required to be *present*, but legitimately empty. The motivating case is
    # `Transition.guard_expression`: an unguarded transition is normal (three of
    # the login model's seventeen), and "" is the honest representation of it.
    # Conflating "absent" with "empty" would either reject real transitions or
    # let a genuinely missing property through.
    may_be_empty: tuple[str, ...] = ()
    enums: dict[str, tuple[str, ...]] = field(default_factory=dict)
    indexed: tuple[str, ...] = ()

    @property
    def all_required(self) -> tuple[str, ...]:
        base = () if self.name in BASELINE_EXEMPT else BASELINE_REQUIRED
        return tuple(dict.fromkeys((*base, *self.required)))


LABELS: dict[str, LabelSpec] = {
    spec.name: spec for spec in (
        LabelSpec(
            "Episode", "Immutable record of one ingested unit; everything derived points here",
            required=("t_recorded", "source_connector", "job_id"),
            indexed=("source_connector", "job_id", "checkpoint_status"),
        ),
        LabelSpec(
            "JiraItem", "Evidence anchor for one Jira issue; survives its Requirement being rejected",
            required=("jira_key", "issue_type"),
            indexed=("jira_key",),
        ),
        LabelSpec(
            "Requirement", "One requirement statement",
            required=("ears_pattern", "revision"),
            indexed=("ears_pattern", "lifecycle_state"),
        ),
        LabelSpec(
            "AcceptanceCriterion", "One atomic, testable condition",
            required=("revision",),
            indexed=("lifecycle_state", "provenance"),
            # `provenance` is S-19's grade, and it is indexed because the
            # question it answers is a filter, not a lookup: "which criteria in
            # this scope are still code_derived" is what separates a coverage
            # claim from a correctness one. Without this property the grade was
            # computed by the review path and had nowhere to go.
            enums={"provenance": PROVENANCE_GRADES,
                   "lifecycle_state": LIFECYCLE_STATES},
        ),
        LabelSpec(
            "State", "One observable situation on one surface (spec M-3)",
            required=("surface",),
            enums={"surface": ("ui", "api"), "lifecycle_state": LIFECYCLE_STATES},
            indexed=("surface", "lifecycle_state", "functional_areas"),
        ),
        LabelSpec(
            "Transition", "One interaction: trigger, guard, source and target state",
            required=("trigger", "guard_expression", "implementation_status", "surface"),
            may_be_empty=("guard_expression",),
            enums={
                "surface": ("ui", "api"),
                "implementation_status": ("implemented", "planned"),
                "extraction_method": ("hand_authored", "static_analysis", "ac_mined"),
                "lifecycle_state": LIFECYCLE_STATES,
            },
            indexed=("surface", "lifecycle_state", "implementation_status",
                     "extraction_method", "functional_areas"),
        ),
        LabelSpec(
            "ModelVersion", "One versioned snapshot of a <journey>-<surface> model",
            required=("journey", "surface", "version"),
            enums={"surface": ("ui", "api")},
            indexed=("journey", "surface", "version", "commit_sha"),
        ),
        LabelSpec(
            "TestPath", "One covering walk: setup plus a single validated transition",
            required=("criterion", "generator_version"),
            indexed=("criterion",),
        ),
        LabelSpec(
            "TestCase", "One rendered, human-executable artefact",
            required=("content_hash",),
            indexed=("content_hash", "published_id", "published_status", "level"),
            # `level` is where the case sits in the pyramid, not what it asserts.
            # Without it, generation cannot be additive: nothing distinguishes a
            # case Métis wrote from an integration test that already covers the
            # same behaviour (REQ-METIS-PG-01).
            enums={"level": ("unit", "integration", "api_functional",
                             "web_functional", "e2e", "performance")},
        ),
        LabelSpec(
            "Finding", "A divergence, gap, unverifiable guard, or drift item",
            required=("finding_type",),
            indexed=("finding_type", "severity", "resolution"),
        ),
        LabelSpec(
            "Revision", "Property-level history for non-model entities",
            indexed=("recorded_at",),
        ),
        LabelSpec(
            "Run", "One pipeline execution: scope, criterion and versions (spec F-3)",
            required=("criterion",),
            indexed=("criterion", "started_at"),
        ),
    )
}

KNOWN_LABELS = frozenset(LABELS)


@dataclass(frozen=True)
class RelationshipSpec:
    from_label: str
    rel_type: str
    to_label: str
    meaning: str
    properties: tuple[str, ...] = ()


ALLOWED_RELATIONSHIPS: tuple[RelationshipSpec, ...] = (
    RelationshipSpec("JiraItem", "REPRESENTS", "Requirement", "System-of-record source"),
    RelationshipSpec("JiraItem", "LINKS_TO", "JiraItem",
                     "A real Jira issue link — provenance, not traceability"),
    RelationshipSpec("Requirement", "HAS_AC", "AcceptanceCriterion", "Its atomic conditions"),
    RelationshipSpec("AcceptanceCriterion", "VALIDATES", "Transition",
                     "Confirmed match (spec X-18)"),
    RelationshipSpec("State", "WHEN", "Transition", "Source state — the implicit Given"),
    RelationshipSpec("Transition", "THEN", "State", "Resulting target state"),
    RelationshipSpec("Transition", "INVOKES", "Transition",
                     "A UI interaction drives this API behaviour (spec M-5a)"),
    RelationshipSpec("ModelVersion", "CONTAINS", "State", "Membership of this version"),
    RelationshipSpec("ModelVersion", "CONTAINS", "Transition", "Membership of this version"),
    RelationshipSpec("TestPath", "GENERATED_FROM", "ModelVersion",
                     "The exact version this path covers"),
    RelationshipSpec("TestPath", "COVERS", "Transition",
                     "Ordered traversal — makes coverage computable",
                     properties=("sequence", "is_validated")),
    RelationshipSpec("TestPath", "PRODUCES", "TestCase", "The rendered artefact"),
    RelationshipSpec("Run", "PRODUCED", "TestPath", "Which run generated this path"),
    RelationshipSpec("Finding", "ABOUT", ANY_LABEL, "What the finding concerns"),
    RelationshipSpec(ANY_LABEL, "HAS_REVISION", "Revision",
                     "Written only by the revision recorder (spec ONT-010)"),
)

RELATIONSHIP_TYPES = tuple(dict.fromkeys(r.rel_type for r in ALLOWED_RELATIONSHIPS))

# Spec §8.7 — excluded, each with the trigger that would bring it back. Kept in
# code so the staging plan is checkable, not just prose.
STAGED_OUT: dict[str, str] = {
    "Goal": "a backlog hierarchy is actually queried",
    "Capability": "a backlog hierarchy is actually queried",
    "Epic": "a backlog hierarchy is actually queried",
    "Feature": "a backlog hierarchy is actually queried",
    "Release": "execution results are ingested and release reporting is required",
    "TestCycle": "execution results are ingested",
    "TestExecution": "execution results are ingested (spec C-10's trigger)",
    "Defect": "operational data enters scope",
    "Incident": "operational data enters scope",
    "Alert": "operational data enters scope",
    "Metrics": "operational data enters scope",
    "Logs": "operational data enters scope",
    "Constitution": "formal governance is adopted",
    "Constraint": "formal governance is adopted",
    "Repository": "impact analysis needs code structure in the graph, not just anchors",
    "Class": "impact analysis needs code structure in the graph",
    "Method": "impact analysis needs code structure in the graph",
    "Endpoint": "impact analysis needs code structure in the graph",
    "Intent": "a concrete need appears — none exists in §§2-7",
    "TestDesign": "a concrete need appears",
    "TestSuite": "a concrete need appears",
    "MicroRequirement": "a concrete need appears",
}


def relationships_from(label: str) -> tuple[RelationshipSpec, ...]:
    return tuple(r for r in ALLOWED_RELATIONSHIPS
                 if r.from_label == label or r.from_label == ANY_LABEL)


def is_allowed(from_label: str, rel_type: str, to_label: str) -> bool:
    for r in ALLOWED_RELATIONSHIPS:
        if r.rel_type != rel_type:
            continue
        if r.from_label not in (from_label, ANY_LABEL):
            continue
        if r.to_label not in (to_label, ANY_LABEL):
            continue
        return True
    return False
