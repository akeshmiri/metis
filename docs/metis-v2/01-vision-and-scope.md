# 01 — Vision, Scope & Principles

## 1.1 Mission

Métis is an **AI-driven specification and quality-engineering platform** whose
single source of truth is an executable, bi-temporal knowledge graph. It ingests
requirements from Jira, extracts specifications from code and API contracts,
models real system behaviour as state machines, generates and maintains
executable tests, and reports quality with an unbroken traceability chain from
business intent to production evidence.

The claim Métis exists to make true, and to be able to prove at any moment:

```
Intent → Requirement → AcceptanceCriterion → Transition (behaviour)
      → TestDesign → TestCase → TestExecution → Release
```

Every link in that chain is a graph edge with provenance, a validity window, a
confidence tier, and a lifecycle state. Nothing in it is a document, a
spreadsheet, or a regenerated per-run artifact.

## 1.2 The two prior systems, and what merging them actually means

The two prior systems solve **adjacent halves of the same problem** and each is
weak exactly where the other is strong.

| Dimension | Métis v1 | Atlas | Métis v2 (this spec) |
|---|---|---|---|
| Persistence | Persistent bi-temporal graph | Per-run artifacts under `.atlas/tmp/` | Persistent graph is authoritative; run artifacts become **derived, disposable projections** of graph state |
| Cross-run memory | Confidence/corroboration compound over time | None — everything re-fetched each run | Graph-backed; a workflow run reads what previous runs established |
| Execution model | Library/MCP calls, no user-facing orchestration | Deterministic manifest-driven stages with confirmation gates | Atlas's engine drives every multi-stage Métis operation, including ingestion and mining |
| Anti-hallucination | 10 persistent guardrail layers, judge, corroboration, contradiction | RPI protocol (Scope Lock → Forbidden Substitutions → Confidence Tagging → Drift Check) within one run | RPI is the *per-run* form; the 10 layers are the *persistent* form. Both run; RPI gates a stage, guardrails gate a write |
| Requirement quality | EARS + ISO/IEC/IEEE 29148 checks, vagueness heuristics | Prose rules in skills | Deterministic checkers, enforced at the write path |
| Test generation | Test *skeletons* from Transitions | Full API/Web/Locust generation with verified schema registry, ISTQB test cases, Zephyr publishing | Atlas's generators, driven from graph-resident TestDesign/Transition data instead of per-run JSON |
| Reporting | Graph-computed quality/release reports, DQ metrics, PPTX/Site | Executive reports from Athena + evidence files | One content-assembly layer over the graph, three renderers (chat, site, deck) plus executive report format |
| Human control | Review queue, lifecycle states | Stage Confirmation Protocol `[C]/[R]/[B]/[X]` | Both: stage gates during work, review queue for graph promotion |
| Onboarding/ops | Helm chart, MCP server, OAuth2/RBAC | Installers, config discovery, plugin registration, Academy | Unified: one config model, one installer, one plugin package, one chart |

**Merging principle:** Atlas contributes the *doing* (deterministic
orchestration, evidence acquisition, generation, review, reporting). Métis v1
contributes the *knowing* (a governed, provenance-backed, temporally correct
model of what is true). Every Atlas skill that previously wrote a JSON artifact
and forgot it now writes to the graph through the guardrail pipeline, and reads
its inputs back from the graph on the next run.

## 1.3 Design principles (normative, referenced throughout)

| # | Principle | Enforced in |
|---|---|---|
| **P1** | **No fact enters the graph without a traceable basis.** Every node and edge carries `source_episode_id` and a `source_span`/evidence field. | §06 Layer 1, §03 schema constraints |
| **P2** | **Temporal truth comes from the source's own recorded timestamp, never ingestion time.** | §04 |
| **P3** | **Every unit of work has a content-derived identity.** No position- or sequence-addressed IDs. | §04.6 |
| **P4** | **Every LLM call must be proven irreplaceable by deterministic code before it is allowed to exist.** | §05.5, §06.2 |
| **P5** | **The system explains itself.** Retrieval, pedagogy, and rejection messages share one provenance substrate. | §09 |
| **P6** | **Determinism of process.** The same input produces the same workflow path, the same stage sequence, and the same artifact set, independent of model. | §07 |
| **P7** | **Conflicts are preserved, never silently reconciled.** Disagreement is first-class data (`Disputed`), not something a run resolves quietly. | §04.4, §06.5 |
| **P8** | **Human confirmation gates every irreversible or externally-visible action** — graph promotion, Jira/Zephyr writes, MR creation, code generation batches. | §06.7, §07.5 |

