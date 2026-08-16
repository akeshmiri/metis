# 05 — Jira Intake & Requirement Mining

**The only requirement-intake source.** Everything that can create an `Intent`,
`Requirement`, `AcceptanceCriterion`, `BusinessRule` or `Defect` arrives through
this pipeline. Everything else (§01.5) is evidence, and is structurally barred
from creating those labels.

## 5.1 Pipeline overview

```
Jira REST API  ──┐
  issues        │   ① Extract        JiraExtractor
  changelog     │──────────────────► UIF document (schema-validated)
  comments      │                          │
  links         │   ② Land                 ▼
  attachments ──┘──────────────────► Episode (immutable, raw_content = prose)
                                           │
                    ③ Stage 1              ▼   deterministic, no model calls
                    segmentation ────► DIRECT | NEEDS_LLM | DISCARD
                                           │
                    ④ Stage 2              ▼   NEEDS_LLM only, cost-gated
                    extraction ───────► proposed Requirement + AC text
                                           │
                    ⑤ Stage 3              ▼   deterministic
                    verification ─────► EARS + vagueness + grounding ratio
                                           │
                    ⑥ Stage 4              ▼   pure planner, then thin writer
                    landing ──────────► LandingPlan → guardrail pipeline
                                           │
                                           ▼
                                    Quarantine (never auto-write)
```

`REQ-MIN-011` — Stage 2 never writes. **Stage 4 owns every write**, so there is
exactly one gated write path rather than two.

## 5.2 The Jira client

| Concern | Requirement |
|---|---|
| **Change detection** | `REQ-INT-003` — reads the **changelog/history API**. Poll-and-diff is prohibited: it misattributes every change since the last poll to "now" |
| Pagination | Cursor-based, checkpointed per page (`REQ-RES-003`) |
| Rate limiting | Respects the server's limits with backoff; a rate-limit response is not an error condition |
| Auth failure | `REQ-INT-016` — stops and asks the user to verify credentials. Never proceeds with partial data |
| Scope | Configured per project/JQL. Never "all issues everywhere" by default |
| Write access | `REQ-INT-018` — **read-only against requirement issues.** Métis writes defects and test cases, never edits a source requirement ticket |

### What is fetched per issue

`summary`, `description`, `issuetype`, `status`, `priority`, `labels`,
`components`, `fixVersions`, configured custom fields (notably acceptance
criteria), `comment` (all, with authors and timestamps), `issuelinks`, parent and
subtasks, and the full `changelog`.

`REQ-INT-012` — `jira_key` is stored **site-qualified**, so it remains globally
unique across Atlassian sites. A bare project key is not sufficient.

## 5.3 Field mapping as configuration

`REQ-INT-004` — Field mappings are configuration, never hardcoded.

```yaml
version: 1.0.0
source_system: jira

field_mappings:
  - {source_field: "key",                   target: "scope.primary_id",              transform: identity}
  - {source_field: "fields.issuetype.name", target: "scope.primary_type",            transform: normalize_issue_type}
  - {source_field: "fields.summary",        target: "metadata.title",                transform: identity}
  - {source_field: "fields.description",    target: "metadata.description",          transform: identity}
  - {source_field: "fields.priority.name",  target: "metadata.priority",             transform: normalize_priority}
  - {source_field: "fields.status.name",    target: "metadata.status.summary_status", transform: normalize_status}
  - {source_field: "fields.labels",         target: "metadata.tags",                 transform: identity}

custom_fields:
  - internal_name: "customfield_XXXXX"
    display_name: "Acceptance Criteria"
    target: "specifications.acceptance_criteria"
    transform: parse_acceptance_criteria

issue_type_normalization:
  Epic: epic
  Story: story
  Feature: feature
  Task: task
  Bug: defect
  Defect: defect

status_normalization:   { "To Do": draft, "In Progress": active, "In Review": active,
                          "Done": completed, "Closed": completed }
priority_normalization: { Blocker: critical, Critical: critical, High: high,
                          Medium: medium, Low: low, Trivial: low }
```

Every organisation's Jira differs in custom field ids, workflow statuses and issue
type names. Encoding any of these in code guarantees a fork per deployment.

## 5.4 Unified Intake Format (UIF v2)

The single normalised shape. Source-agnostic by design (`REQ-INT-002`) even
though only one extractor ships.

