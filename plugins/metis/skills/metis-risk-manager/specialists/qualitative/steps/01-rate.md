# 1 · Rate probability and impact, separately

## Rate them independently

Rate probability across the whole register first, then impact across the whole
register. Rating both at once on one risk causes them to converge — a risk that
feels serious gets a 4 and a 4 — and the grid loses the distinction it exists to
make. A high-impact, low-probability risk and a low-impact, high-probability one
need different responses and must not land in the same cell.

## Anchor against the written scale

Use the definitions from the parent's `steps/01-plan.md`. If the scale was never
written down, stop and write it: ratings made against an unstated scale cannot be
re-derived by anyone who was not present, which makes the whole register
unreviewable.

## Impact is against the project's objectives

Not "how bad does this feel". Impact is on schedule, cost, scope or quality —
name which. A risk with a 5 on quality and a 1 on schedule is a different
management problem from the reverse, and collapsing them to one number loses
that. Where a single figure is needed, take the maximum and say which objective
it came from — not the average, which understates every risk with one severe
consequence.

## Compute the score with the tool

Call `risk_exposure(probability, impact)`. Do not multiply in prose. The tool
returns the cell, the band and the basis, and it refuses an input on the wrong
scale — a 0–1 probability here is a real probability that belongs in `risk_emv`,
and it is caught rather than silently treated as a 0.

## For model-derived candidates

The impact is already set from the finding's severity. **The probability is
absent and must be supplied by a person.** Record who. Once a human sets it, the
rating is theirs; what stays true is that the risk was *identified* by the model,
which is what `derived_from` continues to record.
