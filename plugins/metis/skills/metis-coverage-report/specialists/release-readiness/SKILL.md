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
  - release_verdict
  - classify_failure
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

## The three words, and what each rests on

A recommendation is `Go`, `Go with Conditions`, or `No-Go` — closed, and shared
with the sibling project deliberately, because a reader who moves between the two
must not meet a synonym and read it as a different claim.

**`Go with Conditions` earns its place.** Without it a reviewer with real
reservations chooses between blocking a release and pretending they have none,
and the second is what usually happens.

### Call `release_verdict()`; do not apply the ladder by hand

**This section used to reproduce the ladder as two tables and a bullet list** —
which confidence rests on what, and which recommendation each permits — while
the module that owns it, `risk/verdict.py`, was reachable from nothing. So the
rule that `Go` needs an observed run was enforced by a model reading a table and
copying it correctly, three times over, in a file that also said the refusal was
"checked rather than remembered".

It is checked now. `release_verdict(recommendation, confidence)` returns whether
the evidence supports the words, and `release_verdict(recommendation,
execution_records=N, stale=…)` derives the confidence from the evidence that
actually exists rather than from your impression of it. Called with no
recommendation it serves the whole ladder, so there is nothing left to restate
here.

**Name the four confidence levels; do not reproduce what each permits.**
`confirmed` (execution evidence for the behaviour, recent), `inferred`
(execution evidence for some of it), `estimated` (coverage and validation only,
no run observed), `unknown` (the data does not exist). Those are the words —
shared with the sibling project deliberately, so a reader moving between the two
does not meet a synonym and read a different claim. **Which recommendation each
one permits is the tool's answer**, and it is the mapping that used to be copied
by hand.

**What the tool answers, and what it does not.** It judges the *pairing* — these
words against this evidence. A refusal says the words do not match the evidence;
it does not say the release is unsafe, which is a different question with a
different owner. **Métis recommends nothing.** Which of the three to give is your
call about what you are willing to ship.

**`Go` needs an observed run.** `release_verdict` refuses it on coverage alone
(`estimated` permits only `Go with Conditions` and `No-Go`), and `test_defects.py`
asserts the refusal. Saying *do not ship* on thin evidence is a cautious call you
are entitled to make; saying *ship* on it is a claim the evidence cannot support.

## When something is failing, say what it points at

A readiness report that says "12 failing" hands the reader a number and no next
action. `classify_failure(evidence, expected=…, actual=…, phase=…)` says whether
a failure points at **the system, the test, or the environment** — three
different people, and a report that does not separate them sends all twelve to
the wrong one.

**No priority comes back, and that is deliberate.** How urgent a defect is
depends on what it blocks and who is waiting; neither is in a stack trace.

**An `unclassified` verdict means no rule matched**, never that the failure is
benign. Report it as unclassified rather than folding it into the largest bucket.

**Métis did not observe the failure.** The evidence is whatever you pass in.
Filing a defect from it is `file_defect`, which is write-tier and gated twice —
this specialist classifies and does not file.

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
