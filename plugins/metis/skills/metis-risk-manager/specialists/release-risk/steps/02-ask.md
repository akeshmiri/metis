# 2 · Ask the five that decide it

## The questions, as written

`risk_inputs("release")` carries them verbatim. The two that matter most:

> **Appetite** — "What are we willing to ship broken this time, and what would
> stop the release outright?"

Without this there is **no threshold**. Every finding gathered in step 1 is a
fact with no standard to judge it against, and any verdict would be somebody
substituting their own appetite silently.

> **Rollback** — "Can this be rolled back? How long does it take, and who does
> it?"

This is most of the impact rating. The same defect shipped with a two-minute
rollback and with a two-day one are not the same risk, and nothing in the model
distinguishes them.

## Ask the right person

| Question | Usually |
|---|---|
| appetite | the release decision-maker — the person who would carry a bad call |
| rollback | whoever operates the deployment |
| external commitment | the account or product owner |
| support readiness | the on-call lead |
| accepted known issues | product, with the defect list in front of them |

## Then, and only then, frame the decision

With the answers you can say: *these findings, against this appetite, with this
rollback cost.* That is a decision somebody can make.

Without them, report the findings and the missing inputs — and say plainly that
this is not a go/no-go. An incomplete assessment presented as a recommendation is
the most expensive mistake in this entire skill family, because it is the one
somebody acts on.

## Never hand back a verdict from coverage

If the answer to "did anything actually run" is no, say so first. Coverage
answers *is this tested*, never *did it pass*, and the gap between those two is
exactly where a release goes wrong.
