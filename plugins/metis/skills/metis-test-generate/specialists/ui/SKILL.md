---
name: metis-test-generate-ui
description: Render covering paths for a UI surface as test cases, where a transition may inherit its guard from the API call it invokes and no selector may be guessed. Use when generating tests for a ui-surface model, or when a request names pages, components, forms or user actions.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - get_model
  - validate_model
  - coverage
  - test_cases
  - flow_scaffold
  - journey_walkthrough
  - impact
knowledge-from:
  - mbt.cross_surface
---

# Métis test-generate · ui

The parent — `metis-test-generate` — owns the pipeline, the G2 gate and the rule
that what is emitted states the accepted space and never a value. Those are
assumed here, not restated.

Two things make this surface different, and both are about *what is not on the
transition in front of you*.

## Prerequisites, from the parent

1. ✅ The model is approved (D-10)
2. ✅ One case, one assertion (T-1a)
3. ✅ The accepted space, never a value (X-6e)
4. ✅ G2 is one decision for the whole batch, default No

## A UI guard may not be its own (M-5c)

A UI transition can inherit its guard from the API transition it invokes, so a UI
model read alone **looks ambiguous exactly where the API side determines it**.
`effective_guard` conjoins the two when the `INVOKES` links are supplied.

So: if no links were supplied, say so. A report that calls a UI model ambiguous
without stating that it never looked at the API side has described its own blind
spot as a property of the system.

**Only confirmed links count** (M-5g, F-7). An `INVOKES` edge may exist as a
proposal a reviewer has not ruled on, and a proposal that behaved like a fact
would credit cross-surface coverage on a machine's guess.

## A selector is authored or it does not exist

There is no inference from a component name to a locator. A UI element with no
authored selector **raises** rather than guessing — an invented selector produces
a test that fails for a reason unrelated to the behaviour under test, which is
worse than no test because somebody has to debug it.

## Steps

`steps/01-links.md`, `steps/02-render.md`. The parent's gate step still runs.

The reasoning behind the engine this skill drives is in `knowledge/index.md`.

## What this skill must not do

1. **Never guess a selector.** Raise, and name the element that lacks one.
2. **Never report a UI model as ambiguous without saying whether links were
   supplied.** The caveat travels with the finding (M-5c).
3. **Never count an unconfirmed `INVOKES` proposal as coverage** (M-5g, F-7).
