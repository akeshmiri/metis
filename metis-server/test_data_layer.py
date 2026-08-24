"""
The data half: catalogue, queries, and the joins between them (X-7a, X-19, X-19a).

Free to run. The catalogue comes from a checked-in fixture and every translation
is pure, so no driver is installed and no database is reachable — which is the
property that matters more than convenience: a suite that needs a database is a
suite people stop running.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from code_analysis import db_catalogue as C
from code_analysis import jpa
from metis_mcp.resolution import PendingJoin, findings_for, resolve
from metis_mcp.resolution.joins import edges_for

CATALOGUE = Path(__file__).parent / "demo_project" / "records-store" / "catalogue.json"


@pytest.fixture(scope="module")
def catalogue():
    return C.from_fixture(CATALOGUE)


# --------------------------------------------------------------------------
# X-7a — structure only, and it is checked rather than promised
# --------------------------------------------------------------------------

def test_a_row_read_is_refused():
    """**The line the whole intake sits on.** A database Métis reads to learn
    structure is an intake source; the same database queried to check a test's
    outcome is the System Under Test. "It only reads structure" is exactly the
    claim that stays true until somebody adds one convenient query, so it is
    asserted on the statement rather than trusted."""
    with pytest.raises(C.CatalogueRefused) as e:
        C.assert_no_row_reads(["SELECT * FROM record WHERE archived = false"])
    assert "X-7a" in str(e.value)


@pytest.mark.parametrize("dialect", [C.POSTGRES, C.MYSQL, C.ORACLE])
def test_every_shipped_query_is_against_the_catalogue(dialect):
    """Each reader's own SQL must pass the guard it ships with."""
    C.assert_no_row_reads([C.sql_for(dialect)])


def test_an_unknown_dialect_is_refused_by_name():
    with pytest.raises(C.CatalogueRefused) as e:
        C.sql_for("db2")
    assert "known:" in str(e.value)


# --------------------------------------------------------------------------
# The catalogue
# --------------------------------------------------------------------------

def test_the_catalogue_carries_structure_and_no_rows(catalogue):
    assert catalogue.dialect == C.POSTGRES
    names = {o.name for s in catalogue.schemas for o in s.objects}
    assert names == {"record", "record_tag", "active_record"}
    record = next(o for s in catalogue.schemas for o in s.objects if o.name == "record")
    assert {c.name for c in record.columns} == {"id", "title", "owner_name", "archived"}
    assert next(c for c in record.columns if c.name == "id").primary_key


def test_a_view_is_kept_apart_from_a_table(catalogue):
    kinds = {o.name: o.kind for s in catalogue.schemas for o in s.objects}
    assert kinds["active_record"] == "View"
    assert kinds["record"] == "Table"


def test_names_resolve_qualified_and_bare(catalogue):
    """A repository proposes `record`; whether the catalogue calls it
    `public.record` is not something the code side can know."""
    assert {"record", "public.record"} <= catalogue.table_names()


# --------------------------------------------------------------------------
# The four query tiers
# --------------------------------------------------------------------------

def test_a_derived_method_parses_to_its_predicates():
    q = jpa.classify("findByOwnerAndArchived", "RecordEntity")
    assert q.form == jpa.DERIVED
    assert [(p.property_path, p.operator) for p in q.predicates] == [
        ("owner", "="), ("archived", "=")]


def test_an_operator_suffix_is_honoured():
    q = jpa.classify("findByTitleContainingIgnoreCase", "RecordEntity")
    assert q.predicates[0].operator == "ILIKE"
    assert q.predicates[0].property_path == "title"


def test_the_longest_operator_wins():
    """`GreaterThanEqual` must not be read as `GreaterThan` with a stray
    `Equal` left on the property name."""
    q = jpa.classify("findByAgeGreaterThanEqual", "X")
    assert q.predicates == (jpa.Predicate("age", ">="),)


def test_a_native_query_is_verbatim():
    q = jpa.classify("activeForOwner", "RecordEntity",
                     annotation="SELECT * FROM record", native=True)
    assert q.form == jpa.NATIVE
    t = jpa.translate(q, table="record")
    assert t.sql == "SELECT * FROM record"


