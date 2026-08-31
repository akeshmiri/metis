"""
Per-project storage (`metis storage`) — the Cypher a project restores from.

Free to run: every function under test is pure except `export`/`restore`, and
those are exercised against a fake session. What is asserted is the two things a
wrong answer would be silent about — a value that does not survive the round
trip, and a stale file restored over a checkout it does not describe.
"""
from __future__ import annotations

import json

import pytest

from metis_mcp.storage import (
    GRAPH_FILE,
    MANIFEST,
    STORAGE_VERSION,
    StorageRefused,
    _label_of,
    _statements,
    cypher_literal,
    export,
    read_manifest,
    restore,
    storage_dir,
    verify,
)


# --------------------------------------------------------------------------
# Cypher literals — where a silent corruption would enter
# --------------------------------------------------------------------------

def test_a_string_with_quotes_and_newlines_survives():
    """Recovered source text carries both. Hand-rolled quote-doubling is how a
    backslash or a newline truncates a statement, so the JSON encoder does it."""
    assert cypher_literal('a "quote"') == '"a \\"quote\\""'
    assert cypher_literal("line\nbreak") == '"line\\nbreak"'
    assert cypher_literal("back\\slash") == '"back\\\\slash"'


def test_unicode_is_preserved():
    """`GET /record → Ok200` is what a transition is NAMED. An encoder that
    mangled the arrow would rename every transition in the graph."""
    assert "\\u2192" in cypher_literal("a → b") or "→" in cypher_literal("a → b")
    assert json.loads(cypher_literal("a → b")) == "a → b"


def test_a_bool_is_not_written_as_a_number():
    """`bool` IS an `int` in Python, so an isinstance chain that checks int first
    writes `true` as `1` — and `x_source_state_unresolved: 1` is not false, it is
    a different type that every later comparison reads differently."""
    assert cypher_literal(True) == "true"
    assert cypher_literal(False) == "false"
    assert cypher_literal(1) == "1"


def test_map_keys_are_bare_because_cypher_rejects_quoted_ones():
    """`{id: "x"}` parses and `{"id": "x"}` does not."""
    assert cypher_literal({"id": "x"}) == '{id: "x"}'


def test_a_key_that_is_not_an_identifier_is_back_ticked():
    assert cypher_literal({"odd key": 1}) == "{`odd key`: 1}"


def test_a_type_that_cannot_be_written_is_refused_not_dropped():
    """A property the graph accepted and this cannot emit would vanish from the
    restore without anything saying so."""
    with pytest.raises(StorageRefused) as e:
        cypher_literal(object())
    assert "dropped silently" in str(e.value)


def test_a_temporal_round_trips_as_a_temporal():
    """`created_at` is set by `ON CREATE SET f.created_at = datetime()`. Writing
    it as a quoted string would restore it as text, and every comparison against
    it would silently stop matching."""
    neo4j_time = pytest.importorskip("neo4j.time")

    literal = cypher_literal(neo4j_time.DateTime(2026, 8, 30, 23, 23, 53))
    assert literal.startswith('datetime("2026-08-30T23:23:53')


def test_the_marker_label_is_ordered_not_set_ordered():
    """Two exports of an unchanged graph must not differ, or the file is useless
    in a diff."""
    assert _label_of(["NeedReview", "ApiCall"]) == ("ApiCall", ("NeedReview",))
    assert _label_of(["ApiCall", "NeedReview"]) == ("ApiCall", ("NeedReview",))


def test_a_node_with_only_markers_is_refused():
    with pytest.raises(StorageRefused):
        _label_of(["NeedReview"])


# --------------------------------------------------------------------------
# Statement splitting
# --------------------------------------------------------------------------

def test_comments_and_blanks_are_not_statements():
    text = '// a comment\n\nMERGE (n:X {id: "a"});\n\n// another\nMATCH (n) RETURN n;\n'
    assert _statements(text) == ['MERGE (n:X {id: "a"})', "MATCH (n) RETURN n"]


