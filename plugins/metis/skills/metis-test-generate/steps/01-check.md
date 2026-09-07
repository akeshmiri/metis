# 01 — check the model may be generated from

## Actions

1. `metis validate --journey <j> --surface api`. Blocking findings stop the run.
2. Confirm approval. Through MCP, `test_cases` reports `model_is_approved` and
   `unapproved_elements`; on the CLI the workflow's `model_is_approved`
   precondition refuses the run. **Report the count, not "it is approved".**
3. `coverage_report` (or `metis coverage-gap`) for what the run cannot measure.
   Carry `unmeasured` into what you tell the user — a coverage figure with an
   unstated denominator is the number C-11 warns about.

## Forbidden substitutions

- Do not proceed on "probably approved". The count is available; use it.
- Do not treat `covered: 0, uncovered: 0` as full coverage. An empty model
  produces both, and so does a typo in the journey name.

## Drift check

Every path generated should serve the journey asked for. If most of them do not,
the scope was wrong — re-derive rather than rendering them.

## Report

The model id, the approval count, the criterion, and what could not be measured.
