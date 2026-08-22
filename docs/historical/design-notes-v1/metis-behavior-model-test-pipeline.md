# Requirement → State Transition Model → Test Pipeline
## Making v1 §5's Generation Table Actually Buildable — Constitution Amendment 3

---

## 0. What this closes

Every piece needed for this already exists somewhere in this project, but scattered and not connected end-to-end: EARS conformance (§4.3), `MicroRequirement` decomposition (v1 §3.2), the `Transition`-to-test-type mapping (v1 §5), `metis_propose_test_skeleton` (§11.1), the review queue (§7 Layer 7), and — as of last turn — the code graph (`CALLS` edges) and `test-suite-ingest`/`locust-performance` connectors. This document is the missing connective tissue: **the concrete stage sequence that takes an informal requirement and produces a real, executable functional or performance test, sitting correctly on top of whatever unit/integration coverage already exists**, not duplicating it.

---

## 1. The full pipeline, stage by stage

```
Informal requirement (Jira, Confluence, flat file, BMAD story, or verbal notes intake-processed)
    │
    ▼ [EARS conformance check -- CONST-002, deterministic, §4.3]
Requirement (EARS-conformant, Draft)
    │
    ▼ [Decomposition -- existing, business-analyzer-style, LLM-assisted per RPI]
MicroRequirement (single behavior, precondition/postcondition stated)
    │
    ▼ [STAGE 2 -- Behavior Modeling, NEW, detailed in §2 below]
Transition (State/Guard/Trigger/Action/Event populated)
    │
    ▼ [STAGE 3 -- Pyramid-Gap Check, NEW, detailed in §3 below]
    │   (queries existing unit/integration TestCase coverage via CALLS-edge
    │    traversal before deciding what to generate)
    ▼
    ├──▶ [Functional test skeleton -- metis_propose_test_skeleton, existing]
    └──▶ [Performance test skeleton, IF Performance:SLA-critical -- same tool, test_type=performance]
    │
    ▼ [LLM body-fill -- existing, RPI-gated, §9.2]
Test code (Draft, unreviewed)
    │
    ▼ [Human review -- §7 Layer 7, mandatory, never auto-promoted]
    │
    ▼ [STAGE 5 -- Commit-back, NEW, detailed in §4 below]
Real test file, committed to the actual repo via PR (merge-request-creator pattern)
    │
    ▼ [test-suite-ingest / locust-performance connector picks it up on next run]
TestCase (Approved), now indistinguishable in the graph from any other real, executing test
```

The loop closing at the bottom is the important structural property: **a generated test doesn't live only as a graph node** — it becomes an actual file in the actual repository, gets executed by actual CI, and re-enters the graph through the same connector that ingests any other test. This is what makes "real functional and performance tests" true rather than aspirational — nothing about this pipeline produces a test that only exists inside this platform.

---

## 2. Stage 2: Behavior Modeling — MicroRequirement → Transition (the genuinely new part)

This was previously described only as an ontology target (v1 §3.3), never as an operational stage. Making it concrete:

### 2.1 What the LLM does vs. what's deterministic (per §9's own decision framework, applied here)

| Sub-step | Deterministic or judgment? |
|---|---|
| Parsing a `MicroRequirement`'s stated precondition/postcondition into candidate `State` names | Judgment — natural-language interpretation, genuinely needs an LLM call |
| Identifying the `Trigger` (event/API-call/timer) from the requirement's "when" clause (EARS Event-driven pattern already surfaces this explicitly, §4.3) | Mostly deterministic once EARS-conformant — an Event-driven-pattern requirement's trigger is close to syntactically extractable, not free interpretation |
| Identifying `Guard` conditions from the requirement's "if"/unwanted-behavior clause (again, EARS's Unwanted-behavior pattern already isolates this) | Same as above — EARS conformance does real work here, this is a big reason CONST-002 is a hard gate and not a nice-to-have |
| Populating `Action`/`Events Published`/`Database Updates` | Judgment, informed by corroboration (§2.2 below) |

### 2.2 Corroboration source you didn't have before last turn: the code graph

A proposed `Transition` built purely from requirement-text interpretation is exactly the kind of single-source, interpretive content that shouldn't reach `auto_write` confidence under §7.3's existing rules. **The code graph extension (last turn) gives this stage a genuine second source**: if `application-code`'s `CALLS`/`IMPORTS` edges show an implementing `Method`'s actual control flow (branches, guard clauses, calls to other methods matching the proposed `Action`), that structural evidence **corroborates** the proposed `Transition` per CONST-003/CONST-019's existing ≥2-source rule — the code itself is the second source, not another document. This is a new, concrete instance of corroboration that didn't exist as an option before the code graph was built.

