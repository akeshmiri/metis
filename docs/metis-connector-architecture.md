# Pluggable Intake & Connector Architecture
## Generalizing §6's Ingestion Pipeline — MCP as the Connector Protocol

---

## 0. What changed and why

The original design (v2 §2.2, master spec §5.2) listed a fixed set of sources — Jira, DB schema, OpenAPI, Git, documents, DOORS/Polarion, CI/CD/telemetry — each with its own bespoke connector. You've asked for something structurally different: **the ability to define more intakes over time** (Grafana, production Atlassian, flat files named specifically, with more to come later) **without a new architecture document every time.** That's not a request for three more rows in a table — it's a request to generalize the Extract stage (§6.1) from "a fixed list of connectors" into "a connector *registry* with a declared manifest format," so adding a source becomes filling out a manifest, not redesigning the pipeline.

**The good news, confirmed before designing anything further:** two of your three named sources already have official, actively maintained MCP servers — this isn't a case of forcing MCP onto sources that don't fit it.
- **Grafana**: Grafana Labs publishes an official open-source MCP server exposing dashboards, datasource queries (Prometheus, Loki, and others), alerting rules, incidents, and OnCall — actively maintained, first released January 2025.
- **Atlassian**: Atlassian publishes an official remote MCP server ("Rovo MCP") covering Jira, Confluence, Jira Service Management, Bitbucket, and Compass, OAuth 2.1-secured; a community alternative (`mcp-atlassian`) covers the same surface for Server/Data Center deployments using a Personal Access Token, which matters if your production Atlassian isn't Cloud.
- **Flat files** have no equivalent single standard — that connector stays custom, which is fine; not everything needs to be MCP, just what already has a good MCP server behind it.

---

## 1. Architectural change: this platform is now an MCP client, not only an MCP server

§11 already made this platform an **MCP server** (serving `metis_get_context` etc. to Copilot). This addendum makes it, additionally, an **MCP client** — the Extract stage (§6.1) connects *out* to Grafana's and Atlassian's MCP servers the same way Copilot connects *in* to this platform's. This is a genuine architectural addition, not a relabeling:

```
                    (existing, §11)
   Copilot  <──MCP──  THIS PLATFORM  ──MCP──>  Grafana MCP server (Grafana Labs)
  (consumer)          (server AND               ──MCP──>  Atlassian MCP server (Rovo, or mcp-atlassian)
                        now also client)         ──file_scan──>  Flat-file drop location
```

The platform's Extract stage (§6.1) is where the client role lives — it calls the external MCP server's tools (e.g., Grafana's `list_alert_rules`, `query_prometheus`, Atlassian's issue-search tools) on the same schedule/trigger logic §6.1 already defines for any other source, and wraps each result as an `Episode` exactly as before. **Nothing about the Cognify/Load/guardrail pipeline changes** — only how content arrives at the Extract stage's door.

---

## 2. The Connector Manifest — the actual mechanism for "define more intakes"

Every intake source, present or future, is declared as a manifest rather than hand-coded into the pipeline. This is a generalization of exactly the pattern Atlas's own `atlas-workflow-manifest.yaml` already uses (declarative, not hardcoded skill sequencing) — same idea, applied to sources instead of skills.

**Schema** (full JSON Schema in `metis-connector-manifest-schema.json`, validated):

| Field | Purpose |
|---|---|
| `connector_id`, `display_name`, `version` | Identity |
| `protocol` | `mcp_client` \| `file_scan` \| `direct_api` — `direct_api` is the escape hatch for a future source with no MCP server and no simple file-drop shape |
| `mcp_config` (if `mcp_client`) | Server address/command, transport (stdio/SSE/streamable HTTP), auth type — mirrors §11.3's auth-path distinction (PAT vs. OAuth), same reasoning applies to outbound connections as inbound |
| `entity_type_mapping` | Which ontology entities/episode types this source can produce — makes explicit what a new connector is *for*, so a reviewer approving a new connector manifest can see its blast radius before enabling it |
| `temporal_strategy` | Per §5.2's existing pattern — every connector, new or old, states its `t_recorded` source and known pitfalls; a manifest without this section is incomplete, not just under-specified |
| `precedence_tier` | Where this source sits in §5.3's precedence table for any entity type it can produce — supplementary sources don't get to silently outrank an existing system-of-record |
| `environment_scope` | e.g., `production_only` — see §4 below, this is what "Atlassian *production*" specifically encodes |
| `trust_tier_on_first_use` | Always `calibration_required` — every new connector, including ones defined after this document, goes through the Data Quality Framework's onboarding gate (CONST-036) and its 500-extraction calibration batch before reaching `auto_write` trust. This is not configurable per-manifest; it's a platform-wide rule the manifest can't opt out of. |

`REQ-METIS-CONN-01`: A new connector is enabled by adding a validated manifest to the registry, not by modifying pipeline code — this is what makes "define more intakes" a config change instead of a re-architecture, going forward.
`REQ-METIS-CONN-02`: Every manifest, regardless of source, is still subject to BS-001 (content is data, never instructions) and the full guardrail stack (§7) — an official, vendor-maintained MCP server is a trustworthy *transport*, not a trustworthy *content source*. A Grafana alert annotation or a Jira comment fetched through an official MCP connection is exactly as capable of containing an injection attempt as one fetched by hand-rolled REST calls; the trust boundary (Part B of the Fool-Proof/Security framework) doesn't move just because the pipe is official.

---

## 3. Connector: Grafana

