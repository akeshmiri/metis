"""
REQ-METIS-GRD-02 (Layer 2, §7 of metis-specification.md): structural
validation at Cognify time -- type, cardinality, referential-integrity
checks. "failures quarantined, never auto-created to satisfy a dangling
reference" is the load-bearing clause this module exists to enforce: a
candidate entity referencing a source_episode_id that doesn't actually
exist gets REJECTED, never silently patched by fabricating a stub Episode
node to make the reference valid.

Matches classification_gate.py's pattern: real rule ids, one behavior per
check, and per AF-002's plain-language requirement, every failure names
the SPECIFIC missing/invalid thing, never a generic "validation failed."

The known-labels/required-properties tables below are the real, closed
ontology from schema/metis-graph-01/02-*.cypher -- not invented here, and
not auto-extensible by a caller (an unrecognized label is itself a
rejection reason, per REQ-METIS-GRD-02's "type" check).
"""
from dataclasses import dataclass, field
from typing import Callable

# The real, closed ontology (every label schema/metis-graph-01-entity-baseline-
# constraints.cypher declares a uniqueness/existence constraint for).
# Session 11, item 5: CopilotSession/Prompt/GeneratedCode/AIDecision/
# HumanReview/Cache removed by explicit user decision -- pure LLM-session/
# demo-filler with zero relationships anywhere in this codebase (verified by
# grep before removal), and keeping ephemeral LLM/Copilot session data in a
# graph meant to be a global, persistent source of truth is counterproductive.
# GeneratedTest is NOT removed -- unlike the other 5, metis_mcp/
# test_skeleton_generator.py genuinely uses it for REQ-METIS-BM-03
# (AI-proposed test provenance until it converges with a real TestCase).
# Session 12: TestRun renamed to TestCycle (the batch/container); per-case
# results now live on the new TestExecution node, and TestExecution carries
# which real component-version snapshot (ApplicationConfiguration) it ran
# against -- see structural comments in schema/metis-graph-02-*.cypher.
# Session 13: Trigger/Guard removed entirely -- both were attributes of
# exactly one Transition (now Transition.trigger/guard_expression
# properties), not their own entities. See
# docs/metis-ontology-specification.md, the authoritative per-label/
# per-relationship reference this set and ALLOWED_RELATIONSHIPS below are
# both checked against.
KNOWN_LABELS = {
    "API", "AcceptanceCriterion", "Action", "Alert", "ApplicationConfiguration",
    "AutomationScript", "Branch", "BusinessRule", "Capability", "Class", "Column",
    "Commit", "Constitution", "Constraint", "Database", "Defect", "Endpoint",
    "Epic", "Event", "ExternalAPISpec", "ExternalSystem", "Feature",
    "GeneratedTest", "Goal", "Incident", "Intent", "KafkaTopic",
    "Logs", "Method", "Metrics", "MicroRequirement", "PullRequest", "Release",
    "Repository", "Requirement", "Service", "State", "Table", "TestCase", "TestCycle",
    "TestDesign", "TestExecution", "TestSuite", "Transition", "Workflow",
}

# Baseline (schema-01): every real entity requires these.
BASELINE_REQUIRED = ("id", "source_episode_id")

