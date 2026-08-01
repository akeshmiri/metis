"""
Phase 2: the application-code connector, real end-to-end -- implements the
athena_internal_read protocol declared in
connectors/metis-connector-application-code.json against the mock Athena
Postgres (mock_athena_schema.sql; see that file for why it's a mock, not a
different shape).

Scope for this pass, matching the manifest's entity_type_mapping:
  - Repository row -> a real :Repository node directly (1:1, no extraction
    judgment involved -- registering a repo IS the structural fact).
  - Source-file row -> an Episode landing the RAW file content only. The
    manifest's "Source file, AST-parsed locally... -> Class/Method" step is
    the Cognify structural-extraction stage (PLAN.md Phase 3), deliberately
    kept separate here: Phase 2's job is proving the ingestion half (poll,
    checkpoint, idempotent, resumable, land-don't-discard), not extraction.
    See cognify_structural_extraction.py for the Class/Method pass.
  - Commit/PullRequest: out of scope for this pass -- see
    mock_athena_schema.sql's docstring for why (no real git history exists
    in this environment to draw them from without fabricating dates/authors).

Checkpointing: per source-table stream (repositories, source_files),
independently. The manifest names `updated_at` as the change-detection
column, which this honors as the primary ordering key -- but bare
timestamp comparison has a real tie-breaking hazard (multiple rows sharing
the same updated_at, e.g. seeded in the same batch), so the actual resume
cursor is the tuple (updated_at, id), with id (Postgres BIGSERIAL,
guaranteed monotonic and unique per table) breaking ties deterministically.
This wasn't obvious from the manifest text alone -- found by reasoning
about what "resumability" actually requires under concurrent/batched
writes, not by running into it as a bug.

Crash-safety / resumability: each unit (one repository row or one source
file row) is landed inside a single Neo4j transaction that creates the
Episode AND the Repository node (for repository units) together. If the
process is killed mid-unit, Neo4j rolls the whole transaction back --
nothing partial persists for that unit. The next run's checkpoint query
(MAX over only checkpoint_status='complete' episodes) is therefore
naturally behind that unit, and the unit gets picked up and retried by the
normal WHERE (updated_at, id) > checkpoint poll -- no separate
pending-then-complete reconciliation pass is needed. checkpoint_status is
still written as 'complete' on every landed episode (matching the schema's
review_triage/episode_checkpoint_status index intent), it's just never
durably observed as anything else, by construction.
"""
import sys

import psycopg
from neo4j import GraphDatabase

SOURCE_CONNECTOR = "application-code"


def _checkpoint(session, kind: str) -> tuple:
    rec = session.run(
        """
        MATCH (e:Episode {source_connector: $connector, source_kind: $kind})
        WHERE e.checkpoint_status = 'complete'
        RETURN max(e.source_updated_at) AS max_updated
        """,
        connector=SOURCE_CONNECTOR, kind=kind,
    ).single()
    max_updated = rec["max_updated"] if rec else None
    if max_updated is None:
        return (None, 0)
    rec2 = session.run(
        """
        MATCH (e:Episode {source_connector: $connector, source_kind: $kind})
        WHERE e.checkpoint_status = 'complete' AND e.source_updated_at = $max_updated
        RETURN max(e.source_row_id) AS max_id
        """,
        connector=SOURCE_CONNECTOR, kind=kind, max_updated=max_updated,
    ).single()
    return (max_updated, rec2["max_id"])


def _land_repository(session, job_id: str, row: dict) -> None:
    episode_id = f"application-code:repository:{row['id']}"

    def _write(tx):
        tx.run(
            """
            MERGE (e:Episode {id: $episode_id})
            SET e.source_connector = $connector, e.source_kind = 'repository',
                e.unit_id = $unit_id, e.job_id = $job_id, e.t_recorded = datetime(),
                e.checkpoint_status = 'complete', e.episode_type = 'RepositoryRegistered',
                e.source_row_id = $row_id, e.source_updated_at = $updated_at
            MERGE (r:Repository {id: $name})
            SET r.url = $url, r.source_episode_id = $episode_id
            """,
            episode_id=episode_id, connector=SOURCE_CONNECTOR,
            unit_id=f"repository:{row['name']}", job_id=job_id,
            row_id=row["id"], updated_at=row["updated_at"].isoformat(),
            name=row["name"], url=row["url"],
        )

    session.execute_write(_write)


