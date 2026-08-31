"""
Per-project graph storage: the Cypher a project can be restored from.

**What this changes about rebuilding.** The rule used to be re-ingest and never
migrate, and three places in the tree cite `RD-9` for it. That citation is wider
than the rule: RD-9 belonged to the v1 -> v2 engine migration, which completed at
`61814dc`, and it said "do not write scripts to transform v1 nodes into v2 nodes,
re-extract instead". It never said a project may not keep a restore file. The
rule now is: **restore from the stored Cypher when one is available and matches,
re-ingest when it is not.**

**Why a file is worth having.** Re-ingesting Athena means a Joern CPG over 493
files and seven workflow runs. That is the right thing when the code has moved,
and pure waste when it has not -- the graph is being rebuilt because somebody
dropped a container, not because the service changed.

**Why it is per project and not one dump.** One database holds every project a
deployment has ingested. A single dump would restore Athena by also restoring
everything else, and could not be committed next to the code it describes. The
files live at `<repo>/.metis/storage/`, beside the profile and the academy --
the same place the rest of a project's authored half already lives.

**The staleness guard is the whole design.** A restore file is a second copy of
facts whose real source is the code, and the failure it invites is restoring
yesterday's graph over today's checkout and believing it. So the manifest records
the commit, the ontology, and the counts; `verify` compares them; and
`rebuild_graph.sh` re-ingests rather than restoring when they disagree. A stale
file is never silently preferred.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

STORAGE_VERSION = "metis.storage/1"
MANIFEST = "manifest.json"
GRAPH_FILE = "graph.cypher"
SCHEMA_FILES = ("schema-01-constraints.cypher", "schema-02-relationships.cypher")

# Cypher map keys are identifiers. Every Métis property name is one already
# (`c_trigger`, `f_owner_type`, `m_project`); anything else is back-ticked rather
# than assumed safe, because a property named by a source we do not control is
# exactly where an injection would enter.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Neo4j temporal types -> the Cypher function that reconstructs them. Keyed by
# class name so this module does not import the driver just to isinstance
# against it; the `iso_format` check below is what actually guards the cast.
_TEMPORALS = {
    "DateTime": "datetime", "Date": "date", "Time": "time",
    "LocalDateTime": "localdatetime", "LocalTime": "localtime",
    "Duration": "duration",
}


class StorageRefused(Exception):
    """The export or the restore could not be done, and why."""


def storage_dir(repo: str | Path) -> Path:
    """`<repo>/.metis/storage` — beside the profile and the academy."""
    return Path(repo) / ".metis" / "storage"


# ---------------------------------------------------------------------------
# Cypher literals
# ---------------------------------------------------------------------------

def cypher_literal(value) -> str:
    """A Python value as a Cypher literal.

    **`json.dumps` for strings, deliberately.** JSON string escaping is a subset
    of Cypher's -- `\\"`, `\\\\`, `\\n`, `\\uXXXX` all mean the same thing in both --
    so the encoder that already exists is the correct one, and hand-rolling
    quote-doubling is how a newline or a backslash in recovered source text
    silently truncates a statement.

    Maps are emitted with BARE keys because Cypher map literals do not accept
    quoted ones: `{id: "x"}` parses and `{"id": "x"}` does not.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):                    # before int: bool IS an int
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(cypher_literal(v) for v in value) + "]"
    # Neo4j temporals come back as `neo4j.time.*` and are NOT strings: writing
    # one as a quoted string would restore a DateTime property as text, and
    # every later comparison against it would silently stop matching. Each has a
    # constructor function of the same name in Cypher, so the round trip is
    # exact. `created_at` on Finding and Component is why this is not
    # hypothetical -- `ON CREATE SET f.created_at = datetime()`.
    temporal = _TEMPORALS.get(type(value).__name__)
    if temporal and hasattr(value, "iso_format"):
        return f"{temporal}({json.dumps(value.iso_format())})"
    if isinstance(value, dict):
        return "{" + ", ".join(
            f"{k if _IDENTIFIER.match(k) else '`' + k.replace('`', '``') + '`'}: "
            f"{cypher_literal(v)}" for k, v in value.items()) + "}"
    raise StorageRefused(
        f"cannot write {type(value).__name__} as a Cypher literal: {value!r}. "
        f"A property type the graph accepted and this cannot emit would be "
        f"dropped silently, so it refuses instead")


