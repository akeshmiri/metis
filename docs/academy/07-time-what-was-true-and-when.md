# 7 · Time: what was true, and when

Métis carries two independent axes, and confusing them loses both answers.

| Axis | Question it answers | Values |
|---|---|---|
| `lifecycle_state` | has a human looked at this | `Quarantine` · `Approved` · `Disputed` · `Rejected` · `Deprecated` |
| **validity** | was this ever true, and is it still | `valid_from`, `valid_to` |

**A criterion can be `Approved` and no longer valid.** That is not a
contradiction — somebody agreed it was right, and later the world moved. A system
whose purpose is comparing what the code does **now** against what was said
**then** cannot express *"true until release 4.2"* with a review state alone
(**D-15**).

## Empty means still true

`valid_to` is required and **may be empty**. `""` is the honest representation of
"still true"; absent would be indistinguishable from "nobody recorded it" — the
same conflation `guard_expression` refuses for unguarded transitions.

## Invalidation sets a date. Nothing is deleted

    invalidate(session, ["AC-1"], valid_to="2026-06-01T00:00:00+00:00")

The node stays. Its edges stay. Its `lifecycle_state` is untouched, because
retracting a reviewer's approval would misrepresent what they decided —
invalidation records that the world changed, not that the reviewer was wrong.

*What did we believe in March* stays answerable. That is the entire difference
between a validity window and a `DELETE`.

## Two traps, and how they are closed

**A re-run must not resurrect a superseded fact.** Validity is written by
`ON CREATE SET`, so a routine re-extraction cannot reset `valid_to` to empty. An
invalidation that an unrelated re-run can undo is not an invalidation.

**A read that ignores validity answers the wrong question.** It reports what was
*ever* believed while looking like it reports what is believed *now*, and that
failure is indistinguishable from success. Every read over a validity-carrying
label filters on it, and a test asserts that with an exemption list that is
currently empty.

## Reading the past

    default read    → currently valid
    as-at read      → valid_from <= T < valid_to

The interval is **half-open** on purpose: a fact invalidated at `T` was true up
to `T` and not at `T`. Closing both ends would make it briefly true and
superseded at once.

## Nodes from before this existed

Every node landed before validity carried no `valid_to` at all. A filter
accepting only `""` would have hidden all of them on the day it shipped, so
missing is treated as "nobody recorded an end" — the same claim as empty. An
existing graph keeps answering.
