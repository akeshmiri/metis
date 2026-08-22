# Confidence Tiers

`REQ-METIS-ACD-02`. This is the real state machine behind every fact's
`lifecycle_state` — `metis_mcp/confidence_tiering.py`, `REQ-METIS-GRD-03`
(Layer 3 of the ten-layer guardrail stack).

## The three tiers, exactly as implemented

| Condition | Tier | `lifecycle_state` | What it means |
|---|---|---|---|
| confidence ≥ 0.9, ≥1 source, passes Layer 2 | `auto_write` | `Draft` | Written automatically — **`Draft` is never authoritative**, it still needs review before `Approved` |
| 0.6 ≤ confidence < 0.9 | `quarantine` | `Quarantine` | Held for a human reviewer (Layer 7) — never auto-promoted, not even after a long time unreviewed |
| confidence < 0.6, OR fails Layer 2, OR contradicts existing state | `rejected` | `Rejected` | **Logged only — never written to the graph at all**, not even in a visibly-rejected state |

Two things that always force `rejected`, regardless of the confidence
number: failing Layer 2 structural validation (missing required fields,
dangling `source_episode_id`), or a real logical contradiction with
existing graph state. A high confidence score never overrides either.

## The Constitution gate runs first

`metis_mcp/constitution_gate.py` (`REQ-METIS-GRD-11`) checks a narrow,
real set of Constitution rules **before** this tiering state machine even
runs — currently, `CONST-047`'s four deterministic ISO/IEC/IEEE 29148
checks (unambiguous, complete, singular, consistent) for `Requirement`
candidates. A Constitution violation is **always** `Rejected`, regardless
of confidence — this is a stronger guarantee than the ordinary Layer 2/3
path: even a `Requirement` reported at confidence 0.99 gets hard-rejected
if it fails CONST-047, never allowed to land at `Quarantine` as a "maybe."

## Why "logged only" for Rejected

A `Rejected` fact isn't written as a node at all — there's nothing to see
in the graph. This is deliberate: writing a visibly-`Rejected` node would
still be a node someone could accidentally traverse to or count in a
query. "Logged only" (as an `Episode`-level record, not a graph entity)
keeps `Rejected` facts fully out of the graph's queryable surface while
still being auditable.

## Where this shows up elsewhere

- `metis_mcp/dq_metrics.py`'s DQ-002 (extraction-confidence distribution)
  tracks the real tier breakdown against targets (≥60% `auto_write`,
  ≤30% `quarantine`, ≤10% `rejected`) — see `guardrails/calibration.py`'s
  real, run calibration batch for what those numbers actually looked like
  the one time this was measured for real in this codebase (229 real
  cases: 26.6% / 13.5% / 59.8% — a real miss against those initial
  targets, exactly the kind of finding calibration exists to surface).
- `metis_mcp/memify.py`'s feedback loop adjusts the *default* confidence
  per `(extraction_rule, entity_type, connector)` triple from real human
  corrections — it never changes this tiering logic itself, only the
  input confidence a caller supplies.

## Where to look next

- What gets checked before tiering even runs: [ears-authoring.md](ears-authoring.md)
- The bigger structural picture these tiers sit inside: [graph-model-basics.md](graph-model-basics.md)