| Top-level section | Contents |
|---|---|
| `uif_version` | Schema version constant |
| `scope` | `primary_id`, `primary_type` (epic\|story\|feature\|task\|defect), `source_system`, `created_at`, `last_updated_at`, `uif_generated_at` |
| `metadata` | `title`, `description`, `status` (normalised status object), `priority`, `tags` |
| `facts` | `observations`, `measurements`, `current_state`, `constraints` — each with id, type, name, value, confidence (`observed`\|`inferred`\|`assumed`), `source_ref`, `derived` flag |
| `specifications` | `business_flows`, `acceptance_criteria`, `business_rules`, `non_functional_requirements`, `dependencies` |
| `error_handling` | `error_scenarios`, `edge_cases`, `known_issues` |
| `open_questions` | `ambiguities`, `missing_requirements`, **`conflicts`** |
| `traceability` | **`source_references` (minimum 1, mandatory)**, `evidence_artifacts`, `derivation_log` |

### Normalised status vocabulary

Six orthogonal status families, never a single generic `status` field:

`approval_state`, `automation_status`, `validation_status`, `measurement_status`,
`freshness_status`, `summary_status`.

`REQ-RPT-010` — Reports use this vocabulary. A generic `status` field collapses
six independent questions into one and makes every report ambiguous.

### The four hard rules

| # | Rule | Requirement |
|---|---|---|
| 1 | **FACTS before SPECIFICATIONS** — record what the source says exactly; do not synthesise acceptance criteria at extraction time | `REQ-INT-005` |
| 2 | **Every element carries a source reference** — traceability back to the source artifact is mandatory on every element | `REQ-INT-006` |
| 3 | **Conflict marking, not reconciliation** — when the same fact appears differently, mark both `conflict: true`; never pick one silently | `REQ-INT-007` |
| 4 | **No code samples in UIF** — it captures business facts, not implementation | `REQ-INT-009` |

`REQ-INT-008` — UIF output validates against its schema before write. A failure
stops the run and reports which fields failed. The file is not written.

## 5.5 Landing a UIF document as an Episode

`REQ-INT-010` — `Episode.raw_content` is a **human-readable prose rendering** of
the UIF's content — acceptance criteria, business rules, facts, descriptions —
deliberately dropping machine-only scaffolding (ids, timestamps, extractor names,
confidence enums).

This is not a cosmetic choice. Stage 1 segments and triages *prose*. Serialising
raw JSON would hand it a wall of punctuation with no behavioural cues, and every
block would be discarded.

The Episode carries `source_connector: jira`, `t_recorded` from the issue's own
changelog, `job_id`, `unit_id`, `checkpoint_status`, and a content fingerprint.

### `JiraItem` — the evidence anchor

`REQ-INT-011` — A `JiraItem` is created for every ingested issue and **remains
queryable even when its Requirement is rejected, quarantined, or of an
unsupported type.**

This separation matters: it means "we saw this ticket and here is what happened to
it" is always answerable. Without it, a rejected requirement is indistinguishable
from a ticket that was never fetched.

```
JiraItem -[:REPRESENTS]-> Requirement | Defect
JiraItem -[:HAS_AC]->     AcceptanceCriterion     (this issue's own AC evidence)
JiraItem -[:LINKS_TO]->   JiraItem                (real parent/subtask/issuelink)
Commit   -[:REFERENCES]-> JiraItem                (exact commit-to-ticket evidence)
```

`REQ-INT-014` — Jira issue links are represented as `JiraItem`→`JiraItem` edges,
**distinct from requirement traceability**. A Jira "relates to" link is source-system
metadata, not a claim that one requirement traces to another.

## 5.6 Stage 1 — deterministic segmentation and triage

`REQ-MIN-001` — No model calls. At all.

Blocks are segmented from `raw_content`, normalised, hashed, and classified:

| Outcome | Meaning | Effect |
|---|---|---|
| **DIRECT** | Already satisfies the EARS checker | Never reaches Stage 2 — no model call at all (`REQ-MIN-003`) |
| **NEEDS_LLM** | Prose carrying at least one behavioural cue, but not EARS-shaped | Proceeds to Stage 2 |
| **DISCARD** | Code fences, headings, boilerplate, tables, or prose with no behavioural cue | Counted, with a reason (`REQ-MIN-002`) |

`REQ-MIN-002` — Discards are counted and carry a reason. **Nothing is silently
dropped.** The discard rate is itself a signal: a sudden rise means the source
changed shape, not that the content got worse.

### An honest note on where the saving actually comes from

Measured on v1's own corpus, the **DIRECT short-circuit fired zero times** across
~1,972 blocks — because design documents *about* a requirements system contain no
EARS-shaped sentences. The real measured saving was **DISCARD**, at ~31% of
characters never reaching a model.

Expect DIRECT to matter for real requirement intake and contribute nothing for
narrative documents. **Character reduction, not block reduction, is the number to
trust**, since spend tracks tokens.

### Known limitation, deliberately not fixed

An EARS sentence embedded mid-paragraph is not detected, because the check is
anchored and runs per block. Sentence-level splitting was prototyped and found
zero additional hits on available data, so it was not added on speculation.

