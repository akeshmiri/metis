# Step 2 — Plan (P)

**Scope Lock (carried from Step 1):** still the same single node id.

## Actions

1. Call `metis_check_coverage(target_id=<the node id>)`. Record `covered`
   and `covering_items` verbatim — this is the real, current coverage
   state, not an assumption carried over from Step 1's traceability data
   (traceability and coverage are computed differently; don't conflate
   them, per Forbidden Substitutions).

2. Form a recommendation: **Approve**, **Reject**, or **Needs more
   information**. The recommendation must cite which specific `VERIFIED`
   facts from Step 1 support it. If the strongest support you have is
   `INFERRED`, say so explicitly in the recommendation — don't present an
   inference with the same confidence as a verified fact.

3. If `covered: false` and this item's real kind suggests it's meant to be
   traceable (e.g. a `Requirement`, `TestCase`, or `AcceptanceCriterion`),
   the recommendation should default toward **Needs more information**,
   not Approve — an uncorroborated item passing review because nobody
   checked coverage is exactly the false-confidence failure mode DQ-017
   describes.

## Confidence tagging

Tag the recommendation itself: is it `VERIFIED` (every input fact was
VERIFIED), `INFERRED` (built partly on inference), or does it depend on an
`UNVERIFIED` gap the human needs to close first? Surface this plainly —
don't let an inference-based recommendation read as more certain than it is.

## Drift check

Confirm the recommendation is actually about the locked node id, not a
generalization about "items like this" or the whole quarantine queue.

## Stage Confirmation

```
[C]ontinue to Implementation
[R]eview this stage in detail
[B]ack to Research
[X]it
```
