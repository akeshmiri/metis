# Step 4 — Calibration batch (CONST-036, 500-unit sample)

**Scope Lock:** the one project/repository being onboarded.

## Actions

1. `CONST-036` requires a calibration sample run through the full
   extraction pipeline (Cognify + Layer 6 LLM-as-judge) before a new
   project reaches `auto_write` tier for real. The spec's own number is
   500 units.
2. **Update: this is now real, not blocked.** `guardrails/calibration.py`
   makes real model calls (no `ANTHROPIC_API_KEY` needed — see
   `metis_mcp/llm_client.py`, which shells out to the authenticated
   `claude` CLI) and computes a genuine `auto_write`/`quarantine`/`rejected`
   distribution from real graph entities. Each real call costs real money
   (~$0.05-0.15 observed) and real wall-clock time — run
   `run_calibration_batch(session, sample_size=N)` deliberately, not in an
   unattended loop.
3. **Sample size is a real decision, not a technicality.** Running the
   full 500-unit sample the spec specifies costs real money at that scale
   (~$25-75 going by the per-call cost observed during development) —
   confirm with whoever's onboarding this real project that they actually
   want to spend that before running it at full scale. A smaller real
   sample (this skill's own development used 8) still produces a genuine,
   real distribution — just from less data — and is a reasonable default
   to start with, not a fallback to apologize for.
4. Confidence for each sampled entity is itself a real model judgment
   (`_assess_confidence` in `guardrails/calibration.py`) — not fabricated,
   and not always flattering: a real run during development correctly
   rated one entity `confidence=0.05`/`rejected` because the model noticed
   its own truncated input didn't actually contain the class definition
   being claimed. That's the guardrail working, not a malfunction.

## Stage Confirmation
Since this step now spends real money, it does NOT auto-advance in chain
mode even though it's no longer blocked — confirm the sample size (and
therefore the real cost) explicitly before running:
```
[C]ontinue to Step 5, having confirmed sample size and cost with the user
[R]eview the calibration results in detail
[B]ack to Step 3
[X]it
```
