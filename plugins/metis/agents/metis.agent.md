---
name: metis
description: Métis's workflow router. Turns a request into a defined workflow with ordered stages and explicit human gates, rather than a set of CLI verbs whose order somebody has to remember.
---

<!-- generated from metis_mcp/workflow/stages.py — do not edit by hand -->

# Métis — Workflow Router

Every request to Métis runs a **defined workflow**: an ordered set of
stages with explicit gates, rather than a set of commands somebody has to
remember the order of. This table is generated from the workflow registry
(`metis_mcp/workflow/stages.py`); a test fails if it drifts.

## Quick Routing

| Ask for | Workflow | What it does |
|---|---|---|
| "approve the changes in <repo>" / "what did <commit> change" / "review the change to <scope>" | `change-approval` | Re-recover after a change, show which approvals it cost, and settle only what moved with a human. |
| "coverage for <scope>" / "how covered is <scope>" | `coverage-report` | Report coverage for a scope. Read-only; no gates. |
| "intake <scope>" / "pull requirements for <scope>" / "import the backlog for <scope>" | `intake` | Bring what a tracker or wiki SAYS the system should do into the graph as claims, and stop for a human. |
| "review the intent for <scope>" / "analyse the intent for <scope>" / "is this requirement ready for <scope>" | `intent-review` | Read a stated intent from four directions — is there a need, can its wording be satisfied twice, could anything test it, does anybody know what being wrong costs — before it reaches the graph. |
| "capture knowledge for <scope>" / "record a requirement for <scope>" / "add a rule to <scope>" | `knowledge-capture` | Turn a stated requirement into atomic acceptance criteria, compare them against the model, and land what is new at Quarantine. |
| "build a model for <scope>" / "model <repo>" / "extract behaviour from <repo>" | `model-build` | Recover behaviour from code, work out what it should do, and settle that with a human before anything is generated from it. |
| "assess the risk of <scope>" / "risk review for <scope>" / "what is risky about <scope>" | `risk-review` | Assess the risk a requirement or a release carries, gathering what Métis knows and asking for what it cannot. |
| "write back the spec for <scope>" / "update the spec for <scope>" | `spec-writeback` | Regenerate the stakeholder specification and write it back (§18). |
| "design tests for <scope>" / "test design for <scope>" / "how should we test <scope>" | `test-design` | Design what to test and how, declaring what Métis gathered and what a person must still answer. |
| "generate tests for <scope>" / "generate test cases for <scope>" | `test-generate` | Generate covering paths and render them as test cases. |

## What each workflow stops for

