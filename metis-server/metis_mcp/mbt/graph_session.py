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

    driver = GraphDatabase.driver(config.uri, auth=(config.user, config.password))
    try:
        with driver.session() as s:
            yield s
    finally:
        driver.close()
