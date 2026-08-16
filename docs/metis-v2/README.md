# Métis v2 — Unified Build Specification

> ## ⚠️ PARKED — superseded by [`../metis-application-spec.md`](../metis-application-spec.md)
>
> This 13-document set specified a *platform* by cataloguing the union of three
> systems' features. That approach produced ~4,600 lines in which roughly 350
> concerned generating tests from a model — and a scoping decision removed the
> model source altogether without it being obvious. The result read as a
> requirements-management platform rather than the model-driven test generation
> that was actually wanted.
>
> **The replacement specifies an application, not a platform**, and merges the
> three systems by assigning each a layer role with two contracts between them,
> rather than by unioning their features.
>
> Kept for reference. Sections still useful: §03 (ontology detail), §06
> (guardrail catalogue), §13 (Joern/CPG analysis). Do not treat any of it as
> current scope.

**What this is:** a complete, from-scratch technical specification and
requirements catalogue for **Métis**, a single system that merges every
capability of the two existing prior-art systems in this workspace:

| Prior system | Location | What it contributes |
|---|---|---|
| **Métis (v1)** | `/Users/akeshmiri/Projects/metis` | Persistent bi-temporal Neo4j knowledge graph, closed ontology, 10-layer anti-hallucination guardrail stack, confidence tiering, corroboration, contradiction handling, EARS + ISO 29148 requirement quality, behaviour model (State/Transition) with determinism/completeness/reachability checks, 25 data-quality metrics + composite quality score, Constitution governance, MCP tool server (OAuth2 + stdio + Streamable HTTP), temporal rollback, Academy/Site/PPTX renderers, Helm deployment |
| **Atlas** | `/Users/akeshmiri/Projects/atlas` | Deterministic workflow router + manifest engine, Stage Confirmation Protocol, RPI anti-hallucination protocol, Unified Intake Format (UIF), 11 workflow agents / 29 skills, evidence-first analysis, ISTQB/Zephyr test-case authoring, API + Web functional test generation, Locust performance generation, code review + MR gating, defect-driven regression generation, executive quality reporting, Athena analytics, K8s diagnostics, config discovery and installers |

**Two directives applied throughout this specification:**

1. The new system is named **Métis** (`metis`). There is no "Atlas" runtime,
   router, or namespace in the target system — Atlas's capabilities are
   absorbed as first-class Métis subsystems.
2. **Intake is implemented for Jira only.** Exactly one requirement-intake
   source connector ships: Jira. The connector interface stays open (§5.9), but
   no second source is built in v1. See §1.5 for the precise boundary between
   *requirement intake* (Jira-only) and *evidence acquisition for generation*
   (repository/OpenAPI/test-suite readers, which never create Requirements).

---

## Document set

| # | Document | Contents |
|---|---|---|
| 01 | [Vision, Scope & Principles](01-vision-and-scope.md) | Mission, the merged capability map, scope boundaries, glossary, the Jira-only intake decision and its consequences |
| 02 | [System Architecture](02-architecture.md) | Component model, runtime processes, storage, technology choices, data flow, repository layout |
| 03 | [Ontology & Graph Schema](03-ontology-and-graph-schema.md) | Complete node-label catalogue, relationship catalogue, required properties, Cypher constraint/index scripts, ontology governance rule |
| 04 | [Temporal Model, Provenance & Resumability](04-temporal-provenance-resumability.md) | Four timestamps, bi-temporal edges, precedence, `as_of`/`history`/`diff`, revisions, rollback, `unit_id` idempotency, checkpointing |
| 05 | [Jira Intake & Requirement Mining](05-jira-intake-and-mining.md) | The whole intake subsystem: Jira client, field mapping, UIF v2 schema, Episode landing, 4-stage mining, JiraItem evidence anchors, incremental sync, drift detection |
| 06 | [Guardrails, Data Quality & Governance](06-guardrails-quality-governance.md) | 10 guardrail layers, RPI protocol, confidence tiering, corroboration, contradiction handling, review queue, 25 DQ metrics, composite score, the Constitution and its enforcement mapping |
| 07 | [Workflow Engine, Agents & Skills](07-workflow-engine-and-agents.md) | Deterministic router, workflow manifest schema, stage/ordinal model, Stage Confirmation Protocol, chain mode, artifact contracts, the full agent + skill catalogue |
| 08 | [Behaviour Model, Test Design & Test Generation](08-behaviour-test-design-and-generation.md) | State machine model and checks, test design techniques, coverage mapping, API/Web functional generation, Locust performance generation, Zephyr publishing, defect-driven regression, code review and MR gating |
| 09 | [Reporting, Academy & the MCP/API Surface](09-reporting-academy-and-api.md) | Quality/release/test-design reports, PPTX and Site renderers, Academy content model, complete MCP tool contracts, REST API, client integration |
| 10 | [NFRs, Security & Deployment](10-nfr-security-deployment.md) | Scale/latency/availability targets, OAuth2 + RBAC, data protection, configuration model, containers, Helm chart, observability, runbooks |
| 11 | [Requirements Catalogue](11-requirements-catalogue.md) | Every normative requirement, uniquely identified, testable, with verification method — the contractual core of this specification |
| 12 | [Build Plan & Acceptance Criteria](12-build-plan-and-acceptance.md) | Phase plan, work breakdown, repository bootstrap, test strategy, per-phase exit criteria, migration from the two prior systems |
| 13 | [Static Code Analysis & Behaviour Extraction](13-static-code-analysis-and-behaviour-extraction.md) | Joern sidecar architecture, CPGQL query-pack contract, structural extraction, endpoint discovery, verified type registry, six-step state-transition extraction, AC↔Transition mapping, corroboration semantics, pilot gate |

---

## How to use this specification

- **Building the system:** read 01 → 02 → 03 → 05 → 06 → 07, then implement in
  the phase order of 12. Documents 08–10 are needed from Phase 3 onward.
- **Contracting or estimating:** document 11 is the requirements baseline; every
  requirement carries an ID, a normative statement, and a verification method.
- **Reviewing:** document 03 (ontology) and document 06 (guardrails) are the two
  places where a wrong decision is most expensive to reverse.

## Normative language

`MUST` / `MUST NOT` / `SHALL` — mandatory. `SHOULD` — strongly recommended,
deviation requires a recorded rationale. `MAY` — optional. Requirement IDs use
the form `REQ-<AREA>-<NNN>`; areas are listed in [11](11-requirements-catalogue.md).

## Status of this document set

This is a **design specification written from two working prior-art systems**,
not a record of built software. Where a prior system had a known gap, an
unresolved decision, or a disclosed reconstruction, that fact is carried forward
explicitly rather than papered over — see §1.7 "Known open decisions".
