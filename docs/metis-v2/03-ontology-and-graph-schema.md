# 03 — Ontology & Graph Schema

**This document is authoritative for what may exist in the graph.** It is not a
description written after the fact — it is the source every schema change is
checked against.

## 3.1 The four-place governance rule

A node label or relationship type is legal only when it exists in **all four** of
the following, and none is sufficient alone:

| # | Place | What it holds |
|---|---|---|
| 1 | `schema/metis-graph-01-baseline-constraints.cypher` | Uniqueness + existence constraints, lifecycle/temporal indexes for the label |
| 2 | `schema/metis-graph-02-entity-specific-constraints.cypher` | Entity-specific constraints; the relationship-property index for a new edge type |
| 3 | `metis_mcp/structural_validation.py` | `KNOWN_LABELS` (the label) and `ALLOWED_RELATIONSHIPS` (the `(from_label, rel_type, to_label)` triple) |
| 4 | **This document** | A row in the relevant layer table, or in the Relationship Catalogue |

`REQ-ONT-001` — A label or edge present in only three of the four is a **bug in
whichever one is missing**, not a variant reading of the ontology. CI MUST include
a test that fails when the four disagree, and that test MUST fail if any one of
the four is edited alone.

`REQ-ONT-002` — `structural_validation.py`'s `validate()` (node label + required
properties) and `validate_relationship()` (edge triples) are the **enforcement**
side of this document. A candidate that does not match what is written here is
**rejected — never auto-created to make the rule fit the data.**

`REQ-ONT-003` — The ontology is **closed**. Adding a label or relationship type is
a reviewed change touching all four places. There is no dynamic or
inferred-at-runtime label creation.

## 3.2 Baseline property contract

Every candidate node of every label requires these three:

| Property | Meaning |
|---|---|
| `id` | Globally unique, **content-derived** (§04.6), never sequence-derived |
| `source_episode_id` | The `Episode` justifying this node's existence. **Schema-enforced, no exceptions** (P1) |
| `name` | Readable display data. **Not an identity key** |

Additionally, every node that can be AI-extracted carries:

| Property | Values |
|---|---|
| `lifecycle_state` | `Draft` \| `Reviewed` \| `Approved` \| `Deprecated` \| `Disputed` \| `Rejected` |
| `confidence_tier` | `auto_write` \| `quarantine` \| `rejected` |
| `t_valid` / `t_invalid` | Bi-temporal validity window (§04) |
| `corroboration_count` | Integer, on high-risk labels (§06.4) |

`REQ-ONT-004` — No entity may exist without at least one `source_episode_id`.
This is a **hard schema constraint**, not a convention.

## 3.3 Backbone layer

The hub: everything traces back to an `Intent`; everything testing real behaviour
routes through a `TestDesign`.

| Label | Purpose | Required properties | Allowed outgoing |
|---|---|---|---|
| `Intent` | The atomic, informal "what should happen" statement | `text` | *(target only)* |
| `TestDesign` | One per `Intent`: names the test-design technique(s), covers that Intent's ACs, produces the resulting TestCases | `techniques` | `TRACES_TO`→`Intent`, `COVERS`→`AcceptanceCriterion`, `PRODUCES`→`TestCase` |

## 3.4 Business layer

| Label | Purpose | Required properties | Allowed outgoing |
|---|---|---|---|
| `Goal` | One business objective / service domain | `domain` | *(target only)* |
| `Capability` | A capability delivering toward a Goal | — | `TRACES_TO`→`Goal` |
| `Epic` | A body of work within a Capability | — | `TRACES_TO`→`Capability` |
| `Feature` | A shippable slice of an Epic | — | `TRACES_TO`→`Epic` |
| `Requirement` | One EARS-conformant requirement statement, always re-validated by the checker, never force-tagged | `ears_pattern`, `revision`, `corroboration_count` | `TRACES_TO`→`Feature`\|`Intent`\|`Release`, `HAS_AC`→`AcceptanceCriterion` |
| `AcceptanceCriterion` | One atomic, testable condition belonging to exactly one Requirement; the bridge from backbone to concrete behaviour | `revision` | `TRACES_TO`→`Intent`, `VALIDATES`→`Transition` |
| `BusinessRule` | A standalone rule not expressed as a Requirement | `corroboration_count` | *(target only)* |
| `MicroRequirement` | A Requirement decomposed into a smaller independently-testable unit | — | *(target only)* |
| `JiraItem` | The evidence anchor for one real Jira issue. **Site-qualified** `jira_key` so it stays globally unique across Atlassian sites. Exists and stays queryable even when its Requirement is rejected or quarantined | `jira_key`, `issue_type` | `REPRESENTS`→`Requirement`\|`Defect`, `HAS_AC`→`AcceptanceCriterion`, `LINKS_TO`→`JiraItem` |

