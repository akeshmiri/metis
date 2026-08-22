---
name: metis-knowledge-capture
description: Turn a stated requirement in ordinary language into atomic acceptance criteria, write them to a reviewable knowledge file, and report what the model already has, what contradicts it, and what is new. Use when someone tells Métis a rule the system should follow and wants it formalised and reconciled. It never writes the graph — landing goes through the gated CLI.
---

# Métis knowledge-capture

Somebody says *"if a user has admin permission then they should be able to
archive, restore and export a record."* That is a real requirement and it is not
in a shape anything can use. This skill turns it into acceptance criteria, then
answers three questions against the live model:

```
prose  ──►  knowledge file  ──►  ac-mine  ──►  compare  ──►  land  ──►  G1 (halt)
 (you)      (this skill)                          │
                                    already there · contradicting · new
```

| Answer | What it means | Where it comes from |
|---|---|---|
| **already there** | An element with this natural key exists and its guard agrees | I-5 step 2 — `UNCHANGED` |
| **contradicting** | Same key, different guard: the statement and the model disagree about one behaviour | I-8 — `MODIFIED`, lands `Disputed` |
| **new** | No match | I-5 step 4 — `ADDED`, at `Quarantine` |

Neither side automatically wins (S-10). A precedence rule would silently decide
which of a defect and a stale requirement is correct, and that is the judgement
the gate exists for.

## Why the formalisation happens here and the checking happens in code

`metis_mcp/model_sources/ac_mining.py` parses Given/When/Then and EARS and
**blocks free prose** rather than guessing at it (S-13, TR-4). That refusal is
right: a fluent, well-formed, invented requirement is what guessing produces, and
it is indistinguishable from a real one.

So judgement happens where judgement belongs — in this session, with a person
reading the result — and `metis_mcp/model_sources/knowledge.py` is the
deterministic gate on the output. It calls no model. It checks that every
criterion is atomic, parseable, and says what it was derived from, and reports
every defect at once rather than one per round.

The knowledge file is the artefact, not a temporary buffer: it is diffable,
version-controllable, and reviewable **before** anything touches the graph — the
same reasoning N-7 already applies to review decisions.

## One condition, one action, one validation

An acceptance criterion is atomic. Three conditions in one criterion is three
criteria wearing one id, and a reviewer can only accept or reject the bundle.

```
Given the user has admin permission, when they archive a record, then the record is archived.
Given the user has admin permission, when they restore a record, then the record is restored.
Given the user has admin permission, when they export a record, then the record is exported.
```

Three actions, three criteria. Not one criterion listing three actions, and not
one criterion for "an admin has full access" — that names a permission, not a
behaviour, and nothing can be tested from it.

A condition clause is written `, and ...`. That punctuation is load-bearing:
`when they archive a record and delete a record` is two actions and is rejected,
while `when they archive a record, and they have write access` is one action with
one condition and is accepted. Métis cannot tell those apart from the words
alone, so it reads the comma.

## The negative branch is a requirement, not the absence of one

*"An admin can archive"* says nothing about a non-admin. The complement — *"a
non-admin cannot archive"* — is a rule the system must enforce and needs its own
test, so draft it. But **nobody said it**, and the file records that:

```json
{
  "id": "AC-004",
  "text": "Given the user does not have admin permission, when they archive a record, then the request is rejected.",
  "polarity": "negative",
  "derived": "inferred_complement",
  "complement_of": "AC-001",
  "source_statement": "if a user has admin permission then they should be able to archive a record"
}
```

`derived: "inferred_complement"` is not decoration. It reaches the graph at
`Quarantine` as `code_derived`, and only a human edit or explicit affirmation
promotes it (S-19, `review.decisions.promotion_for`). Presenting an inference as
something a person stated is exactly the fabrication S-13 exists to prevent.

## Gherkin, and the nouns it uses

The knowledge file has a second form: **one Requirement is one Feature, one
AcceptanceCriterion is one Scenario.** It round-trips — a `.feature` is a source,
not only an output, so a BA can edit scenarios in the language their team already
uses and Métis reads them back.

```
@requirement:REQ-ADMIN-01 @area:records
Feature: When a user has admin permission, the system shall permit the requested action

  @ac:AC-004 @negative @inferred @complement_of:AC-001 @code_derived
  Scenario: archive a record → the request is rejected
    Given the user does not have admin permission
    When they archive a record
    Then the request is rejected
```

