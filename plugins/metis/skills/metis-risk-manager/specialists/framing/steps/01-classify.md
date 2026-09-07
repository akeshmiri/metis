# 1 · Is this a risk?

Ask in this order. The first "yes" decides it.

## Has it already happened?

Then it is an **issue**, not a risk. Probability 1 is not a rating, it is a
statement that the uncertainty is gone. Issues in a risk register distort every
aggregate and hide the uncertain things the register is for.

Move it to the issue log. If its occurrence makes *other* things more likely,
those are risks and they are new rows.

## Is it something being treated as true without evidence?

Then it is an **assumption**. Assumptions are the richest source of risk in most
projects and they are invisible precisely because nobody states them — "the data
will be clean", "the API will not change", "the third party will answer in
staging".

Record the assumption, then write the risk it causes: *if this assumption is
false, what happens?* The assumption stays as the risk's origin.

## Is it a fixed boundary somebody has set?

Then it is a **constraint** — a date, a budget, a technology mandate. It belongs
in the plan. Constraints *generate* risks (a fixed date with variable scope is a
risk) but the constraint itself is certain and has no probability.

## Is it uncertain, and would it affect an objective?

Then it is a **risk**. Continue to `02-form.md`.

## Also settle the polarity

Would the effect be negative (**threat**) or positive (**opportunity**)? Most
registers record no opportunities at all, which is a failure nobody notices —
so ask the question explicitly rather than assuming the answer.
