# 12 — Implementation Plan & Acceptance Criteria

## 12.1 The single most important framing: this is not a greenfield build

Measured directly from both working trees, not estimated:

| Asset | Métis v1 | Atlas |
|---|---|---|
| Production Python | **13,070 LOC** across 51 `metis_mcp` modules, 11 connectors, 4 guardrail modules | **61,122 LOC** across 195 files in 30 skills |
| Tests | **9,477 LOC** across 62 test files | embedded per skill |
| Prose assets | 17 design docs, 3 Cypher schema files, 8 connector manifests | 353 markdown files (30 `SKILL.md` + steps + knowledge), 11 agent definitions, 1 workflow manifest (873 lines) |

Roughly **74k LOC of working code already exists**. The implementation plan is
therefore a **port-and-integrate plan with targeted new build**, not a rewrite.
Treating it as greenfield would be the single most expensive mistake available.

### The reuse ledger (grounded in the measurements above)

| Disposition | Asset | LOC (approx) | Rationale |
|---|---|---|---|
| **Carry forward, near-intact** | Métis `metis_mcp/` core — ontology validation, temporal, EARS, vagueness, behaviour model, DQ metrics, confidence tiering, guardrail pipeline, MCP server, OAuth2/RBAC, renderers | ~13,000 | Already tested against a real graph. This *is* the platform core |
| **Carry forward, near-intact** | Métis test suite | ~9,500 | The regression discipline is an asset in its own right; do not restart it |
| **Port selectively** | Atlas `shared/` — config provider, artifact validation, functional-area catalog/spec-pack, schema inventory | ~13,800 → keep maybe 60% | Real infrastructure. Config discovery and artifact validation map directly onto §07's manifest engine |
| **Port selectively** | Atlas `test-developer/` incl. `generate_feign_interfaces.py` (3,222 LOC) | ~4,800 | Genuine generators with no equivalent in v1. Rebind inputs from JSON files to graph queries |
| **Port selectively** | Atlas `merge-request-creator/`, `locust-workflow/`, `bug-reporter/`, `code-reviewer/`, `test-case-reporter/` (Zephyr client) | ~5,800 | Real external-system integrations; keep the clients, replace the orchestration |
| **Port the Jira path only** | Atlas `intake-processor/` | ~3,100 → keep ~30% | Jira-only intake (§01.5). The Confluence/Swagger/Scale/code/database extractors are **not built** in v1 |
| **Retire — superseded by Joern** | Atlas `git-repository-analyzer/` (`analyze_repositories.py` alone is 5,281 LOC) | ~11,000 | §13 replaces hand-rolled repository scanning with a CPG. Keep only the clone/checkout helper |
| **Retire — superseded by Joern** | Métis `cognify/structural_extraction.py` + `code_graph_archaeology.py` | ~380 | §13.5 |
| **Retire — superseded by the graph** | Atlas `business-analyzer/render_business_analysis.py` (7,969 LOC) and the document-rendering chain around it | ~10,000 | A persistent graph replaces a regenerated markdown dossier. This is the core Métis-v1-vs-Atlas thesis (§01.2); keeping both is keeping two sources of truth |
| **New build** | Joern sidecar + query packs + ontology mapper (§13); workflow-manifest engine bound to the graph; graph-backed replacements for Atlas's per-run JSON handoffs; AC↔Transition matcher | — | The genuinely new surface |

**Net:** roughly **21k LOC retired**, **13k carried forward intact**,
**~28k ported with rebinding**, plus the new integration surface. Anyone
proposing a from-scratch build should be asked to justify discarding the 9,477
LOC of passing tests first.

## 12.2 Guiding constraints on how the work is sequenced