Every traceability fact rides in a **tag**, because a tag survives the round trip
and a comment does not. `@inferred` and `@complement_of:` are load-bearing: drop
them and the criterion comes back ungrounded, and `knowledge check` correctly
refuses it.

**It is not executable.** R8 is that Métis emits test cases, not test code. A
`.feature` with no step definitions is a specification that happens to be
machine-readable — say so rather than letting anyone think a suite exists.

`Scenario Outline`, `Examples`, `Background` and `Rule` are **not read**. A file
using them is refused with the line number, because reading it anyway would drop
those rows and report a clean parse.

## The glossary — what the nouns mean

A criterion says *"when they archive a record"*. What is a record, and what does
archiving one change? The glossary answers both, at two levels: a
**BusinessArea** groups, a **BusinessEntity** carries its properties and — the
half no schema records — its **impact**.

```
Record — a stored business document owned by one user
    state (Draft | Active | Archived) — where it sits in its lifecycle
    impact: archiving is reversible for 30 days, then permanent
    impact: archiving cascades to every attachment
```

Entities are matched into criteria by **whole-word name**, never by similarity
(X-17). An entity the glossary does not define is simply not tagged, and that
omission is visible in the rendered Feature rather than approximated.

`AcceptanceCriterion-[:REFERENCES]->BusinessEntity` is what makes impact
answerable in both directions: *which criteria touch this noun*, and *which nouns
does this requirement depend on*. It never replaces D-4's traceability route — a
BusinessEntity is never on the path from a test case to a transition.

## Commands

All real, all in `metis-server`.

```
python3 -m metis_mcp.mbt.cli knowledge check <knowledge.json>
python3 -m metis_mcp.mbt.cli knowledge compare <knowledge.json>
python3 -m metis_mcp.mbt.cli glossary check <glossary.json>
python3 -m metis_mcp.mbt.cli feature render <knowledge.json> --glossary <glossary.json> -o spec.feature
python3 -m metis_mcp.mbt.cli feature read spec.feature --model-id <model> -o <knowledge.json>
python3 -m metis_mcp.mbt.cli workflow run knowledge-capture --scope <scope> \
    --knowledge <knowledge.json> --glossary <glossary.json> --journey <j> --surface api
python3 -m metis_mcp.mbt.cli workflow status knowledge-capture--<scope>
python3 -m metis_mcp.mbt.cli workflow resume knowledge-capture --scope <scope> \
    --knowledge <knowledge.json> --journey <j>
```

Exit codes: `0` complete · `5` **blocked on a human decision, not a failure** ·
anything else failed.

`knowledge check` is free — no graph, no model call. Run it before anything else;
it reports every defect in the file at once.

## Steps

`steps/01-research.md`, `steps/02-formalize.md`, `steps/03-run.md`, in that
order. Read `../shared/knowledge/anti-hallucination-protocol.md` once; its gates
apply here.

## What this skill must not do

1. **Never write the graph.** It writes a JSON file and prints the command that
   lands it. N-8 makes the agent surface read-only, and landing is a proposal
   that still has to pass G1 — a skill that wrote directly would put a candidate
   in the graph that no run recorded and no reviewer was shown.
2. **Never present an inferred criterion as stated.** If the complement is worth
   drafting it is worth labelling. An unlabelled inference is a requirement with
   a forged author.
3. **Never widen the statement.** *"Admins can archive"* does not license a
   criterion about deleting, about audit logs, or about what a moderator can do.
   Anything the person did not say is asked, not assumed — and a criterion whose
   words are not in `source_statement` is the thing S-13 blocks.
4. **Never merge the three answers into one number.** "87% reconciled" destroys
   the only distinction that matters: *already specified*, *contradicts the
   model*, and *new* have different causes and go to different people (F-5).
5. **Never resolve a contradiction.** Report both sides with their guards and let
   a human decide at G1 (S-10). Choosing silently is choosing between a defect
   and a stale requirement without knowing which is which.

## Verification

```bash
cd metis-server
python3 -m pytest test_knowledge.py test_gherkin.py test_workflow.py -q   # no Neo4j, no model calls
```

The load-bearing test is `test_an_unchanged_file_reports_nothing_new`: it mines
the same file twice and asserts the second run adds nothing. A compare that
reports `ADDED` for behaviour already in the model is the failure mode worth
catching, because it looks like success.
