---
name: metis-test-generate-api
description: Render covering paths for an API surface as test cases, where the guard is the endpoint's own and the accepted space comes from the contract. Use when generating tests for an api-surface model, or when a request names endpoints, routes, payloads or status codes.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - get_model
  - validate_model
  - coverage
  - test_cases
  - flow_scaffold
  - payload_shape
  - auth_facts
  - call_recipe
knowledge-from:
  - authoring
  - rendering.contract
---

# Métis test-generate · api

The parent — `metis-test-generate` — owns the pipeline, the G2 gate and the rule
that what is emitted states the accepted space and never a value. Those are
assumed here, not restated.

What is specific to this surface is where the facts come from.

## Prerequisites, from the parent

Already enforced before this skill runs:

1. ✅ The model is approved (D-10); an unapproved one yields a preview, never a batch
2. ✅ One case, one assertion (T-1a)
3. ✅ The accepted space, never a value (X-6e)
4. ✅ G2 is one decision for the whole batch, default No

## What the API surface supplies that the UI surface does not

| Fact | Where it comes from |
|---|---|
| the route | the transition's own trigger, `VERB /path` |
| the request shape | `payload_shape` — fields, types, bounds, required-ness |
| what a caller must present | `auth_facts`, **with its caveat** |
| the outcome | the declared status and body on the transition |
| a worked call | `call_recipe` — placeholders describing the space |

**The auth caveat is not optional garnish.** Declarative security is all
extraction can recover; a filter chain or a gateway enforces authentication
invisibly to it. On a real service zero endpoints declared any, and its auth
travelled as ordinary header parameters — so "nothing declared" and "open" are
different answers and the report must say which one this is.

## Steps

`steps/01-facts.md`, `steps/02-render.md`. The parent's gate step still runs and
is not duplicated here.

The reasoning behind the engine this skill drives is in `knowledge/index.md`.

## What this skill must not do

1. **Never infer a base URL.** It renders as `{base}` with its reason. A host
   guessed from a spec document is the host somebody's test suite will hit.
2. **Never turn a status code into a claim about correctness.** A declared 200 is
   what the code says it returns, not evidence it does.
3. **Never fill a field with a plausible value.** `<string, length 3..40,
   required>` is the answer; a single valid value is one case, and the space is
   what a case is chosen from.
