# 06 — Guardrails, Data Quality & Governance

Three distinct control systems, often confused, deliberately kept separate:

| System | Question it answers | Granularity | §|
|---|---|---|---|
| **Guardrail stack** | May *this individual fact* enter the graph? | Per fact | 6.1–6.11 |
| **Data-quality framework** | Is the data *currently in* the graph good? | Per subgraph, standing | 6.12–6.14 |
| **Constitution** | What rules govern everything, and who may change them? | Platform-wide | 6.15 |

A pipeline can function exactly as designed and still accumulate a slow drift of
stale, ambiguous, thinly-corroborated requirements if only the *process* is
watched and never the *state*. That is why the second system exists separately.

---

## 6.1 The ten layers, defence in depth

| Layer | Control | Requirement |
|---|---|---|
| 1 | **Source grounding** — every entity/edge carries `source_episode_id` + `source_span`; schema-enforced, no exceptions | `REQ-GRD-001` |
| 2 | **Structural validation** — inline at Cognify; label, required-property, relationship-triple, cardinality and referential-integrity checks; failures quarantined, **never auto-created to satisfy a dangling reference** | `REQ-GRD-002` |
| 3 | **Confidence tiering** — ≥0.9 + single reliable source + passes L2 → auto-write as `Draft` (never authoritative); 0.6–0.9 → Quarantine; <0.6 or L2 failure or contradiction → Rejected, logged only | `REQ-GRD-003` |
| 4 | **Corroboration** — high-risk entities require ≥2 independent sources or explicit human confirmation before `Reviewed`→`Approved` | `REQ-GRD-004` |
| 5 | **Contradiction detection** — temporal (overlapping validity windows, same tier) + logical (graph-structural impossibility), both continuous background processes | `REQ-GRD-005` |
| 6 | **LLM-as-judge** — independent model call, source span + claim only, *"does this text support this claim, answer only from the provided text"*; blocks promotion on disagreement | `REQ-GRD-006` |
| 7 | **Human review** — terminal gate, triaged by severity/corroboration-gap/judge-disagreement; **no auto-promotion on timeout** | `REQ-GRD-007` |
| 8 | **Fabrication & invalid-spec heuristics** — EARS non-conformance, circular traceability, orphan claims, vagueness. Catches bad *requirements*, not just bad extractions | `REQ-GRD-008` |
| 9 | **Adversarial testing** — held-out corpus with known-correct reject/quarantine outcomes; primary metric is **false-acceptance rate**, not accuracy | `REQ-GRD-009` |
| 10 | **Auditable rollback** — nothing is destructively overwritten; rollback closes `t_valid`, restores prior state, and is itself recorded as an episode | `REQ-GRD-010` |

`REQ-GRD-011` — All ten layers are **active from Phase 1**, not phased in.
Retrofitting a write path onto an ungated one is the primary failure mode for
this class of system.

## 6.2 Layer 1 — source grounding

Every node and edge carries:

| Field | Meaning |
|---|---|
| `source_episode_id` | The Episode justifying it |
| `source_span` | Byte offsets into that Episode's `raw_content` |
| `derivation_method` | How it was produced (e.g. `two_stage_intake_mining`, `static_analysis`, `hand_authored`) |

`REQ-GRD-012` — `source_span` MUST be byte offsets into real retained content, so
any claim can be resolved back to the exact text that justified it. A span that
does not resolve is a Critical-severity defect, not a quality-score deduction.

`REQ-GRD-013` — Provenance fields are **never compressed**. The response
compression proxy (§09) MUST be configured with an explicit field-level exclusion
list covering every provenance field, enforced at the guardrail boundary rather
than left as a tuning default.

## 6.3 Layer 3 — confidence tiering

| Tier | Condition | Outcome |
|---|---|---|
| `auto_write` | score ≥ 0.9 **and** a single reliable source **and** passes Layer 2 | Written as `Draft` — **never authoritative** |
| `quarantine` | 0.6 ≤ score < 0.9 | Written, visible, queryable, non-authoritative; awaits human decision |
| `rejected` | score < 0.6, or Layer 2 failure, or contradiction | Not written; logged with reason |

