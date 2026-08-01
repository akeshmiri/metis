"""
Phase 7: the flat-files connector (connectors/metis-connector-flatfiles.json),
protocol=file_scan -- genuinely different shape from Phase 2's
athena_internal_read connector, and needs no mock external system at all:
file_scan reads real files from a real local directory directly, so this
runs against this project's own real corpus/*.md files (the same real
dogfooding corpus LocalGraphStore/load_dogfooding_corpus.py already use),
not synthetic content.

Scope: lands one Episode per file (Extract stage only, per §6.1's stage
contract) -- this manifest's entity_type_mapping target
("Document-sourced content") has no corresponding label in the closed
ontology (schema/metis-graph-01-entity-baseline-constraints.cypher's 49
labels), and free-text structural extraction into typed entities is
judgment/LLM work per §6.3's code-vs-LLM table, not deterministic Cognify
like Phase 3's AST parsing -- correctly out of scope here, not silently
skipped.

Checkpointing: per the manifest's temporal_strategy, t_recorded is the
file's own last-modified time where reliable. Resume cursor is (mtime,
path) -- mtime alone has the same tie-breaking hazard Phase 2's connector
found with Postgres updated_at, so path (unique per file) breaks ties.
"""
import glob
import os
import sys

from neo4j import GraphDatabase

SOURCE_CONNECTOR = "flat-files"
ACCEPTED_EXTENSIONS = {".md", ".txt", ".csv"}  # subset of the manifest's list this repo actually has


def _checkpoint(session) -> tuple:
    rec = session.run(
        """
        MATCH (e:Episode {source_connector: $connector})
        WHERE e.checkpoint_status = 'complete'
        RETURN max(e.source_mtime) AS max_mtime
        """,
        connector=SOURCE_CONNECTOR,
    ).single()
    max_mtime = rec["max_mtime"] if rec else None
    if max_mtime is None:
        return (None, "")
    rec2 = session.run(
        """
        MATCH (e:Episode {source_connector: $connector})
        WHERE e.checkpoint_status = 'complete' AND e.source_mtime = $max_mtime
        RETURN max(e.path) AS max_path
        """,
        connector=SOURCE_CONNECTOR, max_mtime=max_mtime,
    ).single()
    return (max_mtime, rec2["max_path"] or "")


def _land_file(session, job_id: str, path: str, mtime: float) -> None:
    rel_path = os.path.relpath(path)
    episode_id = f"flat-files:{rel_path}"

    def _write(tx):
        with open(path, encoding="utf-8") as f:
            content = f.read()
        tx.run(
            """
            MERGE (e:Episode {id: $episode_id})
            SET e.source_connector = $connector, e.unit_id = $unit_id, e.job_id = $job_id,
                e.t_recorded = datetime({epochSeconds: toInteger($mtime)}),
                e.checkpoint_status = 'complete', e.episode_type = 'DocumentIngested',
                e.path = $path, e.source_mtime = $mtime, e.raw_content = $content,
                e.event_time_confidence = 'verified'
            """,
            episode_id=episode_id, connector=SOURCE_CONNECTOR, unit_id=rel_path,
            job_id=job_id, mtime=mtime, path=rel_path, content=content,
        )

    session.execute_write(_write)


def run(watch_glob: str, neo4j_uri: str, neo4j_user: str, neo4j_password: str,
        database: str = "neo4j", job_id: str = "flat-files-manual-run", on_unit=None) -> dict:
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    driver.verify_connectivity()
    landed = 0
    try:
        with driver.session(database=database) as session:
            last_mtime, last_path = _checkpoint(session)
            files = []
            for path in sorted(glob.glob(watch_glob)):
                if os.path.splitext(path)[1] not in ACCEPTED_EXTENSIONS:
                    continue
                mtime = os.path.getmtime(path)
                rel_path = os.path.relpath(path)
                if last_mtime is not None and (mtime, rel_path) <= (last_mtime, last_path):
                    continue
                files.append((path, mtime))
            files.sort(key=lambda pm: (pm[1], os.path.relpath(pm[0])))

            for path, mtime in files:
                _land_file(session, job_id, path, mtime)
                landed += 1
                if on_unit:
                    on_unit(path)
    finally:
        driver.close()
    return {"landed": landed}


def main():
    import os as _os
    from datetime import datetime, timezone
    from metis_mcp.config_manager import ConfigManager

    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    password = _os.environ.get(neo4j_cfg.get("password_env", ""))
    if not password:
        raise ValueError(f"{neo4j_cfg.get('password_env')} must be set.")

    watch_glob = _os.environ.get("METIS_FLATFILES_GLOB") or str(
        (config.effective_path.parent.parent / "corpus" / "*.md").resolve()
    )
    job_id = f"flat-files-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    def _log(path):
        print(f"PROCESSED {path}", file=sys.stderr, flush=True)

    result = run(watch_glob, neo4j_cfg["uri"], neo4j_cfg["user"], password, job_id=job_id, on_unit=_log)
    print(f"Landed {result['landed']} document(s) from {watch_glob} (job {job_id}).", file=sys.stderr)


if __name__ == "__main__":
    main()
