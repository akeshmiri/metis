# 11 — Requirements Catalogue

The contractual baseline. Every requirement is uniquely identified, normative,
and carries a verification method. This document is the artifact a build team is
held to; the other documents explain *why* each requirement is shaped as it is.

## 11.1 Conventions

**Normative language:** `MUST`/`SHALL` — mandatory. `MUST NOT` — prohibited.
`SHOULD` — deviation requires a recorded rationale. `MAY` — optional.

**Verification methods:**

| Code | Method |
|---|---|
| **T** | Automated test — a named test asserts it, and it runs in CI |
| **D** | Demonstration — a runnable command with an observable result |
| **I** | Inspection — code/config/document review against a checklist |
| **A** | Analysis — measurement against a threshold |

`REQ-PLT-000` — Every requirement in this catalogue MUST have a traceable
implementation and a verification artifact before the phase that owns it is
declared complete. A requirement with no verification artifact is not satisfied,
regardless of whether the code appears to exist.

### Scope markers

Following the decisions in [§01.7](01-vision-and-scope.md), requirements carry
one of three scope markers. **Nothing is deleted** — a deferred requirement is
still normative for the release that delivers it.

| Marker | Meaning |
|---|---|
| *(none)* | In scope for v1 and fully verifiable |
| **⚠ partial** | In scope, implemented, but **only partially verifiable** in v1 — the exit record must say so, and it must not be reported as verified |
| **⛔ deferred** | Specified and normative, **not delivered in v1**. Belongs to the follow-on backlog (§12.10) |

`REQ-PLT-000a` — A requirement marked **⚠ partial** MUST appear by ID in its
phase's exit record, naming exactly which behaviour was not exercised. Reporting
it as satisfied is a process failure, not a rounding error.

### Requirements affected by the v1 scope decisions

| ID | Marker | Reason |
|---|---|---|
| `REQ-CGA-013`, `014`, `015`, `016`, `017`, `018`, `019` | ⛔ deferred | DD-1 — §13 Layers 4–5 |
| `REQ-CGA-023` | *(revised)* | Pilot gate reduced to the v1 criteria; follow-on gate retained |
| `REQ-BEH-008` (DQ-024 AC coverage) | ⚠ partial | DD-1 — computed but unfalsifiable; mandatory qualifier per `REQ-DQ-001` |
| `REQ-DQ-001` | *(revised)* | Adds the v1 publication qualifier |
| `REQ-INT-015` (incremental resumable sync) | ⚠ partial | DD-3 — cursor advance simulated by timestamp-sliced replay |
| `REQ-INT-016` (auth failure handling) | ⚠ partial | DD-3 — stub only |
| `REQ-TST-013` (no external call without confirmation) | *(fully verifiable)* | DD-4 — this is a **negative** test; a recording stub proves it completely |
| `REQ-TST-014` (1:1 mapping to published IDs) | ⛔ deferred | DD-4 — no published identifiers exist |
| `REQ-REV-004`, `REV-006`, `REV-007` (MR creation, labelling) | ⚠ partial | DD-4 — positive path stub-only |
| `REQ-DEF-002` (defect filing confirmation) | ⚠ partial | DD-4 — positive path stub-only |
| `REQ-DEF-005` (failed executions produce Defect nodes) | *(in scope)* | Internal graph write, not an external one |
| `REQ-SEC-004` (cross-team denial) | *(in scope, harder)* | DD-2 — enforced at application level; see `REQ-SEC-004a`/`b` |
| `REQ-OPS-005` (backup/restore) | *(revised)* | DD-2 — offline dump; superseded by `REQ-OPS-005a` |

### Requirements added by the v1 scope decisions

| ID | Requirement | V |
|---|---|---|
| `REQ-SEC-004a` | With no native RBAC, team scoping MUST be enforced at the application layer through a **single choke point** every query passes through. | T |
| `REQ-SEC-004b` | A test MUST assert that **no query path bypasses** the scoping choke point — stricter than asserting that scoping works. | T |
| `REQ-OPS-005a` | Backup is a scheduled **offline** dump; a restore drill MUST be performed and MUST reproduce the graph. An untested backup is not a backup. | D |
| `REQ-INT-019` | The cached export MUST include the **full changelog** for every issue; without it the changelog-anchored temporal strategy is untestable. | T |
| `REQ-INT-020` | The export MUST contain a bulk edit, a reopened issue, an AC outside the configured field, an unmapped issue type, and a non-EARS story. | I |
| `REQ-INT-021` | The cached export is real company data, subject to the classification gate, with an explicit classification entry. | I |
| `REQ-INT-022` | Rate-limit backoff, auth-failure handling, real pagination boundaries and live cursor advance MUST be listed as **unexercised against a live instance** in the phase exit record. | I |
| `REQ-CGA-024` | In v1, code analysis corroborates through **structural evidence only** — `Endpoint` or `Method` from a CPG at a named commit, human-approved. | T |
| `REQ-CGA-025` | **Name similarity alone never establishes corroboration.** A similar-sounding endpoint is a candidate for review, not evidence. | T |

## 11.2 Area index

