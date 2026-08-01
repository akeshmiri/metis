"""
Phase 6 tests for CONST-064's token lifecycle -- against a real Neo4j
instance, not mocked. Each test targets one specific clause of the spec:
"1-hour access / 30-day refresh, re-validated every request, not cached
from issuance."
"""
import os
import sys
import time

import jwt
from neo4j import GraphDatabase

from metis_mcp.oauth2 import (
    issue_token, validate_access_token, revoke_token, refresh_access_token,
    JWT_ALGORITHM,
)

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


def _make_user(user_id: str, owner_team: str):
    # execute_write, not bare session.run() -- see test_rbac.py's _setup()
    # comment for why (an unconsumed result can silently swallow a failure).
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MERGE (u:User {id: $id}) SET u.owner_team = $team", id=user_id, team=owner_team
        ).consume())


def _cleanup(user_id: str):
    with _session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (u:User {id: $id}) DETACH DELETE u", id=user_id
        ).consume())
        s.execute_write(lambda tx: tx.run(
            "MATCH (t:Token {user_id: $id}) DETACH DELETE t", id=user_id
        ).consume())


def test_issue_and_validate_access_token_succeeds():
    _make_user("user-a", "team-billing")
    try:
        with _session() as s:
            tokens = issue_token(s, SECRET, "user-a", "team-billing")
            result = validate_access_token(s, SECRET, tokens.access_token)
        assert result.valid
        assert result.user_id == "user-a"
        assert result.owner_team == "team-billing"
    finally:
        _cleanup("user-a")


def test_validate_rejects_unknown_token():
    with _session() as s:
        result = validate_access_token(s, SECRET, "not-a-real-jwt")
    assert not result.valid


def test_validate_rejects_expired_token():
    """Crafted directly (not waiting a real hour) -- exp in the past."""
    _make_user("user-b", "team-billing")
    try:
        expired = jwt.encode(
            {"sub": "user-b", "type": "access", "jti": "fake-jti", "iat": time.time() - 7200,
             "exp": time.time() - 3600},
            SECRET, algorithm=JWT_ALGORITHM,
        )
        with _session() as s:
            result = validate_access_token(s, SECRET, expired)
        assert not result.valid
        assert "expired" in result.reason.lower()
    finally:
        _cleanup("user-b")


def test_revoked_token_rejected_on_next_request():
    """The core Phase 6 acceptance bar: revoked on request N, rejected on
    request N+1 -- not just after natural expiry."""
    _make_user("user-c", "team-billing")
    try:
        with _session() as s:
            tokens = issue_token(s, SECRET, "user-c", "team-billing")
            first = validate_access_token(s, SECRET, tokens.access_token)
            assert first.valid

            payload = jwt.decode(tokens.access_token, SECRET, algorithms=[JWT_ALGORITHM])
            revoke_token(s, payload["jti"])

            second = validate_access_token(s, SECRET, tokens.access_token)
        assert not second.valid
        assert "revoked" in second.reason.lower()
    finally:
        _cleanup("user-c")


def test_owner_team_reevaluated_not_cached_from_issuance():
    """CONST-064's specific closed gap: a token issued while the user was on
    team-a must reflect team-b on the very next validation after the user's
    real team membership changes -- not the token's own embedded claim."""
    _make_user("user-d", "team-a")
    try:
        with _session() as s:
            tokens = issue_token(s, SECRET, "user-d", "team-a")
            before = validate_access_token(s, SECRET, tokens.access_token)
            assert before.owner_team == "team-a"

            s.run("MATCH (u:User {id: 'user-d'}) SET u.owner_team = 'team-b'")

            after = validate_access_token(s, SECRET, tokens.access_token)
        assert after.valid
        assert after.owner_team == "team-b", "must reflect CURRENT team membership, not the stale token claim"
    finally:
        _cleanup("user-d")


def test_refresh_issues_new_valid_access_token():
    _make_user("user-e", "team-billing")
    try:
        with _session() as s:
            tokens = issue_token(s, SECRET, "user-e", "team-billing")
            new_tokens = refresh_access_token(s, SECRET, tokens.refresh_token)
            result = validate_access_token(s, SECRET, new_tokens.access_token)
        assert result.valid
        assert new_tokens.access_token != tokens.access_token
    finally:
        _cleanup("user-e")


def test_refresh_rejected_if_refresh_token_revoked():
    _make_user("user-f", "team-billing")
    try:
        with _session() as s:
            tokens = issue_token(s, SECRET, "user-f", "team-billing")
            payload = jwt.decode(tokens.refresh_token, SECRET, algorithms=[JWT_ALGORITHM])
            revoke_token(s, payload["jti"])

            raised = False
            try:
                refresh_access_token(s, SECRET, tokens.refresh_token)
            except ValueError:
                raised = True
        assert raised
    finally:
        _cleanup("user-f")


if __name__ == "__main__":
    if not NEO4J_PASSWORD:
        print("METIS_NEO4J_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
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
    if _driver:
        _driver.close()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
