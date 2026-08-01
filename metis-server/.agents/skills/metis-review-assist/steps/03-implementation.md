# Step 3 — Implementation (I)

**Scope Lock (carried from Steps 1-2):** still the same single node id.

## Actions

1. Attempt to record the human's actual decision (Approve/Reject, from
   Step 2, as confirmed or overridden by the human) via
   `metis_submit_episode(episode_type="review_decision", payload={...}, source_ref=<the node id>)`.

2. **Show the real response, honestly.** As of this build,
   `metis_submit_episode` always returns:
   ```json
   {"accepted": false, "reason": "metis_submit_episode is disabled by default (REQ-METIS-CPT-01) until the guardrail stack has a production track record. This is a phase-gate, not a bug."}
   ```
   This is the correct, current behavior — not a failure of this skill.
   Tell the user plainly: **the decision was reasoned through but not
   persisted to the graph.** Do not phrase this as "your review has been
   recorded" or any variant that implies persistence happened. That would
   violate `AF-001`'s plain-language requirement and this project's own
   no-fabrication discipline just as much as inventing a graph fact would.

3. If the server's `graph.backend` is later switched to `neo4j` and
   `metis_submit_episode`'s gate is deliberately, explicitly enabled for a
   specific reviewed flow (a real decision someone makes, not a silent
   side effect of this skill running) — this step's response will change
   accordingly, and should be re-verified against the real tool output at
   that time, not assumed to still say "disabled."

## Drift check

Confirm the attempted write's `payload`/`source_ref` actually reference
the one locked node id from Steps 1-2, not a different item that came up
in conversation.

## Stage Confirmation

```
[C]omplete — review session done
[R]eview this stage in detail
[B]ack to Plan
[X]it
```

This is the terminal stage — there is no further auto-advance regardless
of mode.