| Area | Scope | Owning phase (§12) | Count |
|---|---|---|---|
| **PLT** | Platform, architecture, configuration | P0–P1 | 14 |
| **ONT** | Ontology and graph schema | P1 | 14 |
| **TMP** | Temporal model and provenance | P1 | 12 |
| **RES** | Resumability and idempotency | P1–P2 | 9 |
| **INT** | Jira intake | P2 | 18 |
| **MIN** | Requirement mining | P2 | 12 |
| **GRD** | Guardrail stack | P3 | 33 |
| **DQ** | Data-quality framework | P3 | 8 |
| **GOV** | Constitution and governance | P3 | 8 |
| **WFE** | Workflow engine | P4 | 16 |
| **SKL** | Skills and agents | P4 | 8 |
| **CGA** | Static code analysis | P5 | 23 |
| **BEH** | Behaviour model | P5 | 11 |
| **TST** | Test design and functional generation | P6 | 18 |
| **PERF** | Performance test generation | P6 | 6 |
| **REV** | Code review and merge requests | P6 | 9 |
| **DEF** | Defect management | P6 | 6 |
| **RPT** | Reporting | P7 | 11 |
| **ACD** | Academy and explainability | P7 | 8 |
| **MCP** | Tool and API surface | P7 | 12 |
| **SEC** | Security, auth, data protection | P8 | 14 |
| **OPS** | Deployment and operations | P8 | 12 |
| **COST** | Token and cost management | cross-cutting | 9 |

---

## 11.3 PLT — Platform and configuration

| ID | Requirement | V |
|---|---|---|
| PLT-001 | The graph MUST be the single authoritative store for graph state, episode provenance, review-queue state, cost tracking and RBAC. No second operational database is required for the platform's own state. | I |
| PLT-002 | No configuration MAY be embedded in code. Model names, data-sensitivity classification, endpoints and credentials MUST resolve through a configuration layer. | T |
| PLT-003 | The server MUST refuse to start when no configuration file exists. Starting with defaults is prohibited. | T |
| PLT-004 | Configuration resolution MUST follow a documented precedence (project → host → template), first-found-wins, with no silent merging. | T |
| PLT-005 | Credentials MUST resolve from a credentials path distinct from general configuration, and MUST NOT be readable through general file-read tooling. | I |
| PLT-006 | The system MUST be installable from a clean checkout with a single documented command, and that command MUST be exercised in CI. | T |
| PLT-007 | Every external dependency version MUST be pinned, including the code-analysis engine and the model SDK. | I |
| PLT-008 | The integration test harness MUST provision a disposable database, apply schema, and remove it at teardown. Tests MUST NOT write to a deployed configuration. | T |
| PLT-009 | High-volume raw data (test executions at 1M+/month scale) MUST NOT be duplicated into the graph; only aggregates with a drill-down reference. | T |
| PLT-010 | Demo/reference data MUST be wipeable and regenerable by one command, and MUST be regenerated after any graph-affecting change. | D |
| PLT-011 | The platform MUST expose a health endpoint reporting database connectivity, schema version and configuration validity. | D |
| PLT-012 | Schema version MUST be recorded in the graph and checked at startup; a mismatch MUST block startup rather than migrate implicitly. | T |
| PLT-013 | All timestamps MUST be stored in UTC, normalised at the ingestion boundary. | T |
| PLT-014 | Every node identifier MUST be content-derived, never sequence- or position-derived. | T |

## 11.4 ONT — Ontology and schema

| ID | Requirement | V |
|---|---|---|
| ONT-001 | A label or edge type MUST exist in all four governance places; CI MUST fail when they disagree, including when only one is edited. | T |
| ONT-002 | Structural validation MUST reject a candidate that does not match this ontology, and MUST NOT auto-create entities to satisfy a dangling reference. | T |
| ONT-003 | The ontology MUST be closed. No runtime-inferred or dynamically created labels. | T |
| ONT-004 | No entity MAY exist without at least one `source_episode_id`, enforced as a schema constraint. | T |
| ONT-005 | A `TestCase` MUST NOT `VERIFIES` a `Requirement` directly; traceability MUST route through an `AcceptanceCriterion`. | T |
| ONT-006 | Writes to `Intent`, `Requirement`, `AcceptanceCriterion`, `BusinessRule` MUST be rejected when the originating episode's connector is not `jira`. | T |
| ONT-007 | Edges MUST NOT be written to entities external to the analysed repository set; external stubs MUST be filtered, never materialised. | T |
| ONT-008 | `Metrics` nodes MUST store aggregates only, with a reference to the source system. | T |
| ONT-009 | A `State` shared across Transitions MUST carry the union of all touching Transitions' `functional_areas`, computed once. | T |
| ONT-010 | `HAS_REVISION` MUST be written only by the temporal module's revision recorder. | T |
| ONT-011 | Every relationship type MUST have a relationship-property index on `t_valid`. | T |
| ONT-012 | Enum-valued properties MUST have presence enforced by schema constraint and membership enforced by the application gate. Both required. | T |
| ONT-013 | The semantic/vector retrieval path MUST refuse to run until embeddings are populated, and MUST NOT fall back silently to another mode. | T |
| ONT-014 | The tag-citation `VERIFIES` exception MUST remain documented; validation MUST NOT police that call site's target label. | I |

## 11.5 TMP — Temporal model and provenance

