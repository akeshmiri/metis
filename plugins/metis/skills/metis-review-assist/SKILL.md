---
name: metis-review-assist
description: Walk a human reviewer through one Quarantine-tier item from Métis's review queue — real graph context, real traceability, real coverage check, ending in an honest write-path decision. Use when a user wants help deciding an Approve/Reject call on a specific quarantined entity, not for batch-processing the whole queue.
---

# Métis review-assist

**Reconstruction notice:** the original `metis-review-assist` this project's
`CLAUDE.md`/`PLAN.md` describe was absent from this copy of the project when
this session began (see `../shared/knowledge/anti-hallucination-protocol.md`'s
own notice). This is a best-effort reconstruction against the REAL, currently
running MCP server (`metis_mcp/server.py`'s actual 9 tools) rather than the
fuller production contract in `mcp-contracts/metis-mcp-tool-contracts.json` —
this skill calls tools the way they actually work today in dogfooding mode,
not the aspirational production shape.

## Purpose

Given one quarantined entity (a real node id — a `CONST-*`/`REQ-METIS-*` id
in dogfooding mode, or a real `Class`/`Method`/`TestCase` id once Phases
1-4/7 have populated the real graph), this skill:

1. Assembles real context and traceability for the item (Research).
2. Checks real coverage and forms a recommendation (Plan).
3. Attempts the write — and shows the real, honest outcome of that attempt,
   whatever it is (Implementation).

It follows `../shared/knowledge/anti-hallucination-protocol.md`'s RPI gates
and Stage Confirmation Protocol throughout — read that file once, it is not
repeated here.

## Steps

Run in order — see `steps/01-research.md`, `steps/02-plan.md`,
`steps/03-implementation.md`. This is standalone-mode (a single item), so
each step pauses for Stage Confirmation before the next begins.

## Real tools this skill calls

- `metis_get_context(anchor, client="claude", include_draft_tier=False)`
- `metis_get_traceability(node_id, direction="both")`
- `metis_check_coverage(target_id)`
- `metis_explain_decision(node_id)`
- `metis_submit_episode(episode_type, payload, source_ref)` — per
  `REQ-METIS-CPT-01`, this is disabled by default regardless of what this
  skill's Plan stage recommends; Step 3 shows that refusal honestly, it
  does not pretend the decision was recorded.
