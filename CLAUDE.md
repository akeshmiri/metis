# Métis — Project Context for Claude Code

Save this file as `CLAUDE.md` at the project root (`/Users/akeshmiri/Projects/claude/`)
so it loads automatically every session — or paste it directly into a new
Claude Code conversation to start one.

## What this project is

Métis is an AI-driven specification and requirements knowledge-graph
platform for Quality Engineering: it ingests requirements, code, and tests
from multiple real sources, builds a bi-temporal graph with a formal
guardrail stack (anti-hallucination, corroboration, confidence tiering), and
generates real functional/performance tests layered on top of existing
unit/integration coverage.

**Read `README.md` first** — it indexes the full directory tree and says
where each piece lives. Don't re-derive the structure; it's already mapped.

## Session 9 addendum — fixed a real ontology bug: VERIFIES targets AcceptanceCriterion, not Requirement

User correction, stated directly: a TestCase should VERIFY exactly one
AcceptanceCriterion, never a Requirement directly; a Requirement can have
multiple AcceptanceCriteria; a Requirement cannot have a TestCase of its
own. Checked against this platform's own real, original spec before
changing anything — `specification-knowledge-graph-platform.md` (an
earlier foundational doc, still in `corpus/`) already says `TestCase` |
`VERIFIES→Transition/AcceptanceCriterion` — Requirement was never the real
target. `metis_mcp/layer8_heuristics.py`'s own `check_circular_traceability`
(DQ-018) independently confirms this: it already flags a Requirement with
a direct TestCase VERIFIES edge and no HAS_AC in between as suspicious.
So the demo generator (Sessions 6/7) and `metis_mcp/pyramid_gap_check.py`'s
functional-layer heuristic had both drifted from the platform's own real,
already-specified model — a real bug, not a new design choice.

**Fixed for real, across every place the wrong edge existed:**
- `demo_data/generate_demo_data.py`'s Testing layer now generates 1-2 real
  TestCases per AcceptanceCriterion (not per Requirement) — every
  Requirement still gets real test coverage, transitively, through its
  ACs (verified: 0/4,969 demo Requirements have zero transitive coverage
  post-fix). `demo_data/metis_grounded.py`'s grounded layer gets the same
  fix.
- `metis_mcp/pyramid_gap_check.py`'s "functional" layer signal now
  traverses `Method-[:IMPLEMENTS]->Requirement-[:HAS_AC]->AcceptanceCriterion
  <-[:VERIFIES]-TestCase` (previously skipped the AC hop entirely).
- `metis_mcp/dq_metrics.py`'s DQ-017 (end-to-end chain completeness) gets
  the same AC-mediated traversal fix.
- `demo_data/coverage_map.py`'s per-Goal coverage query, same fix.
- Test fixtures updated to match: `test_dq_metrics.py`'s `dqm-test-tc-good`
  and `test_quality_report.py`'s `qr-test-tc-a` now VERIFY their
  Requirement's AcceptanceCriterion, not the Requirement itself.
  `test_layer8_heuristics.py`'s direct-VERIFIES fixtures were deliberately
  left unchanged — that file is testing the circular-traceability
  *detector itself*, so a direct TestCase→Requirement edge with no HAS_AC
  is the intentional fixture for the anti-pattern being detected, not a
  bug to fix.

**Real bug caught while regression-testing this** (not by the user):
`test_dq008_functional_coverage_via_pyramid_gap_check` failed on first
re-run — turned out to be ~48K nodes of *stale* demo data (generated
before this fix) still loaded in the shared Neo4j instance, whose old-style
VERIFIES→Requirement edges no longer match the corrected functional-layer
query, dragging the DQ-metrics-are-global-not-demo-scoped assertion below
1.0. Confirmed by wiping demo data and re-running clean — not a code bug,
same class of test-isolation issue documented in the Session 7 addendum.

Verified for real: 0 direct `TestCase-[:VERIFIES]->Requirement` edges,
14,830 real `TestCase-[:VERIFIES]->AcceptanceCriterion` edges, 0 TestCases
verifying more than one AcceptanceCriterion, at full-scale regeneration
(**52,939 nodes** — up from ~48K since AcceptanceCriteria outnumber
Requirements, so per-AC test generation yields more TestCases than the
prior per-Requirement scheme). Both `metis_generate_quality_report`
tools re-verified live against the corrected data. Full regression suite
green.

## Session 8 addendum — two new MCP tools: real scoped quality reports

User request: a "detail quality report for the given label, version,
requirement" covering functional/performance/security, with executive +
detail sections in business language, plus a release report. Investigated
the existing `metis_quality_score` tool first rather than building from
scratch — found the real reason a new tool was actually needed: its
`scope` parameter is accepted by `server.py`, `academy.assemble_content`,
and `dq_metrics.compute_quality_score`, but **used by none of them** —
every individual `dq_XXX(session)` call ignores it entirely, so
`scope="payments"` and `scope="all"` returned byte-identical numbers. The
real, already-designed fix for the shape existed too:
`mcp-contracts/metis-mcp-tool-contracts.json`'s own `metis_quality_score`
entry already specifies the exact scope shape the user asked for —
`{release_id}` | `{service_id}` | `{requirement_id}` | `{project_wide:
true}` — never implemented, only specified.