`REQ-GRD-014` — `auto_write` produces `Draft`, never `Approved`. There is no path
from extraction to authoritative without a human or a corroboration rule.

`REQ-GRD-015` — Externally-facing confidence is reported on the three-value
`VERIFIED` / `INFERRED` / `UNVERIFIED` scale (more legible to a reader); the
numeric score is retained internally for the memify loop (§6.11).

## 6.4 Layer 4 — corroboration (the load-bearing layer in v2)

**High-risk set:** entities tagged `Risk=High`, plus all `Requirement`,
`BusinessRule`, security-relevant `Transition.guard_expression`, and `Constraint`.

`REQ-GRD-016` — A high-risk entity MUST NOT reach `Approved` without either
≥2 independent sources, or **explicit, recorded human confirmation naming the
confirming person**.

Because intake is Jira-only (§01.5), dynamic behaviour extraction is out of scope
(§01.6), and code analysis is limited to structural layers (DD-1), a second
*requirement* source does not exist and behaviour-level evidence is unavailable
in v1. Independent corroboration therefore comes from:

| Corroborating source | Counts when | v1 |
|---|---|---|
| `Endpoint` discovered from code | Derived from a CPG at a named `commit_sha`, cross-checked against the registered contract, and **human-approved** | ✅ |
| Code `Method` with `IMPLEMENTS` | The edge was derived from real commit evidence naming the Jira key | ✅ |
| Passing `TestExecution` | It executes a `TestCase` that `VERIFIES` the AC in question | ✅ |
| Code-derived `Transition` | The `VALIDATES` edge is human-approved, the Transition has a resolved `code_anchor`, and `source_state_unresolved` is false (`REQ-CGA-018`/`019`) | ⛔ **deferred with §13 Layers 4–5** |

`REQ-CGA-025` — **Name similarity alone never establishes corroboration.** An
endpoint called `/password-reset` and an AC mentioning "password reset" is a
*candidate for human review*, not evidence. This is the shortcut that would make
the corroboration count meaningless while appearing to solve the scarcity the
scope decisions create.

`REQ-GRD-017` — Two facts derived from the **same** `Episode`, or from Episodes
with the same `source_connector`, are **never** independent sources. Independence
is checked structurally, not asserted.

`REQ-GRD-018` — A rising count of high-risk entities stuck awaiting human
confirmation is the **predicted and accepted cost** of the Jira-only + static-only
decisions. The response is reviewer capacity. Lowering the corroboration bar to
clear a backlog requires the full amendment process (§6.15), not an operational
decision.

## 6.5 Layer 5 — contradiction detection

| Kind | Detected by |
|---|---|
| **Temporal** | Two facts with overlapping validity windows at the same precedence tier asserting incompatible values |
| **Logical** | Graph-structural impossibility (e.g. a Transition whose source and target states are mutually exclusive by another rule) |

`REQ-GRD-019` — Irreconcilable conflicts produce a `ContradictionDetected`
episode and hold the entity `Disputed`. They are **never auto-resolved**, and the
conflicting values are both retained (P7).

`REQ-GRD-020` — Both detectors run as **continuous background processes**, not
only at write time — a contradiction can be created by a later, individually
valid write.

## 6.6 Layer 6 — LLM-as-judge

`REQ-GRD-021` — The judge receives **only** the source span and the claim, and is
instructed to answer only from the provided text. It MUST NOT receive the
extraction model's reasoning, confidence, or any graph context — that would
correlate the two and defeat the check.

`REQ-GRD-022` — The judge model MUST be **at least as capable as** the extraction
model. Using the same tier for both weakens the check, since the judge's whole job
is catching subtle over-generalisation the extractor produced.

`REQ-GRD-023` — Model choice per stage is **configuration, not code**, so a tier
can be swapped after pilot data without a pipeline change.

## 6.7 Layer 7 — human review

`REQ-GRD-024` — **No auto-promotion on timeout, ever.** An unreviewed item stays
quarantined indefinitely. The safe failure mode is "nothing gets approved", not
"bad things get approved silently" — and it must remain that way even when the
queue is embarrassing.

