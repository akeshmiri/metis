---
name: metis-test-design-journey
description: Design cross-surface journeys — which UI action invokes which API call, and the guard a UI action inherits from the call beneath it (M-5c) — refusing to guess a selector that was never authored. Use when a request is about end-to-end journeys, UI flows, or how a screen relates to the API behind it.
allowed-tools:
  - design_sections
  - design_inputs
  - design_report
  - journey_walkthrough
  - get_model
  - get_entity
  - list_entities
  - trace
  - product_risk
  - ask
  - run_status
  - list_workflows
---

# Métis test-design · journey

## Prerequisites, from the parent

The parent (`metis-test-design`) has already established, and this skill does
not re-derive:

- a design missing a required input is `incomplete`, never lean;
- the shape comes from `design_sections()` and is never restated in prose;
- rows are ordered by risk, and a band ranks — it never forecasts;
- Métis proposes every row and decides none of them.

This skill owns the `journey` section.

## What this does

Joins the two surfaces. A UI action and the API call it invokes are separate
transitions in separate models, and the link between them is **recovered or
authored — never assumed**.

## Two rules that come from the cross-surface engine

- **M-5c: a UI action may inherit its guard from the call it invokes.** The
  condition is not restated on the UI side; it is the API's, reached through the
  link. A design that restated it would grow a second copy that drifts.
- **A selector is authored or it does not exist** (X-6e). An element with no
  authored selector renders as absent rather than as a guess — guessing one
  produces a case that looks executable and is not.

## An empty section has two readings

Either there is no UI half, or the links were never recovered. Those are
different situations and the drift report says which. Reporting "no journeys" is
not an answer.

## Steps

`steps/01-links.md`.

## What this skill must not do

1. **Never assume a link** from a matching name, path or label. An unconfirmed
   link is not a link.
2. **Never invent a selector.** No CSS guess, no XPath guess, no "probably the
   submit button".
3. **Never restate an inherited guard** on the UI side. Point at the API's.
4. **Never present an unconfirmed link as a journey.** Say it is proposed and
   who has to confirm it.