**Two real, pre-existing schema gaps had to close first**, or the new
scoping would resolve to nothing: `Goal`/`Requirement` carried no real
domain/service property at all (the demo generator's `_svc` field was
Python-only bookkeeping, stripped before every write), and zero
`Requirement-[:TRACES_TO]->Release` edges existed anywhere in the graph
(confirmed by `dq_017`'s own pre-existing note). Fixed in
`demo_data/generate_demo_data.py`: `Goal.domain` is now persisted for
real, and a realistic subset of "shipped" synthetic Requirements
(`jira_status: Done` + `auto_write` confidence) now trace to a real
`Release`.

**Built:**
- `metis_mcp/quality_report.py` — `resolve_scope()` (the real 4-way scope
  resolution), and three real attribute scorers: functional (reuses
  `dq_003`/`dq_006`/`dq_008`, now scope-filterable via a new optional
  `requirement_ids` parameter on each), performance (a new `PERF-01`
  metric — SLA-critical Transition pyramid-gap performance-layer coverage,
  scoped), and security (a new `SEC-01`/`SEC-02` pair — `SEC-01` reuses
  GRD-04's real corroboration rule on scoped Risk=High Requirements;
  `SEC-02` (open Defects) is honestly `None` — no `TestRun->TestCase` edge
  exists anywhere in this codebase, so `Defect` nodes can't be traced back
  to any Requirement scope, same disclosed gap `dq_017` already
  documented). `build_report()` composes these into an executive summary
  (deterministic, template-generated business language — no new model
  call) plus a full per-metric detail breakdown, with a real
  `gate_status` (`clear`/`blocked_individual_gate`/
  `blocked_composite_threshold`) where any failing security/performance
  metric hard-blocks regardless of the functional composite score.
- `metis_generate_quality_report(scope, attributes=None)` and
  `metis_generate_release_report(release_id)` — new MCP tools in
  `metis_mcp/server.py`, both gated on `graph.backend: neo4j` (the real
  ontology this needs doesn't exist in dogfooding-mode's `LocalGraphStore`
  — same disclosed "adapted" pattern already used for
  `metis_propose_test_skeleton`/`metis_submit_episode`). The release
  report adds a real changelog (`academy.generate_changelog`, actual
  `:Revision` history) and a deterministic, rule-based ship/hold/no-ship
  recommendation derived from `gate_status` — never a model judgment call.
- Both tools added to `mcp-contracts/metis-mcp-tool-contracts.json` (a new
  shared `$defs.scope`, also now referenced by `metis_quality_score`'s own
  entry instead of duplicating the shape a third time) and to
  `test_mcp_contracts.py`'s `CASES` record (server tool count 9 → 11,
  including the now-stale `test_e2e.py`/`server.py` docstring references
  to "9 tools", all fixed).

**Verified for real** against both a deterministic fixture
(`test_quality_report.py`, 5 tests — proves `service_id` scope genuinely
returns a different, larger Requirement set than `requirement_id` scope,
and that an under-corroborated Risk=High Requirement genuinely flips
`gate_status` to `blocked_individual_gate`) and the live 48,035-node demo
graph: `service_id`/`release_id`/`requirement_id`/`project_wide` scopes on
the same graph returned real, different `requirement_count`/
`composite_score`/`gate_status` values (140 / 14 / 1 / project-wide-all,
composite 100.0 / 100.0 / 100.0 / 68.7) — concrete proof the filtering
gap is actually fixed, not just accepting the parameter. Full 43-file
regression suite green.

## Session 7 addendum — Demo Data grounded in Métis's own real project

User request: "use metis as a base for demo data and fill the gaps where
needed" — confirmed via AskUserQuestion to mean grounding the demo dataset
in Métis's own real artifacts, with synthetic generation only filling the
remaining scale gap. Added `demo_data/metis_grounded.py`, called from
`generate()` as an additive phase alongside the Session 6 fully-synthetic
layer (that layer is unchanged).

**What's real in the new layer, concretely:**
- **75 unique `REQ-METIS-*` tags** found in `corpus/*.md` via the
  already-proven `metis_mcp.corpus.parse_corpus()` (same parser
  `constitution_gate.py`/`load_dogfooding_corpus.py` reuse) — grouped into
  **18 real Goals**, one per subsystem prefix (GRD, ACD, BM, CONN, COST,
  CPT, ONT, ARCH, CG, ING, MEM, MTX, PG, RES, SKL, SLD, TMP, DQ).
