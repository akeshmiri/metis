# 04 — Temporal Model, Provenance & Resumability

## 4.1 The four timestamps

Conflating any two of these corrupts historical validity windows under backfill or
replay. They are kept distinct at every layer.

| Field | Meaning | Source of truth |
|---|---|---|
| `t_event` | When the fact became true in reality | Source-native metadata when available; otherwise inferred and **flagged as inferred** |
| `t_recorded` | When the source system recorded it | **The preferred anchor for `t_valid`** |
| `t_ingested` | When Métis ingested the episode | Pipeline debugging **only** — never used in a temporal query |
| `t_valid` / `t_invalid` | The graph edge's validity window | Derived from `t_recorded`; closed automatically on supersession |

`REQ-TMP-002` — `t_valid` MUST be derived from `t_recorded`, never from
`t_ingested`, whenever the source provides a reliable recorded timestamp. This is
a hard requirement, not a default: violating it silently misattributes every
historical change to the moment of ingestion.

`REQ-TMP-003` — `t_ingested` MUST NOT appear in any temporal query path. CI
enforces this by inspecting query construction, not by convention.

## 4.2 Per-source temporal strategy

| Source | `t_recorded` anchor | Primary risk if done naively |
|---|---|---|
| **Jira** | The **changelog entry's own timestamp** | Diff-by-polling misattributes every change since the last poll to "now" — the single most common temporal bug in this class of system |
| Git / commits | PR merge time (primary), commit author date (secondary) | Rebase and squash lose individual commit dates |
| OpenAPI / contracts | Git commit date of the spec file | The spec drifts from the deployed API; cross-checked against discovered endpoints, mismatch raises drift |
| DB schema | The migration tool's `applied_at` | Manual out-of-band DDL has no recorded timestamp → flagged `inferred`, routed to quarantine |
| CI / telemetry | Native event timestamp | Clock skew — mitigated by NTP-synced ingestion, normalised to UTC |
| Code analysis (CPG) | The analysed **commit's own** date | Using analysis time would date every extracted transition to the batch run |

`REQ-TMP-004` — Every connector MUST populate `t_recorded` from its source's
native mechanism. A `now()` default is a specification violation, not an
acceptable fallback.

`REQ-TMP-005` — Where no reliable recorded timestamp exists, the fact MUST be
flagged `inferred` and routed to quarantine — never silently defaulted to
ingestion time.

## 4.3 Bi-temporal edges

Every relationship carries its own validity window, independent of the nodes it
connects. This is what makes "what did this look like on 1 March" answerable
rather than approximable.

```cypher
-- every relationship type carries these, and each has an index (REQ-ONT-011)
()-[r:TRACES_TO {t_valid: datetime, t_invalid: datetime|null,
                 t_recorded: datetime, source_episode_id: string}]->()
```

`REQ-TMP-006` — Supersession closes the prior window (`t_invalid` set) and opens
a new one. **Nothing is destructively overwritten** — this is what makes Layer 10
rollback possible at all.

## 4.4 Cross-source precedence

When two sources disagree, precedence is resolved in this order:

1. **System of record for that entity type wins** (configurable per organisation).
2. **Reliability of the recorded timestamp** breaks ties.
3. **Recency** breaks remaining ties.
4. **Irreconcilable conflicts** → contradiction episode, entity held `Disputed`,
   **never auto-resolved**.

### The shipped precedence table

| Entity type | System of record | Wins over |
|---|---|---|
| `Requirement`, `AcceptanceCriterion`, `BusinessRule` | **Jira** | Everything — it is the only intake source (§01.5) |
| `Epic`, `Feature` | Jira | — |
| `Defect` | Jira | — |
| `Endpoint`, `API` | Live contract introspection where available, else the checked-in spec | Documented API descriptions |
| `Class`, `Method`, `Transition` | The CPG at a named commit | Any hand-authored model of the same behaviour |
| `Table`, `Column` | Migration history | Any hand-written data dictionary |
| `TestExecution` | The CI/test-management system's own ingestion timestamp | — |

`REQ-TMP-007` — The precedence table MUST be **versioned, editable graph data**,
not hardcoded, so a per-organisation difference does not require a code change.

**Note on the code-vs-hand-authored row:** where a statically-extracted
`Transition` conflicts with a hand-authored one, the CPG wins on *what the code
does*, but this does not make the hand-authored model wrong — it may describe
intended behaviour the code has not yet implemented. The correct outcome is a
contradiction held `Disputed` for human resolution, not silent replacement. This
is precisely the case Layer 5 exists for.

## 4.5 Temporal query interface

| Query | Returns |
|---|---|
| `as_of(entity, timestamp)` | Point-in-time reconstruction of the entity and its edges |
| `history(entity)` | The full supersession chain, with source and precedence tier per version |
| `diff(entity, t1, t2)` | Structural diff between two points in time |

`REQ-TMP-010` — `history()` MUST include the precedence tier that caused each
version to win. This is what makes "why did this fact win" always inspectable, and
it is the primary mitigation for precedence-table misconfiguration.

