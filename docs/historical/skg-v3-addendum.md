# Specification Knowledge Graph — v3 Addendum
## SDD Skills Survey · Token-Cost Management · Resumable/Idempotent Generation · Code-First Cost Reduction · Academy Layer

Builds on `specification-knowledge-graph-platform.md` (v1) and `skg-technical-specification-v2.md` (v2). Items 6–7 (Atlas skill-style guide, Athena metrics system) are placeholders pending file access — see note at top of chat.

---

## 1. SDD Project Survey — Skills to Adopt for Multi-Source Requirements Management

The 2026 spec-driven-development landscape has matured past "AI writes a spec" into distinct, reusable disciplines. <cite index="74-1">Tools split into buckets: spec-anchored/spec-as-source platforms where the spec persists and code is continuously reconciled to it (Tessl, OpenSpec, Augment's Intent), spec-first scaffolding where a Specify-Plan-Tasks flow is bolted onto a coding session but drifts once generation starts (GitHub Spec Kit, Kiro, GSD), and agentic-agile orchestration with a multi-role agent team (BMAD)</cite>. The SKG belongs in the first bucket by design (the graph *is* the persistent spec), but each bucket has a specific skill worth importing.

### 1.1 Skills catalog (mapped to SKG components)

| Skill | Source project | What it does | SKG integration point |
|---|---|---|---|
| **EARS notation enforcement** | <cite index="68-1">Easy Approach to Requirements Syntax — five patterns that turn fuzzy requirements into testable, AI-parseable statements</cite>, standard across the field, <cite index="73-1">criteria written this way map almost 1:1 onto test cases, which is what makes the spec executable rather than advisory</cite> | Constrains how a `Requirement`/`AcceptanceCriterion` is *written*, not just how it's stored | **Direct fill for v2 §5.8's vagueness-scoring heuristic.** Replace the ad hoc "known-vague-terms" classifier with a structural EARS-conformance check at authoring time: Ubiquitous ("The system shall..."), Event-driven ("When \<trigger\>, the system shall..."), State-driven ("While \<state\>, the system shall..."), Unwanted-behavior ("If \<condition\>, then the system shall..."), Optional ("Where \<feature\>, the system shall..."). A `Requirement`/`AcceptanceCriterion` failing to parse into one of these five patterns is held at `Draft` with a specific, actionable rejection reason — "not EARS-conformant" — rather than a vague "vagueness score." This is a deterministic, code-only check (regex/grammar, no LLM call), which also serves item 4 below. |
| **Delta markers (ADDED / MODIFIED / REMOVED)** | <cite index="69-1">OpenSpec's proposal-centered workflow uses delta markers that track what changes relative to existing functionality rather than greenfield descriptions</cite>, purpose-built for brownfield iteration | Change representation for any spec edit | **Direct fill for item 3 (resumability/one-source-of-truth) — see §3 below**, and a cleaner alternative to diffing full entity states for the SKG's `RequirementUpdated` episode payload: every edit episode carries an explicit `delta_type: ADDED\|MODIFIED\|REMOVED` plus the specific field(s) touched, not a full before/after blob. |
| **Constitution-driven development** | <cite index="70-1">GitHub Spec Kit is described as "battle-tested, constitution-driven development"</cite> — a project-level constitution document that constrains what any generated spec/plan is allowed to contain | A standing, versioned set of non-negotiable project rules that every generated artifact must respect | **Direct fill for v2's Validation Engine.** Model the org's non-negotiables (security baselines, data-residency rules, architectural constraints) as a `Constitution` node — effectively a distinguished, highest-precedence `BusinessRule` set — that every `Requirement`/`Transition` extraction is checked against at Cognify time (v2 §1), not just at review time. This gives the SHACL/OWL structural layer a human-authored, versioned "constitution" to validate against rather than only inferred schema rules. |
| **Spec Registry (eliminate API hallucination for external dependencies)** | <cite index="72-1">The Tessl Spec Registry provides over 10,000 specs for external libraries to eliminate API hallucinations and version mix-ups in production codebases</cite> | A curated, versioned source of ground truth for *third-party* API surfaces, as opposed to your own system | **Fills a gap neither v1 nor v2 addressed**: the SKG's `ExternalSystem` entity (v1 §3.4) currently has no mechanism to prevent a coding agent from hallucinating a third-party API's shape. **Recommended addition:** an `ExternalAPISpec` entity, populated from a registry (Tessl's, or an org-internal equivalent for internal-but-external-to-this-repo services), checked by the same corroboration/grounding layers (v2 §5.1–5.4) before a `Transition.APIs Called` edge referencing an external system is allowed to reach `Approved`. |
| **File-based agent handoffs for traceability** | <cite index="72-1">BMAD-METHOD orchestrates specialized AI agents across the full SDLC using file-based handoffs to maintain a traceable chain from requirements to delivery</cite> | Explicit, inspectable handoff artifacts between pipeline stages, rather than opaque in-memory agent-to-agent context passing | **Reinforces v1 §8's Engineering Memory design**: every stage transition in the SKG's ingestion pipeline (Extract → Cognify → Load → Review, v2 §1) should itself write a durable, human-readable handoff artifact (not just a graph write) — this is largely already implied by the episode model, but the BMAD pattern argues for making the handoff artifact's *readability* a first-class requirement, since it's what a human reviewer actually inspects during the Layer 7 review gate (v2 §5.7). |
| **Living-spec reconciliation** | <cite index="74-1">Augment's Intent maintains "living specs that reconcile to what was built"</cite> — a continuous diff between declared spec and actual implementation, rather than a one-time generation step | Continuous drift detection | **This is exactly v1 §7.2's gap-detection + v2's `SpecDriftDetected` episode (v2 §2.2's Swagger row) generalized.** Confirms the design direction already taken; no new component needed, but validates extending `SpecDriftDetected` beyond just OpenAPI to every source category in §2 of v2 — DB-schema-vs-`Table` drift, DOORS-baseline-vs-graph drift, etc., using one uniform drift-detection mechanism rather than per-source bespoke logic. |
| **Worktree/parallel-isolation for concurrent spec changes** | <cite index="70-1">Spec Kitty provides built-in worktree management + parallel feature isolation, letting multiple in-flight spec changes not collide</cite> | Concurrency control for simultaneous requirement edits | **Fills a genuine gap**: v1/v2 never addressed what happens when two teams edit related requirements concurrently. **Recommended addition:** a lightweight optimistic-locking scheme at the `Requirement`/`AcceptanceCriterion` level — a `revision` counter plus a required `based_on_revision` field on any edit episode; a submission against a stale revision is rejected with a merge-conflict-style prompt to the submitter, rather than silently overwriting. This is the graph-native equivalent of Spec Kitty's worktree isolation. |
| **Proposal-first workflow for brownfield changes** | <cite index="69-1">OpenSpec's workflow requires explicit, auditable documentation before any implementation begins — teams where change management requires this get real value from it</cite> | Change requires a proposal artifact, reviewed, before any code/spec mutation | **Reinforces v2 §5.7's human review gate** — confirms that gating writes behind an explicit, inspectable proposal (rather than an implicit LLM decision) is established best practice across the SDD field, not just this design's own caution. |

### 1.2 What this survey changes about the design

Two concrete additions land in the ontology and pipeline as a result of this survey (both are net-new, not present in v1/v2):
1. **`Constitution` entity** (highest-precedence rule set, checked at Cognify time) — closes a gap where v2's Validation Engine had rules but no single, authoritative, human-owned source for the "never allow" class of constraint.
2. **`ExternalAPISpec` entity + registry-backed corroboration** — closes a gap where nothing previously protected against a coding agent hallucinating a third-party API surface, only your own system's surface.

Everything else in the survey **validates decisions already made** (living-spec reconciliation ≈ existing drift detection; proposal-first ≈ existing review gate) or **hardens an existing mechanism with a more specific technique** (EARS replacing the vaguer heuristic; delta markers formalizing the episode payload shape, detailed next).

---

## 2. Token & Cost Management — Merging Caveman + Headroom + Code-First Reduction

Three complementary layers, operating on different parts of the token budget. None of them substitute for the others.

### 2.1 Caveman — output/prompt style compression

<cite index="62-1">Caveman is a prompt-engineering skill that instructs the model to drop articles, pleasantries, hedging, and verbose synonyms while keeping all technical substance — installed as a system-prompt addition, activated per session</cite>. Independent benchmarking found real but more modest gains than the marketing headline: <cite index="61-1">actual savings on real coding tasks landed between 14 and 21 percent, and a distilled 6-line/85-token micro-version of the full 552-token skill matched or beat it</cite>, with <cite index="61-1">quality holding at 100% across benchmark runs since the technique removes filler, not technical substance</cite>. <cite index="62-1">It is most cost-effective in multi-turn sessions with prompt caching (roughly 39% total cost savings factoring in caching) and in agent pipelines with multi-step reasoning where verbose intermediate output accumulates cost — not in single one-off calls, where it can add more input cost than it saves</cite>.

**Where this applies in the SKG:**
- The Layer 6 LLM-as-judge pass (v2 §5.6) and the Cognify-stage extraction calls (v2 §1) are exactly the "multi-step, high-call-volume, prompt-cached" profile Caveman is suited for — every extraction/judge call re-sends similar scaffolding.
- **Recommendation:** adopt the distilled micro-directive (not the full 552-token skill) as a system-prompt suffix on the Cognify extraction prompt and the Layer 6 judge prompt specifically — these are the two highest-volume, most-repeated call sites in the whole pipeline. Do **not** apply it to `skg_get_context`'s user-facing output through Copilot (v2 §4) — that's a low-volume, single-shot-per-request path per Caveman's own stated ineffective case, and terseness in a developer-facing answer trades UX for negligible savings.
- **Do not apply it to anything that becomes a stored spec artifact.** Caveman is an output-style compressor for ephemeral LLM-to-LLM or LLM-to-pipeline exchanges; a `Requirement` or `AcceptanceCriterion` that a human will read later must stay in full, EARS-conformant prose (§1.1) — compressing stored specification text for token savings would directly undermine the "one source of truth, human-auditable" principle behind the whole platform.

### 2.2 Headroom — deterministic middleware compression of tool/RAG output

<cite index="51-1">Headroom is a context-optimization layer that intercepts and compresses agent tool outputs, RAG retrievals, and file reads before they enter the LLM context window, applying deterministic compression and structural pruning rather than lossy summarization</cite>. <cite index="53-1">Its pipeline runs three stages — a Cache Aligner that stabilizes volatile fields like timestamps and UUIDs so repeated calls hit prompt caches, a Smart Crusher that compresses tool output intelligently, and a Context Manager that fits the result to the token budget — with original data cached separately (a "CCR Store") for retrieval if needed</cite>. <cite index="54-1">It ships as a library, a proxy, or an MCP server</cite>, and <cite index="55-1">operates as a transparent proxy compatible with 100+ models via LiteLLM, requiring no changes to agent logic</cite>.

**Where this applies in the SKG:** this is a close structural match for exactly the kind of traffic the SKG generates — `skg_get_context`, `skg_get_traceability`, and `skg_impact_analysis` (v2 §4.1) all return structured, often-repetitive JSON-shaped graph query results, which is precisely Headroom's target profile (verbose structured tool output, not free text).
- **Recommendation:** insert Headroom (or an equivalent deterministic compression proxy) between the SKG MCP server and the Copilot client, as an MCP-server-to-MCP-server hop or a library call inside the SKG server's response-formatting step. Given <cite name="Headroom" index="55-1">reported reductions of 70–95% on tool-output-heavy traffic with no accuracy loss</cite>, this is likely the single largest lever available for reducing the per-request cost of every read-only tool in v2 §4.1 — larger than any prompt-style change, because it targets the volume driver (verbose graph-query JSON) directly rather than the surrounding prose.
- **Specific fit with the Cache Aligner sub-stage:** the SKG's bi-temporal fields (`t_valid`, `t_recorded`, `t_ingested` — v2 §2.1) are exactly the "volatile field" pattern the Cache Aligner is designed to stabilize for cache-hit purposes; without this, every `skg_get_context` response would have unique timestamps and defeat prompt caching entirely. This is not optional if prompt caching is expected to work at all on graph-query responses.
- **Boundary with Layer 1's grounding requirement (v2 §5.1):** compression must never touch `source_episode_id`/`source_span` fields — these are the audit trail, not display formatting. The Headroom integration should be configured with an explicit field-level exclusion list so compression cannot silently strip provenance data in the name of token savings; this is a hard constraint, not a tuning knob.

### 2.3 Code-first cost reduction (deterministic computation over LLM calls)

This principle already runs through v1/v2 implicitly (Tree-sitter AST parsing, migration-history parsing, SHACL structural checks); this section makes it an explicit, auditable decision framework rather than an ad hoc pattern, per your item 4.

**Decision rule:** for any pipeline step, ask "is this a deterministic transformation of structured input, or does it require judgment/inference over unstructured meaning?" The former is always implemented as code; the latter is the only category that should invoke an LLM call.

| Pipeline step | Deterministic (code) or judgment (LLM)? | Implementation |
|---|---|---|
| Parsing a DB migration file into `Table`/`Column` diffs | Deterministic | SQL/DDL parser — no LLM call |
| Parsing an OpenAPI/Swagger file into `Endpoint` entities | Deterministic | OpenAPI schema parser — no LLM call |
| Detecting spec-vs-deployed-API drift (v2 §2.2) | Deterministic | Structural diff between two parsed OpenAPI documents — no LLM call |
| EARS-conformance check (§1.1) | Deterministic | Grammar/regex-based pattern match — no LLM call |
| Jira changelog → episode conversion | Deterministic | Direct field mapping from Jira's API response — no LLM call |
| AST extraction of `Method`/`Class` from source | Deterministic | Tree-sitter (v1 §18) — no LLM call |
| Graph structural validation (SHACL/OWL, v2 §1) | Deterministic | Constraint solver — no LLM call |
| Contradiction detection — temporal overlap (v2 §5.5) | Deterministic | Interval-overlap query — no LLM call |
| Contradiction detection — logical impossibility (v2 §5.5) | Deterministic | Graph pattern query — no LLM call |
| Confidence-score aggregation / memify tuning (v2 §3.4) | Deterministic | Counting/Bayesian update — no LLM call |
| Extracting entities/relationships from a free-text requirement doc | **Judgment** | LLM call — irreducible, this is the actual value-add of the AI layer |
| Layer 6 grounding verification (v2 §5.6) | **Judgment** | LLM call — irreducible, needs semantic comparison of claim vs. source text |
| Vague-requirement rewriting suggestions | **Judgment** | LLM call, but only triggered *after* the deterministic EARS check (§1.1) fails — the deterministic check is the gate, the LLM call is the (optional, human-invoked) remediation aid |
| Test-skeleton generation body-filling (v1 §5) | **Judgment** | LLM call — syntax/framework-specific completion is inherently a generation task |

**Net effect:** of the roughly fourteen steps in the ingestion→validation pipeline across v1/v2, ten are pure code with zero marginal LLM cost, and only four are irreducibly LLM calls. This ratio is the primary reason the guardrail architecture in v2 §5 is affordable at all — most of the ten-layer stack is cheap structural checking, with LLM calls reserved for the two or three places nothing else can substitute (extraction itself, and the independent grounding check).

---

## 3. Intermediate Markers for Resumable, Non-Duplicating Generation ("One Source of Truth")

This directly answers item 3: how does a long-running ingestion, extraction, or document-generation job survive a mid-stream failure (network drop, timeout, crash) without either losing work or double-writing facts.

### 3.1 The core mechanism: content-addressed checkpoints, not position-addressed ones

**Design principle (novel, load-bearing):** never resume "from line N" or "from the last message sent" — resume from **the last durably-committed, uniquely-identified unit of work**, using idempotent writes keyed by content, not by sequence position. This is what makes "avoid duplication" and "one source of truth" the same guarantee rather than two separate ones to reconcile.

Concretely, every unit of generated or extracted content carries:
- **`unit_id`** — a deterministic identifier derived from its inputs (e.g., `hash(source_episode_id + extraction_rule_id + chunk_offset)` for an extraction step, or `hash(document_id + section_id)` for a generated-document section) — **not** an auto-incrementing counter, because counters aren't reproducible across a retried run.
- **`delta_type`** — borrowed directly from OpenSpec's ADDED/MODIFIED/REMOVED convention (§1.1): every unit of work is explicitly one of these three, never an ambiguous "here's some new content, figure out if it's new."
- **`checkpoint_marker`** — a lightweight, human- and machine-readable inline marker written into the artifact itself as it's produced (see format below), so that even a partially-delivered artifact is self-describing about what's been committed.

### 3.2 Marker format (for long-form generated content — documents, specs, extracted-entity batches)

```
<!-- SKG-CHECKPOINT unit_id=req-batch-0043 delta_type=ADDED status=COMMITTED source_episode=ep_88213 -->
... content for this unit ...
<!-- /SKG-CHECKPOINT unit_id=req-batch-0043 -->
```

For graph writes (not document text), the equivalent is a transactional property on the episode itself rather than an inline text marker: `episode.checkpoint_status ∈ {PENDING, COMMITTED, FAILED}`, written PENDING *before* the extraction call starts and flipped to COMMITTED only after the full Load-stage write (§1's Load box, including confidence scoring and the Layer 1–2 guardrail checks) succeeds atomically.

### 3.3 Resume algorithm

```
On restart of an interrupted job:
  1. Query all units with checkpoint_status = PENDING for this job_id.
  2. For each PENDING unit: discard it entirely (do not attempt to "finish" a
     partial write) — re-derive its unit_id from its original inputs and
     re-run it from scratch. Never resume mid-unit.
  3. Query the highest-numbered COMMITTED unit's unit_id.
  4. Resume generation/extraction from the next logical unit after that,
     using the SAME deterministic unit_id derivation as the original run.
  5. Before writing, check: does a unit with this unit_id already exist as
     COMMITTED? If yes, skip (idempotent no-op) rather than re-write.
     If no, proceed.
```

This algorithm is what guarantees **exactly-once effective delivery despite at-least-once retry**: step 5's existence check, keyed on the content-derived `unit_id` rather than a position counter, is what prevents duplication even if the same unit is attempted twice due to a retry racing a slow-but-successful original attempt (a real failure mode in distributed ingestion, not a hypothetical one).

### 3.4 Why this is "one source of truth"

Because `unit_id` is derived from content/inputs rather than assigned by a sequence counter, **the same logical unit always resolves to the same identity regardless of which run, which retry, or which worker produced it.** This is the property that makes the episode log (v1 §6.2, v2 §1) genuinely append-only-safe: two different ingestion workers processing the same Jira changelog entry after a network partition will independently derive the same `unit_id` and the second write is a guaranteed no-op, not a duplicate episode that then needs deduplication logic downstream. Deduplication-by-detection (comparing content after the fact) is a fallback for cases outside this scheme's coverage, not the primary mechanism — prevention beats detection here because a genuinely append-only graph has no clean way to "undo" a duplicate that's already been read and acted on by a coding agent in between.

### 3.5 Applies to three concrete cases in this platform

1. **Long-running Cognify extraction over a large document batch** (v2 §1) — each chunk gets a `unit_id`; a crashed extraction run resumes without re-extracting (and re-charging LLM cost for) already-committed chunks.
2. **This report-generation process itself** — the same pattern, applied to long technical documents: if a generation run is interrupted, the next attempt should identify the last committed section marker and continue from there rather than regenerating from scratch or silently duplicating a section. Worth adopting as a standing practice for any future long-document deliverables in this project, not just inside the SKG's own pipeline.
3. **The Sleep-Time Consolidation Agent's batch rollups** (v2 §3.3) — consolidation runs over potentially thousands of episodes and must be safely interruptible without either losing progress or double-consolidating.

---

## 4. Academy — A Learning Layer for Users

Per item 5: the platform needs to teach, not just serve answers. This is a new component, not present in v1/v2, sitting alongside the Retrieval layer (v2 §3.2) and the Copilot integration (v2 §4).

### 4.1 Design principle

Every answer the SKG gives a developer through Copilot (v2 §4.1's tools) is also a teaching opportunity — the platform should be able to explain **why** it answered the way it did, not just **what** the answer is, and should have a dedicated space for a user to go deeper when they want to.

### 4.2 Components

| Component | What it does | Where it lives |
|---|---|---|
| **`skg_explain_answer` tool** | Given any prior `skg_get_context`/`skg_get_traceability` response, explains the retrieval path that produced it in plain language: which sources contributed, why the graph traversal took the path it did, what the confidence tier of each fact was | New MCP tool, addendum to v2 §4.1's catalog — read-only, cheap (mostly templated from data already computed, not a fresh LLM call) |
| **Academy module** | A structured, progressive-disclosure learning space: "how requirements become graph nodes," "how to read a traceability chain," "what a confidence tier means and why some facts are quarantined," "how to write an EARS-conformant requirement" (§1.1) | Standalone doc set + interactive walkthroughs, versioned alongside the ontology itself so it never describes a stale schema |
| **Inline "why" annotations** | Every guardrail rejection (v2 §5) surfaces a specific, human-readable reason (already specified in v2 §5.8 for EARS/fabrication checks) — the Academy module is where a first-time user learns to interpret these reasons, and the annotation itself links directly to the relevant Academy page | Both — the annotation is runtime, the explanation it links to is Academy content |
| **"Next steps" guidance** | After any `skg_get_context` call that surfaces a gap (missing AC, stale coverage, orphan requirement — v1 §7.2), the response includes a concrete next action, not just a flag: "this transition has no functional test — run `skg_propose_test_skeleton`" | Built into the tool response shape itself, not a separate feature |
| **Changelog-driven "what's new"** | Since the ontology and validation rules are versioned data (v1 §10.2), the Academy surfaces a running, plain-language changelog of rule/ontology changes — directly reusing the `unit_id`/checkpoint mechanism (§3) to guarantee the changelog itself never duplicates or drops an entry even if the update pipeline is interrupted | Academy module, generated from the same episode stream as everything else — no separate content-authoring pipeline to keep in sync |

### 4.3 Why this belongs in the architecture, not just documentation

A platform whose central value proposition is *trustworthy* traceability (v2's whole guardrail stack) only earns that trust if users can audit *why* they should believe an answer, not just receive one. The Academy layer and the `skg_explain_answer` tool are the user-facing surface of the same provenance data the guardrail architecture (v2 §5) already requires every fact to carry — this is largely a UX/exposition layer on top of data the platform is already obligated to maintain, not a separate subsystem with its own cost profile.

---

## 5. Summary of Net-New Additions in This Addendum

| # | Addition | Answers |
|---|---|---|
| 1 | EARS-conformance check (replacing ad hoc vagueness scoring) | Item 1 |
| 2 | `Constitution` entity, checked at Cognify time | Item 1 |
| 3 | `ExternalAPISpec` entity + registry-backed corroboration | Item 1 |
| 4 | Optimistic-locking/revision scheme for concurrent spec edits | Item 1 |
| 5 | Caveman micro-directive on Cognify/judge prompts only | Item 2 |
| 6 | Headroom (or equivalent) compression proxy between SKG server and Copilot, with a provenance-field exclusion list | Item 2 |
| 7 | Explicit code-vs-LLM decision table for every pipeline step | Item 4 |
| 8 | Content-addressed `unit_id` + checkpoint-marker resume protocol | Item 3 |
| 9 | `skg_explain_answer` tool + Academy module + inline "why" annotations + next-step guidance | Item 5 |
| — | Items 6–7 (Atlas skill style, Athena metrics) | **Pending your file/connector access** |
