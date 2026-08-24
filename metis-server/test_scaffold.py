"""
Page Object and query scaffolds (spec §7.4b, X-6e).

Free to run: both renderers are pure and the input is the checked-in authored
structure, so what is asserted is the real file rather than a fixture's idea of
one.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from metis_mcp.model_sources.structure import load
from metis_mcp.rendering import scaffold as S

STRUCTURE = Path(__file__).parent / "demo_project" / "structure.json"


@pytest.fixture(scope="module")
def structure():
    return load(STRUCTURE)


# **Selectors come from the code, not from the authored file.** `js-ui` reads
# `document.getElementById("archive")` out of `records-page/page.js`; the
# structure file says what is ON the page and the code says how to find it.
#
# This is what the WEB INTAKE returns — `{normalised name: selector}` — and
# nothing more. **The join itself is no longer made here.** It used to be: a
# dict keyed on `name.lower()`, looked up per element, in a test. That meant
# the Page Object this file asserted on was one Métis could not actually
# produce, and the last hand-made join in the system was load-bearing for its
# own proof. `structure.selector_resolution` runs it now, through the same X-19
# machinery the data layer uses.
WEB_INTAKE_SELECTORS = {
    "newrecord": "#new-record",
    "applyfilter": "#apply-filter",
    "archive": "#archive",
}


def _elements(structure, page: str, extracted=None) -> list[dict]:
    """What the engine resolves — no lookup of our own."""
    from metis_mcp.model_sources.structure import elements_for, selector_resolution

    if extracted is None:
        extracted = WEB_INTAKE_SELECTORS
    _, selectors = selector_resolution(structure, extracted)
    return elements_for(structure, page, selectors)


# --------------------------------------------------------------------------
# The Page Object
# --------------------------------------------------------------------------

def test_a_locator_is_the_authored_selector_verbatim(structure):
    code = S.page_object("records-list", _elements(structure, "records-list"))
    assert "archive_locator = '#archive'" in code
    assert "new_record_locator = '#new-record'" in code


def test_an_element_with_no_selector_is_a_stub_never_a_guess(structure):
    """**The condition that makes this file worth having.** `Export` is reached
    in `page.js` by walking the DOM, so no literal names it and `js-ui` reports
    it unresolved. A plausible `#export-button` would look usable, which is what
    makes a fabricated one worse than an empty field (T-9d).

    Give it a stable hook in the page and this stops proving anything; the
    assertion below says so rather than passing quietly.
    """
    elements = _elements(structure, "records-list")
    assert any(e["name"] == "Export" and not e["selector"] for e in elements), (
        "every element resolved to a selector — this test guards nothing")

    code = S.page_object("records-list", elements)
    assert "def export(self):" in code
    assert S.NO_SELECTOR in code
    assert "raise NotImplementedError" in code
    assert "export_locator" not in code, "nothing was invented for it"


def test_a_navigation_returns_the_page_it_leads_to(structure):
    """This is what makes a scenario composable:
    `RecordsListPage(d).new_record().save()`."""
    code = S.page_object("records-list", _elements(structure, "records-list"))
    assert "return RecordDetailPage(self.driver)" in code


def test_a_plain_action_returns_self(structure):
    code = S.page_object("records-list", _elements(structure, "records-list"))
    assert "def archive(self):" in code
    assert "        return self" in code


def test_only_actions_and_navigations_become_methods(structure):
    """A `Row` is a locator, not something you invoke. Rendering a method for one
    would suggest behaviour the structure does not describe (T-6)."""
    code = S.page_object("records-list", _elements(structure, "records-list"))
    assert "def record_row(self)" not in code
    assert "def apply_filter(self):" in code, "an Action does become one"


def test_the_generated_class_is_valid_python(structure):
    """A scaffold that does not parse is not a scaffold."""
    import ast

    for page in structure.pages:
        code = S.page_object(page, _elements(structure, page))
        ast.parse(code)


# --------------------------------------------------------------------------
# The query
# --------------------------------------------------------------------------

def _columns(structure, table: str):
    for db in structure.databases:
        for schema in db.schemas:
            for obj in schema.objects:
                if obj.name == table:
                    return schema.name, [
                        {"name": c.name, "data_type": c.data_type,
                         "constraints": list(c.constraints)} for c in obj.columns]
    raise AssertionError(table)


def test_columns_are_named_never_a_star(structure):
    """A test asserting on a result set should break when a column is removed,
    not silently see one fewer."""
    schema, columns = _columns(structure, "record")
    sql = S.select_query("record", columns, schema=schema)
    assert "*" not in sql
    assert "SELECT id," in sql and "visibility," in sql
    assert "FROM public.record" in sql


def test_a_primary_key_gives_a_by_key_query(structure):
    schema, columns = _columns(structure, "record")
    q = S.query_scaffold("record", columns, schema=schema, dialect="postgresql")
    assert "WHERE id = :id" in q["by_key"]


def test_a_table_with_no_primary_key_has_no_by_key_query(structure):
    """`record_tag` declares none, so there is no key to select on and the
    scaffold says so rather than inventing one."""
    schema, columns = _columns(structure, "record_tag")
    q = S.query_scaffold("record_tag", columns, schema=schema)
    assert q["by_key"] is None


def test_the_not_null_columns_are_what_an_insert_needs(structure):
    schema, columns = _columns(structure, "record")
    q = S.query_scaffold("record", columns, schema=schema)
    assert q["required_on_insert"] == ["title", "owner", "archived"]


def test_the_scaffold_states_that_metis_does_not_execute_it(structure):
    """Nothing in this codebase opens a database connection. Generating a query
    and running one are different capabilities and only the first is here."""
    schema, columns = _columns(structure, "record")
    q = S.query_scaffold("record", columns, schema=schema)
    assert q["executes"] is False
    assert "does not execute" in q["note"]
