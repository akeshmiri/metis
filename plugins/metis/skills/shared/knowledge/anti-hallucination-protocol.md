# Métis anti-hallucination protocol — RPI + Stage Confirmation

**Ported from Atlas** (`.agents/skills/shared/knowledge/anti-hallucination-protocol.md`),
and grounded in `docs/metis-application-spec.md` §9.2, which adopts RPI and the
Stage Confirmation Protocol by name.

This file used to open with a note calling itself a best-effort reconstruction
of something that "does not exist elsewhere". That was wrong on both counts: the
source is intact, and this file had drifted from it — three concrete gates were
missing, and they are the measurable ones. They are restored below and marked.
The note also said "every skill under `.agents/skills/` references this file",
which describes the source project's tree, not this one. Each Métis skill cites
this file once, from its `## Steps` section.

## RPI: Research / Plan / Implementation

Four gates, applied to every skill stage that makes a claim about graph
content or proposes a decision:

1. **Scope Lock** (start of Research). Write down explicitly what this
   stage is bounded to — for a review-assist pass, that's the single
   `node_id`/anchor under review, not the whole quarantine queue. Drifting
   onto unrelated entities mid-review is scope creep, not a bonus.

   **The default out-of-scope set:** generic authentication, rate-limiting,
   concurrency and audit-logging. Do not add them unless the source
   explicitly requires them. They are plausible for almost any system,
   which is exactly what makes them the cheapest thing to hallucinate.
2. **Forbidden Substitutions** (throughout Research and Plan). Never fill a
   gap with a guessed value, a carried-over assumption from a previous
   session, or a silently reconciled conflict. If two sources disagree,
   that disagreement is the finding — not something to resolve by picking
   one side.
3. **Confidence Tagging** (end of Plan, throughout Implementation). Every
   fact used in a recommendation is tagged `VERIFIED` (grounded in a real
   tool response, `source_episode_id` traceable), `INFERRED` (a reasonable
   read of real data, but not itself directly stated), or `UNVERIFIED`
   (couldn't be checked against real data in this session). **Never mark
   something `VERIFIED` without a concrete source reference** — a tool
   response, a `source_episode_id`, or a file and line. A confidence tag
   with nothing behind it is worse than no tag, because it reads as
   evidence. Never proceed past a required output that depends on an
   `UNVERIFIED` item without surfacing that dependency explicitly to the
   human.
4. **Drift Check** (end of Implementation, before the Stage Confirmation
   gate below). Re-derive the scope lock from step 1, and **count**: how
   many produced items — criteria, scenarios, findings, fields — directly
   serve the locked scope, against how many serve generic or out-of-scope
   concerns.

   **Below half, it is drift.** Discard and re-derive rather than passing
   drifted output downstream, and log what was removed and why. The
   threshold is the point: "doesn't actually serve the locked scope" is a
   judgement nobody can fail, and a gate nobody can fail is not a gate.

## Stage Confirmation Protocol

Never auto-advance past a stage that produces a recommendation a human
will act on. After each stage, present:

```
[C]ontinue to next stage
[R]eview this stage in detail
[B]ack to previous stage
[X]it workflow
```

**Standalone mode** (a single quarantine-item review, e.g.
`metis-review-assist`): always pauses and shows the menu — a single-shot
review is exactly the low-volume case where a per-stage confirmation is
cheap and appropriate, not confirmation fatigue.

**Chain mode** (a multi-stage batch, e.g. reviewing an entire quarantine
queue back-to-back): auto-advances between items unless a validation check
fails on one of them, in which case it stops on THAT item and shows the
full menu — this is what prevents a bad batch from silently running to
completion while still not demanding a confirmation click per item when
everything is going fine.

Any skill invocation that would trigger a materially larger scope than
typical (e.g. "review the whole queue" instead of "review this one item")
shows the proposed plan and item count up front and requires explicit
confirmation before starting.
