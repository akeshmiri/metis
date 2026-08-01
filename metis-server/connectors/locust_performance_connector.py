"""
Phase 7 (extended): the locust-performance connector
(connectors/metis-connector-locust-performance.json) -- deterministic AST
parsing of a real Locust load-test script (perf/locustfile.py, a genuine
HttpUser subclass testing Phase 5's real review_api_server.py, not
synthetic content), landing TestCase(type=performance) entities.

Per the manifest's explicit pitfall: "A Locust script targeting an Endpoint
with no corresponding graph entity should not silently create one --
flagged as an unresolved target (quarantine tier) rather than fabricating
an Endpoint node." This graph currently has no real :Endpoint entities (no
API-spec connector has been built), so every target is honestly reported
unresolved -- not a bug, the correct behavior given the real absence of
Endpoint data.
"""
import ast
import sys

from guardrails.pipeline import submit_candidate

SOURCE_CONNECTOR = "locust-performance"
UNRESOLVED_TARGET_CONFIDENCE = 0.7  # -> Quarantine, per the manifest's own rule
RESOLVED_TARGET_CONFIDENCE = 0.95   # -> auto_write, only when a real Endpoint match exists


def _extract_call_target(call: ast.Call) -> str | None:
    """self.client.get('/api/quarantine') -> '/api/quarantine'."""
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


def _extract_tasks(content: str) -> list[dict]:
    tree = ast.parse(content)
    tasks = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        is_http_user = any(
            (isinstance(b, ast.Name) and b.id == "HttpUser") or
            (isinstance(b, ast.Attribute) and b.attr == "HttpUser")
            for b in node.bases
        )
        if not is_http_user:
            continue
        for method in ast.iter_child_nodes(node):
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            weight = 1
            is_task = False
            for dec in method.decorator_list:
                if isinstance(dec, ast.Name) and dec.id == "task":
                    is_task = True
                elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "task":
                    is_task = True
                    if dec.args and isinstance(dec.args[0], ast.Constant):
                        weight = dec.args[0].value
            if not is_task:
                continue
            target = None
            for call in ast.walk(method):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) \
                        and call.func.attr in ("get", "post", "put", "delete", "patch"):
                    target = _extract_call_target(call)
                    break
            tasks.append({
                "class_name": node.name, "task_name": method.name,
                "weight": weight, "target": target,
            })
    return tasks


def run(locustfile_path: str, session, repo: str = "metis-server",
        episode_id: str = "locust-performance:manual") -> dict:
    with open(locustfile_path, encoding="utf-8") as f:
        content = f.read()
    tasks = _extract_tasks(content)

    resolved, unresolved = 0, 0
    for t in tasks:
        tc_id = f"{repo}:perf/locustfile.py:{t['class_name']}.{t['task_name']}"
        endpoint = None
        if t["target"]:
            rec = session.run(
                "MATCH (e:Endpoint) WHERE e.path = $path RETURN e.id AS id LIMIT 1", path=t["target"]
            ).single()
            endpoint = rec["id"] if rec else None

        confidence = RESOLVED_TARGET_CONFIDENCE if endpoint else UNRESOLVED_TARGET_CONFIDENCE
        result = submit_candidate(session, "TestCase",
                                   {"id": tc_id, "source_episode_id": episode_id, "type": "performance"},
                                   confidence=confidence)
        if result.written:
            if endpoint:
                session.execute_write(lambda tx, a=tc_id, b=endpoint: tx.run(
                    "MATCH (tc:TestCase {id: $a}), (e:Endpoint {id: $b}) MERGE (tc)-[:VERIFIES]->(e)",
                    a=a, b=b,
                ).consume())
                resolved += 1
            else:
                session.execute_write(lambda tx, a=tc_id, target=t["target"]: tx.run(
                    "MATCH (tc:TestCase {id: $a}) SET tc.triage_reason = 'unresolved_performance_target', "
                    "tc.attempted_target = $target", a=a, target=target,
                ).consume())
                unresolved += 1

    return {"total_tasks": len(tasks), "resolved": resolved, "unresolved": unresolved, "tasks": tasks}


def main():
    import os
    from neo4j import GraphDatabase
    from metis_mcp.config_manager import ConfigManager

    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    password = os.environ.get(neo4j_cfg.get("password_env", ""))
    if not password:
        raise ValueError(f"{neo4j_cfg.get('password_env')} must be set.")

    locustfile_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "perf", "locustfile.py")
    driver = GraphDatabase.driver(neo4j_cfg["uri"], auth=(neo4j_cfg["user"], password))
    try:
        with driver.session() as s:
            s.execute_write(lambda tx: tx.run(
                "MERGE (e:Episode {id: 'locust-performance:manual'}) "
                "SET e.t_recorded = datetime(), e.source_connector = 'locust-performance', e.job_id = 'manual'"
            ).consume())
            result = run(locustfile_path, s)
    finally:
        driver.close()
    print(f"Locust performance: {result['total_tasks']} task(s), {result['resolved']} resolved, "
          f"{result['unresolved']} unresolved (no matching Endpoint).", file=sys.stderr)


if __name__ == "__main__":
    main()
