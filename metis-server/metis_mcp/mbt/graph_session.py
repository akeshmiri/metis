"""
Graph connection resolution (application spec PLT-002, PLT-003, PLT-005).

No configuration in code. The connection resolves from explicit arguments, then
environment, and **the password only ever from an environment variable** -- never
an argument, so it cannot land in shell history or a process listing.

There is deliberately no default password. A missing one is a halt with an
instruction, not a fallback: a system that connects with a guessed credential is
a system nobody can reason about.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass

DEFAULT_URI = "bolt://localhost:7687"
DEFAULT_USER = "neo4j"
PASSWORD_ENV = "METIS_NEO4J_PASSWORD"
URI_ENV = "METIS_NEO4J_URI"
USER_ENV = "METIS_NEO4J_USER"


class GraphNotConfigured(Exception):
    """Raised when a graph operation is requested without a usable connection."""


@dataclass(frozen=True)
class GraphConfig:
    uri: str
    user: str
    password: str

    @property
    def redacted(self) -> str:
        return f"{self.user}@{self.uri}"


def resolve(uri: str | None = None, user: str | None = None) -> GraphConfig:
    password = os.environ.get(PASSWORD_ENV, "")
    if not password:
        raise GraphNotConfigured(
            f"no graph password. Set {PASSWORD_ENV} in the environment.\n"
            f"  The password is never read from an argument, so it cannot reach "
            f"shell history or a process listing (spec PLT-005)."
        )
    return GraphConfig(
        uri=uri or os.environ.get(URI_ENV, DEFAULT_URI),
        user=user or os.environ.get(USER_ENV, DEFAULT_USER),
        password=password,
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