`REQ-ONT-005` — **A `TestCase` never `VERIFIES` a `Requirement` directly.**
Traceability MUST route through an `AcceptanceCriterion`. A `Requirement`
verified with no `HAS_AC` hop is the exact anti-pattern the circular-traceability
heuristic (DQ-018) flags.

`REQ-ONT-006` — Writes to `Intent`, `Requirement`, `AcceptanceCriterion` and
`BusinessRule` MUST be rejected when the originating `Episode.source_connector`
is not `jira` (§01.5, `REQ-INT-001`). `JiraItem` is by definition Jira-only.

## 3.5 Behaviour layer

Models real application state-machine behaviour. **Scoped strictly to actual
application behaviour** — never a stand-in for a generic business workflow or
approval process.

| Label | Purpose | Required properties | Allowed outgoing |
|---|---|---|---|
| `State` | One discrete state a real application can be in (`LoggedOut`, `AccountLocked`) | — | `WHEN`→`Transition` |
| `Transition` | One real state change. `trigger` and `guard_expression` are **properties**, not nodes — they have no existence apart from the single transition they belong to | `trigger`, `guard_expression`, `implementation_status` | `THEN`→`State` |

### `WHEN` / `THEN`

`State-[:WHEN]->Transition-[:THEN]->State` reads as one continuous forward path
and mirrors the Given/When/Then shape a Transition already structurally is: the
source State is the implicit **Given** (already true), `WHEN` this edge is
traversed the Transition fires, `THEN` its target State is the result.

### Trigger and Guard are not labels

A trigger event and its guard condition exist only in the context of exactly one
Transition. `guard_expression` is what differentiates real branches out of one
State — from `LoggedOut`, one Transition fires on
`credentials_valid AND NOT account_locked`, another on
`NOT credentials_valid AND attempt_count < 5` — three real branches, three
Transitions, one guard property each, not three pointers to a shared node.
Determinism and completeness checks compare these **by value** across Transitions
sharing a `WHEN` source State, never by shared node identity.

### When a condition should become a State

| Promote to `State` | Keep as `guard_expression` |
|---|---|
| Bounded, enumerable, durable (a capped retry counter) | Continuous/unbounded (elapsed time) |
| | Per-request, evaluated fresh each time (credential validity) |
| | Combinatorial (`A OR B`) — unfolding multiplies without adding clarity |

### `implementation_status`

`implemented` \| `planned`. A `planned` Transition is correctly **excluded from
coverage-gap computation** (it is not a gap; it does not exist yet) and has no
live graph path to any Intent/Requirement until it is actually validated.

### v2 additions for static extraction (§13.8)

| Property | Values | Purpose |
|---|---|---|
| `Transition.extraction_method` | `hand_authored` \| `static_analysis` | Provenance of the model itself |
| `Transition.code_anchor` | `repo:path:line` | Required for statically-extracted transitions (`REQ-CGA-013`) |
| `Transition.source_state_unresolved` | boolean | Set when step 6 could not determine a source state. **Blocks corroboration** (`REQ-CGA-019`) |
| `State.state_variable` | fully-qualified field/enum | Which variable this state belongs to |

**No new labels and no new relationship types** are introduced by static
extraction — a deliberate constraint on §13's design.

## 3.6 Testing layer

| Label | Purpose | Required properties | Allowed outgoing |
|---|---|---|---|
| `TestCase` | One real test at one of 6 levels (`unit`\|`integration`\|`api_functional`\|`web_functional`\|`e2e`\|`performance`) | `type` | `VERIFIES`→`AcceptanceCriterion`, `VERIFIES`→`Endpoint` (performance/SLA only), `PART_OF`→`TestSuite` |
| `TestSuite` | A named collection of TestCases | — | *(target only)* |
| `TestCycle` | One execution batch/container. `run_type` ∈ `ci`\|`smoke`\|`nightly`\|`regression`. Per-case results live on `TestExecution`, never a flat property here | `run_type` | `PART_OF`→`TestSuite`, `TRACES_TO`→`Release` (regression only) |
| `TestExecution` | One result for exactly one TestCase in exactly one TestCycle. This is what makes "did this case pass in this run" answerable — a cycle-level flag never could | `executed_at`, `result` | `PART_OF`→`TestCycle`, `EXECUTES`→`TestCase`, `PRODUCES`→`Defect` (failed only), `RAN_AGAINST`→`ApplicationConfiguration` |
| `AutomationScript` | A real automation script backing a TestCase (path reference) | — | *(target only)* |
| `GeneratedTest` | An AI-proposed test skeleton's provenance, pending human confirmation. **Not** a log of LLM session activity | — | *(target only)* |