### Evidence anchoring

Every candidate keeps the byte offsets it came from, so a landed node carries a
real evidence field pointing back into the Episode's `raw_content` (Layer 1).

## 5.7 Stage 2 — gated model extraction

`REQ-MIN-004` — Runs **only** on NEEDS_LLM candidates.

**The discipline: the model proposes, deterministic code verifies.** A proposal
is never trusted because the model sounded confident.

Two anti-fabrication measures, because this is the only place in the pipeline
where text that was not in the source can appear:

| # | Measure | Requirement |
|---|---|---|
| 1 | The prompt forbids introducing behaviour absent from the block, and the **block is passed verbatim** — never summarised or paraphrased | `REQ-MIN-005`, `REQ-MIN-006` |
| 2 | A **grounding ratio** deterministically measures how much of the proposal's vocabulary occurs in the source block | `REQ-MIN-008` |

`REQ-MIN-008` — A proposal below the grounding threshold is blocked as ungrounded
**even if it is perfectly EARS-shaped**, because fluent well-formedness is exactly
what a hallucination looks like.

This is a **heuristic and is disclosed as one**: it catches wholesale invention,
not subtle drift. Subtle drift is Layer 6's job.

`REQ-MIN-010` — The cost gate is consulted **before** any call, and the model
comes from configuration, never a hardcoded literal. Nothing here decides on its
own to spend money at scale.

## 5.8 Stage 3 — deterministic verification

`REQ-MIN-007` — Every returned statement is re-checked against:

1. **EARS conformance** — structural.
2. **Vagueness / unfalsifiability** — unmeasurable language.
3. **Grounding ratio** — §5.7.
4. **ISO/IEC/IEEE 29148 characteristics** — singular, verifiable, unambiguous,
   complete, feasible, correct, necessary, consistent.

`REQ-MIN-009` — A proposal that fails is **retried once**, then recorded as
BLOCKED with its reason. Never silently dropped. Never written anyway.

`REQ-INT-013` — A Story or Epic whose description is not EARS-conformant is **not
landed as a `Requirement`.** It is logged as skipped, and its `JiraItem` remains
present and queryable.

This visibly reduces how many requirements land. Force-fitting them instead
produces a graph that lies about its own quality — and the EARS conformance metric
(DQ-003) would then measure nothing.

## 5.9 Stage 4 — planned landing

`REQ-MIN-012` — Split into a **pure planner** and a **thin writer**:

```
plan_landing(...)  -> LandingPlan   # no database; fully unit-testable
land(session, ...) -> result        # executes the plan
```

Every edge in a `LandingPlan` is checked against the relationship validator —
which is itself pure — so the ontology legality of the whole chain is **provable
without a live database**. This matters because graph-backed tests need a
container, and a plan that silently proposed an illegal edge would otherwise only
fail at write time.

### The chain produced

```
Intent
  ↑ TRACES_TO   Requirement ──HAS_AC──► AcceptanceCriterion
  ↑ TRACES_TO   AcceptanceCriterion
  ↑ TRACES_TO   TestDesign  ──COVERS──► AcceptanceCriterion

State ──WHEN──► Transition ──THEN──► State           (only when behaviour was mined)
AcceptanceCriterion ──VALIDATES──► Transition        (only when behaviour was mined)
```

Every triple is already in the allowed-relationship catalogue. **No schema change
is required by intake.**

### Landing discipline

- `Requirement` goes through the guardrail pipeline; everything else is written at
  `Quarantine` for human review.
- Confidence is set **below** the auto-write floor, deliberately.
- A rejected `Requirement` **aborts the chain** and the reason is returned, never
  swallowed.

## 5.9a Build-time data source: cached export (DD-3)

v1 is built and tested against a **cached export of real Jira tickets**, not a
live connection. This is a deliberate decision (DD-3) and it constrains what can
be verified.

`REQ-INT-019` — The cached export MUST include the **full changelog** for every
issue. Without it, §04.2's changelog-anchored temporal strategy — the single most
important correctness property of this connector — is untestable, and the export
proves nothing about the behaviour that matters most.

`REQ-INT-020` — The export MUST include at least one issue exhibiting each of:
a bulk edit affecting many issues at one timestamp; an issue reopened after
closure; an issue whose acceptance criteria live somewhere other than the
configured custom field; an issue of an unmapped type; and an issue whose
description is not EARS-conformant. An export of only well-formed tickets tests
the happy path and nothing else.

`REQ-INT-021` — The cached export is **real company data** and is subject to the
classification gate (`REQ-SEC-007`) exactly as a live connection would be. It
MUST carry an explicit classification entry, and it MUST NOT be committed to a
repository whose classification is looser than its own.

