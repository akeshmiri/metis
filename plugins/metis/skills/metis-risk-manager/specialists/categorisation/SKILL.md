---
name: metis-risk-manager-categorisation
description: Tailor the risk breakdown structure to one organisation, assign categories consistently, and read a distribution — including the categories nothing was recorded under. Use when a request is about risk categories, an RBS, or where a project's risk is concentrated.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - risk_categories
  - risk_report
  - risk_register_check
---

# Métis risk-manager · categorisation  (area 4)

## Prerequisites, from the parent

The parent (`metis-risk-manager`) has already established, and this skill does
not re-derive:

- risks are framed as cause → event → effect before they are categorised;
- authored and model-derived risks are counted apart in every distribution.

## What this does

The taxonomy is in `risk_categories()`; this is the procedure around it —
narrowing it for one organisation (`steps/01-tailor.md`) and reading what a
distribution actually says (`steps/02-read.md`).

Read `../../references/risk-breakdown-structure.md` for what an RBS is *for*,
which the tool cannot say.

## The reason an RBS earns its place

Three things a flat list cannot do:

1. **It prompts.** Walking ten categories asking "what could go wrong here" finds
   risks that free brainstorming misses, because unprompted recall clusters
   around whatever the team is currently worried about.
2. **It reveals absence.** A category with no risks is the interesting one.
3. **It aggregates.** Exposure by category shows where a project is fragile,
   which a ranked list of individual risks does not.

## What this skill must not do

- **Never leave the category as free text.** That is how a register grows `Tech`,
  `Technical` and `technical` as three rows in one chart. `risk_categories`
  validates and suggests the nearest match.
- **Never read an empty category as safety.** It means *no risk recorded*, which
  is either genuine safety or nobody looked — and nothing here can tell them
  apart. `risk_report` names empty categories rather than dropping them, and the
  ambiguity must be carried into whatever you report.
- **Never build a distribution from present keys only.** A chart of what exists
  cannot show a gap, which is the main thing an RBS is for.
- **Never add a category for one risk.** Adding one is a change to the taxonomy
  and affects every future assignment; it is a decision, not a convenience.
- **Never go three levels deep** unless the third level changes a response. If it
  does not, it is filing.
