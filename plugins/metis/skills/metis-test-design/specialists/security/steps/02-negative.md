# 2 · The refusal case

## Every check implies a case that is usually missing

For each recovered authority, the design carries one condition: **a caller
without it is refused.** State it as a condition on the identity, never as a
credential.

Then ask the question no tool answers: is this the right authority, and is
being wrong a defect or a compliance event? `design_inputs` carries the wording.

## Forbidden substitutions

- Do not merge the positive and negative conditions into one case. A case that
  checks two things cannot say which one failed (T-1a).
- Do not assume the refusal status. Whether an unauthorised caller gets 401, 403
  or 404 is a design decision somebody made, and the model records it or it does
  not.

## Report

One refusal condition per recovered authority, and the obligations nobody has
stated.
