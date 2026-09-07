---
name: metis-test-design-data
description: State what the test data must satisfy as a condition on the accepted space — never a value, never a fixture. Use when a request is about test data, input constraints, what a payload must contain, or what must be violated to reach a rejection.
allowed-tools:
  - design_sections
  - design_inputs
  - design_report
  - payload_shape
  - get_model
  - get_requirement
  - ask
  - run_status
  - list_workflows
---

# Métis test-design · data

## Prerequisites, from the parent

The parent (`metis-test-design`) has already established, and this skill does
not re-derive:

- a design missing a required input is `incomplete`, never lean;
- the shape comes from `design_sections()` and is never restated in prose;
- rows are ordered by risk, and a band ranks — it never forecasts;
- Métis proposes every row and decides none of them.

This skill owns the `data` section.

## What this does

Turns each input into a **condition**. `payload_shape` supplies the accepted
space, the guard supplies what must hold, and the declared constraints supply
what must be **violated** to reach a rejection (GD-3).

## The rule that governs every row

**M-9: a guard is a test data requirement, never a solved value.** Métis may
say a test needs `attempts = 4`, because that is a condition on the data. It may
not produce a username, a password or a payload. The accepted space renders as
`<string, length 3..40, required>` (X-6e) — the space, not something to paste.

`derivation` says how a condition was reached, so a reader can weigh a bound
recovered from a declared constraint differently from one read out of a numeric
guard.

## The half Métis has, and the half it does not

| Gathered | Asked |
|---|---|
| the accepted space, per input | where test data comes from |
| what must hold, from the guard | what may never appear in it (personal data, production extracts) |
| what must be violated, from the constraints | who provisions it |

Without the right column the conditions are correct and **unsatisfiable by
anybody**, which is what `absent_means` says where the values would be.

## Steps

`steps/01-conditions.md`.

## What this skill must not do

1. **Never produce a value, an example or a fixture.** Not even a plausible one,
   and not when asked directly. The condition is the answer (M-9).
2. **Never widen an accepted space to make a condition satisfiable.** If nothing
   can satisfy it, that is a finding about the contract.
3. **Never treat "no constraint declared" as "anything goes".** It means nobody
   declared one, which is a question for the contract owner.
4. **Never merge a violation condition with a satisfaction one.** Reaching a 400
   and reaching a 200 are different rows and different cases.
