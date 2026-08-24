"""
The data layer, reachable (X-19a, X-7a).

`data_landing`, `db_catalogue` and `rendering/scaffold` were built, tested, and
had **no CLI command and no workflow stage** — the capability existed and nobody
could run it. `connectors/intakes.json` marked the database intake `partial` and
named three limits, none of which was "nothing invokes this".

These run the commands as a person would: `--dry-run`, so no graph is needed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
DEMO = HERE / "demo_project"
CATALOGUE = DEMO / "records-store" / "catalogue.json"
STRUCTURE = DEMO / "structure.json"


def _cli(*args):
    out = subprocess.run(
        [sys.executable, "-m", "metis_mcp.mbt.cli", *args],
        capture_output=True, text=True, cwd=HERE)
    return out.returncode, out.stdout, out.stderr


@pytest.fixture(scope="module")
def store_report(tmp_path_factory):
    from code_analysis import engine

    extraction = engine.extract(
        DEMO / "records-store", language="javasrc",
        project="demo-records-store", framework="spring-mvc",
        commit="store", skip_preflight=True)
    path = tmp_path_factory.mktemp("data") / "structural.json"
    path.write_text(extraction.structural.read_text())
    return path


# ---------------------------------------------------------------------------
# `metis data catalogue`
# ---------------------------------------------------------------------------

def test_the_catalogue_command_runs_and_plans_the_structure():
    code, out, err = _cli("data", "catalogue", "--fixture", str(CATALOGUE),
                          "--journey", "records", "--repo", "records-store",
                          "--dry-run")
    assert code == 0, err
    assert "postgresql" in out and "schema(s)" in out
    assert "planned" in out and " 0 nodes" not in out


def test_the_catalogue_command_writes_nothing_on_dry_run():
    _, out, _ = _cli("data", "catalogue", "--fixture", str(CATALOGUE),
                     "--journey", "records", "--repo", "records-store",
                     "--dry-run")
    assert "Nothing was written" in out


def test_an_unreadable_catalogue_is_refused_rather_than_landed_empty(tmp_path):
    bad = tmp_path / "nope.json"
    bad.write_text("{}")
    code, out, _ = _cli("data", "catalogue", "--fixture", str(bad),
                        "--journey", "r", "--repo", "r", "--dry-run")
    assert code != 0 or "REFUSED" in out or "0 object(s)" in out


# ---------------------------------------------------------------------------
# `metis data queries`
# ---------------------------------------------------------------------------

def test_the_queries_command_lands_translated_and_untranslated_alike(store_report):
    """A `JpaQuery` is the honest label for a query no SQL could be produced
    for; landing it as `:Postgres` would put it in the set a reader queries
    when they want real statements."""
    code, out, err = _cli("data", "queries", str(store_report),
                          "--catalogue", str(CATALOGUE), "--dialect",
                          "postgresql", "--journey", "records", "--repo",
                          "records-store", "--dry-run")
    assert code == 0, err
    assert "Postgres" in out and "JpaQuery" in out


def test_a_refuted_table_is_reported_with_the_basis_it_was_proposed_on(
        store_report):
    """The demo's condition: `TagEntity` states no `@Table`, so the Spring
    naming strategy proposes `tag_entity` and the catalogue's `record_tag`
    refutes it. A reviewer needs both halves to fix it."""
    _, out, _ = _cli("data", "queries", str(store_report), "--catalogue",
                     str(CATALOGUE), "--dialect", "postgresql", "--journey",
                     "records", "--repo", "records-store", "--dry-run")
    assert "refuted" in out
    assert "tag_entity" in out and "TagEntity" in out


def test_without_a_catalogue_every_table_is_proposed_not_refuted(store_report):
    """No catalogue means the confirming intake has not run, which is a
    different answer from having run and disagreed."""
    _, out, _ = _cli("data", "queries", str(store_report), "--dialect",
                     "postgresql", "--journey", "records", "--repo",
                     "records-store", "--dry-run")
    assert "proposed" in out and "refuted" not in out


# ---------------------------------------------------------------------------
# `metis page-object`
# ---------------------------------------------------------------------------

def test_the_page_object_command_renders_the_resolved_selectors(tmp_path):
    selectors = tmp_path / "sel.json"
    selectors.write_text(json.dumps({"archive": "#archive",
                                     "newrecord": "#new-record"}))
    code, out, err = _cli("page-object", str(STRUCTURE), "--page",
                          "records-list", "--selectors", str(selectors))
    assert code == 0, err
    assert "archive_locator = '#archive'" in out
    assert "class RecordsListPage" in out


def test_an_element_the_code_never_names_is_a_stub(tmp_path):
    """`Export` is reached by a DOM walk in `records-page/page.js`, on purpose.
    A fabricated selector is worse than none (T-9d)."""
    selectors = tmp_path / "sel.json"
    selectors.write_text(json.dumps({"archive": "#archive"}))
    _, out, _ = _cli("page-object", str(STRUCTURE), "--page", "records-list",
                     "--selectors", str(selectors))
    assert "NotImplementedError" in out
    assert "no selector recovered for 'Export'" in out


def test_without_the_web_intake_the_command_says_so_rather_than_stubbing_quietly():
    """`proposed`, not `refuted` — every method is a stub because an intake has
    not run, and that is a different thing from the code not naming them."""
    code, out, err = _cli("page-object", str(STRUCTURE), "--page",
                          "records-list")
    assert code == 0
    assert "the web intake has not run" in err
    assert "proposed" in err


def test_an_unknown_page_is_refused_with_the_pages_that_exist():
    code, out, _ = _cli("page-object", str(STRUCTURE), "--page", "no-such-page")
    assert code != 0
    assert "REFUSED" in out and "records-list" in out
