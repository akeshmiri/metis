---
name: metis-test-generate
description: Turn an approved behaviour model into covering paths, render them as human-executable test cases, and stop at the publication gate with the whole batch shown. Use when someone asks to generate test cases for a model, render a feature file, or publish a batch to a tracker.
workflow: test-generate
allowed-tools:
  - list_workflows
  - route_request
  - run_status
  - ask
  - get_model
  - validate_model
  - coverage
  - coverage_report
  - test_cases
  - flow_scaffold
  - test_design
  - trace
knowledge-from:
  - publishing.publish
  - publishing.zephyr
  - rendering.gherkin
  - scaffold
---

# Métis test-generate

The model is settled; this is what comes out of it. Four stages, and the third
is a human:

```
generate-paths → render → G2 publication-confirmation (halt) → publish
```

**Nothing here decides anything.** Generation reads only `Approved` (D-10), so
this skill's first job is to check that the model *is* approved and to say so
plainly when it is not — a rendered case from an unreviewed model is a preview,
never a batch.

## What is produced, and what is deliberately not

| Produced | Not produced |
|---|---|
| a test case: preconditions, one action, **one assertion** (T-1a) | executable code — the `generators/` package was deleted on purpose (R8) |
| a `.feature` file: Gherkin as specification | step definitions binding it to a system |
| the accepted space: `<string, length 3..40, required>` | a concrete value somebody could paste (X-6e) |

A case says what must be verified. Producing the implementation belongs to
whatever executes the test.

## Commands

```
metis paths --journey <j> --surface api --criterion all-transitions
metis render --journey <j> --surface api
metis drift --journey <j>
metis publish --journey <j> --confirm publish --batch-size <n> --as <you>
metis workflow run test-generate --scope <scope>
metis workflow status test-generate--<scope>
```

Exit codes: `0` complete · `5` **blocked on a human decision, not a failure** ·
anything else failed.

The MCP surface previews the same batch read-only: `test_cases` returns what
would be generated and states `model_is_approved`; `coverage_report` says what
the run could not measure. The decision stays on the CLI.

## Steps

`steps/01-check.md`, `steps/02-render.md`, `steps/03-gate.md`, in that order.
Read `../shared/knowledge/anti-hallucination-protocol.md` once; its gates apply
here. When a guard's complement has no case, that is a condition decision, not
an omission — `../shared/knowledge/requirement-condition-coverage.md` says which
class it belongs to.


The reasoning behind the engine this skill drives is in
`knowledge/index.md` — generated from the module docstrings that are its
source of truth, so it cannot drift from the code it explains. Read a
fragment when you need the why, not before.
## Before generating: can it be automated at all?

`test_design` classifies every transition `automate` / `manual-only` / `defer`
with a reason, and marks which calls are worth driving under load. It is not a
coverage figure — coverage asks whether behaviour is tested, this asks whether it
*can* be, and a design that skips it automates things it cannot assert.

**`automate` is never awarded on a name** (X-6), and performance candidacy
reports `no-basis` where the model carries no volume facts rather than inventing
an SLA. Carry both refusals into what you tell the user.

## Check before you create

**A confirmation to publish is not a decision to overwrite.** Before creating a
case in a tracker, establish whether one already exists —
`../shared/knowledge/duplicate-guard.md` has the four verdicts and the rule that
matters: a check that could not run is `unknown`, and `unknown` blocks. It is
never read as "nothing found".

This is not the coverage question. "Is this behaviour already covered?" is about
adequacy; this asks whether you are about to create a second copy of one case.

Two states look identical and are not: a ledger reporting no published case
because there is none, and a ledger that has never recorded a publication at all
and therefore cannot tell. The drift report says which one it is.

## Routing to a specialist

The surface decides, and the classification is mechanical — the model carries
`surface` as a first-class field, so this is a lookup rather than a judgement:

- **`surface: api`** → `metis-test-generate-api`. The guard is the endpoint's
  own; the accepted space comes from the contract.
- **`surface: ui`** → `metis-test-generate-ui`. A guard may be inherited from the
  API call it invokes (M-5c), and a selector is authored or it does not exist.

Both specialists enforce everything on this page, so **going direct is not
penalised** when the surface is already known. The parent owns the pipeline, the
G2 gate and the accepted-space rule; a specialist owns what differs.

## The G2 gate

**One decision covers the whole batch** (T-19), and the batch is shown in full
before it is asked for (T-17). Do not ask per case; that is how a reviewer stops
reading.

**"No" is the recommended default.** State it that way, every time. A client
that auto-accepts should land on cancellation, not on a publication — the
literal can be supplied by whatever is driving the run, including an agent.

**Publication is dry-run unless the installation says otherwise.**
`DryRunTransport` builds and validates the real payload and sends nothing. A
real write additionally needs `METIS_ALLOW_EXTERNAL_WRITES=yes`, which a human
set on the machine. Say which of the two is in force *before* the gate, not
after: a reviewer who thinks they are publishing and is not has been misled, and
so has one who thinks they are rehearsing and is not.

## The design-sync gate

`../shared/scripts/check_design_sync.py` is a deterministic structural diff
between a high-level design and its detailed form — no model call, just a check
that two independently written documents still agree. Run it before the gate:
Python computes, the model writes, Python verifies, and this is the third step.

## What this skill must not do

1. **Never generate from an unapproved model.** D-10 is not advisory.
   `path_generation` does not enforce it — the workflow's precondition does — so
   a skill that reached for the paths directly would walk straight past the
   gate.
2. **Never emit a concrete value where the model states a space** (X-6e). A base
   URL renders as `{base}` with its reason; a UI element with no authored
   selector raises rather than guessing.
3. **Never report a dry run as a publication.** `PublicationLedger.published`
   stays empty under dry-run, so `MANUALLY_EDITED` and `OBSOLETE` drift read
   zero — that is a property of the transport, not evidence of no drift.
4. **Never write more than one assertion into a case** (T-1a). A case that
   checks two things cannot say which one failed.

## Verification

```
uv run python -m pytest -q test_rendering.py test_publishing.py test_gherkin.py
```
