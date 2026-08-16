---
name: metis-behavior-modeling
description: Check a proposed set of State/Transition/Guard/Trigger entities for determinism, completeness, and reachability (CONST-048/049) using Phase 8's real Cypher-based checks — surfaces ambiguous or incomplete state machines as Disputed rather than silently resolving them. Use when a user is defining or reviewing a state machine (lifecycle states, workflow transitions) and wants it checked for well-formedness before relying on it.
---

# Métis behavior-modeling

Wraps `metis_mcp/behavior_model.py`'s real, tested determinism/completeness/
reachability checks (Phase 8) as a skill, per `PLAN.md` Phase 10's
instruction to build "a behavior-modeling skill wrapping Phase 8's work."
Follows `../shared/knowledge/anti-hallucination-protocol.md`'s RPI gates and
Stage Confirmation Protocol — read that file once, not repeated here.

**Standalone mode:** this reviews one Transition set (one `State` machine)
per invocation — always pauses for confirmation between steps.

## Scope, disclosed

This skill checks well-formedness of a state machine's STRUCTURE (do two
transitions genuinely conflict, is every state reachable, is every trigger
handled) — real, deterministic graph algorithms, per §9's code-vs-LLM
allocation.

**Update:** `REQ-METIS-BM-01`'s code-graph corroboration and
`MicroRequirement` decomposition, both originally out of scope here, are
now real and callable (see below) — no `ANTHROPIC_API_KEY` was ever set;
the LLM piece goes through the `claude` CLI instead
(`metis_mcp/llm_client.py`), and the code graph comes from a real AST-based
CALLS/IMPORTS/INHERITS extraction pass (`cognify/code_graph_archaeology.py`).

## Steps

See `steps/01-research.md`, `steps/02-plan.md`, `steps/03-implementation.md`.

## Real functions this skill calls

- `metis_mcp.behavior_model.load_transition(...)` — lands the proposed
  State/Transition/Guard/Trigger set into Neo4j.
- `metis_mcp.behavior_model.check_determinism(session, state_id)` — per
  `CONST-048`; marks conflicting Transitions `lifecycle_state='Disputed'`
  with a specific `dispute_reason`, per `CONST-049`.
- `metis_mcp.behavior_model.check_completeness(session)`
- `metis_mcp.behavior_model.check_reachability(session, initial_state_id)`
- `metis_mcp.behavior_model.corroborate_transition(session, transition_id, implementing_method_id, expected_callees)` —
  `REQ-METIS-BM-01`, against the real CALLS graph.
- `metis_mcp.microrequirement.decompose_requirement(text)` — real model
  call, real cost per invocation; use deliberately, not in a loop.
