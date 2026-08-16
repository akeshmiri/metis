# 13 — Static Code Analysis & Behaviour Extraction

**Status:** design, decided. Supersedes Métis v1's `cognify/structural_extraction.py`
and `cognify/code_graph_archaeology.py` entirely, and Atlas's `code-explorer` /
`git-repository-analyzer` code-inspection paths.

**Decision:** code processing is performed by **Joern** (Apache-2.0, Code
Property Graph) running as a **sidecar analysis engine**. Dynamic techniques
(process mining, automata learning) are explicitly **out of scope** — see §13.13
for what that costs and how the design compensates.

> ### v1 scope (DD-1) — read this before implementing
>
> | Layer | § | v1 status |
> |---|---|---|
> | **1. Structural extraction** (`Class`, `Method`, `CALLS`, `IMPORTS`, `INHERITS`) | 13.5 | **IN SCOPE** |
> | **2. Endpoint and contract discovery** | 13.6 | **IN SCOPE** |
> | **3. Verified type/member registry** | 13.7 | **IN SCOPE** |
> | 4. State-transition extraction | 13.8 | **DEFERRED** |
> | 5. AC↔Transition matching | 13.9 | **DEFERRED** |
> | Impact analysis via reachability | 13.11 | **IN SCOPE** (Layer 1 is sufficient) |
>
> Layers 4–5 remain fully specified here because they are the funded follow-on,
> not a discarded idea. **Nothing in Layers 1–3 depends on them**, and Layers 4–5
> depend only on Layer 1 — so deferring them costs no rework.
>
> **What deferral costs, stated once:** `Transition`s remain hand-authored only,
> so **DQ-024 is unfalsifiable in v1** (the same person authors the behaviour and
> its acceptance criterion), and behaviour-level corroboration is unavailable.
> See [§01.8](01-vision-and-scope.md).
>
> **Language:** Java is confirmed as the primary stack (RD-1). `javasrc2cpg`
> (source) and `jimple2cpg` (bytecode) are Joern's two most mature frontends —
> the most favourable case for this decision.

---

## 13.1 Why Joern, and what was rejected

Four hard constraints, applied simultaneously:

| Constraint | Why it is non-negotiable |
|---|---|
| Apache-2.0-compatible on **private** source | The estate is closed-source; a licence that only permits OSS analysis is disqualifying, not inconvenient |
| Multi-language | Generators already target Java, C# and Python (§08); a Java-only engine strands the rest |
| **Control-dependence (CDG) + data-dependence (DDG)** | Without control dependence you cannot recover a `guard_expression`. This eliminates every "structure-only" tool |
| Reachable from our pipeline | Must produce machine-readable output we can map into the closed ontology |

| Tool | Verdict |
|---|---|
| **Joern** | **Selected.** Only tool clearing all four. CPG = AST + CFG + CDG + DDG + call graph; frontends for Java (source and bytecode), C/C++, JS/TS, Python, Kotlin, Go, Ruby, C#, and binaries via Ghidra; CPGQL query language; `joern-export` to `neo4jcsv`/`graphml`/`graphson`/`dot`; flatgraph backend (v4+) |
| CodeQL | Rejected — **licence**. Free only for OSI-licensed open source, academic research, or OSS hosted on GitHub.com; closed source requires a commercial GHAS licence. Also produces a relational database queried by QL, with no graph export |
| Semgrep CE | Rejected — interprocedural and cross-file analysis are **Pro (paid)**; CE is intraprocedural pattern matching with no CFG/CDG and no graph export |
| jQAssistant | **Optional JVM complement, not a replacement.** Neo4j-native, rules written in Cypher, scans bytecode/Maven/Git history — excellent plumbing, but **structural only**: no control or data flow, therefore no guards. May be adopted additionally for architecture and Git-history facts on a JVM estate (§13.12) |
| SootUp / WALA / Doop / Tai-e | **Held in reserve.** IFDS/IDE interprocedural analysis is the most precise route to typestate extraction, but is a framework (analysis written in Java) not a query tool, and is single-language. Escalation path if §13.14's pilot underperforms on a Java-only estate — not the starting point |
| SCIP / LSIF / Kythe / Glean | Rejected — cross-reference indexes with no flow analysis |

`REQ-CGA-001` — Métis MUST NOT depend on any code-analysis engine whose licence
restricts analysis of closed-source code.

## 13.2 Architecture: sidecar, never co-tenant

