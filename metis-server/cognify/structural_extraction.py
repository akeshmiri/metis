"""
Phase 3: minimal Cognify pass -- purely structural extraction, no model
calls, no confidence tiering (that's Phase 4). Matches
metis-specification.md §9's code-vs-LLM principle: get the deterministic
half proven before adding the nondeterministic half.

Reads the raw CodeStructureExtracted Episodes Phase 2's application-code
connector landed (raw_content = actual file text, nothing else) and turns
each into real :Class/:Method nodes via Python's built-in `ast` module.

Deviation from the connector manifest, disclosed: the manifest names
Tree-sitter as the parser ("AST-parsed locally ... Tree-sitter,
deterministic per §9's code-vs-LLM table -- NOT an LLM extraction step").
This uses Python's stdlib `ast` module instead -- still a real, fully
deterministic AST parse of real source (no LLM involved either way), just
without pulling in the Tree-sitter grammar dependency for a single-language
(Python) first pass. Swapping the parser later doesn't change the
downstream node shape.

No fabrication: every property written here traces to a real field on the
parsed AST node (name, lineno) or the source Episode (source_file,
source_episode_id) -- nothing is a default/placeholder standing in for
data that wasn't actually extracted.
"""
import ast
import sys

from neo4j import GraphDatabase

SOURCE_CONNECTOR = "application-code"


def _extract(repo: str, path: str, content: str) -> dict:
    """Pure function, no I/O -- makes the 'known input -> exact expected
    shape' acceptance check straightforward to test directly."""
    tree = ast.parse(content)
    classes = []
    module_functions = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            methods = [
                {"name": n.name, "lineno": n.lineno, "id": f"{repo}:{path}:{node.name}.{n.name}"}
                for n in ast.iter_child_nodes(node)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            classes.append({
                "name": node.name, "lineno": node.lineno,
                "id": f"{repo}:{path}:{node.name}", "methods": methods,
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_functions.append({
                "name": node.name, "lineno": node.lineno,
                "id": f"{repo}:{path}:{node.name}",
            })

    return {"classes": classes, "module_functions": module_functions}


def _write(session, episode_id: str, repo: str, path: str, extraction: dict) -> dict:
    counts = {"classes": 0, "methods": 0, "module_functions": 0}

    def _tx(tx):
        # Each block runs in its own CALL subquery, deliberately isolated --
        # a real bug found by running this against actual files: chaining
        # UNWIND clauses linearly means an empty list at any point (e.g.
        # server.py has 0 classes; corpus.py's one class has 0 methods)
        # collapses the row stream to zero rows for everything chained
        # after it, silently dropping the module-functions write entirely.
        # Isolating each block in CALL (r, e) { ... } means one block's
        # empty list can't affect the other's execution.
        tx.run(
            """
            MATCH (r:Repository {id: $repo})
            MATCH (e:Episode {id: $episode_id})
            SET e.cognified_at = datetime()
            WITH r, e
            CALL (r, e) {
                UNWIND $classes AS c
                    MERGE (cls:Class {id: c.id})
                    SET cls.name = c.name, cls.source_file = $path, cls.lineno = c.lineno,
                        cls.source_episode_id = $episode_id
                    MERGE (r)-[:DEFINES]->(cls)
                    WITH c, cls
                    CALL (c, cls) {
                        UNWIND c.methods AS m
                            MERGE (meth:Method {id: m.id})
                            SET meth.name = m.name, meth.source_file = $path, meth.lineno = m.lineno,
                                meth.source_episode_id = $episode_id, meth.parent_class = c.id
                            MERGE (cls)-[:HAS_METHOD]->(meth)
                        RETURN count(*) AS method_writes
                    }
                RETURN count(*) AS class_writes
            }
            WITH r, e, class_writes
            CALL (r, e) {
                UNWIND $module_functions AS f
                    MERGE (fn:Method {id: f.id})
                    SET fn.name = f.name, fn.source_file = $path, fn.lineno = f.lineno,
                        fn.source_episode_id = $episode_id, fn.parent_class = null
                    MERGE (r)-[:DEFINES]->(fn)
                RETURN count(*) AS fn_writes
            }
            RETURN class_writes, fn_writes
            """,
            repo=repo, path=path, episode_id=episode_id,
            classes=extraction["classes"], module_functions=extraction["module_functions"],
        )

    session.execute_write(_tx)
    counts["classes"] = len(extraction["classes"])
    counts["methods"] = sum(len(c["methods"]) for c in extraction["classes"])
    counts["module_functions"] = len(extraction["module_functions"])
    return counts


def run(neo4j_uri: str, neo4j_user: str, neo4j_password: str, database: str = "neo4j",
        on_unit=None) -> dict:
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    driver.verify_connectivity()
    totals = {"episodes": 0, "classes": 0, "methods": 0, "module_functions": 0}
    try:
        with driver.session(database=database) as session:
            records = session.run(
                """
                MATCH (e:Episode {source_connector: $connector, source_kind: 'source_file'})
                WHERE e.checkpoint_status = 'complete' AND e.cognified_at IS NULL
                RETURN e.id AS episode_id, e.repository_name AS repo,
                       e.path AS path, e.raw_content AS content
                """,
                connector=SOURCE_CONNECTOR,
            )
            rows = list(records)
            for row in rows:
                extraction = _extract(row["repo"], row["path"], row["content"])
                counts = _write(session, row["episode_id"], row["repo"], row["path"], extraction)
                totals["episodes"] += 1
                totals["classes"] += counts["classes"]
                totals["methods"] += counts["methods"] + counts["module_functions"]
                totals["module_functions"] += counts["module_functions"]
                if on_unit:
                    on_unit(row["path"], counts)
    finally:
        driver.close()
    return totals


def main():
    import os
    from metis_mcp.config_manager import ConfigManager

    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    neo4j_password = os.environ.get(neo4j_cfg.get("password_env", ""))
    if not (neo4j_cfg.get("uri") and neo4j_cfg.get("user") and neo4j_password):
        raise ValueError(
            f"graph.neo4j.{{uri,user,password_env}} must be set in {config.effective_path}, "
            f"and its password_env variable must be exported."
        )

    def _log(path, counts):
        print(f"COGNIFIED {path}: {counts['classes']} class(es), "
              f"{counts['methods']} method(s), {counts['module_functions']} module function(s)",
              file=sys.stderr, flush=True)

    totals = run(neo4j_cfg["uri"], neo4j_cfg["user"], neo4j_password, on_unit=_log)
    print(f"Cognified {totals['episodes']} episode(s): {totals['classes']} Class node(s), "
          f"{totals['methods']} Method node(s) total.", file=sys.stderr)


if __name__ == "__main__":
    main()
