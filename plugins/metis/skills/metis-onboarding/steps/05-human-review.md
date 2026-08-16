# Step 5 — Human review of calibration results

**Scope Lock:** the one project/repository being onboarded.

## Actions

1. If Step 4 produced a real calibration result: review the real
   `auto_write`/`quarantine`/`rejected` distribution via Phase 5's real
   review queue (`review_api_server.py` + `docs/metis-review-queue-ui.html`,
   both real, tested, running against real Neo4j `lifecycle_state='Quarantine'`
   data).
2. If Step 4 was skipped (the honest halt, per that step): use the same
   review UI for every ingested item at `Quarantine` tier — the interim
   posture that step recommended.
3. Confirm the ratio looks reasonable for this project specifically —
   `DQ-002`'s platform-wide targets are a reference point, not a
   requirement that this exact project must match; a project with a
   genuinely different real ratio may need connector-specific tuning
   (Forbidden Substitutions: don't force-fit a real, different ratio to
   match the platform-wide expectation just because the target exists).

## Stage Confirmation
`[C]ontinue to Step 6` / `[R]eview` / `[B]ack to Step 4` / `[X]it`
