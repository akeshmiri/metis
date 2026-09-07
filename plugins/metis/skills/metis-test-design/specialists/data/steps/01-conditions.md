# 1 · State the conditions

## Actions

1. `design_report(journey, surface, section="data")`.
2. For each row, check that `condition` is a condition. If it reads as a value,
   it is a defect in the design and not something to pass on.
3. `payload_shape` where the accepted space is missing — an absent space is why
   a condition cannot be stated, and it is reported rather than guessed.

## Three kinds of row, and they are not interchangeable

| `derivation` | Came from | Says |
|---|---|---|
| `contract` | the declared parameter | what the input accepts |
| `numeric_threshold` | a guard like `attempts >= 5` | the boundary values a test needs |
| `boolean_predicate` | a guard like `t.isEmpty()` | it holds, or it does not — **and no boundary** |

## Forbidden substitutions

- Do not turn a length constraint into a string of that length. State the
  condition; whoever executes the test provides the data.
- Do not drop a condition because it looks obvious. `required` is a condition
  somebody has to satisfy, and an omitted request is a real test.

## Report

Conditions per input, which inputs had no recoverable space, and whether anybody
has said where the data comes from.
