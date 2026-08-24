"""
Graph connection resolution (application spec PLT-002, PLT-003, PLT-005).

No configuration in code. The connection resolves from explicit arguments, then
the environment, then a config file. A password is never an argument, so it
cannot reach shell history or a process listing.

There is deliberately no default password. A missing one is a halt with an
instruction, not a fallback: a system that connects with a guessed credential is
a system nobody can reason about.

**The config file, and what PLT-005 is actually protecting.** The rule is not
"the password must come from `os.environ`" -- it is that the secret must not
reach a process listing or shell history. `metis-server/.metis/config.yaml`
records the shape this project already settled on: `password_env` NAMES an
environment variable and the secret lives there, so a checked-in file carries
none. That path is tried first and is the one to use.

A literal `password` is read too, because `~/.metis/config.json` has one and
refusing it outright would mean nothing can connect at all. It is taken only
from a file whose owner alone can read it, and the run says on stderr that it
used one. A world-readable secret read in silence is worse than either
alternative.

**Notes go to stderr, never stdout.** This module is imported by
`metis_mcp.server`, where stdout is the JSON-RPC channel -- a `print` here would
corrupt the protocol for every MCP client.

**JSON only, and a YAML config is reported rather than skipped.**
`pyproject.toml` lists only what is imported, and a YAML parser for one config
file is a poor trade. But the project's own config *is* `.metis/config.yaml`, so
finding one and saying nothing would be the silent failure: "there is
configuration here I cannot read" is a different answer from "there is no
configuration", and only the first tells you why you are being asked for a
password you thought you had already set.

`graph.backend` is ignored. The v1 LocalGraphStore/Neo4jGraphStore split went
with the v1 engine; there is one path now.
"""
from __future__ import annotations

import json
import os
import stat
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

DEFAULT_URI = "bolt://localhost:7687"
DEFAULT_USER = "neo4j"
PASSWORD_ENV = "METIS_NEO4J_PASSWORD"
URI_ENV = "METIS_NEO4J_URI"
USER_ENV = "METIS_NEO4J_USER"


# Functions rather than module constants: `Path.home()` must not be frozen at
# import time, and a test needs to point these somewhere else without reloading
# the module.
CONFIG_PATH_ENV = "METIS_CONFIG_PATH"


def config_paths() -> tuple[Path, ...]:
    """Where a JSON config is looked for. First found wins; there is no merge.

    `METIS_CONFIG_PATH` names a file and, when set, is the **only** candidate.
    That is the deployment contract the Helm chart already writes
    (`values.yaml`: `/etc/metis/config/config.json`, mounted from the secret),
    and an explicit path that silently falls back to a home directory is how a
    pod ends up talking to whatever the node happened to have.

    Otherwise: project before host -- the resolution rule `.metis/config.yaml`'s
    own header states -- so a repository can override the machine it is checked
    out on.
    """
    named = os.environ.get(CONFIG_PATH_ENV, "").strip()
    if named:
        return (Path(named),)
    return (Path(".metis/config.json"), Path.home() / ".metis/config.json")


def unreadable_config_paths() -> tuple[Path, ...]:
    """Configuration this build can see and cannot parse."""
    return (Path(".metis/config.yaml"), Path.home() / ".metis/config.yaml")


class GraphNotConfigured(Exception):
    """Raised when a graph operation is requested without a usable connection."""


@dataclass(frozen=True)
class GraphConfig:
    uri: str
    user: str
    password: str
    # How the password was obtained: an environment variable name, or a file
    # path. Never the secret. Kept so a caller can say how it connected without
    # guessing, and so the literal-password case is inspectable in a test.
    password_source: str = PASSWORD_ENV

    @property
    def redacted(self) -> str:
        return f"{self.user}@{self.uri}"


# Said once per process, keyed by the file it is about. A command that opens two
# sessions resolved twice and printed the same advisory twice, which is how a
# notice becomes noise and then becomes invisible.
_ANNOUNCED: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key in _ANNOUNCED:
        return
    _ANNOUNCED.add(key)
    print(f"metis: {message}", file=sys.stderr)


def _owner_only(path: Path) -> bool:
    """True when neither group nor other can read the file."""
    return not (path.stat().st_mode & (stat.S_IRGRP | stat.S_IROTH))


def _load_config() -> tuple[dict | None, Path | None]:
    """The first readable JSON config, and where it came from."""
    for path in config_paths():
        try:
            raw = path.read_text()
        except OSError:
            continue
        try:
            return json.loads(raw), path
        except json.JSONDecodeError as e:
            # A halt, not a fall-through to the next candidate. Quietly using
            # the host file because the project one has a stray comma is how you
            # end up debugging the wrong machine.
            raise GraphNotConfigured(
                f"{path} is not valid JSON ({e}). Fix it or remove it — it is "
                f"not skipped, because skipping it would connect somewhere else "
                f"without saying so."
            ) from e
    return None, None