## 1.4 In scope

- Requirement intake from **Jira** (issues, sub-tasks, epics, links, comments,
  changelog, attachments metadata, custom AC fields), including incremental,
  resumable, changelog-anchored sync.
- Normalisation to the **Unified Intake Format (UIF v2)** and landing as
  immutable `Episode`s.
- Four-stage **requirement mining** (deterministic segmentation → gated model
  extraction → verification → planned graph landing).
- A closed, versioned **ontology** and Neo4j schema with machine-enforced
  structural validation of both node labels and relationship triples.
- A **bi-temporal** model with revision history, point-in-time query, structural
  diff, and auditable rollback.
- A **10-layer guardrail stack**, confidence tiering, corroboration, LLM-as-judge
  grounding checks, contradiction detection, and a human review queue.
- **Behaviour modelling**: State/Transition machines with determinism, guard
  atomicity, guard completeness, reachability and AC-coverage checks.
- **Test design** (technique selection, coverage mapping, automation viability,
  performance candidate classification) and **test generation** (API, Web,
  Locust) with dual-layer hallucination prevention against a verified model
  schema registry.
- **Test-case publishing** to Zephyr Scale, **defect-driven regression**
  generation, **code review** with severity gating, and **merge-request**
  creation with AI-authorship labelling.
- **Reporting**: composite quality score, scoped quality reports, release
  reports, test-design reports, executive reports, static site and PPTX decks.
- **Academy/explainability**, MCP tool surface, REST review API, OAuth2 + RBAC,
  containerised deployment and Helm chart.

## 1.5 The Jira-only intake boundary (explicit)

**Requirement intake** — the pipeline that can create or modify `Requirement`,
`AcceptanceCriterion`, `Intent`, `BusinessRule` and `Defect` nodes — is
implemented **for Jira only**. This is a hard v1 scope boundary, not a default.

Consequences, stated plainly:

1. `IntakeSource` has exactly one registered implementation: `jira`. The
   extractor interface, UIF schema, and Episode contract are source-agnostic
   (§5.9) so a second source is an additive change, but **no Confluence, Zephyr,
   flat-file, DOORS/Polarion, or document-repository intake ships in v1.**
2. Jira is therefore the **unconditional system of record** for
   `Requirement`, `AcceptanceCriterion`, `BusinessRule`, `Epic`, `Feature` and
   `Defect`. The cross-source precedence table (§04.4) still exists and is still
   data-driven, but in v1 it has one row that can win for those entity types.
3. Corroboration (guardrail Layer 4, §06.4) cannot be satisfied by a second
   *requirement* source in v1. High-risk entities therefore reach `Approved`
   either by (a) **explicit, recorded human confirmation**, or (b) corroboration
   from a **non-requirement evidence source**. With dynamic extraction out of
   scope (§1.6) and code analysis limited to structural layers (DD-1), the
   available independent sources in v1 are: an `Endpoint` discovered from code
   and cross-checked against its contract, a `Method` linked by real commit
   evidence naming a Jira key, or a passing `TestExecution`. Behaviour-level
   corroboration is **deferred with §13's Layers 4–5** — see §1.8 for the full
   accounting. This must not be quietly relaxed to "one source is enough". Its
   practical effect is that fewer entities reach `Approved` without explicit
   human confirmation, which is the safe failure direction.

**Evidence acquisition for generation is a different subsystem and is NOT
"intake".** Repository analysis, OpenAPI/Swagger contract reading, database
schema reading, test-suite scanning, Athena/metrics reading and Kubernetes
observation all remain in scope, because Atlas's test generation is unsafe
without them (they are what makes "this DTO/endpoint/class actually exists"
verifiable). They are constrained as follows:

| Subsystem | May create | May NEVER create |
|---|---|---|
| Jira intake (§05) | `Episode`, `JiraItem`, `Intent`, `Requirement`, `AcceptanceCriterion`, `BusinessRule`, `Defect`, `Epic`, `Feature`, `TestDesign` (proposed) | — |
| Repository analyser | `Repository`, `Class`, `Method`, `Endpoint`, `Commit`, `PullRequest`, `Branch`, `IMPLEMENTS`/`CALLS`/`REFERENCES` edges | `Requirement`, `AcceptanceCriterion`, `Intent`, `BusinessRule` |
| OpenAPI/contract analyser | `API`, `Endpoint`, `ExternalAPISpec`, `Service` | as above |
| DB schema analyser | `Database`, `Table`, `Column` | as above |
| Test-suite / CI reader | `TestCase`, `TestSuite`, `TestCycle`, `TestExecution`, `AutomationScript` | as above |
| Metrics / incident reader | `Metrics`, `Logs`, `Alert`, `Incident`, `Release` | as above |