`joern-export --format=neo4jcsv` is real and works. **We do not use it against the
Métis graph.** Three reasons, each independently sufficient:

1. **Schema violation.** It exports the *CPG* schema — `METHOD`, `CALL`,
   `CONTROL_STRUCTURE`, `IDENTIFIER` — not the Métis ontology. Importing it would
   bypass `KNOWN_LABELS`, `ALLOWED_RELATIONSHIPS`, and the four-place ontology
   governance rule (§03).
2. **Volume mismatch of ~4 orders of magnitude.** A CPG for one mid-size service
   is millions of nodes; the Linux kernel benchmark is 48M nodes / 431M edges.
   The entire Métis specification graph is in the low thousands. Co-tenancy would
   destroy retrieval latency, the DQ metrics, and the "the graph *is* the
   specification" premise.
3. **Wrong write semantics.** `neo4jcsv` targets `neo4j-admin database import` —
   bulk, offline, into an empty database. It is not an incremental, idempotent,
   guardrail-gated write path.

```
  ┌────────────────────────── Joern sidecar ───────────────────────────┐
  │  source checkout                                                    │
  │      → joern-parse ──────────► cpg.bin        (artifact store)      │
  │                                   │                                 │
  │                                   ├─ query pack (versioned CPGQL)   │
  │                                   │     joern --script <pack>.sc    │
  │                                   ▼                                 │
  │                          extraction-report.json                     │
  │                          (ontology-shaped, small)                   │
  └───────────────────────────────────┬─────────────────────────────────┘
                                      │
                      ┌───────────────▼────────────────┐
                      │ code-analysis connector        │
                      │  · Episode per analysed unit   │
                      │  · candidate entities/edges    │
                      └───────────────┬────────────────┘
                                      ▼
              guardrails.pipeline.submit_candidate()  → Quarantine
                                      ▼
                              Métis Neo4j graph
```

`REQ-CGA-002` — The CPG MUST be stored outside the Métis graph, as `cpg.bin`
artifacts. No CPG node label may ever appear in the Métis graph.

**Note on browsable exploration (revised under DD-2):** an earlier draft offered
"a separate Neo4j database" as an option for exploring the CPG interactively.
**Neo4j Community supports only one database per instance** (plus `system`), so
under DD-2 that option does not exist. CPG exploration is done through Joern's own
shell against the `cpg.bin`, or by standing up a throwaway instance outside the
Métis deployment. Neither affects the pipeline — the CPG was never meant to be
queried through Métis.

`REQ-CGA-003` — Every fact derived from code MUST enter the graph through the
same `Episode` + `submit_candidate()` contract as every other connector. There is
no privileged write path for code analysis.

`REQ-CGA-004` — CPG construction is a **batch job owned by the ingestion worker**.
It MUST NOT appear in any request-path or MCP-tool code path; build times run
minutes to hours.

## 13.3 CPG lifecycle

| Phase | Command / action | Notes |
|---|---|---|
| Build | `joern-parse <src> --output cpg.bin --language <frontend>` | Frontend chosen from repository config, not inferred |
| Verify | node/edge counts, frontend error log | A frontend that partially parsed MUST fail the job, not silently under-report (P1) |
| Query | `joern --script packs/<name>.sc --param cpg=cpg.bin` | Query pack, §13.4 |
| Emit | `extraction-report.json` | Ontology-shaped, validated against a JSON Schema before it leaves the sidecar |
| Retain | `cpg.bin` keyed by `(repo, commit_sha)` | Enables diffing two commits without a rebuild |
| Expire | configurable; default keep last 3 commits per repo | CPGs are large |

`REQ-CGA-005` — Every extraction report MUST record `joern_version`,
`frontend`, `query_pack_version`, `repo`, `commit_sha`, and per-file parse status.
A report missing any of these is rejected at the connector boundary.

`REQ-CGA-006` — Analysis MUST be anchored to an exact `commit_sha`. `t_recorded`
for every derived Episode is the **commit's own author/committer date**, never the
analysis time (P2).

## 13.4 The query pack contract

CPGQL is Scala. Ad-hoc queries embedded in Python strings are how this becomes
unmaintainable within two releases.

`REQ-CGA-007` — CPGQL queries MUST live in **versioned query packs** under
`code_analysis/packs/<pack>/`, each with:

