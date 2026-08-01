"""
Phase 6 tests for RBAC scoping (REQ-METIS-CPT-03 / BS-005) -- against real
Neo4j, real tokens, real nodes. Targets the exact acceptance bar PLAN.md
states: "A token issued for one team cannot retrieve another team's
owner_team-scoped nodes, even with a known node id."
"""
import os
import sys

from neo4j import GraphDatabase

from metis_mcp.oauth2 import issue_token, validate_access_token
from metis_mcp.rbac import get_scoped_node

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")
SECRET = "test-signing-secret-not-for-production"

_driver = None


def _session():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver.session()


def _setup():
    # execute_write, not bare session.run() -- an unconsumed auto-commit
    # result is lazy, and a failure (this hit the Service.source_episode_id
    # existence constraint the first time this was written) is silently
    # swallowed instead of raised if nothing forces it to complete before
    # the session closes. execute_write guarantees real completion/errors.
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (u:User {id: 'rbac-user-billing'}) SET u.owner_team = 'billing'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MERGE (u:User {id: 'rbac-user-payments'}) SET u.owner_team = 'payments'"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MERGE (svc:Service {id: 'rbac-test-svc-billing'}) "
            "SET svc.owner_team = 'billing', svc.name = 'billing-api', "
            "svc.source_episode_id = 'rbac-test-fixture'"
        ).consume())


def _cleanup():
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (u:User) WHERE u.id STARTS WITH 'rbac-user-' DETACH DELETE u"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (t:Token) WHERE t.user_id STARTS WITH 'rbac-user-' DETACH DELETE t"
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (svc:Service {id: 'rbac-test-svc-billing'}) DETACH DELETE svc"
        ).consume())


def _token_for(user_id: str):
    with _session() as s:
        tokens = issue_token(s, SECRET, user_id, session_owner_team(s, user_id))
        return validate_access_token(s, SECRET, tokens.access_token)


def session_owner_team(session, user_id: str) -> str:
    rec = session.run("MATCH (u:User {id: $id}) RETURN u.owner_team AS t", id=user_id).single()
    return rec["t"]


def test_same_team_access_allowed():
    token = _token_for("rbac-user-billing")
    with _session() as s:
        result = get_scoped_node(s, token, "rbac-test-svc-billing")
    assert result.allowed
    assert result.node["id"] == "rbac-test-svc-billing"


def test_cross_team_access_denied_even_with_known_node_id():
    """The flagship Phase 6 acceptance criterion: a real, known node id,
    real valid token for a DIFFERENT team -- denied, not silently allowed."""
    token = _token_for("rbac-user-payments")
    with _session() as s:
        result = get_scoped_node(s, token, "rbac-test-svc-billing")
    assert not result.allowed
    assert result.node is None
    assert "billing" in result.reason and "payments" in result.reason


def test_invalid_token_denied():
    from metis_mcp.oauth2 import TokenValidationResult
    invalid = TokenValidationResult(valid=False, reason="fabricated for this test")
    with _session() as s:
        result = get_scoped_node(s, invalid, "rbac-test-svc-billing")
    assert not result.allowed


def test_nonexistent_node_denied():
    token = _token_for("rbac-user-billing")
    with _session() as s:
        result = get_scoped_node(s, token, "does-not-exist-at-all")
    assert not result.allowed
    assert result.node is None


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
