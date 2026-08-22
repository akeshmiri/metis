> **SUPERSEDED — historical record, not the current design.**
>
> This describes the v1 ontology: 45 labels, `structural_validation.py`'s
> `ALLOWED_RELATIONSHIPS`, and the `schema/metis-graph-0*.cypher` files beside
> it in `docs/historical/schema-v1/`. All of that was removed when the engine was
> rebuilt.
>
> **The current ontology is 24 labels**, defined in
> `metis-server/metis_mcp/ontology/labels.py`, which is also the single source
> the Cypher schema is *generated* from (`metis-server/schema/metis2-*.cypher`,
> written by `ontology/schema.py`). The authoritative prose is
> `docs/metis-application-spec.md` §8.
>
> Kept because it is the only written record of why several v1 decisions were
> made — the Trigger/Guard fold-in, the `WHEN`/`THEN` naming, the
> `VERIFIES`→`AcceptanceCriterion` rule — and those reasons still inform the
> current design even where the shape changed.

---

# Métis Ontology Specification

**This is the authoritative, living reference for what may exist in the
graph.** It is not a description written after the fact — it is the
source every schema change is checked against, in this order, together,
every time:

1. `schema/metis-graph-01-entity-baseline-constraints.cypher` — the
   uniqueness/existence constraint block for the label.
2. `schema/metis-graph-02-entity-specific-constraints.cypher` — the
   relationship-property index for the edge type, if new.
3. `metis_mcp/structural_validation.py` — `KNOWN_LABELS` (the label) and
   `ALLOWED_RELATIONSHIPS` (the `(from_label, rel_type, to_label)` triple).
4. **This document** — a row in the relevant layer table (label) or the
   Relationship Catalog (edge).

None of these four is optional, and none is sufficient alone. A label or
edge that exists in only three of the four is a bug in whichever one is
missing, not a variant reading of the ontology. `structural_validation.py`'s
`StructuralValidator.validate()` (Layer 2, node label + required
properties) and `validate_relationship()` (edge triples) are the
**enforcement** side of this document — a candidate that doesn't match
what's written here is rejected, never auto-created to make the rule fit
the data (REQ-METIS-GRD-02's own long-standing discipline, now extended
from nodes to relationships).

**Do not add a node label or a relationship type without updating all
four of the above.** If you're unsure whether something is allowed,
check here first — this document, not tribal knowledge or a prior
session's comment, is the answer.

## How to read the tables

Each layer table has one row per label:

| Column | Meaning |
|---|---|
| Label | The exact Neo4j node label. |
| Purpose | What real-world thing this node represents, one sentence. |
| Required properties | Beyond `id`/`source_episode_id`/`name` (every candidate label requires these three — see `BASELINE_REQUIRED`; `name` is readable display data, not a unique identity key). |
| Allowed outgoing relationships | Every `-[:REL]->(Label)` this label is permitted to have, per the Relationship Catalog below. |

An empty "Allowed outgoing relationships" cell means the label is only
ever a *target*, never a *source*, anywhere in the real ontology today.

---

## Backbone layer

The real hub: everything else in the ontology ultimately traces back to
an `Intent`, and everything that tests real behavior ultimately routes
through a `TestDesign`.

| Label | Purpose | Required properties | Allowed outgoing relationships |
|---|---|---|---|
| `Intent` | The atomic, informal "what should happen" statement — the hub `Requirement`/`AcceptanceCriterion`/`TestDesign` all trace back to. | `text` | *(none — only ever a target)* |
| `TestDesign` | One per `Intent`: names the real test-design technique(s) used, covers that Intent's `AcceptanceCriterion`(s), and produces the `TestCase`(s) that result. | `techniques` | `TRACES_TO`→`Intent`, `COVERS`→`AcceptanceCriterion`, `PRODUCES`→`TestCase` |

## Behavior layer

Models real application state-machine behavior — a login page, a
checkout flow, anything with discrete states and transitions between
them. **Scoped strictly to actual application behavior** — never used as
a stand-in for a generic business workflow or approval process (Session
11's own correction: a prior synthetic "Behavior layer" that wired 80
generic States into a meaningless index ring was removed for exactly
this reason).