| # | Constraint | Why |
|---|---|---|
| C1 | **Walking skeleton first.** Phase 1 ends with one real Jira ticket landing as an `Episode`, becoming a `Requirement`, and being queried back through an MCP tool | Prevents months of horizontal layer-building with nothing demonstrable |
| C2 | **Every phase ends in something a user can run**, not a library that compiles | Each exit criterion below is a command with an observable result |
| C3 | **Guardrails are active from Phase 1, not phased in** | Retrofitting a write path onto an ungated one is the most common way this class of system fails. v1 already learned this |
| C4 | **Nothing auto-writes until Phase 8.** Everything lands at Quarantine | CONST-016; the write path earns trust with a track record |
| C5 | **Vertical slices over horizontal layers.** Each phase cuts through storage → logic → tool surface | |
| C6 | **The regression suite never goes red between phases.** A phase that leaves it red is not complete | Carried forward from v1's working practice |
| C7 | **Wipe and regenerate demo data after any graph-affecting change**, as part of finishing the change | Standing practice adopted in v1 Session 13; not optional |

## 12.3 Phase plan

### Phase 0 — Bootstrap and decisions

**Goal:** a repository that builds, and the six open decisions closed or
explicitly deferred with an owner.

Work packages:
- P0.1 Repository skeleton, packaging, CI, lint/format, dependency pinning.
- P0.2 Disposable Neo4j test harness (carry forward v1's `neo4j_test_support.py` —
  it already stands up a container, applies schema, and force-removes at session end).
