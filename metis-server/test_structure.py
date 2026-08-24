"""
Authored page and data structure (application spec §5.2a, §5.2b; D-1, D-14).

Free to run: pure loading, validation and planning. No Neo4j, no model calls.
"""
import json
import pytest
import sys
from pathlib import Path

from metis_mcp.model_sources.structure import (
    element_id_for,
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
    # The UI element is keyed on (page, name, index) now, so the assertion is
    # agreement with the identity function rather than the authored id — which
    # is display data (D-8) and must be free to change without re-keying.
    assert by_label["UiTable"] == [element_id_for("records-list", "Records table")]
    assert by_label["Table"] == ["tb-record"], "the database table keeps its own id"


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


# --------------------------------------------------------------------------
# Element identity: (page, normalised name, index) — X-19's element_selector
# --------------------------------------------------------------------------

from metis_mcp.model_sources.structure import (  # noqa: E402
    element_display_name,
    elements_for,
    normalised_name,
    pending_selectors,
    selector_resolution,
)


@pytest.mark.parametrize("authored,extracted", [
    ("Archive", "archiveButton"),
    ("Apply filter", "applyFilter"),
    ("New record", "newRecord"),
    ("Export", "exportButton"),
])
def test_the_authored_name_and_the_extracted_name_reduce_to_the_same_basis(
        authored, extracted):
    """All four demo pairs, which is what makes the join possible at all."""
    assert normalised_name(authored) == normalised_name(extracted)


def test_only_one_ui_suffix_is_stripped_and_only_from_the_end():
    """An open suffix list is a guess that grows, and each addition silently
    re-keys every element ending in it. `inputField` is a real name."""
    assert normalised_name("inputField") == "input"
    assert normalised_name("Button") == "button", "not reduced to nothing"


def test_renaming_the_authored_id_does_not_produce_a_second_node():
    """**The reason identity moved off the authored id** (D-8, I-2). A
    structure file that renames `rl-archive` to `archive-btn` describes the same
    button, and a new node would silently split its history in two."""
    before = {n.properties["id"] for n in plan_structure(_structure(), "ep").nodes}
    renamed = _mutated(lambda d: d["pages"]["records-list"][0]["contains"][0]
                       .__setitem__("id", "totally-different-id"))
    after = {n.properties["id"] for n in plan_structure(renamed, "ep").nodes}
    assert before == after


def test_elements_sharing_a_name_on_one_page_keep_distinct_identities():
    """`records-list` already carries more than one element named `click`, so a
    key without an index fuses them into a single node."""
    def add_twin(d):
        page = d["pages"]["records-list"]
        page.append({"id": "rl-extra", "kind": "Action", "name": "Archive"})
    twinned = _mutated(add_twin)
    ids = [n.properties["id"] for n in plan_structure(twinned, "ep").nodes
           if n.properties.get("join_name") == "archive"]
    assert len(ids) == 2 and len(set(ids)) == 2, "the two Archives fused"


def test_a_repeated_name_is_suffixed_for_display_and_a_unique_one_is_not():
    assert element_display_name("Click", 0, 1) == "Click"
    assert element_display_name("Click", 0, 3) == "Click"
    assert element_display_name("Click", 1, 3) == "Click 2"


def test_the_authored_id_survives_as_display_data():
    """It stops being identity; it does not stop being useful. A reviewer needs
    to find the entry in the file that produced a node."""
    authored = {n.properties.get("authored_id")
                for n in plan_structure(_structure(), "ep").nodes}
    assert "rl-table" in authored


# --------------------------------------------------------------------------
# The join itself
# --------------------------------------------------------------------------

def test_an_intake_that_has_not_run_leaves_the_join_proposed():
    """Not refuted. The distinction is the reason this goes through `resolve`
    at all: `proposed` means run the web intake, `refuted` means the belief was
    wrong. A dict lookup returns "" for both."""
    resolution, selectors = selector_resolution(_structure(), None)
    assert resolution.counts["confirmed"] == 0
    assert resolution.counts["refuted"] == 0
    assert resolution.counts["proposed"] == len(pending_selectors(_structure()))
    assert selectors == {}


def test_an_intake_that_ran_and_lacks_the_name_refutes_it():
    """The web intake read the page and the element is not there — that is a
    fact about the code, and reporting it as "not yet" would have a reviewer
    waiting for an intake that has already answered."""
    resolution, _ = selector_resolution(_structure(), {"archive": "#archive"})
    assert resolution.counts["confirmed"] == 1
    assert resolution.counts["refuted"] > 0
    assert resolution.counts["proposed"] == 0


def test_a_confirmed_selector_reaches_the_element_it_was_proposed_for():
    """End to end, with no lookup of the test's own — this join used to live in
    `test_scaffold.py` as a dict, which meant the rendered Page Object was one
    the engine could not produce."""
    structure = _structure()
    _, selectors = selector_resolution(structure, {"archive": "#archive"})
    archive = [e for e in elements_for(structure, "records-list", selectors)
               if e["name"] == "Archive"]
    assert archive and archive[0]["selector"] == "#archive"


def test_a_selector_is_a_property_and_never_a_node():
    """`edges_for` skips property-valued joins; `properties_for` is what picks
    them up. Landing `#archive` as an entity would put a CSS string in the
    label space and give a reviewer a thing to approve that is not a fact about
    the system."""
    from metis_mcp.resolution import KINDS, edges_for, resolve

    resolution = resolve(pending_selectors(_structure()),
                         {"web": {"archive"}})
    assert KINDS["element_selector"].property_name == "selector"
    assert edges_for(resolution, lambda ref: ref) == []


# --------------------------------------------------------------------------
# `RENDERS` — Route -> Page, the third relationship that had no writer
# --------------------------------------------------------------------------

from metis_mcp.model_sources.structure import (  # noqa: E402
    normalised_page_name,
    pending_routes,
    route_resolution,
)

_ROUTES = [{"path": "/records", "screen": "RecordListPage"},
           {"path": "/records/:id", "screen": "RecordDetailPage"},
           {"path": "/summary", "screen": "SummaryPage"}]


def test_a_router_screen_meets_the_page_it_shows():
    _, pairs = route_resolution(_structure(), _ROUTES)
    assert pairs == [("/records/:id", "record-detail")]


def test_a_plural_mismatch_is_refuted_and_not_guessed_away():
    """**The refutation is the right answer.** `RecordListPage` does not meet
    `records-list`, and stripping an `s` to make it would be an open-ended guess
    of exactly the kind the closed suffix list exists to avoid — it would marry
    a `Records` page to a `Record` route on an estate where those differ. The
    reviewer gets both names and decides."""
    resolution, _ = route_resolution(_structure(), _ROUTES)
    from metis_mcp.resolution import findings_for

    refuted = [d for _, _, d in findings_for(resolution) if "recordlist" in d]
    assert refuted and "refuted" in refuted[0]
    assert "RecordListPage" in refuted[0], "the reviewer needs the other side"


def test_a_route_whose_screen_the_router_never_named_is_not_proposed():
    """There is nothing to join on, and an empty basis would marry every such
    route to whichever page also has none."""
    assert pending_routes([{"path": "/x", "screen": ""}]) == []


def test_no_structure_leaves_the_routes_proposed_rather_than_refuted():
    resolution, pairs = route_resolution(None, _ROUTES)
    assert resolution.counts["proposed"] == 3 and pairs == []


def test_a_landed_route_carries_the_basis_it_will_join_on():
    """So the proposal can be re-run against a structure that lands later —
    which is the whole promise of a deferred join."""
    assert normalised_page_name("RecordDetailPage") == "recorddetail"