def test_an_unrecognisable_method_becomes_opaque_with_a_reason():
    """What you asked for: it is not guessed at, it is handed to a person."""
    q = jpa.classify("doTheThing", "RecordEntity")
    assert q.form == jpa.OPAQUE
    assert "needs a person" in q.reason
    assert jpa.translate(q).confidence == jpa.UNRESOLVED


# --------------------------------------------------------------------------
# Translation only goes as far as the catalogue confirms
# --------------------------------------------------------------------------

def _translate(method, entity, catalogue, table, **kw):
    q = jpa.classify(method, entity, **kw)
    return jpa.translate(q, table=table,
                         columns=catalogue.column_names(table) if table else None,
                         column_for=lambda p: {"owner": "owner_name"}.get(p, jpa.snake(p)))


def test_a_confirmed_mapping_yields_real_sql(catalogue):
    t = _translate("findByOwnerAndArchived", "RecordEntity", catalogue, "record")
    assert t.confidence == jpa.CONFIRMED
    assert t.sql == "SELECT * FROM record WHERE owner_name = ? AND archived = ?;"
    assert t.columns == ("owner_name", "archived")


def test_no_confirmed_table_yields_no_sql(catalogue):
    """**`TagEntity` declares no `@Table`**, so the strategy proposes
    `tag_entity` and the catalogue declares `record_tag`. A plausible SQL string
    here would look runnable and be wrong, which is worse than none."""
    t = _translate("findByTag", "TagEntity", catalogue, "")
    assert t.confidence == jpa.UNRESOLVED
    assert not t.sql
    assert "tag_entity" in t.reason and "naming strategy" in t.reason


def test_a_property_the_catalogue_refutes_stops_the_translation(catalogue):
    """One unmatched column is enough: a statement with a wrong column name
    fails at run time against the right table, which is the confusing kind."""
    t = _translate("findByNotAColumn", "RecordEntity", catalogue, "record")
    assert t.confidence == jpa.UNRESOLVED
    assert "refutes it" in t.reason


def test_the_naming_strategy_is_springs_default():
    assert jpa.snake("MfaTransaction") == "mfa_transaction"
    assert jpa.snake("RecordEntity") == "record_entity"


# --------------------------------------------------------------------------
# X-19 — the resolution engine
# --------------------------------------------------------------------------

def _joins():
    return [
        PendingJoin("query_target", "q:1", "record", "@Table on RecordEntity"),
        PendingJoin("query_target", "q:2", "tag_entity",
                    "Spring naming strategy from TagEntity (no @Table)"),
        PendingJoin("entity_storage", "be:record", "record", "glossary noun"),
    ]


def test_nothing_resolves_before_the_confirming_intake_runs():
    out = resolve(_joins(), {})
    assert out.counts == {"confirmed": 0, "refuted": 0, "proposed": 3}
    assert all("has not run" in why for _, why in out.proposed)


def test_the_second_half_arriving_resolves_the_join(catalogue):
    """**The whole point.** Métis looks at both sides, and the join is made as
    soon as the missing piece exists — not by re-running the first intake."""
    out = resolve(_joins(), {"database": catalogue.table_names()})
    assert out.counts["confirmed"] == 2
    edges = edges_for(out, lambda n: f"tbl:{n}")
    assert ("Query", "q:1", "QUERIES", "Table", "tbl:record") in edges
    assert ("BusinessEntity", "be:record", "STORED_IN", "Table", "tbl:record") in edges


def test_a_refuted_proposal_gets_no_edge_and_says_why(catalogue):
    """"Not yet" and "no" are different answers, and collapsing them makes a
    retry loop that never stops asking and never tells anybody it was wrong."""
    out = resolve(_joins(), {"database": catalogue.table_names()})
    assert len(out.refuted) == 1
    join, why = out.refuted[0]
    assert join.to_ref == "tag_entity"
    assert "declares no table named 'tag_entity'" in why
    assert not any(e[1] == "q:2" for e in edges_for(out, lambda n: f"tbl:{n}"))


