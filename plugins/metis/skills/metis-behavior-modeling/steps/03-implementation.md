# Step 3 — Implementation (I)

**Scope Lock (carried from Steps 1-2):** the same one state machine.

## Actions

1. Report the final result to the user plainly:
   - **Well-formed**: no determinism/completeness/reachability findings.
     State clearly that this means the *structure* is sound — it does not
     mean the guard conditions are semantically correct, and it does not
     include `REQ-METIS-BM-01`'s code-graph corroboration (not built, see
     `SKILL.md`'s scope note).
   - **Needs resolution**: list every specific finding from Step 2 (each
     conflicting Transition pair with its `dispute_reason`, each
     completeness gap, each unreachable state) — never a generic "this
     state machine has problems."
2. Any conflicting Transitions found in Step 2 are already marked
   `lifecycle_state='Disputed'` in the graph by `check_determinism` itself
   — confirm this to the user (it's a real side effect of Step 2, not
   something this step does separately) and tell them a human needs to
   resolve which branch is correct; this skill does not pick for them.
3. This build has no write path for "the human resolved it, apply the
   fix" — per this project's `REQ-METIS-CPT-01` discipline, changing a
   Disputed Transition's guard/target still requires a real, explicit
   write path decision, not a side effect of running this skill.

## Stage Confirmation
```
[C]omplete — behavior-modeling review done
[R]eview this stage in detail
[B]ack to Plan
[X]it
```
Terminal step — no further auto-advance.