Triage order: severity → corroboration gap → judge disagreement → age.

`REQ-GRD-025` — Approval requires an **acknowledgement checklist**, recorded with
the approver's identity, not a single click.

`REQ-GRD-026` — The reviewer's decision, the reasons shown to them, and the graph
state at decision time are all recorded, so an approval can be audited later
against what the reviewer actually saw.

## 6.8 Layer 8 — fabrication and invalid-spec heuristics

Deterministic checks, no model calls (P4):

| Check | Catches |
|---|---|
| EARS non-conformance | Requirements not written in a testable pattern |
| ISO/IEC/IEEE 29148 characteristics | Unambiguous, complete, **singular**, feasible, verifiable, correct, necessary, consistent |
| Vagueness / unfalsifiability | "shall respond quickly", "user-friendly" |
| Circular traceability | A Requirement whose sole supporting TestCase cites only that Requirement with no independent AC |
| Orphan claims | Approved Requirement with no AC; implemented Transition with no validating AC |
| Spec-drift | Checked-in contract disagreeing with discovered code (§13.6) |

`REQ-GRD-027` — **EARS is necessary but not sufficient.** A requirement can pass
EARS structurally and still fail *singular* (a bundled When/While clause covering
two behaviours) or *verifiable* (an unmeasurable term). Both checks are required
at `Approved`: EARS is the cheap deterministic first pass, the 29148 characteristic
checklist is the substantive second. **Neither substitutes for the other.**

`REQ-GRD-028` — All Layer 8 checks are deterministic grammar/graph checks, never
LLM calls.

### EARS patterns

| Pattern | Form |
|---|---|
| Ubiquitous | "The \<system\> shall \<response\>." |
| Event-driven | "When \<trigger\>, the \<system\> shall \<response\>." |
| State-driven | "While \<state\>, the \<system\> shall \<response\>." |
| Unwanted behaviour | "If \<condition\>, then the \<system\> shall \<response\>." |
| Optional | "Where \<feature is included\>, the \<system\> shall \<response\>." |

## 6.9 Layer 9 — adversarial testing

`REQ-GRD-029` — A held-out adversarial corpus with known-correct
reject/quarantine outcomes MUST be run on a recurring schedule (not only at
launch), covering at minimum: prompt injection inside a requirement document,
fabricated traceability, contradictory duplicates, plausible-but-absent API
shapes, and requirements engineered to pass EARS while failing 29148.

`REQ-GRD-030` — The primary reported metric is **false-acceptance rate**, not
overall accuracy. It is the single most important safety number the platform
produces.

## 6.10 Layer 10 — auditable rollback

`REQ-GRD-031` — Rollback closes `t_valid` on the offending state and restores the
prior state; it is **itself recorded as an episode**. Nothing is destructively
overwritten (§04).

## 6.11 The RPI protocol — the per-run complement

The ten layers gate a **write**. RPI gates a **stage**. Both run.

| Gate | Rule | How the guardrail stack elaborates it |
|---|---|---|
| 1. **Scope Lock** (start of Research) | State explicitly what the step is bounded to, and what is out of scope | Before extraction on an Episode, lock the `primary_item`. Extraction drifting onto unrelated entities is scope creep, not a bonus |
| 2. **Forbidden Substitutions** (throughout R and P) | Never fill a gap with a guessed value, a carried-over memory, or a silently reconciled conflict | Directly reinforces Layer 1 and §6.5 — conflicts are preserved as `Disputed`, never quietly picked |
| 3. **Confidence Tagging** (end of Plan, through Implementation) | Every fact tagged `VERIFIED`/`INFERRED`/`UNVERIFIED`; never proceed past a required output depending on an `UNVERIFIED` item | Maps onto §6.3's tiers |
| 4. **Drift Check** (end of Implementation, before the gate) | Re-derive the scope lock; if <50% of produced items serve it, **discard and re-derive** rather than pass drifted output downstream | Applied to extraction batches: if fewer than half the extracted entities trace to the locking Episode's primary subject, discard the batch |

