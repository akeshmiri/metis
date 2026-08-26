"""
Authentication for the HTTP surface (PLT-005, N-13, O-4c).

**Why this exists before any endpoint does.** `review_ui` reads `X-Metis-User`
and `X-Metis-Role` and trusts them, and its own docstring says that is *"honest
for a localhost review tool and unacceptable for anything else"*. It binds
loopback, so the trust is bounded by the socket. An API that reaches a network
has no such bound: a trusted header there is an impersonation hole leading
directly into G1 and G2, and every audit record it produces is a record of
whoever the caller said they were.

**The file never contains a usable credential.** Tokens are stored as SHA-256
digests, so a leaked configuration file leaks nothing that can be replayed —
which is the difference between an incident and an inconvenience. `METIS_API_TOKENS`
names the file's PATH and never a secret, per PLT-005: a secret on a command line
is in the shell history, the process listing and any log that captures argv.

**What this deliberately is not.** No sessions, no refresh, no user database, no
password reset. §11.2 targets a single interactive operator and NF-4 states one
instance with no HA target; a bearer token checked against a file is proportionate
to that, and anything more would be a second authentication system to keep correct.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

TOKENS_ENV = "METIS_API_TOKENS"

# The header a client presents. `Authorization: Bearer <token>` rather than a
# bespoke header, so that every proxy, log scrubber and client library already
# knows it carries a secret and should not be echoed.
HEADER = "Authorization"
SCHEME = "Bearer"


class AuthenticationRequired(Exception):
    """No usable credential was presented. Answered with 401."""


class AuthenticationFailed(Exception):
    """A credential was presented and is not valid. Answered with 401.

    Distinct from `AuthenticationRequired` in the code and NOT in what the client
    is told: both produce the same response, because telling an attacker which
    half of the guess was right is free help.
    """


def digest(token: str) -> str:
    """The stored form of a token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _tokens_path() -> Path:
    configured = os.environ.get(TOKENS_ENV, "").strip()
    if not configured:
        raise AuthenticationRequired(
            f"the HTTP surface has no credential store: set {TOKENS_ENV} to a "
            f"file of `sha256<TAB>name<TAB>role` lines. It holds digests, never "
            f"tokens, so it is not itself a secret (PLT-005).")
    return Path(configured)


def load_principals(path: Path | None = None) -> dict[str, tuple[str, str]]:
    """`{digest: (name, role)}` from the configured file.

    Malformed lines are refused rather than skipped. A silently ignored line is a
    principal who believes they have access and does not, or — far worse — a
    typo in a role that quietly grants less than intended and is discovered when
    somebody cannot approve something at the moment they need to.
    """
    from metis_mcp.review.roles import ROLES

    target = path or _tokens_path()
    if not target.exists():
        raise AuthenticationRequired(f"no credential store at {target}")

    principals: dict[str, tuple[str, str]] = {}
    for number, raw in enumerate(target.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) != 3 or not all(parts):
            raise AuthenticationRequired(
                f"{target}:{number}: expected `sha256<TAB>name<TAB>role`")
        token_digest, name, role = parts
        if role not in ROLES:
            raise AuthenticationRequired(
                f"{target}:{number}: unknown role {role!r}; one of "
                f"{', '.join(ROLES)}")
        if len(token_digest) != 64:
            raise AuthenticationRequired(
                f"{target}:{number}: not a sha256 digest — store `digest(token)`, "
                f"never the token itself")
        principals[token_digest.lower()] = (name, role)
    if not principals:
        raise AuthenticationRequired(f"{target} defines no principals")
    return principals


def bearer_from(header_value: str) -> str:
    """The token out of an `Authorization` header."""
    value = (header_value or "").strip()
    if not value:
        raise AuthenticationRequired("no Authorization header")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != SCHEME.lower() or not token.strip():
        raise AuthenticationRequired(f"expected `{SCHEME} <token>`")
    return token.strip()


def authenticate(header_value: str, path: Path | None = None):
    """The `Identity` behind a credential, or a refusal.

    Compared with `hmac.compare_digest` over the DIGESTS. Comparing digests
    rather than tokens means the server never holds a replayable secret in
    memory; comparing in constant time means a wrong token cannot be narrowed
    down by how long the answer took.
    """
    from metis_mcp.review.roles import Identity

    principals = load_principals(path)
    presented = digest(bearer_from(header_value))

    for stored, (name, role) in principals.items():
        if hmac.compare_digest(stored, presented):
            return Identity(name=name, role=role)

    # Deliberately the same message as a malformed credential.
    raise AuthenticationFailed("the presented credential is not recognised")
