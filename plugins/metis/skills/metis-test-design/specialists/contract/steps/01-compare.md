# 1 · Declared against recovered

## Actions

1. `design_report(journey, surface, section="contract")`.
2. For each row, read `declared`, `recovered` and `deviation` together. A blank
   deviation means the two agreed **where they were compared** — which is not
   the same as agreeing everywhere.
3. `get_spec` where a stakeholder-facing statement exists; `payload_shape` for
   the request side.

## Two rows that look alike and are not

| Row | Means |
|---|---|
| `no status declared` | the contract says nothing about the outcome |
| the outcome is declared, not constructed | the annotation asserts it and nothing was seen to produce it |

The second is a test worth writing. The first is a question for whoever owns the
document.

## Forbidden substitutions

- Do not fill a missing declared status from the recovered one. That erases the
  deviation you were looking for.
- Do not report "no deviations" without saying what was compared.

## Report

Deviations with both sides, rows where the contract is silent, and whether
anybody has stated where the process boundaries are.
