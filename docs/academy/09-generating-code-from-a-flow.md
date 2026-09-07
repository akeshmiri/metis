---
topics: practice
---
# 9 · Generating code from a flow

Métis does not write test code, and this lesson is not a plan to make it. It is
about the seam: what Métis hands over, what a generator decides, and why the line
is where it is.

## Why the line exists

The `generators/` package used to emit REST Assured and Playwright sources. It
was deleted, and **R8** is the rule that replaced it: Métis says what must be
verified and whether it is covered; producing the implementation belongs to
whatever executes the test.

The argument is not squeamishness about code. It is that two questions live in
different places and change on different schedules:

- *What must be true of this system?* — changes when the system changes. Métis
  owns it, and can be wrong about it in ways a model check catches.
- *How is that expressed in this framework?* — changes when the framework
  changes, or when a team reorganises its fixtures. Métis cannot see either.

A module answering both is wrong about one of them every time either moves, and
the failure is quiet: the generated code still compiles.

## What is handed over

`flow_scaffold` emits a **flow manifest** — framework-neutral, and deliberately
naming no library, annotation or file layout.

| The manifest carries | A generator turns it into |
|---|---|
| operations, in order (`method`, `path`, `name`) | a task, a test method |
| `setup` — what must hold first | `on_start`, `@BeforeEach` |
| `precondition_group` + `shared_setup` | one hoisted fixture instead of N copies |
| `data_requirements` — conditions, and the steps they bite at | a builder, a faker |
| `payloads` — **the accepted space, never a value** | the ranges that builder draws from |
| `auth` — and what extraction could not see | a client, a fixture |
| `expected` | the assertion |

**The accepted space is the part people get wrong.** A field arrives as
`{"type": "string", "length": [3, 40], "required": true}` and never as `"abc"`.
One valid value is one case; the space is what a case is *chosen from*. A
manifest carrying an example teaches the generator to emit that example forever,
and the boundary cases — the ones worth having — are exactly what it stops
generating.

## A worked example: Locust

Take a performance suite of the shape Athena's `athena-locust` uses. Its units:

- a base user class carrying the client and the logging
- one class per operation, each with a `@task`
- an `on_start` establishing what the operation needs to exist first
- a weighted task list — `tasks = [(AddProject, 1), (GetUserById, 70)]`
- fakers producing the request bodies

The mapping is close to mechanical:

```
manifest.act                 -> the @task body: self.client.<method>(<path>)
manifest.setup               -> on_start, in order
manifest.precondition_group  -> which classes share that on_start
manifest.data_requirements   -> what the faker must satisfy
manifest.payloads            -> the ranges the faker draws from
manifest.auth                -> what the base user presents
```

**And one thing the manifest does not carry: the weights.** `GetUserById` at 70
against `AddProject` at 1 is a statement about how the system is *used*, and
Métis models what the system *does*. Nothing in a behaviour model knows that
reads outnumber writes seventy to one — that comes from traffic, from a product
decision, or from a person who knows the domain.

So a generator must ask for the weights, or default to uniform and say so. It
must not infer them from the model, and it must not quietly pick something
plausible: a load profile that looks measured and was guessed is worse than one
that is obviously flat, because only the second invites the question.

## The same seam for functional tests

A JUnit or pytest suite consumes the same manifest and makes different choices:
`setup` becomes `@BeforeEach` rather than `on_start`, one flow becomes one test
method rather than one weighted task, and the assertion comes from `expected`
rather than from a latency threshold.

Nothing in the manifest changes. That is the test of whether the seam is in the
right place — if a second target needed a different manifest, the manifest would
be carrying framework decisions it had no business holding.

## What this becomes

The translation rules above are knowledge about frameworks. They change when a
framework does, they benefit from worked examples, and they are the kind of thing
somebody should be able to review and disagree with — which is what the academy
is for, rather than a code path nobody reads.

`flow_scaffold`'s `target` parameter selects **which lesson a reader is pointed
at**, and changes nothing about what is emitted. That is deliberate: the moment
naming a target changes the output, the framework knowledge has moved back
inside Métis and R8 is gone in everything but name.

## What to remember

- **Métis states the flow; the framework is somebody else's decision.**
- **The accepted space, never a value** — one value is one case, and the space is
  what cases are drawn from.
- **What the model cannot know, the manifest does not claim** — usage weights are
  the clearest example, and asking is the correct behaviour.
- **A second target must not need a different manifest.** If it does, the seam is
  in the wrong place.