| ID | Requirement | V |
|---|---|---|
| TMP-001 | Four timestamps MUST be modelled distinctly: `t_event`, `t_recorded`, `t_ingested`, `t_valid`/`t_invalid`. | I |
| TMP-002 | `t_valid` MUST be derived from `t_recorded`, never from `t_ingested`, whenever the source provides a reliable recorded timestamp. | T |
| TMP-003 | `t_ingested` MUST be used for pipeline debugging only and MUST NOT appear in any temporal query path. | T |
| TMP-004 | Every connector MUST populate `t_recorded` from its source's native mechanism. A `now()` default is a specification violation, not an acceptable fallback. | T |
| TMP-005 | Where a source provides no reliable recorded timestamp, the fact MUST be flagged `inferred` and routed to quarantine — never silently defaulted. | T |
| TMP-006 | Validity windows MUST close automatically on supersession; nothing is destructively overwritten. | T |
| TMP-007 | The cross-source precedence table MUST be stored as versioned, editable graph data, not hardcoded. | T |
| TMP-008 | Irreconcilable conflicts MUST produce a contradiction episode and hold the entity `Disputed`; both values retained. | T |
| TMP-009 | `as_of(entity, timestamp)` MUST reconstruct point-in-time state. | T |
| TMP-010 | `history(entity)` MUST return the full supersession chain with source and precedence tier per version. | T |
| TMP-011 | `diff(entity, t1, t2)` MUST return a structural diff. | T |
| TMP-012 | Every write path MUST record a revision. A write path that does not is a defect, and CI MUST enumerate any that do not. | T |

## 11.6 RES — Resumability and idempotency

| ID | Requirement | V |
|---|---|---|
| RES-001 | Every generated or extracted unit MUST carry a `unit_id` derived deterministically from its inputs. | T |
| RES-002 | Every edit episode MUST carry `delta_type` ∈ {ADDED, MODIFIED, REMOVED}. | T |
| RES-003 | Long-running artifacts MUST carry `checkpoint_status` ∈ {PENDING, COMMITTED, FAILED}, flipped to COMMITTED only after the full atomic write including guardrail checks succeeds. | T |
| RES-004 | Resume MUST discard all PENDING units, find the highest COMMITTED unit, and continue — never resume mid-unit. | T |
| RES-005 | A write against an existing COMMITTED `unit_id` MUST be a no-op, not a duplicate or an error. | T |
| RES-006 | Idempotency MUST be enforced by a composite database constraint on `(source_connector, unit_id)`, not by application-level checking alone. | T |
| RES-007 | A run interrupted by SIGKILL and resumed MUST produce a graph identical to an uninterrupted run. | T |
| RES-008 | Writes MUST be safe against transaction retry — a bare create on a precomputed id is prohibited; merge-with-on-create semantics are required. | T |
| RES-009 | The resume algorithm MUST apply uniformly to extraction batches, long document generation and background consolidation runs. | T |

## 11.7 INT — Jira intake

| ID | Requirement | V |
|---|---|---|
| INT-001 | Requirement intake MUST be implemented for Jira only. A write of `Requirement`/`AcceptanceCriterion`/`Intent`/`BusinessRule` from a non-`jira` connector MUST be rejected. | T |
| INT-002 | The extractor interface, UIF schema and Episode contract MUST remain source-agnostic so a second source is additive, but no second source MAY ship in v1. | I |
| INT-003 | `t_recorded` MUST come from the Jira changelog/history API, never from poll time or a diff between polls. | T |
| INT-004 | Field mappings (issue types, statuses, priorities, custom AC fields, link types) MUST be configuration, never hardcoded. | T |
| INT-005 | Extraction MUST record what the source says exactly. Acceptance criteria MUST NOT be synthesised at extraction time. | T |
| INT-006 | Every UIF element MUST carry a source reference back to the originating artifact. | T |
| INT-007 | When the same fact differs across sources, both MUST be marked in conflict. Silent reconciliation is prohibited. | T |
| INT-008 | UIF output MUST validate against its schema before write; a validation failure MUST stop the run and report which fields failed. | T |
| INT-009 | UIF MUST NOT contain code samples; it captures business facts, not implementation. | T |
| INT-010 | A UIF document MUST land as an `Episode` whose `raw_content` is human-readable prose rendering, with machine-only scaffolding omitted. | T |
| INT-011 | A `JiraItem` evidence anchor MUST be created for every ingested issue, and MUST remain queryable when its Requirement is rejected, quarantined or unsupported. | T |
| INT-012 | `jira_key` MUST be site-qualified so it is globally unique across Atlassian sites. | T |
| INT-013 | A Story/Epic whose description is not EARS-conformant MUST NOT be landed as a `Requirement`; it MUST be logged as skipped, not force-fit or silently dropped. | T |
| INT-014 | Real Jira parent/subtask/issuelink relationships MUST be represented as `JiraItem`→`JiraItem` edges, distinct from requirement traceability. | T |
| INT-015 | Sync MUST be incremental and resumable, with checkpointing per RES-003. | T |
| INT-016 | Source unreachable or authentication failure MUST stop the run and ask the user to verify credentials — never proceed with partial data silently. | T |
| INT-017 | Jira MUST be the system of record for Requirement, AcceptanceCriterion, BusinessRule, Epic, Feature and Defect, per the precedence table. | I |
| INT-018 | Métis MUST NOT write back to source requirement tickets. Read-only against requirement issues. | T |

