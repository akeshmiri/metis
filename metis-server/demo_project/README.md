# The demo corpus

A Records service that exists to be *extracted*, not to run. Every file here is a
condition some pack behaviour is asserted against, in `../test_extraction.py`.

## Why it exists

Before this corpus the five query packs in `code_analysis/packs/` had **no
behavioural test**. The only assertions on them were greps for a string inside
the Scala, and every correctness claim lived as prose in a `pack.yaml`
`verified_against:` block naming a private repository — five different ones, none
re-checkable by anybody. A pack edit could change what Métis recovers and nothing
would fail.

Building this corpus found ten defects on live paths. Two examples, both of which
had been reported as *zero* rather than as an error:

- `ResponseEntity.status(HttpStatus.X).body(...)` was unreadable, so a service's
  rejection paths came back empty. It is the only form that can carry a body with
  a 4xx (`notFound()` returns a `HeadersBuilder`), so it is what every real error
  handler writes.
- The test-inventory pack ran against a CPG that **structurally cannot contain a
  test**: javasrc2cpg ignores test directories by name. The recorded diagnosis
  blamed unresolved dependencies and pointed at `--fetch-dependencies`, which
  reaches Maven Central and would not have helped.

## How to add to it

**When a real project exposes a defect, reproduce the condition here first, then
fix it.** That order matters: a fix with no condition behind it is a fix nothing
defends. Add the smallest file that exhibits the shape, assert the corrected
output in `test_extraction.py`, and note the condition in the table below.

Nothing here may name a company, a customer, or a private repository. `com.example`
is the reserved-for-examples namespace and the domain is deliberately dull.

## What each part proves

### `records-service/` — the API surface (javasrc2cpg)

| File | Condition |
|---|---|
| `RecordController` | five handlers, mixed verbs, `@Valid`, and two project annotations |
| `ArchiveController` | a route composed from constants **only** — `BASE` + (`ID_SEGMENT` + `"/archive"`), no literal anywhere — plus `@ResponseStatus` |
| `RecordAdvice` | estate-wide 404, 409 and 423 via `status(HttpStatus.X).body(...)` |
| `LegacyAdvice` | the **contested** mapping: `RecordLockedException` to a second status with no `@Order`, so precedence is not statically decidable (GD-9) |
| `ScopedController` | an in-controller `@ExceptionHandler`, scoped by Spring to its own endpoints |
| `ArchiveClient` | `@FeignClient` — two mappings that must **not** be counted as endpoints |
| `dto/RecordDto` | `@Schema`, `@NotBlank`, `@Size`, and an enum whose constants are equivalence classes |
| `dto/ErrorDto` | every rejection has a body type, so `response_body` is never the empty string (which is a claim, not a gap) |
| `dto/RecordSummaryDto` | the intake-noise conditions (X-5a): six trivial accessors and three boilerplate methods that must be **dropped**, plus `getRetries()` — a real field behind it *and* a branch — and `getDisplayLabel()` — a branch and no field — which must both be **kept** |
| `ScopedController.requireSummarisable` | private, guards an endpoint, raises the exception its own handler maps: the case that proves visibility is the wrong axis |
| `annotation/DemoSecured` | a project annotation Métis ships no knowledge of; `profile.json` is the only reason it is understood |
| `annotation/Audited` | `role: ignore` — known and deliberately irrelevant, which is a different statement from unrecognised |
| `dto/RecordBatchDto` | the **nested payload** (X-6b): `List<RecordDto>` whose element type must be followed, `@Size` on a collection landing as `expected_max_size` rather than `_length`, an `@Pattern`, and `@NotBlank @Size(min = 3)` composing to the **strongest** bound — reporting 1 there is weaker than the code |
| `RecordBatchDto.Mode` | an enum with a method (`fromValue`), which is the only shape that reaches `DECLARES_METHOD` from an `:Enum` — the case that catches an edge planned against `:Class`. Plus `private final Mode fallback`, self-typed and **not** a constant: read as one it becomes a fourth value a caller could send |
| `RecordResponses` | two guard shapes. `listOrEmpty` branches to `ok`/`noContent`, so both resolve and an outcome **references** the check; `labelFor` branches to helpers naming no status, so the check is **stranded** and must attach to its endpoint instead |
| `InternalAudit` | reached by no parameter, no response body and no nested field — it must be classified `internal` and **not landed** (X-6d). Delete it and the compaction test stops testing anything |
| `src/test/java/` | real JUnit and Feign `@RequestLine`; one test asserts inline, one through a private helper, one asserts nothing, and one uses a bare literal path that must stay unresolved |