def test_every_unresolved_join_becomes_a_finding(catalogue):
    """A missing half is visible rather than absent — the discipline X-6d applies
    to a fact the model cannot reach, one level up."""
    out = resolve(_joins(), {"database": catalogue.table_names()})
    findings = findings_for(out)
    assert len(findings) == 1
    about, severity, detail = findings[0]
    assert about == "q:2" and severity == "advisory"
    assert "refuted" in detail


def test_a_join_kind_names_which_intake_can_settle_it():
    """That is what makes the engine generic: an intake declares what it can
    propose and what it can confirm, and a fourth intake adds rows here rather
    than code."""
    from metis_mcp.resolution.joins import KINDS

    assert KINDS["query_target"].confirmed_by == ("database",)
    assert KINDS["element_selector"].confirmed_by == ("web",)
    for kind in KINDS.values():
        assert kind.proposed_by and kind.confirmed_by, kind.name
        assert kind.meaning


# --------------------------------------------------------------------------
# Landing the two halves (X-19a)
# --------------------------------------------------------------------------

import json as _json

from metis_mcp.model_sources import data_landing as D
from metis_mcp.model_sources.sources import _report_from_dict

STORE = Path(__file__).parent / "demo_project" / "records-store"


@pytest.fixture(scope="module")
def store_report():
    """The structural pack's own output for `records-store`, captured.

    Regenerated by `test_extraction.py`'s fixture on a real CPG; kept here as a
    file so this module stays free to run.
    """
    from code_analysis import engine

    extraction = engine.extract(STORE, language="javasrc", project="demo-records-store",
                                framework="spring-mvc", commit="store", skip_preflight=True)
    return _report_from_dict(_json.loads(extraction.structural.read_text()))


def test_the_entity_states_its_table_where_the_source_says_so(store_report):
    stated = {e.entity: e.table for e in store_report.entities}
    assert stated["RecordEntity"] == "record"
    assert stated["TagEntity"] == "", (
        "TagEntity declares no @Table — empty is the fact, and a naming-strategy "
        "guess written here would be a plausible wrong table in the graph")


def test_a_column_that_differs_from_its_field_is_carried(store_report):
    record = next(e for e in store_report.entities if e.entity == "RecordEntity")
    mapping = {c["field"]: c["column"] for c in record.columns}
    assert mapping["owner"] == "owner_name"


def test_the_entity_survives_erasure(store_report):
    """`methodReturn.typeFullName` is `java.util.List` — true and useless. The
    generic survives in the declaration, which is where it is read from."""
    entities = {q.method: q.entity for q in store_report.repository_queries}
    assert entities["findByOwnerAndArchived"] == "RecordEntity"
    assert entities["findByTag"] == "TagEntity"


def test_the_catalogue_lands_as_the_data_layer(catalogue):
    plan = D.plan_catalogue(catalogue, journey="records", repo="records-store")
    assert plan.is_legal, plan.errors
    labels = {n.label for n in plan.nodes}
    assert {"Datasource", "Database", "Schema", "Table", "View", "Column"} <= labels


def test_a_translated_query_lands_as_its_dialect(store_report, catalogue):
    plan, _ = D.plan_queries(store_report, journey="records", repo="records-store",
                             dialect="postgresql", catalogue=catalogue)
    assert plan.is_legal, plan.errors
    by_name = {n.properties["name"]: n for n in plan.nodes if n.label != "Episode"}
    assert by_name["findByOwnerAndArchived"].label == "Postgres"
    assert by_name["findByOwnerAndArchived"].properties["query"] == (
        "SELECT * FROM record WHERE owner_name = ? AND archived = ?;")


def test_an_untranslatable_query_lands_as_a_jpa_query_with_its_reason(
        store_report, catalogue):
    """**What you asked for.** `findByTag` has a perfectly good derived name and
    still yields no SQL, because `TagEntity` states no `@Table` and the catalogue
    declares `record_tag`. Landing it as `:Postgres` would put an empty statement
    in the set a reader queries when they want real ones."""
    plan, _ = D.plan_queries(store_report, journey="records", repo="records-store",
                             dialect="postgresql", catalogue=catalogue)
    tag = next(n for n in plan.nodes if n.properties.get("name") == "findByTag")
    assert tag.label == "JpaQuery"
    assert not tag.properties["query"]
    assert "tag_entity" in tag.properties["reason"]