## 11.8 MIN — Requirement mining

| ID | Requirement | V |
|---|---|---|
| MIN-001 | Stage 1 segmentation and triage MUST be fully deterministic, with no model calls. | T |
| MIN-002 | Stage 1 MUST classify each block as DIRECT, NEEDS_LLM or DISCARD; discards MUST be counted and carry a reason. Nothing is silently dropped. | T |
| MIN-003 | A block already satisfying the EARS checker MUST short-circuit and never reach a model call. | T |
| MIN-004 | Stage 2 MUST run only on NEEDS_LLM candidates. | T |
| MIN-005 | The source block MUST be passed verbatim to the model — never summarised or paraphrased. | T |
| MIN-006 | The prompt MUST forbid introducing behaviour absent from the supplied block. | I |
| MIN-007 | Every model proposal MUST be re-checked deterministically against the EARS checker and the vagueness checker before becoming a landing candidate. | T |
| MIN-008 | A grounding ratio MUST be computed measuring how much of the proposal's vocabulary occurs in the source. Proposals below threshold MUST be blocked as ungrounded even when perfectly well-formed. | T |
| MIN-009 | A failed proposal MUST be retried once, then recorded as BLOCKED with its reason — never silently dropped, never written anyway. | T |
| MIN-010 | The cost gate MUST be consulted before any batch of model calls; the model MUST come from configuration. | T |
| MIN-011 | Stage 2 MUST NOT write to the graph. Stage 4 MUST own every write, so there is one gated write path. | T |
| MIN-012 | Stage 4 MUST be split into a pure planner and a thin writer, so edge legality is provable without a live database. | T |

## 11.9 GRD — Guardrails

*(Full statements in [06](06-guardrails-quality-governance.md); condensed here.)*

| ID | Requirement | V |
|---|---|---|
| GRD-001 | Every entity/edge MUST carry `source_episode_id` and `source_span`. | T |
| GRD-002 | Structural validation MUST quarantine failures, never auto-create to satisfy a reference. | T |
| GRD-003 | Confidence tiers MUST be applied per the documented thresholds. | T |
| GRD-004 | High-risk entities MUST require ≥2 independent sources or explicit human confirmation before Approved. | T |
| GRD-005 | Temporal and logical contradiction detection MUST run as continuous background processes. | T |
| GRD-006 | The judge MUST receive only source span and claim, and be instructed to answer only from provided text. | I |
| GRD-007 | Human review MUST be a terminal gate with no auto-promotion on timeout. | T |
| GRD-008 | Fabrication and invalid-spec heuristics MUST run deterministically. | T |
| GRD-009 | An adversarial corpus MUST run on a recurring schedule. | T |
| GRD-010 | Rollback MUST close validity and be recorded as an episode. | T |
| GRD-011 | All ten layers MUST be active from Phase 1. | I |
| GRD-012 | `source_span` MUST resolve to real retained content; a non-resolving span is a Critical defect. | T |
| GRD-013 | Provenance fields MUST be excluded from response compression at the guardrail boundary. | T |
| GRD-014 | `auto_write` MUST produce `Draft`, never `Approved`. | T |
| GRD-015 | External confidence MUST be reported on the three-value scale; numeric retained internally. | T |
| GRD-016 | High-risk Approved MUST name the confirming person when human-confirmed. | T |
| GRD-017 | Facts from the same episode or same connector MUST NOT count as independent sources; independence is checked structurally. | T |
| GRD-018 | Lowering the corroboration bar MUST require the full amendment process, not an operational decision. | I |
| GRD-019 | Irreconcilable conflicts MUST produce `Disputed` with both values retained; never auto-resolved. | T |
| GRD-020 | Contradiction detectors MUST run beyond write time. | T |
| GRD-021 | The judge MUST NOT receive the extractor's reasoning, confidence or graph context. | I |
| GRD-022 | The judge model MUST be at least as capable as the extraction model. | I |
| GRD-023 | Per-stage model choice MUST be configuration. | T |
| GRD-024 | No auto-promotion on timeout, ever. | T |
| GRD-025 | Approval MUST require an acknowledgement checklist recorded with approver identity. | T |
| GRD-026 | The reviewer's decision, the reasons shown, and graph state at decision time MUST be recorded. | T |
| GRD-027 | Both EARS and the 29148 characteristic checklist MUST pass at Approved; neither substitutes for the other. | T |
| GRD-028 | All Layer 8 checks MUST be deterministic, never LLM calls. | T |
| GRD-029 | The adversarial corpus MUST cover injection, fabricated traceability, contradictory duplicates, absent API shapes, and EARS-passing/29148-failing requirements. | T |
| GRD-030 | False-acceptance rate MUST be the primary reported safety metric. | A |
| GRD-031 | Nothing MUST be destructively overwritten. | T |
| GRD-032 | The four RPI gates MUST be documented once and referenced, not re-prosed per skill. | I |
| GRD-033 | Human overrides MUST fire a correction episode feeding a counting-based confidence update — never model retraining. | T |

## 11.10 DQ — Data quality

