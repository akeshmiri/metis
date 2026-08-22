# Standards Integration — Requirement Quality & State-Transition Correctness
## Constitution Amendment 4

---

## 0. What's already there vs. what's genuinely new

Checked the real archive rather than assuming. Atlas's `test-designer` skill already has a working, real pattern: **ISO/IEC/IEEE 29119** (test documentation, default-loaded, maps standard clauses directly onto `test-design-template.md` sections) as the primary standard, with **IEEE 829**, **ISO/IEC/IEEE 15288**, and **12207** (life-cycle processes) as side-references consulted only when a deviation needs justifying. That's a good, proven pattern — default fragment + side-references, not everything loaded always — and it's worth reusing structurally for what follows, rather than inventing a different convention.

**What's not there:** nothing in Atlas addresses requirement quality characteristics (as opposed to test *documentation* structure) or state-machine formal semantics. Those are exactly your stated initial focus, so this is genuinely new ground, not a rename of something that already exists.

---

## 1. Requirements quality: ISO/IEC/IEEE 29148:2018

**What it is:** *Systems and software engineering — Life cycle processes — Requirements engineering.* Among other things, it defines the standard set of **requirement quality characteristics** a well-formed requirement should satisfy: unambiguous, complete, singular (atomic — one requirement, one testable statement), feasible, verifiable, correct, necessary, conforming (to whatever house template/structure is in force), and consistent (with other requirements). EARS (§4.3's existing conformance gate) is a *structural* pattern for writing requirements that tend to satisfy these characteristics — but Métis currently checks EARS structure only, not the underlying characteristics EARS exists to serve. A requirement can be perfectly EARS-shaped and still fail "singular" (bundling two behaviors into one While/When clause) or "verifiable" (an unmeasurable qualitative term like "the system shall respond quickly").

**Why this belongs in the Constitution, not just the spec:** Article I already governs traceability and specification integrity — 29148's characteristics are the missing, internationally-standardized substance behind what "specification integrity" actually means, rather than leaving that term to informal judgment.

## 2. State transitions & triggers: UML Behavior State Machines (ISO/IEC 19505)

**What it is:** the formal semantics underlying `State`/`Transition`/`Guard`/`Trigger`/`Action` — concepts the ontology already has (§4, extended by the Behavior Model pipeline) but without a cited formal basis for what makes a *set* of transitions well-formed, as opposed to merely well-*shaped* individually. UML's Behavior State Machines (derived from Harel statecharts, standardized via ISO/IEC 19505) gives three checkable well-formedness properties directly relevant to what Stage 2 (Behavior Modeling) currently does by LLM interpretation alone:

- **Determinism:** no two `Transition`s from the same source `State` should fire on the same `Trigger` with overlapping (non-mutually-exclusive) `Guard` conditions — an ambiguous state machine, formally.
- **Completeness:** every `State` should have a defined outcome (a `Transition`, or an explicit "no-op"/self-transition) for every `Trigger` that can plausibly occur while in that state — an undefined trigger-in-state is a real, well-known bug class (the classic "what happens if X occurs while we're in state Y and nobody thought about it" defect).
- **Reachability:** every `State` should be reachable from a defined initial state via some path of `Transition`s — an unreachable `State` is either a design error or dead specification.

**Why this matters concretely, not just formally:** these three checks are exactly the kind of thing a human reviewer might miss when confirming a single proposed `Transition` in isolation (Behavior Modeling's Stage 2 currently validates one `Transition` at a time against corroboration, per `REQ-METIS-BM-01`) but a machine check catches immediately once *all* `Transition`s for a given entity are considered together as one state machine.

---

## 3. Constitution Amendment 4 — Article XIII: Standards-Grounded Quality Gates

**CONST-047.** Every `Requirement`/`MicroRequirement` reaching `Approved` MUST be scored against ISO/IEC/IEEE 29148's requirement quality characteristics (unambiguous, complete, singular, feasible, verifiable, correct, necessary, consistent) as a **structured checklist attached to the entity**, not a free-text judgment call — extending `DQ-002` (EARS Conformance, Dimension 2) rather than replacing it: EARS conformance checks *structure*, this checklist checks the *substance* EARS structure exists to serve. A requirement can pass EARS structural conformance and still fail this checklist (e.g., "singular" failing on a bundled While/When clause) — both checks are required, neither substitutes for the other.

**CONST-048.** Any set of `Transition`s sharing a common source-`State` context MUST pass all three state-machine well-formedness checks (determinism, completeness, reachability, §2 above) before any of them individually reaches `auto_write` or `Approved` tier — this is a **set-level check**, run whenever a new `Transition` is proposed for a `State` that already has other `Transition`s, not a one-time check performed once per `Transition` in isolation.

**CONST-049.** A determinism or completeness violation (§2) is surfaced as a `Disputed`-adjacent flag — **not silently resolved by picking one interpretation** — mirroring `CONST-046`'s existing rule for code-graph/requirement-text disagreement. An ambiguous or incomplete state machine is exactly the kind of finding that needs a human's judgment, not the system's guess.

**CONST-050.** Generated functional tests (Behavior Model pipeline, Stage 4) for a `Transition` set that failed §2's completeness check MUST include an explicit test asserting the *documented* behavior for the missing case once a human resolves it — closing the loop from "we found an undefined trigger-in-state" to "there's now a test proving the resolved behavior," not just a graph annotation nobody acts on.

---

## 4. Concrete edits to existing documents

### 4.1 `metis-specification.md` §4.3 (EARS conformance)
Add an explicit citation grounding EARS's *purpose* in ISO/IEC/IEEE 29148's characteristics, and note that structural EARS conformance and substantive 29148 scoring are two distinct, both-required checks (not one implying the other).

### 4.2 `metis-behavior-model-test-pipeline.md` Stage 2 (Behavior Modeling)
Add the three set-level well-formedness checks (§2 above) as an explicit sub-step, run whenever a `Transition` is proposed into a `State` that already has siblings — this is a natural, small addition to a stage that already validates individual `Transition`s, extending it to validate the *set*.

### 4.3 `metis-data-quality-framework.md`
Extend `DQ-002` (currently EARS-structure-only) to reference the 29148 checklist as a required companion score, and add set-level determinism/completeness/reachability as new checkable properties under Dimension 3 (Completeness) — this is the dimension they conceptually belong to, since an incomplete state machine is a completeness defect at the model level, not just the per-requirement level `DQ-003` already covers.

Implementing these now, then presenting the updated files together.

---

## 5. What's genuinely still open

| Item | Status |
|---|---|
| Whether to score 29148's full characteristic set or a prioritized subset for Phase 0 | All eight are defined here; a phased rollout (e.g., unambiguous/singular/verifiable first, the rest at Phase 1) is reasonable if the full set proves too heavy for pilot volume — not decided here |
| Formal tooling for the determinism/completeness/reachability checks (a real graph-algorithm implementation vs. an LLM-assisted heuristic pass) | These are genuinely computable graph properties (reachability is literally graph traversal) — worth implementing as deterministic Cypher queries, not LLM judgment, per the platform's own code-vs-LLM principle (§9) — flagged as an implementation task, not designed here |
