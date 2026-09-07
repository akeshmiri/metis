---
name: metis-risk-manager-framing
description: Decide whether a statement is a risk at all — as opposed to an issue, an assumption or a constraint — and write it as cause, event and effect so it can be responded to. Use when somebody brings a concern, or when a register is full of one-word rows nobody can act on.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - risk_categories
---

# Métis risk-manager · framing  (area 1)

## Prerequisites, from the parent

The parent (`metis-risk-manager`) has already established, and this skill does
not re-derive:

- every risk carries `derived_from: authored | model`, and the two never merge;
- a model-derived candidate carries `probability: null`.

## What this does

The first step of the lifecycle and the one most often skipped. Two decisions,
both before any rating:

1. **Is this a risk?** `steps/01-classify.md`
2. **Is it written so it can be responded to?** `steps/02-form.md`

Skipping this is what produces a register of one-word rows — "Database",
"Performance", "Resourcing" — that nobody can rate, respond to or close, because
nobody can tell what would have to change.

## The four things people bring, and only one is a risk

| | Certainty | Belongs in |
|---|---|---|
| **Risk** | uncertain | the risk register |
| **Issue** | already happened | the issue log |
| **Assumption** | treated as true, unverified | the assumption log — and it is a risk *source* |
| **Constraint** | a fixed boundary | the plan |

Read `../../references/risk-fundamentals.md` for what separates them and why
mixing them breaks the register.

## What this skill must not do

- **Never put an issue in the risk register.** Its probability is 1, which
  distorts every aggregate, and it crowds out the uncertain things the register
  exists for. Move it and say where.
- **Never accept a one-word risk.** "Database" cannot be responded to. Cause,
  event, effect, or it is not yet a register row.
- **Never rate anything.** Rating during framing anchors the conversation on a
  number before the risk is even stated. `metis-risk-manager-qualitative` owns
  that step.
- **Never convert an assumption into a risk silently.** An assumption that turns
  out false is a *cause*; write the risk it causes and keep the assumption
  recorded as its origin.
- **Never reword somebody's concern into something they did not say.** If the
  cause or the effect is unclear, ask. Inventing the missing half produces a risk
  nobody owns.
