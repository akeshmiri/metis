# 08 — Behaviour Model, Test Design & Test Generation

The output side of the platform: from a verified behaviour model, through test
design, to executable tests, published test cases, review and merge.

## 8.1 The behaviour model

A `State`/`Transition` machine describing **real application behaviour** — a
login flow, a checkout, an order lifecycle. Scoped strictly: never a stand-in for
a generic business workflow or approval process (`REQ-BEH-010`).

```
State --[:WHEN]--> Transition --[:THEN]--> State
                      ├─ trigger              (the event that causes it)
                      ├─ guard_expression     (the condition that must hold)
                      ├─ implementation_status (implemented | planned)
                      ├─ extraction_method    (hand_authored | static_analysis)
                      └─ code_anchor          (repo:path:line)

AcceptanceCriterion --[:VALIDATES]--> Transition
```

`REQ-BEH-001` — `trigger` and `guard_expression` are **properties**, never nodes.
A trigger event and its guard condition exist only in the context of exactly one
transition; giving them independent identity implies a sharing that does not exist.

`REQ-BEH-002` — Determinism checking compares Transitions **by property value**
across a shared source State, never by shared node identity.

### Where transitions come from

| Source | Method | Confidence |
|---|---|---|
| Static code analysis (§13) | Six-step state-variable abstraction over the CPG | Quarantine, human-approved |
| Hand-authored | A modeller writes the machine | Quarantine, human-approved |
| Mined from a requirement | Stage 2 behaviour mining (§05.9) | Quarantine |

Where a code-derived and a hand-authored transition conflict, the result is a
contradiction held `Disputed` — not silent replacement (§04.4). The hand-authored
model may describe intended behaviour the code has not implemented yet, which is
information, not error.

## 8.2 Well-formedness checks

Four checks, all deterministic, all fail-closed.

| Check | Property | Failure means |
|---|---|---|
| **Determinism** | No two Transitions sharing a `(source State, trigger)` have overlapping guards | A real input could match two transitions — the machine is ambiguous |
| **Guard completeness** | Guards on a shared `(source State, trigger)` jointly cover the whole meaningful domain | A real input could match **no** transition at all — invisible anywhere in the graph |
| **Reachability** | Every State is reachable from an initial state | A State nothing can reach is either dead or the model is missing a transition |
| **AC coverage (DQ-024)** | Every `implemented` Transition has ≥1 `VALIDATES` edge | Real behaviour with nothing validating it is an unverified claim, not covered behaviour |

`REQ-BEH-003`/`004` — Both guard checks are required. Atomicity without
completeness catches double-matching but misses no-matching, which is the harder
failure to notice because it produces no error anywhere — the input simply does
nothing.

`REQ-BEH-005` — **Fail-closed:** an unparseable guard, or guards over different
variables, is flagged **unverifiable**, never assumed correct. A check that
silently passes what it cannot analyse is worse than no check, because it
manufactures confidence.

`REQ-BEH-007` — `planned` Transitions are excluded from coverage-gap computation.
They are not gaps; they do not exist yet.

`REQ-BEH-011` — A well-formedness failure is surfaced as `Disputed`, never
silently resolved.

### Why AC coverage must target the Transition, not the State

`REQ-BEH-009` — An `AcceptanceCriterion` validates the whole
`(source State, trigger, guard, target State)` scenario.

Validating the target State alone would hide exactly the class of gap explicit
states exist to catch: if four different failure states all transition to
`LoggedIn`, validating the State would make all four look covered by testing one.

### When a condition should become a State

| Promote to `State` | Keep as `guard_expression` |
|---|---|
| Bounded, enumerable, durable — a capped retry counter | Continuous or unbounded — elapsed time |
| | Per-request, evaluated fresh — credential validity |
| | Combinatorial (`A OR B`) — unfolding multiplies without adding clarity |

This rule is what decides whether a statically-recovered guard such as
`attempt_count >= 5` should be unfolded by a human into explicit states. Joern
proposes the guard form; this rule governs the modelling decision (§13.13).

## 8.3 Test design

`REQ-TST-001` — Every test scenario traces to a requirement. Invented scenarios
are prohibited.

```
Intent
  └─ TestDesign  (techniques named)
       ├─ COVERS  → AcceptanceCriterion
       └─ PRODUCES → TestCase
```

`REQ-TST-002` — A `TestDesign` names the design technique(s) used — equivalence
partitioning, boundary value analysis, decision table, state transition, pairwise,
error guessing. "We wrote some tests" is not a design.

### Scenario normalisation

Each scenario carries: `id`, `title`, `source_ac`, `behaviour`, `precondition`,
and one or more conditions each with `id` and `condition_text`. All ids unique,
all traced to source, minimum one scenario.

### Coverage mapping

`REQ-TST-005` — Every scenario receives `automation_status` ∈
`covered` | `missing` | `partial`. **Ambiguous evidence is never treated as
covered** — that single rule is the difference between a coverage number that
means something and one that flatters.