- P0.3 Configuration model: single resolution path, no configuration in code,
  server refuses to start unconfigured (carry forward v1's `config_manager.py`
  contract; fold in Atlas's 3-level discovery).
- P0.4 **All scope decisions are closed** (§01.7: RD-1…RD-6 resolved from
  evidence, DD-1…DD-8 decided). P0.4 is now a *verification* step: confirm each
  recorded decision is reflected in configuration — Java frontend selected,
  Community edition assumed, cached export curated, external writes stubbed —
  rather than a decision-making step. **One input remains open: team composition,
  specifically JVM capability for the Joern query packs and Java generators.**

**Exit criteria:** `pip install -e .` succeeds from a clean checkout; the test
harness starts and tears down Neo4j; the server refuses to start with no config
and starts with one; every OD has a named owner or a recorded decision.

---

### Phase 1 — Graph core + walking skeleton

**Goal:** the ontology is enforced, time is modelled, and one real Jira ticket
makes it end-to-end.

Work packages:
- P1.1 Ontology and schema: node labels, relationship catalogue, constraints and
  indexes (§03). Port v1's three Cypher files and `structural_validation.py`
  (`KNOWN_LABELS` + `ALLOWED_RELATIONSHIPS`, node **and** edge validation).
- P1.2 Ontology governance in CI: the four-place rule (schema-01, schema-02,
  `structural_validation.py`, ontology doc) enforced by a test that fails when
  the four disagree.
- P1.3 Temporal model: four timestamps, bi-temporal edges, `record_revision()`,
  `as_of`/`history`/`diff`, rollback (§04). Port v1's `temporal.py`.
- P1.4 Idempotency and resumability: `unit_id` derivation, `delta_type`,
  `checkpoint_status`, the resume algorithm (§04.6).
- P1.5 **Walking skeleton:** minimal Jira client → `Episode` → `JiraItem` →
  `Requirement` → `metis_get_context` returns it.

**Exit criteria:**
1. A candidate with an unknown label, or a relationship triple absent from
   `ALLOWED_RELATIONSHIPS`, is **rejected**, with a test proving it.
2. The four-place governance test fails when any one of the four is edited alone.
3. `as_of(entity, t)` reconstructs a prior state; `diff` reports the change;
   rollback closes `t_valid` and is itself recorded as an episode.
4. Re-running the same ingestion twice produces **zero** duplicate nodes.
5. `metis_get_context` returns a real requirement traced to a real Jira key.

**Retires:** nothing yet.

---

### Phase 2 — Jira intake and requirement mining

**Goal:** the only intake source, built properly.

Work packages:
- P2.1 Jira client: auth, pagination, rate limiting, **changelog API** (never
  poll-and-diff — `t_recorded` is the changelog entry's own timestamp, §04).
- P2.2 Field mapping as configuration: issue types, statuses, priorities, custom
  AC fields, link types (port Atlas's `jira-extractor.yaml` shape).
- P2.3 UIF v2 schema and the Jira→UIF extractor (port Atlas's `jira_extractor.py`;
  keep the "FACTS before SPECIFICATIONS" and "conflict marking, not
  reconciliation" hard rules verbatim).
- P2.4 UIF → `Episode` landing (port v1's `uif_intake.py`, including its
  markdown-rendering decision — serialising raw JSON hands Stage 1 punctuation).
- P2.5 Four-stage mining: deterministic segmentation → gated model extraction →
  verification (EARS + vagueness + grounding ratio) → planned landing
  (port v1's `intake_segmentation`/`requirement_mining`/`requirement_landing`).
- P2.6 Incremental, resumable sync with checkpointing; `JiraItem` evidence anchors
  that survive their Requirement being rejected.

**Data source (DD-3): a cached export of real tickets**, not a live connection.
P2.7 is therefore a work package in its own right — curating an export that
satisfies `REQ-INT-019` (full changelog) and `REQ-INT-020` (contains a bulk edit,
a reopened issue, an AC in a non-standard location, an unmapped issue type, and a
non-EARS story). An export of only well-formed tickets tests the happy path and
nothing else.

**Exit criteria:**
1. A full sync over the export runs, is **interrupted with SIGKILL**, resumes, and
   produces a graph byte-identical to an uninterrupted run.
2. `t_recorded` on every derived node equals a real changelog timestamp;
   **no node carries an ingestion-time-derived `t_recorded`** (asserted by test).
3. A simulated bulk edit does **not** collapse history to one moment.
4. A non-EARS-conformant Story is **not** landed as a `Requirement` — logged as
   skipped, with its `JiraItem` still present and queryable.
5. A mined requirement below the grounding-ratio threshold is BLOCKED with a
   recorded reason, never written.
6. A `Requirement` write attempt from a non-`jira` connector is rejected
   (`REQ-INT-001`).
7. The phase exit record **explicitly lists** rate-limit backoff, auth-failure
   handling, real pagination boundaries and live cursor advance as
   **implemented but unexercised against a live instance** (`REQ-INT-022`).
   These are not reported as verified.

---

### Phase 3 — Guardrails, review queue, quality and governance

**Goal:** the write path is trustworthy and measurable.

Work packages:
- P3.1 The ten layers end-to-end (§06): grounding, structural validation,
  confidence tiering, corroboration, contradiction detection, LLM-as-judge,
  human review, fabrication heuristics, adversarial corpus, auditable rollback.
- P3.2 Review queue + reviewer API/UI (port v1's `review_api_server.py` and the
  queue UI).
- P3.3 DQ metric catalogue and the composite quality score, with the three gate
  points (release / weekly trend / new-source onboarding).
- P3.4 Constitution gate — hard block ahead of the general rule engine.
- P3.5 Cost gate: explicit plan-and-confirm before any materially-larger batch;
  model choice from config, never a literal.

**Exit criteria:**
1. A deliberately planted prompt-injection document is **quarantined, not
   accepted**, from the adversarial corpus.
2. A high-risk entity with one source **cannot** reach `Approved` without a
   recorded human confirmation.
3. Two contradicting facts produce a `Disputed` state and a
   `ContradictionDetected` episode — neither is silently dropped.
4. `metis_quality_score` returns a real composite number with a per-metric
   breakdown over real ingested content.
5. An unreviewed quarantine item **never** auto-promotes, including after an
   arbitrary elapsed time (explicit negative test).

---

### Phase 4 — Workflow engine, agents and skills

**Goal:** Atlas's determinism, rebound to the graph.

Work packages:
- P4.1 Workflow manifest schema + validator (port Atlas's determinism validator;
  extend it to fail on missing `required_artifacts`/`validation_checks`).
- P4.2 Stage engine: ordinal execution, per-stage validation gates, fail-fast with
  no auto-recovery, artifact path contract.
- P4.3 Stage Confirmation Protocol `[C]/[R]/[B]/[X]`; standalone vs chain mode;
  chain mode stops on any validation failure.
- P4.4 Deterministic intent router with an explicit menu on ambiguity — never a
  guess.
- P4.5 **Rebind handoffs from files to the graph**: stage inputs are graph
  queries; `.atlas/tmp`-style JSON becomes a disposable projection, not the
  source of truth.
- P4.6 Agent/skill catalogue generated from one source so client variants cannot
  drift (carry forward v1's `agent_generator.py` + `skill_catalog.py` drift tests).

**Exit criteria:**
1. The same input produces an **identical stage sequence and artifact set across
   two different models** (Atlas's own cross-model determinism test, kept).
2. A failing `validation_check` blocks advancement and no downstream stage runs.
3. Chain mode auto-advances, and **stops** on an injected validation failure.
4. Skill catalogue drift test fails when a `SKILL.md` and its generated agent
   disagree.

---

### Phase 5 — Static code analysis (Joern, structural layers only — DD-1)

**Goal:** code becomes a structural evidence source and the anti-hallucination
substrate for generation. Full design in
[13](13-static-code-analysis-and-behaviour-extraction.md).

Work packages:
- P5.1 Joern sidecar: pinned version, CPG build/verify/retain/expire keyed by
  `(repo, commit_sha)`. Java frontend (`javasrc2cpg` / `jimple2cpg`, RD-1).
- P5.2 Query-pack framework with fixture tests asserting exact expected output.
- P5.3 **Layer 1** structural extraction — replaces `cognify/`.
- P5.4 **Layer 2** endpoint discovery + contract drift cross-check.
- P5.5 **Layer 3** verified type/member registry.
- P5.6 Impact analysis via reachability.
- P5.7 Add `Transition.extraction_method` and populate it as `hand_authored`
  (§13.8) — one property now, so the Layer 4 follow-on is a pure addition rather
  than a backfill.

**Deferred to a funded follow-on (DD-1), not descoped:** Layer 4 state-transition
extraction and Layer 5 AC↔Transition matching. Neither Layers 1–3 nor anything
downstream depends on them, so deferral costs no rework.

**Exit criteria:** the **v1 pilot gate** of §13.14 passes on one real Java
service — eight criteria, of which the two that justify the phase are:
(1) structural extraction is a **strict superset** of v1's `cognify/` output with
zero regressions, and (2) **cross-file call resolution is materially non-zero**
against calls v1's bounded resolver could not resolve. If (2) is weak, the port
buys multi-language support and little else — worth knowing before, not after.

**Retires:** ~11k LOC of `git-repository-analyzer` and v1's `cognify/`.

**Does not deliver:** code-derived `Transition`s, behaviour-level corroboration,
or a falsifiable DQ-024 (§01.8).

---

### Phase 6 — Test design, generation and SDLC integration

**Goal:** the output side — tests, publishing, review, merge.

Work packages:
- P6.1 Test design: technique selection, coverage mapping, automation-viability
  and performance-candidate classification, driven from graph `TestDesign`.
- P6.2 API + Web functional generation (port Atlas's generators), with
  `REQ-CGA-012` as a hard generation-stage gate — a field absent from the
  CPG-derived registry **fails** the stage.
- P6.3 Zephyr Scale publishing behind a mandatory preview-and-explicit-yes gate.
- P6.4 Locust performance generation.
- P6.5 Code review with Critical/Major/Minor/Info severity gating; MR creation
  with AI-authorship labelling, behind confirmation.
- P6.6 Defect-driven regression generation.

**External writes: none (DD-4).** Test-case publishing, MR creation and defect
filing are implemented behind their confirmation gates and exercised **against
stubs only**. Drafts are written locally. This changes what can be proven:

| Behaviour | Verifiable in v1? |
|---|---|
| Confirmation gate blocks the call when confirmation is withheld | ✅ — it is a *negative* test; a stub proves it completely |
| Draft content is shown in full before any action | ✅ |
| Generated code compiles | ✅ |
| Registry gate fails the stage on an unverified field | ✅ |
| Traceability through an AC, never a Requirement | ✅ |
| The *positive* path — a real test case, MR or defect is actually created | ⛔ Stub only |
| `REQ-TST-014` 1:1 mapping to published identifiers | ⛔ Conditional — no published IDs exist |

**Exit criteria:**
1. Generated code **compiles** (`mvn compile` for the Java stack, RD-1) before
   the stage passes.
2. A generated payload referencing a field not in the verified registry **fails
   the stage** — negative test.
3. Withholding confirmation produces **zero** external calls — negative test
   against a stub that records every attempted call.
4. Every generated `TestCase` traces to an `AcceptanceCriterion`, never directly
   to a `Requirement` (DQ-018 stays at zero).
5. The exit record lists the positive external-write paths as **implemented,
   stub-verified, unexercised against a real target.**

---

### Phase 7 — Reporting, Academy and the API surface

**Goal:** the system explains itself and reports on itself.

Work packages:
- P7.1 One content-assembly layer; three renderers (interactive, static site,
  PPTX) — never three content authors.
- P7.2 Scoped quality reports, release reports, test-design reports, executive
  report format.
- P7.3 Academy content versioned alongside the ontology; every guardrail
  rejection links to the page explaining it.
- P7.4 Full MCP tool surface + REST API; per-client context budgets.

**Exit criteria:**
1. Every claim on a generated deck or page carries a `source_episode_id` —
   asserted by extracting content back out and checking (v1's own content-QA pass).
2. Academy content describing a non-live schema version fails a test.
3. A guardrail rejection message names a specific reason and links to a real page.
4. MCP contract tests pass against a real subprocess, not a mock.

---

### Phase 8 — Hardening, deployment and scale

Work packages: containers and chart; OAuth2 token lifecycle; **application-level
RBAC choke point** (`REQ-SEC-004a`, required because Community has no native RBAC
— DD-2); offline backup and restore drill (`REQ-OPS-005a`); adversarial corpus as
recurring governance; load test at the §10.1 target on a **single instance**;
runbooks.

**Exit criteria:**
1. A cross-team access attempt is denied **even with a known node id**.
2. A test proves **no query path bypasses the scoping choke point**
   (`REQ-SEC-004b`) — stricter than proving scoping works.
3. An offline backup is restored and **reproduces the graph**.
4. The adversarial false-acceptance rate is measured and recorded.
5. A real cost-per-1,000-episodes figure **replaces the estimate**.
6. Rollback is exercised on a deliberately introduced bad fact.
7. The exit record states the accepted data-loss window (equal to the backup
   interval) and that no HA target was tested, because none exists under DD-2.

## 12.4 Critical path and parallelisation

```
P0 ──► P1 ──┬──► P2 ──► P3 ──┬──► P5 ──┐
            │                 │         ├──► P6 ──► P7 ──► P8
            └──► P4 ──────────┴─────────┘
```

- **P1 is the hard serialisation point.** Nothing meaningful parallelises before
  the ontology and temporal model are fixed, because everything writes through them.
- **P4 (workflow engine) can run in parallel with P2+P3** once P1 lands — it
  depends on the graph existing, not on intake being complete.
- **P5 depends on P3**, not P2: code analysis must land through a working
  guardrail pipeline, but does not need Jira intake finished.
- **P6 is the widest phase and the most parallelisable** (API generation, Web
  generation, Locust, review/MR, defect flow are five largely independent tracks).
- **P7 depends on P3** for metrics and **P6** for content worth reporting.

## 12.5 On schedule and staffing

This plan is deliberately expressed in **phases, work packages and testable exit
criteria — not dates or headcount.** Three of the four inputs that determine
calendar time are now settled (RD-1 Java; DD-3 cached export; DD-4 no external
writes). **One remains open: team size and composition**, in particular whether
there is JVM capability for the Joern/CPGQL query packs and the Java generators.

Relative sizing, for planning purposes only: P1 and P3 are the two substantial
phases; **P5 is materially smaller than originally scoped** — Layers 4–5 were the
majority of its difficulty and are deferred (DD-1). P2 and P4 are medium and
heavily port-driven; P6 is wide but shallow per track, and **shallower still**
without live external writes (DD-4). P0, P7 and P8 are small-to-medium.

### What the conservative decisions removed from the plan

| Decision | Removed from scope | Added to scope |
|---|---|---|
| DD-1 Layers 1–3 only | Six-step transition extractor, AC↔Transition matcher, five of the pilot-gate criteria | One property (`extraction_method`) so the follow-on is additive |
| DD-2 Community | Clustering, HA, native RBAC configuration, second-database CPG browsing | **Application-level RBAC choke point + bypass test** — net *more* work |
| DD-3 Cached export | Live credential provisioning, rate-limit handling verification | **Export curation** (`REQ-INT-019`/`020`) — a real work package |
| DD-4 No external writes | Live publishing, MR and defect integration verification | Stub harnesses that record attempted calls |

Two of the four therefore reduce effort; two shift it. DD-2 is the only one that
increases net risk.

## 12.6 Test strategy

Carried forward from v1's working practice, which already caught three real
classes of bug this way:

| Level | Rule |
|---|---|
| Unit | Pure functions tested without a database — planners, validators, EARS/vagueness checkers, the landing planner (ontology legality provable without Neo4j) |
| Integration | Real disposable Neo4j per session; schema applied; force-removed at teardown. Tests never touch a deployed config |
| Contract | MCP tools tested through a **real subprocess client**, not a mock |
| Determinism | Same input, two models, identical stage sequence and artifacts |
| Adversarial | Held-out corpus with known-correct reject/quarantine outcomes; primary metric is **false-acceptance rate**, not accuracy |
| Cost-bearing | Model-calling tests exist, are real, and are **excluded from routine runs** — run explicitly |
| Regression | The full suite is green at every phase boundary (C6) |

**Non-negotiable practice:** when a component is built, run it for real and check
a **specific, verifiable output**. Confirming it imports without crashing is not a
test. Every one of v1's three known historical bugs — the alphabetical-order
attribution error, the silently dropped cross-references, and the broken
`pyproject.toml` — was found this way and would not have been found by review.

## 12.7 Cutover from the two prior systems

| Step | Action |
|---|---|
| 1 | Métis v1 and Atlas keep running unchanged until Phase 6 completes. No big-bang switch |
| 2 | From Phase 2, Jira intake runs in **shadow** — the new graph is populated, but v1 remains the surface people use |
| 3 | From Phase 4, workflows run against the new engine for **one pilot team**, with the Atlas router still available as a fallback |
| 4 | Atlas's `git-repository-analyzer` is retired only after §13.14's pilot gate passes — not before, and not on schedule pressure |
| 5 | Atlas's document-rendering chain is retired when Phase 7's renderers reach parity on the reports people actually use — verify that empirically, don't assume the list |
| 6 | v1's graph content is **re-ingested, not migrated.** Provenance is the whole point; copying nodes without their originating episodes would violate P1 on day one |

## 12.8 Risk register with named triggers

| Risk | Trigger that means it has materialised | Response |
|---|---|---|
| Joern cannot recover usable state machines | §13.14 pilot fails criteria (1)–(5) | Escalate to SootUp+IFDS if Java-only; otherwise reduce Phase 5 scope to Layers 1–3 (structural + endpoints + registry), which are independently valuable, and keep behaviour hand-authored |
| Corroboration becomes unsatisfiable | >40% of high-risk entities stuck awaiting human confirmation after Phase 5 | This is the predicted cost of Jira-only + static-only (§01.5). Response is reviewer capacity, **not** lowering the bar |
| Reviewer bottleneck | Quarantine queue grows for 3 consecutive weeks | Budget reviewer time explicitly; note the safe failure mode is "nothing gets approved", not "bad things get approved" |
| Port cost of Atlas's 61k LOC underestimated | Any single skill port exceeds twice its estimate | Retire rather than port. The retire list (§12.1) is already ~21k LOC; extend it before extending the schedule |
| Ontology churn late in the build | Any schema change after Phase 5 that touches `Transition` or `Requirement` | The four-place governance test makes churn visible and expensive by design — that is intended friction, not an obstacle to remove |
| Single-instance graph proves insufficient | An incident where downtime or a backup-interval data loss actually costs something | DD-2 accepted this knowingly. Enterprise is the escalation, in §12.10's follow-on backlog |
| **Application-level RBAC leaks across teams** | Any query path found that bypasses the scoping choke point | The highest-severity risk DD-2 introduced. `REQ-SEC-004b`'s bypass test is the only structural guarantee — treat a failure as Critical, not as a bug |
| **Corroboration manufactured by name matching** | Any code linking an `Endpoint` to an AC by string similarity | `REQ-CGA-025`. With behaviour-level corroboration deferred, this is the most likely way v1 quietly breaks its own central claim |
| Joern version churn breaks query packs | A Joern upgrade fails pack tests | Version is pinned per pack (`REQ-CGA-009`); upgrades are reviewed changes, never incidental |

## 12.9 Definition of done for v1

Each is checkable; none is a judgement call.

1. Every node and edge carries a resolvable `source_episode_id`. (DQ-001 = 100%)
2. `metis_quality_score` returns a real composite over real content, and the
   release gate blocks below threshold.
3. A ticket change in the export is reflected with correct `t_recorded`, a new
   `Revision`, and no duplicate nodes.
4. An acceptance criterion traces through to a `TestCase` that verifies it, and
   to an `Endpoint` or `Method` derived from a CPG at a named commit.
5. A deliberately bad fact is caught, quarantined, and — if force-introduced —
   rolled back with the rollback itself recorded.
6. No query path bypasses the RBAC choke point (`REQ-SEC-004b`).
7. An offline backup restores and reproduces the graph.
8. Cost per 1,000 episodes is a **measured** number, not an estimate.
9. The generic write path remains disabled, per CONST-016.

### Explicitly NOT part of v1's definition of done

Recorded here so their absence is a decision rather than a shortfall discovered
at acceptance:

| Not delivered | Because |
|---|---|
| An acceptance criterion tracing to a **code-derived `Transition`** | DD-1 |
| **DQ-024 listing real implemented behaviour with no acceptance criterion** — the platform's highest-value report | DD-1. Reported in v1 with the mandatory qualifier that it measures modelling discipline, not real coverage (`REQ-DQ-001`) |
| Live Jira sync verified end-to-end | DD-3 |
| A test case, MR or defect actually created in an external system | DD-4 |
| Any HA or failover behaviour | DD-2 |

## 12.10 The follow-on backlog

Not a wish list — the specified, costed work these decisions deferred. Each has a
trigger that should prompt revisiting it.

| Item | Trigger to revisit |
|---|---|
| §13 Layers 4–5 (transition extraction, AC matching) | The first time someone asks "what behaviour has no acceptance criterion?" and the honest answer is "we cannot tell" |
| Live Jira connection | Before v1 goes to anyone who expects the graph to be current rather than a snapshot |
| External write enablement | When a reviewer starts hand-copying generated test cases into Zephyr |
| Neo4j Enterprise | The first incident where single-instance downtime or a backup-interval data loss actually costs something |
| Dynamic behaviour extraction (§01.6) | If Layers 4–5 land and static recall proves insufficient |
