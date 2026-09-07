---
name: metis-risk-manager-register
description: Set up and keep a risk register — what each field is for, what makes a row actionable, and the self-contradictions that make one wrong while looking normal. Use when a request is about creating, structuring, auditing or cleaning up a risk register.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - risk_register_check
  - risk_report
  - risk_categories
  - risk_exposure
---

# Métis risk-manager · register  (area 9)

## Prerequisites, from the parent

The parent (`metis-risk-manager`) has already established, and this skill does
not re-derive:

- every row carries `derived_from: authored | model`, and no figure merges them;
- a model-derived row carries `probability: null` until a person sets one;
- the scale and thresholds were settled at planning time.

## What this does

The register is a **file** — `Risk` is deliberately not a graph label, and
`docs/academy/PROPOSAL-risk-in-the-graph.md` carries the argument and the
condition that would reverse it. This skill is what keeps that file useful:
setting it up (`steps/01-shape.md`) and keeping it honest as it is edited
(`steps/02-upkeep.md`).

The field definitions and coherence rules are in `knowledge/` — generated from
`risk/register.py`, which is where they are enforced.

## The defect worth more attention than all the others

**`RISK-SCORE-STALE`**: the stored score no longer equals probability × impact,
because somebody re-rated and did not recalculate. The row then sorts wrongly in
every report, every chart and every "top ten" — and it looks completely normal
while doing it. `risk_register_check` finds it; nothing else will.

## What this skill must not do

- **Never judge whether a risk is real.** That is a person's call.
  `risk_register_check` finds self-contradiction, never truth, and a clean result
  is not a statement that the register is right.
- **Never store a score you did not recompute.** Everything that reads the
  register should derive the band from probability × impact rather than trusting
  the column.
- **Never merge the derivations in a total, an average or a chart.**
- **Never let a row exist without an owner.** A risk nobody owns is a risk nobody
  works, and it will be in the register unchanged at closure.
- **Never delete a row.** Close it with a reason —
  `metis-risk-manager-monitoring` owns the four. A row that vanishes takes its
  lesson with it.
