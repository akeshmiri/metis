# Step 3 — Run (I)

## Actions

1. **Run it**, then read the stage table rather than only the exit code. Each row
   carries what that stage concluded — `extract` names the counts and the
   extraction method, `reconcile` names both gap directions separately.

2. **On exit 5**, report the outstanding decision and the exact command the run
   printed for recording it. Do not offer to approve on the user's behalf.

3. **On a failure**, report what failed verbatim. There is no retry and no
   alternative path (F-9): a stage that fails stops the run, and the fix is
   whatever the finding says, not another attempt.

4. **On a fingerprint refusal during resume**, explain what it means: an earlier
   stage's conclusion describes a model that has since changed. Re-run from that
   stage; do not delete the run record to get past it.

## Drift check

If the run produced a model for a service other than the one the user named,
discard it. That is the multi-service scoping failure, and it looks like success.

## Report

State: the extraction method actually recorded, states/transitions landed, what
was skipped and why, both reconciliation gap counts, and where the run stopped.
If nothing is intent-backed, say the run yields coverage rather than correctness.