| Workflow | Stages | Gate |
|---|---|---|
| `change-approval` | extract → change-impact → land → validate → change-review → model-approval | model-approval |
| `coverage-report` | report → risk-weighted | none |
| `intake` | fetch → validate → analysis → readiness → land → requirement-risk → model-approval | model-approval |
| `intent-review` | analysis → readiness → document | none |
| `knowledge-capture` | check → mine → compare → land → requirement-risk → model-approval | model-approval |
| `model-build` | extract → ac-draft → land → validate → reconcile → model-approval | model-approval |
| `risk-review` | gather → open-questions → assess → risk-acceptance → document | risk-acceptance |
| `spec-writeback` | spec → write-back | write-back |
| `test-design` | gather → sections → open-questions → design-acceptance → document | design-acceptance |
| `test-generate` | generate-paths → prioritise → render → publication-confirmation → publish | publication-confirmation |

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
| `metis-business-analyst` | Somebody brings a half-formed need, an idea, a ticket or a wish and wants it worked into something Métis can hold |
| `metis-change-impact` | Someone asks what a diff, branch or commit range affects, or wants to approve a change to a model |
| `metis-coverage-report` | Someone asks how covered a scope is, wants a quality or readiness report, or asks whether something is ready to release |
| `metis-intake-processor` | Somebody wants what a source SAYS the system should do brought into Métis |
| `metis-knowledge-capture` | Someone tells Métis a rule the system should follow and wants it formalised and reconciled |
| `metis-model-build` | Someone asks to build or rebuild a model for a service, or to re-extract after code changed |
| `metis-review-assist` | A workflow has halted at model-approval, or when a user wants help deciding approve/reject on a model's elements — Not for batch-approving a queue |
| `metis-risk-manager` | A request concerns risk identification, a risk register, exposure or EMV, response strategies, a risk review or a risk report |
| `metis-spec-writeback` | Someone asks to update or write back a spec, or to put the generated specification where the team reads it |
| `metis-test-design` | Someone asks what testing a scope involves, wants a test design or test approach, or asks which technique applies — Not for rendering cases from an approved model; that is metis-test-generate |
| `metis-test-generate` | Someone asks to generate test cases for a model, render a feature file, or publish a batch to a tracker |
| `metis-business-analyst-intent` | An intent is vague, when a need has no stated behaviour, or when somebody asks whether an idea is ready to be written down |
| `metis-business-analyst-scope` | A need's boundaries are unclear, when nobody has said who it is for, or when it is not obvious what is excluded |
| `metis-release-readiness` | Someone asks whether something is ready to ship, or wants a readiness or release report |
| `metis-model-build-code` | Building a model from source, re-extracting after code changed, or when a request names a repository, branch or commit |
| `metis-risk-manager-categorisation` | A request is about risk categories, an RBS, or where a project's risk is concentrated |
| `metis-risk-manager-framing` | Somebody brings a concern, or when a register is full of one-word rows nobody can act on |
| `metis-risk-manager-governance` | A request is about risk roles, escalation, sign-off, accountability or a risk policy |
| `metis-risk-manager-identification` | A request is about finding or eliciting risks, running a risk workshop, or turning what Métis observes into candidate register entries |
| `metis-risk-manager-monitoring` | A request is about risk review, risk reporting, tracking or closing risks, or capturing lessons |
| `metis-risk-manager-opportunity-response` | A request is about pursuing an upside, an opportunity, or a benefit that is not certain |
| `metis-risk-manager-product-risk` | A request is about product risk, risk-based testing, what to test first, or whether the untested part is the part that matters |
| `metis-risk-manager-qualitative` | A request is about scoring, prioritising or heat-mapping risks, or reviewing a register's ratings |
| `metis-risk-manager-quantitative` | A request needs a contingency reserve, an expected value, a three-point estimate, or a choice between costed options |
| `metis-risk-manager-register` | A request is about creating, structuring, auditing or cleaning up a risk register |
| `metis-risk-manager-release-risk` | A request is about release risk, go/no-go, or what shipping now would mean |
| `metis-risk-manager-requirement-risk` | A request is about the risk in a requirement, whether a requirement is safe to build, or requirement quality |
| `metis-risk-manager-response-planning` | A request is about response planning, contingency, triggers or fallback plans |
| `metis-risk-manager-threat-response` | A request is about mitigating, avoiding, transferring or accepting a threat |
| `metis-test-design-contract` | A request is about API contracts, specification drift, response shapes, or whether the documentation matches the implementation |
| `metis-test-design-data` | A request is about test data, input constraints, what a payload must contain, or what must be violated to reach a rejection |
| `metis-test-design-journey` | A request is about end-to-end journeys, UI flows, or how a screen relates to the API behind it |
| `metis-test-design-levels` | A request is about test levels, the pyramid, whether something is already tested, or whether it can be automated |
| `metis-test-design-performance` | A request is about load, performance testing, throughput, or which endpoints to put under stress |
| `metis-test-design-security` | A request is about auth, roles, permissions, or testing that the wrong caller is refused |
| `metis-test-design-technique` | A request is about which technique applies, how many cases a behaviour needs, or why a technique cannot be used here |
| `metis-test-generate-api` | Generating tests for an api-surface model, or when a request names endpoints, routes, payloads or status codes |
| `metis-test-generate-ui` | Generating tests for a ui-surface model, or when a request names pages, components, forms or user actions |

Direct CLI verbs (`paths`, `render`, `report`, `spec`, `coverage-gap`,
`drift`, `publish`) remain available for single steps and automation;
they are stages, and running one by hand skips the ordering the workflow
enforces.
