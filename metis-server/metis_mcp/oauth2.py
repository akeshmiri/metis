"""
CONST-064's token lifecycle, implemented against real Neo4j (the single-
database decision -- no separate Postgres/Redis token store), per
`REQ-METIS-CPT-03`: "1-hour access tokens, 30-day revocable refresh tokens,
re-validated every request, not cached from issuance."

Scope, disclosed honestly: this implements the TOKEN LIFECYCLE contract
CONST-064 actually specifies and what its acceptance criteria test --
issuance, expiry, refresh, revocation, and per-request re-validation
against CURRENT team membership (not the token's own embedded claim, which
is exactly the gap CONST-064 closes: "scoping a token at issuance isn't the
same as scoping it for the token's entire lifetime"). It does NOT implement
the full interactive OAuth2 authorization-code/PKCE browser-redirect
consent flow (RFC 6749) -- that needs a real browser + identity provider
UI, out of scope for a backend service test. A real deployment would sit
this token issuance behind that flow, not replace it.

Tokens are JWTs (signed, so tamper-evident and self-describing) but
validity is NOT decided by the JWT alone -- every validation call re-checks
the Token node's revoked flag AND the User node's CURRENT owner_team in
Neo4j, exactly matching CONST-064's "not cached from issuance" requirement.

Operational note found while testing this for real against a live server:
PyJWT warns (InsecureKeyLengthWarning) if the HS256 signing secret is under
32 bytes, per RFC 7518 §3.2. security.jwt_secret_env's value must be a real
32+ byte random secret in any real deployment -- the short strings used in
this module's own tests are test-only and would trigger that same warning.
"""
import time
import uuid
from dataclasses import dataclass

import jwt

ACCESS_TOKEN_TTL_SECONDS = 60 * 60          # 1 hour, per CONST-064
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days, per CONST-064
JWT_ALGORITHM = "HS256"


@dataclass
class IssuedTokens:
    access_token: str
    refresh_token: str
    access_expires_at: float
    refresh_expires_at: float


@dataclass
class TokenValidationResult:
    valid: bool
    user_id: str | None = None
    owner_team: str | None = None  # the CURRENT team membership, re-looked-up, not the JWT's own claim
    reason: str = ""


def _encode(secret: str, jti: str, user_id: str, token_type: str, ttl_seconds: int) -> tuple[str, float]:
    now = time.time()
    exp = now + ttl_seconds
    token = jwt.encode(
        {"sub": user_id, "type": token_type, "jti": jti, "iat": now, "exp": exp},
        secret, algorithm=JWT_ALGORITHM,
    )
    return token, exp


def issue_token(session, secret: str, user_id: str, owner_team: str) -> IssuedTokens:
    """Requires a real :User node with this id and owner_team to already
    exist -- issuance doesn't fabricate a user's team membership, it reads it."""
    user = session.run("MATCH (u:User {id: $id}) RETURN u.owner_team AS team", id=user_id).single()
    if user is None:
        raise ValueError(f"No User node exists for id '{user_id}' -- cannot issue a token for an unknown user.")

    access_jti, refresh_jti = str(uuid.uuid4()), str(uuid.uuid4())
    access_token, access_exp = _encode(secret, access_jti, user_id, "access", ACCESS_TOKEN_TTL_SECONDS)
    refresh_token, refresh_exp = _encode(secret, refresh_jti, user_id, "refresh", REFRESH_TOKEN_TTL_SECONDS)

    # execute_write (a managed transaction), not a bare session.run() -- a
    # real bug found while building this: an unconsumed auto-commit
    # session.run() result is lazy, and if nothing forces it to complete
    # before the session closes, a failure (e.g. a constraint violation)
    # is silently swallowed instead of raised. execute_write guarantees
    # the write actually completes and errors actually propagate.
    def _write(tx):
        # MERGE, not CREATE -- jti is generated once in Python before this
        # (possibly-retried) transaction function runs; the neo4j driver's
        # execute_write can retry after a successful server-side commit (a
        # real, demonstrated edge case -- see metis_mcp/temporal.py). CREATE
        # would hit Token's real jti-uniqueness constraint on that retry;
        # MERGE makes the retry a safe no-op instead (the jti is
        # cryptographically random per real issuance, so a genuine
        # collision between two DIFFERENT issuances would still be
        # vanishingly unlikely and is not what this guards against).
        tx.run(
            """
            MERGE (a:Token {jti: $access_jti})
            ON CREATE SET a.user_id = $user_id, a.type = 'access',
                a.issued_at = $now, a.expires_at = $access_exp, a.revoked = false
            MERGE (r:Token {jti: $refresh_jti})
            ON CREATE SET r.user_id = $user_id, r.type = 'refresh',
                r.issued_at = $now, r.expires_at = $refresh_exp, r.revoked = false
            """,
            access_jti=access_jti, refresh_jti=refresh_jti, user_id=user_id,
            now=time.time(), access_exp=access_exp, refresh_exp=refresh_exp,
        )

    session.execute_write(_write)
    return IssuedTokens(access_token, refresh_token, access_exp, refresh_exp)


def validate_access_token(session, secret: str, token: str) -> TokenValidationResult:
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return TokenValidationResult(valid=False, reason="Token expired.")
    except jwt.InvalidTokenError:
        return TokenValidationResult(valid=False, reason="Token signature invalid or malformed.")

    if payload.get("type") != "access":
        return TokenValidationResult(valid=False, reason="Not an access token.")

    # Re-validated every request, per CONST-064 -- never trusts the decoded
    # payload alone. A revoked token fails here even though its signature
    # and expiry are both still technically valid.
    rec = session.run(
        "MATCH (t:Token {jti: $jti, type: 'access'}) RETURN t.revoked AS revoked, t.user_id AS user_id",
        jti=payload["jti"],
    ).single()
    if rec is None:
        return TokenValidationResult(valid=False, reason="Token not found (never issued, or store was reset).")
    if rec["revoked"]:
        return TokenValidationResult(valid=False, reason="Token has been revoked.")

    # The load-bearing CONST-064 behavior: owner_team is read fresh from the
    # User node on every call, not from the token's own (possibly stale)
    # claim -- if the user's team changed since issuance, this reflects that
    # immediately, without waiting for the token to expire.
    user = session.run("MATCH (u:User {id: $id}) RETURN u.owner_team AS team", id=rec["user_id"]).single()
    if user is None:
        return TokenValidationResult(valid=False, reason="Token's user no longer exists.")

    return TokenValidationResult(valid=True, user_id=rec["user_id"], owner_team=user["team"])


def revoke_token(session, jti: str) -> None:
    session.execute_write(
        lambda tx: tx.run("MATCH (t:Token {jti: $jti}) SET t.revoked = true", jti=jti).consume()
    )


def refresh_access_token(session, secret: str, refresh_token: str) -> IssuedTokens:
    try:
        payload = jwt.decode(refresh_token, secret, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Refresh token invalid: {e}")
    if payload.get("type") != "refresh":
        raise ValueError("Not a refresh token.")

    rec = session.run(
        "MATCH (t:Token {jti: $jti, type: 'refresh'}) RETURN t.revoked AS revoked, t.user_id AS user_id",
        jti=payload["jti"],
    ).single()
    if rec is None or rec["revoked"]:
        raise ValueError("Refresh token not found or revoked.")

    user = session.run("MATCH (u:User {id: $id}) RETURN u.owner_team AS team", id=rec["user_id"]).single()
    if user is None:
        raise ValueError("Refresh token's user no longer exists.")

    return issue_token(session, secret, rec["user_id"], user["team"])
