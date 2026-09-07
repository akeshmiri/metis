---
name: metis-risk-manager-response-planning
description: Turn a chosen response strategy into something somebody can execute — actions with one owner, an observable trigger, a fallback, a reserve — and record the residual and secondary risk it leaves. Use when a request is about response planning, contingency, triggers or fallback plans.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - risk_exposure
  - risk_emv
  - risk_register_check
---

# Métis risk-manager · response-planning  (area 10)

## Prerequisites, from the parent

The parent (`metis-risk-manager`) has already established, and this skill does
not re-derive:

- the risk is ranked and banded, and its polarity is settled;
- a strategy has been chosen by `metis-risk-manager-threat-response` or
  `metis-risk-manager-opportunity-response`;
- every risk has one named owner who can act.

## What this does

**A strategy is a word; this is what makes it happen.** Separate from choosing
the strategy because the two fail differently: a badly chosen strategy is visible
in review, whereas a well-chosen strategy with no trigger and no owner looks
completely fine in the register and never executes.

Steps: `steps/01-plan.md` — actions and an owner, the trigger, the fallback, the
reserve, and the residual and secondary risk.

## What this skill must not do

- **Never leave a trigger unobservable.** "If it looks like it will be late" is
  not a trigger; "if the integration branch is not green by the 14th" is. A
  trigger has to fire for somebody who is not thinking about this risk.
- **Never write "the team" as an owner.** One named person who can act, or the
  action will not happen.
- **Never plan a response with no fallback.** The response reduces the risk; the
  fallback is for when it occurs anyway. A register of responses with no
  fallbacks assumes every mitigation works.
- **Never leave a reserve unallocated.** A contingency with no stated purpose is
  spent on whatever arrives first.
- **Never record the residual as a footnote.** It is a row. A mitigated risk is
  rarely a closed one.