`REQ-METIS-BM-01`: a proposed `Transition` reaches `auto_write` tier only if (a) it passes structural validation (§7 Layer 2) and (b) either a second textual source agrees, or the code graph's structural evidence for the implementing `Method` corroborates the proposed guard/action shape. Absent either, it's `quarantine`-tier, same as any other single-source high-risk content.

`REQ-METIS-BM-02`: where a proposed `Transition` and the code graph's actual structure **disagree** (the requirement says one guard condition, the code implements a different one), this is not silently resolved in either direction — it's written as a `ContradictionDetected` episode (§5.3) and held `Disputed`. This is a genuinely valuable failure mode to catch, not just a technicality: it's either a spec that's drifted from reality, or a bug — either way, a human needs to know, and guessing which one it is would be exactly the kind of silent reconciliation RPI's Forbidden Substitutions rule prohibits.

### 2.3 Set-level well-formedness: checking the whole state machine, not just one Transition at a time (Constitution Amendment 4)

§2.1–2.2 validate one proposed `Transition` in isolation. That's not enough — a `Transition` can individually pass corroboration and still leave the *set* of `Transition`s sharing a `State` ambiguous or incomplete in a way no single-`Transition` check would ever catch. Grounded in UML Behavior State Machine semantics (ISO/IEC 19505, `metis-standards-integration.md` §2), three checks run whenever a new `Transition` is proposed into a `State` that already has sibling `Transition`s:

- **Determinism** — no two `Transition`s from the same source `State` fire on the same `Trigger` with overlapping `Guard` conditions. A violation means the specification is genuinely ambiguous about what happens, not just under-specified.
- **Completeness** — every plausible `Trigger` for a `State` has a defined outcome (a `Transition`, or an explicit no-op). An undefined trigger-in-state is a classic, well-understood defect class, not a hypothetical concern.
- **Reachability** — every `State` is reachable from an initial state via some path. An unreachable `State` is either a design error or dead specification worth flagging.

`REQ-METIS-BM-04` (`CONST-048`): these are graph-computable properties (reachability is literally traversal) — implemented as deterministic Cypher queries, not LLM judgment, consistent with §9's code-vs-LLM principle. A violation is surfaced as a `Disputed`-adjacent flag per `CONST-049`, never silently resolved by picking one interpretation.
`REQ-METIS-BM-05` (`CONST-050`): a completeness violation, once a human resolves what the missing behavior should actually be, gets a corresponding generated functional test (§4 below) asserting that resolved behavior — closing the loop from "we found a gap" to "there's now a test proving it's closed."

---

## 3. Stage 3: Pyramid-Gap Check — the "on top of unit/integration" requirement

This is the part that makes generation additive instead of redundant. Before generating anything, query what already exists for this `Transition`'s implementing `Method`(s):

```
1. Find the Transition's implementing Method(s) via IMPLEMENTS edges.
2. Traverse CALLS edges (new, last turn) to find that Method's actual call chain.
3. Query test-suite-ingest's ingested TestCase graph (also last turn) for existing
   coverage at each layer, using the test file's own path/naming convention
   (unit test paths vs. integration test paths vs. functional/API test paths --
   most real projects already separate these structurally) plus the test
   framework detected (JUnit unit test vs. a REST-assured/Playwright functional
   test vs. a Locust performance test).
4. Compute coverage-by-layer for this Transition:
   unit: covered/not | integration: covered/not | functional: covered/not | performance: covered/not (only relevant if Performance:SLA-critical)
5. Generate ONLY for the gapped layers.
```

**DQ-008 amendment (extends the Data Quality Framework):** the existing DQ-008 ("functional test coverage") is too flat for this purpose — it doesn't distinguish which pyramid layer is covered, only whether *some* test exists. **Amended to be layer-segmented**: `DQ-008a` (unit), `DQ-008b` (integration), `DQ-008c` (functional), `DQ-008d` (performance, only scored for `Performance:SLA-critical` Transitions) — each computed the same way as the original DQ-008, scoped to test files matching that layer's convention. This is what makes Stage 3's gap check queryable as a real metric, not just an internal pipeline decision nobody can audit later.

`REQ-METIS-PG-01`: generation never fires for a layer that's already covered, regardless of how long ago that coverage was written — an old-but-passing unit test is still coverage; Stage 3 defers entirely to §7.2's existing stale-coverage detection (DQ-009) to decide if *re*-generation is warranted, rather than duplicating that logic here.

---

## 4. Stage 5: Commit-back — closing the loop for real

A reviewed, approved generated test doesn't just get a `lifecycle_state=Approved` flag in the graph — it has to become a real file. This reuses Atlas's own `merge-request-creator` pattern directly:

1. The approved test code is written to the correct path in the target repository (following that repo's existing test-path convention, detected during Stage 3's gap check).
2. It carries **that target project's own configured traceability-ID indicator** (`REQ-METIS-CONN-06` — resolved per-project, not a single global `@TestId` convention) linking it back to the `Requirement`/`Transition` it verifies — **generated tests get this automatically, for free, since the pipeline already knows the link and already resolved the target project's pattern before generating; this is actually a stronger guarantee than most human-written tests get**, where the annotation is easy to forget, or gets written in a format that doesn't match that project's actual convention.
3. A PR is opened via the same code-review-gating pattern `merge-request-creator`/`code-reviewer` already use (Article III, CONST-009) — a generated test is still code, still subject to the same review gate as anything else, including CONST-013's AI-generated-artifact review requirement.
4. On merge, the next `test-suite-ingest`/`locust-performance` connector run picks it up exactly like any pre-existing test — **at that point, the graph's `TestCase` node transitions from "generated, pending" to "real, ingested, executing," and the two representations converge into one.**

`REQ-METIS-BM-03`: a generated test's `GeneratedTest` provenance (v1 §3.8) is retained permanently after commit-back, same principle as `CONST-015`/`REQ-METIS-CG-02` — knowing a test was originally AI-generated (even after human review and years of subsequent edits) remains part of its history, never erased.

---

## 5. Constitution Amendment 3 — filed per Article X

> **Amendment 3 metadata**
> Type: Addition (new rules) + one metric segmentation (DQ-008 → DQ-008a–d)
> Rationale: operationalizes the Behavior Modeling and test-generation pipeline end-to-end; DQ-008's segmentation is necessary for Stage 3's gap-check to be auditable rather than an opaque internal decision.

**CONST-044.** Any `Transition` tagged `Performance: SLA-critical` (CONST-021) with no corresponding `performance`-type `TestCase` triggers automatic queuing for performance-test generation (§3–4 above) — this is CONST-021 made operational, not a new obligation, closing the gap between "the rule exists" and "something actually happens because of it."

**CONST-045.** A generated functional or performance test MUST carry a valid traceability annotation (`REQ-METIS-CONN-04`'s convention) before commit-back — a generated test with no annotation would re-orphan itself the moment it's ingested back through `test-suite-ingest`, defeating the entire pipeline's purpose.

**CONST-046.** Where Behavior Modeling's code-graph corroboration (§2.2) surfaces a disagreement between a proposed `Transition` and actual code structure, this is escalated as `Disputed`, never silently resolved toward either the spec or the code — per `REQ-METIS-BM-02`.

---

## 6. Worked example (to make this concrete, not just structural)

> **Input:** a vague ticket: "users should be able to cancel an order."
>
> **EARS conformance (CONST-002):** rejected in original form — no explicit condition or system response. Rewritten (human or `atlas-academy`-assisted): *"While an order is in Placed state, when the user requests cancellation, the system shall transition the order to Cancelled state and refund the payment, unless the order is already Shipped."*
>
> **MicroRequirement decomposition:** two atomic behaviors — (1) cancel-when-Placed, (2) reject-when-Shipped.
>
> **Behavior Modeling (Stage 2):** for behavior (1) — `Transition{from: Placed, to: Cancelled, trigger: CancellationRequested, guard: "status != Shipped", action: "refund payment; emit OrderCancelled"}`. Corroborated against the code graph: the implementing `Method` (`OrderService.cancelOrder()`) has a matching guard clause and calls `RefundService.process()` and `EventBus.emit()` — two-source corroboration achieved (text + code), reaches `auto_write` tier per `REQ-METIS-BM-01`.
>
> **Pyramid-Gap Check (Stage 3):** `test-suite-ingest` shows this method already has unit coverage (a `OrderServiceTest.testCancelOrder()` JUnit test exists) but no functional/API-level test, and this `Transition` isn't tagged `Performance:SLA-critical` — so generation targets **functional only**, skipping unit (already covered) and performance (not applicable).
>
> **Generation → review → commit-back:** a functional API test is skeleton-generated (`metis_propose_test_skeleton`, `test_type=functional`), body-filled, reviewed by a human (who confirms the refund-amount assertion matches business expectations — something the code graph alone couldn't verify), committed to the repo with **this project's own configured traceability-ID indicator** (resolved from its `project_test_id_conventions` entry, `REQ-METIS-CONN-06`) linking it to the original ticket, merged via the normal PR gate, and picked back up by `test-suite-ingest` on the next run — now a real, executing, `Approved` `TestCase`.

---

## 7. What's genuinely still open

| Item | Status |
|---|---|
| Which repos have consistent enough test-path conventions for Stage 3's automatic layer-detection to work reliably | Needs validation against your actual repos, not assumable in general |
| Whether commit-back (Stage 4) targets the same branch/PR as the code change that motivated it, or a separate PR | Reasonable to default to "separate PR, cross-referenced," but genuinely a workflow preference worth confirming |
| Human-review capacity for the volume Stage 2/3 will generate once this pipeline is actually running | Ties back to the already-waived staffing gap (§18) — worth revisiting specifically for this pipeline once real volume is visible, since generation volume here could be substantial |
