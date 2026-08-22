# Repositioning: AI-Driven Athena
## ETL + Knowledge Graph + Statistics — Reconciling Every Connector Against What Already Exists

**Naming note (added after this memo was written): the platform proposed here as "Athena" was subsequently named Ariadne instead**, specifically to avoid the ambiguity this memo's own title now demonstrates — "Athena" doing double duty as both the real ETL system and the new platform's name. Every architectural conclusion below (ETL reuse, storage merge, the connector reconciliation table) stands unchanged; only the product name changed. Read "Athena" below as "the real, existing ETL system," and understand that the platform being designed is Ariadne.

---

## 0. Why this is a better architecture decision, not just a rename

The earlier "Atlas" positioning made this platform an extension of Atlas's *agent/skill* layer — reasonable at the time, but Atlas already has its own AI behavior (RPI, Stage Confirmation, its own skill routing), so building inside it meant working within constraints that already existed for a different purpose. **Athena has no AI layer at all — it's a working, deployed, deterministic ETL system.** That's not a limitation to work around, it's exactly the right shape to extend: this platform's whole architecture already treats deterministic ETL and AI-driven interpretation as separate stages (§6, §9's code-vs-LLM table) — Athena already *is* the deterministic half, built and running. The efficient move isn't to rebuild an ETL layer that duplicates Athena's, it's to make Athena's real connectors the literal Extract stage and add the Cognify/graph/guardrail layer as what was missing.

**New name and framing (as originally proposed here; superseded by "Ariadne" — see the note at the top): ETL + Knowledge Graph + Statistics.**

```
ETL (existing Athena, unchanged)   →   Knowledge Graph (new)   →   Statistics (existing Athena, extended)
athena-client-git, -jira, -scale,      Bi-temporal Neo4j graph,      Postgres (athena_db) + Grafana,
-openapi, -pipeline, -tms, -kube,      Cognify extraction,           now also serving the new
-metric -- real, deployed, no          guardrail stack (§7),         guardrail/quality metrics
changes needed                         Constitution (Articles         (§7.1, Data Quality Framework)
                                        I-XII), EARS, corroboration
```

---

## 1. Connector-by-connector reconciliation (checked against the real module list, not assumed)

