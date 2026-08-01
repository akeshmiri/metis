# Data, Requirement & Specification Quality Framework
## Metrics Catalog + Quality Safeguard Gate — tied to the Constitution as Amendment 1

---

## 0. Why this is separate from §7's existing guardrail metrics

§7.1 of the master specification already has a metrics table, but it measures **the pipeline's behavior** (rejection rate, judge disagreement, reviewer overrides) — it tells you whether the guardrail machinery is working. It does not directly tell you **whether the data currently sitting in the graph is good**. Those are different questions: a pipeline can be functioning exactly as designed and still be accumulating a slow drift of stale, ambiguous, or thinly-corroborated requirements if no one is watching the *state* of the data, only the *process* that produced it.

This framework adds that missing layer: a catalog of metrics computed directly against current graph state, organized by data-quality dimension (not pipeline stage), each with a concrete formula against the schema already built (`atlas-graph-01/02-*.cypher`, `atlas-graph-03-postgres-schema.sql`), a target threshold, and a named consequence when the threshold is breached. It closes with a Constitution amendment making the hard thresholds enforceable, not advisory.

---

## 1. The Nine Quality Dimensions

Adapted from established data-quality practice (DAMA-DMBOK's core dimensions, ISO 8000/25012) and requirement-engineering practice (IEEE 830, INCOSE's requirement characteristics), mapped onto this platform's actual ontology rather than treated abstractly.

| # | Dimension | Question it answers |
|---|---|---|
| 1 | **Grounding** | Is every fact traceable to a real source? |
| 2 | **Conformance** | Is every requirement written in a testable, unambiguous form? |
| 3 | **Completeness** | Does every requirement have what it needs downstream (AC, tests, traceability)? |
| 4 | **Consistency** | Do sources agree, and are disagreements tracked rather than hidden? |
| 5 | **Corroboration** | Is high-risk content backed by more than one source? |
| 6 | **Currency** | Is the data still true, or has reality moved past it? |
| 7 | **Uniqueness** | Is the same requirement represented once, or fragmented across near-duplicates? |
| 8 | **Traceability Integrity** | Does the requirement→...→production chain actually hold together? |
| 9 | **Process Trust** | Is the pipeline that produced this data itself behaving well? (this is §7.1, folded in as the ninth dimension for a complete picture) |

---

## 2. Metric Catalog

Each metric: **ID**, **formula** (against the actual schema), **target**, **band**, **consequence**.

### Dimension 1 — Grounding

| ID | Metric | Formula | Target | Consequence if breached |
|---|---|---|---|---|
| **DQ-001** | Source-grounding completeness | `count(nodes WHERE source_episode_id IS NOT NULL) / count(all nodes)` | **100%, always** | Not a monitored metric — schema-enforced (`REQ-METIS-ONT-03`). Any measured value below 100% indicates a schema-constraint bypass and is a Critical-severity defect (Article VII), not a quality-score deduction. |
| **DQ-002** | Extraction-confidence distribution | `count by confidence_tier (auto_write / quarantine / rejected) / total extractions` (`confidence_tier` property on `Episode` nodes — single-database Neo4j design, `metis-graph-03-single-db-consolidation.cypher`; no separate Postgres extractions table exists) | ≥ 60% `auto_write`, ≤ 30% `quarantine`, ≤ 10% `rejected` — **initial targets, recalibrate after Phase 0** | Rising `rejected` share flags a source or connector producing bad input, not just bad extraction — investigate the source, not just the model |

### Dimension 2 — Conformance

| ID | Metric | Formula | Target | Consequence if breached |
|---|---|---|---|---|
| **DQ-003** | EARS conformance rate | `count(Requirement WHERE ears_pattern IS NOT NULL) / count(Requirement)` | **≥ 95%** | Below target blocks that requirement leaving `Draft` (already a hard gate, CONST-002) — this metric is the *aggregate* health check that catches systemic drift before it's an individual blocked requirement |
| **DQ-004** | Vagueness/unfalsifiability rate | `count(AcceptanceCriterion flagged by §7 Layer 8 heuristic) / count(AcceptanceCriterion)` | **≤ 5%** | Trending upward → the deterministic vagueness check (§7 Layer 8) itself needs tuning, or authors need EARS training (route to `atlas-academy`) |
| **DQ-005** | Atomicity | `count(MicroRequirement WHERE precondition/postcondition both present and single-behavior) / count(MicroRequirement)` | **100%** | A `MicroRequirement` describing more than one behavior violates its own definition (v1 §3.2) — structural validation failure (§7 Layer 2), not a soft metric |

