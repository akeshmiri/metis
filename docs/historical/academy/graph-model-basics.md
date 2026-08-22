# Graph Model Basics

`REQ-METIS-ACD-02` — versioned alongside the ontology per `REQ-METIS-ACD-06`.
Current ontology version: **schema-01/02/03** (`schema/metis-graph-01-entity-baseline-constraints.cypher`,
`-02-entity-specific-constraints.cypher`, `-03-single-db-consolidation.cypher`),
49 closed-ontology labels (`metis_mcp/structural_validation.py`'s `KNOWN_LABELS`),
plus 3 control-plane labels (`Revision`, `MergeProposal`, `ConfidenceAdjustment`)
that deliberately sit outside that closed set — see below.

## What a "fact" looks like in Métis

Every real entity in the graph — a `Requirement`, a `Class`, a `TestCase`,
whatever — carries the same two properties, enforced by real Neo4j
constraints, not convention:

- `id` — unique within its label.
- `source_episode_id` — points at the real `Episode` (the immutable
  ingestion unit) this fact came from. This is `REQ-METIS-ONT-03`: **no
  entity may exist without one.** It's a hard schema constraint — if you
  ever see a fact with no traceable source, that's a schema-constraint
  bypass, a Critical-severity defect (DQ-001), not a quality nit.

Some labels require more: a `Requirement` also needs `ears_pattern`,
`revision`, and `corroboration_count` (`metis_mcp/structural_validation.py`'s
`LABEL_SPECIFIC_REQUIRED`) — these are judgment calls the spec makes
explicit, not mechanical boilerplate. A `Requirement` without an
`ears_pattern` is exactly what the EARS gate (see
[ears-authoring.md](ears-authoring.md)) exists to catch.

## The closed ontology

49 labels, not "whatever a connector feels like writing." An entity whose
label isn't in that set gets rejected outright by Layer 2 structural
validation — not auto-created as a new type. This is deliberate: a graph
where any connector can invent new node types isn't queryable in any
reliable way. Extending the ontology is a real, deliberate schema change,
not an incidental side effect of a connector bug.

**Control-plane labels are the one deliberate exception.** `Episode`
(the ingestion unit itself), and — added later — `Revision`
(`metis_mcp/temporal.py`'s versioning ledger), `MergeProposal`
(`metis_mcp/sleep_time_consolidation.py`'s near-duplicate queue), and
`ConfidenceAdjustment` (`metis_mcp/memify.py`'s feedback-loop cache) are
system machinery, not "extracted facts about the world" — they're
deliberately outside the closed ontology's Layer 2 gate, but they still
get real Neo4j constraints (uniqueness, required fields) for structural
integrity.

## Structural edges

Real, bi-temporal relationship types connect entities: `HAS_AC`,
`IMPLEMENTS`, `VERIFIES`, `PRODUCES`, `TRACES_TO`, `CITES`, plus the
Behavior Model's `FROM_STATE`/`TO_STATE`/`ON_TRIGGER`/`WHEN_GUARD` and the
code graph's `CALLS`/`IMPORTS`/`INHERITS`. Every one of these carries
`created_by`/`created_at`/`confidence` plus the bi-temporal `t_valid`/
`t_invalid` pair — see [reading-traceability-chains.md](reading-traceability-chains.md)
for how those get used.

## Where to look next

- Confidence tiers and what `lifecycle_state` actually means: [confidence-tiers.md](confidence-tiers.md)
- How a requirement gets checked before it's trusted: [ears-authoring.md](ears-authoring.md)
- Following a chain of these edges: [reading-traceability-chains.md](reading-traceability-chains.md)