### Automation viability

`REQ-TST-003` — Every missing scenario is classified:

| Classification | Meaning |
|---|---|
| `extend-existing` | An existing test surface covers this; extend it. The owning surface must be identified |
| `generate-new` | No existing surface; generate |
| `migration-first` | The surface exists but must be migrated before extension |
| `duplicate-covered` | Already covered; do not generate |
| `blocked` | Cannot be automated yet; the blocker must be named |

`REQ-TST-004` — Blocked and duplicate-covered scenarios are **never** passed to
generation.

`REQ-TST-006` — An equivalent-coverage check runs before generation to prevent
duplicate tests, matched on exact endpoint/flow rather than on similarity of name.

### Test levels

`REQ-TST-016` — `TestCase.type` ∈ `unit` | `integration` | `api_functional` |
`web_functional` | `e2e` | `performance`.

## 8.4 The anti-hallucination contract for generation

This is the most important section in this document. Generated test code that
references something which does not exist is the failure mode that destroys trust
in the whole platform fastest.

**Dual-layer prevention:**

| Layer | Mechanism | Requirement |
|---|---|---|
| **1. Verification** | Every referenced class, method, path, endpoint and field is checked against the CPG-derived registry (§13.7) | `REQ-TST-007` |
| **2. Conditional gate** | A reference absent from the registry **fails the stage** — it does not warn, and it does not generate with a placeholder | `REQ-TST-008` |

`REQ-TST-008` is a hard fail by design. In Atlas this was a prose instruction
("no UNVERIFIED fields used in payloads") enforced by instruction-following. With
a CPG it becomes mechanical, and mechanical is the entire point.

`REQ-TST-018` — Evidence status per source is logged as `present` | `partial` |
`absent`. Absent evidence downgrades affected items to `inferred` rather than
letting them pass as verified.

## 8.5 Functional generation — API

| Stage | Output | Gate |
|---|---|---|
| Planning normalisation | Implementation matrix mapping each approved slice to its owning surface | Equivalent-coverage check confirms no existing coverage |
| Approval | A generation batch draft, written and **shown before any code is generated** (`REQ-TST-009`) | Explicit confirmation |
| Generation | Client/interface code, request and response types, test methods, configuration | Types come from the registry, never inferred |
| Test-case drafting | Structured test cases in the organisation's test-management format | Regression checklist addressed per endpoint (`REQ-TST-017`) |
| Publishing | Handoff to the publisher skill | §8.7 |
| Compile check | Language-appropriate build | `REQ-TST-010` — failing compile fails the stage |
| Annotation | Test-ID annotation linking to source requirement/test case | `REQ-TST-011` |

`REQ-TST-010` — The compile check runs **after** the specialist completes, when
code actually exists, and a failure fails the stage. Published test cases already
uploaded are **not** rolled back — that is stated explicitly so the operator knows
the cleanup boundary rather than discovering it.

## 8.6 Functional generation — Web

Same pipeline, different specialist. Additional constraints:

- Page objects with **concrete, verified locators** — never a locator guessed from
  an element description.
- Its own regression checklist for UI concerns.
- A UI element that cannot be verified to exist blocks generation for that
  scenario rather than producing a speculative selector.

## 8.7 Test-case publishing

`REQ-TST-012` — Drafts are written to a transient location and their **full
content shown to the user** before any external test-management action runs.

`REQ-TST-013` — **No external call occurs without a prior explicit affirmative
confirmation.** Not an implied one, not a default-yes, not a confirmation of
something adjacent.

`REQ-TST-014` — Generated code maps 1:1 to published test-case identifiers when
publishing occurred.

One skill is the **sole owner** of external test-management writes (create folder,
search, create test case, attach steps). Specialists hand off to it; they never
call the external system directly. A single owner is what makes
`REQ-TST-013` verifiable — there is exactly one place to assert against.

**Acceptance test:** withhold confirmation and assert **zero** external calls
were made.

## 8.8 Performance generation

`REQ-PERF-001` — Candidates trace to approved business flows. Invented candidates
are prohibited.
`REQ-PERF-002` — SLA targets come from requirements, **never inferred from code**.
A latency target read off an existing implementation measures what the system
does, not what it should do — and then tests it against itself.

| Stage | Output | Gate |
|---|---|---|
| Design | Performance candidate set | Traced to approved flows |
| Preparation | Validated data sets | `REQ-PERF-004` — identifiers preserved as strings; contract assumptions validated against real endpoint contracts |
| Generation | Load-test scenarios and scripts | `REQ-PERF-003` — provider-backed data selection, never hardcoded; `REQ-PERF-005` — no duplicate endpoint or scenario coverage |
| Measurement | Performance summary | `REQ-PERF-006` — latency percentiles, failures and regressions reported explicitly, in the normalised status vocabulary |

