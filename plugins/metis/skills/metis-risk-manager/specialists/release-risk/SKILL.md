---
name: metis-risk-manager-release-risk
description: Assess the risk of releasing a scope now — consuming coverage, validation, what could not be measured and what was actually run, then asking the five things no tool can supply. Use when a request is about release risk, go/no-go, or what shipping now would mean.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - risk_inputs
  - release_risk
  - coverage_report
  - validate_model
  - describe_execution
  - change_review
  - risk_report
  - residual_risk
  - risk_coverage
---

# Métis risk-manager · release-risk

## Prerequisites, from the parent

The parent (`metis-risk-manager`) has already established, and this skill does
not re-derive:

- authored and model-derived risks are never merged;
- `probability: null` until a person sets one.

## It consumes readiness; it does not recompute it

`metis-release-readiness` owns the coverage figures, the evidence ladder
(`confirmed` / `inferred` / `estimated` / `unknown`) and the
structural-vs-operational split. **This skill reads its output and adds the risk
framing.** Two engines computing readiness would give two answers to one
question, and the first thing anybody would ask is which to believe.

If the request is "is it ready?", that is `metis-release-readiness`. If it is
"what are we accepting if we ship?", it is this.

Steps: `steps/01-gather.md`, then `steps/02-ask.md`.

## The half Métis has, and the half it does not

| Gathered | Asked |
|---|---|
| coverage, and what could not be measured | release appetite |
| what caps confidence in those figures | rollback capability and time |
| blocking validation findings | external commitment |
| whether anything was actually run | support readiness |
| what the diff leaves unasserted | accepted known issues |

**Release appetite is the threshold.** Without it, a band is decoration and
nothing here can say whether the findings are acceptable — only what they are.
Rollback is most of the impact rating: the cost of being wrong is the cost of
staying wrong.

## What this skill must not do

- **Never compute a verdict from coverage** (C-11). Covered-and-failing is a
  real state and it is precisely the state a coverage-derived verdict calls
  ready. A verdict needs observed execution evidence.
- **Never recompute coverage.** Read `coverage_report`; it owns the figure.
- **Never treat `unmeasured` as either safety or a defect.** It is a risk about
  the *report* — the behaviour may be perfectly healthy and merely unmeasured.
  Say which kind: `structural` is missing data, `operational` is probably a
  five-minute fix.
- **Never present an incomplete assessment as a go/no-go.** With no appetite and
  no rollback answer there is no threshold to judge against.
- **Never let stale execution evidence pass as current.** An outcome observed
  last month is not a fact about today, and a verdict resting on it inherits its
  age.
