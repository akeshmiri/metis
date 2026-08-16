# Step 2 — Plan (P)

**Scope Lock (carried from Step 1):** the same one state machine.

## Actions

1. For every source State in the set, call
   `check_determinism(session, state_id)`. Any finding means two real
   Transitions share a Trigger with guards that provably overlap (or
   couldn't be verified as exclusive) — per `CONST-049`, this is
   **surfaced, never silently resolved**. Do not pick which of the two
   conflicting Transitions is "probably right."
2. Call `check_completeness(session)` once for the whole set. Every
   `(state_id, trigger_id)` gap is a real, specific missing case — report
   each one by name, not just "the state machine is incomplete"
   (`AF-002`'s specific-reason requirement applies here too).
3. Call `check_reachability(session, initial_state_id)`. Every unreachable
   state is either a real design error or genuinely dead specification —
   ask the user which, don't assume.
4. Form the recommendation: **Well-formed** (no findings across all three
   checks) or **Needs resolution**, listing every specific finding from
   steps 1-3 the user must resolve before treating this state machine as
   reliable.

## Confidence tagging
All three checks' outputs are `VERIFIED` — real Cypher/graph-algorithm
results, not inference. The recommendation itself is `VERIFIED` if it's a
direct summary of those outputs; don't add speculative commentary about
"what the user probably intended" here.

## Drift check
Confirm every finding cited actually belongs to this locked state machine
(check the `source_episode_id`/set membership), not a stale finding from a
previous session's different state machine still sitting in the graph.

## Stage Confirmation
```
[C]ontinue to Implementation
[R]eview this stage in detail
[B]ack to Research
[X]it
```
