# 1 · Profile the product risk

## Type the risk item first

A risk attaches to the thing it threatens, and the kind of thing decides which
factors can be gathered at all. `product_risk` reports the type it used:

| Type | Métis labels | What can be gathered |
|---|---|---|
| functional | `Requirement`, `Feature`, `AcceptanceCriterion` | criteria, provenance, EARS |
| architectural | `Endpoint`, `Page`, `Class` | fan-in, fan-out |
| behavioural | `Transition`, `ApiCall`, `UiAction` | branching, guards, coverage |
| test | `TestCase`, `Scenario` | executions |

A risk written against "the login service" is not typed and cannot be profiled.
Push back and get the item.

## Gather the technical half

`product_risk(journey, surface)` returns, per behaviour, the raw counts **and**
the 1–5 rating derived from them. Report both. The rating is what orders; the
count is what somebody disagrees with, and a rating with its measurement hidden
is not reviewable.

Four PRISMA factors are covered — complexity and interrelations. Four are not:
degree of re-use, size, technology, team experience. The output names them, and
so should you. A profile that reads as complete when it covers half the factors
is worse than one that says which half.

## Read the detectability, and read `unmeasured` separately

Three populations, and they are not three degrees of one thing:

- **scored** — a detectability value exists;
- **failing** — a test that ran reported this broken. A defect, not a gap;
- **unmeasured** — coverage could not be measured. Nothing may be concluded.

Saying "12 of 40 are undetectable and 3 could not be measured" is the honest
sentence. Folding the 3 into either side is the failure this refuses.

## Then stop

Do not rate impact here and do not order anything yet. Impact is the asked half
and it is a different conversation with different people — PRISMA's rule is that
impact factors go to business representatives and likelihood factors to technical
ones, and running them together makes both converge.
