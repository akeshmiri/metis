"""
§8.1 Pinned core memory blocks -- metis_mcp/pinned_memory.py, against real
Neo4j fixtures: a High-risk Approved Constraint, an Open Incident, a
pinned BusinessRule, all reachable within 2 hops of a real Repository
"scope" node.
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.pinned_memory import (
    get_active_constraints, get_open_incidents, get_pinned_business_rules,
    pin_business_rule, assemble_pinned_context,
)

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

_driver = None


def _session():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver.session()


def _setup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (e:Episode {id: 'pm-test-episode'}) "
            "SET e.t_recorded = datetime(), e.source_connector = 'test', e.job_id = 'test'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MERGE (r:Repository {id: 'pm-test-repo'}) SET r.source_episode_id = 'pm-test-episode'"
        ).consume())

        s.execute_write(lambda tx: tx.run(
            "MERGE (c:Constraint {id: 'pm-test-constraint-inscope'}) "
            "SET c.source_episode_id = 'pm-test-episode', c.risk_tag = 'High', "
            "c.lifecycle_state = 'Approved', c.text = 'Payments must be idempotent.'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (r:Repository {id: 'pm-test-repo'}), (c:Constraint {id: 'pm-test-constraint-inscope'}) "
            "MERGE (r)-[:TRACES_TO]->(c)"
        ).consume())
        # Low-risk Constraint in scope -- must NOT be pinned.
        s.execute_write(lambda tx: tx.run(
            "MERGE (c:Constraint {id: 'pm-test-constraint-lowrisk'}) "
            "SET c.source_episode_id = 'pm-test-episode', c.risk_tag = 'Low', "
            "c.lifecycle_state = 'Approved', c.text = 'Minor.'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (r:Repository {id: 'pm-test-repo'}), (c:Constraint {id: 'pm-test-constraint-lowrisk'}) "
            "MERGE (r)-[:TRACES_TO]->(c)"
        ).consume())
        # High-risk Constraint entirely out of scope (no path from pm-test-repo).
        s.execute_write(lambda tx: tx.run(
            "MERGE (c:Constraint {id: 'pm-test-constraint-outofscope'}) "
            "SET c.source_episode_id = 'pm-test-episode', c.risk_tag = 'High', "
            "c.lifecycle_state = 'Approved', c.text = 'Unrelated.'"
        ).consume())

        s.execute_write(lambda tx: tx.run(
            "MERGE (i:Incident {id: 'pm-test-incident-open'}) SET i.source_episode_id = 'pm-test-episode', "
            "i.status = 'Open', i.text = 'Checkout latency spike.'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (r:Repository {id: 'pm-test-repo'}), (i:Incident {id: 'pm-test-incident-open'}) "
            "MERGE (r)-[:TRACES_TO]->(i)"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MERGE (i:Incident {id: 'pm-test-incident-closed'}) SET i.source_episode_id = 'pm-test-episode', "
            "i.status = 'Closed', i.text = 'Resolved already.'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (r:Repository {id: 'pm-test-repo'}), (i:Incident {id: 'pm-test-incident-closed'}) "
            "MERGE (r)-[:TRACES_TO]->(i)"
        ).consume())

        s.execute_write(lambda tx: tx.run(
            "MERGE (b:BusinessRule {id: 'pm-test-rule-unpinned'}) SET b.source_episode_id = 'pm-test-episode', "
            "b.corroboration_count = 1, b.text = 'Not pinned.'"
        ).consume())


def _cleanup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (n) WHERE n.id STARTS WITH 'pm-test-' DETACH DELETE n"
        ).consume())


def test_active_constraints_scoped_to_high_risk_approved_within_2_hops():
    with _session() as s:
        result = get_active_constraints(s, scope_id="pm-test-repo")
    ids = {c["id"] for c in result}
    assert "pm-test-constraint-inscope" in ids
    assert "pm-test-constraint-lowrisk" not in ids, "Low risk must be excluded"
    assert "pm-test-constraint-outofscope" not in ids, "unreachable from scope, must be excluded"


def test_open_incidents_scoped_and_status_filtered():
    with _session() as s:
        result = get_open_incidents(s, scope_id="pm-test-repo")
    ids = {i["id"] for i in result}
    assert "pm-test-incident-open" in ids
    assert "pm-test-incident-closed" not in ids


def test_pinned_business_rules_requires_explicit_pin():
    with _session() as s:
        before = get_pinned_business_rules(s)
        assert "pm-test-rule-unpinned" not in {r["id"] for r in before}

        pin_business_rule(s, "pm-test-rule-unpinned", pinned_by="test-human")
        after = get_pinned_business_rules(s)
        assert "pm-test-rule-unpinned" in {r["id"] for r in after}

        rec = s.run(
            "MATCH (b:BusinessRule {id: 'pm-test-rule-unpinned'}) RETURN b.pinned_by AS by"
        ).single()
        assert rec["by"] == "test-human"


def test_assemble_pinned_context_includes_all_3_blocks_unconditionally():
    with _session() as s:
        ctx = assemble_pinned_context(s, scope_id="pm-test-repo")
    assert any(c["id"] == "pm-test-constraint-inscope" for c in ctx.active_constraints)
    assert any(i["id"] == "pm-test-incident-open" for i in ctx.open_incidents)
    assert not ctx.overflow
    assert ctx.overflow_warning is None


def test_assemble_pinned_context_never_silently_truncates_on_overflow():
    with _session() as s:
        ctx = assemble_pinned_context(s, scope_id="pm-test-repo", token_cap=1)
    assert ctx.overflow is True
    assert ctx.overflow_warning is not None
    assert "never" not in ctx.overflow_warning  # sanity: not accidentally quoting a negation wrong
    # Nothing dropped despite overflow -- same 3 real items still present.
    assert any(c["id"] == "pm-test-constraint-inscope" for c in ctx.active_constraints)
    assert any(i["id"] == "pm-test-incident-open" for i in ctx.open_incidents)


if __name__ == "__main__":
    if not NEO4J_PASSWORD:
        print("METIS_NEO4J_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)
    _setup()
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    try:
        for t in tests:
            try:
                t()
                print(f"PASS {t.__name__}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {t.__name__}: {e}")
            except Exception as e:
                failures += 1
                print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    finally:
        _cleanup()
        if _driver:
            _driver.close()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
