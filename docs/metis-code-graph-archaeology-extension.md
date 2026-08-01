# Code Graph & Code Archaeology Extension
## Closing a gap in `application-code`, and giving DQ-019 an actual remediation path

---

## 0. What was missing

The `application-code` connector (built two turns ago) maps source files to `Repository`/`Class`/`Method` entities via structural containment only — `Repository` CONTAINS `Class` HAS `Method`. It never captured **call graphs**: which methods call which, what imports what, what inherits from what. That's a real gap, not a nice-to-have — it's exactly the layer `metis_impact_analysis` (§11.1) needs to answer "if I change this method, what else breaks" with any precision beyond "things that share a `Transition`."

Separately, the Data Quality Framework's **DQ-019** (orphan-code rate: `Method` nodes with no `IMPLEMENTS` edge to any `Requirement`) was defined as a tracked trend with no actual fix — it said "high/rising rate is a scope-completeness signal" and stopped there. For a codebase that predates this platform entirely (which is the realistic case for most `application-code` ingestion), that's not good enough — there needs to be a real process for going from "orphan code" to "understood code."

Both gaps close together, because code archaeology is specifically how you produce the missing traceability for orphan code, and a code graph is what makes that reconstruction tractable instead of a manual slog.

---

## 1. New ontology relationships: CALLS, IMPORTS, INHERITS

Extends v1's Implementation layer (`Method`, `Class`, `Repository`) with three new relationship types, alongside the existing structural ones:

| Relationship | Meaning | Direction |
|---|---|---|
| `CALLS` | Method A invokes Method B | `Method -[:CALLS]-> Method` |
| `IMPORTS` | Class/file A imports Class/module B | `Class -[:IMPORTS]-> Class` |
| `INHERITS` | Class A extends/implements Class B | `Class -[:INHERITS]-> Class` |

These carry the same bi-temporal properties as every other relationship in this platform (`t_valid`/`t_invalid`, per §5.1) — a call graph isn't static, it changes with every commit, and "this method used to call that one before the refactor" is exactly the kind of point-in-time question §5.4's temporal query interface already exists to answer.

### 1.1 Extraction: deterministic, not LLM — and don't rebuild it, delegate it

Per §9's code-vs-LLM table, call/import/inheritance extraction is a pure AST-parsing task — no judgment involved, purely mechanical. The ecosystem confirms this isn't a hypothetical: multiple production MCP-exposed tools already do exactly this (CodeGraphContext, CodeGraph), built the same way `application-code` already builds structural extraction (Tree-sitter under the hood). **Rather than reimplementing call-graph resolution inside Cognify, `application-code`'s manifest is amended to delegate this specific extraction to an existing code-graph MCP tool**, consistent with the pattern already established for Grafana/Atlassian/GitHub — reuse a maintained tool where the ecosystem has already solved the problem well, rather than rebuild it.

```json
{
  "connector_id": "application-code",
  "amendment": "v1.1.0",
  "additional_mcp_tool_allowlist": [
    "get_callers", "get_callees", "get_call_chain", "get_imports", "get_class_hierarchy"
  ],
  "additional_entity_type_mapping": [
    { "source_shape": "Function/method call site, resolved via the code-graph tool's call-chain analysis", "target_entity_type": "Method-[:CALLS]->Method edge", "target_episode_type": "CallGraphEdgeDiscovered" },
    { "source_shape": "Import statement, resolved cross-file", "target_entity_type": "Class-[:IMPORTS]->Class edge", "target_episode_type": "ImportEdgeDiscovered" },
    { "source_shape": "Class inheritance/interface implementation", "target_entity_type": "Class-[:INHERITS]->Class edge", "target_episode_type": "InheritanceEdgeDiscovered" }
  ]
}
```

`REQ-METIS-CG-01`: call-graph edges are extracted with the same read-only access as the rest of `application-code` (`REQ-METIS-CONN-03` already applies — no new write surface is introduced by this amendment).

---

## 2. Cypher additions

```cypher
// ==========================================================
// Code Graph extension -- relationship indexes for CALLS/IMPORTS/INHERITS
// Run after the existing 01/02 schema files.
// ==========================================================

CREATE INDEX rel_calls_t_valid IF NOT EXISTS FOR ()-[r:CALLS]-() ON (r.t_valid);
CREATE INDEX rel_calls_t_invalid IF NOT EXISTS FOR ()-[r:CALLS]-() ON (r.t_invalid);
CREATE INDEX rel_imports_t_valid IF NOT EXISTS FOR ()-[r:IMPORTS]-() ON (r.t_valid);
CREATE INDEX rel_inherits_t_valid IF NOT EXISTS FOR ()-[r:INHERITS]-() ON (r.t_valid);

// Supports metis_impact_analysis's transitive-call-chain traversal (§3 below) --
// a bounded-depth CALLS traversal is the single most frequent new query pattern
// this extension introduces, so it gets its own composite consideration rather
// than relying on the generic node indexes alone.
CREATE INDEX method_call_lookup IF NOT EXISTS FOR (m:Method) ON (m.id, m.source_episode_id);
```

`sqlfluff`-equivalent sanity: this is pure Cypher DDL, same statement shape already validated in `atlas-graph-01/02-*.cypher` — no new syntax risk introduced.