### `records-ui/` — the React surface (jssrc2cpg)

| File | Condition |
|---|---|
| `router.js` | four routes in a `createBrowserRouter` config, which is what jssrc2cpg actually lowers |
| `SummaryPage.jsx` | **two regex literals** — a regex starts with `/` exactly like a path. Deleting them deletes the proof that the recogniser refuses |
| `RecordDetailPage.jsx` | an interpolated path, which must be reported rather than resolved to its first fragment |
| `RecordListPage.jsx` | `setStatus` with literal arguments — the `ui_states` whose absence kept `react` from being a declared framework |
| both pages | `setStatus(x ? "ready" : "error")`, two real states inside a ternary |

### `records-page/` — the plain-DOM surface (jssrc2cpg)

| File | Condition |
|---|---|
| `records.html` | a small real page: `id`, `class` and `data-testid` hooks a pack can read, and one button (`Export`) deliberately given **none** |
| `page.js` | **where a selector comes from.** `document.getElementById("archive")` is a literal the pack reads, so a selector is *extracted* — it is never authored and never guessed. Four resolve; `exportButton` is reached by walking the DOM (`…children[2].firstElementChild`), so nothing names it and it is reported unresolved. The walk's own `querySelector("tr")` is emphatically not its selector |


`addEventListener`, of which a React application has none — which is why `js-ui`
and `react-ui` are separate packs. One named handler passed by reference, two
inline closures.

### `structure.json` — what is on a page, and where the data lives

Authored, because no pack identifies a component *type*: none can tell a library
`<DataGrid>` from a hand-rolled `<div role="table">`, and all three are a table to
a person writing a test. It carries **no selectors** — those come from `page.js`
above, and the two join on the element's name.

It also holds the database catalogue (`record`, `record_tag`) the query scaffold
is generated from. `record_tag` declares **no primary key** on purpose: a table
with none gets no by-key query rather than an invented one.

### `openapi.json` and `specs/` — the stated side

Three deviations from the code, one per category:

| Deviation | Category |
|---|---|
| the contract documents `POST /record/{id}/restore`, the code has none | contract-only |
| the code has `POST /record/{id}/archive`, the contract omits it | code-only |
| the contract says `DELETE /record/{id}` → 200, the code returns 204 | disagreement |

`specs/records/spec.md` is a third, hand-written account: seven behavioural
criteria and one narrative one that must stay marked as not-a-transition. Its
`AC-4` says 204, so the contract and the criteria disagree with each other as well
as with the code — which is the situation reconciliation exists for.

## Running it

The test suite builds these CPGs itself; `conftest.py` caches them by a hash of
this directory, so they rebuild when the corpus changes and not when Métis does.

```bash
uv run python -m pytest -q test_extraction.py
```

Joern and a JDK are required and a missing one **fails** rather than skipping — a
skip would quietly restore the situation this corpus was built to end. No
database and no network are needed: extraction is database-free, and nothing here
resolves a dependency from a registry.

## `trackers/` — Jira and Zephyr Scale

Captured tracker responses, in the shape `code_analysis.tracker` reads. Each
file is a condition asserted in `test_tracker.py`.

| item | what it proves |
|---|---|
| `DEMO-1` | an **EARS-conformant summary with non-conforming description prose**. This is the ordinary Jira shape and it is the condition that exposed the selection bug: `_requirement_text` preferred description unconditionally, threw the conforming sentence away, and landed the ticket as a `Finding`. It must land as a `Requirement` |
| `DEMO-1`'s description | **Atlassian Document Format** — a nested node tree across two text nodes, the second with its own leading space. Proves the flattener takes text only, reconstructs no structure, and collapses the seam |
| `DEMO-2` | *"Archive is broken again"* — a real Jira title and not a requirement. Must land as a `Finding` pointing at knowledge-capture, verbatim and unmassaged (S-13) |
| `DEMO-T1` | Zephyr Scale's **flat** shape, against Jira's nesting under `fields`. Also that `source_system` stays `scale`, which is what `ANCHORS` keys `ZephyrItem` on |

No company or customer name appears in either file; the base URL is
`tracker.example.com`.
