# Quality Engineering Constitution — ADOPTED
## Requirement Management System (Full Platform Scope — All Stages and Skills)
### Adopted v1.0, derived from the Critical-Systems Constitution Template

---

## Adoption Statement

This is the template Constitution (`metis-constitution-template.md`) with every bracket filled and scoped explicitly to **the entire requirement-management platform** — not just the new graph-extension tools, but every existing Atlas workflow, agent, and skill from the archive: intake, business analysis, specification collection, test design, test generation (API/web/performance), code review, merge-request gating, defect/bug reporting, quality reporting, and the Athena analytics integration. **(Open question surfaced by the later Métis rename, not yet resolved — see the note at the end of this file.)**

**Why this system counts as critical, even though it's a requirement-management tool rather than a customer-facing product:** every downstream system this platform generates specs, tests, and merge decisions for inherits this platform's correctness. A fabricated requirement, an unverified "passing" test, or a merge approved on hallucinated grounds here doesn't fail loudly in this system — it fails quietly in whatever it certified as ready. That's the justification for holding this platform itself to the critical-system bar rather than a lighter one.

**Update (this revision):** every bracket is now filled, including CONST-020's compliance regime and CONST-021's target load — see the closing summary for how each was resolved without fabricating a fact only you could actually know.

---

## Preamble (adopted)

This Constitution is the highest-precedence rule set governing quality engineering across this platform's entire scope. It is checked before any other validation rule. Where any other document, convention, or individual judgment conflicts with an Article below, this Constitution governs.

**Critical-system threshold (adopted):** a defect is treated as critical-system-severity if it causes (a) an incorrect `Approved`-status promotion of an unverified or fabricated fact anywhere in the platform, (b) loss or corruption of traceability data such that a requirement-to-test-to-code chain can no longer be reconstructed, (c) a merge-request or quality report certifying work as tested/ready when it was not, or (d) any safety, regulatory, or irreversible-data-loss impact in a system this platform serves. This is a deliberately broader definition than "the platform crashed" — for a QE platform, silent incorrectness is the higher-severity failure mode.

---

## Article I — Traceability & Specification Integrity

**CONST-001** through **CONST-004**: adopted as written in the template, unmodified. These govern `business-analyzer`, `intake-processor`, `downstream-analyzer`, and `jira-analyzer` directly — every requirement these skills produce or ingest is subject to CONST-001–004 before it can back a test, a merge, or a quality report.

**CONST-001a (new, platform-specific):** `intake-processor`'s unified intake from any evidence source does not itself confer `Approved` status — intake is Article I's Research stage (RPI), not its Implementation stage. An intake result is `Draft` until `business-analyzer`'s synthesis stage and this Constitution's corroboration rule (CONST-003) have both run.

---

## Article II — Test Coverage & Evidence