| ID | Requirement | V |
|---|---|---|
| DQ-R01 | DQ-024 MUST be computed against statically-extracted Transitions; against hand-authored only it is unfalsifiable. | T |
| DQ-R02 | Composite weights MUST be configuration, versioned, recalibrated after pilot. | T |
| DQ-R03 | The composite score MUST NOT average out an individual Critical-severity gap. | T |
| DQ-R04 | Metrics MUST be computed on the documented schedule and be queryable by any user. | D |
| DQ-R05 | The full metric catalogue MUST be implemented with formulas matching those documented. | T |
| DQ-R06 | The release gate, weekly trend check and new-source onboarding gate MUST all be implemented. | T |
| DQ-R07 | A new ingestion source MUST NOT receive `auto_write` trust before clearing the onboarding gate. | T |
| DQ-R08 | DQ-001 below 100% MUST be raised as a Critical defect, not a score deduction. | T |

## 11.11 GOV — Governance

| ID | Requirement | V |
|---|---|---|
| GOV-001 | Constitution rules MUST be stored as real nodes and checked ahead of the general rule engine; violations are hard blocks. | T |
| GOV-002 | Critical and High severity MUST block release without a named approver plus recorded justification. | T |
| GOV-003 | Recurring defect patterns MUST feed back into strengthening the governing Article. | I |
| GOV-004 | Every Article MUST name its enforcement point in code and its failure mode if unenforced. | I |
| GOV-005 | CI MUST publish the list of Constitution rules with no referencing enforcement code. | T |
| GOV-006 | Security-relevant paths MUST require negative and boundary cases regardless of overall coverage percentage; this floor MUST NOT be traded against coverage elsewhere. | T |
| GOV-007 | No `BusinessRule` MAY claim a platform-wide compliance basis; each compliance claim MUST cite its own specific verifiable source. | T |
| GOV-008 | Loosening a rule MUST require more recorded justification than adding one. | I |

## 11.12 WFE — Workflow engine

| ID | Requirement | V |
|---|---|---|
| WFE-001 | The same input MUST produce the same workflow route, stage sequence and artifact set regardless of model. | T |
| WFE-002 | Intent MUST be classified against an explicit pattern table before any routing. | T |
| WFE-003 | Ambiguous input MUST present an explicit workflow menu; guessing is prohibited. | T |
| WFE-004 | Each request MUST route to exactly one primary workflow. | T |
| WFE-005 | The manifest MUST be loaded and validated before execution. | T |
| WFE-006 | Every workflow MUST declare code, description, entry prompt and stages; every stage MUST declare ordinal, required artifacts, validation checks and skills. | T |
| WFE-007 | Stage ordinals MUST be unique within a workflow. | T |
| WFE-008 | Stages MUST execute in ordinal order with no skipping or reordering. | T |
| WFE-009 | Skills within a stage MUST execute in declared order; parallelism only where explicitly marked. | T |
| WFE-010 | Skill execution MUST NOT be made conditional on model inference; conditions MUST be declared in the manifest and evaluated from request shape. | T |
| WFE-011 | A failing validation check MUST block advancement; no downstream stage may run. | T |
| WFE-012 | On validation failure the engine MUST NOT attempt recovery, auto-fixing or an alternative path. It reports and blocks. | T |
| WFE-013 | Standalone mode MUST pause with the `[C]/[R]/[B]/[X]` menu after every stage and MUST NOT auto-advance. | T |
| WFE-014 | Chain mode MAY auto-advance, but MUST stop and show the full menu on any validation failure. | T |
| WFE-015 | Stage inputs MUST be graph queries; file artifacts are disposable projections, never the source of truth. | T |
| WFE-016 | Actual stage output not matching declared expected output MUST stop execution and report the mismatch. | T |

## 11.13 SKL — Skills and agents

| ID | Requirement | V |
|---|---|---|
| SKL-001 | Every skill MUST follow the documented folder structure: `SKILL.md` + `steps/` + `knowledge/`, with scripts, resources, configs and tests separate. | I |
| SKL-002 | Always-enforced rules MUST live in `SKILL.md`; supporting detail in `knowledge/`. | I |
| SKL-003 | Agent definitions for every client MUST be generated from one source so client variants cannot drift. | T |
| SKL-004 | A drift test MUST fail when a skill definition and its generated agent disagree. | T |
| SKL-005 | The skill catalogue MUST be discoverable at runtime through a tool call. | T |
| SKL-006 | Presentation-producing skills MUST separate generation logic from templates, versioned independently. | I |
| SKL-007 | Every skill MUST declare when to stop and ask, with explicit conditions. | I |
| SKL-008 | No skill MAY create a competing router; there is one entry point. | I |

## 11.14 CGA — Static code analysis

*(Full statements in [13](13-static-code-analysis-and-behaviour-extraction.md).)*
`REQ-CGA-001` … `REQ-CGA-023`, covering: licence constraint; sidecar isolation;
Episode contract; batch-only execution; report metadata; commit anchoring; query
packs; fixture tests; version pinning; external-stub filtering; framework
configuration; registry-gated generation; code anchors; unresolved source states;
deterministic pre-filter; no auto-write of `VALIDATES`; unmatched-AC findings;
corroboration conditions; corroboration exclusion for unresolved states; impact
path reporting; jQAssistant isolation; jQAssistant exclusion from behaviour
extraction; the pilot gate.

