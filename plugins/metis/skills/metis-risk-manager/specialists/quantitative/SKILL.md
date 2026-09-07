---
name: metis-risk-manager-quantitative
description: Put money and time on the few risks that justify it — EMV, PERT with its spread, decision trees and sensitivity — and refuse the precision the inputs do not support. Use when a request needs a contingency reserve, an expected value, a three-point estimate, or a choice between costed options.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - risk_emv
  - risk_pert
  - risk_exposure
---

# Métis risk-manager · quantitative  (area 6)

## Prerequisites, from the parent

The parent (`metis-risk-manager`) has already established, and this skill does
not re-derive:

- the register is ranked qualitatively, so there is a top band to work on;
- the 5×5 score is an ordinal rank and cannot be used as an input here;
- authored and model-derived risks are reported apart.

## What this does

Attaches quantities — money, duration, probability — to the small number of
risks where a decision turns on the figure. Read
`../../references/quantitative-methods.md` for what each method is for.

Steps: `steps/01-select.md` — which is mostly a **gate** — then
`steps/02-compute.md`.

## The distinction this skill exists to protect

A 5×5 score is an **ordinal rank**: it orders and cannot be summed. An EMV is a
**quantity**: it can. The tools enforce it — `risk_emv` refuses a 1–5 ordinal,
`risk_exposure` refuses a 0–1 fraction, and each refusal names the other tool.

That refusal is not pedantry. `risk_emv(3, 100000)` would return `300000`: five
times too large, entirely plausible, and destined for a budget.

## What this skill must not do

- **Never quantify the whole register.** Top band only, and only when a decision
  needs the number.
- **Never report a PERT estimate without its spread.** A mean alone gets read as
  a commitment. Two tasks estimating at 7 days, one ranging 6–8 and one 4–14,
  are not the same plan.
- **Never run a Monte Carlo on guessed distributions.** It produces a precise
  curve carrying no more information than the guesses, and the precision is what
  makes it dangerous. Not implemented here, deliberately.
- **Never present EMV as more accurate than its probability.** It is arithmetic
  on a judgement — more precise, not necessarily more right. Report the input.
- **Never quantify a model-derived risk's probability from coverage.** Coverage
  says *untested*; it is not a failure rate, and converting one into the other is
  C-11 with a currency symbol on it.
