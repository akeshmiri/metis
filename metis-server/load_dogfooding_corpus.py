"""
One-off loader: parses the real dogfooding corpus with the exact same
corpus.py used by LocalGraphStore, then writes it into Neo4j as real
DogfoodingItem nodes -- this is what Phase 1's acceptance criterion means by
"load the dogfooding corpus into Neo4j via a one-off script" (PLAN.md).

Why DogfoodingItem, not the production ontology's Requirement/Constitution/
etc. labels: this corpus is Métis's own governance documents (Constitution
rules, DQ metrics, foolproof rules, security boundary rules, and this
platform's own REQ-METIS-* requirements) parsed by corpus.py's tag-based
extractor -- it is not a real EARS-tagged Requirement ingested by a real
connector. The schema's :Requirement label carries real existence
constraints (source_episode_id, ears_pattern) this content doesn't
genuinely have without fabricating them. DogfoodingItem is a distinct label
outside that ontology, carrying corpus.py's actual kind string as a
property instead of overloading a production label dishonestly. The real
production ontology gets populated for real starting at Phase 2/3 (a real
connector + Cognify extraction), not here.

Idempotent: MERGE on id, safe to re-run.
"""
import json
import sys
from datetime import datetime, timezone

from neo4j import GraphDatabase

from metis_mcp.config_manager import ConfigManager
from metis_mcp.corpus import parse_corpus

LABEL = "DogfoodingItem"
REL = "CITES"


def load(uri: str, user: str, password: str, corpus_glob: str, database: str = "neo4j") -> dict:
    all_nodes = parse_corpus(corpus_glob)
    conflicts = all_nodes.pop("__conflicts__")
    nodes = list(all_nodes.values())

    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    try:
        with driver.session(database=database) as s:
            episode_id = f"dogfooding-bootstrap-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            s.run(
                """
                CREATE (e:Episode {
                    id: $episode_id,
                    t_recorded: datetime(),
                    source_connector: 'dogfooding-corpus-loader',
                    job_id: $episode_id,
                    checkpoint_status: 'complete',
                    duplicate_definition_conflicts: $conflicts
                })
                """,
                episode_id=episode_id, conflicts=json.dumps(conflicts),
            )

            for n in nodes:
                s.run(
                    f"""
                    MERGE (item:{LABEL} {{id: $id}})
                    SET item.kind = $kind, item.text = $text,
                        item.source_file = $source_file, item.source_heading = $source_heading,
                        item.source_episode_id = $episode_id
                    """,
                    id=n.id, kind=n.kind, text=n.text,
                    source_file=n.source_file, source_heading=n.source_heading,
                    episode_id=episode_id,
                )

            edge_count = 0
            for n in nodes:
                for ref_id in n.references:
                    s.run(
                        f"""
                        MATCH (a:{LABEL} {{id: $from_id}}), (b:{LABEL} {{id: $to_id}})
                        MERGE (a)-[:{REL}]->(b)
                        """,
                        from_id=n.id, to_id=ref_id,
                    )
                    edge_count += 1

            return {
                "episode_id": episode_id,
                "nodes_loaded": len(nodes),
                "edges_loaded": edge_count,
                "conflicts": len(conflicts),
            }
    finally:
        driver.close()


def main():
    config = ConfigManager()
    corpus_glob = config.get_corpus_glob()
    if not corpus_glob:
        raise ValueError(f"corpus.glob is not set in {config.effective_path}")
    if not __import__("os").path.isabs(corpus_glob):
        corpus_glob = str(config.effective_path.parent.parent / corpus_glob)

    neo4j_cfg = config.get_neo4j_config()
    uri = neo4j_cfg.get("uri")
    user = neo4j_cfg.get("user")
    password_env = neo4j_cfg.get("password_env")
    if not (uri and user and password_env):
        raise ValueError(
            f"graph.neo4j.{{uri,user,password_env}} must all be set in {config.effective_path}"
        )
    import os
    password = os.environ.get(password_env)
    if not password:
        raise ValueError(f"Environment variable {password_env} is not set.")

    result = load(uri, user, password, corpus_glob)
    print(f"Loaded {result['nodes_loaded']} nodes, {result['edges_loaded']} CITES edges "
          f"from {corpus_glob} into Neo4j (episode {result['episode_id']}).", file=sys.stderr)
    if result["conflicts"]:
        print(f"  {result['conflicts']} duplicate-definition conflicts recorded on the episode node.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