## 11.15 BEH — Behaviour model

| ID | Requirement | V |
|---|---|---|
| BEH-001 | `trigger` and `guard_expression` MUST be properties of a Transition, never separate nodes. | T |
| BEH-002 | Determinism checking MUST compare Transitions by property value across a shared source State, not by shared node identity. | T |
| BEH-003 | Guard atomicity MUST be checked: guards on a shared (State, trigger) MUST NOT overlap. | T |
| BEH-004 | Guard completeness MUST be checked: guards on a shared (State, trigger) MUST jointly cover the domain. | T |
| BEH-005 | Both guard checks MUST be fail-closed — unparseable guards or guards on different variables are flagged unverifiable, never assumed correct. | T |
| BEH-006 | Reachability MUST be checked; unreachable States MUST be reported. | T |
| BEH-007 | `planned` Transitions MUST be excluded from coverage-gap computation. | T |
| BEH-008 | Every `implemented` Transition MUST have ≥1 validating AcceptanceCriterion (DQ-024). | T |
| BEH-009 | An AcceptanceCriterion MUST validate the whole (source state, trigger, guard, target state) scenario, not the target state alone. | T |
| BEH-010 | The behaviour layer MUST be scoped to real application behaviour and MUST NOT be used for generic business workflows or approval processes. | I |
| BEH-011 | A well-formedness failure MUST be surfaced as `Disputed`, never silently resolved. | T |

## 11.16 TST — Test design and functional generation

| ID | Requirement | V |
|---|---|---|
| TST-001 | Every test scenario MUST trace to a requirement; invented scenarios are prohibited. | T |
| TST-002 | Test design MUST name the design technique(s) used. | T |
| TST-003 | Automation viability MUST be classified explicitly per scenario (extend-existing / generate-new / migration-first / duplicate-covered / blocked). | T |
| TST-004 | Blocked and duplicate-covered scenarios MUST NOT be passed to generation. | T |
| TST-005 | Coverage mapping MUST NOT treat ambiguous evidence as covered. | T |
| TST-006 | An equivalent-coverage check MUST run before generation to prevent duplicate tests. | T |
| TST-007 | No class, path, endpoint or field MAY be referenced in generated code without verification that it exists. | T |
| TST-008 | Generated payloads MUST reference only fields present in the CPG-derived registry; a missing field MUST fail the stage, not warn. | T |
| TST-009 | An approval artifact MUST be written and shown before any code generation. | T |
| TST-010 | Generated code MUST pass a compile-only check before the stage passes. | T |
| TST-011 | Generated code MUST carry the configured test-ID annotation linking to its source requirement/test case. | T |
| TST-012 | Test-case drafts MUST be shown in full to the user before any external test-management write. | T |
| TST-013 | No external test-management call MAY occur without a prior explicit affirmative confirmation. | T |
| TST-014 | Generated tests MUST map 1:1 to published test-case identifiers when publishing occurred. | T |
| TST-015 | Every generated `TestCase` MUST verify an `AcceptanceCriterion`, never a `Requirement` directly. | T |
| TST-016 | Test level MUST be one of the six defined values. | T |
| TST-017 | A regression checklist MUST be addressed per endpoint/screen, and blocked items MUST surface as warnings in the preview. | T |
| TST-018 | Evidence status for each source MUST be logged (present / partial / absent); absent evidence MUST downgrade affected items to inferred. | T |

## 11.17 PERF — Performance test generation

| ID | Requirement | V |
|---|---|---|
| PERF-001 | Performance candidates MUST trace to approved business flows; invented candidates are prohibited. | T |
| PERF-002 | SLA targets MUST come from requirements, never inferred from code. | T |
| PERF-003 | Scenarios MUST use provider-backed data selection, never hardcoded data. | T |
| PERF-004 | Identifiers in test data MUST be preserved as strings. | T |
| PERF-005 | Duplicate endpoint or scenario coverage MUST be prevented. | T |
| PERF-006 | Measurement summaries MUST report latency percentiles, failures and regressions explicitly, using normalised status vocabulary. | T |

## 11.18 REV — Code review and merge requests

| ID | Requirement | V |
|---|---|---|
| REV-001 | Review findings MUST be classified Critical / Major / Minor / Info. | T |
| REV-002 | Critical or Major findings MUST block merge-request creation. | T |
| REV-003 | A review verdict is itself a governed AI artifact and MUST carry accountability metadata. | T |
| REV-004 | The MR draft MUST be shown and explicitly confirmed before any remote create/update call. | T |
| REV-005 | AI-authorship analysis MUST be completed and the AI-assistance proportion explicitly requested from the user, not assumed. | T |
| REV-006 | The MR title MUST carry the configured AI-review labelling. | T |
| REV-007 | The system MUST state explicitly whether the AI-review label was applied, created or blocked. | T |
| REV-008 | Review MUST verify that generated tests actually assert the requirement, not merely that they exist. | T |
| REV-009 | Review MUST confirm the absence of hallucinated classes and methods against the verified registry. | T |

## 11.19 DEF — Defect management

