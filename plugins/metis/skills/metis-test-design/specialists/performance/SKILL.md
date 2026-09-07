---
name: metis-test-design-performance
description: Decide which calls are worth driving under load from recovered volume facts, and report no-basis rather than inventing an SLA where nobody has sized them. Use when a request is about load, performance testing, throughput, or which endpoints to put under stress.
allowed-tools:
  - design_sections
  - design_inputs
  - design_report
  - test_design
  - get_model
  - describe_execution
  - product_risk
  - ask
  - run_status
  - list_workflows
---

# Métis test-design · performance

## Prerequisites, from the parent

The parent (`metis-test-design`) has already established, and this skill does
not re-derive:

- a design missing a required input is `incomplete`, never lean;
- the shape comes from `design_sections()` and is never restated in prose;
- rows are ordered by risk, and a band ranks — it never forecasts;
- Métis proposes every row and decides none of them.

This skill owns the `performance` section.

## What this does

Classifies each call `performance-candidate`, `functional-only` or `no-basis`,
from facts the model actually carries — paging parameters, bulk types — and
never from a route that sounds busy.

## `no-basis` is not `functional-only`, and the difference is the point

| Verdict | Means |
|---|---|
| `performance-candidate` | a recovered volume fact makes cost scale with the caller's input |
| `functional-only` | measured, and this one does not qualify |
| `no-basis` | **the model carries no volume fact at all** — nobody sized this |

Reporting `no-basis` as `functional-only` reads as "measured, and none qualify",
which is a claim nobody made. On most models `no-basis` is the majority verdict
and saying so plainly is the honest output.

## Métis sets no threshold

`nfr_targets` is asked, and it is required. Without it there is no number a
result could fail against, so a performance case here is a case with no oracle.
Inventing an SLA is the one thing this classification must never do.

## Steps

`steps/01-candidacy.md`.

## What this skill must not do

1. **Never invent a target, an SLA or a load profile.** `no-basis` is the value.
2. **Never say anything is slow.** No execution result is ingested (§8.7, C-11);
   this reads a model, not a run.
3. **Never award candidacy on a route name.** A path is a name; a paging
   parameter is a fact.
4. **Never run load as part of designing it.** Driving load is the `run`
   execution tier and costs its own literal — a design does not touch the system
   it describes.
