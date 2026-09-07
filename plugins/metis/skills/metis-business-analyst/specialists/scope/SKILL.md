---
name: metis-business-analyst-scope
description: Establish what a stated intent is about and what it is not — the business area, the entities, the actors, the dependencies and what is deliberately out of scope — so that a gap is not read as an oversight. Use when a need's boundaries are unclear, when nobody has said who it is for, or when it is not obvious what is excluded.
allowed-tools:
  - analysis_report
  - analysis_aspects
  - search_knowledge
  - list_entities
  - get_entity
  - get_requirement
  - get_spec
  - design_inputs
  - ask
  - run_status
  - list_workflows
---

# Métis business-analyst · scope

## Prerequisites, from the parent

The parent (`metis-business-analyst`) has already established, and this skill
does not re-derive:

- intent is a pre-processor: nothing here lands anything;
- `ready` means representable, never agreed and never good;
- only a claim that cannot be represented is refused — an unfinished one is
  reported and imported;
- a document's claimed acceptance criteria are counted and never trusted (S-13).

## What this does

Produces the context the other readings are performed against: what this is
about, who it is for, what it depends on, and — the one people skip — **what is
deliberately excluded.**

This reading produces context rather than gaps, which is why it is not one of
the four aspects. It changes what the other four mean.

## What is out of scope is the field that stops a false alarm

Without it, every gap the analysis finds reads as an oversight. With it, most of
them read as decisions somebody already made. `out_of_scope` is a declared
optional input in the design ledger for exactly this reason, and its
`absent_means` says so: *scope boundary unrecorded; every gap below reads as an
omission*.

## Entities are looked up, never inferred

A business noun in a sentence is a word. An **entity** is a defined thing with a
key, and `list_entities` says which exist. A term that appears in the statement
and is defined nowhere is its own finding (I-2) — and it is one of the cheapest
findings to close and one of the most expensive to leave.

## Steps

`steps/01-boundaries.md`.

## What this skill must not do

1. **Never infer an entity from a noun.** Look it up. An invented entity is a
   join that will never match anything.
2. **Never assume what is out of scope.** An unstated boundary is unstated; a
   guessed one silently narrows the requirement.
3. **Never treat the absence of an actor as "any user".** Nobody said that.
4. **Never widen the subject.** A related ticket is related, not in scope — the
   scope lock in `../../../shared/knowledge/anti-hallucination-protocol.md`.
