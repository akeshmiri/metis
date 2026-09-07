# 2 · Keep it honest as it is edited

A register decays in predictable ways. All of these are found by
`metis risk check`, and none of them is visible by reading.

## After every rating change, recalculate

`RISK-SCORE-STALE` is the defect that matters most: re-rating without
recalculating leaves a row sorting wrongly everywhere while looking normal. Run
the check after any review that touched a rating.

## Watch for polarity drift

`RISK-RESPONSE-POLARITY` — a threat strategy on an opportunity or the reverse.
Check the **polarity** first: it is usually the field that is wrong, not the
strategy.

## Watch for derivation drift

`RISK-DERIVATION` and `RISK-DERIVATION-SOURCE`. A model-derived row with no
`derived_by` cannot be re-checked when the model moves, and a row whose
`derived_from` is neither value falls into the `unknown` bucket — visible in
`risk_report`, and a sign somebody hand-edited a generated row.

## Re-run the generated half

Model-derived rows go stale when the code moves. Re-run `risk_candidates` and
`requirement_risk`; a candidate that no longer appears is a gap closed **by
evidence**, which is the one closure in this register that is not a judgement.

Two cautions: coverage is not correctness (C-11), and a candidate can vanish
because nobody looked — check `depth_consulted` before reading absence as
progress.

## Do not tidy

The temptation at every review is to delete rows that look stale. Close them with
a reason instead. A register that only shrinks is being groomed, not managed, and
the deleted rows are exactly the ones a post-mortem would want.
