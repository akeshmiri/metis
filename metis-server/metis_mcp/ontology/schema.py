"""
Cypher schema, generated from labels.py (application spec RD-2, D-2).

The spec's four-place governance rule says a label must exist in the schema, the
validator, the catalogue and the specification together. Two of those four are
**generated from one source here**, so they are structurally incapable of
disagreeing. The remaining two are prose and are checked by test_ontology.py.

    python3 -m metis_mcp.ontology.schema           # print
    python3 -m metis_mcp.ontology.schema --write   # write schema/metis2-*.cypher

Regenerate rather than hand-edit. A hand-edit to the generated file is the exact
drift the generation exists to prevent, and the test will catch it.
"""
from __future__ import annotations

import sys
from pathlib import Path

from metis_mcp.ontology.labels import (
    ALLOWED_RELATIONSHIPS,
    ANY_LABEL,
    BASELINE_EXEMPT,
    LABELS,
    RELATIONSHIP_TYPES,
)

HEADER = """// ==========================================================
// Métis schema — GENERATED from metis_mcp/ontology/labels.py
// Do not hand-edit: regenerate with
//     python3 -m metis_mcp.ontology.schema --write
// Hand-edits are drift, and test_ontology.py will fail on them.
// ==========================================================
"""


def _snake(label: str) -> str:
    out = []
    for i, ch in enumerate(label):
        if ch.isupper() and i:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


COMMUNITY = "community"
ENTERPRISE = "enterprise"

_EDITION_NOTE = """
// ---- EDITION: {edition} ----
// Property-existence constraints are an ENTERPRISE-only feature. Under
// Community (spec C1/DD-2) they cannot be created, so required-property
// enforcement lives in metis_mcp/ontology/validation.py instead.
//
// This is the same split spec ONT-012 already makes for enum membership: the
// database enforces what it can, the application gate enforces the rest, and
// both are required. Verified against a real Neo4j 5 Community instance --
// attempting them there fails with "requires Neo4j Enterprise Edition".
"""


def constraints_cypher(edition: str = COMMUNITY) -> str:
    """Part 1: identity, required properties, and per-label indexes.

    `edition` decides whether existence constraints are emitted. Community gets
    them as comments naming the enforcing module, so the DDL states plainly
    where the rule actually lives rather than implying the database holds it.
    """
    lines = [HEADER, _EDITION_NOTE.format(edition=edition),
             "// ---- Part 1: node constraints and indexes ----\n"]

    for label in sorted(LABELS):
        spec = LABELS[label]
        n = _snake(label)
        lines.append(f"// {label} — {spec.purpose}")
        # Uniqueness works on both editions.
        lines.append(
            f"CREATE CONSTRAINT {n}_id_unique IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.id IS UNIQUE;"
        )
        for prop in spec.all_required:
            if prop == "id":
                continue
            statement = (
                f"CREATE CONSTRAINT {n}_{prop}_required IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{prop} IS NOT NULL;"
            )
            lines.append(statement if edition == ENTERPRISE
                         else f"// [enterprise-only] {statement}")
        # Every reviewable label gets a lifecycle index; labels that name it
        # explicitly must not get it twice.
        indexed = list(dict.fromkeys(
            (*spec.indexed, *(() if label in BASELINE_EXEMPT else ("lifecycle_state",)))
        ))
        for prop in indexed:
            lines.append(
                f"CREATE INDEX {n}_{prop}_lookup IF NOT EXISTS "
                f"FOR (n:{label}) ON (n.{prop});"
            )
        if spec.enums:
            # Spec ONT-012: existence is a schema constraint, membership is an
            # application gate. Recorded here so the split is visible in the DDL.
            for prop, allowed in spec.enums.items():
                lines.append(f"//   {label}.{prop} ∈ {{{', '.join(allowed)}}} "
                             f"— enforced by ontology.validation, not by Neo4j")
        lines.append("")

    return "\n".join(lines)


def relationships_cypher() -> str:
    """Part 2: relationship-property indexes.

    Spec ONT-011: every relationship type carries a validity index. v1 discovered
    mid-build that two edge types never had one — an oversight, not a decision.
    Generating them removes the possibility.
    """
    lines = [HEADER, "// ---- Part 2: relationship indexes ----\n"]

    for rel_type in RELATIONSHIP_TYPES:
        r = _snake(rel_type)
        lines.append(
            f"CREATE INDEX rel_{r}_t_valid IF NOT EXISTS "
            f"FOR ()-[x:{rel_type}]-() ON (x.t_valid);"
        )

    lines.append("")
    lines.append("// ---- Catalogue (the closed set enforced by ontology.validation) ----")
    for spec in ALLOWED_RELATIONSHIPS:
        wildcard = " [any label]" if ANY_LABEL in (spec.from_label, spec.to_label) else ""
        props = f"  {{{', '.join(spec.properties)}}}" if spec.properties else ""
        lines.append(
            f"//   ({spec.from_label})-[:{spec.rel_type}]->({spec.to_label}){props}"
            f"{wildcard}  — {spec.meaning}"
        )

    for spec in ALLOWED_RELATIONSHIPS:
        for prop in spec.properties:
            lines.append(
                f"CREATE INDEX rel_{_snake(spec.rel_type)}_{prop} IF NOT EXISTS "
                f"FOR ()-[x:{spec.rel_type}]-() ON (x.{prop});"
            )

    lines.append("")
    return "\n".join(lines)


FILES = {
    "metis2-01-constraints.cypher": lambda: constraints_cypher(COMMUNITY),
    "metis2-01-constraints-enterprise.cypher": lambda: constraints_cypher(ENTERPRISE),
    "metis2-02-relationships.cypher": relationships_cypher,
}


def write(target_dir: str | Path = "schema") -> list[Path]:
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for name, generator in FILES.items():
        path = target / name
        path.write_text(generator())
        written.append(path)
    return written


def statements(text: str) -> list[str]:
    """Split generated Cypher into executable statements, dropping comments."""
    out = []
    for raw in text.split(";"):
        stripped = "\n".join(
            line for line in raw.splitlines() if line.strip() and not line.strip().startswith("//")
        ).strip()
        if stripped:
            out.append(stripped + ";")
    return out


if __name__ == "__main__":
    if "--write" in sys.argv:
        for path in write():
            print(f"wrote {path}")
    else:
        print(constraints_cypher(COMMUNITY))
        print(relationships_cypher())
