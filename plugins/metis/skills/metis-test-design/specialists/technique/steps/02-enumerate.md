# 2 · Enumerate the coverage items

## Actions

1. Read `items` per row. That is how many distinct things the technique asks
   for at that behaviour — not how many test cases will exist, and not how many
   already pass.
2. Read `unavailable` in full. Report the count of refusals beside the count of
   items; a design with 40 items and 12 refusals is a different design from one
   with 40 and none.
3. Check the risk band. `metis-risk-manager-product-risk` owns the rating;
   `Very High` warrants every technique and `Low` warrants one positive case
   that says it is one.

## Forbidden substitutions

- Do not sum items across techniques into a case count. Two techniques over one
  behaviour overlap, and the overlap is not computed here.
- Do not drop `state-transition` rows as trivial. They are the coverage the
  model can always support, and they are what generation will produce.

## Report

Items per technique, refusals with causes, and where the band warrants more than
the guard can yield.
