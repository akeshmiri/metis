# 09 — Reporting, Academy & the Tool/API Surface

## 9.1 One content layer, three renderers

Academy, a browsable site, and slide decks look like three systems. They are
**one content model with three output formats**, and building them as three
systems guarantees they drift.

```
Content assembly  (the ONLY place content is authored/assembled — queries the graph)
   ├── renders inline, interactively, in a chat client   → Academy
   ├── renders as a static browsable HTML site           → Site
   └── renders as a point-in-time .pptx snapshot         → Deck
```

`REQ-RPT-001` — There is exactly one content-assembly stage shared by all output
formats.
`REQ-RPT-002` — Rendering to each format is **deterministic code** (a template
fill), never a second generation pass.

### Why the deck is separate but the site is not

| | Academy | Site | Deck |
|---|---|---|---|
| Audience | In-the-moment | Out-of-the-moment reference | Periodic, stakeholder |
| Freshness | Always current | Always current | **Point-in-time** |
| Interactivity | Interactive | Static, linkable | Static, shared offline |

Academy's general content *is* reference documentation, so a separate site author
would immediately duplicate it — the exact two-sources-of-truth failure the
platform exists to prevent. The deck is genuinely different for one reason:
**it is the only format where staleness is a feature.** A deck from last quarter
should say last quarter's numbers and keep saying them.

`REQ-RPT-005` — Deck output is never auto-regenerated to "fix" staleness.
`REQ-RPT-006` — The site is regenerated on relevant graph change or a short
schedule; it must never be stale.

## 9.2 The provenance rule for all rendered output

`REQ-RPT-003` — **Every claim in any rendered output carries a resolvable
`source_episode_id`.** A deck is not exempt from grounding because it is a
presentation artifact.

`REQ-RPT-004` — Output is verified by **extracting content back out** and
checking for: missing content, leftover placeholder text, and any claim whose
provenance does not resolve. Three passes:

| Pass | Checks |
|---|---|
| **Content** | Every claim traces to its source episode; no placeholders survived |
| **File** | Structural validity; a template-derived artifact is checked against its source template so the template's own pre-existing issues do not misread as regressions |
| **Visual** | Rendered and inspected for overflow, overlap, low contrast, misaligned decoration |

## 9.3 Report catalogue

| Report | Scope | Contents |
|---|---|---|
| **Quality score** | Any subgraph — service, release candidate, project | Composite score plus full per-metric breakdown (§06.13) |
| **Scoped quality report** | Release / service / requirement / project | Functional, performance and security scoring with a deterministic gate status |
| **Release report** | One Release | Requirements included, coverage, executions by configuration, open defects, gate status |
| **Test-design report** | A scope | Techniques used, AC coverage, produced test cases, gaps |
| **Transition test plan** | A behaviour model | Per-transition coverage and the concrete plan to close gaps |
| **Executive report** | A release or programme | Confirmed vs pending evidence, risk, readiness recommendation |

`REQ-RPT-011` — Release readiness is a **deterministic gate status**, not a
narrative judgement. "Go / No-Go / Go with conditions" is computed from the gates
in §06.13, and the narrative explains the computation rather than substituting for
it.

### The rules that make a report trustworthy

| Requirement | Rule |
|---|---|
| `REQ-RPT-007` | Reports state explicitly which metrics are **confirmed** versus **pending evidence** |
| `REQ-RPT-008` | Missing evidence is called out explicitly, never silently omitted |
| `REQ-RPT-009` | A coverage percentage without underlying execution data is a **claim, not evidence**, and is marked as such |
| `REQ-RPT-010` | The normalised status vocabulary is used throughout; a generic `status` field is prohibited |

`REQ-RPT-009` deserves emphasis. A report that prints "87% coverage" without the
`TestExecution` rows behind it is exactly the artifact this platform is meant to
make impossible — it is a merge-blocking claim with no evidence, presented with
the authority of a measurement.

## 9.4 Academy and explainability

| Component | Function | Requirement |
|---|---|---|
| Answer explanation | Explains the retrieval path behind any prior answer: sources, traversal path, confidence tier per fact | `REQ-ACD-001` |
| Academy modules | Progressive-disclosure content: graph model basics, reading traceability chains, confidence tiers, EARS authoring, why a gate fired | `REQ-ACD-002` |
| Inline "why" annotations | Every guardrail rejection surfaces a specific reason, linked to the relevant page | `REQ-ACD-003` |
| Next-step guidance | Every surfaced gap includes a concrete next action, not just a flag | `REQ-ACD-004` |
| Changelog | Plain-language, checkpoint-protected log of ontology and rule changes | `REQ-ACD-005` |
| Onboarding runbook | Documented steps for adding a project, **halting honestly on unimplemented steps** rather than faking a pass | `REQ-ACD-008` |

`REQ-ACD-002` — Academy content is versioned alongside the ontology. Content
describing a schema version that is no longer live **fails a test**. Documentation
that describes a system that no longer exists is worse than no documentation,
because it is trusted.

`REQ-ACD-007` — Explanations derive from the same provenance data the guardrails
already maintain. Academy is a **presentation layer over obligations the platform
already has**, not a separate subsystem with its own cost.

## 9.5 MCP tool surface

