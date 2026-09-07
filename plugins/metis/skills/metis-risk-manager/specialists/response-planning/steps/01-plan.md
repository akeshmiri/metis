# 2 · Plan it so somebody can execute it

A strategy is a word. A plan has five parts, and a row missing any of them will
not be acted on.

## 1 · Actions and an owner

Concrete actions, each with **one** named owner who can act, and a date. "The
team" is not an owner. An action with no date is an intention.

## 2 · The trigger

The observable condition that says the risk is materialising — a threshold, an
event, a date passing. This is what turns a contingency plan from a document
into something that fires.

A trigger must be observable by somebody who is not thinking about this risk.
"If it looks like it will be late" is not a trigger; "if the integration branch
is not green by the 14th" is.

## 3 · The fallback

What happens if the response fails or the trigger fires anyway. The response
plan reduces the risk; the fallback is for when it occurs regardless. A register
with responses and no fallbacks assumes every mitigation works.

## 4 · The reserve

For actively accepted risks and for residual exposure: contingency in time or
money, sized from the quantified figure where there is one. Say what it is for.
An unallocated reserve gets spent on whatever arrives first.

## 5 · The residual and the secondary

Both are new rows in the register, not footnotes:

- **Residual** — what remains after the response. A mitigated risk is rarely a
  closed one, and recording the residual is what stops the response reading as a
  closure.
- **Secondary** — a risk the response itself introduces. Rate it like any other.

## For a model-derived risk

The response to *untested behaviour* is almost always **a test**, not a reserve.
Hand it to the coverage or test-generation workflow rather than planning a
contingency around it — and note that once the behaviour is covered, the risk is
closed by evidence rather than by judgement, which is the one case in this
register where closure can be checked mechanically.

## Re-check the register

Run `risk_register_check` after editing. Changing a response without changing
polarity, or re-rating while planning, is exactly how `RISK-SCORE-STALE` and
`RISK-RESPONSE-POLARITY` get introduced.
