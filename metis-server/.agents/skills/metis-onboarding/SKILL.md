---
name: metis-onboarding
description: Walk through metis-gap-remediation.md §6's real 6-step onboarding runbook for adding a new project/repository to Métis — checks real config (classification_gate.py, .metis/config.yaml), halts honestly on steps this build doesn't yet implement (calibration batch, Tree-sitter coverage), rather than faking a pass. Use when a user wants to onboard a new repository/project into Métis's ingestion pipeline.
---

# Métis onboarding

Implements `docs/metis-gap-remediation.md` §6's real runbook as an actual
skill, per `PLAN.md` Phase 10's instruction, instead of leaving it as prose
nobody follows step-by-step. Follows
`../shared/knowledge/anti-hallucination-protocol.md`'s RPI gates and Stage
Confirmation Protocol — read that file once, not repeated here.

**Chain mode** (this is a 6-step sequential runbook, not a single-item
review): auto-advances between steps unless a step's check fails, in which
case it stops on that step and shows the full Stage Confirmation menu —
per the shared protocol's chain-mode definition.

## The 6 real steps (steps/01-06, one file each)

1. Confirm `project_test_id_conventions` entry (`REQ-METIS-CONN-06`) — halt
   if unconfirmed, never guess a pattern.
2. Classify the repository's data-sensitivity tier (`CONST-051`/`052`).
3. Confirm Tree-sitter grammar coverage (`CONST-063`) — **this build uses
   Python's `ast` module, not Tree-sitter** (see
   `cognify/structural_extraction.py`'s docstring); halt honestly here for
   any project with a non-Python majority language, don't claim coverage
   that doesn't exist.
4. Run the calibration batch (`CONST-036`, 500-unit sample) — **not built
   in this environment** (needs a real Layer 6 LLM-as-judge, no
   `ANTHROPIC_API_KEY` available); halt here and say so, don't fabricate a
   calibration result.
5. Human review of calibration results via the real review UI (Phase 5's
   `review_api_server.py` + `docs/metis-review-queue-ui.html`).
6. Enable full ingestion (Phase 9's `ingestion_worker.py`); monitor
   `metis_quality_score` daily for two weeks, then fall back to standard
   cadence (`CONST-035`).

Steps 4 is a genuine, disclosed stopping point in this build, not a gap this
skill papers over — see that step's own file for what a human running this
skill should do about it (proceed manually with human-only review, or wait
until Layer 6 exists).
