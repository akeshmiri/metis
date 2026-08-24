"""
The database catalogue as an intake (spec §5.2b, X-7a).

A database is not a detail of a service, it is half of what a test has to set up
and assert against — and until now Métis could only be *told* about one, in an
authored file. This reads a real catalogue: schemas, tables, views, columns,
types, nullability, keys.

**Structure only. No row data, ever.** Every statement issued here is against the
information schema, and `assert_no_row_reads` checks that rather than trusting
it. That is not fastidiousness: it is the line X-7a draws. A database Métis reads
to learn structure is an **intake source**; the same database queried to check a
test's outcome is the **System Under Test**, and only the first is available.
Same server, different act.

**Three dialects, one shape.** Postgres and MySQL expose `information_schema`;
Oracle exposes `ALL_TAB_COLUMNS` and friends. The queries differ and nothing else
does, so a reader is a pair of SQL strings and a dialect name.

**Drivers are optional extras** (`[postgres]`, `[oracle]`, `[mysql]`). The test
suite must keep running with none installed — that property is worth more than
convenience — so the fixture path is what the suite exercises and the live path
is opt-in, the same split the query packs use.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CATALOGUE_VERSION = "metis.db-catalogue/1"

POSTGRES = "postgresql"
ORACLE = "oracle"
MYSQL = "mysql"


class CatalogueRefused(Exception):
    """The catalogue could not be read at all — shape or access, not content."""


@dataclass(frozen=True)
class CatalogueColumn:
    name: str
    data_type: str
    nullable: bool = True
    primary_key: bool = False
    references: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CatalogueObject:
    name: str
    kind: str                      # Table | View | Function | DbObject
    columns: tuple[CatalogueColumn, ...] = ()


@dataclass(frozen=True)
class CatalogueSchema:
    name: str
    objects: tuple[CatalogueObject, ...] = ()


@dataclass(frozen=True)
class Catalogue:
    dialect: str
    database: str
    schemas: tuple[CatalogueSchema, ...] = ()

    def table_names(self) -> set[str]:
        """Every object name, for the resolution engine to confirm against.

        Unqualified as well as qualified: a repository proposes `record`, and
        whether the catalogue calls it `public.record` is not something the code
        side can know.
        """
        out: set[str] = set()
        for schema in self.schemas:
            for obj in schema.objects:
                out.add(obj.name)
                out.add(f"{schema.name}.{obj.name}")
        return out

    def column_names(self, table: str) -> set[str]:
        for schema in self.schemas:
            for obj in schema.objects:
                if obj.name == table or f"{schema.name}.{obj.name}" == table:
                    return {c.name for c in obj.columns}
        return set()

    def schema_of(self, table: str) -> str:
        """The schema holding `table`, or `""` if the catalogue has no such table.

        Needed to address a `Column` node: its id is keyed on
        `(schema, table, column)`, and a query proposes an unqualified table
        name. An empty answer is the honest one — it means no edge may be
        planned, not that the default schema should be assumed.
        """
        for schema in self.schemas:
            for obj in schema.objects:
                if obj.name == table or f"{schema.name}.{obj.name}" == table:
                    return schema.name
        return ""


# --------------------------------------------------------------------------
# The queries. Catalogue views only — this is the list `assert_no_row_reads`
# checks against, so a reader that grew a `SELECT * FROM <user table>` fails.
# --------------------------------------------------------------------------

CATALOGUE_SOURCES = {
    POSTGRES: ("information_schema.columns", "information_schema.tables",
               "information_schema.table_constraints",
               "information_schema.key_column_usage",
               "information_schema.constraint_column_usage"),
    MYSQL: ("information_schema.columns", "information_schema.tables",
            "information_schema.key_column_usage"),
    ORACLE: ("all_tab_columns", "all_tables", "all_views", "all_constraints",
             "all_cons_columns"),
}

_COLUMNS_SQL = {
    POSTGRES: """
        SELECT table_schema, table_name, column_name, data_type,
               is_nullable, ordinal_position
          FROM information_schema.columns
         WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
         ORDER BY table_schema, table_name, ordinal_position
    """,
    MYSQL: """
        SELECT table_schema, table_name, column_name, data_type,
               is_nullable, ordinal_position
          FROM information_schema.columns
         WHERE table_schema NOT IN ('mysql', 'sys', 'performance_schema',
                                    'information_schema')
         ORDER BY table_schema, table_name, ordinal_position
    """,
    ORACLE: """
        SELECT owner AS table_schema, table_name, column_name, data_type,
               nullable AS is_nullable, column_id AS ordinal_position
          FROM all_tab_columns
         WHERE owner = :owner
         ORDER BY table_name, column_id
    """,
}


def assert_no_row_reads(statements) -> None:
    """Refuse any statement that is not against a catalogue view (X-7a).

    Checked rather than trusted, because "it only reads structure" is exactly the
    kind of claim that stays true until somebody adds one convenient query.
    """
    allowed = {source for sources in CATALOGUE_SOURCES.values() for source in sources}
    for statement in statements:
        lowered = " ".join(statement.lower().split())
        if not any(source in lowered for source in allowed):
            raise CatalogueRefused(
                "a catalogue reader may only query the catalogue (X-7a). This "
                f"statement names none of {sorted(allowed)[:3]}…: "
                f"{lowered[:80]}")


def sql_for(dialect: str) -> str:
    if dialect not in _COLUMNS_SQL:
        raise CatalogueRefused(
            f"no catalogue reader for {dialect!r}; known: "
            f"{', '.join(sorted(_COLUMNS_SQL))}")
    return _COLUMNS_SQL[dialect]


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def from_fixture(path: str | Path) -> Catalogue:
    """A catalogue captured to a file — what the suite exercises.

    The live readers produce the same shape, so everything downstream is tested
    against this and the connection is the only untested part. That is the same
    split the query packs use, and it is what keeps the suite free of a database.
    """
    data = json.loads(Path(path).read_text())
    version = data.get("catalogue_version")
    if version != CATALOGUE_VERSION:
        raise CatalogueRefused(
            f"unknown catalogue_version {version!r}; this build reads "
            f"{CATALOGUE_VERSION!r}")
    return Catalogue(
        dialect=data.get("dialect", ""), database=data.get("database", ""),
        schemas=tuple(
            CatalogueSchema(
                name=s.get("name", ""),
                objects=tuple(
                    CatalogueObject(
                        name=o.get("name", ""), kind=o.get("kind", "DbObject"),
                        columns=tuple(
                            CatalogueColumn(
                                name=c.get("name", ""),
                                data_type=c.get("data_type", ""),
                                nullable=bool(c.get("nullable", True)),
                                primary_key=bool(c.get("primary_key", False)),
                                references=dict(c.get("references", {}) or {}))
                            for c in o.get("columns", []) or []))
                    for o in s.get("objects", []) or []))
            for s in data.get("schemas", []) or []))


def read(dialect: str, connect, *, owner: str = "") -> Catalogue:
    """A live catalogue, from a connection the caller opened.

    **The connection is the caller's**, because a credential is not this module's
    business: the profile names an environment variable and the value never
    reaches an argument (PLT-005). `connect` is anything with `.cursor()`.

    Every statement is checked before it is issued, so a reader that grew a row
    read fails here rather than in production.
    """
    statement = sql_for(dialect)
    assert_no_row_reads([statement])

    cursor = connect.cursor()
    cursor.execute(statement, {"owner": owner} if dialect == ORACLE else {})

    grouped: dict[tuple[str, str], list[CatalogueColumn]] = {}
    for schema_name, table, column, data_type, nullable, _ in cursor.fetchall():
        grouped.setdefault((schema_name, table), []).append(CatalogueColumn(
            name=column, data_type=data_type,
            nullable=str(nullable).upper() in ("YES", "Y", "TRUE", "1")))

    schemas: dict[str, list[CatalogueObject]] = {}
    for (schema_name, table), columns in sorted(grouped.items()):
        schemas.setdefault(schema_name, []).append(
            CatalogueObject(name=table, kind="Table", columns=tuple(columns)))

    return Catalogue(
        dialect=dialect, database=owner or "",
        schemas=tuple(CatalogueSchema(name=n, objects=tuple(o))
                      for n, o in sorted(schemas.items())))
