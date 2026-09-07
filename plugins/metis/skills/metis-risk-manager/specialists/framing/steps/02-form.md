# 2 · Write it as cause → event → effect

## The form

> **Because** *(cause — a condition that exists now, or may arise)*, **there is a
> risk that** *(event — the uncertain thing)*, **which would** *(effect — the
> consequence to an objective)*.

## Why the form, and not bureaucracy

Each of the three parts is used by a different later step, and a row missing one
of them is stuck:

| Part | What uses it |
|---|---|
| **cause** | the response — mitigation acts on the cause |
| **event** | the trigger — an indicator watches for the event |
| **effect** | the impact rating — the effect is what is being rated |

So "Database" cannot be rated (rated on what effect?), cannot be responded to
(acting on which cause?) and cannot be monitored (watching for what?). It will
sit in the register until it happens.

## Name the objective the effect lands on

Schedule, cost, scope or quality. A risk with a severe quality effect and no
schedule effect is a different management problem from the reverse, and
`metis-risk-manager-qualitative` needs to know which to rate.

## Assign a category

Use `risk_categories()` and validate against it — free text is how a register
grows `Tech`, `Technical` and `technical` as three rows in one chart.
`metis-risk-manager-categorisation` owns the taxonomy itself.

## Then stop

Do not rate it. Hand the framed candidate on.
