---
topics: practice
---
# 6 · From a repository to test cases

The whole path, on the corpus in `demo_project/` — a Records service written to
be extracted, with a deviating OpenAPI document beside it.

## The five steps

    doctor  →  analyse  →  land  →  validate / reconcile  →  [G1]  →  test-generate

| Step | What happens | What can go wrong |
|---|---|---|
| `doctor` | preflight: engine, JDK, packs, graph | a missing dependency, named |
| `analyse` | builds a CPG, runs the query packs | the engine is absent or the wrong version |
| `land` | plans nodes and edges, writes at `Quarantine` | an illegal plan refuses **entirely** |
| `validate` / `reconcile` | determinism, reachability, AC↔transition gaps | unverifiable guards reported as a third outcome |
| **G1** | a human approves | — |
| `test-generate` | paths, rendering, coverage ledger | nothing, if nothing is `Approved` |

## What extraction actually recovers

From the demo service, measured rather than claimed:

| Fact | Count |
|---|---|
| Endpoints | 12 |
| Exception mappings | 5 |
| Methods declared | 64 |
| Dropped as noise | 10 (7 inert accessors, 3 boilerplate) |

The drop count is always reported. A filter that silently removed a third of a
service would be indistinguishable from a service that never had it.

## The comparison is the point

The code says one thing. The OpenAPI document says another. Neither is trusted
over the other, and the disagreement is the output:

| | Routes |
|---|---|
| Both sources describe | 9 |
| Contract only | `POST /record/{id}/restore` |
| Code only | `POST /record/{id}/archive` |

A model extracted from code and used to test that code proves the code does what
the code does (**§4.1**). *The code locks after 3 attempts; the criterion says 5*
is the finding no amount of self-testing produces.

## Why a whole service is re-extracted every time

A code property graph is **whole-program** — call graphs and type resolution are
global — so there is no meaningful per-file rebuild. What is incremental is
everything after: identity is content-derived, so re-landing unchanged content
writes nothing new, and an unchanged tree never re-invokes the engine at all.

For review, `impact` takes the files in a diff and answers which recovered
behaviour they touch. That turns *re-extract everything* into *re-review only
this*.

## What you get at the end

Human-executable test cases, and a coverage ledger keyed by transition. What you
do **not** get is a test that asserts a value nobody recovered: a payload renders
as `<string, length 3..40, required>`, a base URL renders as `{base}` with its
reason, and a UI element with no authored selector raises rather than guessing
(**X-6e**).
