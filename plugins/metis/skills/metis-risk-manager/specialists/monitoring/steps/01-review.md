# 1 · Review, on the agreed cadence

## Set an indicator per risk, not a review date per register

A risk with no indicator is one nobody looks at until it happens. The indicator
is the observable thing the trigger watches — a metric, a date, a state — and it
must be checkable by somebody who is not thinking about this risk.

## Each review does five things

1. **Re-rate what has changed.** Probability and impact move as the project
   moves. Then **recalculate the score** — re-rating without recalculating is
   `RISK-SCORE-STALE`, and it sorts the row wrongly in every report while looking
   completely normal. Run `risk_register_check` after every review, for this.
2. **Check the triggers.** Has any fired? A fired trigger with no action is the
   most expensive kind of register defect.
3. **Check response progress.** An owner, a date, a status. A response in
   progress for four reviews is not in progress.
4. **Add what is new.** Including a fresh `risk_candidates` run if the code has
   moved. Pass `journey` so positive-path-only findings are evaluated; otherwise
   the list is short for a reason unrelated to safety.
5. **Close what is done** — see `02-close.md`.

## Report with `risk_report`, not by hand

`risk_report(register_json)` is the consolidated view: the band distribution with
the derivations kept apart, the categories nobody has recorded anything under,
which High and Very High risks lack an owner or a response, and the coherence
findings. Do not assemble this by reading rows — the tool recomputes bands from
probability × impact rather than trusting a stored `score`, which is the one
thing a hand-written summary reliably gets wrong.

Report the top band, what changed since last time, what fired, and what is
overdue. A full register dump is not a report: nobody reads sixty rows, and the
five that matter are invisible inside them.

## When Métis is the source

`coverage_report`'s `unmeasured` entries belong in the review: a figure that
could not be produced is a risk **about the report**, not about the behaviour,
which may be perfectly healthy and merely unmeasured. Say which — the distinction
is the whole reason those entries exist rather than being silently omitted.
