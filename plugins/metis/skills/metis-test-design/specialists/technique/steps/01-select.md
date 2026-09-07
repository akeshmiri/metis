# 1 · Select the technique

## From the guard, and only from the guard

Run `design_report(journey, surface, section="technique")`. Each row already
names the technique and the condition it varies. Your job is to read the
selection, not to make a second one.

## Which technique the shape of the guard implies

| The guard says | Technique | Why |
|---|---|---|
| `attempts >= 5` | boundary-value | the interesting values are 4, 5, 6 — not "true" and "false" |
| `t.isEmpty()` | equivalence-partition | it holds or it does not; there is no third value |
| several transitions share `(state, trigger)` | decision-table | which **combinations** are reachable is where a missing rule hides |
| two or more inputs vary | pairwise | most multi-input defects are triggered by a pair |
| anything at all | state-transition | it is what the model *is* |

Guard coverage varies each condition independently. A decision table asks which
combinations are reachable and what each produces. **They are different
questions and the second is the one that finds a missing rule.**

## Report

The technique per behaviour, and every refusal with its cause.