| Tool | Default | Access | Purpose |
|---|---|---|---|
| `metis_get_context` | Enabled | Read | Assemble scoped, budget-aware context for an anchor |
| `metis_get_traceability` | Enabled | Read | Walk the traceability chain in either direction |
| `metis_check_coverage` | Enabled | Read | Coverage status for a target |
| `metis_impact_analysis` | Enabled | Read | Reachability-based impact of a change (§13.11) |
| `metis_explain_decision` | Enabled | Read | Why a node is in its current state |
| `metis_explain_answer` | Enabled | Read | The retrieval path behind a prior answer |
| `metis_quality_score` | Enabled | Read | Composite score + breakdown for a scope |
| `metis_generate_quality_report` | Enabled | Read | Scoped quality report |
| `metis_generate_release_report` | Enabled | Read | Release report |
| `metis_generate_test_design_report` | Enabled | Read | Test-design report |
| `metis_generate_transition_test_plan` | Enabled | Read | Per-transition coverage plan |
| `metis_check_behaviour_model` | Enabled | Read | Determinism, guard atomicity/completeness, reachability |
| `metis_propose_test_skeleton` | Feature-flagged | Read | Produces a skeleton only; never commits |
| `metis_list_skills` | Enabled | Read | Runtime skill catalogue |
| `metis_ingest_jira` | Enabled | Write (gated) | Trigger a Jira sync |
| `metis_mine_requirements` | Enabled | Write (gated) | Mine an existing Episode |
| `metis_ingest_code_analysis` | Enabled | Write (gated) | Land a code-analysis extraction report |
| `metis_submit_episode` | **Disabled by default** | Write | Generic write path — organisational opt-in required |

`REQ-MCP-001` — Read tools ship enabled; the generic write path ships disabled.
`REQ-MCP-006` — It remains disabled until the guardrail stack has a production
track record. This is a phase gate, not a permanent restriction.

### Tool contract rules

| Requirement | Rule |
|---|---|
| `REQ-MCP-002` | Every tool has a published input/output JSON Schema, validated as well-formed |
| `REQ-MCP-003` | Contract tests run against a **real subprocess client**, not a mock |
| `REQ-MCP-004` | Traversal depth and top-k are negotiated **per client connection**, not fixed platform-wide |
| `REQ-MCP-005` | Clients differ only at the configuration/discovery layer; auth and permissions are identical server-side |
| `REQ-MCP-009` | Errors are explicit and actionable — **never a silent empty result** |
| `REQ-MCP-011` | Every tool enforces RBAC scoping; a known node id never bypasses team scoping |
| `REQ-MCP-012` | The catalogue is discoverable at runtime and matches the generated agent definitions |

`REQ-MCP-009` matters more than it sounds. An empty result and a permission
denial and a "no such node" are three different facts, and collapsing them into
an empty list teaches users the graph is incomplete when it is not.

## 9.6 Review API

`REQ-MCP-010` — The review API exposes:

| Endpoint | Purpose |
|---|---|
| Queue listing | Filterable by severity, corroboration gap, judge disagreement, age |
| Item detail | The candidate, its source span, the resolved source text, what each guardrail layer said, and the graph context around it |
| Approve / reject | With acknowledgement checklist and recorded identity (`REQ-GRD-025`) |
| Decision history | What was decided, by whom, and **what they were shown at the time** (`REQ-GRD-026`) |

The last one exists so an approval can be audited later against the information
actually available to the reviewer — not against what the graph looks like now.

## 9.7 Context budget and response shaping

| Mechanism | Applies to | Never applies to |
|---|---|---|
| Structural compression of tool responses | All read-only tool responses between server and client | **Provenance fields — hard exclusion** (`REQ-COST-006`) |
| Prompt-directive compression | Extraction and judge prompts | User-facing output; any text that becomes stored specification content (`REQ-COST-007`) |
| Cache stabilisation | Bi-temporal fields normalised before repeated calls so caching can engage (`REQ-COST-005`) | — |

`REQ-MCP-007` / `REQ-COST-006` — Compression is configured with an explicit
field-level exclusion list covering every provenance field, enforced at the
guardrail boundary rather than left as a tuning default. **Provenance is not
compressible** — a shortened source span is a broken source span.

## 9.8 Client integration

| Client | Registration | Depth default |
|---|---|---|
| Claude Code / Desktop | Project `.mcp.json` entry or custom connector | 3-hop |
| GitHub Copilot (Agent mode) | Generated agent discovery file pinning the read-only tool set | 2-hop |

Both reach the identical server over the identical protocol. The generated
discovery file is a **convenience, not a different permission model**
(`REQ-MCP-005`), and it is generated from the same source as every other client's
definition so they cannot drift (`REQ-SKL-003`).

## 9.9 CI conformance check

`REQ-MCP-008` — A CI status check is exposed, agent-agnostic by construction —
identical for human-authored, Copilot-authored and Claude-authored changes.

It fails when a change:

- introduces code implementing a requirement with no traceability chain;
- breaks an existing chain (DQ-017 regression);
- lands a `Transition` change without corresponding AC coverage (DQ-024);
- drops the scoped composite quality score below the release threshold;
- disagrees with the ontology's four-place governance rule.

## 9.10 Acceptance tests for this subsystem

| Test | Asserts |
|---|---|
| Provenance round-trip | Content extracted back out of a rendered deck/site resolves every claim to a real episode |
| Placeholder detection | A template placeholder left unfilled fails the content pass |
| Academy version lock | Content describing a non-live schema version fails |
| Rejection linkage | A guardrail rejection message names a specific reason and links to a real page |
| Contract conformance | Every tool's declared schema matches its real subprocess behaviour |
| Error explicitness | A permission denial, an empty result and a missing node produce three distinguishable responses |
| RBAC scoping | A cross-team request with a valid node id is denied |
| Compression exclusion | Provenance fields survive compression byte-identical |
| Site freshness | A graph change triggers regeneration; the deck does not regenerate |
| Gate determinism | The same graph state produces the same gate status on repeated runs |
