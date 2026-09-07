# Risk fundamentals

Standard practice, not a Métis decision. These definitions would be true if Métis
were deleted; what Métis adds is enforcement of the category vocabulary and the
`derived_from` split.

## The four things people bring, and only one is a risk

| | Certainty | Has a probability? | Belongs in |
|---|---|---|---|
| **Risk** | uncertain | yes, 1–5 or 0–1 | the risk register |
| **Issue** | has occurred | no — it happened | the issue log |
| **Assumption** | treated as true, unverified | no — but its falsity is a risk | the assumption log |
| **Constraint** | fixed and known | no | the plan |

**Why mixing them breaks the register.** An issue has probability 1, so it
dominates every aggregate and makes the register look worse than the uncertain
picture it exists to hold. An assumption has no probability at all, so it cannot
be ranked, and it sits unrated forever. A constraint is certain, so responding to
it is planning, not risk management.

The most common error is the issue. The second is the assumption recorded as a
risk without stating what its falsity would cause.

## The two polarities

| | Effect | Strategy set |
|---|---|---|
| **Threat** | negative | Avoid, Mitigate, Transfer, Accept, Escalate |
| **Opportunity** | positive | Exploit, Enhance, Share, Accept, Escalate |

A register with no opportunities in it is the normal state and a real gap. The
word "risk" pulls everybody toward loss, so the upside is never elicited unless
somebody asks for it deliberately.

## The three parts of a stated risk

> **Because** *(cause)*, **there is a risk that** *(event)*, **which would**
> *(effect)*.

Each part is consumed by a different later step:

- the **cause** is what a mitigation acts on
- the **event** is what an indicator watches for
- the **effect** is what the impact rating rates

A row missing any of them cannot be responded to, monitored or rated. This is
why "Database" is not a risk, and why registers full of one-word rows are never
worked.

## Probability and impact

**Probability** is the chance the event occurs in the period under consideration
— which has to be stated, because "likely" over a two-week sprint and over a
three-year programme are different claims.

**Impact** is the consequence to an objective: schedule, cost, scope or quality.
Name which. A risk with a severe quality effect and no schedule effect is a
different management problem from the reverse, and a single blended number loses
that.

## Exposure

`Exposure = Probability × Impact` on the 5×5 grid.

**It is an ordinal rank, not a quantity.** The scale's levels are labels, so the
product orders risks and does not measure them: it cannot be summed, averaged, or
compared across projects whose scales differ. For a figure that can be summed —
sizing a contingency reserve — use Expected Monetary Value, which needs a real
probability and a real amount.

## Residual and secondary

- **Residual risk** — what remains after the response. Mitigation reduces; it
  rarely eliminates.
- **Secondary risk** — a *new* risk the response itself introduces.

Both are commonly omitted, and both omissions make a response look like a
closure.