```
packs/<pack>/
├── pack.yaml            # name, version, joern version range, target frontends
├── query.sc             # the CPGQL script
├── output.schema.json   # JSON Schema the emitted report must satisfy
└── tests/
    ├── fixtures/        # small, real source files with known-correct answers
    └── expected/        # exact expected JSON per fixture
```

`REQ-CGA-008` — Each query pack MUST have at least one fixture test asserting an
**exact expected output** for known input. A pack whose tests do not run in CI is
not eligible for use against a real repository. (This is the same discipline that
caught the corpus-parser attribution bug and the dropped-cross-reference bug in
v1: run the real thing, check a specific known value.)

`REQ-CGA-009` — The Joern version MUST be **pinned** and declared per pack.
Joern moves fast — the 2.x→4.x migration from OverflowDB to flatgraph was
breaking. A version bump is a reviewed change with a full pack test re-run.

## 13.5 Layer 1 — structural extraction (replaces `cognify/`)

Direct replacement of the two v1 modules (380 lines, Python-only, with a
deliberately bounded resolver that handled only bare module-level names and
`self.foo()` calls).

| CPG source | Métis ontology target |
|---|---|
| `cpg.typeDecl` (non-external) | `Class` — keyed `repo:path:name` |
| `cpg.method` (non-external, non-stub) | `Method` — keyed `repo:path:name.method` |
| `TYPE_DECL --AST--> METHOD` | `Class-[:HAS_METHOD]->Method` |
| `cpg.typeDecl.inheritsFromTypeFullName` | `Class-[:INHERITS]->Class` |
| `cpg.call.callee` (resolved, internal) | `Method-[:CALLS]->Method` |
| import/require/using declarations resolving in-repo | `Class-[:IMPORTS]->Class` |
| repository root | `Repository-[:DEFINES]->Class` |

`REQ-CGA-010` — An edge MUST NOT be written when its target is external to the
analysed repository set. Joern models external callees as stub `METHOD` nodes with
`isExternal = true`; these MUST be filtered, never materialised as Métis nodes.
This preserves v1's explicit rule against fabricating stubs for `Exception`,
`Enum`, or third-party packages.

**What improves over v1, concretely:** cross-file and cross-class call resolution
via `methodFullName` and `REF`/`EVAL_TYPE` edges (v1 could not do this and said
so); real type information; and 10+ languages instead of Python only.

## 13.6 Layer 2 — endpoint and contract discovery

| Extraction | CPGQL shape | Ontology target |
|---|---|---|
| REST handlers | `cpg.method.annotation.name("(Get\|Post\|Put\|Delete\|Patch\|Request)Mapping")` (Spring); framework-specific equivalents per stack | `Endpoint`, `Repository-[:EXPOSES]->Endpoint` |
| Route path + verb | annotation parameter literals | `Endpoint.path`, `Endpoint.method` |
| Handler binding | handler `METHOD` node | used as the **trigger anchor** in §13.8 |

`REQ-CGA-011` — Framework annotation/route conventions MUST be configuration
(`code_analysis/frameworks/<framework>.yaml`), never hardcoded in a query pack.

**Cross-check against the OpenAPI contract:** an `Endpoint` present in the
checked-in spec but absent from code, or vice versa, raises a `SpecDriftDetected`
episode and feeds DQ-014 (§06). This is real drift detection against ground truth,
which v1 could only do for a subset of sources.

## 13.7 Layer 3 — the verified type/member registry

Atlas's `code-explorer` exists to produce a "VERIFIED Model Schema Registry" whose
failure mode is `unverified_count > 0`, and whose downstream rule is *"no
UNVERIFIED fields from model-schema-registry.json used in payloads"* — enforced by
instruction-following.

With a CPG this becomes mechanical: `cpg.typeDecl.name(<DTO>).member` yields real
field names with real `typeFullName`s.

`REQ-CGA-012` — Generated test payloads MUST reference only fields present in the
registry. A generator referencing a field absent from the CPG-derived registry
MUST fail the generation stage, not warn. This converts Atlas's strongest
anti-hallucination rule from a prose instruction into a check.

## 13.8 Layer 4 — state-transition extraction  **[DEFERRED — see scope banner]**

**The design judgement that makes this work:** extraction is performed at
**state-variable granularity**, *not* at CFG-statement granularity. A CFG has
hundreds of basic blocks per method; a real login machine has ~7 states.
Statement-level extraction produces thousands of "transitions" that map to no
acceptance criterion — three orders of magnitude of noise.

