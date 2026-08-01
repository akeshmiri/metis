# Quality Engineering Constitution — Critical Systems
### Template v1.0 — for adoption as the initial `Constitution` entity (§4.2/§7.2)

---

## Preamble

This Constitution is the highest-precedence rule set governing quality engineering on this system. It is checked before any other validation rule (§7.2's `REQ-METIS-GRD-11`: Constitution violations are always a hard block, never a Quarantine-tier soft flag). Where any other document, convention, or individual judgment conflicts with an Article below, this Constitution governs.

**This is a template, not a finished document.** It's written to be adopted, amended, and made specific to your actual system in the bracketed sections and the thresholds marked `[SET BY ORG]`. Adopting it unedited is a worse outcome than adopting a shorter, honestly-scoped version your team will actually enforce — Article X exists so it can evolve without losing its authority.

**Definition of "critical system" for this document:** a system where a defect in production can cause financial loss above `[SET BY ORG threshold]`, safety harm, regulatory violation, or irreversible data loss. If your system doesn't meet this bar, most Articles still apply but the mandatory-gate language in Article III can reasonably be relaxed to advisory — that's an explicit amendment to make, not a default to assume.

---

## Article I — Traceability & Specification Integrity

**CONST-001.** No code may be merged to a protected branch without tracing to a `Requirement` with at least one `AcceptanceCriterion` in `Approved` state. Untraceable code is treated as an undocumented change, not a minor process gap.

**CONST-002.** Every `Requirement` and `AcceptanceCriterion` MUST be EARS-conformant (§4.3) before leaving `Draft`. A requirement that cannot be phrased as a testable Ubiquitous, Event-driven, State-driven, Unwanted-behavior, or Optional statement is not yet a requirement — it's a topic that needs more definition first.

**CONST-003.** No requirement, business rule, or acceptance criterion may be marked `Approved` on the strength of a single source when it is tagged `Risk: High` (§7 Layer 4). Two independent sources, or one source plus explicit named human sign-off, are the minimum bar.

**CONST-004.** Conflicting facts about the same requirement from different sources are never silently reconciled. They are preserved as `Disputed` (§5.3) until a human with the authority to decide does so, and that decision is itself recorded with its rationale.

**Rationale:** a critical system's biggest single point of failure is usually not a bug — it's building the right thing wrong because nobody could point to what "right" meant. Traceability is the control that makes every other Article checkable.

---

## Article II — Test Coverage & Evidence

**CONST-005.** Every `Transition` reachable from an `Approved` requirement MUST have at least one `Approved`-status functional `TestCase` before the transition's implementing code may ship to production. `[SET BY ORG: minimum coverage percentage for integration/API/security/performance test types per risk tier]`.

**CONST-006.** A `TestCase` whose `t_valid` predates the most recent `t_valid` of the `Transition` it claims to verify is stale coverage (§7.2), and stale coverage does not satisfy CONST-005 — it is treated identically to no coverage until re-confirmed against current behavior.

**CONST-007.** Test evidence is retained for `[SET BY ORG: retention period — recommend no less than the longest regulatory or contractual retention requirement applicable to this system]` and is never summarized-then-discarded. A test report claiming "all tests passed" without the underlying run data is not evidence.

**CONST-008.** For any change touching an authentication, authorization, payment, or data-deletion path, negative and boundary test cases are mandatory, not optional — a happy-path-only test suite does not satisfy CONST-005 for these paths regardless of overall coverage percentage.

**Rationale:** coverage percentage alone doesn't answer "was the thing that actually matters tested" — CONST-008 exists because the highest-consequence paths are disproportionately the ones happy-path testing misses.

---

## Article III — Change Control & Release Gating

**CONST-009.** No deployment to production includes a `PullRequest` that closes a `Requirement` without `Approved`-status test coverage tracing to it (mirrors `REQ-METIS-GRD` release-gating logic, §10 rollout).

**CONST-010.** Every production release has a named, tested rollback path, verified before the release — not designed after an incident makes it urgent. "We can restore from backup" is not a verified rollback path unless the restore has actually been exercised within `[SET BY ORG: recency window, recommend ≤ 90 days]`.

**CONST-011.** Emergency changes (hotfixes bypassing normal gating) require: (a) a named approver with the authority to accept the risk, (b) a recorded justification for why normal gating was bypassed, and (c) a follow-up ticket to retroactively satisfy Articles I and II within `[SET BY ORG: recommend ≤ 5 business days]`. An emergency change that never gets its retroactive traceability is a Constitution violation, not a closed exception.

**CONST-012.** Feature flags and configuration toggles that change system behavior are subject to the same traceability requirement as code (CONST-001) — a flag flip is a production change.

**Rationale:** the emergency-change exception exists because critical systems genuinely need one; CONST-011's teeth are in the follow-up requirement, since an "emergency exception" with no expiry is how permanent traceability gaps get created.

---

## Article IV — AI-Generated Artifact Governance

**CONST-013.** No AI-generated code, test, or specification content may be merged, approved, or promoted past `Draft` lifecycle state without a named human reviewer's explicit approval recorded against that specific artifact. A human approving a batch or a PR is not sufficient if the batch mixes human- and AI-authored content — the AI-authored portions need their own recorded review.

**CONST-014.** AI-generated content is never permitted to invent a requirement, ticket ID, API contract, or database schema element that does not exist in a verified source. Where the AI cannot find the information it needs, it states that explicitly rather than producing a plausible-sounding substitute (this is RPI's Forbidden Substitutions rule, §9.2, elevated to Constitution status because it is the single most consequential rule in this document for a system using AI-assisted development).

**CONST-015.** Every AI-generated artifact retains its `AIDecision`/`GeneratedCode`/`GeneratedTest` provenance permanently, even after human edit and approval — "a human touched it eventually" does not erase the record of what was AI-proposed versus human-authored.

**CONST-016.** Autonomous write paths (e.g., `metis_submit_episode`) remain disabled for this system unless and until this Article's controls have a demonstrated track record on this project specifically — a track record on a different project does not transfer.

**Rationale:** this Article exists because the whole reason this extension's guardrail stack (§7) is worth building is that AI-assisted development changes the failure mode from "a person made a mistake" to "a plausible-sounding artifact with no one accountable for it entered the system" — Article IV is where that risk is named explicitly rather than left implicit in the tooling.

---

## Article V — Security & Data Protection

**CONST-017.** Any `Column` or field carrying PII, credentials, or regulated data is tagged as such in the graph (§13) before the table/schema change ships, not retroactively.

**CONST-018.** No secret, credential, or API key is ever stored in an `Episode` payload, a test fixture, a log, or a generated-code artifact in plaintext. Where a connector needs a credential, it is referenced, never embedded.

**CONST-019.** Security-relevant `Transition.guard` conditions (authorization checks, rate limits, input validation boundaries) are subject to Article I's ≥2-source corroboration requirement (CONST-003) without exception — a security control described in only one place is a security control that can silently drift out of sync with the code that enforces it.

**CONST-020.** `[SET BY ORG: applicable compliance regime — e.g. SOC 2, PCI-DSS, HIPAA, GDPR]` requirements are modeled as `BusinessRule` entities with explicit `Compliance` taxonomy tags (§4.4), not left as tribal knowledge — if a rule exists because of a compliance obligation, that obligation is named in the graph, not just implied.

**Rationale:** security requirements are exactly the kind of fact that's dangerous to get "mostly right" — Article V exists to make the security-relevant subset of the ontology harder to under-specify than everything else.

---

## Article VI — Performance & Resilience

**CONST-021.** Every `Transition` tagged `Performance: SLA-critical` (§4.4 taxonomy) has an associated performance/load `TestCase` exercising it at `[SET BY ORG: target load, e.g. 2x expected peak]` before production release, re-verified whenever the transition's implementation changes materially.

**CONST-022.** Dependency failures (a called external system or `ExternalAPISpec`-tracked API being unavailable or slow) are tested explicitly for every `Transition` with an `APIs Called` edge to an `ExternalSystem` — "we assume it will be up" is not an acceptable basis for a critical-path transition.

**Rationale:** performance and resilience defects are disproportionately the ones that only surface under real production load, by which point the cost of fixing them (and of the incident itself) is much higher than catching them pre-release.

---

## Article VII — Defect Management & Severity

**CONST-023.** Every `Defect` traces to the `Requirement`/`Transition` it violates (v1's traceability model, §7.1) — a defect with no traceable root is itself flagged for follow-up, not closed as "fixed" without one.

**CONST-024.** `[SET BY ORG: severity taxonomy, e.g. Critical/High/Medium/Low]` — Critical and High severity defects block release of the affected component regardless of unrelated feature readiness. No override without the same named-approver-plus-recorded-justification pattern as CONST-011.

**CONST-025.** A defect's root cause, once identified, is checked against Article I–VI for whether the underlying gap (missing test, missing corroboration, missing traceability) that let it through is itself now closed — a recurring defect class is evidence a Constitution control needs strengthening, not just that this instance needs fixing.

**Rationale:** CONST-025 is what turns the guardrail stack from a static checklist into something that actually improves over time, mirroring the memify feedback loop (§8.4) at the process level, not just the extraction-confidence level.

---

## Article VIII — Environment & Data Integrity

**CONST-026.** Test environments used for evidence satisfying Article II do not contain real customer/PII data unless that data has been through an approved anonymization/synthesis process — evidence generated against real, unprotected customer data is not acceptable evidence and does not satisfy CONST-005–007.

**CONST-027.** Environment configuration drift (test environment meaningfully diverging from production) is checked before test evidence from that environment is accepted as satisfying Article II — `[SET BY ORG: how drift is verified, e.g. periodic config diff, infrastructure-as-code parity]`.

**Rationale:** evidence from an environment that doesn't resemble production, or that puts real customer data at risk to obtain, satisfies the letter of Article II while defeating its purpose.

---

## Article IX — Audit, Rollback & Incident Response

**CONST-028.** Nothing in this system's history is destructively overwritten. Corrections are new, superseding facts with the prior state preserved (§5.1's bi-temporal model, §7 Layer 10's rollback requirement) — this applies to graph data and to the underlying source systems this extension ingests from, to the extent those systems support it.

**CONST-029.** Every `Incident` traces back through Article VII to the `Defect`/`Requirement` it stems from where a root cause is known, closing the loop from production back to specification (v1 §14's "specification evolution" vision, applied here as a mandatory practice, not an aspirational one).

**CONST-030.** Post-incident review findings that identify a Constitution gap (a rule that should have existed and didn't) are proposed as amendments under Article X within `[SET BY ORG: recommend ≤ 30 days]` of the incident review — a lesson learned that never becomes a rule is a lesson the system will need to learn again.

**Rationale:** this Article is where the Constitution closes its own loop — it's the mechanism by which real incidents make the rules better instead of just generating a postmortem document nobody revisits.

---

## Article X — Amendment Process

**CONST-031.** This Constitution may be amended by `[SET BY ORG: who has authority — e.g. named architecture/security/QE leads, a defined governance board]`. Amendments are themselves versioned `Constitution` entities (§4.2) with a recorded rationale and effective date — never a silent edit to existing rule text.

**CONST-032.** An amendment that weakens an existing rule (raises a threshold, removes a mandatory gate) requires explicit justification recorded alongside it, distinct from an amendment that adds a new rule or tightens an existing one — loosening a control should never be as frictionless as adding one.

**CONST-033.** This Constitution is reviewed in full at least `[SET BY ORG: recommend annually, or after any Critical-severity incident per CONST-030]` — not left to accumulate amendments indefinitely without a holistic pass to check they still cohere as a whole.

---

## Appendix: Enforcement Mapping

| Article | Primary enforcement point | Failure mode if unenforced |
|---|---|---|
| I — Traceability | Cognify-stage structural validation (§7 Layer 2) + release gate (§11.4) | Untraceable production code, unauditable "why does this exist" |
| II — Coverage | `metis_check_coverage` tool + CI gate (§11.4) | False confidence from stale or happy-path-only coverage |
| III — Change Control | Release gate (§11.4), rollback verification | Unreviewed emergency changes become permanent, undocumented |
| IV — AI Governance | Review queue (§7 Layer 7), `metis_submit_episode` disabled by default (§11.1) | Fabricated requirements/APIs entering the graph as if verified |
| V — Security | PII-flag propagation, corroboration (§7 Layer 4) | Security controls drifting out of sync with actual enforcement |
| VI — Performance | Taxonomy-driven test generation (§4.4, §6) | SLA violations discovered in production instead of pre-release |
| VII — Defects | Traceability chain (§7.1), root-cause-to-Article mapping | Recurring defect classes with no systemic fix |
| VIII — Environment | Environment-parity check (org-defined process) | Evidence that doesn't generalize to production, or PII exposure |
| IX — Audit/Rollback | Bi-temporal model (§5.1), Layer 10 rollback (§7) | Unrecoverable errors, lost incident-to-root-cause trail |
| X — Amendment | `Constitution` entity versioning (§4.2) | Rules drifting from what's actually enforced, or silent weakening |

---

*Adoption note: fill every `[SET BY ORG]` bracket before this is loaded as the live `Constitution` entity — a bracket left unfilled is itself a gap CONST-002's own logic would flag if it were a requirement. Recommend a first pass that fills only the brackets your team can commit to enforcing this quarter, with the rest marked `[TBD — Article X review]` rather than guessed at.*