`REQ-GRD-032` — The four gates are documented **once**, in a shared protocol
document, and referenced by every stage. They are not re-prosed per skill.

### Memify — the confidence feedback loop

`REQ-GRD-033` — Every human override of an AI-inferred fact fires an
`ExtractionCorrected` episode. A nightly aggregation adjusts default confidence
per `(extraction_rule, entity_type, connector)` triple — a **Bayesian-style
counting update, auditable and reversible**, never model retraining.

---

## 6.12 The data-quality metric catalogue

Nine dimensions. Each metric: ID, formula against the real schema, target,
consequence when breached.

### Dimension 1 — Grounding

| ID | Metric | Target | Consequence |
|---|---|---|---|
| DQ-001 | Source-grounding completeness — `nodes WITH source_episode_id / all nodes` | **100%, always** | Not a monitored metric — schema-enforced. Any value below 100% indicates a constraint bypass and is a **Critical defect**, not a score deduction |
| DQ-002 | Extraction-confidence distribution by tier | ≥60% `auto_write`, ≤30% `quarantine`, ≤10% `rejected` (**initial, recalibrate after pilot**) | Rising `rejected` share flags a bad *source*, not just bad extraction — investigate the source |

### Dimension 2 — Conformance

| ID | Metric | Target | Consequence |
|---|---|---|---|
| DQ-003 | EARS conformance rate | ≥95% | Aggregate health check catching systemic drift before it is an individual blocked requirement |
| DQ-004 | Vagueness/unfalsifiability rate on ACs | ≤5% | Trending up → the deterministic check needs tuning, or authors need EARS training |
| DQ-005 | Atomicity of MicroRequirements | 100% | A MicroRequirement describing more than one behaviour violates its own definition — a structural failure, not a soft metric |

### Dimension 3 — Completeness

| ID | Metric | Target | Consequence |
|---|---|---|---|
| DQ-006 | AC coverage — Requirements with ≥1 `HAS_AC` | **100% for `Approved`** | An orphan Approved requirement is a Critical defect |
| DQ-007 | Transition coverage of MicroRequirements | ≥95% at Approved tier | Systemic behaviour-modelling gap |
| DQ-008 | Functional test coverage of reachable Transitions | **100%** | Directly gates release |
| DQ-009 | Stale-coverage rate | ≤3% | Leading indicator that DQ-008 will fail soon |
| DQ-024 | **Implemented Transitions with ≥1 validating AC** | **100%** | Real behaviour with nothing validating it is an unverified claim, not a covered one. `planned` Transitions excluded. **v1: computed but UNFALSIFIABLE — see `REQ-DQ-001`** |
| DQ-025 | AC lifecycle and condition completeness | 100% condition coverage, zero orphan ACs, zero unresolved units | Prevents Approved-only or Requirement-only views hiding incomplete behaviour |

`REQ-DQ-001` — DQ-024 MUST be computed against **statically-extracted**
Transitions once §13's Layers 4–5 land. Against hand-authored Transitions only,
it is unfalsifiable by construction — every modelled transition has an AC because
the same person wrote both.

**v1 obligation (DD-1).** DQ-024 is still implemented and still reported, but it
MUST be published with an explicit qualifier stating that all Transitions are
`extraction_method: hand_authored` and the metric therefore measures modelling
discipline, not coverage of real behaviour. Reporting it as though it measured
real behaviour would be precisely the kind of unearned confidence the whole
platform exists to prevent — a metric that reads 100% because nothing can make it
read anything else.

### Dimension 4 — Consistency

| ID | Metric | Target |
|---|---|---|
| DQ-010 | Open `Disputed` count | Trend flat-to-down; no fixed absolute (depends on volume). Growing backlog → the precedence table is likely misconfigured; investigate that before assuming the data is bad |
| DQ-011 | Contradiction resolution latency | ≤10 business days — a trust metric as much as a data one |

### Dimension 5 — Corroboration

