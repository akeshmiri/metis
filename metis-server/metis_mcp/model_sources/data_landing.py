"""
The data layer, landed (spec §8.2's D-12, X-19, X-19a).

Two halves that arrive separately and have to meet:

    the catalogue    Datasource -> Database -> Schema -> Table/View -> Column
    the code         Method -[:ISSUES]-> Query -[:QUERIES]-> Table
                                               -[:USES]---> Column

**Neither half can complete the join alone**, which is the whole reason
`resolution` exists. A repository names `RecordEntity`; only a catalogue can say
whether `record` is a real table. An entity states `@Table(name = "record")` and
that is a fact — but measured on a real service, `@Entity`/`@Table`/`@Column`
were in **zero** files because the entities lived in a dependency jar, so the
usual case is that the code can only propose.

So this module writes what each half knows and **proposes the rest**. A proposal
is a `PendingJoin` with its basis named, never an edge; the resolution pass turns
it into an edge when the other half arrives, or into a finding when the other
half arrives and refutes it.

Pure planner, thin writer — the same shape as `landing` and `raw_landing`, and
for the same reason: nothing reaches the database until the whole plan validates.
"""
from __future__ import annotations

from code_analysis import jpa
from metis_mcp.model_sources.landing import LandingPlan, PlannedEdge, PlannedNode
from metis_mcp.model_sources.raw_landing import _anchor_props, _ident, method_id
from metis_mcp.ontology import validate, validate_relationship
from metis_mcp.resolution import PendingJoin

# `Postgres` / `Oracle` / `MySql` are written INSTEAD of `:Query`, so every
# estate-wide question uses `label_expression("Query")`. A dialect nothing
# recognises lands as the parent rather than as a guess at which database it is.
DIALECT_LABELS = {
    "postgresql": "Postgres", "postgres": "Postgres",
    "oracle": "Oracle",
    "mysql": "MySql", "mariadb": "MySql",
}


def query_id(repo: str, method_full_name: str) -> str:
    return f"qry:{_ident(repo, method_full_name)}"


def table_id(repo: str, schema: str, table: str) -> str:
    return f"tbl:{_ident(repo, schema, table)}"


def column_id(repo: str, schema: str, table: str, column: str) -> str:
    return f"col:{_ident(repo, schema, table, column)}"


def datasource_id(repo: str, name: str) -> str:
    return f"dsr:{_ident(repo, name)}"


def database_id(repo: str, name: str) -> str:
    return f"dbs:{_ident(repo, name)}"


def schema_id(repo: str, database: str, name: str) -> str:
    return f"sch:{_ident(repo, database, name)}"


def query_label(dialect: str, form: str, confidence: str = "") -> str:
    """The dialect, or `JpaQuery` where no statement could be produced.

    **Keyed on the outcome, not only on the form.** A derived method whose table
    no catalogue confirms is every bit as untranslated as an unparseable one —
    `findByTag` has a perfectly good name and still yields no SQL, because
    `TagEntity` states no `@Table` and the catalogue declares `record_tag`.
    Landing it as `:Postgres` would put it in the set a reader queries when they
    want real statements, and its `query` is empty.

    So anything without a statement is a `JpaQuery`: raw, reasoned, and waiting
    for a person.
    """
    if form == jpa.OPAQUE or confidence == jpa.UNRESOLVED:
        return "JpaQuery"
    return DIALECT_LABELS.get((dialect or "").lower(), "Query")


def plan_catalogue(catalogue, *, journey: str, repo: str, job_id: str = "",
                   t_recorded: str = "") -> LandingPlan:
    """`Datasource -> Database -> Schema -> Table/View -> Column`, from a read
    catalogue. Structure only: no row ever reaches here (X-7a)."""
    from datetime import datetime, timezone

    recorded = t_recorded or datetime.now(timezone.utc).isoformat(timespec="seconds")
    episode = "ep-db-" + _ident(repo, catalogue.database, journey)
    plan = LandingPlan(episode_id=episode)

    def add_node(label: str, props: dict) -> None:
        outcome = validate(label, props)
        if not outcome.valid:
            plan.errors.extend(f"{label} {props.get('id','?')}: {e}"
                               for e in outcome.errors)
            return
        plan.nodes.append(PlannedNode(label=label, properties=props))

    def add_edge(fl: str, fi: str, rel: str, tl: str, ti: str) -> None:
        outcome = validate_relationship(fl, rel, tl)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return
        plan.edges.append(PlannedEdge(from_label=fl, from_id=fi, rel_type=rel,
                                      to_label=tl, to_id=ti))

    def base(node_id: str, name: str) -> dict:
        return {"id": node_id, "source_episode_id": episode, "name": name}

    plan.nodes.append(PlannedNode(label="Episode", properties={
        "id": episode, "name": f"db-catalogue: {catalogue.database or journey}",
        "source_connector": "database", "created_at": recorded,
        "job_id": job_id or "db-catalogue"}))

    dsid = datasource_id(repo, catalogue.database or journey)
    add_node("Datasource", {**base(dsid, catalogue.database or journey),
                            "datasource_id": dsid, "dialect": catalogue.dialect})
    dbid = database_id(repo, catalogue.database or journey)
    add_node("Database", {**base(dbid, catalogue.database or journey)})
    add_edge("Datasource", dsid, "CONNECTS_TO", "Database", dbid)

    for schema in catalogue.schemas:
        scid = schema_id(repo, catalogue.database, schema.name)
        add_node("Schema", {**base(scid, schema.name)})
        add_edge("Database", dbid, "HAS_SCHEMA", "Schema", scid)
        for obj in schema.objects:
            label = obj.kind if obj.kind in ("Table", "View", "Function") else "DbObject"
            oid = table_id(repo, schema.name, obj.name)
            # `object_type` is required on every DbObject specialisation: the
            # catalogue's own word for what this is, so a reader does not have to
            # infer it from the label it happens to carry.
            add_node(label, {**base(oid, obj.name), "object_type": obj.kind,
                             "schema_name": schema.name})
            add_edge("Schema", scid, "HAS_OBJECT", label, oid)
            for column in obj.columns:
                cid = column_id(repo, schema.name, obj.name, column.name)
                add_node("Column", {
                    **base(cid, column.name), "data_type": column.data_type,
                    "nullable": column.nullable,
                    "primary_key": column.primary_key})
                add_edge(label, oid, "HAS_COLUMN", "Column", cid)
    return plan


