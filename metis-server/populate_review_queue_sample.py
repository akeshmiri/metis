"""
Phase 5: populates a few real Quarantine-tier items for the reviewer UI to
show, by resubmitting real Class/Method entities Phase 3 already extracted
back through Phase 4's real submit_candidate() gate at a mid-range
confidence -- these are genuinely real code entities (real id, real
source_file, real lineno), not fabricated review scenarios. triage_reason
is 'needs_second_source' because that's honestly true: the application-code
connector is currently these entities' only source, with no corroboration
(Layer 4) run against them yet.

Confidence values here are illustrative placeholders standing in for
Layer 6's real judge score, which doesn't exist yet -- disclosed here, not
hidden, exactly like server.py's other dogfooding-mode adaptations.
"""
import os
import sys

from neo4j import GraphDatabase

from guardrails.pipeline import submit_candidate
from metis_mcp.config_manager import ConfigManager

SAMPLE_SIZE = 3


def main():
    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    password = os.environ.get(neo4j_cfg.get("password_env", ""))
    if not password:
        raise ValueError(f"{neo4j_cfg.get('password_env')} is not set.")

    driver = GraphDatabase.driver(neo4j_cfg["uri"], auth=(neo4j_cfg["user"], password))
    try:
        with driver.session() as session:
            candidates = session.run(
                """
                MATCH (c:Class) WHERE c.lifecycle_state IS NULL
                RETURN c.id AS id, c.source_episode_id AS source_episode_id LIMIT $n
                """,
                n=SAMPLE_SIZE,
            ).data()
            if not candidates:
                print("No un-tiered Class entities available -- run Phase 2/3 first.", file=sys.stderr)
                return
            for c in candidates:
                result = submit_candidate(
                    session, "Class",
                    {"id": c["id"], "source_episode_id": c["source_episode_id"]},
                    confidence=0.72,  # illustrative -- see module docstring
                )
                # execute_write, not bare session.run() -- see
                # test_rbac.py's _setup() comment: an unconsumed
                # auto-commit result can silently swallow a write failure.
                session.execute_write(lambda tx, cid=c["id"]: tx.run(
                    "MATCH (n:Class {id: $id}) SET n.triage_reason = 'needs_second_source'", id=cid
                ).consume())
                print(f"{c['id']}: {result.tiering.tier.value} ({result.tiering.lifecycle_state})",
                      file=sys.stderr)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
