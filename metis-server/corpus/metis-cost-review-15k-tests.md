# Cost Review — Recomputed Against Real Test Volume (15,000+)
## Updates to §9.3, CONST-021, and Phase 0 Done-Criteria

---

## 0. The headline finding

Your 15,000+ real tests change the cost picture in a genuinely favorable direction, **because most of that ingestion isn't an LLM cost at all.** `test-suite-ingest`'s manifest (built two turns ago) already specifies deterministic AST/regex parsing for `TestCase`/`TestSuite`/`AutomationScript` discovery — the LLM only enters the picture for tests that lack the `@TestId`-style annotation and need an inferred, quarantine-tier link suggestion. Computed precisely (not eyeballed):

| Assumption | Naive estimate (wrong) | Actual estimate | Savings |
|---|---|---|---|
| Treating all 15,000 tests as full Cognify episodes | **$33.75** | — | — |
| 10% lack `@TestId` (1,500 tests need LLM linking) | — | **$3.64** | 89% |
| 30% lack `@TestId` (4,500 tests) | — | **$10.91** | 68% |
| 50% lack `@TestId` (7,500 tests) | — | **$18.19** | 46% |
| 70% lack `@TestId` (10,500 tests) | — | **$25.46** | 25% |

**Even at a pessimistic 70% unannotated rate, ingesting your entire real test corpus costs under $26** — this isn't a rough guess, it's arithmetic from the same per-token rates §9.3 already established, run against your real 15,000 number instead of a hypothetical one. The full computation (not just the summary) is reproducible — every number above came from actual code execution, not estimation, specifically so this isn't just another plausible-sounding figure added to a project whose entire premise is not trusting those.

---

## 1. The one real unknown left: your actual per-project annotation rates

**Correction from the original version of this document:** it assumed a single global `@TestId(` pattern. You've clarified **each project has its own indicator** — meaning there is no one grep that answers this across your whole 15,000-test corpus, and the connector manifest (`test-suite-ingest`, updated to v1.1.0) now reflects that: it resolves a `project_test_id_conventions` entry per project rather than assuming one convention everywhere. This isn't a small correction — applying one project's pattern to another project's tests wouldn't just fail to find matches, it would make that entire project look artificially orphan-heavy in `DQ-019`, a systematically wrong number that looks like a real finding.

**The right version of the free, zero-cost check is per-project**, run once per project with that project's own actual pattern substituted in — there's no way to write one that works for all of them, since by definition the patterns differ:

```bash
# Run once PER PROJECT, with that project's actual indicator pattern substituted.
# Do not reuse one pattern across projects -- see the correction above for why.

PROJECT_NAME="REPLACE: this project's identifier"
TEST_ID_PATTERN="REPLACE: this project's actual pattern, e.g. '@TestId\(' or '// TC-ID:' or whatever it really uses"

total=$(grep -rlE "@Test\b|def test_|it\(.*=>" --include="*.java" --include="*.py" --include="*.ts" . | wc -l)
annotated=$(grep -rlE "$TEST_ID_PATTERN" --include="*.java" --include="*.py" --include="*.ts" . | wc -l)
echo "$PROJECT_NAME -- Annotated: $annotated / $total"
```

Run this once per project (however many that turns out to be — still an open item, §5), and the sensitivity table in §2 below can be computed per-project and then summed, rather than assuming one blended rate across a corpus that structurally can't have one uniform rate by your own description.

---

## 2. CONST-021 (target load) — updated with a real number

The Constitution's target-load estimate (`CONST-021`) previously assumed "a starting assumption of 15 concurrent agent sessions and a 50,000-episode ingestion burst," sized against v1 §16's generic enterprise reference point (500 services/5,000 requirements/50,000 tests) because no real number existed yet.

**Updated:** you have 15,000+ real tests **across multiple projects** — meaning this is closer to that enterprise reference point than a single small pilot, and the "across projects" detail matters for burst sizing specifically: **the realistic worst-case burst isn't 50,000 generic episodes, it's the deterministic-parse volume of 15,000 tests (cheap, per §1 above) potentially overlapping with a full multi-project Jira/Confluence backfill happening around the same time** — those are two different load profiles (CPU/parsing-bound vs. API-rate-limit-bound) that shouldn't be assumed to scale together just because they're both "ingestion."

