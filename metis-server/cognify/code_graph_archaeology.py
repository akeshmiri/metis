"""
Code-graph archaeology (docs/metis-code-graph-archaeology-extension.md):
CALLS/IMPORTS/INHERITS edges, extending Phase 3's structural-containment-only
Cognify pass. Deterministic AST parsing, per §9's code-vs-LLM table --
"call/import/inheritance extraction is a pure AST-parsing task, no judgment
involved."

Disclosed deviation from the doc's stated preference: it recommends
delegating this to an existing code-graph MCP tool (CodeGraphContext/
CodeGraph) rather than reimplementing resolution inside Cognify, "reuse a
maintained tool where the ecosystem has already solved the problem well."
No such tool is available in this environment -- built directly via
Python's `ast` module instead, consistent with Phase 3's own AST-vs-
Tree-sitter deviation for the same reason.

Resolution is real but deliberately bounded, not a full whole-program
symbol table:
  - INHERITS: `class Foo(Bar):` -> Foo INHERITS Bar, only when Bar is
    already a real :Class node in the graph (never fabricates a stub for
    an external/stdlib base class like `Exception` or `Enum`).
  - CALLS: a call site resolves to a real :Method node only when it's
    either (a) a bare name matching a real module-level function in the
    graph, or (b) a `self.foo()` call matching a real method on the
    enclosing class. Cross-file/cross-class call resolution beyond that
    is out of scope -- a real, disclosed boundary, not a silent gap.
  - IMPORTS: only intra-repo imports that resolve to an actually-cognified
    module in this same graph produce an edge -- importing `os`/`sys`/an
    external package never fabricates a stub Class for that package.
"""
import ast

from neo4j import GraphDatabase


def _module_path_to_file(module: str) -> str | None:
    """'metis_mcp.corpus' -> 'metis_mcp/corpus.py' -- only meaningful for
    this project's own package, not stdlib/third-party imports."""
    if not module or not module.startswith("metis_mcp"):
        return None
    return module.replace(".", "/") + ".py"


