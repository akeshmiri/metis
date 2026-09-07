---
name: metis-risk-manager-identification
description: Produce risk candidates through a chosen technique, written as cause-event-effect, and rate none of them. Use when a request is about finding or eliciting risks, running a risk workshop, or turning what Métis observes into candidate register entries.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - risk_categories
  - risk_candidates
---

# Métis risk-manager · identification

## Prerequisites, from the parent

The parent (`metis-risk-manager`) has already established, and this skill does
not re-derive:

- the scale, the thresholds and the appetite are settled (`steps/01-plan.md`);
- every risk carries `derived_from`, and authored and model-derived risks are
  never merged;
- a model-derived candidate carries `probability: null` and it stays null.

## What this does

Produces **candidates**. It rates nothing, prioritises nothing and responds to
nothing. Those are three later steps with three different procedures, and doing
them here suppresses the candidates this step exists to collect.

Steps: `steps/01-technique.md`, then `steps/02-elicit.md`.

## What Métis can contribute, and what it cannot

`risk_candidates` returns behaviour a change leaves unasserted — real,
severity-graded, and already in the register's shape. Take it.

**It covers one category out of ten.** Métis cannot see a supplier about to miss
a date, a sponsor leaving, a regulation changing, or an architecture that will
not scale. A register built from `risk_candidates` alone will look full and be
almost empty. Run a human technique as well, always.

Check `depth_consulted` in the result. When false, nobody looked at coverage
depth, and a short list means the input was missing — not that the change is
safe.

## What this skill must not do

- **Never rate a candidate.** No probability, no impact, no score. Handing a
  rated candidate to the qualitative specialist anchors it, which is the exact
  bias that step's procedure exists to avoid.
- **Never write a one-word risk.** "Database" cannot be responded to. Cause,
  event, effect, or it is not a candidate.
- **Never put an issue in the register.** If it has already happened it is an
  issue: its probability is 1 and it distorts every aggregate. Say so and move it.
- **Never present `risk_candidates` output as a complete identification.** State
  which categories it covered and which nobody has looked at yet.
- **Never invent a probability for a model-derived candidate** to make it look
  like the authored ones.