The technique is **state-variable abstraction** (typestate analysis over a CPG).
Six deterministic steps, each independently testable:

| # | Step | CPGQL shape (illustrative — pin to the declared Joern version) | Produces |
|---|---|---|---|
| 1 | **Identify state variables** | enum `TYPE_DECL`s; members whose type matches configured patterns (`.*Status`, `.*State`); fields written from ≥ N distinct sites | the machine's identity |
| 2 | **Enumerate the state domain** | `cpg.typeDecl.name(<enum>).member.name`, plus literals assigned to the variable | **`State` nodes** |
| 3 | **Locate transition sites** | `cpg.assignment.where(_.target...refsTo.isMember.name(<var>))` | **`Transition` candidates**, one per write site, with `file:line` |
| 4 | **Recover the guard** | `.controlledBy.isControlStructure.condition.code` — the conjunction of conditions control-dominating the assignment. This is precisely what CDG exists for | **`guard_expression`** |
| 5 | **Recover the trigger** | call-graph reachability from annotated entry points (§13.6) to the assignment site | **`trigger`** (e.g. `POST /auth/login`) |
| 6 | **Recover the source state** | (a) reads of the variable compared against a literal that dominate the write (`if (status == LOCKED)`); (b) fixpoint over the transition relation from the initialiser | **`WHEN` edge** |

Output maps 1:1 onto the existing ontology with **no new labels**:

```
State -[:WHEN]-> Transition -[:THEN]-> State
                   ├─ trigger
                   ├─ guard_expression
                   ├─ implementation_status = 'implemented'
                   └─ (new properties, §13.9)
```

`REQ-CGA-013` — Every extracted `Transition` MUST carry the exact
`repo:path:line` of the assignment it was derived from, and the verbatim source
text of its guard. A transition without a code anchor is not a valid candidate.

`REQ-CGA-014` — Step 6 is the least reliable step. Where a source state cannot be
determined by (a) or (b), the Transition MUST be landed with **no `WHEN` edge**
and flagged `source_state_unresolved = true` — never given a guessed or
"most likely" source state (P7, RPI Forbidden Substitutions).

### Schema changes required (all four places, per §03's governance rule)

| Change | Kind | v1 |
|---|---|---|
| `Transition.extraction_method` ∈ `{hand_authored, static_analysis}` | new property | **Add in v1** — hand-authored transitions set it to `hand_authored`, so the field exists and is populated from day one |
| `Transition.code_anchor` (`repo:path:line`) | new property | Defer with Layer 4 |
| `Transition.source_state_unresolved` (boolean) | new property | Defer with Layer 4 |
| `State.state_variable` (fully-qualified field/enum) | new property | Defer with Layer 4 |

No new node labels. No new relationship types. `schema-01`, `schema-02`,
`structural_validation.py` and the ontology document all require updating together.

**Why `extraction_method` lands in v1 anyway:** adding a discriminator later
means backfilling every existing `Transition` and guessing at provenance for
nodes written before the field existed. Adding it now costs one property and
makes the eventual Layer 4 rollout a pure addition.

## 13.9 Layer 5 — mapping acceptance criteria to transitions  **[DEFERRED]**

Joern does not do this, and nothing does. What Joern changes is that the problem
becomes **small and bounded**.

```
AC (from Jira, §05)
   │
   ├─ Step A  deterministic pre-filter  ── functional-area tag match
   │                                    ── endpoint reachability match
   │                                    →  candidate set, typically 5–50 Transitions
   │
   ├─ Step B  Layer 6 LLM-as-judge over the bounded candidate list
   │            input: AC text + each candidate's (source state, trigger,
   │                   guard, target state) tuple + code anchor
   │            question: "does this AC assert this behaviour? answer only
   │                       from the provided text"
   │
   └─ Step C  write AcceptanceCriterion-[:VALIDATES]->Transition
                at Quarantine, human-approved (§06.7)
```

`REQ-CGA-015` — Step A MUST run before Step B and MUST be deterministic. A model
call over an unfiltered candidate set is a P4 violation.

`REQ-CGA-016` — A `VALIDATES` edge derived from Step B MUST NOT auto-write. It
lands at Quarantine regardless of judge confidence.

`REQ-CGA-017` — Where an AC matches **zero** candidate transitions, that is a
first-class finding (`AcceptanceCriterionUnimplemented`), not a silent no-op.
Where an `implemented` Transition matches zero ACs, DQ-024 fires.

