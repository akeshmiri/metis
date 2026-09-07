---
name: metis-risk-manager-monitoring
description: Keep a register alive — indicators and triggers, a review cadence, reporting through the consolidated report, and closure with the reason recorded. Use when a request is about risk review, risk reporting, tracking or closing risks, or capturing lessons.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - risk_exposure
  - risk_register_check
  - risk_report
  - risk_candidates
  - coverage_report
---

# Métis risk-manager · monitoring

## Prerequisites, from the parent

The parent (`metis-risk-manager`) has already established, and this skill does
not re-derive:

- risks are ranked, banded and have responses with owners and triggers;
- the review cadence was agreed at planning time (`steps/01-plan.md`);
- authored and model-derived risks are reported apart, never averaged.

## What this does

The part that decides whether the whole process was worth doing. A register
written once and never revisited is a document; one that is reviewed, updated and
closed with reasons is a control.

A different cadence and a different audience from every other step — the others
run once per risk, this runs on a clock over the whole register — which is why it
is its own procedure.

Steps: `steps/01-review.md`, then `steps/02-close.md`.

## Report with `risk_report`, never by hand

`risk_report(register_json)` is the consolidated view. It recomputes bands from
probability × impact rather than trusting a stored `score`, which is the one
thing a hand-assembled summary reliably gets wrong — and it keeps authored and
model-derived counts apart in every band.

## What this skill must not do

- **Never report a merged total.** The summary carries `by_derivation` and
  `mixed`; both go into the report. Sixteen risks that are twelve judged and four
  untested behaviours is a different picture from sixteen judged risks, and a
  merged number removes the reader's ability to see it.
- **Never produce an overall risk score.** `risk_report` refuses to, and says why
  in its own output. Do not assemble one from the parts it gives you.
- **Never close a risk without a reason.** Occurred, no longer applicable,
  mitigated to acceptable, or accepted with a reserve — one of those, recorded. A
  row that silently disappears takes its lesson with it.
- **Never let closure be the goal.** A register that only shrinks is being
  groomed, not managed. New risks arrive throughout; a review producing none is a
  signal about the review.
- **Never report a coverage figure as a correctness figure** (C-11). A transition
  may be fully covered and currently failing. Coverage answers *is this tested*.
- **Never treat an empty `risk_candidates` result as good news.** Check
  `depth_consulted` — false means nobody looked.
