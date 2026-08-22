# Step 3 — Decide (I)

Record what the human decided. Nothing here decides anything itself.

## Actions

1. **Edit `review.json`** with the user's decisions: `reviewer` set to their real
   identity, `decision` per item, `rationale` on every reject (it is required),
   and `criterion_text` edited only where the user actually changed the wording.

2. **Apply.**
   ```
   python3 -m metis_mcp.mbt.cli review apply --journey <j> --surface <s> review.json
   ```

   Three refusals are normal and must be reported honestly rather than worked
   around:

   - **stale fingerprint** — the model moved since the export. Re-export and
     review again; decisions made against different evidence must not be applied
     (N-14).
   - **self-approval** — the reviewer proposed this element (N-10).
   - **no reviewer identity** — every decision records who made it.

3. **Report what actually changed**, including the promotion count: how many
   criteria moved to `human_confirmed`, and how many remain `code_derived`.

4. **Resume the run.**
   ```
   python3 -m metis_mcp.mbt.cli workflow resume model-build --scope <scope> \
       --journey <j> --surface <s>
   ```

## Drift check

If fewer than half the items the user was asked about relate to the model they
named, that is drift — discard and re-derive rather than applying a decision set
that wandered.

## What to say at the end

State the run's real status. If the model is approved but **no** criterion is
intent-backed, say so plainly: this run yields **coverage, not correctness**
(S-3). That is a true and useful thing to tell someone, and smoothing over it is
how a coverage number gets mistaken for a correctness claim.