def indented_map(props: dict, indent: str = "    ") -> str:
    """One property per LINE, keys sorted, `id` first.

    **This is the whole reason the format looks the way it does.** The first
    version emitted each label's whole node list on one line: 2.8 MB of Athena
    in 155 lines, the longest 531,746 characters. Changing one guard rewrote a
    half-megabyte line, which `git diff` reports as one changed line and GitHub
    refuses to render — so a merge request could not show what data changed,
    which is the main thing a committed graph is FOR.

    One property per line makes a changed guard a one-line diff. Sorting makes
    two exports of an unchanged graph byte-identical; `id` leads because it is
    what a reviewer scans for.
    """
    keys = sorted(props, key=lambda k: (k != "id", k))
    inner = ",\n".join(f"{indent}  {k if _IDENTIFIER.match(k) else chr(96) + k + chr(96)}: "
                        f"{cypher_literal(props[k])}" for k in keys)
    return "{\n" + inner + f"\n{indent}}}"


def _label_of(labels) -> tuple[str, tuple[str, ...]]:
    """The primary label and any markers, in a stable order.

    `:NeedReview` rides alongside a real label. Emitting them in set order would
    make two exports of an unchanged graph differ, which would make the file
    useless in a diff.
    """
    ordered = sorted(labels)
    primary = [x for x in ordered if x != "NeedReview"]
    markers = [x for x in ordered if x == "NeedReview"]
    if not primary:
        raise StorageRefused(f"node carries only marker labels: {ordered}")
    return primary[0], tuple(primary[1:]) + tuple(markers)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

NODES_FOR_PROJECT = """
MATCH (n) WHERE n.m_project = $project
OPTIONAL MATCH (e:Episode {id: n.source_episode_id})
RETURN labels(n) AS labels, properties(n) AS props,
       coalesce(e.source_connector, 'other') AS connector
ORDER BY n.id
"""

EDGES_FOR_PROJECT = """
MATCH (a)-[r]->(b)
WHERE a.m_project = $project AND b.m_project = $project
RETURN labels(a) AS from_labels, a.id AS from_id, type(r) AS rel,
       labels(b) AS to_labels, b.id AS to_id, properties(r) AS props
ORDER BY a.id, type(r), b.id
"""

# Nodes an episode of this project produced that carry no `m_project`. They are
# what a restore would lose, and the number is reported rather than rounded away.
UNCLAIMED = """
MATCH (e:Episode) WHERE e.m_project = $project
MATCH (n) WHERE n.source_episode_id = e.id AND n.m_project IS NULL
RETURN count(n) AS n
"""