def test_a_semicolon_inside_a_string_does_not_split():
    """`json.dumps` escapes newlines, so a `;` inside a literal never ends a
    line — which is the only reason a splitter this small is honest."""
    text = 'MERGE (n:X {id: "a;b"});\n'
    assert _statements(text) == ['MERGE (n:X {id: "a;b"})']


# --------------------------------------------------------------------------
# Export and restore, against a fake session
# --------------------------------------------------------------------------

class _Rows(list):
    def single(self):
        return self[0] if self else None


class _FakeSession:
    def __init__(self, nodes=(), edges=()):
        self.nodes, self.edges = list(nodes), list(edges)
        self.ran = []

    def run(self, cypher, params=None, **kw):
        if "n.m_project = $project" in cypher and "labels(n)" in cypher:
            return _Rows(self.nodes)
        if "a.m_project = $project" in cypher:
            return _Rows(self.edges)
        if "count(n) AS n" in cypher:
            return _Rows([{"n": 0}])
        self.ran.append(cypher)
        return _Rows()


def _schema(tmp_path):
    d = tmp_path / "schema"
    d.mkdir(parents=True, exist_ok=True)
    (d / "metis2-01-constraints.cypher").write_text("// constraints\n")
    (d / "metis2-02-relationships.cypher").write_text("// relationships\n")
    return d


def test_export_writes_a_manifest_and_a_graph(tmp_path):
    session = _FakeSession(
        nodes=[{"labels": ["Lesson"], "props": {"id": "l1", "name": "One"},
                "connector": "lessons"}],
        edges=[{"from_labels": ["Lesson"], "from_id": "l1", "rel": "BELONGS_TO",
                "to_labels": ["Topic"], "to_id": "t1", "props": {}}])
    out = tmp_path / "storage"

    manifest = export(session, "athena", out,
                      schema_source=_schema(tmp_path), commit="abc123")

    assert manifest["project"] == "athena"
    assert manifest["counts"]["nodes"] == 1
    assert (out / MANIFEST).is_file() and (out / GRAPH_FILE).is_file()
    assert 'MERGE (n:Lesson {id: row.id})' in (out / "nodes-lessons.cypher").read_text()


def test_relationships_are_listed_after_every_node_file(tmp_path):
    """An edge statement opens with two MATCHes and merges nothing when either
    endpoint is missing. Restoring relationships before nodes would land zero
    edges and report success — the silent-edge failure, from the restore side."""
    session = _FakeSession(
        nodes=[{"labels": ["Lesson"], "props": {"id": "l1", "name": "One"},
                "connector": "lessons"},
               {"labels": ["Endpoint"], "props": {"id": "e1", "name": "E"},
                "connector": "raw-intake"}],
        edges=[])
    manifest = export(session, "athena", tmp_path / "s",
                      schema_source=_schema(tmp_path), commit="abc")

    files = manifest["files"]
    assert files[-1] == GRAPH_FILE, f"relationships must load last, got {files}"
    assert files.index("nodes-lessons.cypher") < files.index(GRAPH_FILE)
    assert files.index("nodes-raw-intake.cypher") < files.index(GRAPH_FILE)


def test_the_export_splits_on_how_the_facts_arrived(tmp_path):
    """Measured on Athena: `raw-intake` is 5,029 nodes of recovered evidence and
    `code` is 402 — the states and transitions a reviewer reads. One file would
    bury the 402 in the 5,029 on every merge request."""
    session = _FakeSession(
        nodes=[{"labels": ["ApiCall"], "props": {"id": "t1", "name": "T"},
                "connector": "code"},
               {"labels": ["Parameter"], "props": {"id": "p1", "name": "P"},
                "connector": "raw-intake"}],
        edges=[])
    out = tmp_path / "s"
    export(session, "athena", out, schema_source=_schema(tmp_path), commit="abc")

    assert "ApiCall" in (out / "nodes-code.cypher").read_text()
    assert "ApiCall" not in (out / "nodes-raw-intake.cypher").read_text()


