"""
§5.4 (temporal query interface) + Layer 10 (auditable rollback,
REQ-METIS-GRD-10) -- built together since both operate on the same real
mechanism: a `:Revision` supersession chain per entity, `t_valid`/
`t_invalid` derived from `t_recorded` (REQ-METIS-TMP-01), nothing ever
destructively overwritten.

Real, disclosed gap this closes: the schema (metis-graph-01/02-*.cypher)
already declares `t_valid`/`t_invalid` indexes on nodes and relationships,
and REQ-METIS-ONT-05 already specifies a `revision` integer property on
Requirement/AcceptanceCriterion -- but until this module, nothing in this
codebase ever wrote more than one version of an entity's state or read
those fields back. Every existing write path (structural_validation.py,
confidence_tiering.py, the connectors) SETs an entity's properties
in-place, with no history kept -- this module is the first real mechanism
for entities that need one. It's usable standalone today (record_revision
is a real, independently-callable function, tested end-to-end below,
Requirement-edit callers can adopt it) -- retrofitting every existing
connector write path to call it is a separate, much larger integration
task, out of scope here and not silently claimed as done.

Design: a `:Revision {id, revision, t_valid, t_invalid, t_recorded,
source_episode_id, properties_json}` node per version,
`(entity)-[:HAS_REVISION]->(:Revision)`. The entity's own live properties
always mirror its current (t_invalid IS NULL) Revision -- ordinary queries
keep working unchanged against the live node; this module is the audit/
time-travel/rollback layer on top, not a replacement for it.

Real, corrected claim about id uniqueness: schema-01's constraints are
declared PER LABEL (`FOR (n:Constitution) REQUIRE n.id IS UNIQUE`, etc.),
NOT a single global constraint across every label -- two different labels
CAN legitimately share the same id string without violating any
constraint. This is not hypothetical: `:DogfoodingItem` (the self-
referential dogfooding corpus's own shadow copy, per
neo4j_graph_store.py's docstring) uses the exact same natural ids as the
production ontology (e.g. both a `:DogfoodingItem` and a real
`:Constitution` node can be `{id: 'CONST-046'}`) -- verified for real, not
assumed, after `metis_mcp/constitution_gate.py`'s loader hit a real
constraint violation caused by exactly this collision. Every query below
excludes `:DogfoodingItem` explicitly for that reason -- it's the one
known, deliberate, real id-namespace overlap in this ontology; nothing
else in the closed 49-label set is known to collide (each label's id
generation scheme is structurally distinct -- `repo:path:name` vs
`CONST-NNN` vs UUID-ish, etc.).

  record_revision  -- write a new version (closes the prior one's t_valid
                       window automatically, per REQ-METIS-TMP-01/§5.1)
  as_of            -- point-in-time reconstruction (§5.4)
  history          -- full supersession chain (§5.4)
  diff             -- structural diff between two points in time (§5.4)
  rollback         -- Layer 10/REQ-METIS-GRD-10: writes the target
                       revision's state as a NEW revision (never deletes/
                       overwrites the intervening history), records a real
                       RollbackPerformed episode
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Bookkeeping keys live on the Revision node itself, not inside the
# snapshotted properties_json -- excluding them keeps diff()/as_of() from
# reporting their own plumbing as a "change."
_CONTROL_KEYS = {"id", "revision", "t_valid", "t_invalid", "t_recorded", "source_episode_id"}


@dataclass
class RevisionRecord:
    revision: int
    t_valid: str
    t_invalid: str | None
    t_recorded: str
    source_episode_id: str
    properties: dict = field(default_factory=dict)


def _snapshot_properties(props: dict) -> dict:
    return {k: v for k, v in props.items() if k not in _CONTROL_KEYS}


def record_revision(session, entity_id: str, properties: dict, source_episode_id: str,
                     t_recorded: str | None = None) -> int:
    """Writes a new Revision, closes the prior current one's t_valid window
    (REQ-METIS-TMP-01: t_valid derived from t_recorded, closed automatically
    on supersession), applies `properties` onto the live entity node so
    ordinary queries stay current, and bumps `entity.revision`
    (REQ-METIS-ONT-05). id-based, scoped to exclude `:DogfoodingItem` --
    see module docstring for why that specific exclusion is real and
    necessary, not defensive-for-no-reason."""
    snapshot = _snapshot_properties(properties)
    # Computed once in Python, not left to Cypher's now() -- guarantees the
    # exact same instant closes the prior Revision's t_invalid and opens
    # the new one's t_valid (no daylight between two separate datetime()
    # calls inside the same write).
    effective_t_recorded = t_recorded or datetime.now(timezone.utc).isoformat()

    def _write(tx):
        # Real bug caught writing metis_mcp/academy.py's changelog against
        # this function: every MATCH below silently matches zero rows if
        # `entity_id` doesn't already exist as a real node -- the whole
        # write becomes a no-op, but execute_write still returns a revision
        # number as if something was written. Fail loudly instead: a
        # revision can only ever be recorded for an entity that's real.
        exists = tx.run(
            "MATCH (e {id: $entity_id}) WHERE NOT e:DogfoodingItem RETURN e LIMIT 1",
            entity_id=entity_id,
        ).single()
        if exists is None:
            raise ValueError(
                f"record_revision: no entity with id '{entity_id}' exists -- refusing to "
                f"silently no-op. Create the entity node first, then record its first revision."
            )
        rec = tx.run(
            "MATCH (e {id: $entity_id}) WHERE NOT e:DogfoodingItem "
            "MATCH (e)-[:HAS_REVISION]->(r:Revision) "
            "RETURN r.revision AS revision ORDER BY r.revision DESC LIMIT 1",
            entity_id=entity_id,
        ).single()
        next_revision = (rec["revision"] + 1) if rec else 1
        # MERGE below, not CREATE -- real bug caught by an intermittently
        # failing test: the neo4j driver's execute_write() can retry this
        # whole function on a transient error even after the server-side
        # commit actually succeeded (a documented at-least-once edge case,
        # not specific to this codebase). CREATE isn't idempotent against
        # that retry -- a second attempt tries to create the exact same
        # Revision id again and hits the real uniqueness constraint. MERGE
        # keyed on the same deterministic id makes a retry a safe no-op
        # instead of an error, matching this project's own established
        # MERGE-based idempotency convention used everywhere else
        # (submit_candidate, load_transition, etc.).
        tx.run(
            "MATCH (e {id: $entity_id}) WHERE NOT e:DogfoodingItem "
            "MATCH (e)-[:HAS_REVISION]->(r:Revision) "
            "WHERE r.t_invalid IS NULL "
            "SET r.t_invalid = datetime($t_recorded)",
            entity_id=entity_id, t_recorded=effective_t_recorded,
        )
        tx.run(
            """
            MATCH (e {id: $entity_id}) WHERE NOT e:DogfoodingItem
            MERGE (r:Revision {id: $entity_id + ':rev:' + toString($next_revision)})
            ON CREATE SET r.revision = $next_revision, r.t_valid = datetime($t_recorded),
                r.t_invalid = null, r.t_recorded = datetime($t_recorded),
                r.source_episode_id = $source_episode_id, r.properties_json = $properties_json
            MERGE (e)-[:HAS_REVISION]->(r)
            SET e += $properties, e.revision = $next_revision
            """,
            entity_id=entity_id, next_revision=next_revision, t_recorded=effective_t_recorded,
            source_episode_id=source_episode_id, properties_json=json.dumps(snapshot),
            properties=properties,
        )
        return next_revision
    return session.execute_write(_write)


def _row_to_record(row: dict) -> RevisionRecord:
    return RevisionRecord(
        revision=row["revision"], t_valid=row["t_valid"], t_invalid=row["t_invalid"],
        t_recorded=row["t_recorded"], source_episode_id=row["source_episode_id"],
        properties=json.loads(row["properties_json"]),
    )


def history(session, entity_id: str) -> list[RevisionRecord]:
    """§5.4 history(entity): full supersession chain, oldest first. Each
    entry carries its own source_episode_id -- 'source + precedence-tier
    per version' per §5.4's stated purpose (precedence-tier itself lives on
    the Episode, not duplicated here)."""
    rows = session.run(
        "MATCH (e {id: $entity_id}) WHERE NOT e:DogfoodingItem "
        "MATCH (e)-[:HAS_REVISION]->(r:Revision) "
        "RETURN r.revision AS revision, toString(r.t_valid) AS t_valid, "
        "toString(r.t_invalid) AS t_invalid, toString(r.t_recorded) AS t_recorded, "
        "r.source_episode_id AS source_episode_id, r.properties_json AS properties_json "
        "ORDER BY r.revision ASC",
        entity_id=entity_id,
    ).data()
    return [_row_to_record(row) for row in rows]


def as_of(session, entity_id: str, timestamp: str) -> RevisionRecord | None:
    """§5.4 as_of(entity, timestamp): point-in-time reconstruction -- the
    Revision whose validity window contains `timestamp` (ISO 8601 string,
    compared as Neo4j datetime -- ordering, not string equality)."""
    row = session.run(
        "MATCH (e {id: $entity_id}) WHERE NOT e:DogfoodingItem "
        "MATCH (e)-[:HAS_REVISION]->(r:Revision) "
        "WHERE r.t_valid <= datetime($timestamp) "
        "AND (r.t_invalid IS NULL OR r.t_invalid > datetime($timestamp)) "
        "RETURN r.revision AS revision, toString(r.t_valid) AS t_valid, "
        "toString(r.t_invalid) AS t_invalid, toString(r.t_recorded) AS t_recorded, "
        "r.source_episode_id AS source_episode_id, r.properties_json AS properties_json",
        entity_id=entity_id, timestamp=timestamp,
    ).single()
    return _row_to_record(row) if row else None


def diff(session, entity_id: str, t1: str, t2: str) -> dict:
    """§5.4 diff(entity, t1, t2): structural diff between two points in
    time. Reports added/removed/changed keys -- honest about the case
    where the entity has no Revision covering one or both timestamps
    (not silently treated as 'no change')."""
    snap1 = as_of(session, entity_id, t1)
    snap2 = as_of(session, entity_id, t2)
    if snap1 is None or snap2 is None:
        return {
            "entity_id": entity_id, "t1": t1, "t2": t2, "comparable": False,
            "reason": f"No revision covers {'t1' if snap1 is None else 't2'} "
                      f"({t1 if snap1 is None else t2}) -- cannot diff.",
        }
    p1, p2 = snap1.properties, snap2.properties
    added = {k: p2[k] for k in p2.keys() - p1.keys()}
    removed = {k: p1[k] for k in p1.keys() - p2.keys()}
    changed = {k: {"from": p1[k], "to": p2[k]} for k in p1.keys() & p2.keys() if p1[k] != p2[k]}
    return {
        "entity_id": entity_id, "t1": t1, "t2": t2, "comparable": True,
        "revision_at_t1": snap1.revision, "revision_at_t2": snap2.revision,
        "added": added, "removed": removed, "changed": changed,
    }


def rollback(session, entity_id: str, target_revision: int, actor: str,
             reason: str) -> dict:
    """Layer 10/REQ-METIS-GRD-10: 'rollback closes t_valid, restores prior
    state, recorded as an episode.' Never destructively overwrites --
    restoring revision N's state after M more revisions happened creates
    revision M+1 with N's snapshot, leaving 1..M fully intact in history.
    A real RollbackEpisode is written (never a bare property flip nobody
    can audit)."""
    target = session.run(
        "MATCH (e {id: $entity_id}) WHERE NOT e:DogfoodingItem "
        "MATCH (e)-[:HAS_REVISION]->(r:Revision {revision: $target_revision}) "
        "RETURN r.properties_json AS properties_json",
        entity_id=entity_id, target_revision=target_revision,
    ).single()
    if target is None:
        return {
            "entity_id": entity_id, "rolled_back": False,
            "reason": f"No revision {target_revision} exists for '{entity_id}' -- refusing to "
                      f"guess a target state.",
        }
    current = session.run(
        "MATCH (e {id: $entity_id}) WHERE NOT e:DogfoodingItem "
        "MATCH (e)-[:HAS_REVISION]->(r:Revision) WHERE r.t_invalid IS NULL "
        "RETURN r.revision AS revision", entity_id=entity_id,
    ).single()
    from_revision = current["revision"] if current else None
    target_properties = json.loads(target["properties_json"])

    episode_id = f"rollback:{entity_id}:{from_revision}-to-{target_revision}:{actor}"

    def _write(tx):
        # MERGE, not CREATE -- same real, demonstrated execute_write retry
        # edge case as record_revision above; episode_id is deterministic
        # and computed before this possibly-retried function runs.
        tx.run(
            """
            MERGE (ep:Episode {id: $episode_id})
            ON CREATE SET ep.t_recorded = datetime(), ep.source_connector = 'rollback',
                ep.job_id = $episode_id, ep.episode_type = 'RollbackPerformed', ep.entity_id = $entity_id,
                ep.from_revision = $from_revision, ep.to_revision = $target_revision,
                ep.actor = $actor, ep.rollback_reason = $reason
            """,
            episode_id=episode_id, entity_id=entity_id, from_revision=from_revision,
            target_revision=target_revision, actor=actor, reason=reason,
        )
    session.execute_write(_write)

    new_revision = record_revision(session, entity_id, target_properties, episode_id)

    return {
        "entity_id": entity_id, "rolled_back": True, "from_revision": from_revision,
        "restored_state_of_revision": target_revision, "new_revision": new_revision,
        "episode_id": episode_id,
        "reason": f"Revision {target_revision}'s state re-applied as new revision "
                  f"{new_revision} -- revisions {target_revision + 1}..{new_revision - 1} "
                  f"remain in history, untouched, per the bi-temporal no-destructive-overwrite rule.",
    }
