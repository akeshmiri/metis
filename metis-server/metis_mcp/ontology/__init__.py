"""The twelve-label ontology (application spec §8)."""
from metis_mcp.ontology.labels import (
    ALLOWED_RELATIONSHIPS,
    ANY_LABEL,
    BASELINE_REQUIRED,
    KNOWN_LABELS,
    LABELS,
    LIFECYCLE_STATES,
    RELATIONSHIP_TYPES,
    STAGED_OUT,
    is_allowed,
    label_expression,
    relationships_from,
)
from metis_mcp.ontology.validation import (
    ValidationResult,
    validate,
    validate_relationship,
    validate_update,
    wildcard_relationships,
)

__all__ = [
    "LABELS", "KNOWN_LABELS", "BASELINE_REQUIRED", "LIFECYCLE_STATES",
    "ALLOWED_RELATIONSHIPS", "RELATIONSHIP_TYPES", "ANY_LABEL", "STAGED_OUT",
    "is_allowed", "label_expression", "relationships_from",
    "validate", "validate_relationship", "validate_update", "ValidationResult",
    "wildcard_relationships",
]