def test_a_query_reaches_its_table_only_once_the_catalogue_confirms(
        store_report, catalogue):
    """Both directions, on one report: four proposals confirm and one is refuted,
    and the refuted one gets no edge."""
    _, pending = D.plan_queries(store_report, journey="records",
                                repo="records-store", dialect="postgresql",
                                catalogue=catalogue)
    assert len(pending) == 5

    before = resolve(pending, {})
    assert before.counts["proposed"] == 5, "nothing confirms before the catalogue"

    after = resolve(pending, {"database": catalogue.table_names()})
    assert after.counts["confirmed"] == 4
    assert [j.to_ref for j, _ in after.refuted] == ["tag_entity"]


def test_every_query_carries_the_path_a_transition_reaches_it_by(
        store_report, catalogue):
    """`Method -[:ISSUES]-> Query` is what makes a table reachable from
    behaviour at all: ApiCall -> Endpoint -> HANDLED_BY -> Method -> ISSUES."""
    plan, _ = D.plan_queries(store_report, journey="records", repo="records-store",
                             dialect="postgresql", catalogue=catalogue)
    issues = [e for e in plan.edges if e.rel_type == "ISSUES"]
    assert len(issues) == 5
    assert {e.from_label for e in issues} == {"Method"}


# ---------------------------------------------------------------------------
# `Query -[:USES]-> Column` — the relationship that was declared and unwritten
# ---------------------------------------------------------------------------

def test_a_translated_query_links_to_the_columns_it_touches(store_report, catalogue):
    """`USES` was in `ALLOWED_RELATIONSHIPS` with no writer.

    The translation already resolves which columns a statement touches — that
    resolution is what makes it CONFIRMED rather than UNRESOLVED — and the
    result was thrown away. So a reviewer could see that a query hits `record`
    but not that it filters on `owner_name`, which is exactly the fact a test
    case needs to choose a value.
    """
    plan, _ = D.plan_queries(store_report, journey="records", repo="records-store",
                             dialect="postgresql", catalogue=catalogue)
    uses = [e for e in plan.edges if e.rel_type == "USES"]
    assert uses, "no USES edge planned — the columns were resolved and dropped"
    assert all(e.to_label == "Column" for e in uses)


def test_a_uses_edge_points_at_a_column_the_catalogue_actually_declares(
        store_report, catalogue):
    """**The failure this guards is an edge to a node that does not exist.**

    `land` reports an unmatched edge and does not fail, so both halves report
    success and the chain is broken — the `VALIDATES`-against-`:Transition`
    mistake, one layer down. Every `USES` target must therefore be an id the
    catalogue plan would have written.
    """
    cat_plan = D.plan_catalogue(catalogue, journey="records", repo="records-store")
    landed_columns = {n.properties["id"] for n in cat_plan.nodes
                      if n.label == "Column"}
    assert landed_columns, "the catalogue plan wrote no columns — fixture is wrong"

    plan, _ = D.plan_queries(store_report, journey="records", repo="records-store",
                             dialect="postgresql", catalogue=catalogue)
    for edge in [e for e in plan.edges if e.rel_type == "USES"]:
        assert edge.to_id in landed_columns, (
            f"{edge.to_id} is not a column the catalogue landed")


def test_no_uses_edge_is_planned_when_the_catalogue_cannot_address_the_column(
        store_report):
    """No catalogue means no schema, and no schema means no addressable id.

    Proposing the edge anyway is the tempting move and the wrong one: the table
    belief is already carried as a `PendingJoin` with its basis named, which is
    the representation that can be reviewed. An edge cannot.
    """
    plan, _ = D.plan_queries(store_report, journey="records",
                             repo="records-store", dialect="postgresql")
    assert not [e for e in plan.edges if e.rel_type == "USES"]
