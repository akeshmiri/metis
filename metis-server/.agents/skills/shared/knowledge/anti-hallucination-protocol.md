# Métis anti-hallucination protocol — RPI + Stage Confirmation

**Reconstruction notice:** this file does not exist elsewhere in the current
copy of this project — `metis-server/.agents/` was entirely absent when this
session picked up the work (a gap of the same kind CLAUDE.md already
documents for `pyproject.toml`: something that didn't survive the move to
this machine, not a stalled task). This is a best-effort reconstruction,
grounded directly in `docs/metis-specification.md` §9.2's real text (RPI
adopted from Atlas by name, Stage Confirmation Protocol adopted the same
way), not invented from scratch. Every skill under `.agents/skills/`
references this file once, per Atlas's own convention: "do not duplicate
this prose into individual step files; link to it instead."

## RPI: Research / Plan / Implementation

Four gates, applied to every skill stage that makes a claim about graph
content or proposes a decision:

1. **Scope Lock** (start of Research). Write down explicitly what this
   stage is bounded to — for a review-assist pass, that's the single
   `node_id`/anchor under review, not the whole quarantine queue. Drifting
   onto unrelated entities mid-review is scope creep, not a bonus.
2. **Forbidden Substitutions** (throughout Research and Plan). Never fill a
   gap with a guessed value, a carried-over assumption from a previous
   session, or a silently reconciled conflict. If two sources disagree,
   that disagreement is the finding — not something to resolve by picking
   one side.
3. **Confidence Tagging** (end of Plan, throughout Implementation). Every
   fact used in a recommendation is tagged `VERIFIED` (grounded in a real
   tool response, `source_episode_id` traceable), `INFERRED` (a reasonable
   read of real data, but not itself directly stated), or `UNVERIFIED`
   (couldn't be checked against real data in this session). Never proceed
   past a required output that depends on an `UNVERIFIED` item without
   surfacing that dependency explicitly to the human.
4. **Drift Check** (end of Implementation, before the Stage Confirmation
   gate below). Re-derive the scope lock from step 1. If the
   recommendation being presented doesn't actually serve that locked
   scope, discard it and redo the stage rather than presenting drifted
   output.

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