def _password_from_file(graph: dict, path: Path) -> tuple[str, str]:
    """`(password, source)` out of one `graph.neo4j` block, or `("", "")`."""
    named = str(graph.get("password_env") or "")
    if named:
        secret = os.environ.get(named, "")
        if not secret:
            raise GraphNotConfigured(
                f"{path} names {named!r} as the password variable (PLT-005), "
                f"and {named} is not set in the environment."
            )
        return secret, named

    literal = str(graph.get("password") or "")
    if not literal:
        return "", ""
    if not _owner_only(path):
        raise GraphNotConfigured(
            f"{path} holds a literal password and is readable beyond its owner. "
            f"Run `chmod 600 {path}`, or replace the `password` key with "
            f"`password_env` naming an environment variable (PLT-005)."
        )
    _warn_once(
        str(path),
        f"using the literal password in {path}. The convention here is "
        f"`password_env`: name a variable there and keep the secret in the "
        f"environment (PLT-005)."
    )
    return literal, str(path)


def _no_password_message() -> str:
    named = os.environ.get(CONFIG_PATH_ENV, "").strip()
    if named and not Path(named).exists():
        return (f"{CONFIG_PATH_ENV}={named} names a config file that does not "
                f"exist. It is not skipped: an explicit path falling back to a "
                f"home directory is how a deployment reads the wrong machine's "
                f"configuration.")
    lines = [
        f"no graph password. Set {PASSWORD_ENV} in the environment, or put a "
        f"`graph.neo4j.password_env` in one of:",
        *(f"    {path}" for path in config_paths()),
        f"  The password is never read from an argument, so it cannot reach "
        f"shell history or a process listing (spec PLT-005).",
    ]
    unreadable = [p for p in unreadable_config_paths() if p.exists()]
    if unreadable:
        # F-10: what was found and not used is named. Being asked for a password
        # while a config file sits there unread is the confusing case.
        lines.append(
            "  Found configuration this build cannot parse (JSON only, no YAML "
            "reader): " + ", ".join(str(p) for p in unreadable) + "."
        )
    return "\n".join(lines)


def resolve(uri: str | None = None, user: str | None = None) -> GraphConfig:
    """The connection, or a halt naming every place that was looked at.

    Environment beats file, so `METIS_NEO4J_PASSWORD=... <command>` still
    overrides a machine's stored configuration for one run.
    """
    password = os.environ.get(PASSWORD_ENV, "")
    source = PASSWORD_ENV if password else ""
    file_uri = file_user = ""

    data, path = _load_config()
    if data is not None:
        graph = (data.get("graph") or {}).get("neo4j") or {}
        file_uri = str(graph.get("uri") or "")
        file_user = str(graph.get("user") or "")
        if not password:
            password, source = _password_from_file(graph, path)

    if not password:
        raise GraphNotConfigured(_no_password_message())

    return GraphConfig(
        uri=uri or os.environ.get(URI_ENV) or file_uri or DEFAULT_URI,
        user=user or os.environ.get(USER_ENV) or file_user or DEFAULT_USER,
        password=password,
        password_source=source,
    )

@contextmanager
def session(uri: str | None = None, user: str | None = None):
    """Yield a Neo4j session, or halt with an actionable message.

    The driver import is deferred so every file-based command still runs with no
    database dependency at all -- which is what keeps the test suite fast.
    """
    config = resolve(uri, user)
    try:
        from neo4j import GraphDatabase
    except ImportError as e:  # pragma: no cover - environment-dependent
        raise GraphNotConfigured(
            "the neo4j driver is not installed; run: pip install neo4j"
        ) from e

    # **Notifications are deliberately NOT filtered.** The obvious tidy-up here
    # is to disable the `UNRECOGNIZED` classification: querying a graph that has
    # not been populated yet is a normal state (`entity render` before a
    # glossary is landed), and Neo4j answers with a multi-line notice per unknown
    # property key that buries the command's own message.
    #
    # That was tried and reverted. The same classification carries "label does
    # not exist" -- which is precisely how a query written against `:Transition`
    # announces that it matched nothing because the nodes carry `:ApiCall`. That
    # is the failure mode this codebase has been bitten by repeatedly, and it is
    # silent everywhere else. Trading it away to quieten an empty-graph notice is
    # the wrong side of the deal.
    #
    # If the noise needs solving, solve it where it is displayed, not by asking
    # the server to stop reporting.
    driver = GraphDatabase.driver(config.uri, auth=(config.user, config.password))

    try:
        with driver.session() as s:
            yield s
    finally:
        driver.close()


def count_written(result) -> int:
    """The `written` column of a `RETURN count(...) AS written`.

    Lives here because both writers need it and neither may import the other:
    `model_sources.landing` already imports from `mbt`, so the helper cannot sit
    on either side of that edge.

    A real driver always returns a `Result`; `None` only comes from a recording
    fake in a test, and crashing on one would make the writers untestable
    without a container. Zero is the honest answer there — the stub did not
    claim to write anything.
    """
    if result is None:
        return 0
    for row in result:
        return int(row["written"])
    return 0