# Label-specific additions (schema-02): judgment calls the spec makes
# explicit, not mechanical boilerplate -- e.g. a Requirement without an
# ears_pattern is exactly what REQ-METIS-ONT-04's EARS gate exists to catch.
LABEL_SPECIFIC_REQUIRED = {
    # corroboration_count added after a real bug: schema-02's
    # requirement_corroboration_count/businessrule_corroboration_count
    # existence constraints were never caught here, because nothing had
    # actually written a real :Requirement-labeled node through this gate
    # until the bmad-method connector did (everything before that used
    # DogfoodingItem/Class/Method/TestCase, none of which require it).
    "Requirement": ("ears_pattern", "revision", "corroboration_count"),
    "BusinessRule": ("corroboration_count",),
    # Session 11/12: a TestCycle with no run_type is exactly the kind of
    # "coverage claim with no real evidence behind it" CONST-005a already
    # flags. application_version moved off this label in Session 12 --
    # TestExecution.result/executed_at plus its RAN_AGAINST
    # ApplicationConfiguration now carry the precise per-case evidence a
    # single flat version string never could.
    "TestCycle": ("run_type",),
    # Session 12: a TestExecution with no executed_at/result is a claim with
    # no real evidence -- same CONST-005a rationale as TestCycle above.
    "TestExecution": ("executed_at", "result"),
    "AcceptanceCriterion": ("revision",),
    "Episode": ("t_recorded", "source_connector", "job_id"),
}

# Session 13, item 4: the real relationship-level guardrail -- Layer 2
# validated node label + required properties + source_episode existence,
# but nothing ever validated relationship TYPE/cardinality at all. This is
# the literal `ALLOWED_RELATIONSHIPS` half of docs/
# metis-ontology-specification.md's Relationship Catalog -- kept in sync
# manually; a mismatch between the two is a bug in whichever one is stale,
# not a design choice. Every triple here is a real relationship this
# codebase actually creates today (confirmed by grep across demo_data/,
# connectors/, guardrails/, metis_mcp/ before writing this table down --
# not invented here, and not auto-extensible by a caller, same discipline
# KNOWN_LABELS already uses for node labels).
ALLOWED_RELATIONSHIPS: set[tuple[str, str, str]] = {
    ("Capability", "TRACES_TO", "Goal"),
    ("Epic", "TRACES_TO", "Capability"),
    ("Feature", "TRACES_TO", "Epic"),
    ("Requirement", "TRACES_TO", "Feature"),
    ("Requirement", "TRACES_TO", "Intent"),
    ("Requirement", "TRACES_TO", "Release"),
    ("Requirement", "HAS_AC", "AcceptanceCriterion"),
    ("AcceptanceCriterion", "TRACES_TO", "Intent"),
    ("AcceptanceCriterion", "VALIDATES", "Transition"),
    ("TestDesign", "TRACES_TO", "Intent"),
    ("TestDesign", "COVERS", "AcceptanceCriterion"),
    ("TestDesign", "PRODUCES", "TestCase"),
    ("TestCase", "VERIFIES", "AcceptanceCriterion"),
    ("TestCase", "VERIFIES", "Endpoint"),
    ("TestCase", "PART_OF", "TestSuite"),
    ("TestCycle", "PART_OF", "TestSuite"),
    ("TestCycle", "TRACES_TO", "Release"),
    ("TestExecution", "PART_OF", "TestCycle"),
    ("TestExecution", "EXECUTES", "TestCase"),
    ("TestExecution", "PRODUCES", "Defect"),
    ("TestExecution", "RAN_AGAINST", "ApplicationConfiguration"),
    ("ApplicationConfiguration", "INCLUDES_VERSION", "Service"),
    ("State", "WHEN", "Transition"),
    ("Transition", "THEN", "State"),
    ("Database", "HAS", "Table"),
    ("Repository", "DEFINES", "Class"),
    ("Class", "HAS_METHOD", "Method"),
    ("Class", "IMPORTS", "Class"),
    ("Class", "INHERITS", "Class"),
    ("Method", "CALLS", "Method"),
    ("Method", "IMPLEMENTS", "Requirement"),
    ("PullRequest", "PRODUCES", "Commit"),
}

# HAS_REVISION is the one relationship type intentionally NOT scoped to a
# fixed from_label -- metis_mcp/temporal.py's record_revision() writes it
# from ANY real entity (every label can have revision history), always to
# a Revision node. Modeled separately rather than enumerating every
# from_label x HAS_REVISION x Revision triple in ALLOWED_RELATIONSHIPS.
_GENERIC_RELATIONSHIP_TARGETS = {"HAS_REVISION": "Revision"}


