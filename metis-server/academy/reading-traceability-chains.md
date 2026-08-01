# Reading Traceability Chains

`REQ-METIS-ACD-02`. A traceability chain is a real, walkable path of
structural edges — `metis_mcp/server.py`'s `metis_get_traceability` tool
walks it for you, but it's worth knowing what it's actually walking.

## The chain, concretely

```
Requirement --HAS_AC--> AcceptanceCriterion
Method --IMPLEMENTS--> Requirement
TestCase --VERIFIES--> Requirement
Requirement --TRACES_TO--> Feature / Release
```

Each edge is real graph structure, not a computed guess — `metis_mcp/
dq_metrics.py`'s DQ-017 ("end-to-end chain completeness") walks exactly
this shape to check whether a shipped `Release`'s `Requirement`s actually
have a real `VERIFIES` edge from a `TestCase`, not just a plausible-looking
one.

## Point-in-time chains

Every structural edge carries `t_valid`/`t_invalid` — a chain didn't
always look the way it does right now. `metis_mcp/temporal.py`'s
`as_of(entity_id, timestamp)` reconstructs what a specific entity's
tracked properties looked like at a specific past instant, from the real
`:Revision` supersession chain (§5.4's `history`/`diff` do the same for
the full change history and for structural diffs between two points).
This is the answer to "what did this requirement say before last week's
edit" — a real query, not an inference.

## When a chain is broken

`metis_get_traceability`'s real `gaps` field (and `metis_mcp/dq_metrics.py`'s
DQ-018, circular-traceability) surface two different failure shapes:

- **A missing edge** — a `Requirement` with no `VERIFIES`-linked `TestCase`
  at all. Real gap, needs a real test.
- **Circular traceability** — a `Requirement`'s *only* supporting
  `TestCase` cites it with no independent `AcceptanceCriterion` behind
  either. This pattern (checked by `metis_mcp/layer8_heuristics.py`'s
  `check_circular_traceability`) usually means the test was written
  first and the traceability link added after the fact, not derived from
  a real accepted requirement — worth investigating individually, never
  assumed innocent.

## Hybrid retrieval's graph-traversal mode

`metis_mcp/hybrid_retrieval.py`'s `graph_traversal_search` is the same
underlying mechanism, generalized: given any anchor node, it finds
everything within N hops via the same real structural edges, scored by
distance (`1 / (1 + hops)`) — useful when you want "everything connected
to X," not just one specific chain type.

## Where to look next

- What the labels/edges you're following actually mean: [graph-model-basics.md](graph-model-basics.md)
- Why some facts in a chain are more trustworthy than others: [confidence-tiers.md](confidence-tiers.md)
