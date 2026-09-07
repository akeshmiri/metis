---
name: metis-risk-manager-requirement-risk
description: Assess the risk one requirement carries — gathering EARS conformance, criteria and their provenance, approval state and coverage from the graph, then asking the five things no tool can derive. Use when a request is about the risk in a requirement, whether a requirement is safe to build, or requirement quality.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - risk_inputs
  - requirement_risk
  - get_requirement
  - check_ears
  - ac_quality
  - coverage_report
  - trace
  - search_knowledge
  - risk_exposure
knowledge-from:
  - risk.inputs
---

# Métis risk-manager · requirement-risk

## Prerequisites, from the parent

The parent (`metis-risk-manager`) has already established, and this skill does
not re-derive:

- every risk carries `derived_from`, and a model-derived one says *this is
  untested*, never *this is likely to fail*;
- `probability: null` until a person sets one.

## What this does

Applies the gather-or-ask ledger to one requirement. `requirement_risk` gathers
what Métis holds; the five things it cannot derive come back as questions with
the words to ask.

Steps: `steps/01-gather.md`, then `steps/02-ask.md`. The reasoning behind the
ledger itself is in `knowledge/index.md`, generated from `risk/inputs.py`.

## The half Métis has, and the half it does not

| Gathered | Asked |
|---|---|
| EARS conformance, criterion quality | business criticality |
| criteria count and provenance | volatility |
| lifecycle state, supersession | regulatory exposure |
| coverage of its behaviour | stakeholder agreement |
| the source anchor | external dependency |

`risk_inputs("requirement")` returns both lists with the exact questions.

**The right column is not a nice-to-have.** Business criticality *is* the impact
rating; volatility *is* the probability. Without them there is no exposure — only
a list of observations. That is why the assessment reports `incomplete` and why
that word appears before the findings rather than after.

## What this skill must not do

- **Never present the gathered half as the assessment.** It is the half that was
  reachable, and it is the half that does not contain the impact rating.
- **Never read a short risk list as a safe requirement.** Check `status`. If it
  is `incomplete`, the list is short because nobody answered.
- **Never invent a probability or a criticality** to make the assessment look
  finished. `probability: null` is the honest value and the document preserves it.
- **Never treat zero coverage as a defect.** Coverage says *untested* (C-11).
  Untested and broken are different claims.
- **Never assess a requirement without saying which inputs were not gathered.**
  The document lists them with what their absence means, and that list is the
  part a reader needs in order to weigh the rest.