**Why DQ-024 finally becomes real:** in v1 every `implemented` Transition was
hand-authored in `demo_data/login_example.py`, so "implemented behaviour with no
acceptance criterion" was unfalsifiable by construction. With Transitions
extracted from actual code, DQ-024's gap list becomes *real shipped behaviour that
nobody wrote an acceptance criterion for* — which is arguably the single most
valuable report the platform can produce.

## 13.10 Corroboration

### What Layers 1–3 contribute in v1

`REQ-CGA-024` — In v1, code analysis contributes corroboration through **structural
evidence only**. An `Endpoint` or `Method` counts as an independent source for an
`AcceptanceCriterion` **only when**:

- it was derived from a CPG built at a named `commit_sha` (`REQ-CGA-006`), **and**
- the originating Episode's `source_connector` is `code-analysis`, not `jira`
  (structurally guaranteed, `REQ-GRD-017`), **and**
- the link to the AC is **human-approved**, not inferred from name similarity.

`REQ-CGA-025` — Name similarity alone MUST NOT establish corroboration. An
`Endpoint` called `/password-reset` and an AC mentioning "password reset" is a
**candidate for human review**, not evidence. This is the exact shortcut that
would make the corroboration count meaningless while appearing to solve the
scarcity problem DD-1 creates.

### What Layers 4–5 would add  **[DEFERRED]**

`REQ-CGA-018` — A code-derived `Transition` counts as an independent source for
an `AcceptanceCriterion` **only when** the `VALIDATES` edge was human-approved
(not judge-proposed alone), **and** the Transition carries a resolved
`code_anchor`, **and** the connectors differ.

`REQ-CGA-019` — Code corroboration MUST NOT be granted where
`source_state_unresolved = true`. A half-recovered transition is weaker evidence
than the guard text alone and must not be laundered into a corroboration count.

Both remain normative for the follow-on. Neither is available in v1.

## 13.11 Impact analysis and slicing

`metis_impact_analysis` currently matches changed file paths. With a CPG it
becomes real reachability:

- **Backward slice** from a changed `Method` → which `Endpoint`s and which
  `Transition`s it can affect → which `AcceptanceCriterion`s → which `TestCase`s
  must re-run.
- `joern-slice data-flow` and `joern-slice usages` emit JSON directly, designed
  for downstream ingestion.

`REQ-CGA-020` — Impact analysis MUST report reachability distance and the path,
not just a set — a `TestCase` 6 hops away is not the same finding as one directly
verifying the changed method, and reporting them identically is misleading.

## 13.12 Optional JVM complement — jQAssistant

If the onboarded estate is JVM-dominant, jQAssistant MAY be run **in addition**
for facts Joern gets to less directly: Maven module structure, Git history,
package/architecture dependency rules, JPA/XML descriptors. Its rules are Cypher
and it writes Neo4j natively.

`REQ-CGA-021` — If adopted, jQAssistant MUST write to its **own** database and
feed Métis through the same Episode/`submit_candidate()` contract as Joern
(§13.2). Its Neo4j-native convenience is not a licence to bypass the guardrails.

`REQ-CGA-022` — jQAssistant MUST NOT be used for `State`/`Transition` extraction.
It has no control-dependence analysis and therefore cannot recover a guard;
anything it produced for that purpose would be structurally unable to satisfy
`REQ-CGA-013`.

## 13.13 Disclosed limits of the static-only decision

Stated plainly, because these are the things that will surprise someone later:

| Limit | Consequence | Mitigation in this design |
|---|---|---|
| **Only explicitly-represented state is recoverable.** State encoded in row presence, spread across services, or held in a UI router will not be found | Whole classes of behaviour invisible | Configurable state-variable patterns; unmatched services report "no state machine found" honestly rather than emitting a degenerate one |
| **Counter-derived states will not appear.** Code has `attemptCount++` and `if (count >= 5)`; there is no `Failed1..Failed4` in the source | The v1 login example's own most important modelling fix is not auto-recoverable | Joern proposes the **guard** form; the ontology's existing rule (bounded, enumerable, durable → promote to `State`; continuous/combinatorial → keep as guard) governs whether a human unfolds it. Explicit division of labour, not a gap |
| **Joern's data flow is not sound.** False and missed edges both occur | Wrong transitions can be proposed | Everything lands at Quarantine; nothing auto-writes; `REQ-CGA-014` forbids guessed source states |
| **No frequency or liveness data.** Static analysis cannot say a transition never fires in production | Test prioritisation loses a strong signal | Accepted. `TestExecution` data gives a partial substitute for exercised paths |
| **Absence of a transition is not evidence of absence** of the behaviour | An AC with no match may be unimplemented *or* implemented in a way the extractor cannot see | `REQ-CGA-017` reports it as a finding for human triage, never as a proven gap |
| **Frontend maturity varies.** Java/JS/Python are mature; Go/Ruby are newer | Extraction quality is language-dependent | Per-language pilot gate (§13.14); quality measured, not assumed |

