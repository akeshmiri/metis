---
name: metis
description: Métis's workflow router. Turns a request into a defined workflow with ordered stages and explicit human gates, rather than a set of CLI verbs whose order somebody has to remember.
---

<!-- generated from metis_mcp/workflow/stages.py — do not edit by hand -->

<!-- generated from metis_mcp/workflow/stages.py — do not edit by hand -->

# Métis — Workflow Router

Every request to Métis runs a **defined workflow**: an ordered set of
stages with explicit gates, rather than a set of commands somebody has to
remember the order of. This table is generated from the workflow registry
(`metis_mcp/workflow/stages.py`); a test fails if it drifts.

## Quick Routing

| Ask for | Workflow | What it does |
|---|---|---|
| "coverage for <scope>" / "how covered is <scope>" | `coverage-report` | Report coverage for a scope. Read-only; no gates. |
| "capture knowledge for <scope>" / "record a requirement for <scope>" / "add a rule to <scope>" | `knowledge-capture` | Turn a stated requirement into atomic acceptance criteria, compare them against the model, and land what is new at Quarantine. |
| "build a model for <scope>" / "model <repo>" / "extract behaviour from <repo>" | `model-build` | Recover behaviour from code, work out what it should do, and settle that with a human before anything is generated from it. |
| "write back the spec for <scope>" / "update the spec for <scope>" | `spec-writeback` | Regenerate the stakeholder specification and write it back (§18). |
| "generate tests for <scope>" / "generate test cases for <scope>" | `test-generate` | Generate covering paths and render them as test cases. |

## What each workflow stops for

| Workflow | Stages | Gate |
|---|---|---|
| `coverage-report` | report | none |
| `knowledge-capture` | check → mine → compare → land → model-approval | model-approval |
| `model-build` | extract → ac-draft → land → validate → reconcile → model-approval | model-approval |
| `spec-writeback` | spec → write-back | write-back |
| `test-generate` | generate-paths → render → publication-confirmation → publish | publication-confirmation |

## Running one

```
metis workflow list
metis workflow run <code> --scope <scope> [...]
metis workflow status <code>--<scope>
metis workflow resume <code> --scope <scope> [...]
```

Exit `0` complete · **`5` blocked on a human decision, not a failure** ·
anything else failed.

## Preconditions are checked, not remembered

- `spec-writeback` requires: `model_is_approved`
- `test-generate` requires: `model_is_approved`

These are registered predicates evaluated before the first stage runs —
so "this workflow needs that one to have happened first" is enforced,
not documented.

## No match

If a request matches nothing above, or matches two workflows equally,
**ask which one the user wants**. Do not guess: a run started in the
wrong workflow produces a confident artefact about the wrong thing.

## Skills

| Skill | Use when |
|---|---|
| `metis-behavior-modeling` | A user is defining or reviewing states and transitions and wants them checked for well-formedness |
| `metis-intake-processor` | Somebody wants what a source SAYS the system should do brought into Métis |
| `metis-knowledge-capture` | Someone tells Métis a rule the system should follow and wants it formalised and reconciled |
| `metis-model-build` | Someone asks to build or rebuild a model for a service, or to re-extract after code changed |
| `metis-review-assist` | A workflow has halted at model-approval, or when a user wants help deciding approve/reject on a model's elements |

Direct CLI verbs (`paths`, `render`, `report`, `spec`, `coverage-gap`,
`drift`, `publish`) remain available for single steps and automation;
they are stages, and running one by hand skips the ordering the workflow
enforces.