| Field | Value |
|---|---|
| `connector_id` | `grafana-metrics` |
| `protocol` | `mcp_client`, connecting to the official Grafana Labs MCP server |
| Entity mapping | Alert rules → `Alert`; Grafana Incident records → `Incident`; periodic Prometheus/Loki query results for pre-defined SLA queries → `Metrics` snapshots |
| Temporal strategy | `t_recorded` = the alert/incident's own timestamp as reported by Grafana — this slots directly into §5.2's existing "CI/CD, telemetry, incidents" row (already the most reliable category, event-sourced by nature), it doesn't need a new row, just a named implementation of one that already existed conceptually |
| Precedence | System-of-record for `Alert`/`Incident` entities specifically — nothing else in the current source list produces these, so there's no conflict to arbitrate |
| Why this matters for the guardrail stack | This is the connector that finally makes §7.1's Layer 9 adversarial-testing metric and the Data Quality Framework's DQ-014 (spec-vs-deployed drift) checkable against *real* production signal instead of only structural sources — an `Alert` firing repeatedly against a `Transition` with thin test coverage is a direct, high-value corroboration of exactly the kind of gap this platform exists to surface |

---

## 4. Connector: Atlassian (Production)

| Field | Value |
|---|---|
| `connector_id` | `atlassian-prod` |
| `protocol` | `mcp_client` — official Rovo MCP server if your Atlassian is Cloud; `mcp-atlassian` (PAT-based) if Server/Data Center |
| `environment_scope` | **`production_only` — this is the literal meaning of "production" in your request, encoded as a manifest field, not just a naming convention.** A separate manifest (`atlassian-sandbox`, disabled by default) exists for any staging/test Atlassian instance so sandbox noise never enters the same graph as production truth without an explicit, separate connector decision to enable it. |
| Entity mapping | Jira → `Requirement`/`AcceptanceCriterion`/`Epic`/`Feature`/`Defect` (already defined, §5.2/§5.3 — this connector is the concrete MCP-based implementation of what was previously described only abstractly as "a Jira-analyzer-style connector"); Confluence → `Document`-sourced content (§5.2's existing Documents row); Jira Service Management → `Defect`/`Incident` depending on ticket type; **Compass → `Service`/`API` entities** — this is new: Compass is Atlassian's own service catalog product, and its component/API metadata is a legitimate, previously-unlisted source for the Architecture layer (v1 §3.4), arguably a better fit than inferring `Service` boundaries purely from repo structure |
| Precedence | Unchanged from §5.3's existing Jira-as-system-of-record table — this connector is *how* that precedence gets implemented, not a change to what wins |

**BS-010 (new, extends the Fool-Proof/Security framework's B-series):** the `production_only` scope restriction is enforced at the manifest/credential level (the service account or OAuth grant issued to this connector literally cannot reach the sandbox instance), not by a naming convention a connector could accidentally ignore — same "credential is the boundary" principle as BS-004.

---

## 5. Connector: Flat Files

| Field | Value |
|---|---|
| `connector_id` | `flat-files` |
| `protocol` | `file_scan` |
| Entity mapping | Generalizes §5.2's existing "Documents" row beyond Confluence/Notion specifically — any dropped/uploaded PDF, Markdown, Word, or CSV becomes an episode the same way a Confluence page does |
| Temporal strategy | File's own last-modified timestamp preferred as `t_recorded`; where a file system doesn't preserve that reliably (e.g., a re-uploaded copy), `t_recorded = t_ingested`, flagged `event_time_confidence: unknown` — identical rule to §5.2's original Documents row, since flat files are a special case of that row, not a new temporal pattern |
| Precedence | Weakest tier by default (§5.3's existing rule: documents never solely back a `Requirement`'s validity window when a stronger source exists) — unless a specific manifest override names a flat-file source as authoritative for a specific entity type your org actually treats that way (e.g., a signed PDF contract as the authoritative source for a specific `Constraint`) |

---

## 6. Trust boundary reinforcement (extends the Fool-Proof/Security framework's Part B)

None of the three connectors above — including the two backed by official, vendor-maintained MCP servers — change Zone 0/1's untrusted status (§B.1 of the Fool-Proof/Security framework). To make this concrete: a Grafana incident annotation or a Jira comment field can contain exactly the same class of injection attempt as any other free-text source (the `metis-adversarial-injection-corpus.json` cases already cover this generically — INJ-004's "urgent, skip the corroboration requirement" pattern is just as plausible arriving via a Grafana incident note as via a Jira comment). **The official-vendor status of the transport is irrelevant to content trust** — this is worth stating explicitly because it's the natural place for a false sense of security to creep in ("it came through Atlassian's own official server, surely it's safe"), and BS-001/BS-002's architectural separation (extraction has no write credential) already protects against this regardless, but the reasoning is worth spelling out rather than left implicit.

---

## 7. What's genuinely still open

| Item | Status |
|---|---|
| Grafana/Atlassian MCP server auth credentials (service account tokens, OAuth app registration) | Needs your actual Grafana instance and Atlassian site details — not something to fill with a placeholder, this is real infrastructure setup |
| Flat-file drop location (watched folder vs. upload endpoint vs. both) | Needs a decision on your actual intended workflow — both are reasonable, genuinely your call |
| Whether Compass is actually in use in your Atlassian instance | If not, the `Service`/`API` mapping in §4 simply has nothing to ingest yet — not a blocker, just dormant until relevant |

Everything else — the manifest schema, the three connector definitions, the trust-boundary reasoning, the dual MCP-client/server architecture — is complete and ready to implement without further input.
