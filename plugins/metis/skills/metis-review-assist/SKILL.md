---
name: metis-review-assist
description: Walk a reviewer through the G1 model-approval gate — the outstanding elements, the validation findings and reconciliation gaps that are the evidence for deciding, and the acceptance criteria each rule carries — ending in a recorded decision and a resumed run. Use when a workflow has halted at model-approval, or when a user wants help deciding approve/reject on a model's elements. Not for batch-approving a queue.
---

# Métis review-assist

G1 is one of exactly two human gates (`docs/metis-application-spec.md` §3.4), and
it is where a workflow **stops and waits**. Nothing auto-promotes on elapsed time
(F-8): an unreviewed model stays unapproved indefinitely, and the safe failure is
"no tests generated", never "tests generated from an unreviewed model".

This skill helps a person make that decision well. It does not make it for them.

## What this skill is for, and what it is not

| | |
|---|---|
| **For** | One model whose run has halted at `model-approval`, where a reviewer wants the evidence assembled and the decision recorded properly |
| **Not for** | Approving everything to get past the gate. A bulk approve buys `lifecycle_state: Approved` and nothing else — it cannot buy intent (S-19), and pretending otherwise is the failure this gate exists to prevent |

## The evidence a reviewer is owed (N-3)

A decision screen that cannot show its evidence **blocks the decision** rather
than presenting a partial view (N-4). For model approval that means all of:

- the outstanding elements, **named** — nobody can act on "10 problems";
- every validation finding, with its severity;
- reconciliation gaps in **both** directions, never merged into one number (F-5);
- per-element source, so N-10's separation of proposer from approver can apply;
- the acceptance criterion each rule carries, if it has one.

## Steps

Run in order — `steps/01-research.md`, `steps/02-plan.md`, `steps/03-decide.md`.
Each stage pauses before the next begins. Read
`../shared/knowledge/anti-hallucination-protocol.md` once; its four gates apply
throughout and are not repeated here.

## The commands this skill actually runs

All real, all in `metis-server`:

```
metis workflow status <run-id>
metis validate  --journey <j> --surface <s>
metis reconcile --journey <j> --surface <s>
metis review export --journey <j> --surface <s> -o review.json
metis review apply  --journey <j> --surface <s> review.json
metis workflow resume model-build --scope <scope> --journey <j> --surface <s>
```

## Two rules this skill must not soften

**A plain approve does not create intent.** `review/decisions.py:promotion_for`
promotes a criterion from `code_derived` only on a real **edit** or an explicit
`affirmed_as_intent`. A criterion drafted from the code and approved unchanged
documents the system; it does not validate it (§4.1, S-19). Never suggest setting
`affirmed_as_intent` in bulk — that single field is the only thing standing
between a rubber stamp and a manufactured correctness claim.

**The proposer may not approve their own proposal** (N-10). Landed elements carry
`proposed_by` from their Episode. If the reviewer is the proposer, `review apply`
refuses; say so plainly rather than suggesting `allow_self_approval`, which is
recorded as a self-approval when used.
