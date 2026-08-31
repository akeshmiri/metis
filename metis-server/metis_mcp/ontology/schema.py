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
    PROJECT_PROPERTY,
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

# **Enterprise is no longer generated** (C1). Property-existence constraints are
# an Enterprise-only feature, and shipping a second DDL that uses them meant two
# schemas could disagree about what the database enforces — with the application
# gate in `ontology/validation.py` silently redundant on one and load-bearing on
# the other. Métis targets Community, so it generates the Community schema and
# nothing else, and the gate is the enforcement everywhere rather than a fallback.
#
# The constant stays so a caller passing it gets a refusal that says why, instead
# of an AttributeError.
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

    **Community only.** Existence constraints are emitted as comments naming the
    module that actually enforces them, so the DDL states where the rule lives
    rather than implying the database holds it.
    """
    if edition != COMMUNITY:
        raise ValueError(
            f"Métis generates the {COMMUNITY} schema only (C1). "
            f"{edition!r} was dropped: property-existence constraints are an "
            f"Enterprise feature, and two schemas that disagree about what the "
            f"database enforces make `ontology/validation.py` load-bearing on "
            f"one and redundant on the other. It is the enforcement everywhere.")
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
            # Always a comment now: the guard above admits nothing else, and a
            # live branch on a value that cannot occur reads as though the other
            # path is reachable.
            lines.append(f"// [enterprise-only, enforced by "
                         f"ontology/validation.py] {statement}")
        # Every reviewable label gets a lifecycle index; labels that name it
        # explicitly must not get it twice.
        # `source_episode_id` is indexed on every non-exempt label for the same
        # reason `lifecycle_state` is: it is a baseline property that a real
        # question filters on. "Everything this ingestion produced" was a full
        # scan per label, which is why `Episode` looked like an orphan --
        # reachable by no edge AND expensive to reach by property.
        #
        # An `Episode -[:PRODUCED]-> *` edge was the alternative and is worse:
        # one edge per node, restating a fact the node already carries, and two
        # representations that can disagree. This session has spent most of its
        # time on exactly that class of defect.
        # `m_project` joins them for the same reason: "everything belonging to
        # this project" is what `storage export` asks, once per label, and
        # without an index it is a full scan of a graph that holds every project
        # a deployment has ingested. Episode gets it too -- it is exempt from the
        # baseline because it cannot point at itself, not because it belongs to
        # no project.
        indexed = list(dict.fromkeys(
            (*spec.indexed, PROJECT_PROPERTY,
             *(() if label in BASELINE_EXEMPT
               else ("lifecycle_state", "source_episode_id")))
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

    # ---- Free text search --------------------------------------------------
    # One index across every searchable label, because a search that had to be
    # told which label to look in would not be a search. Generated from
    # `labels.SEARCH_TARGETS` so the index and `graph_loader.SEARCH_CYPHER`
    # cannot name different properties.
    from metis_mcp.ontology.labels import SEARCH_INDEX, SEARCH_TARGETS

    search_labels = "|".join(sorted(SEARCH_TARGETS))
    search_props = sorted({p for props in SEARCH_TARGETS.values() for p in props})
    lines += [
        "// Free-text search (Lucene, Community edition). Replaces substring",
        "// matching: `CONTAINS` cannot rank, cannot tokenise, and cannot tell a",
        "// title match from a body match.",
        f"CREATE FULLTEXT INDEX {SEARCH_INDEX} IF NOT EXISTS",
        f"FOR (n:{search_labels})",
        f"ON EACH [{', '.join('n.' + p for p in search_props)}]",
        "// The `english` analyzer, not the default `standard` one. Measured: with",
        "// the default, searching `lock` returned NOTHING for a criterion whose",
        "// text says \"the account is locked\" — standard tokenises and lowercases",
        "// but does not stem, so it beats CONTAINS on ranking and loses to it on",
        "// the word-form matching that is half the reason to want full text.",
        "OPTIONS {indexConfig: {`fulltext.analyzer`: 'english'}};",
        "",
    ]

    # ---- Semantic search ---------------------------------------------------
    # Same labels as the full-text index: a search that had to be told which
    # kind of similarity to use would not be a search either. Nodes without an
    # embedding are simply absent from this index, so it is inert until
    # something populates the property.
    from metis_mcp.ontology.labels import (
        VECTOR_DIMENSIONS,
        VECTOR_PROPERTY,
        VECTOR_SIMILARITY,
        vector_index_for,
    )

    lines += [
        "// Semantic search. Inert until `embedding` is populated — an unembedded",
        "// node is absent from its index rather than wrong in it.",
        "//",
        "// One index PER LABEL: Neo4j accepts the multi-label form for a full-text",
        "// index and rejects it for a vector index.",
    ]
    for label in sorted(SEARCH_TARGETS):
        lines += [
            f"CREATE VECTOR INDEX {vector_index_for(label)} IF NOT EXISTS",
            f"FOR (n:{label})",
            f"ON (n.{VECTOR_PROPERTY})",
            "OPTIONS {indexConfig: {",
            f"  `vector.dimensions`: {VECTOR_DIMENSIONS},",
            f"  `vector.similarity_function`: '{VECTOR_SIMILARITY}'",
            "}};",
        ]
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
    """Split generated Cypher into executable statements, dropping comments.

    **Comments come out before the split, and the order is the whole point.**
    This used to split on `;` first and strip `//` lines from each piece, which
    works right up until a comment contains a semicolon -- and one does:
    `Episode`'s purpose line reads "Immutable record of one ingested unit;
    everything derived points here". The split then cut inside the comment, the
    tail lost its `//` prefix, and that orphaned prose was glued onto the front
    of the NEXT statement, which the server refused as a syntax error.

    Three uniqueness constraints (`Episode.id`, `JiraItem.id`, `Page.id`) and the
    `COVERS.sequence` index were silently absent from a database this function
    had just been used to build. Missing uniqueness is the worst shape for this
    failure: nothing errors, and duplicate ids land.
    """
    body = "\n".join(line for line in text.splitlines()
                     if line.strip() and not line.strip().startswith("//"))
    return [piece.strip() + ";" for piece in body.split(";") if piece.strip()]


if __name__ == "__main__":
    if "--write" in sys.argv:
        for path in write():
            print(f"wrote {path}")
    else:
        print(constraints_cypher(COMMUNITY))
        print(relationships_cypher())
