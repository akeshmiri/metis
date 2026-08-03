"""
Session 10, item 1's "keep the graph up to date" -- a real, scoped active
resync/drift-detection core, reusing existing real infrastructure rather
than inventing a new mechanism:

  check_staleness       -- per real Episode.source_connector, real
                            days-since-most-recent-t_recorded. Answers
                            "is the graph up to date" for any connector,
                            no new storage needed.
  sync_and_detect_drift  -- calls a connector's own existing, already-
                            idempotent entrypoint again for real, then
                            compares each touched entity's properties
                            before/after via metis_mcp.temporal.
                            record_revision() -- its real changed-fields
                            output IS the drift signal (no new diffing
                            logic). When anything actually changed, writes
                            a real SpecDriftDetected Episode: the concrete
                            thing metis_mcp/dq_metrics.py's DQ-014 has
                            been reporting "never created" since Session 4.

Real, disclosed scope: proof-wired through TWO connectors end to end in
main() -- connectors/test_suite_connector.py (simplest, fastest, already
idempotent, ingests this repo's own real test files) from Session 10, and
connectors/atlassian_connector.py's Confluence path (Session 11, item 4 --
the concrete "document management" case named directly) as a second,
structurally different proof: Confluence pages land as bare Episode nodes
with no downstream typed entity (Session 4's disclosed ontology gap --
"Document-sourced content" has no closed-ontology label), unlike
TestCase's Episode-plus-typed-node shape. _snapshot_entities special-cases
entity_label='Episode' to snapshot those nodes directly rather than
assuming a wrapper-Episode-plus-typed-node hop always exists. The
mechanism itself is connector-agnostic -- any zero-arg `rerun_fn` plus the
real label(s) it writes works -- so wiring the remaining 8 connectors
through this is mechanical follow-up, not a redesign, and is NOT silently
claimed done here.

Real, disclosed data quirk this module works around, not silently
assumes away: Episode.t_recorded is stored inconsistently across this
codebase -- real connectors (test_suite_connector.py, atlassian_
connector.py) use Cypher's native `datetime()`, while demo_data/
generate_demo_data.py uses a Python ISO string property. check_staleness
normalizes both rather than erroring on the mix (a real pre-existing
inconsistency, not introduced here, and out of scope to unify in this
module).
"""
import uuid
from datetime import datetime, timezone

from metis_mcp.temporal import record_revision


def _to_datetime(value):
    if hasattr(value, "to_native"):
        dt = value.to_native()
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def check_staleness(session) -> list[dict]:
    rows = session.run(
        "MATCH (ep:Episode) WHERE ep.source_connector IS NOT NULL AND ep.t_recorded IS NOT NULL "
        "RETURN ep.source_connector AS connector, ep.t_recorded AS t_recorded"
    ).data()

    latest_by_connector: dict[str, datetime] = {}
    for row in rows:
        try:
            dt = _to_datetime(row["t_recorded"])
        except (ValueError, TypeError):
            continue  # a real, unparseable t_recorded value -- skip it, don't crash the whole check
        connector = row["connector"]
        if connector not in latest_by_connector or dt > latest_by_connector[connector]:
            latest_by_connector[connector] = dt

    now = datetime.now(timezone.utc)
    return [
        {
            "connector": connector, "most_recent_t_recorded": dt.isoformat(),
            "days_since_last_update": round((now - dt).total_seconds() / 86400, 2),
        }
        for connector, dt in sorted(latest_by_connector.items())
    ]


def _snapshot_entities(session, connector_name: str, entity_label: str,
                        episode_type: str | None = None) -> dict:
    if entity_label == "Episode":
        # Document-management connectors (e.g. Confluence) land content
        # directly as Episode nodes -- source_connector set on the Episode
        # itself, no separate wrapper Episode + downstream typed node. The
        # Episode IS the entity that drifts (its raw_content/title changing
        # on re-ingestion is the real drift signal).
        if episode_type:
            rows = session.run(
                "MATCH (n:Episode {source_connector: $connector, episode_type: $episode_type}) RETURN n",
                connector=connector_name, episode_type=episode_type,
            ).data()
        else:
            rows = session.run(
                "MATCH (n:Episode {source_connector: $connector}) RETURN n", connector=connector_name,
            ).data()
    else:
        rows = session.run(
            f"MATCH (ep:Episode {{source_connector: $connector}}) "
            f"MATCH (n:{entity_label} {{source_episode_id: ep.id}}) "
            f"RETURN n",
            connector=connector_name,
        ).data()
    return {row["n"]["id"]: dict(row["n"]) for row in rows}


def _record_spec_drift_episode(session, connector_name: str, drifted: list[dict], episode_id: str) -> None:
    def _write(tx):
        tx.run(
            "MERGE (e:Episode {id: $id}) "
            "ON CREATE SET e.t_recorded = datetime(), e.source_connector = 'graph-sync', "
            "e.unit_id = $id, e.job_id = $id, e.checkpoint_status = 'complete', "
            "e.episode_type = 'SpecDriftDetected', e.drifted_connector = $connector, "
            "e.drifted_entity_count = $count, e.drifted_entity_ids = $entity_ids",
            id=episode_id, connector=connector_name, count=len(drifted),
            entity_ids=[d["entity_id"] for d in drifted],
        )
    session.execute_write(_write)