### Dimension 3 — Completeness

| ID | Metric | Formula | Target | Consequence if breached |
|---|---|---|---|---|
| **DQ-006** | AC coverage | `count(Requirement WITH ≥1 HAS_AC edge) / count(Requirement)` | **100%** for `Approved`, tracked separately for `Draft` | Orphan `Approved` requirement is a Critical defect (violates CONST-001) |
| **DQ-007** | Transition coverage | `count(MicroRequirement WITH ≥1 PRODUCES edge) / count(MicroRequirement)` | **≥ 95%** for `Approved` tier | Below target → systemic gap in behavior modeling, not just individual missing transitions |
| **DQ-008** | Test coverage (functional) | `count(Transition WITH ≥1 VERIFIES edge, non-stale) / count(Transition reachable from Approved Requirement)` | **100%** — this is CONST-005 restated as a measured metric | Directly gates release (§11.4 CI check) |
| **DQ-009** | Stale-coverage rate | `count(TestCase WHERE t_valid < linked Transition's most recent t_valid) / count(TestCase)` | **≤ 3%** | Feeds directly into DQ-008 — a rising stale rate is a leading indicator DQ-008 will fail soon even if it hasn't yet |

### Dimension 4 — Consistency

| ID | Metric | Formula | Target | Consequence if breached |
|---|---|---|---|---|
| **DQ-010** | Open contradiction count | `count(nodes WHERE lifecycle_state = 'Disputed')` | **Trend flat-to-down**, no fixed target (absolute count depends on ingestion volume) | Growing backlog → §5.3 precedence table likely misconfigured for a real source; investigate the precedence table before assuming the data itself is bad |
| **DQ-011** | Contradiction resolution latency | `avg(time from ContradictionDetected episode to Disputed→resolved)` | **≤ 10 business days** | Long-open disputes erode trust in the whole graph faster than their raw count suggests — this is a UX/trust metric as much as a data one |

### Dimension 5 — Corroboration

| ID | Metric | Formula | Target | Consequence if breached |
|---|---|---|---|---|
| **DQ-012** | High-risk corroboration compliance | `count(Requirement/BusinessRule WHERE Risk=High AND corroboration_count ≥ 2, or human-confirmed) / count(Requirement/BusinessRule WHERE Risk=High AND lifecycle_state='Approved')` | **100%** | This is CONST-003/CONST-019 — any value below 100% is a Constitution violation, escalate as Critical (Article VII), not a metric to trend |
| **DQ-013** | Average corroboration count (non-high-risk) | `avg(corroboration_count)` across `Approved` `Requirement`/`AcceptanceCriterion` | Track as a trend, no hard target | A slow decline suggests the platform is accepting single-source facts more often — worth a periodic sanity check even where the hard rule (DQ-012) only bites at High risk |

### Dimension 6 — Currency

