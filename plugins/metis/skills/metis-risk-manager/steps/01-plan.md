# 1 · Plan

What must be settled **before** the first risk is written down, because each of
these changes what every later entry means.

## Settle the scale, and record it

`risk_exposure` uses a 1–5 probability and a 1–5 impact. That is the tool's
scale; it is not automatically the organisation's. Before rating anything, write
down what each of the five levels means **for this project** — a 5 impact on a
two-week internal tool is not a 5 on a payments migration.

Record it where the register lives. A register whose scale is undocumented
cannot be compared with itself six months later, and its scores cannot be
re-derived by anyone who was not in the room.

## Settle the thresholds

`risk_exposure` returns a band (`Low` / `Medium` / `High` / `Very High`). A band
is not a decision. Decide, and write down:

- which band requires a documented response,
- which band requires an owner at what level,
- which band blocks a release.

Without this the band is decoration.

## Settle the appetite, per category

Appetite is not one number. A team may accept substantial schedule risk and
almost no data-protection risk. Run `risk_categories()` and state the appetite
against the categories you will actually use — an RBS is organisational, and
narrowing it in one place is expected.

## Settle who owns a risk

Every risk needs one named owner who can act. "The team" is not an owner. An
unowned risk is a note.

## Settle the derivation rule

State that the register will carry `derived_from` on every row, and that
authored and model-derived risks are reported apart. Deciding this at planning
time is much cheaper than discovering halfway through that a chart merged them.

## Output

A short written section covering: the scale, the thresholds, the appetite, the
ownership rule, and the review cadence. Then proceed to identification.