def _analyze_file(repo: str, path: str, content: str) -> dict:
    tree = ast.parse(content)
    inherits_edges = []   # (child_class_id, parent_class_name)
    imports = []          # resolved_file_path
    calls_edges = []      # (caller_method_id, callee_name, is_self_call)
    classes_in_file = []  # class_ids defined in this file -- IMPORTS' real source nodes

    module_level_functions = {
        n.name for n in ast.iter_child_nodes(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                f = _module_path_to_file(alias.name)
                if f:
                    imports.append(f)
        elif isinstance(node, ast.ImportFrom) and node.module:
            f = _module_path_to_file(node.module)
            if f:
                imports.append(f)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            class_id = f"{repo}:{path}:{node.name}"
            classes_in_file.append(class_id)
            for base in node.bases:
                if isinstance(base, ast.Name):
                    inherits_edges.append((class_id, base.id))

            class_methods = {
                n.name for n in ast.iter_child_nodes(node)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            for method_node in ast.iter_child_nodes(node):
                if not isinstance(method_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                method_id = f"{repo}:{path}:{node.name}.{method_node.name}"
                for call in ast.walk(method_node):
                    if not isinstance(call, ast.Call):
                        continue
                    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) \
                            and call.func.value.id == "self" and call.func.attr in class_methods:
                        calls_edges.append((method_id, f"{class_id}.{call.func.attr}", True))
                    elif isinstance(call.func, ast.Name) and call.func.id in module_level_functions:
                        calls_edges.append((method_id, f"{repo}:{path}:{call.func.id}", False))

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_id = f"{repo}:{path}:{node.name}"
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) \
                        and call.func.id in module_level_functions and call.func.id != node.name:
                    calls_edges.append((fn_id, f"{repo}:{path}:{call.func.id}", False))

    return {
        "inherits": inherits_edges, "imports": imports, "calls": calls_edges,
        "classes_in_file": classes_in_file,
    }


def _write_edges(session, repo: str, path: str, analysis: dict) -> dict:
    counts = {"inherits": 0, "imports": 0, "calls": 0}

    def _tx(tx):
        for child_id, parent_name in analysis["inherits"]:
            rec = tx.run(
                "MATCH (parent:Class {name: $name}) RETURN parent.id AS id LIMIT 1",
                name=parent_name,
            ).single()
            if rec is None:
                continue  # real base class not in graph (stdlib/external) -- never fabricated
            tx.run(
                "MATCH (child:Class {id: $child_id}), (parent:Class {id: $parent_id}) "
                "MERGE (child)-[:INHERITS]->(parent)",
                child_id=child_id, parent_id=rec["id"],
            )
            counts["inherits"] += 1

        # IMPORTS is schema-literally Class-[:IMPORTS]->Class -- source nodes
        # are every real Class defined in THIS file (files with zero classes,
        # e.g. server.py's module-level-only functions, genuinely can't
        # produce an IMPORTS edge under this literal schema; disclosed
        # limitation, not a bug).
        if analysis["classes_in_file"]:
            for imported_file in analysis["imports"]:
                targets = tx.run(
                    "MATCH (n:Class) WHERE n.source_file = $file RETURN n.id AS id",
                    file=imported_file,
                ).data()
                if not targets:
                    continue  # imported module not cognified in this graph -- never fabricated
                for src_id in analysis["classes_in_file"]:
                    for target in targets:
                        tx.run(
                            "MATCH (src:Class {id: $src_id}), (dst:Class {id: $dst_id}) "
                            "MERGE (src)-[:IMPORTS]->(dst)",
                            src_id=src_id, dst_id=target["id"],
                        )
                        counts["imports"] += 1

        for caller_id, callee_id, _is_self in analysis["calls"]:
            rec = tx.run("MATCH (m:Method {id: $id}) RETURN m.id AS id LIMIT 1", id=callee_id).single()
            if rec is None:
                continue  # real call site, but callee not a cognified Method -- never fabricated
            tx.run(
                "MATCH (caller:Method {id: $caller_id}), (callee:Method {id: $callee_id}) "
                "MERGE (caller)-[:CALLS]->(callee)",
                caller_id=caller_id, callee_id=callee_id,
            )
            counts["calls"] += 1

    session.execute_write(_tx)
    return counts


def run(neo4j_uri: str, neo4j_user: str, neo4j_password: str, database: str = "neo4j",
        on_unit=None) -> dict:
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    driver.verify_connectivity()
    totals = {"files": 0, "inherits": 0, "imports": 0, "calls": 0}
    try:
        with driver.session(database=database) as session:
            rows = session.run(
                """
                MATCH (e:Episode {source_connector: 'application-code', source_kind: 'source_file'})
                WHERE e.checkpoint_status = 'complete'
                RETURN e.repository_name AS repo, e.path AS path, e.raw_content AS content
                """
            ).data()
            for row in rows:
                analysis = _analyze_file(row["repo"], row["path"], row["content"])
                counts = _write_edges(session, row["repo"], row["path"], analysis)
                totals["files"] += 1
                totals["inherits"] += counts["inherits"]
                totals["imports"] += counts["imports"]
                totals["calls"] += counts["calls"]
                if on_unit:
                    on_unit(row["path"], counts)
    finally:
        driver.close()
    return totals


def main():
    import os
    import sys
    from metis_mcp.config_manager import ConfigManager

    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    password = os.environ.get(neo4j_cfg.get("password_env", ""))
    if not password:
        raise ValueError(f"{neo4j_cfg.get('password_env')} must be set.")

    def _log(path, counts):
        print(f"CODE-GRAPH {path}: {counts['inherits']} INHERITS, "
              f"{counts['imports']} IMPORTS, {counts['calls']} CALLS", file=sys.stderr, flush=True)

    totals = run(neo4j_cfg["uri"], neo4j_cfg["user"], password, on_unit=_log)
    print(f"Code-graph archaeology: {totals['files']} file(s) -- "
          f"{totals['inherits']} INHERITS, {totals['imports']} IMPORTS, {totals['calls']} CALLS edges.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