## 4.6 Provenance and revisions

Every node carries `source_episode_id`; every change additionally records a
`Revision`.

```
(entity)-[:HAS_REVISION]->(:Revision {
    revision_number, recorded_at, changed_properties, prior_values,
    source_episode_id, actor, delta_type
})
```

`REQ-TMP-012` — **Every write path MUST record a revision.** CI MUST enumerate
any write path that does not, and that list MUST be empty before Phase 8.

This is called out explicitly because it is the exact obligation v1 left
unfinished: the mechanism existed and was tested, but was not wired into every
connector's write path. Retrofitting it later is a larger job than doing it at
each write path as it is built.

`REQ-ONT-010` — `HAS_REVISION` is written **only** by the revision recorder. No
connector or generator writes it directly.

## 4.7 Content-derived identity

`REQ-RES-001` — Every generated or extracted unit carries a `unit_id` derived
deterministically from its inputs:

```
unit_id = hash(source_episode_id + extraction_rule_id + chunk_offset)
```

Never an auto-incrementing counter, never a position in a list.

**Why this matters more than it looks:** two independent workers processing the
same input after a network partition converge on the same `unit_id`. The second
write is a guaranteed no-op, not a duplicate requiring downstream deduplication.
This is **prevention, not after-the-fact detection**.

`REQ-PLT-014` — Every node identifier is content-derived. `REQ-RES-006` — this is
enforced by a composite database constraint on `(source_connector, unit_id)`, not
by application-level checking alone.

## 4.8 Delta markers

`REQ-RES-002` — Every edit episode carries an explicit
`delta_type ∈ {ADDED, MODIFIED, REMOVED}`.

An explicit marker replaces ambiguous full-state diffs: "this field is absent"
becomes distinguishable from "this field was removed", which a state comparison
cannot tell apart.

## 4.9 Checkpointing and the resume algorithm

`REQ-RES-003` — Long-running artifacts carry
`checkpoint_status ∈ {PENDING, COMMITTED, FAILED}`, flipped to `COMMITTED` **only
after the full atomic write, including guardrail checks, succeeds.**

```
1. Discard all PENDING units from the interrupted run — never resume mid-unit.
2. Find the highest-numbered COMMITTED unit.
3. Resume from the next logical unit, re-deriving unit_id identically.
4. Before writing: if unit_id already exists as COMMITTED, skip (idempotent no-op).
   Otherwise proceed.
```

`REQ-RES-009` — This algorithm applies uniformly to: Jira sync batches, Cognify
extraction batches, code-analysis extraction reports, long document generation,
and background consolidation runs. One algorithm, not five.

`REQ-RES-007` — **The acceptance test:** a run interrupted with SIGKILL and
resumed MUST produce a graph identical to an uninterrupted run. This is a real
test with a real signal, not a simulated interruption.

## 4.10 Transaction-retry safety

`REQ-RES-008` — A bare `CREATE` against a precomputed id is **not** safe against
driver-level transaction retry: the retry re-executes the create and the
constraint rejects it, turning a transient network blip into a hard failure.
Every write uses merge-with-on-create semantics.

This is recorded as a requirement rather than a note because it was a real,
subtle bug found across five files in v1 — including two that predated the
session that found it. It does not surface under normal conditions and only
appears under retry, which is exactly when a system is already degraded.

## 4.11 Rollback

`REQ-GRD-010` / `REQ-GRD-031` — Rollback:

1. Closes `t_valid` on the offending state.
2. Restores the prior state from its `Revision` chain.
3. **Is itself recorded as an episode**, with the actor and the justification.

Nothing is deleted. A rollback is therefore itself reversible, and the fact that a
rollback happened is a queryable part of the record rather than an absence in it.

`REQ-OPS-009` — Rollback of a bad ingestion run is exercised at least once before
production enablement. A rollback mechanism that has never been run is a claim,
not a capability.

## 4.12 Temporal correctness test suite

The tests that must exist, because each corresponds to a way this goes wrong
silently:

| Test | Asserts |
|---|---|
| Backfill replay | Re-ingesting historical data produces the same validity windows as the original ingestion, not windows anchored to the replay time |
| Out-of-order arrival | An episode recorded earlier but ingested later lands with the correct `t_valid`, not after the already-ingested later one |
| Supersession chain | Three sequential updates produce three revisions and exactly one open validity window |
| Point-in-time | `as_of` at each of the three points returns the correct distinct state |
| Precedence | Two sources disagreeing resolve per the table, and `history()` names the deciding tier |
| Contradiction | Two same-tier sources disagreeing produce `Disputed`, with **both** values retained |
| Interrupted resume | SIGKILL mid-run, resume, graph identical to uninterrupted |
| Retry safety | A forced transaction retry produces no duplicate and no failure |
| Rollback | Bad fact rolled back, prior state restored, rollback episode present |
| No-`t_ingested` | No temporal query path references `t_ingested` |
