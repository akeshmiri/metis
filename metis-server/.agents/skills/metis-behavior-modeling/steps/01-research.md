# Step 1 — Research (R)

**Scope Lock:** the one State machine (one set of States sharing Transitions)
the user is proposing or asking to review — not every state machine in the
graph.

## Actions

1. Get the proposed set from the user: every `(from_state, to_state,
   trigger, guard_expression)` tuple, and which State is the initial one.
   Do not infer a missing transition or guess a plausible guard — an
   incomplete description from the user is exactly what Step 2's
   completeness check exists to catch formally; don't paper over it here
   by guessing what they probably meant (Forbidden Substitutions).
2. Land the set for real via `metis_mcp.behavior_model.load_transition`
   for each tuple (idempotent — MERGE-based, safe to re-run if the user
   corrects an entry).
3. If any guard expression isn't a simple `<var> <op> <num>` threshold
   (what `guards_conflict` can actually verify): tag it `UNVERIFIED` for
   overlap-checking purposes now — Step 2's determinism check will
   conservatively flag it as a potential conflict rather than silently
   assuming it's safe, per the same fail-closed discipline as
   `classification_gate.py`.

## Confidence tagging
Every landed tuple is `VERIFIED` (it's exactly what the user stated,
written verbatim into the graph) — this step doesn't infer anything about
the state machine's correctness, only records its stated shape.

## Stage Confirmation
```
[C]ontinue to Plan
[R]eview this stage in detail
[B]ack — re-enter the transition set
[X]it
```