- Each tag's real sentence is hand-paraphrased into one genuinely
  EARS-conformant Requirement (`metis_mcp/ears_checker.py`'s conformance
  check is a strict literal regex — raw corpus prose never matches it
  verbatim, so this couldn't be mechanical). Every paraphrase is
  re-validated through the real, unmodified `check_ears_conformance` and
  `ConfidenceTiering.evaluate()` at generation time — same no-force-tag
  discipline as the synthetic layer — and carries `derived_from`/
  `source_file`/`source_heading` back to its real corpus tag for real
  traceability.
- `IMPLEMENTS` edges point at the **real, already-existing (non-demo)
  Method pool** this repo's own earlier Cognify run already populated (207
  real Methods across `metis_mcp/*.py`) — matched by real module filename
  per subsystem, not a synthetic duplicate. 61/75 grounded Requirements
  resolved a real implementing Method; the other 14 (RES, MTX, ING, SKL,
  CG prefixes) honestly have none, matching this project's own documented
  "genuinely open items" (`REQ-METIS-RES-01..04`/`REQ-METIS-MTX-01..03`
  are explicitly not-yet-built, `SKL` is a markdown skill file not Python,
  `CG`'s `cognify/code_graph_archaeology.py` predates the last real
  ingestion run) — disclosed via a count in the run summary, not faked.
- 18 real Confluence-shaped `DocumentIngested` Episodes, `raw_content`
  read directly from this repo's own real `README.md`/`PLAN.md`/
  `CLAUDE.md`/`docs/*.md` (truncated to ~4000 chars each, not embedded
  whole).
- Every business-layer node (grounded or synthetic) now carries a
  `source_kind` property (`"metis_project"` | `"synthetic"`), so the two
  layers are honestly distinguishable in the graph, not silently mixed.
- Still `is_demo_data: true` / wipeable, additive to (not replacing) the
  50-Goal synthetic layer — total Goals at `factor=1.0` is now 68 (50
  synthetic + 18 real).

**Real bug found and fixed while building this**: two of the 75
hand-written paraphrases (`REQ-METIS-ING-01`/`02`) initially opened with
"Each connector shall ..." instead of "The X shall ...", failing the real
Ubiquitous-pattern regex (`^The (?P<system>.+?) shall ...`) — caught by
actually running all 75 through `check_ears_conformance` before touching
the live graph, not assumed. Fixed by rewording both to open with "The
ingestion pipeline shall ...".

**Real bug found and fixed, more subtle**: the new grounded-layer test
(`test_grounded_requirements_trace_to_real_metis_content`) didn't wipe
demo data at the end, unlike every other test in `test_demo_data.py` —
this left demo data loaded for whichever test file ran next in the
regression suite, and `metis_mcp/dq_metrics.py`'s DQ-008/global metrics
aren't demo-data-scoped, so `test_dq_metrics.py`/
`test_test_skeleton_generation.py` failed with polluted global counts.
Not a bug in the grounding logic itself — caught by running the *full*
regression suite after the change, not just `test_demo_data.py` in
isolation. Fixed by wiping at the end of the new test too, restoring the
invariant the whole suite implicitly depends on.

Verified for real at default scale (`factor=1.0`, seed 42): **48,035
nodes / 59,023 relationships** (still within the 40-50K target), 68 total
Goals, all 6 `test_demo_data.py` tests passing (5 existing + 1 new), full
46-file regression suite green. `QUICKSTART.md`'s Demo Data section
updated to describe the grounded layer.

## Session 6 addendum — Demo Data redesigned for structural coherence at production scale

