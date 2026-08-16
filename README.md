# Métis Project Root

Everything built across this project's design and implementation phases,
organized as a real directory tree under this repository root.

## Layout

```
claude/
├── docs/                      Active design, governance, and spec documents
│   ├── metis-specification.md          The master technical specification (19 sections)
│   ├── metis-constitution-adopted.md   Governance: 12 Articles, 64 CONST-* rules, 5 Amendments
│   ├── metis-constitution-template.md  Reusable blank Constitution template
│   ├── metis-data-quality-framework.md 22 DQ metrics, composite quality score
│   ├── metis-foolproof-security-framework.md   Non-expert safeguards + trust-boundary security
│   ├── metis-behavior-model-test-pipeline.md    Requirement→State-Machine→Test pipeline
│   ├── metis-code-graph-archaeology-extension.md  CALLS/IMPORTS/INHERITS + code archaeology
│   ├── metis-standards-integration.md  ISO/IEC/IEEE 29148 + UML statechart grounding
│   ├── metis-cost-review-15k-tests.md  Real cost computation at actual corpus scale
│   ├── metis-gap-remediation.md        Constitution Amendment 5 — 9 of 10 flagged gaps closed
│   ├── metis-deep-review-gaps.md       The original 10-gap audit that Amendment 5 responds to
│   ├── metis-multi-client-integration.md  Claude + Copilot MCP connection guide
│   ├── metis-connector-architecture.md Pluggable connector/manifest architecture
│   ├── metis-const-053-confirmation-record.md  ZDR/API-agreement checklist (open item)
│   ├── metis-review-queue-ui.html      Working reviewer interface (open directly in a browser)
│   └── athena-repositioning-reconciliation.md  Naming history: Atlas → Ariadne → Métis
│
├── docs/historical/            Superseded early drafts, kept for history only
│   ├── specification-knowledge-graph-platform.md   (v1)
│   ├── skg-technical-specification-v2.md            (v2)
│   └── skg-v3-addendum.md                           (v3)
│
├── schema/                     Neo4j Cypher schema (the active, current design)
│   ├── metis-graph-01-entity-baseline-constraints.cypher
│   ├── metis-graph-02-entity-specific-constraints.cypher
│   ├── metis-graph-03-single-db-consolidation.cypher   ← the final single-database design
│   └── superseded/
│       └── metis-graph-03-postgres-schema-SUPERSEDED.sql  (pre-single-DB decision, history only)
│
├── connectors/                 ETL connector manifests (JSON, schema-validated)
│   ├── metis-connector-manifest-schema.json    The JSON Schema all connectors validate against
│   ├── metis-connector-application-code.json   Git/code — reads Athena's tables directly
│   ├── metis-connector-atlassian-prod.json     Jira/Confluence/Compass
│   ├── metis-connector-bmad-method.json        BMAD-METHOD product specs
│   ├── metis-connector-flatfiles.json
│   ├── metis-connector-grafana.json            Inbound alerts/incidents
│   ├── metis-connector-locust-performance.json
│   └── metis-connector-test-suite.json         Per-project test-ID convention resolution
│
├── mcp-contracts/
│   ├── metis-mcp-tool-contracts.json           The 9 MCP tools' real input/output schemas
│   └── metis-adversarial-injection-corpus.json 12-case guardrail regression corpus
│
├── metis-server/                REAL, TESTED Python MCP server (start here for dev work); local dogfooding e2e passes, production validation requires a seeded Neo4j graph
│   ├── metis_mcp/
│   │   ├── server.py            The 9 MCP tools; stdio AND OAuth2-gated Streamable HTTP transport (live-deployed)
│   │   ├── config_manager.py    No-config-in-code resolution (~/.metis/config.json; real env-var overrides)
│   │   ├── classification_gate.py  CONST-051/052/053 enforcement (ZDR gating)
│   │   ├── graph_store.py       LocalGraphStore — dogfooding-corpus stand-in
│   │   ├── neo4j_graph_store.py Neo4jGraphStore — real Cypher backend
│   │   ├── structural_validation.py / confidence_tiering.py  Layer 2/3 guardrails
│   │   ├── llm_client.py / llm_judge.py / microrequirement.py  Real model calls via the `claude` CLI (Layer 6, MicroRequirement)
│   │   ├── oauth2.py / rbac.py / http_transport.py  CONST-064 token lifecycle + team scoping
│   │   ├── ears_checker.py / behavior_model.py  EARS conformance + determinism/completeness/reachability/BM-01 corroboration
│   │   ├── pyramid_gap_check.py / test_skeleton_generator.py  Behavior Model Stage 3/4/5 (real test generation, CONST-050)
│   │   ├── requirement_quality.py / vagueness.py / layer8_heuristics.py  CONST-047's 29148 checklist + Layer 8 (REQ-METIS-GRD-08)
│   │   ├── temporal.py  §5.4 as_of/history/diff + Layer 10 auditable rollback (real :Revision supersession chain)
│   │   ├── dq_metrics.py  All 22 DQ-* metrics + the §3.1 weighted composite quality_score
│   │   ├── contract_validator.py / manifest_validator.py  CONST-062 MCP contract tests + connector manifest schema validation
│   │   ├── token_optimization.py  §9.1 Caveman/Headroom/Cache-Aligner
│   │   ├── hybrid_retrieval.py / pinned_memory.py  §8.1/§8.2 (semantic/vector mode honestly disclosed as blocked)
│   │   ├── sleep_time_consolidation.py / memify.py  §8.3/§8.4 (near-duplicate detection, non-lossy rollup, Beta-Bernoulli confidence feedback)
│   │   ├── copilot_integration.py  Generates the real spec-aware.agent.md discovery file from config
│   │   ├── constitution_gate.py  REQ-METIS-GRD-11: real :Constitution nodes + CONST-047 hard-block, ahead of the general Layer 2/3 pipeline
│   │   ├── cost_gate.py  REQ-METIS-COST-08: real "Confirm to proceed? [yes/no]" gate for materially-larger-than-typical LLM batches
│   │   ├── academy.py  §12 Academy: real content-assembly stage (why-links, next-step guidance, changelog from :Revision history)
│   │   ├── site_renderer.py  §12.5: real static HTML site from Academy content
│   │   └── pptx_renderer.py  §4.6.1: real point-in-time .pptx quality-snapshot deck
│   ├── connectors/               All 7: application_code, flatfiles, test_suite, locust_performance, bmad_method, grafana, atlassian (now incl. Confluence/JSM/Compass, + mock_*_server.py for the 2 that need one)
│   ├── cognify/                  structural_extraction.py (Class/Method, AST) + code_graph_archaeology.py (CALLS/IMPORTS/INHERITS, AST)
│   ├── guardrails/               pipeline.py, corpus_runner.py, calibration.py — Layer 2/3 wiring, adversarial corpus, CONST-036 calibration
│   ├── perf/locustfile.py        Real Locust script for review_api_server.py (locust-performance connector's real target)
│   ├── test_fixtures/bmad/       Disclosed synthetic BMAD-shaped fixture (no real BMAD project exists here)
│   ├── demo_data/                Cached-ticket offline importer plus a small, wipeable gap-fill dataset; see QUICKSTART.md
│   ├── ingestion_worker.py       Wraps connectors + Cognify on a poll loop (metis-ingestion-worker service, live-deployed)
│   ├── review_api_server.py      Real HTTP API behind docs/metis-review-queue-ui.html (now also serves /api/demo-data/*)
│   ├── Dockerfile.*              Real Dockerfiles for all 3 metis-chart components (non-root, live-deployed)
│   ├── academy/                  4 real Academy pages (graph model, traceability, confidence tiers, EARS authoring) — §12
│   ├── site/                     Real generated example output of metis_mcp/site_renderer.py
│   ├── quality-snapshot.pptx     Real generated example output of metis_mcp/pptx_renderer.py
│   ├── ~/.metis/config.json     Shared host-level Métis configuration
│   ├── corpus/                  Bundled copy of docs/ for offline dogfooding
│   ├── test_*.py                 41 real test files — see CLAUDE.md for the full list/commands (a few make real, costed LLM calls and are deliberately excluded from routine runs)
│   ├── metis.config.example.json
│   ├── pyproject.toml / requirements.txt
│   └── QUICKSTART.md            Start here — install, configure, connect Claude Code
│
├── .github/agents/spec-aware.agent.md  Real, generated Copilot discovery file (metis_mcp/copilot_integration.py)
│
└── metis-chart/                 Helm chart — helm lint/template + a real live deployment, 8 real bugs found+fixed total
    ├── Chart.yaml                Neo4j Enterprise as a subchart dependency
    ├── values.yaml               components: mcp-server, ingestion-worker, guardrail-corpus-runner (all 3 now live-deployed)
    ├── values-sbx.yaml           Sandbox/Phase-0 overrides
    ├── templates/serviceaccount.yaml  Was missing entirely — every Pod spec referenced it, none created it
    ├── templates/
    ├── files/                    Bundled connector manifests + config, packaged into ConfigMaps
    └── README.md                 Install instructions + honest notes on what wasn't validated
```

