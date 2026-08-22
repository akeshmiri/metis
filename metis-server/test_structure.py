"""
Authored page and data structure (application spec §5.2a, §5.2b; D-1, D-14).

Free to run: pure loading, validation and planning. No Neo4j, no model calls.
"""
import json
import sys
from pathlib import Path

from metis_mcp.model_sources.structure import (
    DANGLING_REFERENCE,
    DB_KINDS,
    ILLEGAL_CONTAINMENT,
    MISSING_FIELD,
    UI_KINDS,
    UNKNOWN_KIND,
    StructureRefused,
    load,
    plan_structure,
    validate,
)
from metis_mcp.ontology.labels import KNOWN_LABELS, is_allowed, label_expression

FIXTURE = Path(__file__).parent / "test_fixtures" / "structure.json"


def _structure():
    return load(FIXTURE)


def _mutated(fn):
    data = json.loads(FIXTURE.read_text())
    fn(data)
    import tempfile
    tmp = Path(tempfile.mkdtemp()) / "s.json"
    tmp.write_text(json.dumps(data))
    return load(tmp)


# --------------------------------------------------------------------------
# The shape it accepts
# --------------------------------------------------------------------------

def test_the_fixture_is_legal():
    assert validate(_structure()) == []


def test_an_unknown_version_is_refused_rather_than_read_optimistically():
    try:
        _mutated(lambda d: d.update(structure_version="metis.structure/99"))
    except StructureRefused as e:
        assert "metis.structure/99" in str(e)
    else:
        raise AssertionError("an unknown version may mean anything")


def test_the_ui_tree_nests_to_any_depth():
    """Page -> UiTable -> Row -> Dialog -> Action is four levels, and a real one."""
    ids = {e.id for e in _structure().elements()}
    assert {"rl-table", "rl-row", "rl-confirm", "rl-confirm-yes"} <= ids


# --------------------------------------------------------------------------
# Containment — read from the catalogue, never restated
# --------------------------------------------------------------------------

def test_a_row_cannot_sit_in_a_menu():
    def add(d):
        d["pages"]["records-list"][0]["contains"].append(
            {"id": "bad", "kind": "Row", "name": "nope"})
    problems = validate(_mutated(add))
    assert any(p.kind == ILLEGAL_CONTAINMENT and p.entry_id == "bad" for p in problems)


def test_a_pagination_cannot_sit_on_a_form():
    def add(d):
        d["pages"]["record-detail"][0]["contains"].append(
            {"id": "bad", "kind": "Pagination", "name": "nope"})
    assert any(p.kind == ILLEGAL_CONTAINMENT for p in validate(_mutated(add)))


def test_the_rules_come_from_the_catalogue_not_a_second_copy():
    """D-2: a second copy of the containment rules is a second thing to keep in
    step, and the four places exist so nobody has to remember them separately."""
    assert is_allowed("UiTable", "HAS_ELEMENT", "Row")
    assert not is_allowed("Menu", "HAS_ELEMENT", "Row")
    assert not is_allowed("Form", "HAS_ELEMENT", "Pagination")


def test_an_unknown_element_kind_is_named_with_what_is_known():
    def add(d):
        d["pages"]["record-detail"].append({"id": "bad", "kind": "Carousel"})
    problem = next(p for p in validate(_mutated(add)) if p.kind == UNKNOWN_KIND)
    assert "Carousel" in problem.detail and "Menu" in problem.detail


# --------------------------------------------------------------------------
# References that have to resolve
# --------------------------------------------------------------------------

def test_a_navigation_to_a_page_that_is_not_here_is_caught():
    def bad(d):
        d["pages"]["records-list"][0]["contains"][0]["navigates_to"] = "nowhere"
    assert any(p.kind == DANGLING_REFERENCE for p in validate(_mutated(bad)))


def test_only_a_navigation_goes_somewhere():
    def bad(d):
        d["pages"]["record-detail"][0]["contains"][0]["navigates_to"] = "records-list"
    problem = next(p for p in validate(_mutated(bad)) if p.kind == MISSING_FIELD)
    assert "only a Navigation" in problem.detail


def test_stored_in_must_name_a_real_object():
    """The join that makes "a record exists in Archived state" answerable."""
    def bad(d):
        d["stored_in"]["record"] = "tb-missing"
    assert any(p.kind == DANGLING_REFERENCE for p in validate(_mutated(bad)))