def _land_source_file(session, job_id: str, row: dict) -> None:
    episode_id = f"application-code:source_file:{row['id']}"
    unit_id = f"source_file:{row['repository_name']}:{row['path']}"

    def _write(tx):
        tx.run(
            """
            MERGE (e:Episode {id: $episode_id})
            SET e.source_connector = $connector, e.source_kind = 'source_file',
                e.unit_id = $unit_id, e.job_id = $job_id, e.t_recorded = datetime(),
                e.checkpoint_status = 'complete', e.episode_type = 'CodeStructureExtracted',
                e.source_row_id = $row_id, e.source_updated_at = $updated_at,
                e.repository_name = $repo_name, e.path = $path, e.language = $language,
                e.raw_content = $content
            """,
            episode_id=episode_id, connector=SOURCE_CONNECTOR, unit_id=unit_id,
            job_id=job_id, row_id=row["id"], updated_at=row["updated_at"].isoformat(),
            repo_name=row["repository_name"], path=row["path"],
            language=row["language"], content=row["content"],
        )

    session.execute_write(_write)


def run(pg_dsn: str, neo4j_uri: str, neo4j_user: str, neo4j_password: str,
        database: str = "neo4j", job_id: str = "application-code-manual-run",
        on_unit=None) -> dict:
    """on_unit(kind, row) is called after each unit is durably landed --
    used by tests to observe/interrupt progress, and by a future daemon
    (Phase 9's ingestion-worker) to log progress."""
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    driver.verify_connectivity()
    landed = {"repository": 0, "source_file": 0}
    try:
        with driver.session(database=database) as session, psycopg.connect(pg_dsn) as pg:
            last_updated, last_id = _checkpoint(session, "repository")
            with pg.cursor(row_factory=psycopg.rows.dict_row) as cur:
                if last_updated is None:
                    cur.execute("SELECT * FROM athena.mv_repositories ORDER BY updated_at, id")
                else:
                    cur.execute(
                        "SELECT * FROM athena.mv_repositories "
                        "WHERE (updated_at, id) > (%s, %s) ORDER BY updated_at, id",
                        (last_updated, last_id),
                    )
                for row in cur.fetchall():
                    _land_repository(session, job_id, row)
                    landed["repository"] += 1
                    if on_unit:
                        on_unit("repository", row)

            last_updated, last_id = _checkpoint(session, "source_file")
            with pg.cursor(row_factory=psycopg.rows.dict_row) as cur:
                if last_updated is None:
                    cur.execute("SELECT * FROM athena.mv_source_files ORDER BY updated_at, id")
                else:
                    cur.execute(
                        "SELECT * FROM athena.mv_source_files "
                        "WHERE (updated_at, id) > (%s, %s) ORDER BY updated_at, id",
                        (last_updated, last_id),
                    )
                for row in cur.fetchall():
                    _land_source_file(session, job_id, row)
                    landed["source_file"] += 1
                    if on_unit:
                        on_unit("source_file", row)
    finally:
        driver.close()
    return landed


def main():
    import os
    from datetime import datetime, timezone

    from metis_mcp.config_manager import ConfigManager
    from connectors.seed_mock_athena import _dsn_from_config

    config = ConfigManager()
    pg_dsn = _dsn_from_config()
    neo4j_cfg = config.get_neo4j_config()
    neo4j_password = os.environ.get(neo4j_cfg.get("password_env", ""))
    if not (neo4j_cfg.get("uri") and neo4j_cfg.get("user") and neo4j_password):
        raise ValueError(
            f"graph.neo4j.{{uri,user,password_env}} must be set in {config.effective_path}, "
            f"and its password_env variable must be exported."
        )

    job_id = f"application-code-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    def _log(kind, row):
        label = row.get("name") or row.get("path")
        print(f"PROCESSED {kind} {label}", file=sys.stderr, flush=True)

    landed = run(pg_dsn, neo4j_cfg["uri"], neo4j_cfg["user"], neo4j_password, job_id=job_id, on_unit=_log)
    print(f"Landed {landed['repository']} repository unit(s), "
          f"{landed['source_file']} source_file unit(s) (job {job_id}).", file=sys.stderr)


if __name__ == "__main__":
    main()
