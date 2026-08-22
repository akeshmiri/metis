# Gap Remediation — Constitution Amendment 5
## Fixing Nine of the Ten Flagged Gaps With Concrete Decisions, Not Just Frameworks

The tenth (reviewer UI) is built separately as an actual interface, not a policy document — see `metis-review-queue-ui.html`.

---

## 1. Vendor data-handling policy for external LLM calls (was gap #5 — the one with real legal exposure)

Checked Anthropic's actual current policy rather than assuming. The relevant facts: the commercial API defaults to **30-day retention with no training on customer data**, and a **Zero Data Retention (ZDR) agreement is available for eligible enterprise customers** — inputs/outputs aren't stored at all beyond abuse-screening, but it requires a direct commercial agreement with Anthropic (not self-serve), and it doesn't cover every API surface (Batch, Files API, and Console/Workbench are excluded from ZDR even when the org has it elsewhere).

**Decision:**

**CONST-051.** Content reaching an external LLM API (Cognify extraction, Layer 6 judge calls, code archaeology's intent-reconstruction step) is classified before the call, not after:
- **Public/Internal** (most requirements, most test code, public API specs) — proceeds under the org's standard API terms (30-day retention, no training) without further gating.
- **Confidential** (proprietary algorithms, unreleased-feature code, anything under an active NDA with a third party) — MUST route through a Zero Data Retention agreement. If the org does not have one in place, ingestion of `Confidential`-tagged content is **blocked at the connector level**, not merely flagged, until ZDR is confirmed active.
- **Restricted** (credentials, keys, anything BS-002 already prohibits from leaving the extraction boundary) — never reaches an LLM call at all; this is unchanged, already covered by the existing security framework, restated here for completeness.

**CONST-052.** `Confidential` classification is a `Repository`/`Service`-level property set during onboarding (§4 below), not inferred per-file by the pipeline — a wrong inference here is exactly the kind of thing that shouldn't be guessed, per RPI's Forbidden Substitutions rule. A repository not yet classified defaults to `Confidential` (fail closed), never `Public/Internal` (fail open).

**CONST-053.** Before Phase 0 ingests any real proprietary repository, the org's actual API agreement status (standard 30-day retention vs. ZDR) MUST be confirmed and recorded against `CONST-051`'s classification scheme — this is the one item in this whole remediation pass with real legal exposure if skipped, not just operational awkwardness.

---

## 2. Right-to-erasure exception to the bi-temporal "never delete" model (was gap #4)

**Decision:** a narrow, audited hard-delete path — the one deliberate exception to P1 (bi-temporal, invalidate-don't-delete).

**CONST-054.** Hard deletion is permitted **only** for: (a) a legally-required erasure request (GDPR/CCPA-class), (b) PII scrubbing after an employee's offboarding where retention would violate policy, or (c) active incident containment (e.g., a credential accidentally ingested despite BS-002). No other reason qualifies — "the data is just old" or "nobody uses this anymore" are `t_invalid` cases, not deletion cases; the ordinary bi-temporal model already handles those correctly.

**CONST-055.** A hard-delete action requires **two-person sign-off** (never unilateral) and produces a permanent, minimal audit record — `request_id`, legal basis, requestor, approver, timestamp, and the scope of what was deleted (node/relationship count and type, never the deleted content itself) — retained indefinitely even though the underlying data is gone. This preserves auditability of *the fact that a deletion happened* without preserving the thing that was deleted, which is the actual property a right-to-erasure request requires.

**CONST-056.** Hard deletion cascades to any `Transition`/`TestCase`/derived content whose sole corroborating source was the deleted node — those derived facts drop to `quarantine` tier for re-review rather than being silently deleted alongside their source, since their own correctness doesn't necessarily depend on the deleted node's content (e.g., a `Transition` corroborated by both a now-deleted document and the code graph retains its `Approved` status; one corroborated only by the deleted document does not).

---

## 3. Guardrail regression testing as an ongoing practice, not a one-time corpus (was gap #6)

**CONST-057.** The 12-case adversarial injection corpus (`metis-adversarial-injection-corpus.json`) runs as a **required CI check** on any change to the guardrail stack's implementation (Layers 1–9, §7) — not just once during design validation. A guardrail-stack change that doesn't pass all 12 cases blocks merge, the same way any other required status check does.

**CONST-058.** Independently of code changes, the corpus also runs **quarterly against a random sample of production ingestion** — not to test the corpus itself, but to catch drift: a guardrail that correctly rejected all 12 synthetic cases at design time can still degrade against real, messier inputs six months later as the underlying LLM models change versions. A quarterly real-data check is the only way to catch that kind of drift before a review-queue miss does.

---

## 4. Ontology migration strategy (was gap #2)

**CONST-059.** Every node carries a `schema_version` property, set at write time to the ontology version active when it was written. This is not retroactively backfilled onto existing nodes when the ontology changes — it's a forward-looking marker so a future migration script can identify which nodes need transformation.

**CONST-060.** An ontology change that adds a new entity/relationship type (like the code-graph extension did) requires no migration — existing nodes are simply silent on the new type until re-processed. An ontology change that *alters* an existing entity's required properties or relationship semantics (a genuine breaking change, not yet needed but foreseeable) requires a numbered migration script following the same convention as the schema files themselves (`metis-migration-NN-<description>.cypher`), and a defined compatibility window: the platform's query layer supports both the old and new shape for **90 days** post-migration (matching `CONST-010`'s existing rollback window, for consistency), after which the old shape is no longer supported and any node still on it is a data-quality defect, not a supported state.

---

## 5. Pipeline operational health monitoring, distinct from content-quality metrics (was gap #3)

**CONST-061.** Four operational metrics, tracked separately from the 22 DQ metrics (which measure content quality, not pipeline health):

| Metric | What it catches |
|---|---|
| `connector_lag_seconds` (per connector, vs. `change_detection_column`) | A connector silently falling behind Athena's own data — the "ingestion just stopped and nobody noticed" failure mode |
| `extraction_failure_rate` (Cognify calls erroring, not just producing low-confidence output) | Distinguishes "the model judged this uncertain" (a guardrail doing its job) from "the pipeline is broken" (an operational incident) |
| `llm_api_error_rate` (rate-limit, timeout, auth failures) | Vendor-side or credential issues, not content-quality issues |
| `ingestion_queue_depth` | Backlog building up faster than it's processed |

These are exposed as new Grafana panels alongside the existing guardrail-metrics dashboard (§12.4), on Athena's existing schema-catalog pattern — same mechanism, different metric category, not a new reporting surface.

---

## 6. Onboarding runbook for a new project/team (was gap #7)

**Concrete steps, not a re-derivation of scattered requirements each time:**

1. Confirm `project_test_id_conventions` entry for the project (per-project pattern, `REQ-METIS-CONN-06`) — halt here if unconfirmed, do not proceed on a guess.
2. Classify the repository's data-sensitivity tier (`CONST-051`/`052` above) — default `Confidential` until explicitly set otherwise.
3. Confirm Tree-sitter grammar coverage for the project's actual language mix (§8 below) — halt here if an unsupported language is detected in more than a token fraction of the codebase.
4. Run the calibration batch (`CONST-036`, 500-unit sample) against this project specifically.
5. Human review of calibration results — confirm the `auto_write`/`quarantine`/`rejected` distribution looks reasonable for this project before enabling full ingestion (a project with wildly different ratios than the platform-wide targets in `DQ-002` may need connector-specific tuning, not a blanket assumption that Phase 0's targets apply everywhere).
6. Enable full ingestion; monitor `DQ` metrics and the new operational metrics (§5 above) daily for the first two weeks, then fall back to the standard cadence (`CONST-035`).

---

## 7. Métis's own testing strategy (was gap #8)

**CONST-062.** Métis's own implementation is held to a testing standard, not exempted from one just because it's the platform that generates tests for others:
- **Deterministic components** (EARS parser, connector manifest validation, migration scripts, the reachability/determinism/completeness checks from Amendment 4) get conventional unit tests — these are pure functions over structured input, no different from any other code.
- **Guardrail logic** is tested via the adversarial corpus (§3 above) as its primary regression suite, extended over time as new failure modes are found in production — not reinvented as a separate test framework.
- **MCP tool handlers** get contract tests validated directly against `metis-mcp-tool-contracts.json`'s existing input/output schemas — the schemas already define what a valid call/response looks like; testing against them is nearly free given they already exist.

---

## 8. Multi-language coverage verification (was gap #10)

**CONST-063.** Tree-sitter grammar availability is confirmed **per project**, not assumed platform-wide, as part of onboarding step 3 (§6 above). A project whose codebase includes a language without a mature Tree-sitter grammar (or without the corresponding code-graph extraction logic built out) has that portion of `application-code`/the code-graph extension explicitly marked unsupported for that language — falling back to structural containment only (no `CALLS`/`IMPORTS`/`INHERITS` edges for that portion), rather than silently producing incomplete or wrong call-graph data without flagging it.

---

## 9. MCP server auth — filling in the token lifecycle (was gap #9)

§11.2 established OAuth2, scoped per-user, team-scoped tokens — correct but thin. Filling in the lifecycle:

**CONST-064.** Access tokens are short-lived (1 hour), refresh tokens longer-lived (30 days) and revocable. Token validity is checked **at every request**, not cached from issuance — if a user's `owner_team`/RBAC assignment changes mid-session (they're moved teams, or offboarded), the *next* request re-evaluates against current team membership rather than trusting a token that encoded now-stale permissions. This closes the gap the original one-liner left open: scoping a token at issuance isn't the same as scoping it for the token's entire lifetime.

---

## What's still open after this pass

| Item | Status |
|---|---|
| Reviewer UI (was gap #1) | Built separately — `metis-review-queue-ui.html` |
| Which specific ZDR terms the org can actually get from Anthropic | A real commercial negotiation, not something resolvable in a document — `CONST-053` requires confirming status before proceeding, not assuming a specific outcome |
| Whether 90 days is the right migration compatibility window, or should match a different cadence | Chosen for consistency with the existing rollback window (`CONST-010`) — reasonable default, not load-tested |
