# Métis — Deep Review: What's Missing

Went back through all 23 documents rather than working from memory of what I intended to build. Found one real leftover bug during this pass (a GitHub check name still said `atlas/spec-conformance` after the rename — fixed in `metis-specification.md`). Below is what's genuinely missing or underdeveloped, not a padded checklist — each item explains why it matters, not just that it's absent.

---

## What's solid (brief, for context — not the focus of this review)

Architecture, ontology (~49 entities + code graph), bi-temporal model, ingestion (7 connectors + Athena ETL reuse), the full guardrail stack (12 Constitution Articles, 46 `CONST-*` rules, 3 amendments), 22 data-quality metrics, the security/trust-boundary framework, the Behavior-Model→Test pipeline, cost analysis grounded in real numbers, and the naming/positioning history are all built with real depth and cross-checked validation throughout. That's not what needs attention right now.

---

## 1. No interface for the humans doing the actual review work

**This is the gap I'd fix first.** The entire guardrail architecture (§7) depends on humans reviewing quarantine-tier items — Article IV, the Fool-Proof framework's acknowledgment checklist, `AF-005`, all of it assumes someone sits down and works a queue. What that queue actually *is*, today: a raw Cypher query (`WHERE lifecycle_state='Quarantine'`) that a reviewer would need direct Neo4j Browser access and query-writing ability to run. There's no reviewer-facing screen — no "here's your queue, here's the risk tag, here's the acknowledgment checklist, click approve or reject." For a system explicitly designed around **non-expert users** (the Fool-Proof framework's entire premise), requiring raw Cypher to do the one recurring human task in the system is a real contradiction, not a minor omission.

## 2. No ontology migration strategy

The ontology has already changed twice in this conversation (the code-graph extension added `CALLS`/`IMPORTS`/`INHERITS`; the single-database consolidation moved several structures into Neo4j-native form). Nothing in the design says what happens to **already-ingested nodes** when the ontology changes again — is there a schema-version property on nodes, a migration script convention, a compatibility window? Right now, evolving the ontology a third time has no defined procedure, which means it would be improvised under pressure instead of following a process the Constitution already holds everything else to.

## 3. Pipeline operational health has no monitoring — only content-quality metrics do

§7.1's guardrail metrics (source-grounding rate, rejection rate, etc.) and the 22 DQ metrics measure whether the *content* is good. Nothing measures whether the *pipeline* is healthy: connector polling lag against Athena's `updated_at` columns, Cognify extraction failure/retry rates, LLM API error rates, queue depth if ingestion falls behind. These are two different failure modes — "the graph is filling up with bad facts" vs. "the graph has stopped filling up at all" — and only the first one has instrumentation. A silent connector failure (Athena's polling job dies, nobody notices) would currently show up as nothing at all, not as an alert.

## 4. Bi-temporal "never delete" vs. real deletion requirements — a real, unaddressed tension

The whole temporal model (§5) is built on invalidating, never deleting — `t_invalid` gets set, the history stays. That's the right default for traceability. But real compliance sometimes requires actual erasure (an employee's identity data on a `Requirement.author` field after they leave, a GDPR-style deletion request, a customer's data in an ingested support ticket). Nothing in the current design reconciles "never delete" with "sometimes you must delete" — this needs an explicit answer (e.g., a narrow, audited hard-delete path that's the one deliberate exception to P1), not a silent gap that surfaces the first time someone actually asks for a takedown.

## 5. Sending proprietary source code to an external LLM API has no reviewed policy

The cost model (§9.3, the 15K-test review) assumes Cognify calls go to Haiku/Sonnet-class models over the Anthropic API. The security framework (Amendment 2) covers *access control within* the platform thoroughly — who can see what in the graph. It does not cover the separate question of **whether your org's actual source code, requirements, and Jira content are permitted to leave your network boundary to an external LLM vendor at all** — that's a data-handling/DPA/vendor-review question, not a guardrail-content question, and it's a different kind of review (legal/compliance) than anything built so far addresses. Worth resolving before Phase 0 starts ingesting real proprietary repos, not after.

## 6. The adversarial injection corpus is a one-time test set, not a running practice

12 cases across 9 categories were built to validate Layer 9 once. Nothing says this corpus gets run again — as a CI check every time the guardrail stack changes, or periodically against production data to catch drift. A one-time test that was never wrong the day it was written doesn't tell you anything about the system six months and several prompt-engineering iterations later.

## 7. No onboarding runbook for a new project or team

The calibration-batch concept (`CONST-036`) and the per-project `test_id_conventions` mechanism both assume someone already knows what to configure. There's no step-by-step "a new team wants Métis to ingest their repo — here's what to do, in order" document. Given the earlier finding that `test-suite-ingest` alone needs a confirmed pattern per project before it can run, and that this could be a genuinely large number of projects (100K Jira tickets across "projects," plural), this is going to be a repeated operational task, not a one-time setup — worth having a real runbook for rather than reconstructing the steps from scattered requirements each time.

## 8. Métis has no defined testing strategy for its own code

Slightly uncomfortable to flag, given what this platform is *for*: nowhere in 23 documents is there a stated approach for testing Métis's own implementation — the Cognify extraction logic, the guardrail layer implementations, the MCP tool handlers. A platform built to generate functional/performance tests for other systems, with no documented test strategy for itself, is the kind of gap worth closing before, not after, someone notices the irony in production.

## 9. MCP server auth is stated, not designed

To be fair to what's already there: §11.2 does specify OAuth2, scoped per-user, tokens carrying `owner_team`/RBAC assignment — this isn't a total gap. But it's one requirement line, not a design: no token lifecycle (expiry, refresh), no session-revocation story (what happens when someone's access is pulled mid-session), no answer for how a Claude Code or future non-Copilot client authenticates differently than the OAuth2-for-Copilot path already sketched. Thin, not absent.

## 10. Multi-language coverage for AST-based parsing is assumed, not verified

The code-graph extension and `application-code`/`test-suite-ingest` connectors were designed and reasoned about almost entirely in Java terms (matching Athena's real Java Spring Boot codebase and your own Java-based test automation project). Tree-sitter itself is multi-language, so this is likely fine — but nothing in the design explicitly confirms coverage for non-Java projects if your ~100K-ticket, multi-project scope includes any, and the `project_test_id_conventions`/pattern-per-project mechanism was designed with Java's `@TestId`-style annotations as the running example throughout.

---

## Suggested priority, if you want one

**Fix before Phase 0 starts ingesting anything real:** #5 (LLM data-handling policy) — this is the one item where waiting has actual legal exposure, not just operational awkwardness.

**Fix before Phase 0 generates real review volume:** #1 (reviewer UI) — the guardrail stack's entire safety model depends on humans actually doing the review step; right now that step requires Cypher fluency.

**Fine to defer, but track explicitly rather than forget:** #2, #3, #4, #6, #7, #8, #9, #10 — real gaps, none of them block a small pilot, all of them will matter at the scale you've already described (100K tickets, 15K tests, multiple projects).

Want me to build out any of these — the reviewer UI is probably the highest-value next artifact, given it's the one blocking the actual human workflow this whole system depends on?
