"""
Structural validation for the twelve-label ontology (application spec D-2, ONT-002).

The enforcement half of labels.py. Two checks, both pure:

    validate(label, properties)                 node label + required properties
    validate_relationship(from, rel, to)        the (from, rel, to) triple

**A candidate that does not match is rejected — never auto-created to make the
rule fit the data** (ONT-002). That discipline is the reason the ontology stays
closed: the cheapest way to "fix" a validation failure is to widen the ontology,
and refusing to do so automatically is what keeps it twelve labels rather than
forty-five again.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from metis_mcp.ontology.labels import (
    ANY_LABEL,
    KNOWN_LABELS,
    LABELS,
    ALLOWED_RELATIONSHIPS,
    is_allowed,
)


@dataclass
class ValidationResult:
    valid: bool
    label: str = ""
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


def validate(label: str, properties: dict) -> ValidationResult:
    """Check a candidate node against its label's contract."""
    if label not in KNOWN_LABELS:
        return ValidationResult(
            valid=False, label=label,
            errors=[
                f"unknown label {label!r}; the ontology is closed "
                f"(known: {', '.join(sorted(KNOWN_LABELS))})"
            ],
        )

    spec = LABELS[label]
    errors: list[str] = []

    for prop in spec.all_required:
        if prop not in properties or properties[prop] is None:
            errors.append(f"{label}: required property {prop!r} is missing")
            continue
        value = properties[prop]
        # Present-but-empty is a distinct case from absent, and only some
        # properties may legitimately be empty (see LabelSpec.may_be_empty).
        if (isinstance(value, str) and not value.strip()
                and prop not in spec.may_be_empty):
            errors.append(f"{label}: required property {prop!r} is empty")

    for prop, allowed in spec.enums.items():
        value = properties.get(prop)
        if value is not None and value not in allowed:
            # A Neo4j property-existence constraint cannot express enum
            # membership (spec ONT-012); the schema guarantees presence and this
            # gate guarantees membership. Both are required.
            errors.append(
                f"{label}.{prop} = {value!r} is not one of {', '.join(allowed)}"
            )

    return ValidationResult(valid=not errors, label=label, errors=errors)


def validate_update(label: str, properties: dict) -> ValidationResult:
    """Check a **partial update** to an existing node (spec D-10, ONT-012).

    `validate` is for a candidate node and rightly demands the whole required
    set. A `SET n.provenance = ...` on a node that already exists supplies one
    property, so running it through `validate` would fail on properties the node
    already has -- and the practical result of that mismatch is that every `SET`
    in this codebase skipped the gate entirely.

    So this checks what a partial update *can* get wrong: an unknown label, and
    enum membership on the properties actually being written. It deliberately
    does not check required-property presence, because absence from an update is
    not absence from the node.
    """
    if label not in KNOWN_LABELS:
        return ValidationResult(
            valid=False, label=label,
            errors=[
                f"unknown label {label!r}; the ontology is closed "
                f"(known: {', '.join(sorted(KNOWN_LABELS))})"
            ],
        )

    spec = LABELS[label]
    errors: list[str] = []
    for prop, allowed in spec.enums.items():
        if prop not in properties:
            continue
        value = properties[prop]
        if value is not None and value not in allowed:
            errors.append(
                f"{label}.{prop} = {value!r} is not one of {', '.join(allowed)}"
            )
    return ValidationResult(valid=not errors, label=label, errors=errors)


def validate_relationship(from_label: str, rel_type: str, to_label: str) -> ValidationResult:
    """Check an edge against the relationship catalogue."""
    errors: list[str] = []

    for label in (from_label, to_label):
        if label not in KNOWN_LABELS:
            errors.append(f"unknown label {label!r} in ({from_label})-[:{rel_type}]->({to_label})")
    if errors:
        return ValidationResult(valid=False, errors=errors)

    if rel_type not in {r.rel_type for r in ALLOWED_RELATIONSHIPS}:
        return ValidationResult(
            valid=False,
            errors=[f"unknown relationship type {rel_type!r}; the ontology is closed"],
        )

    if not is_allowed(from_label, rel_type, to_label):
        permitted = [
            f"({r.from_label})-[:{r.rel_type}]->({r.to_label})"
            for r in ALLOWED_RELATIONSHIPS if r.rel_type == rel_type
        ]
        return ValidationResult(
            valid=False,
            errors=[
                f"({from_label})-[:{rel_type}]->({to_label}) is not in the catalogue; "
                f"permitted for this type: {', '.join(permitted)}"
            ],
        )

    return ValidationResult(valid=True)


def wildcard_relationships() -> tuple[str, ...]:
    """The relationship types deliberately not scoped to a fixed label.

    Exposed so the exception is visible and testable rather than discovered:
    revision history applies to every label, and a finding can concern anything.
    Everything else is a closed triple.
    """
    return tuple(
        r.rel_type for r in ALLOWED_RELATIONSHIPS
        if ANY_LABEL in (r.from_label, r.to_label)
    )