| ID | Requirement | V |
|---|---|---|
| DEF-001 | A defect record MUST trace to exact failure evidence, never inferred. | T |
| DEF-002 | Defect drafts MUST be written to a transient location and explicitly confirmed before filing. | T |
| DEF-003 | Defect-derived test cases MUST replicate the exact reproduction steps as preconditions. | T |
| DEF-004 | No invented test conditions MAY be added; all trace to the defect or a linked story. | T |
| DEF-005 | Failed test executions MUST produce a linked `Defect` node. | T |
| DEF-006 | Defect coverage reports MUST state explicitly which scenarios are covered versus pending. | T |

## 11.20 RPT — Reporting

| ID | Requirement | V |
|---|---|---|
| RPT-001 | There MUST be exactly one content-assembly stage shared by all output formats. | I |
| RPT-002 | Rendering to each format MUST be deterministic code, never a second generation pass. | T |
| RPT-003 | Every claim in any rendered output MUST carry a resolvable `source_episode_id`. | T |
| RPT-004 | Rendered output MUST be verified by extracting content back out and checking for missing content, placeholder text and unresolved provenance. | T |
| RPT-005 | Point-in-time deck output MUST NOT be auto-regenerated; staleness there is intentional. | I |
| RPT-006 | The browsable site MUST be regenerated on relevant graph change or a short schedule; it MUST NOT be stale. | T |
| RPT-007 | Reports MUST state explicitly which metrics are confirmed versus pending evidence. | T |
| RPT-008 | Missing evidence MUST be called out explicitly, never silently omitted. | T |
| RPT-009 | A coverage percentage without underlying execution data MUST be treated as a claim, not evidence, and marked as such. | T |
| RPT-010 | Reports MUST use the normalised status vocabulary, never a generic status field. | T |
| RPT-011 | Release readiness MUST be expressed as a deterministic gate status, not a narrative judgement. | T |

## 11.21 ACD — Academy and explainability

| ID | Requirement | V |
|---|---|---|
| ACD-001 | A tool MUST explain the retrieval path behind any prior answer: sources, traversal path, confidence tier per fact. | T |
| ACD-002 | Academy content MUST be versioned alongside the ontology; content describing a non-live schema version MUST fail a test. | T |
| ACD-003 | Every guardrail rejection MUST surface a specific reason linked to the relevant Academy page. | T |
| ACD-004 | Every surfaced gap MUST include a concrete next action, not just a flag. | T |
| ACD-005 | A plain-language changelog of ontology and rule changes MUST be maintained under checkpoint protection. | T |
| ACD-006 | Academy MUST be the only place explanatory content is authored. | I |
| ACD-007 | Explanations MUST be derived from the same provenance data the guardrails already maintain, not a parallel store. | I |
| ACD-008 | Onboarding a new project MUST follow a documented runbook that halts honestly on unimplemented steps rather than faking a pass. | D |

## 11.22 MCP — Tool and API surface

| ID | Requirement | V |
|---|---|---|
| MCP-001 | Read tools MUST ship enabled; the write path MUST ship disabled by default. | T |
| MCP-002 | Every tool MUST have a published input/output JSON Schema, validated as well-formed. | T |
| MCP-003 | Contract tests MUST run against a real subprocess client, not a mock. | T |
| MCP-004 | Traversal depth and retrieval top-k MUST be negotiated per client connection, not fixed platform-wide. | T |
| MCP-005 | Registration MUST differ per client only at the configuration/discovery layer; auth and permissions MUST be identical server-side. | I |
| MCP-006 | The write path MUST remain disabled until the guardrail stack has a production track record. | I |
| MCP-007 | Read-only tool responses MAY be structurally compressed, excluding provenance fields. | T |
| MCP-008 | A CI conformance check MUST be exposed as a required status check, agent-agnostic. | D |
| MCP-009 | Tool errors MUST be explicit and actionable, never a silent empty result. | T |
| MCP-010 | The review API MUST expose queue listing, item detail, and approve/reject with recorded identity. | T |
| MCP-011 | Every tool MUST enforce RBAC scoping; a known node id MUST NOT bypass team scoping. | T |
| MCP-012 | The tool catalogue MUST be discoverable at runtime and MUST match the generated agent definitions. | T |

## 11.23 SEC — Security and data protection

| ID | Requirement | V |
|---|---|---|
| SEC-001 | Authentication MUST use OAuth2 with per-user scoping. | T |
| SEC-002 | Access tokens MUST have a bounded lifetime; refresh tokens MUST be revocable. | T |
| SEC-003 | Tokens MUST be re-validated every request, never cached from issuance. | T |
| SEC-004 | Cross-team access MUST be denied even when a valid node identifier is supplied. | T |
| SEC-005 | A non-interactive token path MUST exist for CI/automation contexts. | T |
| SEC-006 | Episode payloads MUST store references rather than raw secrets or sensitive personal data where the content is sensitive. | T |
| SEC-007 | Sensitivity classification MUST be resolved per repository from configuration and MUST fail closed. | T |
| SEC-008 | Content classified above the configured threshold MUST NOT be sent to an external model. | T |
| SEC-009 | PII flags MUST propagate as access-control tags through derived entities. | T |
| SEC-010 | The audit log MUST itself be access-controlled. | T |
| SEC-011 | Credentials MUST never be written to logs, artifacts, compressed content or generated output. | T |
| SEC-012 | Containers MUST run as non-root with a read-only root filesystem at the container level. | T |
| SEC-013 | Every externally-visible write MUST be attributable to a named identity. | T |
| SEC-014 | A model-provider data-retention posture MUST be recorded in configuration and enforced by the classification gate. | T |

