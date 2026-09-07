---
name: metis-test-design-contract
description: Compare what each endpoint declares against what its code was recovered to do, and report a deviation as a test case and a question rather than as a defect. Use when a request is about API contracts, specification drift, response shapes, or whether the documentation matches the implementation.
allowed-tools:
  - design_sections
  - design_inputs
  - design_report
  - payload_shape
  - get_model
  - get_spec
  - validate_model
  - product_risk
  - ask
  - run_status
  - list_workflows
---

# Métis test-design · contract

## Prerequisites, from the parent

The parent (`metis-test-design`) has already established, and this skill does
not re-derive:

- a design missing a required input is `incomplete`, never lean;
- the shape comes from `design_sections()` and is never restated in prose;
- rows are ordered by risk, and a band ranks — it never forecasts;
- Métis proposes every row and decides none of them.

This skill owns the `contract` section.

## What this does

Puts the declared outcome beside the recovered one and names the difference as a
condition. The status, the response body and the media types come from the
model; the outcome's source says whether it was **constructed in code** or only
**declared on an annotation**, and that difference is the deviation question in
its purest form.

## A deviation is a case and a question, never a defect

The document may be stale or the code may be wrong, and deciding which is a
person's judgement that no static comparison can make. So the design carries
both sides and asks — it does not pick a winner and it does not file a bug.

## It depends on a boundary nobody has stated

`runtime_architecture` is asked and required here. Without it, this section
describes one process as though it were the system: what crosses a boundary,
and therefore what a contract test is even for, is unknown.

## Steps

`steps/01-compare.md`.

## What this skill must not do

1. **Never declare the code correct or the document correct.** Report the
   difference; the choice is somebody's.
2. **Never emit a concrete value where the contract states a space** (X-6e). A
   base URL renders as a placeholder with its reason.
3. **Never treat a declared-only outcome as recovered.** Nothing was seen to
   produce it, and that is exactly what makes it worth a test.
4. **Never call an endpoint to check.** A design reads the model; contacting the
   system under test is a tier and it is `off` by default.
