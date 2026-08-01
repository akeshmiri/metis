# Step 6 — Enable full ingestion, then monitor

**Scope Lock:** the one project/repository being onboarded.

## Actions

1. Enable the real ingestion worker (Phase 9's `ingestion_worker.py`,
   deployed via `metis-chart`'s `ingestion-worker` component) for this
   project's connector(s).
2. For the first two weeks: check `metis_quality_score` (the real MCP
   tool) daily, plus `guardrails/corpus_runner.py`'s adversarial-corpus
   pass rate (Phase 9's `guardrail-corpus-runner` CronJob) — both real,
   both already running.
3. After two weeks with no concerning findings: fall back to the standard
   cadence (`CONST-035`) rather than continuing daily manual checks
   indefinitely.

## Stage Confirmation
`[C]omplete — onboarding done` / `[R]eview` / `[B]ack to Step 5` / `[X]it`

Terminal step — no further auto-advance.