## 13.14 Pilot gate — mandatory before production adoption

### v1 gate (Layers 1–3)

`REQ-CGA-023` — Before the code-analysis connector may write to a production
graph, it MUST pass a pilot against **one real Java service**:

| # | Criterion | Target |
|---|---|---|
| 1 | Structural extraction (`Class`/`Method`/`CALLS`/`IMPORTS`/`INHERITS`) vs. v1 `cognify/` output on the same repository | **strict superset**, zero regressions |
| 2 | Cross-file call resolution — calls v1's bounded resolver could not resolve | **materially non-zero**; this is the whole reason for the change |
| 3 | External stubs materialised as Métis nodes | **exactly zero** (`REQ-CGA-010`) |
| 4 | Endpoint discovery vs. the checked-in contract | **≥ 0.9** agreement, every discrepancy explained rather than tolerated |
| 5 | Verified type/member registry — fields resolvable for the DTOs used by existing tests | **100%**; any gap disables generation for that type rather than warning (`REQ-TST-008`) |
| 6 | Partial-parse detection — a deliberately broken source file fails the job | **exact**; a partially parsed repository must never emit a report (§13.3) |
| 7 | Whole-pipeline run lands only at Quarantine; no auto-write occurs | **exact** |
| 8 | Re-running against the same `commit_sha` produces zero duplicate nodes | **exact** |

Criterion 2 is the one that justifies the work. If Joern's resolution is not
materially better than v1's `self.foo()`-and-bare-name resolver, the change buys
multi-language support and little else — which would be worth knowing before the
port, not after.

### Follow-on gate (Layers 4–5)  **[DEFERRED]**

Retained verbatim for when Layers 4–5 are funded. Measured against a
hand-modelled ground-truth state machine on a service with an explicit status enum:

| # | Criterion | Target |
|---|---|---|
| 1 | States recovered vs. ground truth | **recall ≥ 0.8** |
| 2 | Transitions recovered vs. ground truth | **recall ≥ 0.7** |
| 3 | Proposed transitions that are spurious | **precision ≥ 0.8** |
| 4 | Guards recovered verbatim and correctly attributed | **≥ 0.9** of recovered transitions |
| 5 | Source states resolved | **≥ 0.6** |

If these fail on a Java estate, the escalation is **SootUp + IFDS** (§13.1) — not
a loosening of the thresholds.

## 13.15 Requirements index

`REQ-CGA-001` … `REQ-CGA-023` above are consolidated into
[11 — Requirements Catalogue](11-requirements-catalogue.md) under area **CGA**.

## 13.16 Consequential edits to other documents

| Document | Edit required |
|---|---|
| [01 §1.5](01-vision-and-scope.md) | Corroboration paragraph: static code analysis is now the **primary** independent corroborating source; tighten per `REQ-CGA-018`/`019` |
| [01 §1.6](01-vision-and-scope.md) | Add dynamic behaviour extraction (process mining, automata learning) to explicit out-of-scope, with the §13.13 cost table referenced |
| [03](03-ontology-and-graph-schema.md) | Four new properties (§13.8); no new labels or relationship types |
| [05](05-jira-intake-and-mining.md) | `code-analysis` is a *non-intake* connector — it may never write `Requirement`/`AcceptanceCriterion`/`Intent`/`BusinessRule` (§01.5's table already states this) |
| [06](06-guardrails-quality-governance.md) | Layer 4 corroboration semantics; DQ-024 becomes computable; new finding type `AcceptanceCriterionUnimplemented` |
| [08](08-behaviour-test-design-and-generation.md) | Verified type/member registry replaces `code-explorer`; `REQ-CGA-012` becomes a generation-stage gate |
| [10](10-nfr-security-deployment.md) | JVM runtime + heap sizing for the ingestion worker; CPG artifact storage and retention |
