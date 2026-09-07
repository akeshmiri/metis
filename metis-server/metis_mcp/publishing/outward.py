"""
The shared half of every write that leaves Métis.

Three connectors now write outward — Zephyr Scale, Jira, GitLab — and each needs
the same four things: the installation switch, a credential that never came from
an argument, an HTTP call with no third-party library, and a failure message that
distinguishes *refused* from *could not tell*. Written once here so the three
cannot drift into three different ideas of what a gate is.

**Two keys, always.** `publish.Transport.check_permitted` requires
`METIS_ALLOW_EXTERNAL_WRITES=yes` on the installation, and every gated flow
requires a literal in the run. The second exists because the first can be
supplied by whatever is driving the run, including an agent; the first exists
because a human set it on a machine.

**A failed lookup is never absence.** The rule the duplicate guard is built on,
and it belongs here because all three connectors check before they create.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT_SECONDS = 30


class OutwardWriteFailed(Exception):
    """The remote refused, or could not be reached. Nothing further is sent."""


class Unverifiable(OutwardWriteFailed):
    """A check that should have answered did not.

    Distinct from `OutwardWriteFailed` because the caller must treat it
    differently: a refusal is an answer, and this is the absence of one. Reading
    it as "nothing found" is how a duplicate gets created.
    """


def credential(env_name: str, what: str) -> str:
    """A secret from the environment, never from an argument (PLT-005).

    A token on a command line is in the shell history, the process listing, and
    any log that captures argv — which is why `METIS_NEO4J_PASSWORD` has always
    worked this way and why every connector here does too.
    """
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise OutwardWriteFailed(
            f"{what} needs {env_name} set in the environment. Nothing was sent.")
    return value


def request(method: str, url: str, *, token: str, body: dict | None = None,
            auth_scheme: str = "Bearer", extra_headers: dict | None = None):
    """One HTTP call, on the standard library.

    `requests` is not a Métis dependency and adding it to send a few JSON
    documents would be a fifth runtime dependency paid for by everyone who never
    publishes anything.
    """
    headers = {"Authorization": f"{auth_scheme} {token}",
               "Content-Type": "application/json"}
    headers.update(extra_headers or {})
    data = json.dumps(body).encode("utf-8") if body is not None else None

    try:
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=headers)
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8") or "{}"
    except urllib.error.HTTPError as e:
        # The status and the remote's reason — never the request body, which
        # carries the content and sits beside an Authorization header, and this
        # string ends up in logs.
        raise OutwardWriteFailed(
            f"{method} {_safe(url)} refused with {e.code}: {e.reason}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise OutwardWriteFailed(
            f"{method} {_safe(url)} could not be reached: {e}. Whether the "
            f"write landed is UNKNOWN — check before retrying, because a retry "
            f"after one that landed creates a duplicate.") from None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise OutwardWriteFailed(
            f"{method} {_safe(url)} returned a body that is not JSON") from None


def lookup(method: str, url: str, *, token: str, auth_scheme: str = "Bearer",
           extra_headers: dict | None = None):
    """A check-before-create read. Any failure is `Unverifiable`, never empty."""
    try:
        return request(method, url, token=token, auth_scheme=auth_scheme,
                       extra_headers=extra_headers)
    except OutwardWriteFailed as e:
        raise Unverifiable(
            f"could not check what already exists: {e}. A failed lookup is not "
            f"evidence of absence, so nothing was created.") from None


def quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _safe(url: str) -> str:
    """A URL with any embedded credential and query string removed."""
    return url.split("?")[0]