def plan_queries(report, *, journey: str, repo: str, dialect: str = "",
                 catalogue=None, job_id: str = "", t_recorded: str = "",
                 ) -> tuple[LandingPlan, list[PendingJoin]]:
    """`Method -[:ISSUES]-> Query`, and either an edge to a table or a proposal.

    Returns the plan **and** the joins it could not make. The second half of that
    tuple is the honest part: a query whose table nobody has confirmed still
    lands — it is a real thing the application does — and what is missing is the
    edge, reported rather than invented.
    """
    from datetime import datetime, timezone

    recorded = t_recorded or datetime.now(timezone.utc).isoformat(timespec="seconds")
    episode = "ep-qry-" + _ident(repo, journey)
    plan = LandingPlan(episode_id=episode)
    pending: list[PendingJoin] = []

    plan.nodes.append(PlannedNode(label="Episode", properties={
        "id": episode, "name": f"queries: {journey}", "source_connector": "code",
        "created_at": recorded, "job_id": job_id or "queries"}))

    # `@Table` where the source states it; the entity's own columns likewise.
    stated_table = {e.entity: e.table for e in getattr(report, "entities", ())}
    stated_column = {
        e.entity: {c.get("field"): c.get("column") for c in (e.columns or ())
                   if c.get("column")}
        for e in getattr(report, "entities", ())}

    for fact in getattr(report, "repository_queries", ()) or ():
        query = jpa.classify(fact.method, fact.entity,
                             annotation=fact.statement, native=fact.native)
        table = stated_table.get(fact.entity, "")
        columns = catalogue.column_names(table) if (catalogue and table) else None
        mapping = stated_column.get(fact.entity, {})
        translated = jpa.translate(
            query, table=table, columns=columns,
            column_for=lambda p, m=mapping: m.get(p) or jpa.snake(p))

        qid = query_id(repo, fact.method_id)
        label = query_label(dialect, query.form, translated.confidence)
        outcome = validate(label, {
            "id": qid, "source_episode_id": episode, "name": fact.method,
            "query": translated.sql, "form": query.form,
            "dialect": dialect, "confidence": translated.confidence,
            "repository": fact.repository, "entity": fact.entity,
            "reason": translated.reason,
            **_anchor_props(getattr(fact, "anchor", None))})
        if not outcome.valid:
            plan.errors.extend(f"{label} {qid}: {e}" for e in outcome.errors)
            continue
        plan.nodes.append(PlannedNode(label=label, properties={
            "id": qid, "source_episode_id": episode, "name": fact.method,
            "query": translated.sql, "form": query.form,
            "dialect": dialect, "confidence": translated.confidence,
            "repository": fact.repository, "entity": fact.entity,
            "reason": translated.reason,
            **_anchor_props(getattr(fact, "anchor", None))}))

        # The path a transition reaches a table by. Planned whether or not the
        # method was landed — `land` reports an unmatched edge, which is the
        # honest outcome when the call graph was bounded away from it.
        plan.edges.append(PlannedEdge(
            from_label="Method", from_id=method_id(repo, fact.method_id),
            rel_type="ISSUES", to_label=label, to_id=qid))

        # **`USES`, where the catalogue can address the column.** The
        # translation already resolved which columns the statement touches —
        # that is what made it CONFIRMED — and until now they were dropped, so
        # `Query -[:USES]-> Column` was a declared relationship nothing wrote.
        #
        # Only when the catalogue holds the table, because a `Column` id is
        # keyed on `(schema, table, column)` and an unconfirmed table has no
        # schema to key against. An edge to a node that does not exist is worse
        # than no edge: `land` reports it as unmatched and the run still passes.
        if catalogue and table and translated.columns:
            schema_name = catalogue.schema_of(table)
            confirmed_columns = catalogue.column_names(table)
            for column in translated.columns:
                if not schema_name or column not in confirmed_columns:
                    continue
                plan.edges.append(PlannedEdge(
                    from_label=label, from_id=qid, rel_type="USES",
                    to_label="Column",
                    to_id=column_id(repo, schema_name, table, column)))

        # **The join, or the proposal.** A table the source states and a
        # catalogue confirms is an edge; anything else is a PendingJoin carrying
        # what it was proposed on, so a reviewer can weigh it.
        proposed = table or jpa.snake(fact.entity)
        basis = (f"@Table on {fact.entity}" if table
                 else f"Spring naming strategy from {fact.entity} (no @Table)")
        pending.append(PendingJoin(kind="query_target", from_id=qid,
                                   to_ref=proposed, basis=basis,
                                   detail=fact.method))
    return plan, pending
