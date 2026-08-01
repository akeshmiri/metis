# Métis — Implementation Plan
## For Claude Code — Read `CLAUDE.md` First, This Is the Task Backlog

`CLAUDE.md` is persistent context (what exists, what decisions are settled,
how this project works). This document is the actual sequenced backlog of
what's left, based on a real audit of the codebase against the design docs —
not a wishlist, a specific accounting of gaps found by checking, not
guessing.

**Working rule for every phase below, carried over from how this project has
operated so far: build it, then run it for real and check a specific output
— don't mark a phase done because it doesn't crash on import.** Three real
bugs were caught this way already (see `CLAUDE.md`'s "working style"
section); assume there are more waiting in the phases below, not zero.

## Session 2 addendum — everything originally descoped is now built

After the Phase 1-10 pass below was complete, the user asked to build
everything that had been left out. What changed:

- **The four previously-skipped connectors are now built**: `locust-performance`
  (a real Locust script for this project's own `review_api_server.py`, no
  mock needed), `bmad-method-specs` (real parser, tested against a
  disclosed synthetic fixture — no real BMAD project exists here),
  `grafana-metrics` and `atlassian-prod` (real ingestion code against
  small, disclosed mock HTTP servers standing in for the real external
  systems — same pattern as Phase 2's mock Athena).
- **The LLM-dependent pieces are now real**, not skipped: no
  `ANTHROPIC_API_KEY` exists in this environment, but the `claude` CLI
  (Claude Code) is installed and independently authenticated — real,
  costed, automatable calls via `claude -p --model <model>
  --output-format json` (see `metis_mcp/llm_client.py`). Built on this:
  Layer 6 LLM-as-judge (`metis_mcp/llm_judge.py`), `MicroRequirement`
  decomposition (`metis_mcp/microrequirement.py`), and a real (deliberately
  small-scale — 8 cases, not the spec's 500 — real API calls cost real
  money) `CONST-036` calibration batch (`guardrails/calibration.py`).
- **`REQ-METIS-BM-01`'s code-graph corroboration is now real**: a
  deterministic AST-based CALLS/IMPORTS/INHERITS extraction pass
  (`cognify/code_graph_archaeology.py`) plus the actual corroboration check
  (`metis_mcp/behavior_model.py`'s `corroborate_transition`), verified
  against this project's own real call graph.
- **`mcp-server`/`ingestion-worker` are now live-deployed**, not just
  smoke-tested standalone — real network reachability from inside Docker
  Desktop's Kubernetes to the host-run Neo4j/Postgres containers via
  `host.docker.internal`, confirmed live. This surfaced five more real
  chart/deployment bugs (a Secret nobody wired into any container's env,
  an env var declared but never read by the app, a values-file override
  that silently dropped two other env vars because Helm replaces whole
  arrays across `-f` files rather than merging them, a `securityContext`
  field placed at the wrong level for the Kubernetes API to accept, and
  images with no non-root user despite `runAsNonRoot: true`) — all fixed;
  see `CLAUDE.md` for the full list.

What was still genuinely open after this pass — real Confluence/JSM/
Compass ingestion, and the CONST-036 calibration batch — is now built too;
see the Session 3 addendum immediately below.

---

## Session 3 addendum — the remaining spec/plan gap audit, closed

After Session 2 closed out everything originally descoped, the user asked
for a systematic audit against every doc (`docs/metis-specification.md`,
`metis-standards-integration.md`, `metis-data-quality-framework.md`,
`metis-gap-remediation.md`, `metis-behavior-model-test-pipeline.md`), then
to build all of it. 16 real items, each with real code, real tests against
the real Neo4j instance, and — per this project's established discipline —
real bugs found and fixed while building, not just claimed working:

1. **Test generation from Behavior Model** (`metis_propose_test_skeleton`,
   CONST-050) — `metis_mcp/pyramid_gap_check.py` (Stage 3: real
   unit/integration/functional/performance coverage detection via
   Method/TestCase id-convention parsing, disclosed as a heuristic) +
   `metis_mcp/test_skeleton_generator.py` (Stage 4 deterministic skeleton
   generation + optional real LLM body-fill + Stage 5 commit-back, which
   honestly halts without a confirmed `project_test_id_conventions` entry
   or a real git repo rather than fabricating either). CONST-050 closure
   detection (a Transition that's the sole resolution of a completeness
   gap) verified with a real test. Fixed a real gap: `locust_performance_
   connector.py` never tagged `TestCase.type = 'performance'` despite the
   manifest specifying it.
2. **CONST-047** (ISO/IEC/IEEE 29148 8-characteristic checklist) —
   `metis_mcp/requirement_quality.py`: 4 deterministic checks (unambiguous
   via a shared vagueness heuristic, complete, singular, consistent — the
   last one cross-checks real numeric thresholds against sibling
   Requirements sharing an EARS pattern+shape) + 4 real LLM-judgment
   checks (verifiable/feasible/correct/necessary, one combined costed
   call, excluded from routine regression like the other LLM tests).
3. **Layer 10 auditable rollback** + 4. **§5.4 temporal query interface**
   — built together in `metis_mcp/temporal.py` since both need the same
   real `:Revision` supersession-chain mechanism (nothing in this codebase
   previously wrote more than one version of an entity). `record_revision`/
   `as_of`/`history`/`diff`/`rollback` all real, tested; rollback writes
   the target state as a NEW revision (never deletes intervening history)
   and records a real `RollbackPerformed` Episode.
5. **Layer 8** (REQ-METIS-GRD-08) — `metis_mcp/vagueness.py` (shared
   disclosed term-list heuristic) + `metis_mcp/layer8_heuristics.py`
   (EARS non-conformance, vagueness/DQ-004, circular-traceability/DQ-018,
   orphan-claim detection — all 4 real).
6. **Full 22-metric DQ composite score** — `metis_mcp/dq_metrics.py`,
   every DQ-001..DQ-022 as a real Cypher computation, honest `value: None`
   with a specific reason for the handful genuinely not computable yet
   (DQ-005/007 need `:MicroRequirement` nodes nothing writes, DQ-009/011/
   014/021 need episode types or write paths that don't exist yet) rather
   than a fabricated number. `compute_quality_score` implements §3.1's
   weighted formula, correctly reports `release_gate_pass: None` (never a
   silent pass/fail) when any component lacks real data. Wired into
   `metis_quality_score` for `graph.backend=neo4j`. Found and fixed a real
   Cypher bug in the process: `OPTIONAL MATCH` + `count(*)` (instead of
   `count(<matched var>)`) silently counted every row as "covered"
   regardless of whether the optional match actually matched.
7. **CONST-062 MCP contract tests** — `metis_mcp/contract_validator.py` +
   `test_mcp_contracts.py`, real subprocess MCP-protocol calls against all
   9 tools, validated against `mcp-contracts/metis-mcp-tool-contracts.json`'s
   real JSON schemas. **Real finding, previously undisclosed**: all 9 tools
   deviate from the full production contract shape in Phase 0 dogfooding
   mode (only 3 of the deviations were documented before this); the test
   file's `CASES` dict is now the accurate, regression-checked record of
   exactly which and why. Fixed two real bugs this surfaced along the way:
   `metis_get_traceability`/`metis_check_coverage` returned a different
   key name (`id` vs `node_id`/`target_id`) on their found-vs-not-found
   branches.
8. **Connector manifest schema validator** — `metis_mcp/manifest_validator.py`,
   validates all 7 real connector manifests against `metis-connector-
   manifest-schema.json` (all 7 pass clean — a real, useful negative
   result). Added `jsonschema` as an explicit dependency (was only ever
   present transitively).
9. **Token optimization** (§9.1) — `metis_mcp/token_optimization.py`:
   Caveman-style prompt compression (real filler-stripping, JSON-span-
   protected, wired into `llm_judge.py`'s system prompt), Headroom-style
   response compression (real structural pruning with a hard provenance-
   field exclusion, opt-in via `token_optimization.headroom_enabled`,
   wired into `metis_get_context`/`metis_get_traceability`/
   `metis_impact_analysis`), and Cache-Aligner temporal-field
   stabilization.
10. **§8.2 Hybrid retrieval** — `metis_mcp/hybrid_retrieval.py`: real
    graph traversal, real BM25 via the `metis_graph_fulltext` index
    (declared in schema-01, never actually queried by any code before
    this), temporal point-in-time (reuses item 4's `as_of`), and a real
    disclosed deterministic weighted-score reranker merge — semantic/
    vector mode honestly refuses (no embedding model in this environment;
    4 real HNSW vector indexes exist but nothing populates `embedding`).
    Fixed a real bug: a Cypher parameter literally named `query` collides
    with `Session.run(query, ...)`'s own first positional parameter.
11. **§8.1 Pinned core memory blocks** — `metis_mcp/pinned_memory.py`:
    `active_constraints`/`open_incidents`/`pinned_business_rules`, real
    2-hop scope traversal, unconditional inclusion (never ranked/filtered),
    a real disclosed token-count approximation, and a visible (never
    silent) overflow warning.
12. **§8.3 Sleep-time consolidation** — `metis_mcp/sleep_time_
    consolidation.py`: real lexical Jaccard near-duplicate detection
    (`:MergeProposal` nodes, `PendingReview`, never auto-merged — this is
    now DQ-016's real data source too) + non-lossy rollup summarization
    with a real, resumable checkpoint (same pattern as `application_code_
    connector.py`'s).
13. **§8.4 Memify feedback loop** — `metis_mcp/memify.py`: a real
    Beta-Bernoulli posterior update per `(extraction_rule, entity_type,
    connector)` triple from real `ExtractionCorrected` episodes —
    auditable (every correction is a permanent Episode) and reversible
    (recomputed from scratch every time, not a mutated running average).
14. **Real Confluence/JSM/Compass ingestion** — extended `atlassian_
    connector.py` (JSM request → Defect, Confluence page → Episode-only
    per the same real ontology gap `flatfiles_connector.py` already
    documents, Compass component → Service) and `mock_jira_server.py`
    (3 new endpoints using real Atlassian Cloud REST API path
    conventions). Found and fixed a real design bug before it shipped:
    embedding a Confluence page's version number into its Episode id
    would have violated schema-03's real `(source_connector, unit_id)`
    uniqueness constraint the moment a page's version changed.
15. **Copilot integration** — built now per explicit user direction
    (previously deliberately deferred). `metis_mcp/copilot_integration.py`
    generates the real `spec-aware.agent.md` discovery file from actual
    resolved config (not a hand-typed template) — the generated artifact
    is checked in at `.github/agents/spec-aware.agent.md`. Config-only, as
    scoped: no real GitHub Copilot instance exists in this environment to
    connect against live.
16. **CONST-036 full calibration batch** — real, disclosed finding: this
    codebase's actual real (non-demo, source-text-backed) Class+Method
    pool started at 127 entities (33+94), not 500 — demo-data-generated
    entities were deliberately excluded since their Episodes carry no real
    `raw_content`, and scoring confidence against empty text would be
    calibration theater, not a genuine signal. Found and fixed a real
    Cypher bug while building this: a trailing `LIMIT` after `UNION` only
    applies to the last branch, not the combined result —
    `sample_size=4` was silently returning 37 rows (all 33 unlimited
    Class rows + 4 limited Method rows) before the fix. By the time the
    full batch actually ran, this session's own new modules had grown the
    real pool to 229 (42 Class + 187 Method) — the real AST-based Cognify
    pass picking up this session's own real new source files. **Real
    result: 229 real, costed `claude`-CLI calls (haiku) → 61 auto_write
    (26.6%), 31 quarantine (13.5%), 137 rejected (59.8%)** — a genuine
    miss against DQ-002's initial targets (≥60%/≤30%/≤10%), exactly the
    kind of finding calibration exists to surface; full detail in
    `metis-server/calibration_result.json`. One real transient CLI
    failure hit mid-run (exited 1, empty stderr, confirmed transient by
    an isolated retry succeeding) — fixed with a real 3-attempt retry in
    `_assess_confidence`, same mitigation `llm_judge.py` already uses.

**~15 new real modules, ~15 new real test files (all passing against the
live Neo4j instance, LLM-calling ones run and verified at least once),
several real bugs found and fixed along the way** — see `CLAUDE.md`'s
Session 4 addendum for the consolidated list and the full regression
count.

---

## Session 4 addendum — fresh full-project re-audit finds 8 more real gaps, user closes 4

The user asked for an independent re-review of the *entire* project
(not scoped to Session 3's own 16-item list) to check for anything still
missing. Cross-checked every `REQ-METIS-*`/`CONST-*` id across every real
doc against actual code. Found 8 real, previously-undocumented gaps
(`REQ-METIS-ACD-01..09`/Academy, `REQ-METIS-SLD-01..03`/PPTX,
`REQ-METIS-MTX-01..03`, `REQ-METIS-COST-08`, `REQ-METIS-RES-01..04`,
`REQ-METIS-GRD-11`, `REQ-METIS-SKL-01/02`, `REQ-METIS-CPT-06`) — the user
picked 4 to build now (GRD-11, SKL-01/02, COST-08, and the large one —
§12 Academy + Site + PPTX). MTX/RES/CPT-06 remain open by explicit choice,
not silently dropped.

**Two real bugs from Session 3's own prior work, fixed immediately on
discovery** (before any new feature work): `Revision`/`MergeProposal`/
`ConfidenceAdjustment` (Session 3's new control-plane labels) had zero
schema constraints, unlike every other real label in the project — fixed
with 5 new constraints in `schema-02`. Two new config keys were readable
by code but undocumented in the example/chart config files — fixed in
both.

**GRD-11** (`metis_mcp/constitution_gate.py`): real `:Constitution` nodes
now populate the production ontology (reusing `corpus.py`'s already-proven
parser), plus a real, narrowly-scoped hard-block: a `Requirement`
candidate failing CONST-047's 4 deterministic checks is REJECTED before
the general Layer 2/3 pipeline even runs — closing a real gap (only EARS-
pattern *presence* gated submission before this, never the substantive
checklist). Real, unplanned discovery: `schema-02` already had a
`constitution_precedence_required` constraint with a comment describing
this exact design, predating this session — confirming this was a known,
intended gap, not a speculative addition.

**SKL-01/02** (`.agents/metis.agent.md`): a real Quick-Routing-table
router for all 5 real skills, modeled on Atlas's own pattern.

**COST-08** (`metis_mcp/cost_gate.py`): a real "Confirm to proceed?
[yes/no]" gate, wired into `guardrails/calibration.py` — the one real
large-batch scenario this project has (the prior session's own 229-call
run would have needed this confirmation had it existed then).

**§12 Academy + Site + PPTX** — the large item:
- `metis_mcp/academy.py`: 4 real Academy pages, a real why-link mapping
  from actual rejection-reason strings (wired into `guardrails/pipeline.py`),
  real next-step guidance (wired into `metis_get_context`), and a real
  changelog generated from `metis_mcp/temporal.py`'s actual `:Revision`
  history — one shared content-assembly stage both renderers use.
- `metis_mcp/site_renderer.py` + a real generated example at
  `metis-server/site/`.
- `metis_mcp/pptx_renderer.py` + a real generated example at
  `metis-server/quality-snapshot.pptx`. Real Content QA + File QA; Visual
  QA honestly disclosed as not built (no image-rendering infrastructure
  here). New dependencies (`markdown`, `python-pptx`) confirmed installable.
- Fixed `metis_explain_answer` to return the contract's real shape
  instead of forwarding to `metis_explain_decision`'s unrelated one —
  `graph.backend=neo4j` now genuinely conforms (verified directly);
  `graph.backend=local` still doesn't fully (no formal Episode record for
  dogfooding text documents), disclosed via `adapted: true`.
- **Real bug found and fixed**: `temporal.py`'s `record_revision()`
  silently no-op'd (returned a fake success value) against a nonexistent
  entity id — now raises. Caught building the changelog feature's test,
  not reported by a user.
- **Real bug found and fixed**: `corpus.py`'s `parse_corpus()` mixes a
  `'__conflicts__'` sentinel into its returned dict; the two existing
  callers already knew to pop it, `constitution_gate.py` was the first
  new caller to hit the resulting `AttributeError` for real.

Full regression after this round: **41/41 test files passing**. See
`CLAUDE.md`'s Session 5 addendum for the consolidated list.

**Follow-up the same session — a second, deeper self-review of the
Session 4 work itself found 6 more real bugs**, most significantly two
systemic ones swept across the whole codebase, not just the call site
that happened to surface each first:
- `next_step_guidance`/`ACADEMY_CONTENT_VERSION`/`generate_changelog`
  were real but under-wired (3 of 4 gap types dead, version never
  rendered, changelog never called outside its own test) — fixed, and
  `constitution_gate.py` got a real operational `main()` it never had.
- **Id uniqueness is per-label, not global** — `:DogfoodingItem` shares
  real id strings with the production ontology by design, and every
  label-agnostic `MATCH (e {id: $id})` query silently risked matching
  both. Fixed across `temporal.py`, `hybrid_retrieval.py`,
  `pinned_memory.py`, `llm_judge.py`, and `server.py`.
- **`execute_write()` can retry after a successful commit** (a real,
  reproduced Neo4j driver edge case, not hypothetical — caught as an
  intermittently-failing test), and `CREATE` on a pre-computed id isn't
  safe against that. Fixed with `MERGE ... ON CREATE SET` across
  `temporal.py`, `memify.py`, `sleep_time_consolidation.py`, and two
  files that predate this session entirely — `oauth2.py` and
  `guardrails/corpus_runner.py` — meaning this was a real, latent bug in
  already-shipped Phase 4/9 code.

Full regression after this follow-up: **42/42 test files passing.**

---

## Phase 0 — Verify the baseline (do this first, every session)

Before starting any new phase, confirm the existing baseline still works —
don't build on top of something silently broken:

```bash
cd metis-server
.venv/bin/python3 test_config_manager.py       # expect 4/4
.venv/bin/python3 test_classification_gate.py   # expect 8/8
.venv/bin/python3 test_e2e.py                   # expect all 9 tools, no errors
```

If any of these fail, fix that before starting new work — don't build Phase
N+1 on top of a broken Phase N.

---

## Phase 1 — `Neo4jGraphStore`

**Why first:** almost nothing downstream can be tested against real data
until this exists. `LocalGraphStore` is a text-corpus stand-in; the real
system needs a real graph.

**Grounding:** `schema/metis-graph-01-entity-baseline-constraints.cypher`,
`schema/metis-graph-02-entity-specific-constraints.cypher`,
`schema/metis-graph-03-single-db-consolidation.cypher` — the schema is
already decided (single Neo4j Enterprise/Community database, tiered
`MetricsSnapshot` rollup, `lifecycle_state`/`risk_tag` properties instead of
a review-queue table). Do not redesign the schema; implement against it.

**Tasks:**
1. Stand up a real local Neo4j instance (Community edition is fine — see
   `metis-chart/values-sbx.yaml` for the Phase 0 posture). Docker is the
   fastest path if available locally.
2. Run all three schema files against it for real — this has never
   happened in this project yet. Fix whatever doesn't apply cleanly (there
   will likely be something; these were written and reasoned about, never
   executed).
3. Implement `metis_mcp/neo4j_graph_store.py` with the exact same method
   signatures as `LocalGraphStore`: `get_node`, `neighbors`,
   `traceability_chain`, `impact_analysis`, `orphan_rate`, `search`.
4. Add a config flag (`METIS_GRAPH_BACKEND=local|neo4j`, resolved through
   `config_manager.py` — **not** a new env var read directly in code,
   consistent with the no-config-in-code rule) so `server.py` can select
   either backend without code changes.

**Acceptance criteria — do not mark this phase done until all of these pass:**
- [x] All three Cypher files execute against a real Neo4j instance with zero errors — required fixing 4 real bugs in the schema files themselves (invalid vector-index label union, a constraint/index name collision, invalid `CREATE PROPERTY EXISTENCE CONSTRAINT` syntax, and unsupported filtered/partial indexes); see CLAUDE.md's "concrete next build tasks" §1 for the details.
- [x] A new `test_neo4j_graph_store.py` exists and passes against the real instance (not mocked) — 10/10, run against Neo4j 5.26 Enterprise via Docker.
- [x] The existing `test_e2e.py` passes with `graph.backend: neo4j` in `.metis/config.yaml` (this project resolves backend selection through config, per the no-config-in-code rule, rather than a raw `METIS_GRAPH_BACKEND` env var read directly in code) — proves the swap is real. Required one small, justified harness fix: `StdioServerParameters` needed explicit `env=os.environ.copy()`, since the MCP SDK only forwards an allowlisted env subset to the spawned subprocess by default, not `METIS_NEO4J_PASSWORD`.
- [x] At least one manually-inserted real node round-trips correctly through `metis_get_context` — `load_dogfooding_corpus.py` loaded 177 real nodes / 359 real citation edges from the actual corpus; `metis_get_context('CONST-047')` returns the real text against the neo4j backend.

Note: this loaded the dogfooding corpus under a new `DogfoodingItem` label,
not the production ontology's `Requirement`/`Constitution`/etc. labels —
see `load_dogfooding_corpus.py`'s docstring. The real production ontology
still isn't populated by anything; that's Phase 2/3.

---

## Phase 2 — One real connector, end-to-end

**Why second:** proves the ingestion half of the pipeline works, not just
the query half Phase 1 validated. `application-code` is the best first
candidate — it's the most concretely specified (`athena_internal_read`
protocol, already has a real manifest).

**Grounding:** `connectors/metis-connector-application-code.json` — read
this first, it defines the exact protocol (`athena_internal_read`,
`change_detection_column: updated_at`, `poll_interval_seconds: 300`).

**Tasks:**
1. **This needs a real Athena Postgres instance to read from, or a
   realistic mock of one — decide which before starting.** If no real
   Athena instance is available in this environment, build a minimal mock
   Postgres table matching Athena's real schema shape (check the archived
   Athena schema-catalog pattern referenced in `metis-connector-architecture.md`
   if it's available in this environment) rather than inventing a
   different shape.
2. Implement the actual polling logic: query `WHERE updated_at > last_checkpoint`,
   not a full-table scan every cycle.
3. Land results as real `Episode`/`Requirement`-or-equivalent nodes in
   Neo4j (Phase 1's store), not just parsed-and-discarded.
4. Implement checkpoint tracking so a restart resumes from where it left
   off — this is `metis-specification.md` §10's resumability requirement,
   already designed, not yet built.

**Acceptance criteria — DONE:**
- [x] Running the connector twice in a row produces zero new episodes the second time — verified (`test_application_code_connector.py`).
- [x] Killing the process mid-run and restarting resumes correctly — verified with a real `SIGKILL` on a real subprocess, not simulated.
- [x] A real query against Neo4j shows the expected node count, matching a dynamically-computed known input size.

No real Athena instance was available, so per this phase's own instruction,
a minimal mock Postgres (`connectors/mock_athena_schema.sql`) was built,
seeded with genuinely real content (this repo's own `metis_mcp/*.py`
files) — not a different shape invented from scratch, and not fabricated
business data. Commit/PullRequest ingestion was descoped (no real git
history exists in this environment to draw from honestly) — disclosed in
`mock_athena_schema.sql`'s docstring, not silently skipped.

---

## Phase 3 — Minimal Cognify pass (structural extraction, no LLM yet)

**Why third, and why "no LLM yet":** get the deterministic half of
extraction working and tested before adding the nondeterministic half —
matches this project's own code-vs-LLM principle (`metis-specification.md`
§9). Adding LLM calls before the deterministic pipeline is proven just
makes debugging harder.

**Tasks:**
1. Take Phase 2's raw ingested content and do purely structural extraction
   into typed graph entities — no model calls, no confidence tiering yet,
   just "this raw row becomes this typed node with these properties."
2. Wire this into Phase 1's Neo4j store for real writes (this is the first
   phase that actually writes non-trivial content into the graph).

**Acceptance criteria — DONE:**
- [x] A known input (the real `metis_mcp/*.py` files) produces exactly the expected node shape — verified against an independently-computed count (11 classes / 54 methods at the time; `test_structural_extraction.py` recomputes the expected count fresh each run rather than trusting a frozen number, after a hardcoded-count staleness trap was hit once already this session).
- [x] No-fabrication check: every property traces to a real AST field (`name`, `lineno`) or the source Episode — verified by a dedicated test.

**Real bug found and fixed:** chaining `UNWIND` clauses linearly in one
Cypher query meant an empty list partway through (e.g. a file with 0
classes, or a class with 0 methods) collapsed the row stream to zero rows
for everything chained after it — silently dropping the module-functions
write for those files. Fixed by isolating each block in its own `CALL (r,
e) { ... }` subquery. Caught by checking real per-file counts by hand, not
by the query failing to run.

---

## Phase 4 — The deterministic guardrail layers

**Why fourth:** now there's real content to guard. Start with the layers
that are pure logic (no LLM), matching `classification_gate.py`'s pattern —
that module is the template for how the rest of this should look: real
`CONST-*` rule numbers, real tests per rule, no vague "guardrail applied"
logging.

**Grounding:** `docs/metis-foolproof-security-framework.md`,
`docs/metis-constitution-adopted.md` Articles I–IV.

**Tasks, in this order (deterministic first, matching §9's principle):**
1. Structural validation (Layer 2) — is a proposed entity even well-formed
   before anything else happens to it.
2. Confidence tiering skeleton (`auto_write`/`quarantine`/`rejected`) —
   the state machine, without the judge-call logic yet (that needs an LLM,
   deferred to a later phase).
3. The `lifecycle_state`/`risk_tag` property scheme on real nodes, matching
   `schema/metis-graph-03-single-db-consolidation.cypher`'s design exactly.

**Acceptance criteria — DONE:**
- [x] Each layer has its own test file matching `test_classification_gate.py`'s convention: `test_structural_validation.py` (Layer 2, 8 tests), `test_confidence_tiering.py` (Layer 3, 9 tests), `test_guardrail_pipeline.py` (both wired together against real Neo4j, 5 tests).
- [x] A deliberately malformed entity (missing `source_episode_id`, a dangling `source_episode_id` reference, a `Requirement` missing `ears_pattern`) is rejected with the specific reason, verified both at the unit level and end-to-end against a real Neo4j instance (confirming the entity was never written at all, not just that a message was returned).

`metis_mcp/structural_validation.py` (Layer 2) and `metis_mcp/confidence_tiering.py`
(Layer 3, state machine only — no judge-call/LLM logic, as scoped) are wired
together in `guardrails/pipeline.py`, which actually writes real
`lifecycle_state`/`risk_tag` onto real Neo4j nodes.

---

## Phase 5 — Wire the reviewer UI to the real server

**Why fifth, not first, despite being visually complete already:** it's
currently a convincing mockup with hardcoded sample data — genuinely
useful only once there's a real queue behind it, which needed Phases 1–4
first.

**Grounding:** `docs/metis-review-queue-ui.html` (the UI itself),
`.agents/skills/metis-review-assist/` (the skill this UI's "Review" button
conceptually triggers).

**Tasks:**
1. Replace the hardcoded `items` array with a real fetch against the MCP
   server's quarantine query (`WHERE lifecycle_state='Quarantine'`, per the
   schema).
2. Wire the Approve/Reject buttons to actually call `metis_submit_episode`
   — **this means the write path gate (`REQ-METIS-CPT-01`) needs a real
   decision here**: either keep it disabled and have the UI clearly show
   "recording disabled, decision noted but not written" (matching what
   `metis-review-assist` Step 3 already does honestly), or make the
   explicit, deliberate call to enable it for this specific UI flow with
   full guardrail backing from Phase 4. Don't silently enable it as a side
   effect of "making the button work."

**Acceptance criteria — DONE, with one criterion reinterpreted (disclosed):**
- [x] The UI shows real quarantine items created by Phase 3/Phase 7 (real `Class`/`Method`/`TestCase` entities, resubmitted through Phase 4's real gate at Quarantine tier) — the hardcoded sample array is gone entirely.
- [x] *(Reinterpreted)* The second criterion assumed the write-path-enabled fork of this phase's own explicit decision. This build took the **disabled** fork (the safer default, requiring no separate deliberate-enablement decision) — `REQ-METIS-CPT-01` stays closed, matching `metis_submit_episode`'s existing behavior. The equivalent real proof: approving/rejecting returns the honest "noted but NOT written" acknowledgment, **and** the underlying node's `lifecycle_state` is confirmed unchanged in Neo4j afterward — verified in `test_review_api_server.py`.

Built `review_api_server.py`, a small, explicitly-scoped HTTP API (not the
full production transport — that's Phase 6, sequenced after this on
purpose) serving `GET /api/quarantine` and `POST /api/decision` to
`docs/metis-review-queue-ui.html`, whose JS now fetches real data instead
of a hardcoded array. **Disclosed limitation:** no browser-automation tool
was available in this environment — verified via `curl`, a real spawned-
server integration test, and a Node.js JS-syntax check, not an actual
interactive browser session.

---

## Phase 6 — Production transport (Streamable HTTP + OAuth2)

**Why sixth, not earlier:** stdio has been sufficient for all local Claude
Code testing so far; this is only needed for actual multi-user deployment,
which shouldn't happen before Phases 1-5 prove the system works at all.

**Grounding:** `docs/metis-specification.md` §11.2,
`docs/metis-multi-client-integration.md`, `metis-chart/values.yaml`'s
`mcp-server` component (which already declares `MCP_TRANSPORT:
streamable-http` — currently nothing reads that env var; this phase makes
it real).

**Tasks:**
1. Implement Streamable HTTP transport as an alternative to stdio in
   `server.py` (the MCP SDK supports both — this is a transport swap, not
   a tool-logic rewrite).
2. Implement OAuth2 per `CONST-064`'s already-specified token lifecycle
   (1-hour access tokens, 30-day revocable refresh, re-validated every
   request — not cached from issuance).
3. Team/RBAC scoping tied to Neo4j Enterprise's native roles (if using
   Enterprise) or an equivalent check against `owner_team` properties (if
   still on Community per Phase 0's posture).

**Acceptance criteria — DONE, verified live:**
- [x] A token issued for one team cannot retrieve another team's `owner_team`-scoped node, even with a known node id — `test_rbac.py`'s flagship test, real Neo4j.
- [x] A revoked token is rejected on its very next request — verified twice: once at the unit level (`test_oauth2.py`), and once **live against the actual running Streamable HTTP server**: issued a real token, confirmed `curl` with it returned 200 against `/mcp`, revoked it, confirmed the *exact same token* immediately returned 401 with `"Token has been revoked."`

`metis_mcp/oauth2.py` implements the token lifecycle contract against real
Neo4j (`:User`/`:Token` nodes — no separate Postgres/Redis, per the single-
database decision); `metis_mcp/http_transport.py`'s `OAuth2Middleware` gates
the real `mcp.streamable_http_app()`. Disclosed scope: the full interactive
OAuth2 authorization-code/PKCE browser-consent flow (RFC 6749) is not
implemented — that needs a real browser + IdP UI, out of scope for a
backend service; a real deployment sits this token issuance behind that
flow. A real bug was found and fixed live: registering `/healthz` before
`add_middleware()` does NOT exempt it from the auth gate (Starlette
middleware wraps the whole ASGI chain regardless of route registration
order) — the middleware itself now exempts it explicitly.

---

## Phase 7 — Remaining connectors

**All six connectors are now built — DONE.** Built the two structurally
distinct ones first (`flatfiles`, `test-suite-ingest`); the remaining four
were initially skipped as mechanical repeats of Phase 2's pattern, then
built anyway per the Session 2 addendum above once asked to. `locust-performance`
uses a real Locust script for this project's own `review_api_server.py`
(no mock needed at all); `bmad-method-specs` is real parsing code tested
against a disclosed synthetic fixture (no real BMAD project exists here);
`grafana-metrics`/`atlassian-prod` are real ingestion code against small,
disclosed mock HTTP servers standing in for the real external systems.
Building `bmad-method-specs` found a real gap in Phase 4's own guardrail
code: `structural_validation.py` never checked schema-02's
`corroboration_count` existence constraint for `Requirement`/`BusinessRule`
— nothing had tried to write a real `:Requirement` node through the gate
until this connector did. Fixed, with a regression test.

**`flatfiles`** (file_scan protocol — genuinely needs no mock at all, reads
this project's own real `corpus/*.md` files directly): idempotent,
resumable (real `SIGKILL` test), exact known count — 3/3 tests
(`test_flatfiles_connector.py`).

**`test-suite-ingest`** (AST-parsing, explicitly flagged as "genuinely new
work" in its own manifest): parses this project's own real `test_*.py`
files, resolves real traceability links via real `REQ-METIS-*`/`CONST-*`
tags already present in several test files' docstrings (not fabricated —
these tests were written against those specific rules), creates real
`VERIFIES` edges to real existing graph nodes. Orphan test cases (no tag
match) are quarantined with a specific `triage_reason`, never given a
guessed link — 4/4 tests (`test_test_suite_connector.py`).

---

## Phase 8 — Behavior Model → Test pipeline

**Grounding:** `docs/metis-behavior-model-test-pipeline.md`,
`docs/metis-standards-integration.md` §2–3 (the determinism/completeness/
reachability checks — already specified as "implement as deterministic
Cypher queries," not designed here, that instruction still stands).

**Tasks:**
1. EARS conformance checker (deterministic regex/parser, per
   `REQ-METIS-ONT-04` — do not implement this as an LLM call).
2. `MicroRequirement` decomposition (this one genuinely needs an LLM, per
   the original design — the atomic-behavior split is judgment, not parsing).
3. `Transition`/`State`/`Guard`/`Trigger`/`Action` extraction, with the
   code-graph corroboration check (`REQ-METIS-BM-01`) — this needs Phase 1's
   graph store AND a real code graph (`CALLS`/`IMPORTS`/`INHERITS` edges,
   `docs/metis-code-graph-archaeology-extension.md`), which isn't listed as
   its own phase above — add it here as a sub-task if not already done.
4. The determinism/completeness/reachability checks as real Cypher queries
   against the `Transition` graph.

**Acceptance criteria — DONE, with MicroRequirement/Layer 6 explicitly descoped:**
- [x] A deliberately ambiguous pair of transitions (same `Trigger`, overlapping `Guard`s — modeled on this project's own real confidence-tiering boundaries, `confidence >= 0.9` vs `confidence >= 0.6`, a genuine domain ambiguity) is caught by `check_determinism` and both Transitions are marked `lifecycle_state='Disputed'` with a specific `dispute_reason` — never silently resolved. A real logic bug was found and fixed here too: the interval-overlap check initially didn't distinguish strict (`<`) from non-strict (`<=`) bounds, so `confidence < 0.6` and `confidence >= 0.6` — a clean, non-overlapping partition — were wrongly flagged as overlapping at the boundary.
- [x] The EARS checker rejects real non-conformant text and accepts all five real conformant examples, all copied verbatim from `metis-specification.md` §4.3 — not synthetic examples (`test_ears_checker.py`, 7/7).

**`MicroRequirement` decomposition, the Layer 6 LLM-as-judge, and
`REQ-METIS-BM-01`'s code-graph corroboration are now all built** — see the
Session 2 addendum near the top of this document. No `ANTHROPIC_API_KEY`
was ever set; real calls go through the `claude` CLI instead
(`metis_mcp/llm_client.py`). The code-graph corroboration needed a real
`CALLS`/`IMPORTS`/`INHERITS` extraction pass, also now built
(`cognify/code_graph_archaeology.py`).

`metis_mcp/behavior_model.py`'s reachability check was also caught and
fixed before shipping: an undirected Cypher variable-length pattern would
have treated `FROM_STATE`/`TO_STATE` edges as traversable in either
direction (they point opposite ways relative to the State nodes), over-
reporting reachability. Replaced with a real edge-pair fetch + Python BFS
respecting direction.

---

## Phase 9 — `metis-ingestion-worker` and `metis-guardrail-corpus-runner` as real services — DONE

**`helm lint`/`helm template` ran for real for the first time in this
project's history, and found three real bugs, none previously caught
because neither had ever been run:**
1. `values.yaml` had no `secrets:` key at all, so `.Values.secrets.athenaDbPassword`
   errored on a nil pointer before its own `| default "REPLACE-AT-INSTALL-TIME"`
   fallback ever ran. Fixed by adding `secrets: {}`.
2. `_objects.tpl`'s `image:` field was wrapped in hardcoded literal single
   quotes instead of Helm's `quote` function — any apostrophe in the
   registry/repository placeholder text (e.g. "Athena's own...") broke the
   YAML mid-string. Fixed with `printf ... | quote`.
3. **The chart referenced a ServiceAccount by name in every Pod spec, but
   no template anywhere actually created one** — every real deployment
   would have failed at pod admission (`serviceaccount ... not found`),
   regardless of whether the container images existed. Added the missing
   `templates/serviceaccount.yaml`.

- [x] `helm template .` renders cleanly (`helm lint`: 0 chart(s) failed; 20 real k8s resources rendered) after the three fixes above.
- [x] Deployed to a real cluster — Docker Desktop's built-in Kubernetes (kind/minikube weren't installed; this is functionally equivalent for this purpose) — with a real, locally-built `metis-guardrail-corpus-runner` image. **Confirmed the CronJob fired three consecutive times** on its real schedule, each producing a `Completed` pod with real log output (12/12 real adversarial-corpus cases passing).

**Update (Session 2 addendum): `mcp-server`/`ingestion-worker` are now
also live-deployed**, not just smoke-tested standalone. Both reached the
real, host-run Neo4j and mock-Athena-Postgres containers over the network
from inside the cluster (via `host.docker.internal`), confirmed live:
`mcp-server`'s real `/healthz` returned 200 over a real port-forward, and
the in-cluster `ingestion-worker` found and processed 16 real un-cognified
episodes on the shared graph, live, from inside the cluster. Getting here
required finding and fixing five more real chart bugs (see `CLAUDE.md`'s
summary) — none of which the CronJob-only deployment above would have
surfaced, since the CronJob's pod spec doesn't set a pod-level
`securityContext` and the corpus-runner doesn't read `config.yaml` or a
Secret at all.

`guardrails/corpus_runner.py` (CONST-057/058): runs the real 12-case
adversarial corpus against the real Layer 3 state machine at a fixed,
deliberately-unprivileged confidence — proving the architecturally
load-bearing guarantee (confidence is always an external parameter,
never derived from parsing instructions out of ingested text) rather than
the originally-intended full LLM-judge pass, which needs a real model call
this environment doesn't have.

`ingestion_worker.py` wraps Phases 2/3/7's already-tested connectors +
Cognify into one polling loop with a `/healthz` endpoint, per
`metis-chart/values.yaml`'s `DEFAULT_POLL_INTERVAL_SECONDS`.

---

## Phase 10 — More skills — DONE, with a significant discovery

**`metis-server/.agents/skills/metis-review-assist` — the real, existing
skill this phase's own instructions say every new skill must structurally
match — does not exist anywhere in this copy of the project.** The entire
`.agents/` directory was absent. Same category of gap as the `pyproject.toml`
bug `CLAUDE.md` already documented (something that didn't survive the move
to this machine), just not previously noticed because nothing in Phases
0-9 needed it. Flagged to the user directly rather than silently inventing
skill content with no real template to check against.

**By explicit user decision:** reconstructed `metis-review-assist` first
(grounded in `metis-specification.md` §9.2's real RPI/Stage-Confirmation
text and this codebase's actual, currently-callable tool signatures — not
invented from nothing, but disclosed as a reconstruction, not the
original), then built the two new skills against that reconstructed
template:
- `.agents/skills/shared/knowledge/anti-hallucination-protocol.md` (shared, referenced once per skill, per Atlas's own convention)
- `.agents/skills/metis-review-assist/` (reconstructed)
- `.agents/skills/metis-behavior-modeling/` (new — wraps Phase 8's real determinism/completeness/reachability checks; explicitly scopes out `REQ-METIS-BM-01` code-graph corroboration and `MicroRequirement` decomposition, same LLM/code-graph gaps as Phase 8)
- `.agents/skills/metis-onboarding/` (new — implements `metis-gap-remediation.md` §6's real 6-step runbook; steps 3 and 4 honestly halt rather than fake a pass, since this build uses Python's `ast` module instead of Tree-sitter and has no real calibration/judge model)

---

## What's deliberately NOT in this plan

- **The Zero Data Retention agreement** — a business decision already made (no, for now), not an engineering task. Don't build around eventually needing it; build for the current `public_internal`-by-default posture.
- **A general Constitution-enforcement engine** — each phase above implements specific, named rules with specific tests, the same way `classification_gate.py` does for `CONST-051-053`. Building a generic "rule engine" that interprets all 64 rules automatically was never the plan and isn't a good idea — most rules need real judgment about what "enforcement" even means for them, not a generic interpreter. `REQ-METIS-GRD-11`'s real implementation (Session 4 addendum) follows exactly this pattern — one specific, named rule (CONST-047) with a real deterministic check, not a 64-rule interpreter.

Everything else that used to be listed here (the four connectors,
`MicroRequirement` decomposition, Layer 6 LLM-as-judge, `REQ-METIS-BM-01`
corroboration, live `mcp-server`/`ingestion-worker` deployment, Copilot
integration, real Confluence/JSM/Compass ingestion, the `CONST-036`
calibration batch at its real available scale, `REQ-METIS-GRD-11`,
`REQ-METIS-SKL-01/02`, `REQ-METIS-COST-08`, and §12 Academy/Site/PPTX) is
now built — see the Session 2, 3, and 4 addenda near the top of this
document.