### What remains verifiable, and what does not

| Property | Verifiable from a cached export? |
|---|---|
| Changelog anchoring, `t_recorded` correctness | ✅ — provided `REQ-INT-019` holds |
| Bulk-edit correctness | ✅ — provided `REQ-INT-020` holds |
| Field mapping, normalisation, custom-field extraction | ✅ |
| UIF shape and schema validation | ✅ |
| Mining stages 1–4, grounding, EARS skip behaviour | ✅ |
| Idempotency and SIGKILL resume (`REQ-RES-007`) | ✅ — replay is replay |
| Conflict preservation | ✅ |
| **Incremental cursor advance against a moving instance** | ⛔ Partially — simulated by replaying the export in timestamp slices |
| **Pagination against real page boundaries** | ⛔ Partially |
| **Rate-limit backoff** | ⛔ Not verifiable |
| **Auth failure handling** (`REQ-INT-016`) | ⛔ Not verifiable — stub only |

`REQ-INT-022` — The four partially- or non-verifiable behaviours above MUST be
implemented and unit-tested against stubs, and MUST be listed as **unexercised
against a live instance** in the phase exit record. They are not to be reported
as verified.

## 5.10 Incremental sync

| Step | Behaviour |
|---|---|
| Cursor | Per project, stored in the graph, anchored to the last processed changelog timestamp |
| Batch | Configurable page size; each page checkpointed |
| Idempotency | `unit_id` per issue-version; re-processing is a no-op (`REQ-RES-005`) |
| Deletion | A Jira issue that disappears does **not** delete graph nodes. It closes their validity window and records the closure. Deletion in a source is a fact about the source, not a licence to erase history |
| Re-open | An issue reopened after closure supersedes cleanly through the normal revision chain |

`REQ-INT-015` — Sync is incremental and resumable, with checkpointing.
`REQ-RES-007` — SIGKILL mid-sync, resume, identical graph.

## 5.11 Handling of Jira-specific realities

Things that look like edge cases and are actually the normal state of real Jira
instances:

| Reality | Handling |
|---|---|
| Acceptance criteria live in a custom field, a description heading, a checklist plugin, or comments — often all four in one project | Configured extraction order; all found ACs land, each with its own `source_ref`; conflicts marked, not merged |
| Description is Atlassian Document Format, not markdown | Rendered to prose at extraction; the raw structure is retained in the Episode |
| Issue type names are localised or customised | `issue_type_normalization` mapping; an unmapped type produces a `JiraItem` with no Requirement, logged — not a guess |
| Status workflows differ per project | `status_normalization` per project configuration |
| A ticket is edited hundreds of times | Changelog-anchored revisions; each meaningful change is one revision, not one per field touched |
| Bulk edits touch thousands of issues with one timestamp | Handled correctly *because* `t_recorded` comes from the changelog rather than poll time — this is exactly the case poll-and-diff corrupts |
| Attachments contain the real specification | Metadata only in v1. Attachment content extraction is a **second intake source** and is out of scope (§01.5) — flagged, not silently skipped |

## 5.12 What intake explicitly does not do

| Not done | Why |
|---|---|
| Synthesise acceptance criteria at extraction time | `REQ-INT-005` — that is Stage 2's job, under verification |
| Reconcile conflicting facts | `REQ-INT-007` — conflicts are data |
| Trust an upstream claim that something *is* an acceptance criterion | UIF arrives already claiming structure; that claim is evidence, not authority. The mined result goes through the same guardrails as anything else |
| Auto-write anything | Everything lands at Quarantine |
| Write back to Jira requirement tickets | `REQ-INT-018` |
| Ingest Confluence, Zephyr, documents, or any second source | §01.5 — the interface stays open, the implementation does not ship |

## 5.13 Acceptance tests for this pipeline

| Test | Asserts |
|---|---|
| Changelog anchoring | Every derived node's `t_recorded` equals a real changelog timestamp; **no node** carries an ingestion-derived one |
| Bulk-edit correctness | A simulated bulk edit does not collapse all history to one moment |
| Non-EARS skip | A non-conformant Story produces a `JiraItem` and **no** `Requirement`, with a skip reason |
| Grounding block | A fabricated-but-fluent proposal is BLOCKED with a reason |
| Conflict preservation | Two conflicting AC statements both land, both marked, neither chosen |
| Chain legality | Every `LandingPlan` edge validates offline against the relationship catalogue |
| Connector enforcement | A `Requirement` write attempt from a non-`jira` connector is rejected (`REQ-INT-001`) |
| Resume | SIGKILL mid-sync → resume → identical graph |
| Idempotency | Full re-run produces zero duplicate nodes |
| Deletion | A removed Jira issue closes validity, does not delete nodes |
