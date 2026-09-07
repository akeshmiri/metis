---
name: metis-business-analyst-intent
description: Establish whether there is a need here at all and whether anybody has said how it behaves, refusing a need with no specification rather than landing a claim nothing can ever be checked against. Use when an intent is vague, when a need has no stated behaviour, or when somebody asks whether an idea is ready to be written down.
allowed-tools:
  - check_intent
  - analysis_report
  - analysis_aspects
  - check_ears
  - search_knowledge
  - list_entities
  - get_entity
  - ask
  - run_status
  - list_workflows
---

# Métis business-analyst · intent

## Prerequisites, from the parent

The parent (`metis-business-analyst`) has already established, and this skill
does not re-derive:

- intent is a pre-processor: nothing here lands anything;
- `ready` means representable, never agreed and never good;
- only a claim that cannot be represented is refused — an unfinished one is
  reported and imported;
- a document's claimed acceptance criteria are counted and never trusted (S-13).

## What this does

The first of the four readings, and the only one that can block. Two things are
authored and one deliberately is not:

    Intent          a stated need, in ordinary language
    Specification   how that need behaves, stated so it can be checked
    Feature         NOT authored — Métis derives it from evidence

`check_intent` is the reader. It was reachable only from `metis intent check` on
the CLI, so no workflow and no agent could consult it before.

## An Intent with no Specification is refused, not landed

A need nobody has said the behaviour of is a wish. Landing it puts a node in the
graph that nothing can ever be checked against — the dangling reference D-1
exists to prevent — and it would sit at `Quarantine` for ever, because there is
nothing a reviewer could approve it against.

**This is the one place the analysis refuses**, and the refusal is not a
judgement about the idea. "Records should be tidy" may be an excellent goal. It
is not yet a claim.

## Provenance is required, and there is no default

A specification a person wrote is `independently_authored`; one decoded from an
endpoint is `code_derived`. Only the first counts as intent. Letting this default
would silently promote extraction output to intent, which is the one claim this
platform must never make.

## Steps

`steps/01-need.md`, then `steps/02-behaviour.md`.

## What this skill must not do

1. **Never write the specification for them.** Turning "records should be tidy"
   into a behaviour is inventing the requirement, and the invention would carry
   `independently_authored` provenance it has not earned.
2. **Never guess at provenance.** There is no default, deliberately.
3. **Never accept a need with no statement.** An intent with no words is a
   label, and nothing downstream can be checked against a label.
4. **Never decide a need is untestable on a heuristic.** That verdict blocks an
   import; it is a person's judgement and it is supplied, never inferred.