`REQ-INT-001` (§11) states this as a testable rule: a write of a
`Requirement`/`AcceptanceCriterion`/`Intent`/`BusinessRule` whose originating
`Episode.source_connector` is not `jira` MUST be rejected by structural
validation.

## 1.6 Out of scope for v1

Stated so nobody re-derives them as gaps:

- Any second requirement-intake source (see §1.5).
- **Dynamic behaviour extraction** — process mining from event logs (pm4py) and
  active automata learning (LearnLib). Behaviour is recovered **statically only**,
  by state-variable abstraction over a Code Property Graph
  ([13](13-static-code-analysis-and-behaviour-extraction.md)). This is a decision,
  not an oversight; what it costs is tabulated honestly in §13.13 — principally
  no frequency/liveness signal, and no recovery of state that is not explicitly
  represented in source.
- Semantic/vector retrieval mode — the HNSW indexes are created (§03.8) and the
  query path is written, but it refuses to run until an embedding pipeline
  populates `embedding` properties. It does not fall back to keyword search and
  pretend (P5).
- Automatic write-back of generated requirements *into* Jira. Métis reads Jira
  and writes Zephyr test cases, Jira defects and GitLab/GitHub MRs — all behind
  explicit human confirmation — but does not edit source requirement tickets.
- Multi-tenant hosting. Single-tenant deployment with team-scoped RBAC only.
- Selecting a graph-database vendor contract, or authoring an organisation's
  actual Constitution rule content (the mechanism is specified; the content is
  the adopting organisation's).

## 1.7 Resolved decisions

All open decisions are now closed. Six were resolved from evidence in the prior
systems; four were decided explicitly. Each is recorded with its consequence, so
a later reversal is a visible change rather than a rediscovery.

### Resolved from evidence in the prior systems

| # | Decision | Resolution | Evidence |
|---|---|---|---|
| RD-1 | **Primary language** | **Java.** Feign for API tests, Selenium + TestNG for web | Atlas generators: 105 `.java`, 103 Feign, 21 Selenium, 12 TestNG references; `mvn compile` build check |
| RD-2 | **Jira flavour** | **Jira Server / Data Center**, not Cloud. PAT auth, `/rest/api/2` | `atlassian.template.json` |
| RD-3 | **Test management** | **Zephyr Scale (Server/DC)**, `/rest/atm/1.0` | `scale_token` in the same template |
| RD-4 | **VCS** | **GitLab primary** (merge-request terminology, `.gitlab-ci.yml`); GitHub supported | Both `gitlab.template.json` and `github.template.json` present |
| RD-5 | **Model tiers** | Extraction `claude-haiku-4-5`, judge `claude-sonnet-5` | Already configured; satisfies `REQ-GRD-022` (judge ≥ extractor) |
| RD-6 | **Model-vendor retention posture** | **No ZDR agreement; fail-closed classification gate.** A recorded decision with a procurement checklist, not a stalled task | `zdr.confirmed: false` plus the CONST-053 record |

### Decided explicitly

| # | Decision | Resolution | Consequence — stated, not implied |
|---|---|---|---|
| DD-1 | **Code-analysis scope** | **Joern, structural layers only** (Layers 1–3: code structure, endpoint discovery, verified type registry). State-transition extraction and AC↔Transition matching are **deferred** | Retires ~11k LOC of repository scanning and v1's `cognify/`, and makes the verified type registry mechanical. **But: no code-derived `Transition`s in v1** — see §1.8 |
| DD-2 | **Graph engine** | **Neo4j Community only.** Revisit only if production adoption happens | No clustering, no online backup, no native RBAC, and **only one database per instance**. §10.1's availability target moves out of scope; RBAC becomes application-level (§10.2) |
| DD-3 | **Jira access for build** | **Cached export of real tickets**, including full changelog | Real data shapes and reproducible tests, with no credentials required. Incremental-sync and rate-limit behaviour are built but **only partially verifiable** (§05.10) |
| DD-4 | **External writes** | **None in v1.** Generate locally; draft only | Test-case publishing, MR creation and defect filing are implemented and gated, but exercised only against stubs. Confirmation-gate *negative* tests remain fully verifiable (§08.7) |
| DD-5 | **Compliance regime** | **None formally asserted** — every compliance-tagged `BusinessRule` must cite its own specific, verifiable source | Stricter than naming a regime: it stops individual rules inheriting unverified authority from a platform-wide claim |
| DD-6 | **Constitution amendment authority** | Provisional single owner | Revisit at multi-team adoption; a single point of failure by construction |
| DD-7 | **Target load** | 15 concurrent sessions × 3 headroom; 50,000-episode backfill burst | An engineering estimate from stated assumptions, **not an observed fact.** First number to replace with pilot data |
| DD-8 | **Test-ID annotation** | Configurable per repository; default `@TestId` | With DD-4, no published test-case identifiers exist in v1, so `REQ-TST-014`'s 1:1 mapping is conditional on publishing being enabled |

## 1.8 The one consequence worth stating plainly

DD-1 removes the last independent corroborating source for *behaviour*.

Three scope decisions compound here, and it is worth seeing them together rather
than discovering the interaction during Phase 5:

| Decision | Removes |
|---|---|
| Jira-only intake (§1.5) | A second **requirement** source |
| Static-only behaviour (§1.6) | Runtime/observed behaviour as evidence |
| Structural-layers-only code analysis (DD-1) | Code-derived **`Transition`s** |

**What survives as independent corroboration** — and this is genuinely enough to
proceed with, which is why this is a note and not an objection:

- `Endpoint`s discovered from code and cross-checked against the contract
  (Layer 2 is **in** scope).
- `Method`s linked by real commit evidence naming a Jira key (Layer 1 is **in**
  scope).
- Passing `TestExecution`s from CI.

**What is genuinely lost in v1:**

- **DQ-024 stays unfalsifiable.** With `Transition`s only ever hand-authored,
  "implemented behaviour with no acceptance criterion" cannot be computed
  honestly — the same person writes both sides. The report I would have called
  this platform's most valuable output is deferred, not delivered.
- Behaviour-level corroboration (`AcceptanceCriterion -[:VALIDATES]-> Transition`
  against real code) is unavailable, so more high-risk entities will require
  explicit human confirmation to reach `Approved`.

Neither is a reason to change course. Both are reasons to (a) staff the review
queue deliberately from Phase 3, and (b) treat §13's deferred Layers 4–5 as a
funded follow-on rather than a stretch goal that quietly never happens.

## 1.8 Glossary

| Term | Definition |
|---|---|
| **Episode** | The atomic, immutable ingestion unit — one raw event/document fragment, retained forever, from which entities are extracted. Never deleted, even after extraction. |
| **UIF** | Unified Intake Format — the single normalised JSON shape every intake extractor produces (§05.3). |
| **Cognify** | The extraction stage where structure is proposed from an Episode, gated by structural validation before any write. |
| **Bi-temporal edge** | A relationship carrying `t_valid`/`t_invalid` (when the fact was true) separate from `t_recorded`/`t_ingested` (when it was captured). |
| **Lifecycle state** | `Draft → Reviewed → Approved → Deprecated`, plus `Disputed` and `Rejected`. |
| **Confidence tier** | `auto_write` / `quarantine` / `rejected` — the autonomy level granted to an extracted fact. |
| **Constitution** | The highest-precedence, human-authored rule set, checked before all other validation. A Constitution violation is a hard block, never a soft flag. |
| **EARS** | Easy Approach to Requirements Syntax — five sentence patterns used as a deterministic requirement-quality gate. |
| **RPI** | Research / Plan / Implementation — the four-gate per-run anti-hallucination protocol (Scope Lock, Forbidden Substitutions, Confidence Tagging, Drift Check). |
| **Stage Confirmation Protocol** | The `[C]ontinue / [R]eview / [B]ack / [X]it` gate presented between workflow stages. |
| **Chain mode** | A multi-workflow run triggered by a `generate …` intent that auto-advances between stages, stopping only on a validation failure. |
| **unit_id** | A content-derived identifier making every write idempotent and every batch resumable. |
| **Delta marker** | `ADDED` / `MODIFIED` / `REMOVED` on any edit episode. |
| **Memify** | The feedback loop that retunes default extraction confidence from accumulated human corrections. |
| **Pinned core memory** | A small, always-in-context set of high-risk constraints/incidents per service, never reranked out. |
| **Sleep-time agent** | A scheduled background consolidation process that never touches the live request path. |
| **Quarantine** | The holding state for facts that pass structure but not confidence — visible, queryable, non-authoritative, awaiting human decision. |