# --------------------------------------------------------------------------
# The data tree
# --------------------------------------------------------------------------

def test_a_datasource_must_say_which_sql_it_speaks():
    """It decides what a test can issue through it, and a connection string does
    not disclose it."""
    def bad(d):
        d["datasources"][0].pop("dialect")
    problem = next(p for p in validate(_mutated(bad)) if p.kind == MISSING_FIELD)
    assert "dialect" in problem.detail


def test_a_column_with_no_type_cannot_tell_a_fixture_what_to_put_in_it():
    def bad(d):
        d["databases"][0]["schemas"][0]["objects"][0]["columns"][0].pop("data_type")
    assert any(p.kind == MISSING_FIELD for p in validate(_mutated(bad)))


def test_an_unclassified_object_stays_a_worklist_rather_than_forcing_a_new_label():
    """The open end of "and other database elements like function, view, ...".

    `DbObject` is the base for the same reason `UiElement` and `Transition` are:
    an object nobody classified is a question somebody can find, not a synonym
    for all of them.
    """
    assert "DbObject" in DB_KINDS
    assert "DbObject" in KNOWN_LABELS
    assert "DbObject" in label_expression("DbObject")


# --------------------------------------------------------------------------
# Landing
# --------------------------------------------------------------------------

def test_both_trees_plan_through_the_ontology_gate():
    plan = plan_structure(_structure(), "ep-1")
    assert plan.is_legal, plan.errors
    labels = {n.label for n in plan.nodes}
    assert {"Menu", "UiTable", "Row", "Pagination", "Sort", "Dialog", "Action",
            "Event", "Navigation", "Form"} <= labels
    assert {"Datasource", "Database", "Schema", "Table", "View", "Column"} <= labels


def test_the_ui_table_is_not_the_database_table():
    """The collision worth being loud about: `Table` is the stored relation, and
    `MATCH (t:Table)` returning page controls would be a trap."""
    plan = plan_structure(_structure(), "ep-1")
    by_label = {}
    for node in plan.nodes:
        by_label.setdefault(node.label, []).append(node.properties["id"])
    assert by_label["UiTable"] == ["rl-table"]
    assert by_label["Table"] == ["tb-record"]


def test_everything_lands_at_quarantine():
    """S-4 holds for authored structure exactly as for anything else."""
    plan = plan_structure(_structure(), "ep-1")
    ui = [n for n in plan.nodes if n.label in UI_KINDS]
    assert ui and all(n.properties["lifecycle_state"] == "Quarantine" for n in ui)


def test_a_columns_constraints_survive_as_gd3_variants():
    plan = plan_structure(_structure(), "ep-1")
    title = next(n for n in plan.nodes
                 if n.label == "Column" and n.properties["name"] == "title")
    assert "not null" in title.properties["constraints"]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)


def test_a_structure_file_can_stand_on_its_own():
    """`Page` requires a `component`, so this could only ever reference a page
    some other source had already landed — and it referenced it by the BARE
    name while `landing` writes `{model}::page::{name}`. Both halves meant every
    `HAS_ELEMENT` edge came back unmatched on a fresh graph."""
    from metis_mcp.model_sources.structure import load, page_id_for, plan_structure

    structure = load("test_fixtures/structure.json")
    plan = plan_structure(structure, "ep-1", component="records")
    assert plan.is_legal, plan.errors[:3]

    pages = [n for n in plan.nodes if n.label == "Page"]
    assert pages, "no Page was created"
    assert all(n.properties["component"] == "records" for n in pages)

    created = {n.properties["id"] for n in pages}
    for edge in plan.edges:
        if edge.from_label == "Page":
            assert edge.from_id in created, (
                f"{edge.rel_type} is planned from {edge.from_id!r}, which nothing "
                f"creates — the namespacing trap between two writers")


def test_the_page_id_matches_what_landing_writes():
    """One node, two writers, and they have to agree about its id (I-2)."""
    from metis_mcp.model_sources.structure import page_id_for

    assert page_id_for("records", "records-list") == "records::page::records-list"


def test_without_a_component_pages_are_referenced_not_created():
    """The old behaviour is still available: a caller that knows the model source
    landed first can reference rather than create."""
    from metis_mcp.model_sources.structure import load, plan_structure

    plan = plan_structure(load("test_fixtures/structure.json"), "ep-1")
    assert not [n for n in plan.nodes if n.label == "Page"]
