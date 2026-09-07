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


class SchemaUnavailable(Exception):
    """A UIF cannot be validated here, because the schema is not reachable."""


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
    # The row nobody thinks to add: whether the document contract is reachable
    # at all. A deployment that cannot open the schema validates nothing, and
    # until this line existed it said so nowhere.
    can_validate, why = uif_schema_available()
    lines += ["", f"  [{'ok ' if can_validate else 'NONE'}] uif-schema  "
                  f"validate a UIF against its declared shape"]
    if not can_validate:
        lines.append(f"           {why}")
    lines += ["", "None of these executes anything against the System Under "
                  "Test (X-7a)."]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Validating a UIF against its own schema.
#
# `metis-intake-processor/SKILL.md` told a reader "a UIF is validated against
# `../shared/schemas/unified-intake-format.schema.json` — 830 lines, and the
# machine-readable half of everything below", and **nothing in the engine opened
# that file**. The only reader in the tree was `test_independence.py`, which
# pulls the `source_system` enum out of it to check the port was complete. So the
# document shape was asserted by a skill and checked by nobody, which is the
# silent-success shape CLAUDE.md names: a claim that reads as a guarantee.
#
# This does not replace `intake_landing.conformance`. That asks the questions the
# schema cannot — whether the text is EARS-conformant, whether an anchor exists,
# what will land as a `Finding` — and it runs at landing time. This asks the
# narrower mechanical one, and it can be asked before anything is planned.
# --------------------------------------------------------------------------

def uif_schema_path() -> Path:
    """Where the UIF schema lives: with the skills, not with the server.

    It is the contract a *document producer* writes against, and the producers
    are the skills. `test_independence.py` already reads it from here.
    """
    return (Path(__file__).resolve().parents[2] / "plugins" / "metis"
            / "skills" / "shared" / "schemas"
            / "unified-intake-format.schema.json")


def uif_schema_available() -> tuple[bool, str]:
    """Whether a UIF can be validated here, and what is missing if not.

    The validator itself is never the missing half: `jsonschema` is a hard
    dependency of `mcp`, so anything that can run the server has it. What is
    genuinely absent in some deployments is the schema **file** — it ships in
    `plugins/`, beside the skills that write against it, and a
    `pip install metis-mcp-server` with no repository checked out beside it has
    the code and not the contract. That deployment must say it cannot validate
    rather than report a clean document.
    """
    path = uif_schema_path()
    if not path.exists():
        return False, (f"the UIF schema is not at {path} — it ships with "
                       f"`plugins/`, not with this package, so an install "
                       f"without the repository beside it cannot validate")
    return True, ""


def validate_uif(document: dict) -> list[dict]:
    """Every way a document departs from the UIF schema.

    Raises `SchemaUnavailable` rather than returning an empty list when the
    schema cannot be read — "no errors found" and "nothing looked" are different
    claims, and conflating them is exactly how the duplicate guard's `unknown`
    verdict gets read as `no_match`.
    """
    available, why = uif_schema_available()
    if not available:
        raise SchemaUnavailable(why)

    import jsonschema

    schema = json.loads(uif_schema_path().read_text())
    validator = jsonschema.Draft7Validator(schema)
    return [
        {"path": "/".join(str(p) for p in error.absolute_path) or "(document)",
         "message": error.message}
        # Sorted so the same document reports the same order twice running:
        # an unstable error list makes a diff between two runs unreadable.
        for error in sorted(validator.iter_errors(document),
                            key=lambda e: list(e.absolute_path))
    ]
