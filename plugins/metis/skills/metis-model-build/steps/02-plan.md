# Step 2 — Plan (P)

## Actions

1. **State what the run will do**, stage by stage, and what it will write. `land`
   writes to the graph; everything before it is in memory. Say so before running.

2. **Predict the halt.** A first run on an unreviewed model *will* stop at G1.
   That is the designed outcome — set the expectation now so exit code 5 does not
   read as a failure when it appears.

3. **Check for an existing run.** `workflow run` starts fresh; `workflow resume`
   continues. Starting fresh over a halted run discards nothing durable, but it
   does re-land — confirm which the user wants.

4. Tag each expectation `VERIFIED` / `INFERRED` / `UNVERIFIED`.

## Gate

Show the plan and wait. This stage writes to a database; that is worth a pause.
