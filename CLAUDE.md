# Métis — Project Context for Claude Code

This file belongs at the Métis project root so it loads automatically every
session — or paste it directly into a new Claude Code conversation to start one.

## What this project is

Métis is an AI-driven specification and requirements knowledge-graph
platform for Quality Engineering: it ingests requirements, code, and tests
from multiple real sources, builds a bi-temporal graph with a formal
guardrail stack (anti-hallucination, corroboration, confidence tiering), and
generates real functional/performance tests layered on top of existing
unit/integration coverage.

**Read `README.md` first** — it indexes the full directory tree and says
where each piece lives. Don't re-derive the structure; it's already mapped.

## Session 13 addendum — Trigger/Guard folded into Transition, real relationship-level guardrail + ontology spec doc, and a real requirements-completeness gap found and fixed

User reviewed the live login-example graph and pushed on the behavior
model's own design, in three rounds:

**Round 1 — three concrete corrections + "build a spec."** (1) Remove
`Transition-[:TRACES_TO]->Intent` (Trigger never had one). (2)
`AcceptanceCriterion` should validate the concrete behavior it tests --
new `AcceptanceCriterion-[:VALIDATES]->Transition` edge. (3) Trigger is
conceptually an attribute of one Transition, not its own entity --
**removed as a node**, folded into `Transition.trigger`; user then said
Guard should get the same treatment ("I have no clue what Guard is") --
**removed as a node too**, folded into `Transition.guard_expression`.
Plus: "we do not generate node on the fly... build a spec for how to
build graph database and how to build a guardrail so we do not do
anything outside of that doc."

Built:
- `metis_mcp/behavior_model.py`: `load_transition()` sets `trigger`/
  `guard_expression` directly on the Transition node instead of
  MERGE-ing separate Trigger/Guard nodes + `ON_TRIGGER`/`WHEN_GUARD`
  edges. `check_determinism()`/`check_completeness()` (CONST-048/049)
  rewritten to compare Transitions by property value (`t1.trigger =
  t2.trigger`) instead of shared-node identity.
  `metis_mcp/test_skeleton_generator.py`'s `_fetch_transition_detail()`/
  `_resolves_completeness_gap()` got the same property-based rewrite
  (`TransitionDetail.trigger_id`/`trigger_name` collapsed into one
  `trigger` field -- they were always the same string).
- `demo_data/login_example.py`: removed `Transition-TRACES_TO->Intent`;
  added `AcceptanceCriterion-[:VALIDATES]->Transition` per AC. Real,
  disclosed consequence: a `planned` Transition (no AC yet, by design)
  now has **no live graph path** to its own Intent/Requirement until it's
  actually built and validated -- the most honest available modeling,
  not a bug.
- **New `docs/metis-ontology-specification.md`** -- the authoritative,
  living reference: one table per layer (label, purpose, required
  properties, allowed outgoing relationships) plus a consolidated
  Relationship Catalog (every real `(FromLabel)-[:REL]->(ToLabel)` triple
  in the codebase, derived by grepping `demo_data/`, `connectors/`,
  `guardrails/`, `metis_mcp/`, not invented). States the governance rule
  directly: schema-01 + schema-02 + `structural_validation.py` +
  this doc, all four, together, every time.
