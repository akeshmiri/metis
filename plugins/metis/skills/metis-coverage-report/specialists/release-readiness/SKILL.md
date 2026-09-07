---
name: metis-release-readiness
description: Assemble what is known about a scope's readiness — coverage, validation, reconciliation and what could not be measured — and hand a person the evidence to decide. Use when someone asks whether something is ready to ship, or wants a readiness or release report.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - get_model
  - validate_model
  - coverage
  - coverage_report
  - trace
  - impact
knowledge-from:
  - mbt.coverage
---

# Métis coverage-report · release-readiness

The parent — `metis-coverage-report` — owns the absence vocabulary and the rule
that a figure not measured and a figure that is zero are different facts. Those
are assumed here.

This specialist exists because "is it ready?" is the question people actually
ask, and answering it well means **refusing the form of answer they expect**.

## Prerequisites, from the parent

1. ✅ Coverage, not outcome (C-11) — execution results are ingested (§8.7, revised) but never write the coverage ledger (C-10), so a transition can be fully covered and currently failing. Report both; merge neither
2. ✅ Every figure is measured, unmeasured with a cause and kind, or unavailable
3. ✅ Confidence is capped by the weakest input used

## A verdict is possible now, and only from execution evidence

**This used to say "no verdict, ever", and the reason was that §6.8a named a
verdict-from-coverage as the trigger for reinstating the staged-out execution
labels.** Those labels are reinstated. The trigger was pulled deliberately, so
the rule it protected changes shape rather than disappearing:

| Evidence available | What to say |
|---|---|
| coverage only | **no verdict.** A coverage figure is not a claim about quality (C-11), and it never became one |
| coverage **and** `TestExecution` records | a verdict, with its confidence capped by the weakest input |
| execution records that are stale | the verdict, and how old the evidence is — an outcome observed last month is not a fact about today |

**The refusal that survives unchanged:** never compute Go / No-Go from coverage.
Covered-and-failing is a real state, and it is precisely the state a
coverage-derived verdict would call ready.

Confidence, capped by what was actually used:

- `confirmed` — execution evidence for the behaviour in question, recent
- `inferred` — execution evidence for some of it
- `estimated` — coverage and validation only, no runs observed
- `unknown` — the data does not exist, with the reason

What to give with any of them: what is covered, what is not, what could not be
measured and why. Then say what the verdict rests on, so a reader can disagree
with the input rather than only with the conclusion.

## Structural absence and operational failure are different facts

| Kind | Means | The harm of confusing them |
|---|---|---|
| `structural` | the data genuinely does not exist | reported as an outage, somebody restarts a service that was never involved |
| `operational` | something that should have answered did not | reported as unmeasurable, it reads as a permanent gap and hides a five-minute fix |

## Steps

`steps/01-assemble.md`, `steps/02-hand-over.md`.

The reasoning behind the engine this skill drives is in `knowledge/index.md`.

## What this skill must not do

1. **Never compute a verdict from coverage alone** (C-11). A verdict needs
   observed execution evidence; with coverage only, the honest answer is what is
   tested and what is not.
2. **Never present coverage as correctness.** A model whose criteria are all
   `code_derived` is documentation agreeing with itself (S-19, §4.1).
3. **Never omit a figure it could not compute.** Silence reads as zero (F-10).
4. **Never let publication drift read as "no drift"** when nothing was ever
   recorded as sent — that is "cannot tell".