def sync_and_detect_drift(session, connector_name: str, entity_label: str, rerun_fn,
                           episode_type: str | None = None) -> dict:
    """rerun_fn: a zero-arg callable that re-runs the connector for real
    (e.g. `lambda: test_suite_connector.run(files, uri, user, password)`).
    entity_label: the real node label this connector writes (e.g. 'TestCase'),
    or 'Episode' for a document-management connector that lands content
    directly as Episode nodes (e.g. Confluence via atlassian_connector.py) --
    episode_type then narrows which Episodes count (e.g. 'DocumentIngested').

    Every entity this connector currently owns gets a real Revision
    recorded (first one if new, another one if its properties genuinely
    changed) -- record_revision is MERGE-based and idempotent, safe to
    call every sync run even when nothing changed."""
    before = _snapshot_entities(session, connector_name, entity_label, episode_type)
    rerun_fn()
    after = _snapshot_entities(session, connector_name, entity_label, episode_type)

    sync_episode_id = f"graph-sync:{connector_name}:{uuid.uuid4()}"
    drifted = []
    for entity_id, new_props in after.items():
        # Attribute the revision to the entity's own real source_episode_id
        # (set by the connector's own real ingestion) -- fall back to this
        # sync run's episode id only if that's somehow missing.
        record_revision(session, entity_id, new_props, new_props.get("source_episode_id", sync_episode_id))
        old_props = before.get(entity_id)
        if old_props is None:
            continue  # newly created this run -- real provenance recorded above, not "drift"
        changed = {
            k: {"from": old_props.get(k), "to": v} for k, v in new_props.items()
            if k != "id" and old_props.get(k) != v
        }
        if changed:
            drifted.append({"entity_id": entity_id, "changed_fields": changed})

    if drifted:
        _record_spec_drift_episode(session, connector_name, drifted, sync_episode_id)

    return {
        "connector": connector_name, "entities_checked": len(after),
        "newly_created": len(after) - len(before.keys() & after.keys()),
        "drifted": drifted,
    }


def main():
    """Proof-wired through two real connectors: test_suite_connector.py
    (Session 10) and atlassian_connector.py's Confluence path (Session 11,
    item 4 -- requires connectors/mock_jira_server.py already running at
    METIS_MOCK_JIRA_URL; skipped with a note if unreachable, not silently
    faked). Real, disclosed scope -- the other 8 connectors aren't wired
    through this yet (see module docstring)."""
    import glob
    import os
    import sys
    import urllib.error
    import urllib.request

    from connectors import atlassian_connector, test_suite_connector
    from metis_mcp.config_manager import ConfigManager
    from neo4j import GraphDatabase

    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    password = os.environ.get(neo4j_cfg.get("password_env", ""))
    if not password:
        raise ValueError(f"{neo4j_cfg.get('password_env')} must be set.")

    server_dir = config.effective_path.parent.parent
    test_files = sorted(glob.glob(str(server_dir / "test_*.py")))

    def rerun_test_suite():
        test_suite_connector.run(test_files, neo4j_cfg["uri"], neo4j_cfg["user"], password,
                                  job_id=f"graph-sync-{uuid.uuid4()}", repo="metis-server")

    mock_jira_url = os.environ.get("METIS_MOCK_JIRA_URL", "http://127.0.0.1:8424")

    driver = GraphDatabase.driver(neo4j_cfg["uri"], auth=(neo4j_cfg["user"], password))
    driver.verify_connectivity()
    try:
        with driver.session() as session:
            print("Staleness by connector:", file=sys.stderr)
            for row in check_staleness(session):
                print(f"  {row['connector']}: {row['days_since_last_update']}d since last update", file=sys.stderr)

            result = sync_and_detect_drift(session, "test-suite-ingest", "TestCase", rerun_test_suite)
            print(f"\ntest-suite-ingest sync: {result['entities_checked']} TestCase(s) checked, "
                  f"{len(result['drifted'])} drifted.", file=sys.stderr)
            for d in result["drifted"]:
                print(f"  DRIFT {d['entity_id']}: {d['changed_fields']}", file=sys.stderr)

            try:
                urllib.request.urlopen(f"{mock_jira_url}/rest/api/2/search", timeout=2)
            except (urllib.error.URLError, OSError):
                print(f"\natlassian-prod Confluence sync skipped: mock_jira_server not reachable "
                      f"at {mock_jira_url} (start it with `python3 -m connectors.mock_jira_server` "
                      f"first).", file=sys.stderr)
                return

            def rerun_confluence():
                with driver.session() as s2:
                    s2.execute_write(lambda tx: tx.run(
                        "MERGE (e:Episode {id: 'graph-sync:atlassian-manual'}) "
                        "SET e.t_recorded = datetime(), e.source_connector = 'graph-sync-driver', "
                        "e.job_id = 'graph-sync-driver'"
                    ).consume())
                    atlassian_connector.run(mock_jira_url, s2, "graph-sync:atlassian-manual")

            result2 = sync_and_detect_drift(session, "atlassian-prod", "Episode", rerun_confluence,
                                             episode_type="DocumentIngested")
            print(f"\natlassian-prod Confluence sync: {result2['entities_checked']} document(s) checked, "
                  f"{len(result2['drifted'])} drifted.", file=sys.stderr)
            for d in result2["drifted"]:
                print(f"  DRIFT {d['entity_id']}: {list(d['changed_fields'])}", file=sys.stderr)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