## 3.7 Architecture layer

| Label | Purpose | Required properties | Allowed outgoing |
|---|---|---|---|
| `Service` | A real deployed service/component | — | *(see gap note)* |
| `API` | A versioned API surface owned by a Service | — | *(see gap note)* |
| `Endpoint` | One real HTTP endpoint | — | target of `TestCase.VERIFIES`, `Repository.EXPOSES`, `ExternalAPISpec.DEFINES` |
| `Database` | A real database instance | — | `HAS`→`Table` |
| `Table` | A real table | — | *(target only)* |
| `Column` | A real column | — | *(target only)* |
| `KafkaTopic` | A real topic | — | *(none)* |
| `ExternalSystem` | A third-party integration point | — | *(none)* |
| `ExternalAPISpec` | A registered external OpenAPI/Swagger spec (`registry_source`) | `registry_source` | `DEFINES`→`Endpoint` |
| `ApplicationConfiguration` | A component-version snapshot — what was deployed when a TestExecution ran. Carries no version data itself; every version lives on its own edge | — | `INCLUDES_VERSION` (edge property `version`)→`Service` |

**Disclosed gap carried forward from v1:** `Service` and `API` currently have no
real outgoing relationships. v2 SHOULD close this in Phase 5 —
`Service-[:EXPOSES]->API-[:HAS_ENDPOINT]->Endpoint` is the natural shape, and
Joern's endpoint discovery (§13.6) is what makes it populatable with real data
rather than inferred. **Not silently implied fixed here** — it is a Phase 5 work
package, and if it is not done the gap remains and must stay documented.

## 3.8 Implementation layer

| Label | Purpose | Allowed outgoing |
|---|---|---|
| `Repository` | One code repository | `DEFINES`→`Class`, `EXPOSES`→`Endpoint` |
| `Class` | One class, `repo:path:name`-keyed | `HAS_METHOD`→`Method`, `IMPORTS`→`Class`, `INHERITS`→`Class` |
| `Method` | One method/function, `repo:path:name.method`-keyed | `CALLS`→`Method`, `IMPLEMENTS`→`Requirement` |
| `PullRequest` | A real pull request | `PRODUCES`→`Commit` |
| `Commit` | A real commit with exact Jira keys and changed paths | `REFERENCES`→`Requirement`\|`JiraItem`\|`AcceptanceCriterion`, `MODIFIES`→`Method` |
| `Branch` | A real branch | *(none)* |

`REQ-ONT-007` — An edge MUST NOT be written when its target is external to the
analysed repository set. Joern models external callees as stubs with
`isExternal = true`; these MUST be filtered, never materialised (`REQ-CGA-010`).

## 3.9 Operations, Governance and Meta layers

| Label | Layer | Purpose | Allowed outgoing |
|---|---|---|---|
| `Release` | Operations | A shipped release/version | *(target only)* |
| `Defect` | Operations | A real defect, with `severity`/`jira_status` | *(target only)* |
| `Incident` | Operations | A production incident | *(none)* |
| `Alert` | Operations | A monitoring alert | *(none)* |
| `Metrics` | Operations | A metrics snapshot — **aggregates only** | *(none)* |
| `Logs` | Operations | A log excerpt | *(none)* |
| `Constitution` | Governance | One parsed rule from the project's Constitution corpus | *(target only)* |
| `Constraint` | Governance | A standalone constraint | *(none)* |
| `Episode` | Meta | The provenance record for every ingested unit. Every other node's `source_episode_id` points at one of these | `DIRECTLY_LINKS_TO`→`Episode` |
| `Revision` | Meta | One point-in-time snapshot of a node's properties | *(target only)* |

`REQ-ONT-008` — `Metrics` nodes MUST store **aggregates only**, with a reference
back to the source system for drill-down. Raw high-volume execution rows
(1M+/month scale) are **never duplicated into the graph**.

**Why there is no `CopilotSession`/`Prompt`/`GeneratedCode`/`AIDecision`/
`HumanReview` label:** these were a speculative "AI layer" in v1 and were removed
by explicit decision — keeping ephemeral LLM/session data in a graph meant to be a
persistent source of truth is counterproductive. `GeneratedTest` is *not* part of
that removal: it tracks durable provenance (an AI-proposed test pending human
confirmation), not a session log.

## 3.10 Cross-cutting: `functional_areas`

