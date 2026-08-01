---
name: metis
description: Métis's own top-level skill router. Built independently, on the same Quick-Routing-table pattern Atlas's atlas.agent.md uses -- not a copy of it, not a registration inside it. No Atlas installation, shared runtime, or shared router is required to use anything below.
---

# Métis — Skill Router

`REQ-METIS-SKL-01`/`REQ-METIS-SKL-02` (`docs/metis-specification.md` §4.6):
every Métis skill lives in Métis's own tree (`.agents/skills/<name>/`,
`SKILL.md` + `steps/` + this project's own
`shared/knowledge/anti-hallucination-protocol.md`) and registers here, in
Métis's own router — modeled on Atlas's `atlas.agent.md` Quick Routing
table as a *pattern*, reimplemented independently. If an org runs both
Atlas and Métis, this file and Atlas's are two separate, non-overlapping
entry points; neither depends on the other's installation.

## Quick Routing

| Trigger | Skill | Use when |
|---|---|---|
| "review this quarantined item" / "help me approve or reject \<id\>" / "walk me through the review queue" | [`metis-review-assist`](skills/metis-review-assist/SKILL.md) | A human reviewer wants help deciding an Approve/Reject call on one specific Quarantine-tier entity — not batch-processing the whole queue. |
| "check this state machine" / "is this workflow well-formed" / "review these transitions" | [`metis-behavior-modeling`](skills/metis-behavior-modeling/SKILL.md) | A user is defining or reviewing a state machine (lifecycle states, workflow transitions) and wants determinism/completeness/reachability checked before relying on it (CONST-048/049). |
| "onboard a new repo" / "add a new project to Métis" / "set up ingestion for \<repo\>" | [`metis-onboarding`](skills/metis-onboarding/SKILL.md) | A user wants to onboard a new repository/project into Métis's ingestion pipeline — walks the real 6-step runbook from `metis-gap-remediation.md` §6. |
| "build a quality deck" / "generate a slide deck" / "I need a PowerPoint for \<review\>" | [`metis-deck-renderer`](skills/metis-deck-renderer/SKILL.md) | A user wants a shareable, dated `.pptx` quality-score snapshot for a periodic report or leadership review — point-in-time by design, never auto-refreshed. |
| "generate the site" / "build the docs site" / "publish the Academy pages" | [`metis-site-renderer`](skills/metis-site-renderer/SKILL.md) | A user wants a browsable, always-current static HTML reference site — not a dated, shareable snapshot (use `metis-deck-renderer` for that). |

No trigger above match? Don't guess which skill applies — ask the user
which of the five real workflows above they actually want, or whether
they need a real MCP tool call instead (`metis_get_context`/
`metis_get_traceability`/etc., §11.1) rather than a multi-step skill at
all. Inventing a fourth routing entry with no real skill behind it would
violate the same no-fabrication discipline every skill below already
follows.

## What's deliberately not routed here

- Direct MCP tool calls (`metis_get_context`, `metis_get_traceability`,
  `metis_check_coverage`, `metis_impact_analysis`, `metis_explain_decision`,
  `metis_explain_answer`, `metis_propose_test_skeleton`,
  `metis_submit_episode`, `metis_quality_score`) — these are single-call
  tools, not multi-stage skills; call them directly, no routing needed.
- Anything not listed above genuinely doesn't have a skill yet. Adding a
  routing entry with no real skill folder behind it is exactly the kind
  of fabrication this file exists to avoid — extend this table only when
  a real `.agents/skills/<name>/SKILL.md` exists to point at.