## Where to actually start

1. **Read `metis-server/QUICKSTART.md` first** — it's the fastest path to a running, testable thing.
2. Run the test suites in `metis-server/` to confirm nothing broke (see `CLAUDE.md` for the full command list).
3. `PLAN.md` is the authoritative, phase-by-phase record of what's built, every real bug found and fixed, and what's explicitly out of scope and why — read it (including its Session 2 addendum) before assuming anything is or isn't done.
4. `docs/metis-specification.md` is the canonical reference for *why* everything is shaped the way it is — §16 in particular has the full, honest naming/positioning history.
5. `docs/metis-deep-review-gaps.md` → `docs/metis-gap-remediation.md` is the paper trail for what's been fixed vs. still open.

## What's genuinely still open (as of this snapshot — see PLAN.md for full detail)

- `docs/metis-const-053-confirmation-record.md` — the org's actual Zero Data Retention agreement status with Anthropic is not yet confirmed (currently, deliberately, `zdr.confirmed: false` — no commercial agreement is being pursued right now, a real decision, not an oversight).
- `plugins/metis/skills/metis-review-assist` — the real original was missing from this copy of the project entirely; the current one is a disclosed reconstruction, not the original.
- `metis-chart/`'s three application images (`metis-mcp-server`, `metis-ingestion-worker`, `metis-guardrail-corpus-runner`) — the chart deploys them, it doesn't build them.
- `metis-chart` passes local `helm lint` and `helm template`; deployment still requires real registry coordinates and published application images.
- §8.2's semantic/vector retrieval mode — no embedding model is available in this environment; `metis_mcp/hybrid_retrieval.py` disclosed-refuses rather than faking it.
- `REQ-METIS-MTX-01..03` (Athena metrics/Grafana dashboard integration), `REQ-METIS-RES-01..04` (uniform resumability vocabulary), and `REQ-METIS-CPT-06` (a GitHub required status check) — found by Session 5's fresh full-project re-audit; the user chose not to build these this round.
- Retrofitting every existing write path to call `metis_mcp/temporal.py`'s `record_revision` — the real versioning/rollback mechanism exists and is tested, but isn't wired into every connector's write path yet.
- Real Confluence/JSM/Compass ingestion, real Copilot config generation, the `CONST-036` calibration batch, `REQ-METIS-GRD-11`/`SKL-01-02`/`COST-08`, and the full §12 Academy/Site/PPTX system are now all built (PLAN.md's Session 3/4 addenda, CLAUDE.md's Session 4/5 addenda) — Copilot's live connection still needs an actual live Copilot instance this environment doesn't have.
