# The v1 → v2 migration plan

**This plan completed at commit `61814dc`.** It was §20.2–§20.7 of
[`docs/metis-application-spec.md`](../metis-application-spec.md) and is kept
here for its reasoning, not as a description of anything current.

Read it as a record of a decision, not as instructions. Specifically:

- **§20.2's line counts** audit the v1 tree — `structural_validation.py`,
  `guardrails/pipeline.py`, `uif_intake.py`, `cognify/`. None of those exist.
- **§20.4 targets twelve labels.** The ontology settled at forty-five, each with
  a named writer and a named reader under D-1. §8.2 of the spec is authoritative
  and `test_ontology.py` pins the count.
- **RD-11 places `ontology2` beside `structural_validation.py`.** Neither exists;
  the outcome was `metis_mcp/ontology/` and the deletion of the v1 module.
- **§20.5's "Existing LOC: 0"** table lists the MBT engine, the model-source
  framework, the CPG sidecar, identity, the renderer, the specification
  generator, the review UI and roles. All eight are built.

What survives into the live specification is the readiness register (RD-1…RD-7,
now §20.1) — six of seven closed — because `metis_mcp/ontology/schema.py` cites
RD-2 and RD-6 by id. Nothing in the tree cites RD-8 through RD-16.

For what the rebuild actually produced, see [`CHANGELOG.md`](../../CHANGELOG.md).

---

### 20.2 What changes in Métis — measured

Every line counted from the current tree, not estimated.

| Disposition | LOC | Share | Modules |
|---|---|---|---|
| **Reuse as-is** | **852** | 7% | `behavior_model.py` (444 — determinism, guard completeness, reachability; exactly §2.6) · `neo4j_graph_store.py` (193) · `guardrails/pipeline.py` (91) · `ears_checker.py` (59) · `vagueness.py` (65) |
| **Adapt** | **1,863** | 14% | `structural_validation.py` (380 — mechanism keeps, 45 labels → 12) · `intake_segmentation.py` (344) · `requirement_mining.py` (327) · `temporal.py` (280 — revisions keep, `ModelVersion` is new) · `requirement_landing.py` (278) · `uif_intake.py` (254) |
| **Replace** | **1,178** | 9% | `test_skeleton_generator.py` (303) and `transition_coverage_plan.py` (303) → the MBT engine · `cognify/` (380) → the CPG sidecar · `pyramid_gap_check.py` (192) → dropped |
| **Out of scope** | **~9,177** | **70%** | Academy, site and deck renderers, DQ metrics, Constitution gate, hybrid retrieval, memify, sleep-time consolidation, token optimisation, Copilot integration, pinned memory, micro-requirements, LLM judge, agent generator, skill catalogue, cost gate, OAuth2/RBAC as built, six of seven connectors |
| **Total** | **13,070** | | |

**Tests:** 9,477 LOC across 62 files. **1,741 LOC across 10 files carry forward**
(18%) — the rest exercise out-of-scope or replaced code.

### 20.3 The conclusion this forces

**RD-8.** This is **not an incremental change to Métis.** It is a new application
that harvests roughly **4,500 lines** (2,715 production + 1,741 test) from a
13,000-line codebase, of which **70% is out of scope**.

Treating it as an evolution of the existing server would mean carrying nine
thousand lines of unused code past a schema replacement — and the existing tests
largely defend that code, so they would resist the change rather than protect it.

### 20.4 The schema is replaced, not migrated

| | Current | Target |
|---|---|---|
| Labels | ~45 | **12** (§8.2) |
| New labels | — | `ModelVersion`, `TestPath`, `Finding`, `Run`, plus `Override` (§17) |
| New relationships | — | `CONTAINS`, `GENERATED_FROM`, `COVERS`, `PRODUCES`, `INVOKES`, `ABOUT` |
| Removed | — | ~33 labels and their relationships (§8.7) |

**RD-9.** There is no data worth migrating. Provenance is the point (D-1), and
copying nodes without their originating episodes would violate it on day one.
Content is **re-ingested**, not migrated.

### 20.5 What is genuinely new