def export(session, project: str, out_dir: str | Path, *,
           schema_source: str | Path = "schema", commit: str = "") -> dict:
    """Write `<out_dir>/` so `restore` can rebuild this project's subgraph."""
    if not project:
        raise StorageRefused("export needs a project name; there is no default")

    nodes = [(_label_of(r["labels"]), dict(r["props"]), r["connector"])
             for r in session.run(NODES_FOR_PROJECT, {"project": project})]
    if not nodes:
        raise StorageRefused(
            f"no node carries m_project = {project!r}. Either nothing for this "
            f"project has been landed since `m_project` existed, or the name is "
            f"wrong — `storage projects` lists what is there")

    edges = [dict(r) for r in session.run(EDGES_FOR_PROJECT, {"project": project})]
    unclaimed = (session.run(UNCLAIMED, {"project": project}).single() or {})["n"]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # The schema travels WITH the data. A restore into an empty database has to
    # create the constraints before the MERGEs run, and pointing at the
    # installed Métis for them would make the file restorable only next to the
    # version that wrote it.
    source = Path(schema_source)
    schema_written, schema_digest = [], __import__("hashlib").sha256()
    for name, generated in zip(SCHEMA_FILES, sorted(source.glob("metis2-*.cypher"))):
        text = generated.read_text()
        (out / name).write_text(text)
        schema_digest.update(text.encode())
        schema_written.append(name)

    # **Split by the connector the facts arrived through, not by a taxonomy
    # invented here.** Measured on Athena: `raw-intake` is 5,029 nodes of
    # recovered evidence (2,682 Parameters, 870 Endpoints) and `code` is 402 —
    # the states, transitions and findings a reviewer actually reads. One file
    # would bury the 402 in the 5,029 on every merge request. The grouping is
    # the Episode's own `source_connector`, so it describes how the data really
    # arrived rather than how somebody decided to categorise it.
    groups: dict[str, dict[tuple, list[dict]]] = {}
    for (primary, extra), props, connector in nodes:
        groups.setdefault(connector, {}).setdefault((primary, extra), []).append(props)

    by_edge: dict[tuple, list[dict]] = {}
    for e in edges:
        key = (_label_of(e["from_labels"])[0], e["rel"], _label_of(e["to_labels"])[0])
        by_edge.setdefault(key, []).append(
            {"a": e["from_id"], "b": e["to_id"], "props": dict(e["props"] or {})})

    def _header(what: str) -> list[str]:
        return [f"// Métis project storage — {project} — {what}",
                f"// GENERATED by `metis storage export`. Restore with "
                f"`metis storage restore`.",
                f"// Read {MANIFEST} first: it says which commit and ontology "
                f"this matches.", ""]

    written: list[str] = []
    for connector, by_label in sorted(groups.items()):
        lines = _header(connector)
        for (primary, extra), rows in sorted(by_label.items()):
            marks = "".join(f":{m}" for m in extra)
            lines.append(f"// {primary}{marks} — {len(rows)} node(s)")
            lines.append("UNWIND [")
            # One map per entry, one property per line. The trailing comma sits
            # on the line it belongs to so inserting a node is a clean insertion
            # in the diff rather than a change to its neighbour.
            body = [f"  {indented_map(r)}" for r in rows]
            lines.append(",\n".join(body))
            lines.append("] AS row")
            lines.append(f"MERGE (n:{primary} {{id: row.id}}) SET n += row"
                         + "".join(f" SET n:{m}" for m in extra) + ";")
            lines.append("")
        name = f"nodes-{connector}.cypher"
        (out / name).write_text("\n".join(lines))
        written.append(name)

    lines = _header("relationships")
    for (from_label, rel, to_label), rows in sorted(by_edge.items()):
        lines.append(f"// ({from_label})-[:{rel}]->({to_label}) — {len(rows)} edge(s)")
        lines.append("UNWIND [")
        lines.append(",\n".join(f"  {indented_map(r)}" for r in rows))
        lines.append("] AS row")
        lines.append(f"MATCH (a:{from_label} {{id: row.a}}) "
                     f"MATCH (b:{to_label} {{id: row.b}}) "
                     f"MERGE (a)-[r:{rel}]->(b) SET r += row.props;")
        lines.append("")
    (out / GRAPH_FILE).write_text("\n".join(lines))
    written.append(GRAPH_FILE)

    from metis_mcp.ontology.labels import LABELS

    manifest = {
        "version": STORAGE_VERSION,
        "project": project,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": commit,
        "ontology": {"labels": len(LABELS),
                     "schema_sha256": schema_digest.hexdigest()},
        "counts": {
            "nodes": len(nodes),
            "relationships": len(edges),
            "by_label": {k[0]: len(v) for k, v in sorted(by_label.items())},
        },
        # Order is load-bearing: schema, then every node file, then edges. An
        # edge statement opens with two MATCHes and merges nothing when either
        # endpoint is missing — the silent-edge failure this project has shipped
        # twice — so relationships must come last.
        "files": [*schema_written, *written],
        # Reported, never silent. A restore rebuilds what is in the file, and
        # this says what the file could not claim.
        "unclaimed_nodes": unclaimed,
    }
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def read_manifest(in_dir: str | Path) -> dict | None:
    """The manifest, or `None` when this directory holds no export.

    `None` rather than an exception: "is there a restore file" is a question
    `rebuild_graph.sh` asks about a directory that usually does not exist, and
    the absence is the ordinary answer, not a fault.
    """
    path = Path(in_dir) / MANIFEST
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise StorageRefused(f"{path} is not valid JSON: {e}") from e
    if data.get("version") != STORAGE_VERSION:
        raise StorageRefused(
            f"{path} is {data.get('version')!r} and this build writes "
            f"{STORAGE_VERSION!r}; re-export rather than restoring a format "
            f"nothing here has read")
    return data