@dataclass
class ValidationResult:
    valid: bool
    label: str
    reasons: list[str] = field(default_factory=list)


def validate_relationship(from_label: str, rel_type: str, to_label: str) -> ValidationResult:
    """The relationship-level counterpart to StructuralValidator.validate()
    -- rejects any (from_label, rel_type, to_label) triple that isn't in
    ALLOWED_RELATIONSHIPS (or the HAS_REVISION generic case), naming the
    specific unknown combination, never silently allowed through.

    Documented, intentional exception NOT covered here:
    connectors/test_suite_connector.py's TestCase-[:VERIFIES]->(target)
    links to whatever real, already-existing entity a test file's
    docstring cites by tag, with no fixed target label -- validity is
    enforced by real tag-existence at write time (REQ-METIS-CONN-04), not
    a closed target-label list, since it's a citation mechanism, not a
    structural design relationship. See docs/
    metis-ontology-specification.md's Relationship Catalog note."""
    generic_target = _GENERIC_RELATIONSHIP_TARGETS.get(rel_type)
    if generic_target is not None:
        if to_label == generic_target:
            return ValidationResult(valid=True, label=from_label)
        return ValidationResult(valid=False, label=from_label, reasons=[
            f"'{rel_type}' must target '{generic_target}', not '{to_label}'."
        ])
    if (from_label, rel_type, to_label) in ALLOWED_RELATIONSHIPS:
        return ValidationResult(valid=True, label=from_label)
    return ValidationResult(valid=False, label=from_label, reasons=[
        f"Unknown relationship '({from_label})-[:{rel_type}]->({to_label})' -- not part of the "
        f"closed relationship catalog (docs/metis-ontology-specification.md); rejected, not "
        f"auto-created as a new edge type."
    ])


class StructuralValidator:
    """
    Usage:
        validator = StructuralValidator(episode_exists=lambda eid: ...)
        result = validator.validate(label="Requirement", entity={...})
        if not result.valid:
            # quarantine/reject -- do NOT create the entity, and do NOT
            # auto-create a stub Episode to satisfy a dangling reference.
            ...

    episode_exists is injected (not hardcoded to a live Neo4j call) so this
    is unit-testable without a real database -- the real caller wires it to
    an actual `MATCH (e:Episode {id: $id}) RETURN e` check.
    """

    def __init__(self, episode_exists: Callable[[str], bool]):
        self._episode_exists = episode_exists

    def validate(self, label: str, entity: dict) -> ValidationResult:
        reasons: list[str] = []

        # -- Type check --
        if label not in KNOWN_LABELS:
            reasons.append(
                f"Unknown entity type '{label}' -- not part of the closed ontology "
                f"(schema/metis-graph-01-entity-baseline-constraints.cypher); rejected, "
                f"not auto-created as a new type."
            )
            # A type this unrecognized can't be meaningfully checked further
            # (there's no known required-property set for it) -- stop here
            # rather than reporting confusing follow-on cardinality errors.
            return ValidationResult(valid=False, label=label, reasons=reasons)

        # -- Cardinality check: required properties present and non-empty --
        required = BASELINE_REQUIRED + LABEL_SPECIFIC_REQUIRED.get(label, ())
        for prop in required:
            if entity.get(prop) in (None, ""):
                reasons.append(f"Missing required property '{prop}' for entity type '{label}'.")

        # -- Referential-integrity check: source_episode_id must reference a
        # real, already-landed Episode -- never auto-created to satisfy this. --
        source_episode_id = entity.get("source_episode_id")
        if source_episode_id and not self._episode_exists(source_episode_id):
            reasons.append(
                f"source_episode_id '{source_episode_id}' does not reference an existing "
                f"Episode -- entity quarantined, not auto-created to satisfy a dangling "
                f"reference (REQ-METIS-GRD-02)."
            )

        return ValidationResult(valid=not reasons, label=label, reasons=reasons)