An optional **string-array** property on `Intent`, `Requirement`,
`AcceptanceCriterion`, `TestDesign`, `TestCase`, `State` and `Transition` — the
whole backbone + behaviour chain one real scenario touches.

```cypher
MATCH (t:Transition) WHERE 'login' IN t.functional_areas RETURN t
MATCH (n) WHERE 'login-successful' IN n.functional_areas RETURN n
```

Array-valued because one node genuinely belongs to more than one area at once
(`login` the coarse area, `login-failed` the sub-flow).

`REQ-ONT-009` — A `State` shared across multiple Transitions MUST carry the
**union** of every touching Transition's tags, computed once and set once — never
per-transition, which would silently keep only the last writer's tags.

**Property, not a node, by design:** a lightweight classification with no
description, owner or sub-structure. If a functional area later needs its own
metadata or a queryable "list every area", promoting it to a `FunctionalArea`
node is the natural escalation — not built preemptively.

## 3.11 Relationship Catalogue

This table **is** `structural_validation.py`'s `ALLOWED_RELATIONSHIPS`. A
mismatch is a bug in whichever is stale.

| From | Relationship | To | Meaning |
|---|---|---|---|
| `Capability` | `TRACES_TO` | `Goal` | Backlog hierarchy |
| `Epic` | `TRACES_TO` | `Capability` | Backlog hierarchy |
| `Feature` | `TRACES_TO` | `Epic` | Backlog hierarchy |
| `Requirement` | `TRACES_TO` | `Feature` | Backlog hierarchy |
| `Requirement` | `TRACES_TO` | `Intent` | This Requirement formalises this Intent |
| `Requirement` | `TRACES_TO` | `Release` | Shipped in this Release |
| `Requirement` | `HAS_AC` | `AcceptanceCriterion` | Atomic testable conditions |
| `AcceptanceCriterion` | `TRACES_TO` | `Intent` | Directly traceable to its Intent |
| `AcceptanceCriterion` | `VALIDATES` | `Transition` | Validates this concrete behaviour |
| `TestDesign` | `TRACES_TO` | `Intent` | This design targets this Intent |
| `TestDesign` | `COVERS` | `AcceptanceCriterion` | Design covers this AC |
| `TestDesign` | `PRODUCES` | `TestCase` | Design produced this TestCase |
| `TestCase` | `VERIFIES` | `AcceptanceCriterion` | Functional coverage |
| `TestCase` | `VERIFIES` | `Endpoint` | Performance/SLA coverage only |
| `TestCase` | `PART_OF` | `TestSuite` | Suite membership |
| `TestCycle` | `PART_OF` | `TestSuite` | Which suite this cycle executed |
| `TestCycle` | `TRACES_TO` | `Release` | Regression cycles only |
| `TestExecution` | `PART_OF` | `TestCycle` | Cycle membership |
| `TestExecution` | `EXECUTES` | `TestCase` | Which case ran |
| `TestExecution` | `PRODUCES` | `Defect` | Failed executions only |
| `TestExecution` | `RAN_AGAINST` | `ApplicationConfiguration` | Which version snapshot |
| `ApplicationConfiguration` | `INCLUDES_VERSION` | `Service` | Edge property `version` |
| `State` | `WHEN` | `Transition` | Source state / implicit Given |
| `Transition` | `THEN` | `State` | Resulting target state |
| `Database` | `HAS` | `Table` | Architecture |
| `Repository` | `DEFINES` | `Class` | Code structure |
| `Repository` | `EXPOSES` | `Endpoint` | Which repo defines this endpoint |
| `Class` | `HAS_METHOD` | `Method` | Code structure |
| `Class` | `IMPORTS` | `Class` | Code structure |
| `Class` | `INHERITS` | `Class` | Code structure |
| `Method` | `CALLS` | `Method` | Code structure |
| `Method` | `IMPLEMENTS` | `Requirement` | Which Requirement this method implements |
| `PullRequest` | `PRODUCES` | `Commit` | VCS |
| `Commit` | `REFERENCES` | `Requirement` | Commit names this Jira key |
| `Commit` | `REFERENCES` | `JiraItem` | Exact commit-to-ticket evidence |
| `Commit` | `REFERENCES` | `AcceptanceCriterion` | `evidence_status` on the edge distinguishes explicit AC reference from ticket-scope association |
| `Commit` | `MODIFIES` | `Method` | Commit changed the file containing this Method |
| `ExternalAPISpec` | `DEFINES` | `Endpoint` | Which external spec documents this endpoint |
| `JiraItem` | `REPRESENTS` | `Requirement` | System-of-record source |
| `JiraItem` | `REPRESENTS` | `Defect` | System-of-record source |
| `JiraItem` | `HAS_AC` | `AcceptanceCriterion` | This issue's own AC evidence (distinct from `Requirement.HAS_AC`, the normalised ownership edge) |
| `JiraItem` | `LINKS_TO` | `JiraItem` | Real Jira parent/subtask/issuelink |
| `Episode` | `DIRECTLY_LINKS_TO` | `Episode` | Source-system direct link; **provenance only, not requirement traceability** |
| *(any label)* | `HAS_REVISION` | `Revision` | The one relationship type intentionally **not** scoped to a fixed from-label — every label can have revision history |

