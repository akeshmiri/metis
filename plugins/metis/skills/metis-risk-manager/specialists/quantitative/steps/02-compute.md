# 4 · Compute, with the tools, and report what it rests on

Read `../../references/quantitative-methods.md` for what each method is for.

## Always call the tool

`risk_emv`, `risk_pert`, `risk_exposure`. Never compute in prose. The arithmetic
is trivial and the input validation is not — the tools refuse the scale
confusions that produce plausible wrong answers, and prose cannot.

Each returns a `basis` line. It goes into the report.

## EMV

`risk_emv(probability, financial_impact)`.

Sum across the top band for a reserve. Report the summed figure **with the
probabilities it came from**, because the sum inherits every one of their errors
and hides them behind one confident number.

If the tool refuses, the probability was on the wrong scale. Do not divide by
five to make it fit — find a real probability, or stay with the ranking.

## PERT

`risk_pert(optimistic, most_likely, pessimistic)`.

Report the estimate **and** the standard deviation, in the same sentence. The
spread is the part that carries the risk information; dropping it converts an
estimate into a commitment. Two tasks estimating at 7 days, one ranging 6–8 and
one 4–14, are not the same plan.

If the tool refuses, the three estimates were out of order. That is somebody
having stated them wrongly, and it needs a person — not a sort.

## Decision trees

Compute EMV per branch with `risk_emv` and take the best. Show the tree. Its
value is not the winning number; it is that the branches and their probabilities
end up written down where someone can disagree with them.

## Sensitivity

Vary one input at a time across its plausible range, record the swing in the
outcome, sort descending. Report the top three and what they imply about where to
spend effort. This usually changes the plan more than any other method here.

## Report the derivation split

If any quantified risk was model-derived, say so explicitly and separately. A
reserve sized partly from coverage gaps is a different claim from one sized from
judged probabilities, and merging them into a single figure removes the reader's
ability to tell.
