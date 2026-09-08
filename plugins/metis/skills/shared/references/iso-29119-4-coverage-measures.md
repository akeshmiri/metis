# Coverage measures — ISO/IEC/IEEE 29119-4

**A side reference, not loaded by default.** Consult it when a coverage figure
has to be named in the standard's vocabulary, or when somebody asks what a
percentage actually measured.

It would still be true if Métis were deleted, which is why it is a reference
rather than knowledge. The techniques themselves are in
`test-techniques-reference.md` beside this file; this is the **measurement** half.

**Shared, because three skills consume it**: `metis-coverage-report` computes the
measures, `metis-behavior-modeling` checks the machine they are computed over,
and `metis-test-design-technique` chooses which technique a behaviour warrants.

## The structure of a coverage measure

29119-4 defines each test design technique together with the **coverage items**
it produces and the **coverage measure** over them. The shape is always the same:

    coverage = coverage items exercised / coverage items identified

Two things follow, and both matter more than the arithmetic:

- **The denominator is a property of the technique**, not of the system. Change
  the technique and the same test suite reports a different percentage.
- **A coverage item is not an assertion.** An item is what a technique asks for;
  whether anything checks it is a separate question (C-11).

## The criteria Métis computes

Read from `mbt/criteria.py`, which is the source of truth:

| Criterion | Coverage items | Notes |
|---|---|---|
| `all-states` | each state in the machine | the weakest of the three structural measures |
| `all-transitions` | each transition | Métis's default |
| `all-transition-pairs` | each adjacent pair of transitions | 29119-4's higher state-machine measure |
| `guard-coverage` | each atomic condition in a guard | bounded by the short-circuit chain (GD-1..GD-9), not the full product |
| `boundary-coverage` | each boundary of a numeric threshold | **refused** where a predicate has no boundary — `t.isEmpty()` has none, and manufacturing one is inventing data (M-9) |
| `decision-table` | each rule of the table | refused whole where a guard contains OR: half a table is worse than none (M-17) |
| `pairwise` | each pair of factor values | degenerates to equivalence partitioning where only one input varies, and says so |

## The three things a Métis coverage figure is bounded by

State these whenever a percentage is quoted.

1. **What extraction reached.** The measure is computed over the recovered model.
   `coverage_report`'s `unmeasured` is the part it could not reach at all — a
   figure printed without it overstates the denominator's completeness.
2. **Approval.** Generation reads only `Approved` (D-10). A model at
   `Quarantine` has coverage that describes nothing anyone may generate from.
3. **Testedness, not correctness.** C-11: a transition may be fully covered and
   currently failing. Métis reports both halves and never merges them — that is
   why the execution labels were staged out in the first place (§8.7).

## What this reference does not do

It does not reproduce the standard, and it does not claim conformance. 29119-4
defines many more techniques than Métis computes; the seven above are the ones
with a deterministic implementation and a test. A technique absent here is absent
because nothing computes it, which is a statement about Métis, not about the
standard.