`REQ-PERF-004`'s string rule looks trivial and is not: numeric coercion of
identifiers silently corrupts high-precision ids, and the resulting test passes
against the wrong entity.

Performance tests attach to the graph as
`TestCase{type: performance} -[:VERIFIES]-> Endpoint` — the one case where a
TestCase verifies an Endpoint rather than an AcceptanceCriterion.

## 8.9 Code review

`REQ-REV-001` — Findings are classified **Critical / Major / Minor / Info**.
`REQ-REV-002` — Critical or Major findings **block** merge-request creation.

| Review dimension | Checks |
|---|---|
| Requirement satisfaction | `REQ-REV-008` — the test actually asserts the requirement, not merely that a test exists with a matching name |
| Specification exercise | The contract is genuinely exercised — serialisation, error handling, auth |
| Hallucination | `REQ-REV-009` — every referenced class and method verified against the registry |
| Traceability | Test-ID annotations present and resolving to real graph nodes |

`REQ-REV-003` — **A review verdict is itself a governed AI artifact.** It carries
accountability metadata. It is not exempt from the no-fabrication rule for being
evaluative rather than generative — an unfounded "approved" is a fabrication with
unusually high consequences.

## 8.10 Merge requests

`REQ-REV-004` — The draft is shown and explicitly confirmed before any remote
create or update call.
`REQ-REV-005` — AI-authorship analysis is completed and the AI-assistance
proportion is **explicitly requested from the user**, never assumed or inferred.
`REQ-REV-006` — The title carries the configured AI-review labelling.
`REQ-REV-007` — The system states explicitly whether the label was applied,
created, or blocked — three distinct outcomes that must not be collapsed into
"done".

## 8.11 Defect-driven regression

```
Failure evidence  →  Defect record  →  Reproduction scenario
                                    →  Regression test design
                                    →  Generated test
                                    →  Coverage verification
```

| Requirement | Rule |
|---|---|
| `REQ-DEF-001` | The defect traces to exact failure evidence, never inferred |
| `REQ-DEF-002` | Drafts are written transiently and explicitly confirmed before filing |
| `REQ-DEF-003` | Derived test cases replicate the **exact** reproduction steps as preconditions |
| `REQ-DEF-004` | No invented test conditions; all trace to the defect or a linked story |
| `REQ-DEF-005` | Failed executions produce a linked `Defect` node |
| `REQ-DEF-006` | Coverage reports state which scenarios are covered versus pending |

`REQ-DEF-003`'s "exact" matters: generalising reproduction steps into a tidier
scenario is how a regression test stops reproducing the regression.

## 8.12 Execution recording

```
TestCycle {run_type: ci|smoke|nightly|regression}
   ▲ PART_OF
TestExecution {executed_at, result}
   ├─ EXECUTES     → TestCase
   ├─ PRODUCES     → Defect                      (failed executions only)
   └─ RAN_AGAINST  → ApplicationConfiguration
                        └─ INCLUDES_VERSION {version} → Service
```

Per-case results live on `TestExecution`, never as a flat property on the cycle —
a cycle-level flag cannot answer "did *this* case pass in *this* run" once a cycle
covers more than one case.

`ApplicationConfiguration` carries no version data itself; every version lives on
its own edge. This is what makes a release report able to say which component
versions a result actually reflects.

## 8.13 Coverage computation

| Metric | Definition |
|---|---|
| Functional coverage | `implemented` Transitions reachable from an Approved Requirement with ≥1 non-stale verifying TestCase |
| API coverage | Endpoints with a direct Requirement trace and ≥1 verifying TestCase |
| Performance coverage | SLA-tagged Transitions with ≥1 performance TestCase |
| Security coverage | Auth, payment and data-deletion paths with negative **and** boundary cases |
| Stale coverage | TestCases whose validity predates their linked Transition's most recent change |

`REQ-GOV-006` — The security floor cannot be traded against a higher percentage
elsewhere. An overall coverage number that hides an untested authentication path
is precisely the report this platform exists to prevent.

## 8.14 Acceptance tests for this subsystem

| Test | Asserts |
|---|---|
| Guard atomicity | An overlapping-guard pair is detected |
| Guard completeness | A domain gap (`>= 0.9` / `< 0.5`, leaving `[0.5, 0.9)`) is detected, and a genuinely exhaustive group is not false-positived |
| Fail-closed | An unparseable guard is flagged unverifiable, not passed |
| Reachability | An unreachable State is reported |
| DQ-024 | An `implemented` Transition with no validating AC is flagged; a `planned` one is not |
| Registry gate | A payload referencing an absent field **fails the stage** |
| Compile gate | Non-compiling generated code fails the stage |
| Confirmation gate | Withholding confirmation produces **zero** external calls |
| Traceability | Every generated TestCase verifies an AC, never a Requirement directly |
| Review gate | A Critical finding blocks MR creation |
| Defect fidelity | A generated regression test's preconditions match the reproduction steps exactly |