## 11.24 OPS — Deployment and operations

| ID | Requirement | V |
|---|---|---|
| OPS-001 | All components MUST be container images built from committed Dockerfiles. | D |
| OPS-002 | Deployment MUST be by a versioned chart that passes lint and template rendering in CI. | T |
| OPS-003 | Every referenced Kubernetes resource MUST be defined by the chart; a referenced-but-undefined resource MUST fail CI. | T |
| OPS-004 | Environment overrides MUST merge predictably; array-replacement semantics MUST be documented and tested. | T |
| OPS-005 | Backup and restore MUST be exercised, with restore reproducing the graph. | D |
| OPS-006 | Ingestion MUST run as a scheduled worker, never in a request path. | I |
| OPS-007 | Guardrail metrics MUST be exported to the organisation's existing metrics surface, not a parallel dashboard system. | D |
| OPS-008 | Environment drift MUST be verified by infrastructure-as-code diff against committed configuration. | T |
| OPS-009 | Rollback of a bad ingestion run MUST be exercised at least once before production enablement. | D |
| OPS-010 | Cost per unit of ingestion MUST be measured and recorded, replacing any estimate. | A |
| OPS-011 | Runbooks MUST exist for ingestion failure, review-queue backlog, contradiction spike and rollback. | I |
| OPS-012 | Load testing MUST be performed at the documented target load before production enablement. | A |

## 11.25 COST — Token and cost management

| ID | Requirement | V |
|---|---|---|
| COST-001 | Deterministic code MUST be preferred over a model call wherever the task is deterministic; each model call site MUST be justified. | I |
| COST-002 | Structural extraction (AST/CPG, schema parsing, contract parsing, field mapping) MUST be deterministic code. Model calls are reserved for free-text sources. | T |
| COST-003 | Any action triggering a materially larger-than-typical batch MUST show the proposed plan and stage count and require explicit confirmation before starting. | T |
| COST-004 | The pipeline MUST hard-stop on any RPI gate failure or guardrail rejection rather than running a bad batch to completion. | T |
| COST-005 | Bi-temporal fields MUST be normalised before repeated calls so prompt caching can engage. | T |
| COST-006 | Compression MUST never be applied to provenance fields. | T |
| COST-007 | Compression MUST NOT be applied to text that becomes stored specification content. | T |
| COST-008 | Per-stage model selection MUST be configuration so tiers can be swapped without a pipeline change. | T |
| COST-009 | Cost attribution MUST be recorded per episode, enabling "what did this cost to extract" as a property lookup. | T |

---

## 11.26 Verification summary

| Method | Count (approx) | Notes |
|---|---|---|
| **T** — automated test | ~215 | The overwhelming majority. A requirement verified only by inspection is a weaker requirement |
| **D** — demonstration | ~15 | Deployment, installation, runbooks |
| **I** — inspection | ~35 | Design constraints and documentation obligations that cannot be asserted mechanically |
| **A** — analysis | ~5 | Threshold measurements (load, cost, false-acceptance rate) |

`REQ-PLT-000` (above) applies to all of them: no verification artifact, not
satisfied.

## 11.27 Requirements that are deliberately hard

Flagged because they will be under pressure during the build, and conceding any
of them quietly would hollow out the platform:

| ID | Why it will be under pressure | Why it must hold |
|---|---|---|
| GRD-024 | An embarrassing quarantine backlog makes timeout-promotion tempting | The safe failure mode is "nothing approved", not "bad things approved silently" |
| GRD-004 / GRD-017 | Jira-only + static-only makes corroboration genuinely hard | This is the accepted, predicted cost of both scope decisions. Response is reviewer capacity |
| ONT-001 | The four-place rule makes schema change deliberately expensive | That friction is the feature |
| TST-008 | A hard fail on a missing field will block generation runs | It converts the strongest anti-hallucination rule from prose into a check |
| MIN-008 | Grounding-ratio blocks will reject fluent, plausible output | Fluent well-formedness is exactly what a hallucination looks like |
| INT-013 | Skipping non-EARS stories means visibly fewer requirements land | Force-fitting them produces a graph that lies about its own quality |
| CGA-019 | Excluding unresolved-source-state transitions from corroboration reduces an already-scarce resource | A half-recovered transition laundered into a corroboration count is worse than no count |
| CGA-025 | With behaviour-level corroboration deferred (DD-1), matching an endpoint name to an AC by string similarity is the obvious way to manufacture the corroboration the scope decisions removed | It would make the corroboration count meaningless while appearing to solve the scarcity. This is the single most likely place v1 quietly breaks its own central claim |
| DQ-001 / BEH-008 | DQ-024 will read 100% in v1 and look like success | It reads 100% because nothing can make it read otherwise. Publishing it without the qualifier is unearned confidence of exactly the kind the platform exists to prevent |
| SEC-004b | Proving no path *bypasses* scoping is more work than proving scoping works | Without native RBAC (DD-2), this test is the only structural guarantee. One new tool that forgets to scope is how a cross-team leak happens |