**CONST-005 (adopted, filled):**
- Functional test coverage: **100%** of `Approved` `Transition`s reachable from an `Approved` `Requirement`, before implementing code ships.
- Integration/API coverage (`test-developer`'s `api-developer` specialist): **≥ 80%** of `Endpoint`s with a direct `Requirement` trace.
- Performance coverage (`locust-workflow`): mandatory for every `Transition` tagged `Performance: SLA-critical` (see CONST-021).
- Security-relevant paths (auth, payment, data-deletion): negative + boundary cases mandatory per CONST-008, independent of overall percentage — this floor cannot be traded off against a higher number elsewhere.

**CONST-006, CONST-007 (adopted, filled):**
- Stale-coverage rule adopted unmodified.
- Evidence retention: **5 years**, or the longest retention period contractually/regulatorily required for any system this platform serves, whichever is longer — re-evaluate this number the moment CONST-020's compliance question below is answered, since that answer may raise it.

**CONST-008 (adopted, unmodified).**

**CONST-005a (new, platform-specific):** `test-case-reporter` and `report-generator` outputs claiming a coverage number are themselves subject to CONST-007 — a coverage percentage in a report without the underlying `TestCase`/`TestRun` data behind it is not evidence, it's a claim, and is treated as `Draft`-tier until the underlying data is confirmed queryable.

---

## Article III — Change Control & Release Gating

**CONST-009 (adopted, unmodified)** — enforced by `merge-request-creator`'s gating step and `code-reviewer`.

**CONST-010 (adopted, filled):** rollback recency window — **90 days**. Applies to this platform's own deployments (the graph and episode log — both the single Neo4j Enterprise database, per the storage-consolidation decision; there is no separate Postgres instance — and the MCP tool servers) as well as to systems it certifies — a platform that can't roll back its own bad ingestion run has no standing to require rollback readiness of anything else.

**CONST-011 (adopted, filled):** emergency-change follow-up window — **3 business days** (tightened from the template's suggested 5, given this platform's critical-system classification above). Enforced through `bug-reporter`'s defect trail and `merge-request-creator`'s exception logging.

**CONST-012 (adopted, unmodified).**

---

## Article IV — AI-Generated Artifact Governance

**CONST-013 through CONST-016: adopted unmodified, and explicitly extended to cover every AI-generation point in the full skill set, not only the new graph-extension tools:**

| AI-generation point | Governed by |
|---|---|
| `business-analyzer`'s canonical spec synthesis | CONST-013, 014 |
| `test-designer`'s scenario/test-case design | CONST-013, 014 |
| `test-developer` (`api-developer`/`web-developer`) code generation | CONST-013, 014, 015 |
| `locust-workflow`'s generated load-test scripts | CONST-013, 014, 015 |
| `code-reviewer`'s generated review comments/verdicts | CONST-013 — a review verdict is itself an artifact requiring accountability, not exempt because it's evaluative rather than generative |
| `report-generator`/`quality-reporter`'s generated reports | CONST-013 — a quality report is a claim about the system, subject to the same no-fabrication rule as any other generated content |
| `merge-request-creator`'s generated MR descriptions | CONST-013, 014 |
| `bug-reporter`'s generated defect descriptions | CONST-013, 014 |
| `metis_submit_episode` (new graph-extension write path) | CONST-013, 014, 015, **and CONST-016 stays in force: disabled by default** |

**CONST-016 (adopted, unmodified):** applies platform-wide — no autonomous write path anywhere in this system auto-promotes without the track record this Article requires.

---

## Article V — Security & Data Protection

**CONST-017, CONST-018, CONST-019: adopted unmodified.**

**CONST-020 (resolved — filled with an honest default, not fabricated):** applicable compliance regime — **"No compliance regime formally asserted."** This is a real, adopted value, not a placeholder: it means every `BusinessRule` tagged `Compliance` today must trace to a named, verifiable source (a specific contract clause, a specific statute) exactly as CONST-020 already required — and since none is asserted platform-wide, **no `BusinessRule` may currently claim a platform-wide compliance basis; any compliance claim must cite its own specific source at the individual rule level.** This is stricter than either asserting a named regime (which would let individual rules inherit unverified authority from the platform-wide claim) or leaving the bracket genuinely blank (which the original template correctly refused to do). If a real regime is later confirmed (SOC 2, GDPR, etc.), that's a CONST-032-style amendment — tightening a currently-strict default by naming a specific, verifiable basis, not weakening anything.

---

## Article VI — Performance & Resilience

**CONST-021 (resolved — grounded starting estimate, not guessed):** target load — **3× a starting assumption of 15 concurrent agent sessions (Copilot + eventual Claude Code) and a 50,000-episode ingestion burst**, re-validated quarterly. This is sized against a QE organization in the range this platform's ontology and MVP scope implies — v1 §16's scalability analysis used 500 services/5,000 requirements/50,000 tests as its enterprise reference point, and a full-project backfill at that scale is the realistic worst-case burst. **This is an engineering estimate from stated assumptions, explicitly not a fact about any specific organization** — replace both the session count and the burst size with real numbers the moment Phase 0 usage data exists (§18.3), and treat this starting figure as directional, not load-tested.

**CONST-022 (adopted, unmodified)** — directly governs this platform's own `ExternalAPISpec` corroboration requirement (§4.2) as well as systems it tests.

---

## Article VII — Defect Management & Severity

**CONST-023 (adopted, unmodified)** — enforced by `bug-reporter`.

**CONST-024 (adopted, filled):** severity taxonomy — **Critical / High / Medium / Low**, defined for this platform specifically:
- **Critical:** any incorrect `Approved` promotion of an unverified fact; any traceability chain break; any merge/quality-report certifying untested work as tested.
- **High:** stale coverage not detected before release; a corroboration requirement (CONST-003/CONST-019) bypassed.
- **Medium:** a Quarantine-tier item aging past its expected review window without being a Critical-path blocker.
- **Low:** cosmetic/reporting inconsistencies with no traceability or correctness impact.

Critical and High block release of the affected component, no override without CONST-011's named-approver-plus-justification pattern.

**CONST-025 (adopted, unmodified)** — this is the rule that makes `bug-reporter` + `report-generator` findings feed back into Article I–VI strengthening, not just per-instance fixes.

---

## Article VIII — Environment & Data Integrity

**CONST-026 (adopted, unmodified).**

**CONST-027 (adopted, filled):** drift verification — **infrastructure-as-code diff**, following the precedent already established by Athena's own Helm-chart-based deployment (`orchestration/athena/`) — this platform's environments should be defined the same way, with drift checked as a diff against the committed chart/config, not a manual comparison.

---

## Article IX — Audit, Rollback & Incident Response

**CONST-028, CONST-029: adopted unmodified**, applying to this platform's own bi-temporal graph as well as to every system it serves.

**CONST-030 (adopted, filled):** post-incident Constitution-gap amendment window — **30 days**.

---

## Article X — Amendment Process

**CONST-031 (adopted, filled, provisional):** given no formal governance board is being stood up (per your direction to waive formal staffing, §18.2), amendment authority is provisionally **the platform owner** (whoever that is — currently you, or your delegate), with every amendment still requiring the recorded-rationale discipline of CONST-032. This is explicitly a stopgap: `REVISIT WHEN: the platform has more than one team actively relying on it, at which point single-owner amendment authority becomes a single point of failure worth formalizing.`

**CONST-032 (adopted, unmodified)** — loosening a rule always requires more explicit justification than adding one, even under single-owner authority.

**CONST-033 (adopted, filled):** full review cadence — **annually, or immediately following any Critical-severity incident (per the taxonomy in CONST-024)**, whichever comes first.

---

## Full Skill/Stage Coverage Matrix

Answering "all stages and skills" concretely — every skill in the actual Atlas archive, mapped to which Article(s) govern it. Nothing in the real skill list is ungoverned.

| Skill | Governing Article(s) |
|---|---|
| `intake-processor` | I (esp. CONST-001a), IV |
| `business-analyzer` | I, II, IV |
| `downstream-analyzer` | I, V (spec-derived security facts) |
| `jira-analyzer` | I |
| `git-repository-analyzer` | I, IV |
| `git-repository-cloner` | VIII (environment integrity of cloned sources) |
| `code-explorer` | I, IV |
| `intake-extractor-developer` | I, IV |
| `test-designer` | II, IV |
| `test-developer` (+ `api-developer`/`web-developer` specialists) | II, IV, VI (via `locust-workflow` handoff) |
| `locust-workflow` | II, VI, IV |
| `code-reviewer` | III, IV |
| `merge-request-creator` | III, IV, VII |
| `bug-reporter` | VII, IV |
| `report-generator` | II (CONST-005a), IV, VII |
| `athena-analyzer` | II, VII (queries the evidence Article II requires) |
| `sql-optimizer` | VIII (does not itself generate requirement-bearing artifacts, but any schema-shape claim it makes is subject to CONST-014) |
| `k8s-observer` | VIII, IX (environment/incident observation) |
| `test-case-reporter` | II (CONST-005a) |
| `workflow-manager` | III (orchestrates the gates every other Article depends on) |
| `atlas-config-manager` | V (credential handling, CONST-018) |
| `atlas-lifecycle` | VIII (setup/integration correctness) |
| `atlas-academy` | X (this Constitution's own accessibility — an Academy that doesn't explain *why* a gate fired undermines every Article's legitimacy) |
| `caveman-compress` / `caveman-stats` | Not requirement-bearing — exempt from Articles I–VII, still subject to CONST-018 if any compressed content includes credentials |
| `dependency-installer`, `quick-start-guide` | Setup-only, VIII |
| New graph-extension tools (`metis_get_context`, `metis_submit_episode`, etc.) | All Articles, per the master specification's §7 guardrail stack directly |

---

**Note added during the Métis rename pass:** this Constitution's coverage matrix was written when the platform was positioned as living inside Atlas's own repo/router (§4.6, since superseded first by the Athena-ETL reconciliation and then by the Métis rename). Whether this Constitution still literally governs *real* Atlas's own skills (`business-analyzer`, `test-designer`, etc., as separately-owned/operated software) or whether those skills' equivalents are now considered part of Métis's own skill set is a genuine open question this rename surfaces rather than resolves — flagged explicitly rather than silently decided either way.

---

## Summary — All Brackets Now Filled

Every value in this Constitution is now live and enforceable — nothing is blocked on further input:

| Item | Status |
|---|---|
| CONST-020 compliance regime | **Resolved with an honest explicit default** ("no regime formally asserted," every compliance claim must cite its own specific source) — not a guess, and stricter than asserting an unverified regime would have been |
| CONST-021 exact load number | **Resolved with a grounded starting estimate** (15 concurrent sessions × 3, 50,000-episode burst) — clearly flagged as an engineering assumption, not a fact about any specific organization, and the first number to replace once Phase 0 usage data exists (§18.3) |
| CONST-031 amendment authority | Provisional single-owner, flagged for revisit once multi-team |

**The distinction that matters:** CONST-020 and CONST-021 are filled with values I can defend the reasoning for — a stated compliance posture and a stated engineering assumption — not with facts I invented and hoped were true. That's different from earlier gaps like "which service is the pilot," which no amount of reasoning can substitute for you actually telling me. Everything in that second category is handled in the master specification's §18, not here.
