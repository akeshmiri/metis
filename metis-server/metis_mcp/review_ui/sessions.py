"""
Browser sessions for the review UI — the half a bearer token cannot serve.

**Why this exists at all.** `_identity` requires a verified credential for every
decision, which is right and which made the surface unusable in a browser: a
page navigation cannot carry an `Authorization` header, and the CSP omits
`script-src` deliberately, so no script can add one. The choice was between
relaxing the CSP to let JavaScript hold a token, and letting the server remember
who logged in. This is the second, because it keeps the credential out of
anything a page can read and leaves the CSP as strict as it was.

**Opaque, random, and in memory only.** A session id is 32 bytes from
`secrets.token_urlsafe`; it is not derived from the token, so it cannot be
reversed into one. The store dies with the process, which is correct for a tool
NF-4 describes as a single local instance — a review session that outlived the
server would be a credential nobody could revoke.

**The cookie carries no authority of its own.** It names a row in this store, and
the row holds the `Identity` that `api/auth.py` already verified. So there is
still exactly one authentication implementation: this remembers an answer, it
does not decide one.

`SameSite=Strict` and `HttpOnly` are both load-bearing. Strict is the CSRF
defence — a decision POST is state-changing and must not be reachable from
another origin's page — and HttpOnly keeps the id away from any script that
later gains a foothold.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

COOKIE = "metis_session"

# Long enough to review a queue without re-authenticating, short enough that an
# unattended terminal is not an open decision surface indefinitely.
LIFETIME = timedelta(hours=8)


@dataclass
class Session:
    identity: object
    expires_at: datetime


@dataclass
class SessionStore:
    """In-memory sessions. One per server process."""

    _rows: dict = field(default_factory=dict)

    def open(self, identity, now: datetime | None = None) -> str:
        """Record a verified identity and return the id that names it."""
        moment = now or datetime.now(timezone.utc)
        sid = secrets.token_urlsafe(32)
        self._rows[sid] = Session(identity=identity,
                                  expires_at=moment + LIFETIME)
        return sid

    def get(self, sid: str, now: datetime | None = None):
        """The identity behind a session id, or None.

        An expired row is deleted on read rather than left to accumulate. There
        is no sweeper: a process that never gets another request has nothing to
        sweep, and one that does will clear its own expired rows as it goes.
        """
        row = self._rows.get(sid or "")
        if row is None:
            return None
        if (now or datetime.now(timezone.utc)) >= row.expires_at:
            del self._rows[sid]
            return None
        return row.identity

    def close(self, sid: str) -> bool:
        """Log out. True when a session was actually removed."""
        return self._rows.pop(sid or "", None) is not None

    def __len__(self) -> int:
        return len(self._rows)


def cookie_value(header_value: str, name: str = COOKIE) -> str:
    """One cookie out of a `Cookie:` header, without importing http.cookies.

    Hand-parsed because `SimpleCookie` is lenient in ways that do not help here:
    it silently drops a malformed pair, and a session id is either present and
    well-formed or absent.
    """
    for part in (header_value or "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value.strip()
    return ""


def set_cookie(sid: str) -> str:
    """The `Set-Cookie` value. See the module docstring for why each flag."""
    return (f"{COOKIE}={sid}; HttpOnly; SameSite=Strict; Path=/; "
            f"Max-Age={int(LIFETIME.total_seconds())}")


def clear_cookie() -> str:
    return f"{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
