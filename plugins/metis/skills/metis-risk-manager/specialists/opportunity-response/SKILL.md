---
name: metis-risk-manager-opportunity-response
description: Choose a response to a positive risk — exploit, enhance, share, accept, escalate — in a register that almost certainly records none. Use when a request is about pursuing an upside, an opportunity, or a benefit that is not certain.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - risk_exposure
  - risk_emv
  - risk_register_check
---

# Métis risk-manager · opportunity-response  (area 8)

## Prerequisites, from the parent

The parent (`metis-risk-manager`) has already established, and this skill does
not re-derive:

- the register is ranked and banded;
- every risk has one named owner who can act;
- authored and model-derived risks stay distinguishable.

## Why this is its own skill and not half of the threat one

**Because a register with no opportunities in it is the normal state, and that is
a failure nobody notices.** Risk practice defines five opportunity strategies and
teams use none of them; the word "risk" pulls everybody toward loss, so the
upside half is quietly dropped and the register looks complete while covering one
polarity.

Keeping it separate means a request about upside lands somewhere that is *about*
upside, rather than in a skill whose every example is a threat.

Steps: `steps/01-choose.md`. The five strategies are in
`../../references/risk-response-strategies.md`.

## What this skill must not do

- **Never apply a threat strategy.** Mitigate, avoid and transfer are not
  opportunity responses; `risk_register_check` reports the crossed pair as
  `RISK-RESPONSE-POLARITY`.
- **Never record an opportunity as a threat with a negative impact.** The
  polarity field exists so the two can be counted separately, and a
  "negative-impact threat" makes an opportunity invisible in every report.
- **Never let Accept be the default here either.** For an opportunity, Accept
  means *we will take it if it arrives and do nothing to pursue it*, and it
  should be a decision somebody made rather than the outcome of nobody looking.
- **Never treat Share as giving it away.** Sharing gives a partner part of the
  benefit in exchange for the capability to capture it; recording it as a loss
  misses why it was chosen.
- **Never invent opportunities to balance the register.** A forced upside row is
  noise, and it teaches readers the opportunity column is decorative.