---

## 3. `metis_impact_analysis` amendment: transitive call-chain traversal

§11.1's `metis_impact_analysis` currently answers "what `Requirement`s/`Service`s/`TestCase`s does this diff affect" by walking `IMPLEMENTS`/`VERIFIES` edges only — it finds what a changed `Method` is *documented* to affect, not what it *actually, structurally* affects through code that calls it. That's a real precision gap: a `Method` with no direct `Requirement` link but three callers that each *do* trace to `Requirement`s was previously invisible to impact analysis.

**Amendment:** for any changed `Method`, `metis_impact_analysis` now also traverses `CALLS` edges transitively (bounded depth, `[SET BY ORG: recommend 3 hops, matching §11.1's existing traversal-depth convention]`) to find all *callers*, then checks each caller for its own `IMPLEMENTS` trace to a `Requirement` — surfacing indirect impact the original design would have missed entirely.

```
skg_impact_analysis(changed_files) now computes:
  1. direct_impact = Methods in changed_files -> IMPLEMENTS -> Requirement (existing)
  2. transitive_impact = Methods in changed_files
       <-[:CALLS*1..3]- calling Methods -> IMPLEMENTS -> Requirement (NEW)
  3. union both, deduplicated, each tagged with its hop distance
     so a direct hit and a 3-hop transitive hit aren't presented as equally confident
```

This directly improves the accuracy of the Constitution's own `CONST-009` release gate (§11.4) — a release blocked or allowed based on impact analysis is now checking real call-chain blast radius, not just documented traceability.

---

## 4. Code archaeology: the actual remediation path for DQ-019 (orphan code)

This is the process gap that's now closed, not just a new data source.

### 4.1 When it triggers

Any `Method` flagged by DQ-019 (no `IMPLEMENTS` edge) that also has **incoming `CALLS` edges from methods that themselves DO trace to a `Requirement`** — meaning it's not dead code, it's *load-bearing* undocumented code — is queued for code archaeology, not just logged as a trend statistic. Truly unreferenced orphan code (no callers at all) is a separate, lower-priority case (candidate for actual removal, not reconstruction).

### 4.2 The workflow (RPI-gated, per §9.2, same discipline as everything else)

1. **Research (R):** mine the `Method`'s git history — every `Commit` touching it, every `PullRequest` that introduced or modified it, commit messages, and code comments. This is pure git-history retrieval, the same `application-code` connector already provides, no new access needed.
2. **Plan (P):** synthesize a candidate explanation of *why* the code exists — what problem it appears to solve, inferred from usage patterns (its callers, per the new `CALLS` edges), naming, and commit-message context. **This step is explicitly LLM-assisted** (unlike call-graph extraction itself) — inferring *intent* from evidence is judgment, not parsing, per §9's own code-vs-LLM table.
3. **Implementation (I):** the synthesized explanation is written as a candidate `Requirement` (or, more often, a `BusinessRule` describing an implicit constraint the code enforces) — **tagged `confidence_tier=quarantine`, `event_time_confidence=inferred`, and explicitly labeled "reconstructed via code archaeology, not originally authored"** in its provenance. This is not optional labeling — per CONST-014/RPI's Forbidden Substitutions rule, a reconstructed requirement must never be indistinguishable from one a human actually wrote; conflating the two would let inferred content quietly accumulate the same trust as verified content, exactly the failure mode Article IV exists to prevent.
4. **Gate:** the reconstructed `Requirement`/`BusinessRule` goes through the standard review queue (§7 Layer 7) like any other quarantine-tier item — a human who knows the domain confirms or corrects the inferred intent before it can reach `Approved`. Code archaeology proposes; it never promotes itself.

### 4.3 Why this closes the loop properly, not just partially

Without this workflow, DQ-019 was a metric with nowhere to go — "orphan code rate is high" told you there was a problem but not what to do about the specific `Method`s causing it. Now: DQ-019 flags candidates → the `CALLS`-edge check (§4.1) prioritizes the load-bearing ones → code archaeology produces a properly-tagged, human-reviewable candidate explanation → the normal guardrail stack decides whether it's good enough to promote. Nothing here bypasses any existing control — it's a *feeder* into the existing quarantine/review pipeline, not a new trust path.

`REQ-METIS-CG-02`: code-archaeology-originated `Requirement`/`BusinessRule` entities MUST retain a permanent, non-removable provenance tag distinguishing them from originally-authored content, even after human review and approval — mirrors `CONST-015`'s rule for AI-generated code (provenance survives approval, it doesn't get erased by it).

---

## 5. What's genuinely still open

| Item | Status |
|---|---|
| Which specific code-graph MCP tool to standardize on (CodeGraphContext vs. CodeGraph vs. another) | Both are real, actively maintained options with slightly different tool surfaces — a real evaluation against your actual codebase language mix would decide this better than a guess here |
| Transitive traversal depth for `metis_impact_analysis` (3 hops proposed) | Reasonable starting point matching §11.1's existing convention, not load-tested |
| Whether "truly unreferenced" orphan code (§4.1) gets its own removal workflow | Flagged as a separate, lower-priority case — not designed here, since it's a different problem (dead code cleanup) from the one this document addresses (undocumented but load-bearing code) |
