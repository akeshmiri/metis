# 2 · Depth achievable against depth warranted

## The interesting case is the gap

`depth` says what the model can support: `full`, `partial`, or `positive-only`.
`warranted` says what the risk band justifies. **Neither finds the interesting
case alone** — behaviour that warrants deep testing and cannot receive it.

That gap is carried into the uncertainty section as an open question with an
owner, because it is a decision: cover it manually, change the code so it can be
asserted, or accept it. It will never appear in a coverage figure — the
behaviour may be fully covered at the depth it can reach.

## Actions

1. Read the `depth` and `warranted` columns together.
2. For every row where warranted exceeds achievable, name the behaviour and ask
   which of the three responses applies.
3. Do not average the two. They are answers to different questions.

## Report

Rows where the warrant exceeds what is achievable, and what was decided for each.