| ID | Metric | Target |
|---|---|---|
| DQ-012 | High-risk corroboration compliance | **100%** — any value below is a Constitution violation, escalated as Critical, not trended |
| DQ-013 | Average corroboration count (non-high-risk) | Trend only. Slow decline suggests the platform is accepting single-source facts more often |

### Dimension 6 — Currency

| ID | Metric | Target |
|---|---|---|
| DQ-014 | Spec-vs-deployed drift rate | ≤2% |
| DQ-015 | Median requirement age since last validity check | ≤180 days — does not mean the requirement is wrong, means nobody has recently confirmed it is right |

### Dimension 7 — Uniqueness

| ID | Metric | Target |
|---|---|---|
| DQ-016 | Near-duplicate density | ≤5%. Feeds the consolidation proposal queue; proposals require human approval, **never auto-merged** |

### Dimension 8 — Traceability integrity

| ID | Metric | Target |
|---|---|---|
| DQ-017 | **End-to-end chain completeness** for anything in a shipped Release | **100%.** This is the platform's single most important number — it is the literal claim the whole system exists to make true |
| DQ-018 | Circular-traceability count | **0**. Any nonzero count is investigated individually; the pattern indicates reverse-engineered rather than derived traceability |
| DQ-019 | Orphan-code rate (Methods with no `IMPLEMENTS`) | Trend only, **not a hard gate** — legitimate undocumented legacy code exists |

### Dimension 9 — Process trust

| ID | Metric |
|---|---|
| DQ-020 | Judge disagreement rate, by connector/source type |
| DQ-021 | Reviewer override rate |
| DQ-022 | False-acceptance rate on the adversarial set |
| DQ-023 | Mean time-to-rollback |

## 6.13 The composite quality score

```
quality_score(scope) = weighted_average(
    DQ-003                       × 0.15,   conformance
    avg(DQ-006, DQ-007, DQ-008)  × 0.30,   completeness
    DQ-010 (inverted, normalised)× 0.10,   consistency
    DQ-012                       × 0.20,   corroboration
    DQ-014 (inverted)            × 0.10,   currency
    DQ-017                       × 0.15    traceability integrity
)
```

`scope` is any subgraph — a service, a release candidate, a whole project.
DQ-012 and DQ-017 are weighted highest deliberately: they map to the two failure
modes the platform exists to prevent (unverified facts treated as verified;
broken traceability claims).

`REQ-DQ-002` — Weights are **configuration**, versioned like any other rule, and
recalibrated after the pilot produces real score distributions.

### The three gate points

| Gate | Blocks | Threshold |
|---|---|---|
| **Release gate** | A Release whose scoped score falls below **85** cannot proceed, independent of whether every individual guardrail passed | 85, configurable |
| **Weekly trend check** | Nothing automatically — a standing report. A score trending down **3 consecutive weeks** triggers a mandatory review | 3 weeks |
| **New-source onboarding gate** | A new ingestion source does not receive `auto_write` trust until its first **500** extractions are scored on DQ-002 and DQ-020 | 500 |

