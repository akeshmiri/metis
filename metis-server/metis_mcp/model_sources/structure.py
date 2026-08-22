"""
Authored structure: what is on a page, and where the data lives
(application spec §5.2a, §5.2b; D-1, D-14).

**Why authored and not extracted.** No pack identifies component *types*.
`react-ui` recovers screens, route paths and status variables; `js-ui` recovers
`addEventListener` bindings whose element selector its own comment calls
"frequently NOT recoverable". Neither can tell a library `<DataGrid>` from a
hand-rolled `<div role="table">` from a `<table>`, and all three are a table to
the person writing a test. A database catalogue read from a live connection is
the obvious future writer for the data half and is not this either.

So a person says so, in a checked-in file, reviewed in a pull request — the same
discipline as the glossary and the knowledge file. When an extractor can fill
part of it in, it writes the same labels through the same landing planner and
nothing about the ontology changes.

**Two trees, one module**, because they are one idea at two ends: a `UiTable` on
a page and the `Table` it lists come from the same authored description of a
system, and splitting them into two files would make the join between them
somebody's manual bookkeeping.

    Page ──HAS_ELEMENT──▶ UiTable ──HAS_ELEMENT──▶ Row / Pagination / Sort / Action
    Datasource ──CONNECTS_TO──▶ Database ──HAS_SCHEMA──▶ Schema ──HAS_OBJECT──▶ Table
                                                                        │
                                          BusinessEntity ──STORED_IN────┘
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from metis_mcp.mbt.model import QUARANTINE
from metis_mcp.ontology.labels import LABELS

FILE_VERSION = "metis.structure/1"

# The element kinds a container may hold, straight from the catalogue — so the
# file's rules and the ontology's cannot disagree.
UI_KINDS = ("Menu", "UiTable", "Form", "Dialog", "Row", "Pagination", "Sort",
            "Action", "Event", "Navigation", "UiElement")
DB_KINDS = ("Table", "View", "Function", "DbObject")

UNKNOWN_KIND = "unknown_kind"
ILLEGAL_CONTAINMENT = "illegal_containment"
DUPLICATE_ID = "duplicate_id"
MISSING_FIELD = "missing_field"
DANGLING_REFERENCE = "dangling_reference"


@dataclass(frozen=True)
class Element:
    """One control, and what it contains. Recursive: the tree is the point."""

    id: str
    kind: str
    name: str = ""
    page: str = ""
    contains: tuple["Element", ...] = ()
    # For an Action: the event that invokes it. For a Navigation: where it goes.
    on_event: str = ""
    navigates_to: str = ""

    def walk(self):
        yield self
        for child in self.contains:
            yield from child.walk()


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class DbObjectSpec:
    id: str
    kind: str
    name: str
    columns: tuple[Column, ...] = ()


@dataclass(frozen=True)
class SchemaSpec:
    id: str
    name: str
    objects: tuple[DbObjectSpec, ...] = ()


@dataclass(frozen=True)
class DatabaseSpec:
    id: str
    name: str
    schemas: tuple[SchemaSpec, ...] = ()


@dataclass(frozen=True)
class DatasourceSpec:
    id: str
    name: str
    dialect: str
    database: str = ""


@dataclass(frozen=True)
class Problem:
    kind: str
    entry_id: str
    detail: str

    def describe(self) -> str:
        return f"[{self.kind:<21}] {self.entry_id}: {self.detail}"


@dataclass
class Structure:
    pages: dict[str, tuple[Element, ...]] = field(default_factory=dict)
    datasources: list[DatasourceSpec] = field(default_factory=list)
    databases: list[DatabaseSpec] = field(default_factory=list)
    # `BusinessEntity id -> table id`. The join that makes "a record exists in
    # Archived state" answerable: the entity is what the business calls it, the
    # table is where it is kept.
    stored_in: dict[str, str] = field(default_factory=dict)

    def elements(self):
        for page, roots in sorted(self.pages.items()):
            for root in roots:
                yield from root.walk()


class StructureRefused(Exception):
    """The file could not be read at all — shape, not content."""


def _element(raw: dict, page: str) -> Element:
    return Element(
        id=raw["id"], kind=raw.get("kind", "UiElement"),
        name=raw.get("name", raw["id"]), page=page,
        on_event=raw.get("on_event", ""),
        navigates_to=raw.get("navigates_to", ""),
        contains=tuple(_element(c, page) for c in raw.get("contains", []) or []),
    )


def load(path: str | Path) -> Structure:
    data = json.loads(Path(path).read_text())
    version = data.get("structure_version")
    if version != FILE_VERSION:
        raise StructureRefused(
            f"unknown structure_version {version!r}; this build reads {FILE_VERSION!r}")

    structure = Structure()
    for page, elements in (data.get("pages", {}) or {}).items():
        structure.pages[page] = tuple(_element(e, page) for e in elements or [])

    for ds in data.get("datasources", []) or []:
        structure.datasources.append(DatasourceSpec(
            id=ds["id"], name=ds.get("name", ds["id"]),
            dialect=ds.get("dialect", ""), database=ds.get("database", "")))

    for db in data.get("databases", []) or []:
        structure.databases.append(DatabaseSpec(
            id=db["id"], name=db.get("name", db["id"]),
            schemas=tuple(SchemaSpec(
                id=sc["id"], name=sc.get("name", sc["id"]),
                objects=tuple(DbObjectSpec(
                    id=o["id"], kind=o.get("kind", "DbObject"),
                    name=o.get("name", o["id"]),
                    columns=tuple(Column(
                        name=c["name"], data_type=c.get("data_type", ""),
                        constraints=tuple(c.get("constraints", ()) or ()))
                        for c in o.get("columns", []) or []))
                    for o in sc.get("objects", []) or []))
                for sc in db.get("schemas", []) or [])))

    structure.stored_in = dict(data.get("stored_in", {}) or {})
    return structure


def _containment_allowed(container_kind: str, child_kind: str) -> bool:
    """Read from the catalogue, never restated here.

    A second copy of the containment rules is a second thing to keep in step, and
    D-2's whole point is that the four places are kept together rather than
    remembered separately.
    """
    from metis_mcp.ontology.labels import is_allowed

    return is_allowed(container_kind, "HAS_ELEMENT", child_kind)


def validate(structure: Structure) -> list[Problem]:
    problems: list[Problem] = []
    seen: set[str] = set()

    for page, roots in sorted(structure.pages.items()):
        for root in roots:
            for element in root.walk():
                if element.id in seen:
                    problems.append(Problem(DUPLICATE_ID, element.id,
                                            "two elements share this id"))
                seen.add(element.id)
                if element.kind not in UI_KINDS:
                    problems.append(Problem(
                        UNKNOWN_KIND, element.id,
                        f"{element.kind!r} is not a UI element kind. Known: "
                        f"{', '.join(UI_KINDS)}"))
                    continue
                for child in element.contains:
                    if child.kind in UI_KINDS and not _containment_allowed(
                            element.kind, child.kind):
                        problems.append(Problem(
                            ILLEGAL_CONTAINMENT, child.id,
                            f"a {child.kind} cannot sit inside a {element.kind} — "
                            f"the catalogue does not allow that edge, and landing "
                            f"would refuse it"))
            if not _containment_allowed("Page", root.kind) and root.kind in UI_KINDS:
                problems.append(Problem(
                    ILLEGAL_CONTAINMENT, root.id,
                    f"a {root.kind} cannot sit directly on a Page"))

    known_pages = set(structure.pages)
    for element in structure.elements():
        if element.navigates_to and element.kind != "Navigation":
            problems.append(Problem(
                MISSING_FIELD, element.id,
                f"`navigates_to` is set on a {element.kind}; only a Navigation "
                f"goes somewhere"))
        if element.navigates_to and element.navigates_to not in known_pages:
            problems.append(Problem(
                DANGLING_REFERENCE, element.id,
                f"navigates_to {element.navigates_to!r} is not a page in this file"))

    tables = {o.id for db in structure.databases for sc in db.schemas
              for o in sc.objects}
    for entity_id, table_id in sorted(structure.stored_in.items()):
        if table_id not in tables:
            problems.append(Problem(
                DANGLING_REFERENCE, entity_id,
                f"stored_in names {table_id!r}, which is not an object in this file"))

    databases = {db.id for db in structure.databases}
    for ds in structure.datasources:
        if not ds.dialect:
            problems.append(Problem(
                MISSING_FIELD, ds.id,
                "no dialect. Which SQL a datasource speaks decides what a test can "
                "issue through it, and it is not guessable from a connection string"))
        if ds.database and ds.database not in databases:
            problems.append(Problem(
                DANGLING_REFERENCE, ds.id,
                f"connects to {ds.database!r}, which is not a database in this file"))

    for db in structure.databases:
        for sc in db.schemas:
            for obj in sc.objects:
                if obj.kind not in DB_KINDS:
                    problems.append(Problem(
                        UNKNOWN_KIND, obj.id,
                        f"{obj.kind!r} is not a database object kind. Known: "
                        f"{', '.join(DB_KINDS)} — an object whose kind nobody "
                        f"classified stays `DbObject`, which is a worklist"))
                for column in obj.columns:
                    if not column.data_type:
                        problems.append(Problem(
                            MISSING_FIELD, f"{obj.id}.{column.name}",
                            "no data_type. A column whose type nobody recorded "
                            "cannot tell a fixture what to put in it"))
    return problems


def page_id_for(component: str, page: str) -> str:
    """The id `landing` writes a Page with, so the two agree (I-2).

    `landing.plan_landing` writes `{model_id}::page::{name}`. This planned edges
    against the BARE name, so `Page-[:HAS_ELEMENT]->Form` matched nothing even
    when the page was there — the namespacing trap, in the one place both
    writers touch the same node.
    """
    return f"{component}::page::{page}" if component else page


def plan_structure(structure: Structure, episode_id: str,
                   component: str = "") -> "LandingPlan":
    """Both trees, through the ontology gate that already exists.

    `component` is the deployable these screens belong to. Given one, the pages
    are **created** here rather than assumed: `Page` requires a `component`, and
    without it this could only ever reference a page some other source had
    already landed — which made a structure file unable to stand on its own and
    every one of its `HAS_ELEMENT` edges unmatched on a fresh graph.

    Omit it and the old behaviour holds: pages are referenced, not created, and
    the model source must land first.
    """
    from metis_mcp.model_sources.landing import LandingPlan, PlannedEdge, PlannedNode
    from metis_mcp.ontology.validation import validate as validate_node
    from metis_mcp.ontology.validation import validate_relationship

    plan = LandingPlan(episode_id=episode_id)

    def add_node(label: str, props: dict) -> bool:
        outcome = validate_node(label, props)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return False
        plan.nodes.append(PlannedNode(label=label, properties=props))
        return True

    def add_edge(fl: str, fid: str, rel: str, tl: str, tid: str) -> None:
        outcome = validate_relationship(fl, rel, tl)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return
        plan.edges.append(PlannedEdge(fl, fid, rel, tl, tid))

    for page, roots in sorted(structure.pages.items()):
        if component:
            add_node("Page", {
                "id": page_id_for(component, page), "source_episode_id": episode_id,
                "name": page, "component": component,
                "lifecycle_state": QUARANTINE,
            })
        for root in roots:
            for element in root.walk():
                add_node(element.kind, {
                    "id": element.id, "source_episode_id": episode_id,
                    "name": element.name, "element_type": element.kind,
                    "page": page, "lifecycle_state": QUARANTINE,
                })
                for child in element.contains:
                    add_edge(element.kind, element.id, "HAS_ELEMENT",
                             child.kind, child.id)
                if element.kind == "Navigation" and element.navigates_to:
                    add_edge("Navigation", element.id, "NAVIGATES_TO",
                             "Page", page_id_for(component, element.navigates_to))
            add_edge("Page", page_id_for(component, page), "HAS_ELEMENT",
                     root.kind, root.id)

    for ds in structure.datasources:
        add_node("Datasource", {
            "id": ds.id, "source_episode_id": episode_id, "name": ds.name,
            "dialect": ds.dialect})
        if ds.database:
            add_edge("Datasource", ds.id, "CONNECTS_TO", "Database", ds.database)

    for db in structure.databases:
        add_node("Database", {"id": db.id, "source_episode_id": episode_id,
                              "name": db.name})
        for sc in db.schemas:
            add_node("Schema", {"id": sc.id, "source_episode_id": episode_id,
                                "name": sc.name})
            add_edge("Database", db.id, "HAS_SCHEMA", "Schema", sc.id)
            for obj in sc.objects:
                add_node(obj.kind, {
                    "id": obj.id, "source_episode_id": episode_id,
                    "name": obj.name, "object_type": obj.kind})
                add_edge("Schema", sc.id, "HAS_OBJECT", obj.kind, obj.id)
                for column in obj.columns:
                    column_id = f"{obj.id}.{column.name}"
                    add_node("Column", {
                        "id": column_id, "source_episode_id": episode_id,
                        "name": column.name, "data_type": column.data_type,
                        "constraints": list(column.constraints)})
                    add_edge(obj.kind, obj.id, "HAS_COLUMN", "Column", column_id)

    for entity_id, table_id in sorted(structure.stored_in.items()):
        add_edge("BusinessEntity", entity_id, "STORED_IN", "Table", table_id)

    return plan


def format_problems(problems: list[Problem], structure: Structure) -> str:
    if not problems:
        elements = sum(1 for _ in structure.elements())
        columns = sum(len(o.columns) for db in structure.databases
                      for sc in db.schemas for o in sc.objects)
        return (f"Structure — {len(structure.pages)} page(s), {elements} element(s); "
                f"{len(structure.databases)} database(s), {columns} column(s).")
    lines = [f"Structure — {len(problems)} problem(s); nothing is landed until "
             f"they are fixed.", ""]
    return "\n".join(lines + [f"  {p.describe()}" for p in problems])