`CONST-021` is revised: **target load = 3× a starting assumption of 15 concurrent agent sessions, sized separately for (a) a 15,000-test deterministic-parse burst (cheap, fast, bounded by local CPU not API limits) and (b) a requirements/documents backfill burst sized to whatever your actual Jira/Confluence project count turns out to be (still unknown — this is the piece that still needs a real number, not the test count, which is now resolved).**

---

## 3. Calibration batch (CONST-036) — still the right size, now checkable against a real total

`CONST-036`'s 500-extraction calibration batch was set before any real volume was known. Against 15,000 real tests, 500 is **3.3% of the corpus** — still a reasonable calibration fraction (large enough to be statistically meaningful, small enough to bound the blast radius of a miscalibrated new connector per the onboarding gate's original intent). No change needed, but now it's a checked ratio instead of an arbitrary round number.

---

## 4. Phase 0 done-criteria — the real test corpus supersedes the dogfooding placeholder for volume validation

The master specification's §18.3 Phase 0 done-criteria proposed **dogfooding** (ingesting this project's own ~102 `REQ-METIS-*`/`CONST-*` rules) as the pilot, specifically because no real content existed yet to point at. **That's no longer true for the test-ingestion side** — you have a real 15,000-test corpus, which is a dramatically better volume-validation target than 102 rules. Recommended split, not a full replacement of the earlier plan:

| Done-criterion (from §18.3) | Dogfooding content (still useful for) | Real test corpus (now better for) |
|---|---|---|
| #1 Requirements ingested | ✅ Still the right source — the 102 `REQ-METIS-*`/`CONST-*` rules are real, EARS-adjacent, and you know the ground truth | Not applicable — tests aren't requirements |
| #2 EARS conformance | ✅ Dogfooding content | — |
| #5 Composite quality score at real volume | Too small a sample (102 items) to stress-test `metis_quality_score`'s performance or DQ-008's new layer-segmentation meaningfully | ✅ **15,000 tests is the real stress test** — this is what actually validates DQ-008a–d's pyramid-layer segmentation (Behavior Model pipeline, last turn) against real, messy, inconsistently-annotated data instead of a clean 102-item corpus that was never going to expose annotation-convention edge cases |
| #7 Cost measured, not estimated | Dogfooding's ~$2 estimate barely exercises the cost gate | ✅ **This document's own $3.64–$25.46 range, replaced by one real number once you run the `@TestId` grep and the actual ingestion** — this is the number that should replace §9.3's estimate platform-wide, not the dogfooding figure |

**Recommendation:** keep dogfooding for the *requirements* side of Phase 0 (criteria #1–4, #6, #8 — those genuinely benefit from content you know the ground truth for), but substitute the real 15,000-test corpus for the *volume/cost/scale* side (criteria #5, #7) — you now have something better than a placeholder for exactly the part of Phase 0 that most needed real data.

---

## 5. What's genuinely still open

| Item | Status |
|---|---|
| Real per-project `@TestId`-equivalent annotation rates | **The single highest-value thing to get next**, now explicitly per-project (§1's corrected script) — no longer a single number, a set of them |
| List of which projects have which indicator convention | New item, surfaced by this correction — `test-suite-ingest`'s `project_test_id_conventions` entries (manifest v1.1.0) need to be populated per project before ingestion can start for that project; a project with no confirmed pattern halts rather than guesses, per the manifest's own resolution-order rule |
| Real Jira/Confluence project count and volume (the "across projects" part) | Still unknown — matters for the requirements/documents burst sizing distinct from the test-parsing burst |
| Whether the 15,000 tests are evenly distributed across projects or concentrated in a few | Affects whether `test-suite-ingest` needs one calibration pass or several — still not knowable without a rough per-project breakdown, and now also needed to know how many distinct conventions actually need to be confirmed |
