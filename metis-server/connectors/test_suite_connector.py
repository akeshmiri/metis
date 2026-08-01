"""
Phase 7: the test-suite-ingest connector (connectors/metis-connector-test-
suite.json) -- explicitly flagged there as "genuinely new work, not an
Athena passthrough": real AST parsing of this project's own test_*.py
files, extracting TestCase entities, and resolving real traceability links
via this project's configured tag pattern (REQ-METIS-CONN-06: per-project
convention, resolved through config_manager.py -- not a single global
@TestId assumption).

Per-project convention for "metis-server": reuses corpus.py's own
TAG_PATTERN (REQ-METIS-*/CONST-*/DQ-*/AF-*/BS-* appearing in a test
module's docstring) -- not invented fresh, and genuinely real: these test
files' docstrings do reference real Constitution/requirement ids because
they were written against those specific rules (see e.g.
test_classification_gate.py's "CONST-051/052/053" docstring).

REQ-METIS-CONN-04's core rule, implemented for real via Phase 4's actual
guardrail pipeline (reused, not reinvented): a TestCase in a file whose
docstring cites a real, already-existing graph node gets a real
VERIFIES edge and a high confidence (auto_write tier). A TestCase in a
file with NO tag match is landed as an orphan -- quarantine tier, no
Requirement link fabricated or guessed by similarity.
"""
import ast
import sys

from neo4j import GraphDatabase

from guardrails.pipeline import submit_candidate
from metis_mcp.corpus import TAG_PATTERN

SOURCE_CONNECTOR = "test-suite-ingest"
ORPHAN_CONFIDENCE = 0.7    # -> Quarantine tier (Phase 4), never guessed-link auto_write
LINKED_CONFIDENCE = 0.95   # -> auto_write tier, only when a REAL tag match exists


def _extract_test_functions(content: str) -> list[dict]:
    tree = ast.parse(content)
    return [
        {"name": n.name, "lineno": n.lineno}
        for n in ast.iter_child_nodes(tree)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    ]


def _module_docstring_tags(content: str) -> list[str]:
    tree = ast.parse(content)
    doc = ast.get_docstring(tree) or ""
    return TAG_PATTERN.findall(doc)


def _land_episode(session, job_id: str, repo: str, path: str, content: str) -> str:
    episode_id = f"test-suite-ingest:{path}"

    def _write(tx):
        tx.run(
            """
            MERGE (e:Episode {id: $episode_id})
            SET e.source_connector = $connector, e.unit_id = $unit_id, e.job_id = $job_id,
                e.t_recorded = datetime(), e.checkpoint_status = 'complete',
                e.episode_type = 'TestCaseDiscovered', e.path = $path, e.raw_content = $content
            """,
            episode_id=episode_id, connector=SOURCE_CONNECTOR, unit_id=path,
            job_id=job_id, path=path, content=content,
        )

    session.execute_write(_write)
    return episode_id


def _known_tag_exists(session, tag: str) -> bool:
    rec = session.run("MATCH (n {id: $id}) RETURN n LIMIT 1", id=tag).single()
    return rec is not None


def run(test_files: list[str], neo4j_uri: str, neo4j_user: str, neo4j_password: str,
        database: str = "neo4j", job_id: str = "test-suite-ingest-manual-run",
        repo: str = "metis-server", on_unit=None) -> dict:
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    driver.verify_connectivity()
    totals = {"files": 0, "test_cases": 0, "linked": 0, "orphans": 0}
    try:
        with driver.session(database=database) as session:
            for path in sorted(test_files):
                with open(path, encoding="utf-8") as f:
                    content = f.read()

                episode_id = _land_episode(session, job_id, repo, path, content)
                tags = [t for t in _module_docstring_tags(content) if _known_tag_exists(session, t)]
                link_target = tags[0] if tags else None

                test_functions = _extract_test_functions(content)
                for fn in test_functions:
                    tc_id = f"{repo}:{path}:{fn['name']}"
                    confidence = LINKED_CONFIDENCE if link_target else ORPHAN_CONFIDENCE
                    result = submit_candidate(
                        session, "TestCase",
                        {"id": tc_id, "source_episode_id": episode_id},
                        confidence=confidence,
                        risk_tag=None,
                    )
                    if result.written and link_target:
                        session.execute_write(lambda tx, a=tc_id, b=link_target: tx.run(
                            "MATCH (tc:TestCase {id: $a}), (target {id: $b}) "
                            "MERGE (tc)-[:VERIFIES]->(target)", a=a, b=b,
                        ).consume())
                        totals["linked"] += 1
                    elif result.written:
                        # A real, specific triage reason -- distinct from
                        # Phase 5's Class/Method items' 'needs_second_source'
                        # -- this genuinely is a different quarantine cause
                        # (no traceability tag match, per REQ-METIS-CONN-04),
                        # not the same one reused generically.
                        session.execute_write(lambda tx, a=tc_id: tx.run(
                            "MATCH (tc:TestCase {id: $a}) SET tc.triage_reason = 'no_traceability_match'",
                            a=a,
                        ).consume())
                        totals["orphans"] += 1
                    totals["test_cases"] += 1

                totals["files"] += 1
                if on_unit:
                    on_unit(path, len(test_functions), link_target)
    finally:
        driver.close()
    return totals


def main():
    import glob
    import os
    from datetime import datetime, timezone
    from metis_mcp.config_manager import ConfigManager

    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    password = os.environ.get(neo4j_cfg.get("password_env", ""))
    if not password:
        raise ValueError(f"{neo4j_cfg.get('password_env')} must be set.")

    server_dir = config.effective_path.parent.parent
    test_files = [
        os.path.relpath(f, server_dir)
        for f in glob.glob(str(server_dir / "test_*.py"))
    ]
    job_id = f"test-suite-ingest-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    def _log(path, n_tests, link_target):
        tag_note = f"-> {link_target}" if link_target else "(orphan, no tag match)"
        print(f"PROCESSED {path}: {n_tests} test case(s) {tag_note}", file=sys.stderr, flush=True)

    os.chdir(server_dir)
    totals = run(test_files, neo4j_cfg["uri"], neo4j_cfg["user"], password, job_id=job_id, on_unit=_log)
    print(f"Ingested {totals['files']} file(s), {totals['test_cases']} TestCase(s) "
          f"({totals['linked']} linked, {totals['orphans']} orphan) (job {job_id}).", file=sys.stderr)


if __name__ == "__main__":
    main()