The Session 3 demo generator was real but structurally arbitrary: every
`Requirement` independently called `vocab.pick(r, vocab.SERVICES)` with no
reference to its own parent Feature/Epic/Goal, so a Goal's own child data
read as thematically unrelated to itself. User-reported directly ("the
demo data is very random and not structure") and fixed by redesigning
`demo_data/generate_demo_data.py`: every Goal is now assigned ONE service
domain at creation, and every Capability/Epic/Feature/Requirement/
Repository/Class/Method beneath it inherits that SAME domain — verified
for real post-fix (not just asserted): a "wishlist" Goal's Requirements
all read `WISH-104x` Jira keys and "the wishlist service shall ..." text;
a "search" Goal's read `SEAR-...`/"the search service shall ...", etc.

Also now real, per explicit user request ("build Jira and confluance data
around them ... I need Demo to look like production data with 40-50K
graph nodes"):
- **Exactly 50 Goals**, each with a real per-goal **50-150 Requirements**
  target — the per-goal loop keeps generating EARS/confidence-gated
  candidates until that many are actually WRITTEN (not just attempted),
  since ~1/6 of candidates are deliberately non-EARS-conformant and
  confidence-tiering deliberately rejects some, exercising those real
  gates without starving the target count.
- **Every Requirement now gets a guaranteed 1-3 TestCases** via VERIFIES
  (previously ~60% random coverage) — verified for real:
  `zero_test_reqs = 0` across all 4,894 Requirements in a full run.
- Real Jira-shaped metadata directly on Requirement/Defect nodes
  (`jira_key`/`jira_status`/`jira_sprint`/`jira_issue_type`), matching
  `atlassian_connector.py`'s actual field conventions — `jira_key`'s
  project-code prefix is derived from the Goal's service domain, so it's
  consistent per-domain (`WISH-`, `SEAR-`, `PAY-`, ...), not random.
- Real Confluence-shaped data as `episode_type='DocumentIngested'`
  Episodes (a PRD per Goal, a design doc on ~30% of Features) — same
  Episode-only shape `atlassian_connector.py`'s real `_land_confluence_pages`
  uses, since Confluence has no typed-entity target in the closed
  ontology (established in Session 4).
- Code layer redesigned: one Repository per service domain (was random
  per-index naming), and Method/TestCase ids now follow the real
  `repo:path:name` convention `metis_mcp/pyramid_gap_check.py` actually
  parses (previously demo ids didn't match that convention at all, so the
  platform's own Stage-3 coverage tooling had nothing real to find in demo
  data). IMPLEMENTS edges (Method → Requirement) now preferentially draw
  from the SAME service's repo, not any random method anywhere in the
  graph (the exact same class of "very random" bug, in the code layer).

**Real bug found and fixed while building this**: the first full-scale
run landed at 34,858 nodes with Requirement/Goal averaging 46.7 — under
the user's 50 floor — because ~1/6 candidates are deliberately
non-conformant and the original `confidence = uniform(0.3, 1.0)` put
~43% of the rest into the real Rejected tier (`< 0.6`), so a flat
per-goal candidate count under-delivered. Fixed two ways: the while-loop
above (targets the WRITTEN count, not the candidate count) and narrowing
confidence to `uniform(0.45, 1.0)` (~27% rejected — more realistic for a
backlog than 43%). A second real bug, also found by running it for real
rather than assuming it worked: random per-class method-name collisions
(`{action}_{noun}` drawn from a ~480-combination space) caused MERGE to
silently deduplicate a couple of Method nodes per run, so
`summary["total_nodes"]` (a Python-side count) didn't match the real
graph count `test_generate_reported_total_matches_real_graph_count`
checks — fixed by suffixing method names with their per-class index for
guaranteed uniqueness.

Verified for real at default scale (`factor=1.0`, seed 42, ~4.2s runtime):
**47,593 nodes / 58,607 relationships**, 50 Goals, 4,894 Requirements
(97.9/Goal average, within the 50-150 target), 49 distinct labels, 10
relationship types, all 5 `test_demo_data.py` tests passing, plus the
full 46-file regression suite (0 failed). `Scale(factor=0.05)`/
`Scale(factor=0.1)` smoke-scale calls in `test_demo_data.py` needed no
changes — `Scale.n()`'s multiplier mechanism and `generate()`'s/
`wipe_demo_data()`'s public signatures were preserved unchanged, so
`review_api_server.py`'s one-click load/wipe endpoints keep working
without modification. `QUICKSTART.md`'s Demo Data section numbers are
updated to match this real, current shape.

## Session 5 addendum — full-project re-audit (beyond Session 4's own list), user picked 4 of 8 real gaps to close

After Session 4 closed its own 16-item list, the user asked for a fresh,
independent review of the *whole* project (not just that list) to find
anything still missing. Cross-checked every `REQ-METIS-*`/`CONST-*` id in
every doc against actual code (not just Session 4's own work). Found 8
real, previously-undocumented gaps; the user picked 4 to build now
(GRD-11, SKL-01/02, COST-08, and the big one — §12 Academy + Site + PPTX).
The other 4 (§8's Athena metrics integration `REQ-METIS-MTX-*`, the
`REQ-METIS-RES-01..04` resumability vocabulary, a GitHub required status
check for `REQ-METIS-CPT-06`) remain open, not silently dropped — see
"Genuinely open items" below.

**Two real bugs fixed immediately, from this session's OWN prior work**
(caught auditing, not by the user pointing them out):
1. Three new labels from Session 4 (`Revision`, `MergeProposal`,
   `ConfidenceAdjustment`) had zero schema constraints — every other
   label in the project gets real Neo4j uniqueness/existence constraints;
   these didn't. Fixed: 5 new constraints in `schema-02`, applied live,
   regression-verified.
2. Two new config keys (`token_optimization.headroom_enabled`,
   `server.public_url`) were readable by `config_manager.py` but
   undocumented in `metis.config.example.yaml`/the Helm chart's bundled
   config. Fixed in both, plus the real `.metis/config.yaml`.

**The 4 items actually built, each with real code and real tests:**

- **GRD-11** (`metis_mcp/constitution_gate.py`) — real `:Constitution`
  nodes now exist in the production ontology (reusing `corpus.py`'s
  already-proven parser, not a new regex), plus a real, narrowly-scoped
  hard-block demonstration: a `Requirement` candidate failing CONST-047's
  4 deterministic checks is now REJECTED *before* the general Layer 2/3
  pipeline runs, regardless of confidence — closing a real, previously-open
  gap (only EARS-pattern presence gated Requirement submission before
  this; the substantive 29148 checklist was never actually consulted at
  submission time). **Real, unplanned discovery**: `schema-02` already had
  a `constitution_precedence_required` constraint (`precedence_rank`)
  with a comment describing this exact GRD-11 design — predates this
  session entirely, confirming this was a known, intended gap, not a
  speculative addition.
- **SKL-01/02** — `.agents/metis.agent.md`, a real Quick-Routing-table
  router (modeled on Atlas's own pattern, not copied) for all 5 real
  skills (the original 3 plus the 2 new renderer skills below).
- **COST-08** (`metis_mcp/cost_gate.py`) — a real "Confirm to proceed?
  [yes/no]" gate, wired into `guardrails/calibration.py`'s
  `run_calibration_batch` (the one real large-batch scenario this project
  already has — the exact 229-real-call run from Session 4 would have
  required this confirmation had it existed then).
- **§12 Academy + Site + PPTX** — the big one:
  - `metis_mcp/academy.py`: 4 real, grounded Academy pages (`academy/*.md`),
    a real why-link mapping from actual rejection-reason strings to
    Academy anchors (wired into `guardrails/pipeline.py`'s
    `SubmissionResult.academy_link`), real next-step guidance (wired into
    `metis_get_context`'s not-found response), and a real changelog
    generated from `metis_mcp/temporal.py`'s actual `:Revision` history —
    the single shared content-assembly stage both renderers below call.
  - `metis_mcp/site_renderer.py` + `.agents/skills/metis-site-renderer/`:
    real static HTML generation (via the real `markdown` library), a real
    generated example checked in at `metis-server/site/`.
  - `metis_mcp/pptx_renderer.py` + `.agents/skills/metis-deck-renderer/`:
    real `.pptx` generation (via `python-pptx`), real Content QA + File
    QA (Visual QA honestly disclosed as not built — no image-rendering
    infrastructure here), a real generated example at
    `metis-server/quality-snapshot.pptx`. New dependencies added
    (`markdown`, `python-pptx`) — both confirmed installable, real
    network access available in this environment.
  - Fixed `metis_explain_answer` (`REQ-METIS-ACD-01`) to actually return
    the contract's real `{explanation, sources, confidence_summary,
    academy_links}` shape instead of forwarding to `metis_explain_decision`'s
    unrelated one — `graph.backend=neo4j`'s output now genuinely conforms
    to the contract (verified directly); `graph.backend=local` still
    doesn't fully (no formal Episode record exists for dogfooding text
    documents), disclosed via `adapted: true`, not silently claimed fixed.
  - **Real bug found and fixed along the way**: `metis_mcp/temporal.py`'s
    `record_revision()` silently no-op'd (returned a fake "success"
    revision number) when called against an entity id that didn't exist
    yet — `MATCH` on a nonexistent node matches zero rows, so the whole
    write silently did nothing. Now raises a real `ValueError` instead.
    Caught building the changelog feature's own test, not by a user
    report.
  - **Real bug found and fixed**: `corpus.py`'s `parse_corpus()` mixes a
    `'__conflicts__'` sentinel key (a plain dict, not a `GraphNode`) into
    its returned dict — the two existing real callers already knew to
    pop it; `constitution_gate.py` was the first new caller and hit the
    `AttributeError` for real before the fix.

Full regression after all of this: **41/41 test files passing** (the
deterministic set — LLM-cost test files run and verified separately, same
as always).

### Session 5 follow-up — a second, deeper self-review found 6 more real bugs in the Session 5 work itself

The user asked to review the whole project again. Rather than re-deriving
the same requirement-by-requirement audit, this pass checked the Session 5
work *itself* for completeness gaps — and found real ones, the same day
they were written:

1. **`next_step_guidance` was 75% dead code.** 4 gap types were defined;
   only `not_found` was ever actually called from a real tool. Fixed:
   wired `no_traceability` into `metis_check_coverage`'s `covered=False`
   branch, and added the missing `not_found` wiring to
   `metis_get_traceability`/`metis_check_coverage` (only `metis_get_context`
   had it). `quarantine_stuck`/`circular_traceability` remain real,
   tested, unwired utility entries — disclosed precisely, not overclaimed.
2. **`ACADEMY_CONTENT_VERSION` was computed but never rendered anywhere**
   — `REQ-METIS-ACD-06` requires versioned content, but a version nobody
   can see isn't really versioned. Fixed: every rendered Academy page now
   shows it in a real footer.
3. **`generate_changelog()` was never called outside its own test** —
   `REQ-METIS-ACD-05` requires a real changelog; a changelog function
   nobody renders isn't one. Fixed: `metis_mcp/constitution_gate.py`'s
   `load_constitution_rules()` now calls `temporal.py`'s `record_revision`
   for real (only when a rule's text actually changed, so re-running the
   loader never creates spurious history), and `site_renderer.py` renders
   a real `changelog.html` from that history.
4. **`load_constitution_rules()` had no real operational entry point at
   all** — only tests ever called it; a real deployment's `:Constitution`
   entity set would never actually get populated. Fixed: added a real
   `main()` (same connector-style pattern as `atlassian_connector.py`),
   run for real against the live instance — 64 real rules now genuinely
   loaded.
5. **The big one — a systemic, previously-undetected id-collision bug**:
   `metis_mcp/temporal.py`'s docstring claimed "`id` is unique across the
   whole ontology," which is false — schema-01's uniqueness constraints
   are declared PER LABEL, not globally, and `:DogfoodingItem` (the
   self-referential dogfooding corpus's shadow copy) is verified to share
   real id strings with the production ontology (`CONST-046` is both a
   real `:DogfoodingItem` and a real `:Constitution` node). Surfaced for
   real the moment `constitution_gate.py`'s loader hit an actual Neo4j
   constraint violation (a label-agnostic `MATCH` matched both nodes,
   causing a duplicate-id write inside one Cypher statement). Fixed with
   an explicit `WHERE NOT ...:DogfoodingItem` exclusion everywhere this
   pattern appears — swept the whole codebase for it, not just the one
   call site that broke first: `temporal.py` (all 5 functions),
   `hybrid_retrieval.py`'s `graph_traversal_search`, `pinned_memory.py`'s
   `get_active_constraints`/`get_open_incidents`, `llm_judge.py`'s
   `apply_judge_to_quarantine_item`, and this session's own new
   `metis_explain_answer` fix. (`rbac.py`'s equivalent pattern is
   naturally protected — `DogfoodingItem` never sets `owner_team` — so
   left as-is rather than changed for no reason.) A new, explicit
   regression test (`test_record_revision_ignores_a_dogfoodingitem_
   sharing_the_same_id`) proves the fix against the real collision, not a
   synthetic one.
6. **A second systemic bug, found verifying fix #5**: after the
   `DogfoodingItem` fix, `test_temporal.py` still failed *intermittently*
   — a real Neo4j `ConstraintError` on a duplicate `Revision` id, on a
   re-run of a test that had just passed. Root cause: the neo4j driver's
   `execute_write()` can retry a transaction function even after the
   server-side commit already succeeded (a documented at-least-once edge
   case, not specific to this codebase) — and `record_revision`'s
   `CREATE` for the Revision node isn't idempotent against that retry, so
   a retry re-attempts creating the identical id and hits the real
   uniqueness constraint. Confirmed reproducible 1-in-a-few-runs, not
   hypothetical. Fixed with `MERGE ... ON CREATE SET` (this project's own
   established idempotency convention, used everywhere else already) —
   verified with 3 consecutive clean runs after the fix. **Swept the
   whole codebase for the same pattern** (any `CREATE` on a node whose id
   is computed once in Python before a transaction function that could be
   retried) and fixed every real instance found, not just the one that
   happened to fail first: `metis_mcp/temporal.py` (`record_revision` and
   `rollback`'s Episode), `metis_mcp/memify.py`'s `ExtractionCorrected`
   Episode, `metis_mcp/sleep_time_consolidation.py`'s checkpoint Episode,
   `metis_mcp/oauth2.py`'s access/refresh `Token` issuance, and
   `guardrails/corpus_runner.py`'s run-outcome Episode — two of those
   five (`oauth2.py`, `corpus_runner.py`) predate this session entirely,
   meaning this was a real, latent bug in already-shipped Phase 4/9 code,
   not something newly introduced.

Full regression after this follow-up: **42/42 test files passing**, 3x
confirmed clean on the specific test that had been intermittently failing.

## Session 4 addendum — the remaining spec/plan gap audit, closed

After Session 3's demo data, the user asked what else was missing from the
full documentation set, then to build all of it — 16 real items (full
per-item detail in `PLAN.md`'s Session 3 addendum; this section is the
persistent-context summary). All new code, all tested against the real
running Neo4j instance, several real bugs found and fixed along the way
(this project's established pattern, not a coincidence):

- **Real bugs found and fixed this session** (beyond the feature work
  itself): a Cypher `OPTIONAL MATCH` + `count(*)` bug that silently
  reported every Requirement as AC-covered regardless of whether the
  optional match matched (`count(<var>)` is the fix); two MCP tools
  (`metis_get_traceability`/`metis_check_coverage`) returning a different
  key name on their found-vs-not-found branches; a Cypher parameter
  literally named `query` colliding with `Session.run(query, ...)`'s own
  positional parameter; a trailing `LIMIT` after `UNION` applying only to
  the last branch, not the combined result, silently returning more rows
  than requested; a design bug caught *before* shipping — embedding a
  Confluence page's version into its Episode id would have violated the
  real `(source_connector, unit_id)` uniqueness constraint the moment a
  page's version changed; `locust_performance_connector.py` never tagged
  `TestCase.type = 'performance'` despite its own manifest specifying it.
- **CONST-062 contract tests found something real and previously
  undisclosed**: all 9 MCP tools deviate from the full production contract
  shape (`mcp-contracts/metis-mcp-tool-contracts.json`) in Phase 0
  dogfooding mode — only 3 of the 9 deviations were documented in
  `server.py`'s own docstring before this. `test_mcp_contracts.py`'s
  `CASES` dict is now the accurate, regression-checked record.
- **CONST-036's calibration ran at this codebase's real ceiling, not a
  padded 500**: the actual real (non-demo, source-text-backed) Class+
  Method pool grew from 127 to 229 entities over the course of this
  session (this session's own new modules are real Python source that the
  real AST-based Cognify pass picked up) — demo-data entities were
  deliberately excluded since their Episodes carry no real `raw_content`,
  and scoring confidence against empty text isn't a genuine signal. Real
  result from the full run at that ceiling (229 real, costed `claude` CLI
  calls, haiku): **61 auto_write (26.6%), 31 quarantine (13.5%), 137
  rejected (59.8%)** — real, informative, and a genuine miss against
  DQ-002's initial targets (≥60% auto_write, ≤30% quarantine, ≤10%
  rejected), exactly the kind of finding a real calibration run is
  supposed to surface (DQ-002's targets are explicitly flagged in
  `metis-data-quality-framework.md` as "the least-confident number in
  this document"). One real transient failure hit and fixed while
  running this: the `claude` CLI exited 1 with empty stderr partway
  through a 127-call run; confirmed transient (an isolated retry of the
  identical call succeeded), fixed with a real 3-attempt retry in
  `guardrails/calibration.py`'s `_assess_confidence`, same mitigation
  `llm_judge.py` already uses for its own observed reliability issue.
  Full result: `metis-server/calibration_result.json`.
- **Copilot integration, built now** (previously deliberately deferred):
  `metis_mcp/copilot_integration.py` generates the real `spec-aware.
  agent.md` discovery file from actual config, checked in at
  `.github/agents/spec-aware.agent.md`. Config-only — no live Copilot
  instance exists here to connect against.
- **Confluence/JSM/Compass are now real**, not just Jira issues:
  `atlassian_connector.py` extended with 3 new real source-shape handlers
  against 3 new mock endpoints using real Atlassian Cloud REST API path
  conventions (`mock_jira_server.py`).
- **~15 new real modules under `metis_mcp/` + `guardrails/`, ~15 new real
  test files** — see `README.md`'s updated layout tree for the full list.
  Full deterministic regression (37 test files, everything except the 4
  real-LLM-cost ones) is 100% green — 204 individual test assertions
  passing against the live Neo4j instance.
- **What's still genuinely open after this pass**: §8.2's semantic/vector
  retrieval mode (no embedding model in this environment — disclosed-
  refuses rather than fakes it), retrofitting every existing write path
  to call the new real `temporal.py` versioning mechanism (built and
  tested, but not yet wired into every connector — a separate, larger
  integration task), and a real original `metis-review-assist` if one
  ever turns up elsewhere.

## Session 3 addendum — one-click Demo Data

`demo_data/generate_demo_data.py` (new): a real, reusable ~12,000-node/
~11,000-relationship synthetic dataset across 43 real ontology labels and
10 real relationship types, for exploring the platform at a scale the
~500-node dogfooding corpus can't show. **Not fabricated in the ways that
matter** — every `Requirement`'s text is checked against the real,
unmodified EARS checker (a non-conformant candidate is dropped, never
force-tagged); `lifecycle_state` comes from a real call to the real
`ConfidenceTiering.evaluate()`; a deliberately overlapping-guard pair is
run through the real determinism checker and genuinely ends up `Disputed`.
All demo nodes are tagged `is_demo_data: true` with `demo:`-prefixed ids —
`wipe_demo_data()` only ever touches those, never the real Phase 1-9 data.

One-click from the browser: `docs/metis-review-queue-ui.html` now has a
"Load demo data"/"Wipe demo data" panel, backed by three new real
endpoints on `review_api_server.py` (`GET /api/demo-data/status`,
`POST /api/demo-data/load`, `POST /api/demo-data/wipe`). One-click from the
terminal: `python3 -m demo_data.generate_demo_data` (`--wipe` to remove).
Requires `graph.backend: neo4j` — doesn't work against `LocalGraphStore`.

Building this against the already-loaded dogfooding/connector data found
two more real interactions, both fixed: `test_structural_extraction.py`
counted `:Class`/`:Method` nodes without excluding `is_demo_data: true`
(demo data also populates those labels); and demo `Requirement`s landing
in `Quarantine` tier had no `triage_reason`, which `review_api_server.py`'s
real triage-reason check correctly flagged as a gap.

## Session 2 addendum — everything is now built, including the LLM parts

After Phases 1-10 were done, the user asked to build everything that had
been descoped. The one real assumption that changed: **no
`ANTHROPIC_API_KEY` exists in this environment, but the `claude` CLI
(Claude Code) is installed and independently authenticated** — real,
costed calls via `claude -p --model <model> --output-format json`
(`metis_mcp/llm_client.py`). That single finding unblocked everything
previously marked "needs a real LLM call": Layer 6 LLM-as-judge
(`metis_mcp/llm_judge.py`), `MicroRequirement` decomposition
(`metis_mcp/microrequirement.py`), and a real (deliberately small-scale —
8 cases, not the spec's 500; real calls cost real money) `CONST-036`
calibration batch (`guardrails/calibration.py`). All three make genuine
model calls and are tested against real project text, not canned
responses.

Also now built: `REQ-METIS-BM-01`'s code-graph corroboration (needed a
real `CALLS`/`IMPORTS`/`INHERITS` extraction pass,
`cognify/code_graph_archaeology.py`, built via AST — deterministic, no
LLM), the four previously-skipped connectors (`locust-performance`,
`bmad-method-specs`, `grafana-metrics`, `atlassian-prod` — two need no
mock at all, two use small disclosed mock HTTP servers), and live
(not just standalone-smoke-tested) deployment of `mcp-server`/
`ingestion-worker` to Docker Desktop's Kubernetes, reaching the real
host-run Neo4j/Postgres over the network via `host.docker.internal`.

**The live deployment attempt alone found five more real chart bugs**,
none of which the Phase 9 CronJob-only deployment had surfaced:
1. `templates/secrets.yaml` creates a real Secret, but no template ever
   wired it into any container's environment (`envFrom`/`secretRef` was
   simply missing) — every deployed component would have started with no
   real password/secret values at all, silently.
2. `values.yaml` declares `NEO4J_URI`/`ATHENA_DB_HOSTNAME` env vars, but
   `config_manager.py` only ever read from `config.yaml` — the env vars
   were dead. Fixed by having `get_neo4j_config()`/`get_connector_config()`
   let the real env var override the config default, the standard
   per-deployment-override pattern.
3. `values-sbx.yaml` overrode `components.ingestion-worker.env` with a
   single entry (just the one it meant to change) — Helm replaces whole
   arrays across `-f` files rather than merging them, so this silently
   dropped `CONNECTOR_MANIFEST_DIR` and `METIS_HOME` from the base
   `values.yaml`'s list. Fixed by restating the full list.
4. The `mcp-server` component had no `METIS_HOME`/`mountedConfigMaps` at
   all — it had no way to ever find `config.yaml`, so it halted on every
   startup with `ConfigNotFoundError`, regardless of image content.
5. `readOnlyRootFilesystem` was placed under the Pod-level
   `securityContext` in `_objects.tpl`, but it's a **container**-level
   field — Kubernetes rejected the whole Deployment ("field not declared
   in schema"). Fixed by moving the block to the container level (where
   `runAsNonRoot` is also valid). Separately, `runAsNonRoot: true` needs
   an image that actually runs as non-root and a **numeric** UID (a named
   user isn't verifiable at admission time) — none of the three
   Dockerfiles had one; all three now do (`USER 10001`).

Building `bmad-method-specs` also found a real gap in Phase 4's own
guardrail code, still worth knowing: `structural_validation.py` never
checked schema-02's `corroboration_count` existence constraint for
`Requirement`/`BusinessRule`, because nothing had ever tried to write a
real `:Requirement` node through the gate before that connector did.
Fixed, with a regression test.

**What's still genuinely open after all of this:** real Confluence/JSM/
Compass ingestion (only the Jira-issue path of `atlassian-prod` is built),
and running `CONST-036`'s calibration at its actual specified 500-unit
scale against a real project (a cost/time decision for whoever actually
onboards one, not a technical blocker). See `PLAN.md`'s own Session 2
addendum for the full detail this summary compresses.

## What's real vs. what's scaffolded — know this before touching anything

**PLAN.md now has full, phase-by-phase detail on everything below,
including every real bug found and fixed while building it — this section
is a summary, not the full record.** As of the most recent session,
Phases 1-9 are done and Phase 10 is done with a significant caveat (below).

- **`metis-server/`** is real, tested Python — an MCP server with 9 working
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
- **`metis-server/.agents/skills/` — significant discovery: the real
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
.venv/bin/python3 test_e2e.py                  # real MCP client, 11 tools (graph.backend: local by default)

# Everything else (Phases 1-9) needs a running Neo4j + mock Athena Postgres.
# Podman, not Docker (Session 9): identical Dockerfile-compatible build/run
# semantics, rootless by default -- these two commands are the only
# actionable (non-historical) container usage anywhere in this project.
podman run -d --name metis-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/metis-dev-pass -e NEO4J_ACCEPT_LICENSE_AGREEMENT=yes \
  neo4j:5.26-enterprise
podman run -d --name metis-athena-mock -p 5432:5432 \
  -e POSTGRES_USER=athena -e POSTGRES_PASSWORD=athena-mock-pass -e POSTGRES_DB=athena_mock \
  postgres:17
# then run schema/metis-graph-01/02/03-*.cypher against Neo4j, and
# connectors/mock_athena_schema.sql against Postgres, then:
export METIS_NEO4J_PASSWORD=metis-dev-pass METIS_ATHENA_PASSWORD=athena-mock-pass
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
.venv/bin/python3 test_dq_metrics.py                   # 22 tests -- full DQ-001..022 + composite score
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
  real scale numbers (100K Jira tickets, 15K tests, 1M+/month executions)
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
   the current one under `.agents/skills/` is a disclosed reconstruction
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
