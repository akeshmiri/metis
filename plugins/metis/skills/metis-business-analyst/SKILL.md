---
name: metis-business-analyst
description: Analyse a stated intent before it reaches the graph — reading it from four directions, consolidating what is missing, and refusing the import only when the claim cannot be represented honestly. Use when somebody brings a half-formed need, an idea, a ticket or a wish and wants it worked into something Métis can hold. It is the pre-processor; landing goes through the gated CLI.
workflow: intent-review
allowed-tools:
  - list_workflows
  - route_request
  - run_status
  - ask
  - check_intent
  - analysis_aspects
  - analysis_report
  - validate_intake
  - check_ears
  - ac_quality
  - design_inputs
  - risk_inputs
  - search_knowledge
  - list_entities
  - get_entity
  - get_requirement
  - get_spec
knowledge-from:
  - analysis.gaps
  - analysis.readiness
---

# Métis business-analyst

**Intent is a pre-processor.** Nothing here lands anything; this is the work that
happens *before* a claim is a node, and before `intake` will let it become one.

Until this existed, `intake` ran fetch → validate → land → assess risk, so the
first moment anybody saw what was wrong with a claim was after it was in the
graph. `intake` now runs `analysis` and `readiness` **before** `land`, and this
skill is what performs them.

## Four readings, and two of them are somebody else's

A half-formed intent fails in four unrelated ways, and each is invisible to the
readers that catch the other three. `analysis_aspects()` returns the map:

| Reading | Asks | Owned by |
|---|---|---|
| **intent** | is there a need here, and did anybody say how it behaves? | `metis-business-analyst-intent` |
| **requirement** | can two people satisfy this the same way? | `metis-knowledge-capture` |
| **design** | could anything ever test it? | `metis-test-design` |
| **risk** | what does being wrong cost? | `metis-risk-manager-requirement-risk` |

**Consult the last three; do not reimplement them.** Each already runs the
procedure it owns, and a second copy here would drift from the one that runs.
Passing the analysis to the design and risk families for a deeper look is the
whole shape of this skill.

The **scope** reading — actors, entities, what is deliberately out of scope —
is `metis-business-analyst-scope`. It produces context rather than gaps, which
is why it is not one of the four.

### Keep this yourself

Consolidation. Routing between the four readings *is* the analysis, so a
specialist for it would be a skill that only calls its caller.

## Ready is not good, and saying so is most of the job

`analysis_report` returns `ready` or `not-ready`, and the word is narrow:

- **`not-ready`** — the claim cannot be *represented* honestly. A need with no
  specification would become a node nothing can ever be checked against (D-1).
  There is no literal that passes this: the claim itself has to change.
- **`ready`** — it can be landed at `Quarantine`, **carrying every reported gap
  with it**. Nobody has agreed with it. A person decides at G1 (S-4).

A requirement nobody has costed, whose environments are unlisted, is `ready`.
Refusing those would mean Métis only accepted claims that were already finished,
which is not what intake is for — but they are reported, every one, and that
list is what the person at G1 should be reading.

## Commands

```
metis intent review <file> -o review.md
metis intent check <file>
metis workflow run intent-review --scope <scope> --source <file>
metis workflow run intake --scope <scope>
```

`intent review` exits `1` on `not-ready` without needing `--strict`: landing
would create a dangling claim, and a pipeline should stop on that by default.

## Steps

`steps/01-read.md`, `steps/02-consult.md`, `steps/03-consolidate.md`, in that
order. Read `../shared/knowledge/anti-hallucination-protocol.md` once; its scope
lock applies here, and this is where it earns most — a half-formed intent invites
filling in.

Before proposing anything be created, `../shared/knowledge/duplicate-guard.md`
has the four verdicts, and `unknown` blocks.

The reasoning behind the gap taxonomy is in `knowledge/index.md` — generated
from the module docstrings that are its source of truth. Read a fragment when a
step cites it, not before.

## The document is edited, and that is the point

`metis intent review -o <file>` writes Markdown whose `Closed`, `Owner` and
`Notes` columns are yours, along with any gap you add. **A gap an analyst adds
is a gap none of the four readers can see**, which is the case this file is
editable for.

## What this skill must not do

1. **Never invent the need.** A vague intent is a question for the person who
   raised it, not a gap to fill in with the most plausible reading.
2. **Never trust a document's claimed acceptance criteria** into criteria
   (S-13). They are counted so their absence can be reported, and nothing more:
   a criterion asserted by the document that raised the requirement is not
   independent evidence of it.
3. **Never land anything.** This skill proposes; `metis intake land` and
   `metis intent land` write, and both stop at G1.
4. **Never report `ready` as agreed, or as good.** It means representable.
5. **Never refuse a claim for being unfinished.** Only `not-ready` refuses, and
   only because the claim could not be represented.
6. **Never decide a claim is untestable on a heuristic.** That verdict blocks an
   import, and it is a person's judgement — supplied, never inferred.