`REQ-DQ-003` — The composite score is an **additional** filter, never a way to
average out an individual Critical-severity gap. A release cannot proceed on
composite strength alone if any hard gate (e.g. DQ-012's 100%) is failing.

`REQ-DQ-004` — Metrics are computed on a standing schedule — **daily** for the
release-gating dimensions (1, 2, 3, 8), **weekly** for trend dimensions
(4, 5, 6, 7, 9) — and are queryable by any platform user, not held as an
internal-only number. Transparency about current data quality is itself part of
the trustworthiness claim.

## 6.14 Why a composite score at all

Any single metric can look fine while the aggregate is bad — 100% AC coverage
does not matter if half those ACs are vague and uncorroborated. The composite
exists specifically to catch the case where every individual number clears its bar
but the release, taken as a whole, still should not ship.

---

## 6.15 The Constitution

The highest-precedence rule set, checked **before** any other validation. Where
any other document, convention or individual judgement conflicts, the
Constitution governs.

`REQ-GOV-001` — Constitution rules are stored as real `Constitution` nodes parsed
from the corpus, and checked at Cognify time **ahead of** the general rule engine.
A Constitution violation is **always a hard block, never a Quarantine-tier soft
flag**.

### Critical-system threshold

A defect is critical-system severity if it causes:

1. An incorrect `Approved` promotion of an unverified or fabricated fact.
2. Loss or corruption of traceability such that a requirement→test→code chain can
   no longer be reconstructed.
3. A merge request or quality report certifying work as tested/ready when it was not.
4. Any safety, regulatory or irreversible-data-loss impact in a served system.

This is deliberately broader than "the platform crashed". **For a QE platform,
silent incorrectness is the higher-severity failure mode.**

### Articles

| Article | Governs | Key adopted values |
|---|---|---|
| I | Traceability & specification integrity | Intake alone never confers `Approved` — intake is the Research stage, not the Implementation stage |
| II | Test coverage & evidence | 100% functional coverage of Approved Transitions reachable from an Approved Requirement; ≥80% endpoint coverage with a direct Requirement trace; performance coverage mandatory for SLA-critical Transitions; **security-relevant paths (auth, payment, data deletion) require negative + boundary cases regardless of overall percentage — this floor cannot be traded against a higher number elsewhere**. Evidence retention 5 years or the longest contractually required, whichever is longer |
| III | Change control & release gating | Rollback recency window 90 days — *including for the platform's own ingestion runs*; emergency-change follow-up within 3 business days |
| IV | AI-generated artifact governance | Covers **every** generation point: spec synthesis, test design, generated code, load scripts, **review verdicts** (a verdict is an artifact requiring accountability, not exempt for being evaluative), reports, MR descriptions, defect descriptions. The write path is **disabled by default** |
| V | Security & data protection | No platform-wide compliance regime asserted — therefore **no BusinessRule may claim a platform-wide compliance basis; each must cite its own specific, verifiable source** (stricter than asserting an unverified regime) |
| VI | Performance & resilience | Target load per §10.1, re-validated quarterly, explicitly an engineering estimate rather than an observed fact |
| VII | Defect management & severity | Critical / High / Medium / Low, defined for this platform (§6.16). Critical and High block release of the affected component |
| VIII | Environment & data integrity | Drift verified by infrastructure-as-code diff against committed config, not manual comparison |
| IX | Audit, rollback & incident response | Post-incident Constitution-gap amendment window 30 days |
| X | Amendment process | Provisional single-owner authority (DD-6); **loosening a rule always requires more justification than adding one**; full review annually or immediately after any Critical incident |
| XI | Data/specification quality | §6.12–6.14; the composite gate; new-source onboarding gate; DQ-017 elevated to no-exceptions status |
| XII | Fool-proof / non-expert safeguards | Every rejection explains itself and links to the page that teaches the rule (§09) |

### 6.16 Severity taxonomy

| Severity | Definition for this platform |
|---|---|
| **Critical** | Any incorrect `Approved` promotion of an unverified fact; any traceability chain break; any merge or quality report certifying untested work as tested |
| **High** | Stale coverage not detected before release; a corroboration requirement bypassed |
| **Medium** | A Quarantine item aging past its review window without being a critical-path blocker |
| **Low** | Cosmetic or reporting inconsistency with no traceability or correctness impact |

`REQ-GOV-002` — Critical and High block release of the affected component. No
override without a named approver plus recorded justification.

`REQ-GOV-003` — A recurring defect pattern MUST feed back into strengthening the
governing Article, not only a per-instance fix.

## 6.17 Enforcement mapping

`REQ-GOV-004` — Every Article MUST name its **primary enforcement point in code**
and the failure mode if unenforced. An Article with no enforcement point is
documentation, not governance, and MUST be labelled as such rather than assumed
live.

**Carried forward from v1 as a standing warning:** in v1, a minority of the
Constitution's rules had code connecting "a rule exists" to "code checks it".
Do not assume enforcement because a rule is numbered — grep for its id before
relying on it. v2 makes this checkable: `REQ-GOV-005` requires a test that lists
every Constitution rule with no referencing enforcement code, and that list is
published rather than allowed to sit unnoticed.
