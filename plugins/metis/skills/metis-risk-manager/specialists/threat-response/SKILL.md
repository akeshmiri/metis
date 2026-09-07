---
name: metis-risk-manager-threat-response
description: Choose a response to a negative risk — avoid, mitigate, transfer, accept, escalate — and record the residual and any secondary risk the response introduces. Use when a request is about mitigating, avoiding, transferring or accepting a threat.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - risk_exposure
  - risk_emv
  - risk_register_check
---

# Métis risk-manager · threat-response  (area 7)

## Prerequisites, from the parent

The parent (`metis-risk-manager`) has already established, and this skill does
not re-derive:

- the register is ranked and banded, and the thresholds say which band requires
  a documented response;
- every risk has one named owner who can act;
- authored and model-derived risks stay distinguishable.

## What this does

Picks a strategy for a **threat**. The five are in
`../../references/risk-response-strategies.md`; `steps/01-choose.md` is how to
choose between them.

Turning the chosen strategy into something executable — owner, trigger,
fallback, reserve — is `metis-risk-manager-response-planning`. A strategy word
without that is not a plan.

## Confirm the polarity before anything else

If this is an **opportunity**, stop and use
`metis-risk-manager-opportunity-response`. The strategy sets are disjoint apart
from Accept and Escalate, and `risk_register_check` reports a crossed pair as
`RISK-RESPONSE-POLARITY` — which in practice almost always means the polarity
was recorded wrongly, not that the strategy was badly chosen.

## What this skill must not do

- **Never respond to everything.** A response for every row spends the
  mitigation budget on the wrong risks. The thresholds decide which rows get one.
- **Never treat Transfer as elimination.** Insurance and fixed-price contracts
  move who pays. The event still occurs, the schedule still slips, and closing a
  transferred risk as though the impact were gone is a standard register defect.
- **Never let Accept be a default.** Accepted-with-a-reserve-and-an-owner is
  management; never-responded-to is its absence, and six months later a register
  cannot tell them apart unless the reason was written down.
- **Never omit the residual.** Mitigation reduces and rarely eliminates. Without
  a residual recorded, a response reads as a closure.
- **Never omit the secondary risk.** Outsourcing to remove a capacity risk
  introduces a supplier risk. It is a new row.
- **Never plan a contingency reserve against a model-derived risk.** The response
  to *untested behaviour* is a test, not money.