| Component | Existing LOC |
|---|---|
| **MBT engine** — criteria, path generation (§6) | **0** |
| Model-source framework and override layer (§4, §17) | 0 |
| CPG sidecar, query packs, ontology mapper (§5) | 0 |
| Identity, matching, delta (§14) | 0 |
| ISTQB renderer and automation payload (§7) | 0 |
| Stakeholder specification generator (§18) | 0 |
| Review UI (§9.3) | 0 |
| Roles and identity (§9.6) | 0 |

The MBT engine remains the piece that exists in none of the three systems and
carries the most risk — which is why N-16 puts it first.

### 20.6 Change strategy — evolve `metis-server` in place

**Decision: the new application is built inside the existing `metis-server`
tree.** This is the option with the most exposure — deleting 9,000 lines while
adding new ones, and replacing a schema in a live package. The strategy below
exists to remove that exposure rather than accept it.

**RD-10 — the governing rule: additive first, deletion last.** Every risk in
evolving in place comes from deleting or mutating too early. Nothing existing is
removed or changed until the new chain works.

#### Phase A — additive only

New packages alongside the existing ones. **No deletions. No edits to
out-of-scope modules.**

```
metis-server/
  metis_mcp/
    mbt/              NEW  criteria, path generation (§6)
    model_sources/    NEW  the three sources + override layer (§4, §17)
    identity/         NEW  natural keys, matching, delta (§14)
    rendering/        NEW  ISTQB + automation payload (§7)
    specgen/          NEW  stakeholder specification (§18)
    ontology2/        NEW  the 12-label ontology, alongside the existing one
    …                 existing modules untouched
  code_analysis/      NEW  Joern sidecar, query packs, mapper (§5)
```

**RD-11.** `ontology2` sits **beside** `structural_validation.py`, not inside it.
Changing `KNOWN_LABELS` from 45 to 12 in place would break the existing suite
immediately; a parallel module lets both exist until cutover.

**RD-12.** The existing test suite **stays green throughout Phase A**, because
nothing it depends on has changed. This is the main advantage evolve-in-place
offers, and it is only realised if RD-10 is respected.

**RD-13.** Harvesting is in-place adaptation for the 852 reuse-as-is lines
(§20.2), and copy-then-adapt for the 1,863 adapt lines — the originals stay until
Phase C.

#### Phase B — cutover

Once the chain runs end to end on the login model and the first Athena service:

| Step | Action |
|---|---|
| 1 | Apply the new schema to a **fresh** database (RD-9: re-ingest, never migrate) |
| 2 | Switch the new application to `ontology2` |
| 3 | Re-ingest content through the new pipeline |
| 4 | Run the full acceptance set (§13, §19) against real data |

**RD-14.** Cutover is reversible until step 4 passes: the old package and old
schema are untouched, so reverting is a configuration change, not a restore.

#### Phase C — retire

**One deliberate deletion pass**, after Phase B passes and not before.

| Delete | LOC |
|---|---|
| The ~9,177 lines of out-of-scope modules (§20.2) | ~9,177 |
| The ~52 test files covering them | ~7,700 |
| `test_skeleton_generator.py`, `transition_coverage_plan.py`, `pyramid_gap_check.py`, `cognify/` | 1,178 |
| The old 45-label ontology; `ontology2` is renamed into its place | — |

**RD-15.** Deletion is a **single reviewable change**, not attrition across the
build. Piecemeal removal is how a codebase ends up half-migrated, with nobody sure
which half is live.

**RD-16 — the risk that remains.** If Phase C never happens, the tree carries
9,000 lines of dead code and two ontologies indefinitely, and the next person
cannot tell which is current. Phase C is not optional cleanup; it is the step that
makes the decision to evolve in place correct rather than merely convenient.

### 20.7 Remaining readiness gaps

| # | Gap | Size |
|---|---|---|
| ~~RD-1~~ | ~~Extraction engine~~ | ✅ Closed (X-1a) |
| ~~RD-3~~ | ~~Module layout~~ | ✅ Closed (§20.6 Phase A) |
| **RD-2** | Schema DDL for the 12 labels and their relationships | Small |
| **RD-4** | Work breakdown and sequencing within N-16's stages | A planning pass |
| **RD-5** | Test strategy for the new system | A planning pass |
| **RD-6** | Framework configuration schemas (X-4, X-10b) | Small |
| **RD-7** | Review UI design (§9.3 states obligations, not design) | A planning pass |

---
