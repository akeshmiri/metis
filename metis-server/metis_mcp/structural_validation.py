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
KNOWN_LABELS = {
    "AIDecision", "API", "AcceptanceCriterion", "Action", "Alert", "AutomationScript",
    "Branch", "BusinessRule", "Cache", "Capability", "Class", "Column", "Commit",
    "Constitution", "Constraint", "CopilotSession", "Database", "Defect", "Endpoint",
    "Epic", "Event", "ExternalAPISpec", "ExternalSystem", "Feature", "GeneratedCode",
    "GeneratedTest", "Goal", "Guard", "HumanReview", "Incident", "Intent", "KafkaTopic",
    "Logs", "Method", "Metrics", "MicroRequirement", "Prompt", "PullRequest", "Release",
    "Repository", "Requirement", "Service", "State", "Table", "TestCase", "TestDesign",
    "TestRun", "TestSuite", "Transition", "Trigger", "Workflow",
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
    "AcceptanceCriterion": ("revision",),
    "Episode": ("t_recorded", "source_connector", "job_id"),
}


@dataclass
class ValidationResult:
    valid: bool
    label: str
    reasons: list[str] = field(default_factory=list)


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