| New manifest built in this conversation | Athena's real existing module | Verdict |
|---|---|---|
| `application-code` | `athena-client-git` | **Superseded — reuse Athena's existing client directly.** No new MCP-based Git connector needed; Athena's Git client becomes the Extract-stage implementation, and the *new* work is only the code-graph layer (`CALLS`/`IMPORTS`/`INHERITS`) sitting on top of what Athena already fetches. |
| `atlassian-prod` (Jira portion) | `athena-client-atlassian-jira` | **Superseded for Jira — reuse directly.** |
| `atlassian-prod` (Confluence, Compass, JSM portions) | *No existing Athena module* | **Genuinely new — keep.** Athena's Jira client doesn't cover these; this is real added scope, not duplicated effort. |
| `test-suite-ingest` (execution results, case metadata) | `athena-client-atlassian-scale` (Zephyr) + `athena-client-tms` | **Overlaps at the execution/case-metadata level — reconcile, don't duplicate.** Athena already ingests test *management* data (what ran, pass/fail, case ownership in Zephyr/TMS). |
| `test-suite-ingest` (source-code-level AST discovery, `@TestId`-equivalent linking) | *No existing Athena module* | **Genuinely new — keep.** Zephyr/TMS know a test case *exists and ran*; they don't parse the actual test *file* to extract structure or verify the traceability annotation is really there in code, not just claimed in a test-management tool. This is real, additive value, not redundant with Zephyr/TMS. |
| `locust-performance` | *No existing Athena module* (Athena has `athena-client-pipeline-testng`, which is CI/perf-adjacent but not Locust-specific) | **Genuinely new — keep**, though worth checking whether `pipeline-testng`'s data should feed the same `Metrics`/`TestCase(performance)` entities rather than treating Locust as the only performance source. |
| `grafana-metrics` (inbound: alerts, incidents) | *No existing Athena module — Athena produces Grafana dashboards, it doesn't ingest from Grafana* | **Genuinely new — keep.** This is the inverse direction of what Athena already does (outbound dashboard generation vs. inbound alert/incident ingestion) — no overlap despite the shared vendor name. |
| `flat-files` | *No existing Athena module* | **Genuinely new — keep.** |
| `bmad-method-specs` | *No existing Athena module* | **Genuinely new — keep.** |
| OpenAPI/Swagger source (described conceptually in §5.2, never given its own manifest) | `athena-client-openapi` | **Was about to be rebuilt from scratch — now doesn't need to be.** Reuse Athena's existing client; the *new* work is only the spec-vs-deployed drift detection (`SpecDriftDetected`, §5.2) layered on top. |
| CI/CD source (described conceptually in §5.2, never given its own manifest) | `athena-client-pipeline` | **Same as above — reuse, don't rebuild.** |
| DB schema/migration source (described conceptually, never given a manifest) | *No existing Athena module* | **Genuinely new — keep**, and worth building since it's a real gap in Athena's own current coverage too, not just this extension's. |
| Kubernetes environment/deployment state | *No existing Athena module was targeted by this project until now* | `athena-client-kube` **exists and was never connected to anything in this project** — a real opportunity: environment/deployment state maps onto `Release`/environment-parity checks (Fool-Proof framework §B, CONST-027's drift verification) that were previously marked `[SET BY ORG: how drift is verified]` with no concrete mechanism. This closes that gap for free. |
| Generic metrics | *No existing Athena module was targeted* | `athena-client-metric` **exists and is a better general-purpose `Metrics` entity source than building anything bespoke** — worth using ahead of, or alongside, the Grafana-specific connector. |

**Net effect:** of the ~10 connectors built across this conversation, roughly half turn out to be unnecessary new builds — real, working code already does that job. The genuinely new work concentrates exactly where it should: the AI-interpretive layer (Cognify, EARS, Behavior Modeling, code graph, guardrails) and the handful of sources Athena truly never touched (Confluence, Compass, flat files, BMAD, DB migrations, inbound Grafana alerts, source-level test-code AST parsing). That's a meaningfully smaller and more honest build than treating everything as greenfield.

---

## 2. Storage architecture: one database, not two

**Superseded twice over — flagged rather than silently rewritten.** This section originally proposed merging the new schema into Athena's existing `athena_db` Postgres. Two later decisions changed this further: (1) the naming — `atlas_graph`/`athena_graph` became `ariadne_graph`; (2) more substantially, a later conversation about total data volume (100K Jira tickets, 1M+/month test executions) concluded the episode log, review queue, and RBAC should move to Neo4j entirely rather than to any Postgres schema — see `metis-graph-03-single-db-consolidation.cypher` for the final, current design (renamed again since, from `ariadne-graph-03-*`, per the subsequent Métis rename). This section's original reasoning is kept below for history; it is not the active architecture.

§3.3 previously specified a separate Postgres instance for the episode log (`atlas_graph` schema). **Revised: this is a new schema inside Athena's existing `athena_db` database**, not a second Postgres instance — same server, same backup/ops tooling, same Helm-managed deployment Athena already has. Neo4j remains genuinely new (Athena has no graph database today), but there's no reason to stand up a second relational database when a working one, already operationally mature, is right there.

```
athena_db (existing, unchanged operationally)
   ├── athena schema        -- existing tables/views, untouched
   └── athena_graph schema  -- new: episodes, extractions, review_queue,
                               users, team_membership, model_call_log,
                               test_run_results (renamed from atlas_graph.*)
```

`REQ-ATHENA-ARCH-01`: the new schema is additive — no existing Athena table, view, or Grafana dashboard is modified or renamed by this repositioning. The two schemas coexist in the same database without cross-dependency at the DDL level (though the new schema-catalog pattern, §12.4's earlier note, can reference both).

---

## 3. What this changes about earlier decisions, and what it doesn't

| Earlier decision | Status under this repositioning |
|---|---|
| §12.4's "live integration with Athena via `athena-analyzer`" | **Deepens rather than reverses** — this was already the right call; now it's not "this extension talks to Athena," it's "this extension's ETL layer *is* Athena's existing code" |
| The Constitution (all 12 Articles, 46 `CONST-*` rules) | **Unchanged in substance.** Nothing about renaming the platform changes what EARS conformance, corroboration, or the guardrail stack require — this was already written to govern *content quality*, not tied to which ETL code produces the content |
| The Fool-Proof/Security framework (Part A/B) | **Unchanged in substance**, with one genuine improvement: `athena-client-kube` gives `CONST-027`'s environment-drift check (previously an unfilled `[SET BY ORG]`) an actual mechanism instead of a placeholder |
| The Data Quality Framework (22 metrics, composite score) | **Unchanged** — these measure graph content quality regardless of which connector populated it |
| The Behavior Model → Test pipeline (last-but-one turn) | **Unchanged**, and slightly strengthened — `athena-client-pipeline`/`-tms` give Stage 3's pyramid-gap check a second, execution-level data source to cross-check against the source-code-level `test-suite-ingest` findings |

---

## 4. What I'm explicitly not doing yet

**Update: this section is now historical.** The rename to Ariadne was completed as its own dedicated pass, per the recommendation below — every file, tool name, and requirement ID prefix was updated (`REQ-ATLAS-*` → `REQ-ARIADNE-*`, `atlas_*` tools → `ariadne_*`, files renamed with an `ariadne-` prefix), with the same section-by-section care described here, rather than a blind find-replace. This memo's own references to "Atlas" and "Athena" as the two real, distinct prior-art systems remain unchanged, since those are accurate historical citations, not the platform's own former name.

Original text, kept for history:

This memo is the **decision record**, not the executed rename. The earlier Atlas rename (several turns back) required careful, section-by-section correction — a blind find-replace broke meaning everywhere the text drew a contrast between two named systems, and I had to fix it by hand afterward. The same risk applies here, likely worse, since "Athena" already appears in every document built so far as *the thing being integrated with* — a mechanical rename would turn "this extension integrates with Athena" into nonsense the same way "SKG vs Atlas" briefly became "Atlas vs Atlas" last time.

**Recommendation: confirm this architecture decision first (§1's reconciliation table, §2's storage merge, the name itself), then I do the full terminology and file-rename pass as its own dedicated piece of work**, the same way the Atlas rename was handled — not folded into this same turn, so it can be done carefully rather than fast.

---

## 5. What's genuinely still open

| Item | Status |
|---|---|
| ~~Confirm the name itself~~ | **Resolved: Ariadne** (not "Athena," to avoid ambiguity with the real ETL system this platform reconciles with — see the dedicated naming discussion later in the conversation) |
| Whether `athena-client-pipeline-testng` should be folded into the `locust-performance` reconciliation or kept distinct | Needs a look at what `pipeline-testng` actually captures before deciding — flagged, not resolved here |
| Scope/timing of the actual rename pass (§4) | Ready whenever you want it — recommend as its own turn, not combined with further new capability work |