def verify(manifest: dict, *, commit: str = "",
           schema_source: str | Path = "schema") -> list[str]:
    """What disagrees between this export and the current checkout.

    **An empty list is the only thing that authorises a restore.** Each entry is
    a reason to re-ingest instead: restoring a graph recovered from a commit the
    tree has moved past produces a model that describes code nobody is running,
    and nothing downstream would say so — `validate` would pass, `report` would
    print a figure, and the figure would be about the past.
    """
    import hashlib

    problems = []
    stored_commit = (manifest.get("commit") or "").strip()
    if commit and stored_commit and commit != stored_commit:
        problems.append(
            f"commit moved: exported at {stored_commit[:12]}, checkout is "
            f"{commit[:12]} — the code these facts were recovered from has changed")
    if commit and not stored_commit:
        problems.append("the export records no commit, so it cannot be shown to "
                        "match this checkout")

    digest = hashlib.sha256()
    for generated in sorted(Path(schema_source).glob("metis2-*.cypher")):
        digest.update(generated.read_text().encode())
    stored = (manifest.get("ontology") or {}).get("schema_sha256", "")
    if stored and stored != digest.hexdigest():
        problems.append(
            "the ontology has changed since the export: the stored Cypher may "
            "name labels or properties the schema no longer has")
    return problems


def restore(session, in_dir: str | Path) -> dict:
    """Replay an export into the graph. Returns the manifest it replayed.

    Statement-at-a-time over the driver rather than shelling out to
    `cypher-shell`: the caller already holds a session, and a restore that
    depends on a container's binary being on the path cannot run against a
    remote database.
    """
    manifest = read_manifest(in_dir)
    if manifest is None:
        raise StorageRefused(f"no {MANIFEST} in {in_dir}; nothing to restore")

    root = Path(in_dir)
    for name in manifest.get("files", []):
        path = root / name
        if not path.is_file():
            raise StorageRefused(
                f"{MANIFEST} lists {name} and it is not there — a partial "
                f"restore would leave a graph that looks whole")

    for name in manifest["files"]:
        for statement in _statements((root / name).read_text()):
            session.run(statement)
    return manifest


def _statements(text: str) -> list[str]:
    """Split a Cypher file on `;` at end of line, dropping comments and blanks.

    Deliberately small, and it is only ever asked to read files this module
    wrote: every statement it emits ends its line with `;`, and no string
    literal it emits contains a newline followed by `;` because `json.dumps`
    escapes newlines. A general Cypher parser here would be a claim this cannot
    back up.
    """
    out, current = [], []
    for line in text.splitlines():
        if line.startswith("//") or not line.strip():
            continue
        current.append(line)
        if line.rstrip().endswith(";"):
            out.append("\n".join(current).rstrip().rstrip(";"))
            current = []
    if current:
        out.append("\n".join(current))
    return [s for s in out if s.strip()]


PROJECTS = """
MATCH (n) WHERE n.m_project IS NOT NULL
RETURN n.m_project AS project, count(n) AS nodes ORDER BY project
"""


def projects(session) -> list[dict]:
    """Every project the graph holds nodes for, with its size."""
    return [dict(r) for r in session.run(PROJECTS)]