| ID | Metric | Formula | Target | Consequence if breached |
|---|---|---|---|---|
| **DQ-014** | Spec-vs-deployed drift rate | `count(SpecDriftDetected episodes open) / count(Endpoint or Table entities)` | **≤ 2%** | Rising rate → the living-spec reconciliation (v1 §12's "Augment-derived" pattern) isn't keeping pace with actual system change |
| **DQ-015** | Median requirement age since last validity check | `median(now() - t_valid)` across `Approved` `Requirement`s | **≤ 180 days** | An old, never-revisited requirement in a fast-changing system is a silent risk — this doesn't mean the requirement is wrong, it means no one has recently confirmed it's still right |

### Dimension 7 — Uniqueness

| ID | Metric | Formula | Target | Consequence if breached |
|---|---|---|---|---|
| **DQ-016** | Near-duplicate density | `count(pairs flagged by sleep-time consolidation agent, §8.3, above similarity threshold) / count(Requirement)` | **≤ 5%** | Feeds the sleep-time agent's consolidation proposal queue — proposals require human approval (§8.3), never auto-merged |

### Dimension 8 — Traceability Integrity

| ID | Metric | Formula | Target | Consequence if breached |
|---|---|---|---|---|
| **DQ-017** | End-to-end chain completeness | `count(Requirement WITH unbroken path to ≥1 Approved TestRun) / count(Requirement WITH status=Approved AND linked to a Release)` | **100%** for anything in a shipped `Release` | This is the platform's single most important number — it's the literal claim the whole system exists to make true |
| **DQ-018** | Circular-traceability count | `count(Requirement WHERE sole supporting TestCase cites only that Requirement with no independent AcceptanceCriterion)` (§7 Layer 8's circularity heuristic) | **0** | Any nonzero count is investigated individually — this pattern indicates reverse-engineered rather than derived traceability |
| **DQ-019** | Orphan-code rate | `count(Method WITH no IMPLEMENTS edge) / count(Method in a service under this platform's scope)` | Track as a trend; **not** a hard gate (legitimate undocumented legacy code exists) | High/rising rate on a service that's supposed to be fully under management is a scope-completeness signal, not necessarily an error |

### Dimension 9 — Process Trust (§7.1, restated here for a complete single catalog)

| ID | Metric | Formula | Target |
|---|---|---|---|
| **DQ-020** | Judge disagreement rate | per §7.1 | Tracked by connector/source type |
| **DQ-021** | Reviewer override rate | per §7.1 | Rising trend investigated |
| **DQ-022** | False-acceptance rate (adversarial set) | per §7.1, §7 Layer 9 | The platform's core safety metric — see §7.1 for full detail, not restated here |

---

## 3. The Safeguard: a Composite Quality Gate, Distinct From Per-Fact Guardrails

§7's ten-layer guardrail stack decides whether an *individual fact* enters the graph. This safeguard is different in kind: it's a **standing, continuously computed composite score over the graph's current state**, checked at three points where an aggregate quality judgment — not a per-fact one — is the right control.

### 3.1 Composite score computation

```
quality_score(scope) =
    weighted_average(
        DQ-003 (conformance)      × 0.15,
        DQ-006 + DQ-007 + DQ-008  × 0.30,   (completeness, averaged)
        DQ-010 (inverted, normalized) × 0.10,   (consistency)
        DQ-012                    × 0.20,   (corroboration -- weighted heavily: this is the hardest gate)
        DQ-014 (inverted)          × 0.10,   (currency)
        DQ-017                    × 0.15    (traceability integrity -- the platform's core claim)
    )
```
`scope` is any subgraph — a service, a release candidate, a whole project. Weights above are a starting proposal, not fixed; DQ-012 and DQ-017 are weighted highest deliberately, since those two map directly to the two failure modes this whole platform exists to prevent (unverified facts treated as verified; broken traceability claims).

### 3.2 The three gate points

| Gate point | What it blocks | Threshold |
|---|---|---|
| **Release gate** (extends §11.4's existing CI check) | A `Release` whose scoped `quality_score` falls below **85** cannot proceed, independent of whether every individual §7 guardrail passed — a release can pass every per-fact check and still represent an unhealthy slice of the graph in aggregate (e.g., technically-passing but heavily stale coverage) | **Adopted at 85.** Configurable, versioned like everything else in §10.2's validation-rule-engine pattern — revisit at the Phase 0→1 boundary once real score distributions exist to calibrate against |
| **Weekly trend check** (new, not previously in the spec) | Nothing blocks automatically — this is a standing report, not a gate — but a `quality_score` trending down for **3 consecutive weeks** triggers a mandatory review under CONST-025's "recurring gap → strengthen the control" logic | **Adopted at 3 weeks.** Monitoring, not blocking |
| **New-source onboarding gate** | Before a new ingestion source (e.g., adding a second Jira instance, a new document repository) is allowed to write at `auto_write` confidence tier, its first **500** extractions are scored on DQ-002 and DQ-020 specifically — a new source doesn't inherit the trust an established one has earned | **Adopted at 500.** N/A until the calibration batch completes |

### 3.3 Why a composite score, not just the individual metrics

Any single metric can look fine while the aggregate signal is bad — 100% AC coverage doesn't matter if half those ACs are vague (DQ-004) and uncorroborated (DQ-012). The composite score exists specifically to catch the case where every individual number clears its bar but the requirement or release, taken as a whole, still shouldn't ship. It is a genuine judgment call layered on top of the deterministic per-metric checks, not a replacement for them — both are needed.

`REQ-METIS-DQ-01`: The composite score and its full metric breakdown are queryable via a new tool, `metis_quality_score(scope)` — read-only, ships enabled by default (low risk, pure aggregation over already-computed data, no new LLM calls).

---

## 4. Constitution Amendment 1 — Article XI: Data, Requirement & Specification Quality

Per the adopted Constitution's own Article X (CONST-031/032), this is filed as a formal amendment, not a silent edit: it **adds** rules (frictionless per CONST-032) and doesn't weaken any existing one, so it doesn't trigger the heavier justification bar CONST-032 reserves for loosening amendments.

> **Amendment 1 metadata**
> Proposed by: platform owner (per CONST-031's provisional single-owner authority)
> Date: this session
> Type: Addition (new Article) — not a modification of any existing Article
> Rationale: the adopted Constitution's Articles I–X govern individual facts and individual gates; this amendment adds the aggregate, composite-quality layer identified as missing when reviewing what "data/requirement/specification quality" requires as a whole, not just per-item.

**CONST-034.** Every `Release` is subject to the composite `quality_score` gate (§3.2) in addition to, not instead of, every applicable rule in Articles I–IX. A release cannot proceed on the strength of the composite score alone if any individual hard gate (e.g., DQ-012's 100% corroboration-compliance requirement) is failing — the composite score is an additional filter, never a way to average out an individual Critical-severity gap.

**CONST-035.** The full metric catalog in §2 above is computed on a standing schedule — **daily for Dimension 1/2/3/8 metrics that gate releases, weekly for Dimension 4/5/6/7/9 trend metrics** (adopted) — and is queryable by any platform user via `metis_quality_score`, not held as an internal-only number. Transparency about current data quality is itself part of this platform's trustworthiness claim.

**CONST-036.** A new ingestion source does not receive `auto_write` confidence-tier trust (§7.3) until it clears the onboarding gate (§3.2) — this closes a gap in the original Article I–IX set, which defined corroboration and confidence rules per-fact but didn't previously address a systematically bad *source* producing many individually-plausible-looking bad facts.

**CONST-037.** DQ-017 (end-to-end chain completeness for anything in a shipped `Release`) is elevated to the same enforcement tier as CONST-005 — **100%, no exceptions, no override without the full CONST-011 emergency-change pattern.** This is the metric this platform's entire value proposition rests on; it does not get a soft target.

---

## 5. Updated Enforcement Mapping (extends the adopted Constitution's Appendix)

| Article | Primary enforcement point | Failure mode if unenforced |
|---|---|---|
| **XI — Data/Spec Quality (new)** | `metis_quality_score` tool + release gate (§3.2) + weekly trend monitoring | Individually-passing facts aggregating into an unhealthy release; a bad new source poisoning the graph before anyone notices the pattern |

---

## 6. Status — All Brackets Now Filled (adopted defaults, not final)

| Item | Status |
|---|---|
| Composite score weights (§3.1) | **Adopted as proposed** (0.15/0.30/0.10/0.20/0.10/0.15) — recalibrate after Phase 0 shows which dimension actually predicts real-world problems; this is a starting point with real numbers behind it, not a placeholder |
| Release-gate threshold (85), calibration-batch size (500), trend-check window (3 weeks) | **Adopted at the stated values.** Same discipline as the Constitution: a real number the platform can enforce today beats a blank waiting for perfect information |
| DQ-002's initial tier targets (60/30/10) | **Adopted as stated in §2, Dimension 1.** Explicitly the least-confident number in this document — flagged for the earliest re-check once Phase 0 extraction volume exists, likely within the first few weeks rather than waiting for a full quarter like the others |

**Nothing in this framework is blocked on further input.** Every threshold is now a live, enforceable number. "Adopted" here means "in force and revisable," not "permanent" — Article X's amendment process (§4) is exactly the mechanism for revising any of these once real data justifies a different number, and CONST-032 already requires more justification to loosen a number than to tighten one.