`REQ-ONT-010` — `HAS_REVISION` MUST be written **only** by the temporal module's
`record_revision()`. No connector or generator writes it directly.

## 3.12 Schema file structure

| File | Content | Generation |
|---|---|---|
| `metis-graph-01-baseline-constraints.cypher` | Per label: `id` uniqueness, `source_episode_id` existence, indexes on `lifecycle_state`, `t_valid`, `t_invalid` | **Auto-generated** from the label list. Never hand-edited |
| `metis-graph-02-entity-specific-constraints.cypher` | Judgement calls: EARS/revision existence, `confidence_tier` indexes, `corroboration_count`, relationship-property indexes per edge type, vector and full-text indexes | Hand-written |
| `metis-graph-03-episode-and-operational.cypher` | Episode log, idempotency, checkpointing, cost tracking, RBAC scoping | Hand-written |

Representative shapes:

```cypher
-- 01: mechanical, per label
CREATE CONSTRAINT requirement_id_unique IF NOT EXISTS
  FOR (n:Requirement) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT requirement_source_episode_required IF NOT EXISTS
  FOR (n:Requirement) REQUIRE n.source_episode_id IS NOT NULL;
CREATE INDEX requirement_lifecycle_state IF NOT EXISTS
  FOR (n:Requirement) ON (n.lifecycle_state);

-- 02: judgement calls
CREATE CONSTRAINT requirement_ears_pattern IF NOT EXISTS
  FOR (r:Requirement) REQUIRE r.ears_pattern IS NOT NULL;
CREATE INDEX rel_when_t_valid IF NOT EXISTS
  FOR ()-[r:WHEN]-() ON (r.t_valid);

-- 03: idempotency, the single most important operational constraint
CREATE CONSTRAINT episode_unit_id_per_connector IF NOT EXISTS
  FOR (e:Episode) REQUIRE (e.source_connector, e.unit_id) IS UNIQUE;
```

`REQ-ONT-011` — Every relationship type in the catalogue MUST have a
relationship-property index on `t_valid`. (v1 discovered mid-build that two edge
types had never had one — an oversight, not a decision.)

`REQ-ONT-012` — A Neo4j property-existence constraint cannot express enum
membership. Where a property is enum-valued (`ears_pattern`, `implementation_status`,
`lifecycle_state`, `confidence_tier`, `run_type`, `TestCase.type`), the constraint
guarantees **presence** and the application-layer gate enforces **membership**.
Both are required; neither substitutes for the other.

## 3.13 Vector and full-text indexes

HNSW vector indexes and full-text indexes are created for the four labels that
carry substantive prose (`Requirement`, `AcceptanceCriterion`, `Intent`,
`Episode`).

`REQ-ONT-013` — The vector indexes exist and the semantic query path is
implemented, but it **MUST refuse to run** until an embedding pipeline populates
`embedding` properties. It MUST NOT silently fall back to keyword search — a
retrieval mode that quietly substitutes another is a P5 violation (§01.6).

## 3.14 One documented exception

A TestCase may be linked to whatever real, already-existing entity its module
docstring cites by tag (e.g. a `Constitution` rule id) via
`TestCase-[:VERIFIES]->(target)` with **no fixed target label**. Validity is
enforced by real tag-existence at write time, not by a closed target-label list,
because this is a **citation** mechanism, not a structural design relationship.

`REQ-ONT-014` — `validate_relationship()` MUST NOT attempt to police this call
site's target label, and this exception MUST remain documented here so it is not
mistaken for an unenforced hole.

## 3.15 Governance in practice

**Adding a label:** write its 01 constraint block → add to `KNOWN_LABELS` → add
its row to the relevant layer table here.
**Adding a relationship:** write its 02 index → add the triple to
`ALLOWED_RELATIONSHIPS` → add its row to the Relationship Catalogue.

All places, every time. The automated half (`validate()` /
`validate_relationship()`) and the human-readable half (this document) are not
optional cover for each other.
