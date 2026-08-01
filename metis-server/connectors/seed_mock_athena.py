"""
Seeds the mock Athena Postgres (mock_athena_schema.sql) with real content --
this codebase's own metis_mcp/*.py files, read from disk for real, not
invented sample text. Idempotent: ON CONFLICT DO UPDATE, safe to re-run
(re-running with unchanged files updates rows' updated_at only if content
actually changed -- see the WHERE clause below -- so it doesn't defeat
the connector's own incremental-sync test).
"""
import glob
import os
import sys

import psycopg

REPO_NAME = "metis-server"
REPO_URL = "file://" + os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def seed(dsn: str):
    src_dir = os.path.join(os.path.dirname(__file__), "..", "metis_mcp")
    files = sorted(
        f for f in glob.glob(os.path.join(src_dir, "*.py"))
        if os.path.getsize(f) > 0  # __init__.py is empty, nothing to extract
    )

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO athena.mv_repositories (name, url, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (name) DO UPDATE SET updated_at = now()
                WHERE athena.mv_repositories.url IS DISTINCT FROM EXCLUDED.url
                """,
                (REPO_NAME, REPO_URL),
            )
            for f in files:
                path = os.path.relpath(f, os.path.join(src_dir, ".."))
                with open(f, encoding="utf-8") as fh:
                    content = fh.read()
                cur.execute(
                    """
                    INSERT INTO athena.mv_source_files
                        (repository_name, path, content, language, updated_at)
                    VALUES (%s, %s, %s, 'python', now())
                    ON CONFLICT (repository_name, path) DO UPDATE
                        SET content = EXCLUDED.content, updated_at = now()
                        WHERE athena.mv_source_files.content IS DISTINCT FROM EXCLUDED.content
                    """,
                    (REPO_NAME, path, content),
                )
        conn.commit()
    print(f"Seeded mock Athena: 1 repository ({REPO_NAME}), {len(files)} real source files.",
          file=sys.stderr)


def _dsn_from_config() -> str:
    from metis_mcp.config_manager import ConfigManager

    cfg = ConfigManager().get_connector_config("application_code").get("athena", {})
    password = os.environ.get(cfg.get("password_env", ""))
    if not (cfg and password):
        raise ValueError(
            "connectors.application_code.athena must be set in .metis/config.yaml, "
            "and its password_env variable must be exported."
        )
    return (f"postgresql://{cfg['user']}:{password}@{cfg['host']}:{cfg['port']}/{cfg['dbname']}")


if __name__ == "__main__":
    seed(_dsn_from_config())
