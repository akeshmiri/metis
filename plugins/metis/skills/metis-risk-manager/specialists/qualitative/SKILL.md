---
name: metis-risk-manager-qualitative
description: Rank risks on the 5x5 probability-impact grid, producing an order and a band rather than a measurement, with no financial input. Use when a request is about scoring, prioritising or heat-mapping risks, or reviewing a register's ratings.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - risk_exposure
  - risk_categories
  - risk_register_check
---

# Métis risk-manager · qualitative  (area 5)

## Prerequisites, from the parent

The parent (`metis-risk-manager`) has already established, and this skill does
not re-derive:

- the 1–5 scale is defined **for this project** and written down, and the band
  thresholds are agreed (`steps/01-plan.md`);
- candidates arrive unrated from `metis-risk-manager-identification`;
- a model-derived candidate has `probability: null`, and this is where a person
  supplies one — after which the rating is theirs;
- authored and model-derived risks are reported apart, never averaged.

## What this does

The cheap step that makes the expensive one affordable. Rank everything here;
`metis-risk-manager-quantitative` then costs money and effort on the few rows
where a decision turns on a figure a rank cannot supply.

Steps: `steps/01-rate.md`, then `steps/02-rank.md`.

**Ranking is usually the whole answer.** Going on to quantify a Low risk is how
a risk process becomes theatre.

## The one thing to keep saying

**The score is an ordinal rank, not a quantity.** `risk_exposure` returns a
`basis` line saying so, and it is there to be repeated. A 5×5 score cannot be
summed, averaged, or compared across projects whose scales differ.

## What this skill must not do

- **Never average scores.** Not across a register, not across a category, not
  across time. The mean of an ordinal is not a number about anything.
- **Never report a score without its basis.** Stripped of the ordinal caveat, a
  12 gets treated as a measurement within one hand-off.
- **Never convert a 5×5 rating into a probability** so that EMV will accept it.
  A "4" does not mean 0.8 and nothing in the scale says it does.
- **Never merge authored and model-derived rows in a heat map** without saying
  which is which. A model-derived row says *untested*, not *likely*.
- **Never rate an issue.** Probability 1 means it has happened; it is not a risk.
- **Never quietly change a rating.** Re-rating without recalculating the score is
  `RISK-SCORE-STALE`: it sorts the risk wrongly in every report while looking
  completely normal.