| Label | Purpose | Required properties | Allowed outgoing relationships |
|---|---|---|---|
| `State` | One discrete state a real application can be in (e.g. `LoggedOut`, `AccountLocked`). | — | `WHEN`→`Transition` |
| `Transition` | One real state change: `trigger` (the event that causes it) and `guard_expression` (the condition that must hold) are properties of the Transition itself, not separate nodes — a trigger/guard has no existence apart from the one transition it belongs to. `implementation_status` (`'implemented'`\|`'planned'`) distinguishes already-built behavior from specified-but-not-yet-built behavior — a `planned` Transition is correctly excluded from coverage-gap computation (it isn't a gap; it doesn't exist yet) and has no live graph path to any `Intent`/`Requirement` until it's actually validated (see `AcceptanceCriterion.VALIDATES` below). | `trigger`, `guard_expression`, `implementation_status` | `THEN`→`State` |

**`WHEN`/`THEN` (renamed from `FROM_STATE`/`TO_STATE`, then
`LAUNCHES`/`LANDS_IN`)**: reads as one continuous forward path —
`State-[:WHEN]->Transition-[:THEN]->State` — rather than two edges both
originating at the Transition. Mirrors the Given/When/Then shape a
Transition already structurally is: the State it's reached from is the
implicit "Given" (it's already true before anything fires), `WHEN` this
edge is traversed the Transition fires, `THEN` this edge's target State
is the result.

**Trigger and Guard are not node labels.** They were removed as separate
entities: a trigger event and its guard condition exist only in the
context of exactly one Transition, so they're the `trigger`/
`guard_expression` properties on that Transition, not their own nodes
with an independent identity. `guard_expression` is what differentiates
the real branches out of one State — e.g. from `LoggedOut`, one
Transition fires when `credentials_valid AND NOT account_locked`,
another when `NOT credentials_valid AND attempt_count < 5`, a third when
`NOT credentials_valid AND attempt_count >= 5` — three real branches,
three real Transitions, one guard property each, not three pointers to a
shared node. `metis_mcp/behavior_model.py`'s determinism/completeness
checks (CONST-048/049) compare these properties by value across
Transitions sharing a `WHEN` source State, not by shared node
identity.

**Guard atomicity AND completeness, not just atomicity**:
`check_determinism()`'s `guards_conflict()` checks that guards on a
shared `(State, trigger)` don't overlap (atomic). A real, requested
extension, `check_guard_completeness()`, checks the complementary
property: that a shared `(State, trigger)`'s guards jointly cover the
*whole* meaningful domain, not just that they don't overlap — a real
input matching none of them would silently match no transition at all.
Same fail-closed discipline as `guards_conflict()`: an unparseable guard,
or guards on different variables, is flagged as unverifiable, never
assumed complete. Not every condition should become an explicit State,
though — only bounded, enumerable, durable ones (e.g. a capped retry
counter). Continuous/unbounded conditions (elapsed time), per-request
conditions evaluated fresh each time (credential validity), or
combinatorial ones (`A OR B`) stay real guards — unfolding those into
states would either be infinite or multiply combinatorially without
adding real clarity.

**Coverage guardrail (DQ-024, `metis_mcp/layer8_heuristics.py`'s
`check_transition_ac_coverage`)**: every `implemented` Transition must
have at least one `AcceptanceCriterion-[:VALIDATES]->` edge — real
behavior with nothing validating it is an unverified claim, not a
covered one. `planned` Transitions are excluded (nothing to validate yet
is correct, not a gap). This traceability edge, not `State`/`Event`
alone, is what has to carry the claim: an `AcceptanceCriterion` validates
the whole `(source State, trigger, guard, target State)` scenario a
Transition represents — validating just the target State would hide
exactly the kind of gap explicit states were introduced to catch (e.g.
`Failed1`-`Failed4`→`LoggedIn` all share a target State; validating the
State alone would make all four look covered by testing just one).

## Cross-cutting: `functional_areas`

An optional string-array property, real and requested, available on
`Intent`, `Requirement`, `AcceptanceCriterion`, `TestDesign`, `TestCase`,
`State`, and `Transition` — the whole backbone + behavior-model chain one
real scenario (e.g. `demo_data/login_example.py`) touches. Lets a
one-line query pull everything belonging to a named functional area,
without a new node type or relationship:

```cypher
MATCH (t:Transition) WHERE 'login' IN t.functional_areas RETURN t
MATCH (n) WHERE 'login-successful' IN n.functional_areas RETURN n
```

Array-valued because one node can genuinely belong to more than one area
at once — e.g. `t3-lockout` is both `"login"` (the coarse area) and
`"login-failed"` (the specific sub-flow). A `State` shared across
multiple Transitions (e.g. `LoggedOut`, touched by `t1`/`t2a`/`t4`/`t7`/
`t8`) gets the real *union* of every Transition's tags that touches it,
not just whichever one happened to write last.

**Property, not a node, by design**: this is a lightweight
classification, not a rich, independently-referenceable entity (no
description, no owner, no sub-structure) — matching this project's
existing precedent for domain/category tagging (`Goal.domain` is a plain
property, not a node). If a functional area later needs its own metadata
or a queryable "list every area that exists," promoting it to a real
`FunctionalArea` node is the natural escalation — not something built
preemptively here.

## Business layer

The requirements hierarchy — real, human-authored specification content,
not code or tests.

| Label | Purpose | Required properties | Allowed outgoing relationships |
|---|---|---|---|
| `Goal` | Top of the backlog hierarchy — one per real business objective/service domain. | `domain` | *(none — only ever a target)* |
| `Capability` | A capability delivering toward a Goal. | — | `TRACES_TO`→`Goal` |
| `Epic` | A body of work within a Capability. | — | `TRACES_TO`→`Capability` |
| `Feature` | A shippable slice of an Epic. | — | `TRACES_TO`→`Epic` |
| `Requirement` | One real, EARS-conformant requirement statement — always re-validated through `metis_mcp/ears_checker.py`, never force-tagged. | `ears_pattern`, `revision`, `corroboration_count` | `TRACES_TO`→`Feature`, `TRACES_TO`→`Intent`, `TRACES_TO`→`Release`, `HAS_AC`→`AcceptanceCriterion` |
| `AcceptanceCriterion` | One atomic, testable condition belonging to exactly one Requirement — also the real bridge from the backbone to concrete behavior. | `revision` | `TRACES_TO`→`Intent`, `VALIDATES`→`Transition` |
| `BusinessRule` | A standalone business rule not expressed as a Requirement. | `corroboration_count` | *(none — only ever a target)* |
| `MicroRequirement` | A Requirement decomposed into a smaller, independently-testable unit (Layer 6 LLM-as-judge output). | — | *(none — only ever a target)* |
| `JiraItem` | The explicit evidence anchor for one real Jira issue — site-qualified `jira_key` so it stays globally unique across Atlassian sites. Distinct from a normalized `Requirement`/`Defect`: a `JiraItem` can exist (and stay queryable) even when its own Requirement is rejected or quarantined. | `jira_key`, `issue_type` | `REPRESENTS`→`Requirement`, `REPRESENTS`→`Defect`, `HAS_AC`→`AcceptanceCriterion`, `LINKS_TO`→`JiraItem` |

**A `TestCase` never `VERIFIES` a `Requirement` directly.**
`Requirement<-VERIFIES-TestCase` with no `HAS_AC` hop in between is the
exact anti-pattern `metis_mcp/layer8_heuristics.py`'s
`check_circular_traceability` (DQ-018) flags as suspicious — traceability
must always route through a real `AcceptanceCriterion`.

## Testing layer

| Label | Purpose | Required properties | Allowed outgoing relationships |
|---|---|---|---|
| `TestCase` | One real test, at one of 6 real levels (`unit`\|`integration`\|`api_functional`\|`web_functional`\|`e2e`\|`performance`). | `type` | `VERIFIES`→`AcceptanceCriterion`, `VERIFIES`→`Endpoint` (performance/SLA-target tests only), `PART_OF`→`TestSuite` |
| `TestSuite` | A named collection of TestCases. | — | *(none — only ever a target)* |
| `TestCycle` | One real execution batch/container (a "run") — `run_type` (`ci`\|`smoke`\|`nightly`\|`regression`) classifies it. Per-case results live on `TestExecution`, never a flat property on the cycle itself. | `run_type` | `PART_OF`→`TestSuite`, `TRACES_TO`→`Release` (regression cycles only) |
| `TestExecution` | One real result for exactly one TestCase within exactly one TestCycle — `executed_at`/`result` only. This is what makes "did this case pass in this run" answerable; a TestCycle-level flag never could, once a cycle covers more than one case. | `executed_at`, `result` | `PART_OF`→`TestCycle`, `EXECUTES`→`TestCase`, `PRODUCES`→`Defect` (failed executions only), `RAN_AGAINST`→`ApplicationConfiguration` |
| `AutomationScript` | A real automation script backing a TestCase (path-only reference). | — | *(none — only ever a target)* |
| `GeneratedTest` | An AI-proposed test skeleton's provenance, pending human confirmation/convergence with a real TestCase (REQ-METIS-BM-03). **Not** a log of LLM/Copilot session activity — see Meta layer for why that distinction matters. | — | *(none — only ever a target)* |

## Architecture layer

Real infrastructure components. **Disclosed, current gap**: `Service`,
`API`, and `Endpoint` carry no real outgoing relationships anywhere in
this codebase today (their `_service`/`_api` linking fields are computed
during generation but discarded before write) — `Database`/`Table` are
the only pair in this layer with a real edge between them. Not silently
implied fixed; a future session's job, not this one's.

| Label | Purpose | Required properties | Allowed outgoing relationships |
|---|---|---|---|
| `Service` | A real deployed service/component. | — | *(none today — disclosed gap above)* |
| `API` | A versioned API surface owned by a Service. | — | *(none today — disclosed gap above)* |
| `Endpoint` | One real HTTP endpoint of an API. | — | `TestCase.VERIFIES` targets it (performance/SLA tests); owned by exactly one `Repository` (`EXPOSES`) or `ExternalAPISpec` (`DEFINES`) |
| `Database` | A real database instance. | — | `HAS`→`Table` |
| `Table` | A real table within one Database. | — | *(none — only ever a target)* |
| `Column` | A real column within one Table. | — | *(none — only ever a target; `Table.HAS` doesn't yet extend to Column, same disclosed gap)* |
| `KafkaTopic` | A real Kafka topic. | — | *(none)* |
| `ExternalSystem` | A real third-party/external system integration point. | — | *(none)* |
| `ExternalAPISpec` | A real, registered external OpenAPI/Swagger specification (`registry_source` — e.g. `swaggerhub`\|`apis.guru`\|`internal-registry`), landed by `metis_mcp/atlas_bridge.py`'s swagger-ingestion path. | `registry_source` | `DEFINES`→`Endpoint` |
| `ApplicationConfiguration` | A real component-version snapshot — what was actually deployed when a TestExecution ran, for release-report generation. Carries no version data itself; every version lives on its own `INCLUDES_VERSION` edges. | — | `INCLUDES_VERSION` (with a `version` property)→`Service` |

## Implementation layer

Real source-code structure, from an actual (or demo-tagged "as if real")
AST-based Cognify pass.

| Label | Purpose | Required properties | Allowed outgoing relationships |
|---|---|---|---|
| `Repository` | One real code repository. | — | `DEFINES`→`Class`, `EXPOSES`→`Endpoint` (real REST endpoints discovered by `git-repository-analyzer`, landed via `metis_mcp/atlas_bridge.py`) |
| `Class` | One real class, `repo:path:name`-keyed. | — | `HAS_METHOD`→`Method`, `IMPORTS`→`Class`, `INHERITS`→`Class` |
| `Method` | One real method/function, `repo:path:name.method`-keyed. | — | `CALLS`→`Method`, `IMPLEMENTS`→`Requirement` |
| `PullRequest` | A real pull request. | — | `PRODUCES`→`Commit` |
| `Commit` | A real commit with exact Jira keys and changed source paths from commit-impact evidence. | — | `REFERENCES`→`Requirement`, `MODIFIES`→`Method` |
| `Branch` | A real branch. | — | *(none)* |

## Operations layer

| Label | Purpose | Required properties | Allowed outgoing relationships |
|---|---|---|---|
| `Release` | A real shipped release/version. | — | *(none — only ever a target)* |
| `Defect` | A real defect, with `severity`/`jira_status`. | — | *(none — only ever a target, of `TestExecution.PRODUCES`)* |
| `Incident` | A real production incident. | — | *(none)* |
| `Alert` | A real monitoring alert. | — | *(none)* |
| `Metrics` | A real metrics snapshot. | — | *(none)* |
| `Logs` | A real log excerpt. | — | *(none)* |

## Governance layer

| Label | Purpose | Required properties | Allowed outgoing relationships |
|---|---|---|---|
| `Constitution` | One real, parsed rule from the project's own Constitution corpus. | — | *(none — only ever a target of connector-level tag-citation `VERIFIES`, see Relationship Catalog note)* |
| `Constraint` | A real, standalone constraint. | — | *(none)* |

## Meta layer

| Label | Purpose | Required properties | Allowed outgoing relationships |
|---|---|---|---|
| `Episode` | The real provenance record for every ingested unit — `source_connector`, `t_recorded`, `job_id`. Every other node's `source_episode_id` points at one of these. | `t_recorded`, `source_connector`, `job_id` | `DIRECTLY_LINKS_TO`→`Episode` (source-system direct link only) |
| `Revision` | One real point-in-time snapshot of a node's properties, written by `metis_mcp/temporal.py`'s `record_revision()`. | — | *(none — only ever a target)* |

**Why there is no `CopilotSession`/`Prompt`/`GeneratedCode`/`AIDecision`/
`HumanReview` label**: these existed in an earlier session as a
speculative "AI layer" tracking Copilot/Claude session activity, and were
removed by explicit user decision — keeping ephemeral LLM/session data in
a graph meant to be a global, persistent source of truth is
counterproductive. `GeneratedTest` (Testing layer, above) is not part of
that removal — it tracks a real, durable provenance state (an AI-proposed
test pending human confirmation), not a session log.

---

## Relationship Catalog

Every `(FromLabel)-[:REL_TYPE]->(ToLabel)` triple that exists anywhere in
this codebase today. This table **is** `metis_mcp/
structural_validation.py`'s `ALLOWED_RELATIONSHIPS` — the two are kept in
sync manually; a mismatch between them is a bug in whichever one is
stale.

| From | Relationship | To | Meaning |
|---|---|---|---|
| `Capability` | `TRACES_TO` | `Goal` | Backlog hierarchy |
| `Epic` | `TRACES_TO` | `Capability` | Backlog hierarchy |
| `Feature` | `TRACES_TO` | `Epic` | Backlog hierarchy |
| `Requirement` | `TRACES_TO` | `Feature` | Backlog hierarchy |
| `Requirement` | `TRACES_TO` | `Intent` | Backbone: this Requirement formalizes this Intent |
| `Requirement` | `TRACES_TO` | `Release` | This (shipped) Requirement is included in this Release |
| `Requirement` | `HAS_AC` | `AcceptanceCriterion` | This Requirement's atomic testable conditions |
| `AcceptanceCriterion` | `TRACES_TO` | `Intent` | Backbone: this AC is also directly traceable to its Intent |
| `AcceptanceCriterion` | `VALIDATES` | `Transition` | This AC validates this concrete application behavior |
| `TestDesign` | `TRACES_TO` | `Intent` | Backbone: this design targets this Intent |
| `TestDesign` | `COVERS` | `AcceptanceCriterion` | This design covers this AC |
| `TestDesign` | `PRODUCES` | `TestCase` | This design produced this real TestCase |
| `TestCase` | `VERIFIES` | `AcceptanceCriterion` | Functional coverage |
| `TestCase` | `VERIFIES` | `Endpoint` | Performance/SLA coverage (`locust_performance_connector.py`) |
| `TestCase` | `PART_OF` | `TestSuite` | Suite membership |
| `TestCycle` | `PART_OF` | `TestSuite` | Which suite this cycle executed |
| `TestCycle` | `TRACES_TO` | `Release` | Regression cycles only — which release this cycle validated |
| `TestExecution` | `PART_OF` | `TestCycle` | Which cycle this execution belongs to |
| `TestExecution` | `EXECUTES` | `TestCase` | Which case this execution ran |
| `TestExecution` | `PRODUCES` | `Defect` | Failed executions only |
| `TestExecution` | `RAN_AGAINST` | `ApplicationConfiguration` | Which component-version snapshot this execution ran against |
| `ApplicationConfiguration` | `INCLUDES_VERSION` | `Service` | `version` property on the edge — this config's real component version |
| `Episode` | `DIRECTLY_LINKS_TO` | `Episode` | A direct source-system link (for example, a cached Jira `issuelink`); provenance only, not requirement traceability |
| `State` | `WHEN` | `Transition` | Behavior model — this State is the (implicit Given) precondition; WHEN this fires |
| `Transition` | `THEN` | `State` | Behavior model — THEN the Transition results in this target State |
| `Database` | `HAS` | `Table` | Architecture |
| `Repository` | `DEFINES` | `Class` | Code structure |
| `Class` | `HAS_METHOD` | `Method` | Code structure |
| `Class` | `IMPORTS` | `Class` | Code structure |
| `Class` | `INHERITS` | `Class` | Code structure |
| `Method` | `CALLS` | `Method` | Code structure |
| `Method` | `IMPLEMENTS` | `Requirement` | Which Requirement this real method implements |
| `PullRequest` | `PRODUCES` | `Commit` | VCS structure |
| `Commit` | `REFERENCES` | `Requirement` | The commit evidence names the Jira key carried by this Requirement |
| `Commit` | `MODIFIES` | `Method` | The commit changed the exact repository-qualified source file containing this Method |
| `Repository` | `EXPOSES` | `Endpoint` | Which repository's code defines this real REST endpoint (`atlas_bridge.py` repository-analysis ingestion) |
| `ExternalAPISpec` | `DEFINES` | `Endpoint` | Which external OpenAPI/Swagger spec documents this endpoint (`atlas_bridge.py` swagger ingestion) |
| `JiraItem` | `REPRESENTS` | `Requirement` | This Jira issue is the system-of-record source for this normalized Requirement |
| `JiraItem` | `REPRESENTS` | `Defect` | This Jira Bug/JSM request is the system-of-record source for this normalized Defect |
| `JiraItem` | `HAS_AC` | `AcceptanceCriterion` | This specific Jira issue's own AC evidence (distinct from `Requirement`-`HAS_AC`, the normalized ownership edge) |
| `JiraItem` | `LINKS_TO` | `JiraItem` | A real Jira parent/subtask/issuelink between two Jira issues |
| `Commit` | `REFERENCES` | `JiraItem` | Exact commit-to-ticket evidence, by normalized Jira key |
| `Commit` | `REFERENCES` | `AcceptanceCriterion` | Direct commit-to-AC evidence — `evidence_status` on the edge distinguishes an explicit AC reference from a ticket-scope association |
| *(any real label)* | `HAS_REVISION` | `Revision` | Generic, written only by `metis_mcp/temporal.py`'s `record_revision()` — the one relationship type intentionally NOT scoped to a fixed from-label, since every label can have revision history |

**One documented, intentional exception, not a gap**:
`connectors/test_suite_connector.py` links a TestCase to whatever real,
already-existing entity its module docstring cites by tag (e.g. a
`Constitution` rule id) via `TestCase-[:VERIFIES]->(target)` with no
fixed target label — validity is enforced by real tag-existence at write
time (`_known_tag_exists()`, REQ-METIS-CONN-04), not by a closed
target-label list, since this is a citation mechanism, not a structural
design relationship. `validate_relationship()` (Part 5) does not attempt
to police this specific call site's target label for that reason —
documented here so it isn't mistaken for an unenforced hole.

## Governance in practice

Adding a new label: write its schema-01 constraint block, add it to
`KNOWN_LABELS`, add its row above. Adding a new relationship: write its
schema-02 index, add the triple to `ALLOWED_RELATIONSHIPS`, add its row
to the Relationship Catalog. All three, every time — `metis_mcp/
structural_validation.py`'s own `validate()`/`validate_relationship()`
functions are the automated half of this discipline; this document, kept
current, is the human-readable half. Neither is optional cover for the
other.
