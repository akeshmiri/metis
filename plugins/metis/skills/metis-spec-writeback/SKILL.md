---
name: metis-spec-writeback
description: Regenerate the stakeholder specification from an approved model and write it back into the team's own repository, behind a gate and without ever overwriting a hand-edited file. Use when someone asks to update or write back a spec, or to put the generated specification where the team reads it.
workflow: spec-writeback
allowed-tools:
  - list_workflows
  - route_request
  - run_status
  - ask
  - get_model
  - validate_model
  - get_spec
  - get_requirement
  - trace
knowledge-from:
  - specgen.writeback
---

# Métis spec-writeback

Two stages, and the second is a human:

```
spec → write-back gate (halt) → written
```

**A specification that only lives in Métis is one the team does not read.** So
the generated document goes where the specs they already open live —
`<repo>/.specify/specs/<feature>/spec.md` — which makes this the second thing in
the system that writes outside its own graph, and it is gated accordingly.

## The two rules that shape everything here

**T-15: a hand-edited file is never overwritten by regeneration.** Somebody's
edits are a decision. A regeneration that silently replaces them destroys the
record of that decision and teaches the team not to edit the file, which defeats
the point of putting it there.

**SP-5: a specification with unapproved rules is withheld by default.** Writing
an unreviewed extraction into the team's spec directory gives a machine guess the
standing of a decision. The override exists, is explicit, and should be named in
the report when it is used.

## Commands

```
metis spec --journey <j> --surface api
metis spec --journey <j> --write-back <repo> --confirm publish \
     --batch-size <n> --as <you>
metis workflow run spec-writeback --scope <scope>
metis workflow status spec-writeback--<scope>
```

Exit codes: `0` complete · `5` **blocked on a human decision, not a failure** ·
anything else failed.

## Steps

`steps/01-build.md`, `steps/02-gate.md`. Read
`../shared/knowledge/anti-hallucination-protocol.md` once; its gates apply here.


The reasoning behind the engine this skill drives is in
`knowledge/index.md` — generated from the module docstrings that are its
source of truth, so it cannot drift from the code it explains. Read a
fragment when you need the why, not before.
## Check before you write

T-15 is the same discipline `../shared/knowledge/duplicate-guard.md` describes,
applied to a file: establish what is already there before writing over it, and
treat a check that could not run as `unknown` rather than as permission. A
directory that cannot be read is not an empty directory.

## Two keys, and say which one is missing

Writing into a product repository needs the literal word `publish` **in this
run** (T-18), *and* `METIS_ALLOW_EXTERNAL_WRITES=yes` on the installation. The
second exists because the first can be supplied by whatever is driving the run,
including an agent — so a word in a run is not on its own evidence a person
agreed to a write outside Métis.

When a run is refused, say which of the two was missing. "Refused" alone sends
somebody to re-type a word that was never the problem.

## What this skill must not do

1. **Never overwrite a file the team has edited** (T-15). If the plan withholds
   a document for that reason, report the withholding — it is the system working,
   not a failure.
2. **Never write an unapproved specification without `--allow-unapproved`, and
   never pass it silently** (SP-5).
3. **Never report a write that did not happen.** A plan that withheld everything
   is not a successful write. This stage returned `PASSED, "written back"`
   without calling the writer at all until 2026-09-01; that is the failure mode
   to stay ahead of.
4. **Never synthesise specification prose by judgement** (SP-1). The document is
   generated from the model. If the model does not say it, it does not go in.

## Verification

```
uv run python -m pytest -q test_writeback.py test_workflow.py -k writeback
```
