"""
What Métis reads, loaded rather than described (spec §5.0, X-7a).

`connectors/` already held seven manifests and a JSON Schema, and **nothing ever
opened them.** They declare an `athena_internal_read` protocol against entity
types the current ontology does not have. Its own README says so: *"a directory of
plausible configuration implies a feature, and finding out by running it is worse
than being told."*

So this one has a reader, and `test_intakes.py` checks the declaration against the
code — the registered sources, the intake anchors, the label catalogue. A
declaration that drifts fails, which is the only thing that stops it becoming the
eighth stale manifest.

**X-7a, the rule it exists to enforce: Métis never executes anything against the
System Under Test.** It reads from intake sources and writes to its own graph. It
does not call the API it models, drive the UI it models, or run a query against
the database it models. Every access mode in the schema is read-only by
construction and `executes_against_sut` is a constant `false`, so claiming
otherwise is a schema error rather than a judgement somebody makes under pressure.

The distinction that does the work: **a database Métis reads is an intake source;
the same database reached to check a test's outcome is the SUT.** Same server,
different act, and only the first is Métis's.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

INTAKES_VERSION = "metis.intakes/1"

WORKING = "working"
PARTIAL = "partial"
DECLARED = "declared"

# Read-only by construction, each of them. There is deliberately no mode for
# "runs something" — adding one would be the change that needs arguing for.
ACCESS_MODES = ("local_files", "read_only_connection", "authored_file",
                "uif_document")


class IntakesRefused(Exception):
    """The declaration could not be read at all — shape, not content."""


def _root() -> Path:
    """`connectors/`, beside the repository root rather than inside the server.

    It is configuration about the estate, not about this package, and it sits
    where the manifests it supersedes already sit.
    """
    return Path(__file__).resolve().parents[2] / "connectors"


@lru_cache(maxsize=1)
def load(path: str | Path = "") -> dict:
    """The declaration, with the two invariants a schema cannot express checked.

    Nothing here consults the network or a database. Loading a description of
    what Métis may read is not itself a read of anything.
    """
    target = Path(path) if path else _root() / "intakes.json"
    if not target.exists():
        raise IntakesRefused(f"no intake declaration at {target}")

    data = json.loads(target.read_text())
    version = data.get("intake_version")
    if version != INTAKES_VERSION:
        raise IntakesRefused(
            f"unknown intake_version {version!r}; this build reads "
            f"{INTAKES_VERSION!r}")

    seen: set[str] = set()
    for intake in data.get("intakes", []):
        name = intake.get("id", "")
        if not name or name in seen:
            raise IntakesRefused(f"duplicate or missing intake id {name!r}")
        seen.add(name)
        if intake.get("executes_against_sut") is not False:
            # The one line in this module that is a policy rather than a parse.
            raise IntakesRefused(
                f"intake {name!r} claims it executes against the System Under "
                f"Test. X-7a forbids it: Métis reads intake sources and writes "
                f"its own graph, and nothing else")
        if intake.get("access") not in ACCESS_MODES:
            raise IntakesRefused(
                f"intake {name!r} declares access {intake.get('access')!r}; "
                f"known modes are {', '.join(ACCESS_MODES)}, all read-only")
    return data


def all_intakes() -> list[dict]:
    return list(load().get("intakes", []))


def get(intake_id: str) -> dict | None:
    return next((i for i in all_intakes() if i["id"] == intake_id), None)


def by_status(status: str) -> list[dict]:
    return [i for i in all_intakes() if i.get("status") == status]


def describe() -> str:
    """The capability map, as a person would want to read it.

    `declared` is listed with the rest rather than hidden: an intake with no
    reader is the most useful row in the table, because it is the one somebody
    would otherwise assume works.
    """
    lines = ["Intakes — what Métis reads", ""]
    order = {WORKING: 0, PARTIAL: 1, DECLARED: 2}
    for intake in sorted(all_intakes(),
                         key=lambda i: (order.get(i["status"], 9), i["id"])):
        mark = {WORKING: "ok ", PARTIAL: "part", DECLARED: "NONE"}[intake["status"]]
        lines.append(f"  [{mark}] {intake['id']:<10} {intake['reads'][:62]}")
        if intake["status"] == DECLARED:
            lines.append(f"           no reader — the capability does not exist")
        for limit in intake.get("limits", ())[:2]:
            lines.append(f"           · {limit[:70]}")
    lines += ["", "None of these executes anything against the System Under "
                  "Test (X-7a)."]
    return "\n".join(lines)
