# Quantitative methods

Standard practice. Use these on the top band only — quantifying a Low risk is how
a risk process turns into theatre.

## Expected Monetary Value

`EMV = probability × impact`, where probability is a **real** probability (0–1)
and impact is money. `risk_emv` computes it.

It is a quantity: it may be summed across a portfolio, which is what makes it
useful for sizing a contingency reserve. That is exactly what a 5×5 score cannot
do.

**The trap.** A 1–5 ordinal passed as the probability produces a number up to
five times too large that looks entirely normal, and EMV is the figure that ends
up in a budget. `risk_emv` refuses a probability outside 0–1 for this reason.

**The honest caveat.** EMV is arithmetic on a probability that is usually
somebody's judgement. It is more precise than a 5×5 score, and not necessarily
more accurate. Report the input beside the output.

## PERT / three-point estimation

`(O + 4M + P) / 6`, weighting the most likely case four times. `risk_pert`
computes it and returns the standard deviation `(P − O) / 6`.

**Always report the spread.** A mean without one invites the estimate to be read
as a commitment, which is the single most common way a three-point estimate does
damage. Two tasks can both estimate at 7 days where one ranges 6–8 and the other
4–14; those are not the same plan.

`risk_pert` refuses estimates that are out of order rather than sorting them: a
confident answer computed from an input somebody stated wrongly is worse than a
refusal.

## Decision trees

For a choice between options where each branch has a probability and a value.
Compute EMV per branch and take the best. The tree's value is not the number — it
is that it forces the branches and their probabilities to be written down where
someone can disagree with them.

## Sensitivity analysis (tornado diagram)

Vary one input at a time across its plausible range and record the effect on the
outcome; sort by the size of the swing. The result shows which uncertainties
actually matter.

This is usually the highest-value quantitative technique, because it redirects
effort: most projects have two or three inputs that dominate and a long tail that
does not, and effort is typically spread evenly across them.

## Monte Carlo simulation

Sample the input distributions many times to get an outcome distribution rather
than a point estimate. Answers "what is the probability we finish by the 30th",
which no single-point method can.

**Not implemented here**, deliberately: it needs a distribution per input and a
correlation structure between them, and both are usually guessed. A simulation
built on guessed distributions produces a precise-looking curve carrying no more
information than the guesses. The precision is the danger.

## Choosing

| You need | Use |
|---|---|
| To order the register | The 5×5 (`risk_exposure`) — not these |
| To size a contingency reserve | EMV, summed |
| To estimate a duration or cost | PERT, with the spread |
| To choose between options | A decision tree |
| To know where to spend effort | Sensitivity |
| A confidence level on a date | Monte Carlo — with honest distributions or not at all |