def test_a_property_change_is_a_one_line_diff(tmp_path):
    """**The requirement this format exists for.** The first version emitted a
    label's whole node list on one line — 2.8 MB of Athena in 155 lines, the
    longest 531,746 characters — so changing one guard rewrote a half-megabyte
    line and a merge request could not show what data changed."""
    def _export(guard, where):
        session = _FakeSession(nodes=[{
            "labels": ["ApiCall"],
            "props": {"id": "t1", "name": "T", "b_guard_expression": guard},
            "connector": "code"}], edges=[])
        export(session, "p", where, schema_source=_schema(tmp_path / guard),
               commit="abc")
        return (where / "nodes-code.cypher").read_text().splitlines()

    (tmp_path / "before").mkdir(); (tmp_path / "after").mkdir()
    before = _export("", tmp_path / "before" / "s")
    after = _export("x.isEmpty()", tmp_path / "after" / "s")

    changed = [(a, b) for a, b in zip(before, after) if a != b]
    assert len(changed) == 1, f"expected one changed line, got {changed}"
    assert "b_guard_expression" in changed[0][1]


def test_export_refuses_a_project_with_no_nodes(tmp_path):
    """A file claiming to restore a project it holds nothing for is worse than
    no file: `verify` would pass and the restore would produce an empty graph."""
    with pytest.raises(StorageRefused) as e:
        export(_FakeSession(), "nope", tmp_path / "s", schema_source=_schema(tmp_path))
    assert "no node carries m_project" in str(e.value)


def test_export_refuses_without_a_project_name():
    with pytest.raises(StorageRefused):
        export(_FakeSession(), "", "/tmp/whatever")


def test_a_missing_manifest_is_absence_not_failure(tmp_path):
    """`rebuild_graph.sh` asks about a directory that usually does not exist."""
    assert read_manifest(tmp_path) is None


def test_a_manifest_from_another_format_is_refused(tmp_path):
    (tmp_path / MANIFEST).write_text(json.dumps({"version": "metis.storage/99"}))
    with pytest.raises(StorageRefused):
        read_manifest(tmp_path)


# --------------------------------------------------------------------------
# The staleness guard — the reason a restore is allowed at all
# --------------------------------------------------------------------------

def test_a_moved_commit_is_stale(tmp_path):
    """Restoring a graph recovered from a commit the tree has moved past yields
    a model describing code nobody is running, and nothing downstream says so:
    `validate` passes and `report` prints a figure about the past."""
    manifest = {"version": STORAGE_VERSION, "commit": "aaaaaaaa", "ontology": {}}
    problems = verify(manifest, commit="bbbbbbbb", schema_source=_schema(tmp_path))
    assert any("commit moved" in p for p in problems)


def test_a_matching_commit_is_not_stale(tmp_path):
    manifest = {"version": STORAGE_VERSION, "commit": "aaaaaaaa", "ontology": {}}
    assert verify(manifest, commit="aaaaaaaa", schema_source=_schema(tmp_path)) == []


def test_an_export_with_no_commit_cannot_be_shown_to_match(tmp_path):
    manifest = {"version": STORAGE_VERSION, "commit": "", "ontology": {}}
    problems = verify(manifest, commit="abc", schema_source=_schema(tmp_path))
    assert any("records no commit" in p for p in problems)


def test_a_changed_ontology_is_stale(tmp_path):
    """The stored Cypher may name labels or properties the schema no longer has."""
    manifest = {"version": STORAGE_VERSION, "commit": "abc",
                "ontology": {"schema_sha256": "0" * 64}}
    problems = verify(manifest, commit="abc", schema_source=_schema(tmp_path))
    assert any("ontology has changed" in p for p in problems)


def test_restore_refuses_when_a_listed_file_is_absent(tmp_path):
    """A partial restore would leave a graph that looks whole."""
    (tmp_path / MANIFEST).write_text(json.dumps({
        "version": STORAGE_VERSION, "project": "x", "files": ["graph.cypher"],
        "counts": {"nodes": 1, "relationships": 0}}))
    with pytest.raises(StorageRefused) as e:
        restore(_FakeSession(), tmp_path)
    assert "partial restore" in str(e.value)


def test_storage_dir_is_beside_the_profile_and_the_academy():
    assert storage_dir("/repo").as_posix() == "/repo/.metis/storage"