- **New relationship-level guardrail**: `metis_mcp/
  structural_validation.py`'s `ALLOWED_RELATIONSHIPS` (the literal data
  behind the doc's Relationship Catalog) + `validate_relationship()` --
  the same enforcement Layer 2's node-label check already does, extended
  to edges for the first time (previously nothing validated relationship
  type/cardinality at all). One documented, intentional exception:
  `test_suite_connector.py`'s tag-citation `TestCase-[:VERIFIES]->
  (target)` has no fixed target label by design (validated by real
  tag-existence instead, REQ-METIS-CONN-04) -- not a policing gap.
- **New DQ-024** (`metis_mcp/layer8_heuristics.py`'s
  `check_transition_ac_coverage`, added mid-session on the user's own
  follow-up): every `implemented` Transition must have >=1
  `AcceptanceCriterion-VALIDATES->` edge -- real behavior nothing
  validates is an unverified claim, not a covered one. `planned`
  Transitions excluded (nothing to validate yet is correct).

**Round 2 — "the state-transition still looks wrong," a real
architecture brainstorm.** User pushed further: shouldn't a Transition
just be a link, not a node? Investigated and found two real, hard Neo4j
constraints, not style preferences: (1) a relationship cannot be the
target of another relationship, so `AcceptanceCriterion-[:VALIDATES]->
Transition` requires Transition to be a node; (2) `metis_mcp/temporal.py`'s
whole provenance mechanism (`record_revision`/`history`/`as_of`/`diff`)
writes `(entity)-[:HAS_REVISION]->(:Revision)`, which also requires
`entity` to be a node -- so a Transition-as-edge would permanently lose
real revision history, the one entity type representing behavior
changing over time, directly cutting against Session 10/11's own
"Métis should be Temporal context aware" requirement. Explored a
target-state-only alternative (real ambiguity found: `t2`/`t3`
originally shared a target *event* but diverged on state; separately,
4 different transitions shared a target *state* -- `LoggedOut`) and an
`Event`-node alternative (same ambiguity, mirrored: `t2`/`t3` shared the
*event* `submit_invalid_credentials` but diverged on guard). **User's own
final call, given full information: keep Transition as a node.** Nothing
changed from Round 1's design as a result -- this was a real
architecture review that confirmed the existing shape, not a rebuild.

**Round 3 — a genuine, real requirements-completeness gap, found by user
inspection, not by running the checker first.** The original lockout
sub-flow modeled the 5-attempt counter as a guard on a `LoggedOut`
self-loop (`attempt_count < 5` / `>= 5`) -- which hid 4 real, distinct
security states (1/2/3/4 prior failures) behind one guard variable, and
hiding them is exactly what let a real gap go unnoticed: nothing in that
model ever asked "what happens on a VALID login after 1, 2, 3, or 4 prior
failures?" User: "shall we revisit requirement management part?"

Fixed for real in `demo_data/login_example.py`: re-modeled with explicit
`Failed1`-`Failed4` states, each getting its own real, distinct,
EARS-conformant Requirement/AcceptanceCriterion -- both for the
failure-count increment (`t2a`-`t2d`) AND the "valid credentials still
succeed from here" recovery path per state (`t1b`-`t1e`), plus the
lockout transition retargeted from `Failed4` (was `LoggedOut`). Real
Transition count: 9 implemented -> **16 implemented** + 1 planned (2FA
enrollment, unchanged). Verified live, not assumed: all 17 real
Requirement texts re-checked through the actual `check_ears_conformance`
(all conformant); `check_determinism` finds 0 ambiguous pairs;
`check_reachability` finds 0 unreachable states; **the exact original
gap is confirmed closed** -- none of `LoggedOut`/`Failed1`-`Failed4` are
missing either login-flow trigger anymore (queried directly, not
inferred). `check_completeness` does report 73 gaps against the *whole*
login example, but 63 of those are the checker's own strict "every state
must handle every trigger used anywhere" definition correctly surfacing
expected non-applicability (e.g. `AccountLocked` has no `click_forgot_
password` handler -- correct, that form isn't reachable while locked
out), not real problems -- reported honestly to the user as the real
output, not smoothed over. DQ-024: 0 flagged, real AC coverage on all 16
implemented Transitions.

Also this session: restored real data that a prior full-database reset
(user's own explicit choice, a separate request) had wiped --
`load_dogfooding_corpus.py` (177 `DogfoodingItem` nodes),
`connectors/seed_mock_athena.py` (the mock Postgres backing
`application_code_connector.py` had never been touched by the Neo4j-only
reset, but its Neo4j-side checkpoint episodes had been wiped, so it
found nothing to resume from until re-seeded), `application_code_connector.py`,
and `cognify/code_graph_archaeology.py` (real `CALLS`/`IMPORTS`/
`INHERITS`) -- all re-run for real, confirmed via the 4 previously-failing
test files (`test_bm01_corroboration.py`, `test_neo4j_graph_store.py`,
`test_demo_data.py`, `test_test_skeleton_generation.py`) going green.

Verified for real at default scale (`factor=1.0`, seed 42): full 45-file
deterministic regression suite green, `KNOWN_LABELS` = 45 (Trigger/Guard
removed, net even after Session 12's TestCycle/TestExecution/
ApplicationConfiguration additions), real `VALIDATES` edges present, 0
`Trigger`/`Guard` nodes or `ON_TRIGGER`/`WHEN_GUARD` relationships
anywhere.

**Round 4 — two more real, same-session follow-ups.**

1. **`check_guard_completeness()`** (`metis_mcp/behavior_model.py`), on
   the user's own request: `check_determinism()`'s `guards_conflict()`
   already checks that guards on a shared `(State, trigger)` don't
   overlap (atomicity) -- nothing checked the complementary property,
   that they jointly cover the *whole* domain (completeness). A real
   input matching none of the guards would silently match no transition
   at all, invisible anywhere in the graph. Built as the natural sibling
   of the existing interval-based overlap check (same `_parse_guard`/
   `_interval_for` machinery, same fail-closed discipline -- unparseable
   guards or guards on different variables are flagged unverifiable, not
   assumed complete). Verified for real: 0 findings against the live
   login example (expected -- the `Failed1`-`Failed4` redesign already
   made every `(state, trigger)` pair map to exactly one transition, so
   there's no multi-guard group left to check), and a new dedicated test
   fixture (`test_behavior_model.py`) proves it catches a genuine gap
   (`severity >= 0.9` / `severity < 0.5`, leaving `[0.5, 0.9)`
   uncovered) and doesn't false-positive on a real jointly-exhaustive
   group. `docs/metis-ontology-specification.md` gained real guidance on
   when a condition should become an explicit State (bounded, enumerable,
   durable) vs. stay a guard (continuous, per-request, or combinatorial).
2. **`FROM_STATE`/`TO_STATE` renamed to `LAUNCHES`/`LANDS_IN`**, with
   `LAUNCHES` direction reversed (was `Transition-[:FROM_STATE]->State`,
   now `State-[:LAUNCHES]->Transition`). User's own reasoning: this makes
   the whole thing read as one continuous forward path,
   `State-[:LAUNCHES]->Transition-[:LANDS_IN]->State`, instead of two
   edges both originating at the Transition -- and matches the rest of
   the ontology's verb-phrase convention (`TRACES_TO`, `VALIDATES`,
   `EXECUTES`, ...), which `FROM_STATE`/`TO_STATE` never did. Real,
   incidental find: neither `FROM_STATE` nor `TO_STATE` ever had a
   relationship-property index in schema-02 (an oversight); `LAUNCHES`/
   `LANDS_IN` get one now, closing that gap at the same time. Touched 5
   real files (`behavior_model.py`, `test_skeleton_generator.py`,
   `login_example.py`, `structural_validation.py`'s
   `ALLOWED_RELATIONSHIPS`, the ontology spec doc) -- no test file
   referenced the old names directly, so none needed changes.

Re-verified after both: full 45-file regression suite green, live graph
showed 17 real `LAUNCHES`/17 real `LANDS_IN` edges, 0 `FROM_STATE`/
`TO_STATE` anywhere.

**Round 5 — one more rename, same session**: `LAUNCHES`/`LANDS_IN` ->
`WHEN`/`THEN` (direction unchanged from Round 4 -- still
`State-[:WHEN]->Transition-[:THEN]->State`), explicitly to mirror the
Given/When/Then shape a Transition already structurally is: the State
it's reached from is the implicit "Given," `WHEN` this edge fires is the
Transition, `THEN` this edge's target State is the result. Same 5 real
files touched as Round 4 (`behavior_model.py`, `test_skeleton_generator.py`,
`login_example.py`, `structural_validation.py`'s `ALLOWED_RELATIONSHIPS`,
the ontology spec doc), same schema-02 index rename (`rel_launches_t_valid`/
`rel_lands_in_t_valid` dropped live, `rel_when_t_valid`/`rel_then_t_valid`
created). Re-verified: full 45-file regression suite green, live graph
shows 17 real `WHEN`/17 real `THEN` edges, 0 `LAUNCHES`/`LANDS_IN`/
`FROM_STATE`/`TO_STATE` anywhere.

**Round 6 — `functional_areas`, same session**: an optional string-array
property, real and requested, added to the whole backbone + behavior-
model chain (`Intent`, `Requirement`, `AcceptanceCriterion`,
`TestDesign`, `TestCase`, `State`, `Transition`) so a one-line query
finds everything in a named functional area (`MATCH (t:Transition)
WHERE 'login' IN t.functional_areas RETURN t`). Property, not a node --
matches this project's existing `Goal.domain` precedent for lightweight
domain tagging, not a rich referenceable entity (disclosed escalation
path if that changes: promote to a real `FunctionalArea` node later, not
built preemptively). All 17 real login-example Transitions tagged for
real (`"login"` plus a specific sub-flow: `"login-successful"` for
`t1`/`t1b`-`t1e`, `"login-failed"` for `t2a`-`t2d`/`t3`, `"password-
reset"`/`"session-management"`/`"account-recovery"`/`"2fa"` for the
rest) -- every downstream Intent/Requirement/AcceptanceCriterion(s)/
TestDesign/TestCase(s) spawned from a Transition inherits its same tags.
`State` is the one real wrinkle: shared across multiple Transitions
(`LoggedOut` alone is touched by 5, across 5 different sub-flows), so its
`functional_areas` is a real Python-side union built during the main
loop and SET once at the end, not per-transition (which would have
silently kept only the last transition's tags). Two new regression tests
in `test_login_example.py` prove both the one-line query returns exactly
the right, disjoint Transition sets and the union logic is real (`Logged
Out` ends up tagged with all 6 real areas that touch it). `docs/
metis-ontology-specification.md` documents this as a new cross-cutting
section. Full 45-file regression suite green.

**Round 7 — demo generator reset: focus on login + metis, minimal gap-fill
instead of a large synthetic company, same session**: user request,
verbatim: "reset Demo data generation to focus only on login and metis,
fill the gaps but remove the need for large amount of data" plus a
standing-practice instruction to wipe+regenerate demo data after any
graph-impacting change going forward, without being asked each time.
Since Session 6, `demo_data/generate_demo_data.py` had generated a large,
fully-fictional ~50-Goal/~5,000-Requirement synthetic company (~40,000-
50,000 nodes at `factor=1.0`) to simulate "production scale." By Session
13, the two REAL sources -- `demo_data/login_example.py` (hand-authored
login state machine) and `demo_data/metis_grounded.py` (75 real
Requirements grounded in this repo's own `corpus/*.md`) -- had become the
actually valuable part of the dataset; the large synthetic layer around
them was pure volume with no traceability value of its own.

**Two real, load-bearing findings from reading the old generator before
touching it, both confirmed live, not assumed:**
1. The old Architecture layer's `Service.owner_team` was set from
   `vocab.SERVICES` (fictional company service names -- "payments,"
   "fraud-detection," etc.), which had never shared a single value with
   any real `Goal.domain` (only `metis_grounded.py`'s real 18 subsystem
   prefixes ever populate that property). `test_demo_data.py`'s own
   `test_goals_carry_domain_and_some_requirements_trace_to_a_release`
   already checks for this join -- a real, previously-latent bug the old
   generator's large synthetic Business layer happened to paper over by
   giving `Service.owner_team` SOME `Goal.domain`-shaped string, just
   never the real one.
2. `Requirement-[:TRACES_TO]->Release` only ever existed via the old
   synthetic layer's "shipped" (Jira `Done` + `auto_write`-confidence)
   Requirements -- removing that layer removes the only source of this
   edge unless a real substitute exists.

**Fixed by keying the new gap-fill layer to the real 18
`metis_grounded.GROUNDED_GOALS` domain prefixes instead of a second,
disconnected fictional vocabulary**: the new Architecture layer's Service
pool is one Service per real prefix, `owner_team = prefix.lower()` --
genuinely equal to `metis_grounded.py`'s own real `Goal.domain` value, not
just shaped like it. Release linkage now traces a subset of
`metis_grounded.py`'s own real `Requirement`s that already carry
`jira_status: 'Done'` (written by that module already, nothing new) to a
small new `Release` pool.

**Removed entirely**: the large synthetic Business layer (Goal ->
Capability -> Epic -> Feature -> Requirement, the 50-150-per-Goal target
loop, the EARS-pattern-cycling text generator), the `vocab.SERVICES`-keyed
Architecture layer, the per-service Implementation layer (Repository/
Class/Method pool sized only to give the synthetic Requirements something
to `IMPLEMENTS` -- with the synthetic Requirements gone, that pool had no
purpose; `login_example.py`/`metis_grounded.py` already create/reuse their
own real, much smaller Class/Method data), the synthetic per-Goal/Feature
Confluence-episode block (`metis_grounded.py` already creates real
Confluence episodes from this repo's own README/PLAN/CLAUDE.md/docs/*.md
-- no need for a second, fabricated source), and `Action`/`Event`/
`Workflow` (zero relationships to anything, confirmed by Session 11's own
grep and never revisited -- pure count-padding, dropped rather than
shrunk). `login_example.py` and `metis_grounded.py` themselves were **not
modified** -- both already real, already correctly scaled, and the whole
point of this reset.

**Added**: a small, coherent gap-fill layer (order of 10s per label, not
1,000s) covering the ontology labels neither real source touches --
Governance (`Constitution`/`ExternalAPISpec`/`Constraint`/`BusinessRule`/
`MicroRequirement`), Architecture (`Service`/`API`/`Endpoint`/`Database`
`-[:HAS]->Table` with real `record_revision()` calls/`Column`/
`KafkaTopic`/`ExternalSystem`/`ApplicationConfiguration`
`-[:INCLUDES_VERSION]->Service`), VCS (`PullRequest`
`-[:PRODUCES]->Commit`/`Branch`), Testing bulk (`TestSuite`/`TestCycle`/
`TestExecution`/`AutomationScript` -- built AROUND the real `TestCase`
pool `login_example.py`/`metis_grounded.py` already wrote, queried back
from the graph, never a new fabricated `TestCase` pool), and Operations
(`Release`/`Incident`/`Alert`/`Metrics`/`Logs`/`Defect`, `Defect`
`PRODUCES`'d from real failed `TestExecution`s). `vocab.py` is kept (still
used for realistic Table/Defect/Incident/PR text) but no longer drives
Service/domain identity. `Scale`/`factor` is preserved exactly, now
scaling only this small gap-fill layer -- `login_example.py`/
`metis_grounded.py` always write their full real content regardless of
`factor`, same as before.

**Verified live, not assumed**: full regeneration at default scale
(`factor=1.0`, seed 42) now produces **1,238 nodes / 1,554 relationships**
across 41 distinct labels and 17 distinct relationship types (was ~63,710
demo nodes under the old generator, confirmed by wiping it before this
change) -- comfortably clears `test_generate_spans_many_labels_and_
relationship_types`'s `>=30` labels / `>=8` relationship-types thresholds
without padding. All 7 `test_demo_data.py` tests pass, including both
previously-fragile ones (`test_goals_carry_domain_and_some_requirements_
trace_to_a_release`'s `Service.owner_team = Goal.domain` join now
genuinely resolves; `Requirement-[:TRACES_TO]->Release` edges now exist
for real). `test_login_example.py`'s full 9 tests pass unmodified,
confirming `login_example.py` still integrates cleanly with the smaller
`generate()`. `metis_generate_quality_report`'s `service_id` scope was
spot-checked directly against a real new Service id
(`demo:service:acd`) and correctly resolved, via the real `Service.
owner_team = Goal.domain` join, to all 9 real ACD-domain grounded
Requirements. Full 43-file deterministic regression suite green (0
failures). No schema changes were needed -- this was a generator-only
reset; every label/relationship type reused is already in the closed
ontology `structural_validation.py`/the ontology spec doc define.

**Standing practice adopted going forward** (the request's second,
durable instruction, not a one-time action): after any change that
touches the graph (schema, generator, or ontology), wipe + regenerate
demo data and re-run the affected tests as a normal part of finishing the
change -- without waiting to be asked each time. This was already the de
facto pattern for the last several rounds of Session 13's own work
(Rounds 1-6 above); this makes it an explicit, standing convention rather
than an implicit habit.

## Historical Summary (Sessions 2-12) — durable facts only

The detailed round-by-round narration for these sessions was trimmed on
2026-08-09 (it described intermediate designs since superseded by Session
13, e.g. the `LAUNCHES`/`LANDS_IN` naming and the removed AI-session
layer). Only end-state facts that still matter are kept below; the current
schema/architecture is authoritative over anything summarized here.

- **TestCycle/TestExecution/ApplicationConfiguration** (Session 12): `TestRun`
  was renamed `TestCycle`. Each (TestCycle, TestCase) pair gets its own real
  `TestExecution` node (`executed_at`/`result`), `PART_OF->TestCycle`,
  `EXECUTES->TestCase`, `PRODUCES->Defect`, `RAN_AGAINST->ApplicationConfiguration`.
  `ApplicationConfiguration-[:INCLUDES_VERSION {version}]->Service` tracks
  per-execution component versions as edges, not properties.
- **Behavior scope + LLM-session layer removed** (Session 11): State/Transition/
  Trigger/Guard data comes solely from `demo_data/login_example.py` (a real,
  hand-authored login-page state machine) — an earlier generic 80-State/
  300-Transition "ring" was pure count-padding and was deleted. A speculative
  6-label "AI session" layer (`CopilotSession`/`Prompt`/`GeneratedCode`/
  `AIDecision`/`HumanReview`/`Cache`) had zero real relationships and was
  removed entirely, except `GeneratedTest` (genuinely used by
  `test_skeleton_generator.py`, kept). `Database-[:HAS]->Table` added with
  real revision history. Staleness/drift detection (`graph_sync.py`) extended
  to a second connector (Confluence).
- **Intent/TestDesign backbone** (Session 10): `Intent` (hub node) and
  `TestDesign` are the real backbone Requirements/tests derive from.
  `TestCase.type` is a real 6-value taxonomy. `Transition.implementation_status`
  (`implemented`/`planned`) excludes not-yet-built behavior from coverage-gap
  computation. Every node gets real provenance via `temporal.py`'s
  `record_revision()`. `metis_generate_test_design_report` MCP tool + site page
  added. `DQ-014` (spec-drift detection) made real.
  **Deferred, still open**: linking State/Transition to real DB tables/components
  (multi-table-per-transition modeling) — discussed, not built.
- **VERIFIES targets AcceptanceCriterion, never Requirement directly** (Session 9)
  — a real ontology bug fix, applied everywhere (demo generator, pyramid gap
  check, DQ-017, coverage map). A Requirement can have multiple ACs; only the
  AC gets verified by a TestCase.
- **Scoped quality/release reports** (Session 8): `metis_generate_quality_report`
  (scope = release/service/requirement/project-wide) and
  `metis_generate_release_report`, with real functional/performance/security
  scorers (`PERF-01`, `SEC-01`/`SEC-02`) and a deterministic `gate_status`.
  Required adding real `Goal.domain`/`Requirement-TRACES_TO->Release` data,
  which hadn't existed before.
- **Demo data, grounded + then removed** (Sessions 3/6/7, reversed in Session
  13): a large ~50-Goal synthetic-company generator (Session 6, targeting
  40-50K nodes) plus a grounded layer from this repo's own `REQ-METIS-*` corpus
  tags (Session 7) were built up over three sessions. **Session 13 Round 7
  removed the entire large synthetic layer** as "pure volume with no
  traceability value of its own" — only `login_example.py` and
  `metis_grounded.py` (the real, grounded content) remain as demo data sources
  today. Don't rebuild the large synthetic layer without a real reason.
- **Full-project re-audits** (Sessions 4, 5): closed a series of real,
  previously-undocumented spec/plan gaps (Constitution hard-block GRD-11,
  cost-confirmation gate COST-08, Academy/Site/PPTX renderers, Copilot
  integration file, real Confluence/JSM/Compass connectors, CONST-036
  calibration run at real ceiling). Found and fixed a systemic
  `DogfoodingItem` id-collision bug (label-agnostic Cypher `MATCH` could hit
  a dogfooding shadow node sharing an id with a production node — fixed with
  explicit `WHERE NOT ...:DogfoodingItem` exclusions across 5+ call sites) and
  a Neo4j driver retry-idempotency bug (bare `CREATE` on a pre-computed id
  isn't safe against transaction retries — fixed with `MERGE ... ON CREATE
  SET` across 5 files, 2 of which predated Session 5 entirely).
- **Everything previously descoped got built** (Session 2): real LLM calls via
  the `claude` CLI (no `ANTHROPIC_API_KEY` in this environment) power Layer 6
  LLM-as-judge, `MicroRequirement` decomposition, and a real (small-scale)
  `CONST-036` calibration batch. Code-graph corroboration
  (`cognify/code_graph_archaeology.py`, AST-based, no LLM) and 4 more
  connectors were added. Live k8s deployment surfaced and fixed 5 real Helm
  chart bugs (missing Secret wiring, dead env-var overrides, `values-*.yaml`
  array-replace-not-merge drop, missing `METIS_HOME` on `mcp-server`,
  `readOnlyRootFilesystem` misplaced at pod- instead of container-level).

## What's real vs. what's scaffolded — know this before touching anything

**PLAN.md now has full, phase-by-phase detail on everything below,
including every real bug found and fixed while building it — this section
is a summary, not the full record.** As of the most recent session,
Phases 1-9 are done and Phase 10 is done with a significant caveat (below).

- **`metis-server/`** is real, tested Python — an MCP server with 16 working
  tools (stdio AND, as of Phase 6, OAuth2-gated Streamable HTTP, now
  **live-deployed**, see the Session 2 addendum above), a real
  `Neo4jGraphStore` alongside the original dogfooding `LocalGraphStore`, a
  real, complete six-connector set (`application-code`, `flat-files`,
  `test-suite-ingest`, `locust-performance`, `bmad-method-specs`,
  `grafana-metrics`, `atlassian-prod`), a real Cognify structural-extraction
  pass plus real code-graph archaeology (`CALLS`/`IMPORTS`/`INHERITS`), real
  Layer 2/3/6 guardrail gates (Layer 6 makes real model calls, see above),
  real `MicroRequirement` decomposition, a real reviewer-UI API, real
  OAuth2/RBAC, real determinism/completeness/reachability/`BM-01`
  corroboration checks, and a real `guardrail-corpus-runner` +
  `ingestion-worker` (both live-deployed) — **~227 tests passing** across
  41 test files, plus 4 LLM-calling test files that are real but
  deliberately excluded from routine regression runs since they cost real
  money per run (run them all before touching anything, see below — this
  number will drift as work continues; trust the actual test run, not this
  sentence, if they disagree).
- **`plugins/metis/skills/` (moved from `metis-server/.agents/skills/`) — significant discovery: the real
  `metis-review-assist` skill this file used to describe here did not
  exist anywhere in this copy of the project.** The whole `.agents/`
  directory was absent — same category of gap as the `pyproject.toml` bug
  below (didn't survive the move to this machine), just not noticed until
  Phase 10 actually went looking for it. By explicit user decision, it was
  **reconstructed** (grounded in `metis-specification.md` §9.2's real RPI/
  Stage-Confirmation text and this codebase's real, currently-callable
  tool signatures — disclosed as a reconstruction, not the original) and
  two new skills were built against that reconstructed template:
  `metis-behavior-modeling` and `metis-onboarding`. If you find a REAL
  original `metis-review-assist` elsewhere, prefer it over the
  reconstruction and re-check the other two skills still match its actual
  shape.
- **`metis-chart/`** is a real Helm chart. `helm lint`/`helm template` have
  now actually been run (Phase 9) and found three real bugs, now fixed: a
  missing `secrets: {}` default, a YAML-breaking hardcoded single-quote
  around the `image:` field, and — the significant one — **no
  `ServiceAccount` resource was ever defined**, despite every Pod spec
  referencing one by name; the chart would have failed at pod admission in
  any real cluster, regardless of images. It has also now been **deployed
  for real** (Docker Desktop's local Kubernetes) with a real, locally-built
  `metis-guardrail-corpus-runner` image, and the CronJob was confirmed
  firing on schedule three times in a row with real successful output.
  `mcp-server`/`ingestion-worker` are now **also live-deployed**, reaching
  the real host-run Neo4j/Postgres over the network — see the Session 2
  addendum above for the five more chart bugs that surfaced getting there.
- **`docs/`** is real design work — architecture, ontology, a 64-rule
  Constitution across 5 Amendments, cost analysis grounded in real
  computed numbers, not estimates.
- **Constitution-to-code enforcement has grown well beyond one rule set,**
  but is still not all 64. Real code now enforces (with real tests):
  `CONST-051/052/053` (classification gate), `CONST-047`-adjacent structural
  validation and `CONST-036`-adjacent confidence tiering (Phase 4),
  `CONST-048/049` (state-machine determinism/completeness/reachability,
  Phase 8), `CONST-057/058` (adversarial corpus runner, Phase 9), and
  `CONST-064` (OAuth2 token lifecycle, Phase 6). Most of the Constitution's
  remaining rules still govern behavior with no code connecting "a rule
  exists" to "code checks it" — don't assume enforcement just because a
  rule is numbered; grep for its `CONST-*` id in `metis-server/` before
  relying on it being live.
- **Genuinely not built, and why:** real Confluence/JSM/Compass ingestion
  (only `atlassian-prod`'s Jira-issue path is wired up), and `CONST-036`'s
  calibration at its actual specified 500-unit scale (this build ran 8
  real cases — real calls cost real money, and running 500 wasn't asked
  for). Everything else that used to be listed here as blocked
  (`MicroRequirement` decomposition, Layer 6 LLM-as-judge,
  `REQ-METIS-BM-01` corroboration, the four remaining connectors) is now
  built — see the Session 2 addendum above.

## First thing to do in this session

Verify nothing broke in the move to this machine — don't assume it's fine:

```bash
cd metis-server
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python3 test_config_manager.py      # 4 tests, no external dependency
.venv/bin/python3 test_classification_gate.py  # 8 tests, no external dependency
.venv/bin/python3 test_ears_checker.py          # 7 tests, no external dependency
.venv/bin/python3 test_e2e.py                  # real MCP client, 16 tools (graph.backend: local by default)

# The pytest suite starts its own disposable Neo4j automatically through
# metis-server/neo4j_test_support.py. It applies schema 01/02/03, loads the
# 177-item dogfooding corpus into that container, points subprocesses at a
# temporary config, and force-removes the container at session end. Tests
# never write to the deployed ~/.metis/config.json graph.
#
# The application-code connector still needs the separate mock Athena Postgres:
# Podman, not Docker (Session 9), provides the same Dockerfile-compatible,
# rootless-by-default semantics.
podman run -d --name metis-athena-mock -p 5432:5432 \
  -e POSTGRES_USER=athena -e POSTGRES_PASSWORD=athena-mock-pass -e POSTGRES_DB=athena_mock \
  postgres:17
# Apply connectors/mock_athena_schema.sql against Postgres. Athena still uses
# its password_env setting:
export METIS_ATHENA_PASSWORD=athena-mock-pass
.venv/bin/python3 test_neo4j_graph_store.py            # 10 tests
.venv/bin/python3 test_application_code_connector.py   # 3 tests, real SIGKILL resumability test
.venv/bin/python3 test_structural_extraction.py        # 5 tests
.venv/bin/python3 test_structural_validation.py        # 9 tests
.venv/bin/python3 test_confidence_tiering.py           # 9 tests
.venv/bin/python3 test_guardrail_pipeline.py           # 5 tests
.venv/bin/python3 test_review_api_server.py            # 3 tests
.venv/bin/python3 test_oauth2.py                       # 7 tests
.venv/bin/python3 test_rbac.py                         # 4 tests
.venv/bin/python3 test_flatfiles_connector.py          # 3 tests
.venv/bin/python3 test_test_suite_connector.py         # 4 tests
.venv/bin/python3 test_behavior_model.py               # 7 tests
.venv/bin/python3 test_http_transport.py               # 2 tests, no external dependency
.venv/bin/python3 test_corpus_runner.py                # 3 tests (1 needs Neo4j)
.venv/bin/python3 test_bm01_corroboration.py           # 3 tests
.venv/bin/python3 test_code_graph_archaeology.py       # 4 tests
.venv/bin/python3 test_demo_data.py                    # 5 tests
.venv/bin/python3 test_locust_performance_connector.py # 2 tests
.venv/bin/python3 test_atlassian_connector.py          # 2 tests (real mock Confluence/JSM/Compass)
.venv/bin/python3 test_bmad_method_connector.py        # 2 tests
.venv/bin/python3 test_grafana_connector.py            # 1 test
# Session 4 addendum -- the 16-item spec/plan gap audit:
.venv/bin/python3 test_test_skeleton_generation.py     # 8 tests -- Behavior Model Stage 3/4/5
.venv/bin/python3 test_requirement_quality.py          # 7 tests -- CONST-047 deterministic checks
.venv/bin/python3 test_temporal.py                     # 7 tests -- §5.4 + Layer 10 rollback
.venv/bin/python3 test_layer8_heuristics.py            # 6 tests -- Layer 8 (REQ-METIS-GRD-08)
.venv/bin/python3 test_dq_metrics.py                   # 23 tests -- full DQ-001..023 + composite score
.venv/bin/python3 test_mcp_contracts.py                # 1 test -- CONST-062, real MCP subprocess
.venv/bin/python3 test_manifest_validator.py           # 5 tests -- connector manifest schema validation
.venv/bin/python3 test_token_optimization.py           # 11 tests -- §9.1 Caveman/Headroom/Cache-Aligner
.venv/bin/python3 test_hybrid_retrieval.py             # 7 tests -- §8.2
.venv/bin/python3 test_pinned_memory.py                # 5 tests -- §8.1
.venv/bin/python3 test_sleep_time_consolidation.py     # 4 tests -- §8.3
.venv/bin/python3 test_memify.py                       # 6 tests -- §8.4
.venv/bin/python3 test_copilot_integration.py          # 4 tests, no external dependency
# Session 5 addendum -- fresh full-project re-audit, 4 of 8 real gaps closed:
.venv/bin/python3 test_constitution_gate.py            # 6 tests -- GRD-11 Constitution hard-block
.venv/bin/python3 test_cost_gate.py                    # 6 tests, no external dependency -- COST-08
.venv/bin/python3 test_academy.py                      # 7 tests -- §12 Academy content-assembly
.venv/bin/python3 test_site_and_pptx_renderers.py      # 3 tests -- §12.5 Site + §4.6.1 PPTX renderers
# Session 10 addendum -- Intent/TestDesign backbone + staleness/drift detection:
.venv/bin/python3 test_login_example.py                # 7 tests -- real login-page Intent/TestDesign backbone
.venv/bin/python3 test_graph_sync.py                   # 3 tests -- staleness + drift detection (2 proof connectors as of Session 11)
# Two-stage intake mining (Requirement/AC derivation from any Episode's raw_content).
# All three are FREE to run: no Neo4j, no model calls, no config -- Stage 2's tests
# inject a stub `call`, and Stage 4's test the pure planner, not the writer.
.venv/bin/python3 test_intake_segmentation.py          # 13 tests -- Stage 1 deterministic triage
.venv/bin/python3 test_requirement_mining.py           # 13 tests -- Stage 2, LLM stubbed
.venv/bin/python3 test_requirement_landing.py          # 13 tests -- Stage 4 chain planning + edge legality
# Skill marketplace (plugins/metis + plugins/metis-mcp). Both free to run.
.venv/bin/python3 test_skill_catalog.py                # 13 tests -- skill/router/agent drift checks
.venv/bin/python3 test_marketplace_manifest.py         # 9 tests -- marketplace + plugin manifest shape
.venv/bin/python3 test_uif_intake.py                   # 10 tests -- UIF -> Episode landing (ported intake-processor)
```

LLM-calling test files (real, costed, deliberately excluded from the list
above -- run explicitly, not as part of routine regression):
`test_llm_judge.py`, `test_microrequirement.py`, `test_calibration.py`,
`test_requirement_quality_llm.py`.

If `pip install -e .` fails with a "Multiple top-level packages discovered"
error, that's a known bug already fixed in this copy's `pyproject.toml`
(`packages = ["metis_mcp"]` under `[tool.setuptools]`) — if you see it
anyway, the fix didn't survive the copy; check that section is present.

Two more known-fixed bugs, found the same way (running the real thing, not
assuming it works): `test_e2e.py` used to hardcode
`/home/claude/metis-server` as the subprocess command/cwd (a Claude Desktop
sandbox path) — fixed to use `sys.executable` and the script's own
directory. And `mcp>=1.0.0` (unpinned) resolves to `mcp==2.0.0`, which
reorganized the SDK and removed `mcp.server.fastmcp.FastMCP` entirely,
breaking `server.py` on import — pinned to `mcp>=1.0.0,<2.0.0` in both
`pyproject.toml` and `requirements.txt`. If either regresses, that's the
fix.

## Key decisions already made — don't re-litigate these without a real reason

- **Single database: Neo4j Enterprise.** No separate Postgres — episode log,
  review queue, cost tracking, and RBAC are all Neo4j-native. Decided after
  reference scale numbers (100K Jira tickets, 15K tests, 1M+/month executions)
  and after confirming Enterprise licensing was needed anyway for HA.
- **ETL reuse, not rebuild.** Métis reads FROM Athena's (a real, existing
  ETL system) already-populated tables via the `athena_internal_read`
  connector protocol — it does not re-fetch from Git/Jira/etc.
  independently. About half the connectors originally planned turned out
  to be unnecessary once this was checked against Athena's real modules.
- **No configuration in code.** Model names, ZDR status, and per-repository
  data-sensitivity classification all resolve through `config_manager.py`
  from `.metis/config.yaml` (project) or `~/.metis/config.yaml` (host),
  modeled on a real internal config-resolution convention. The server
  refuses to start if neither file exists — this is deliberate.
- **No commercial ZDR agreement with Anthropic right now** — an explicit,
  current decision (not a stalled task), recorded in
  `.metis/config.yaml` and `docs/metis-const-053-confirmation-record.md`.
  Standard API terms (no training, 30-day auto-delete) are being treated as
  sufficient. Most repositories should be classified `public_internal`
  under this decision, not left to fail closed as `confidential`.
- **Claude first, Copilot in parallel** — not Copilot-first-Claude-deferred.
  Both connect to the identical MCP server; only the discovery/config layer
  differs per client (see `docs/metis-multi-client-integration.md`).
- **Podman, not Docker, for local dev dependencies** (Session 9). The 3
  real Dockerfiles (`metis-server/Dockerfile.*`) stay named `Dockerfile.*`
  unchanged — Podman reads that format natively, `podman build -f
  Dockerfile.mcp-server` works identically to `docker build`, no
  functional reason to rename. The Session 2 addendum's real, historical
  deployment to "Docker Desktop's built-in Kubernetes" is left as written
  (it's a factual record of what was actually run then, not a standing
  instruction) — but **any future real cluster deployment work should use
  `kind` or `minikube` with the podman driver instead**, since Podman has
  no Docker-Desktop-equivalent bundled Kubernetes control plane. Not yet
  needed again since Session 2's live deployment — flagged here so the
  next person doing cluster work doesn't reach for `docker` by habit.

## The concrete next build tasks

**All ten phases, everything originally descoped, the full Session 3 (now
Session 4's own numbering — see PLAN.md) spec/plan gap audit, and 4 of the
8 gaps Session 5's fresh full-project re-audit found are now done.** Don't
re-derive this file's old task list; it's stale as of this update. The
real remaining work:

1. **A real original `metis-review-assist`**, if one turns up elsewhere —
   the current one under `plugins/metis/skills/` is a disclosed reconstruction
   (see above); if a real original is found, prefer it and re-check
   `metis-behavior-modeling`/`metis-onboarding` still match its actual shape.
2. **§8.2's semantic/vector retrieval mode** — still genuinely blocked, no
   embedding model available in this environment (verified: no Ollama, no
   sentence-transformers, no OpenAI-compatible endpoint). The 4 real HNSW
   vector indexes exist and would work the moment a real embedding
   pipeline populates `embedding` properties — `metis_mcp/hybrid_
   retrieval.py`'s `semantic_vector_search()` refuses to fake it.
3. **Retrofitting every existing write path to call `metis_mcp/temporal.py`'s
   `record_revision`** — the real versioning/rollback mechanism exists and
   is tested, but `structural_validation.py`/`confidence_tiering.py`/the
   connectors don't call it on every write yet; that's a separate,
   larger integration task across every write path, not something this
   session's build claims is already wired in everywhere.
4. **`REQ-METIS-MTX-01..03`** — writing guardrail metrics as new objects
   in Athena's real schema catalog + a Grafana dashboard JSON alongside
   `DefectsStatistics.json`/`RegressionStatistics.json`. Not built — only
   a mock Athena connector exists in this environment, no real Athena
   schema-catalog/Grafana surface to write into.
5. **`REQ-METIS-RES-01..04`** — the specific resumability property
   vocabulary (`delta_type ∈ {ADDED,MODIFIED,REMOVED}`, `checkpoint_status
   ∈ {PENDING,COMMITTED,FAILED}`). Connectors already have their own real,
   working, tested checkpoint patterns (see `application_code_connector.py`'s
   docstring) — just not this exact uniform vocabulary across all of them.
6. **`REQ-METIS-CPT-06`** — a GitHub required status check
   (`metis/spec-conformance`). Not built — no CI integration exists in
   this environment.

## Working style for this project — carried over deliberately

This project has a real, demonstrated pattern: claims get checked, not
assumed, and when a check finds a bug, that gets fixed and disclosed, not
smoothed over. Concrete precedent, not just a stated value — three real
bugs were caught this way and are worth knowing about:

1. A corpus parser initially attributed a rule's definition to the wrong
   file, purely because of alphabetical processing order — caught by
   spot-checking actual output against known content, not by code review.
2. Cross-references from citations in other files were silently dropped —
   caught the same way, by checking a specific expected value and finding
   it missing.
3. `pyproject.toml` was broken from the start (`pip install -e .` failed)
   but never caught because earlier testing only ever installed
   dependencies directly, never ran the actual install command a real user
   would run.

Keep that pattern: when you build something, run it for real and check a
specific, verifiable output — don't just confirm it doesn't crash on import.

## Genuinely open items (don't invent solutions to these unprompted — ask)

- Zero Data Retention agreement status with Anthropic — a real business
  decision already made for now (see above), not a technical task.
- A real original `metis-review-assist` skill, if one exists elsewhere —
  the current one is a disclosed reconstruction (see above).
- §8.2's semantic/vector retrieval mode — blocked on a real embedding
  model existing in this environment, not a code gap (see "concrete next
  build tasks" above).
- Actual Copilot live-connection verification, and the real OAuth2
  provider/hostname decision behind it — `metis_mcp/copilot_integration.py`
  generates the real discovery artifact from config, but there's no live
  Copilot instance here to connect it to and confirm end-to-end.
- `REQ-METIS-MTX-01..03` (Athena metrics/Grafana dashboard integration),
  `REQ-METIS-RES-01..04` (the uniform resumability vocabulary), and
  `REQ-METIS-CPT-06` (a GitHub required status check) — Session 5's
  re-audit found these real; the user chose not to build them this round
  (see "concrete next build tasks" above for why each is still open).
- Real Confluence/JSM/Compass ingestion, real Copilot config generation,
  the `CONST-036` calibration batch, GRD-11/SKL-01-02/COST-08, and the
  full §12 Academy/Site/PPTX system are now all built — see PLAN.md's
  Session 3 addendum and this file's Session 4/5 addenda above.
