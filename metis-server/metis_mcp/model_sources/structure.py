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
    # **A selector is NOT authored here.** It was, briefly, and that was the
    # wrong source: a plain-DOM page names its elements in code —
    # `document.getElementById("archive")` — and `js-ui` reads that literal, so
    # the selector is *extracted* like every other fact. What this file
    # describes is what is ON a page; how to find it comes from the code.

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


# The suffixes a UI name carries that say what a thing IS rather than which
# thing it is. Closed on purpose: an open list is a guess that grows, and each
# addition silently re-keys every element that ends in it.
_UI_SUFFIXES = ("button", "input", "link", "field")


def normalised_page_name(name: str) -> str:
    """The join basis between a router screen and an authored page.

    `RecordDetailPage` and `record-detail` both reduce to `recorddetail`.

    **No plural handling, deliberately.** The demo's `RecordListPage` does NOT
    meet `records-list`, and that refutation is the right answer: stripping an
    `s` is an open-ended guess of exactly the kind the UI-suffix list is closed
    to avoid, and it would silently marry a `Records` page to a `Record` route
    on some estate where those are different screens. A reviewer gets a finding
    naming both sides instead.
    """
    flat = "".join(ch for ch in (name or "").casefold() if ch.isalnum())
    return flat[:-4] if flat.endswith("page") and len(flat) > 4 else flat


def normalised_name(name: str) -> str:
    """The join basis between an authored element and an extracted selector.

    Case-folded, separators removed, and one trailing UI suffix stripped — so
    `Archive`, `archive-btn`'s authored `Archive`, and the code's
    `archiveButton` all reduce to `archive`. Verified against the demo page:
    `Apply filter`/`applyFilter`, `New record`/`newRecord`, `Export`/
    `exportButton` all meet.

    Only ONE suffix is stripped, and only from the end. `inputField` is a real
    element name and reducing it to nothing would fuse it with every other.
    """
    flat = "".join(ch for ch in (name or "").casefold() if ch.isalnum())
    for suffix in _UI_SUFFIXES:
        if flat.endswith(suffix) and len(flat) > len(suffix):
            return flat[: -len(suffix)]
    return flat


def element_index(page_elements, name: str) -> dict[int, int]:
    """`{position in walk order: index}` for every element sharing `name`.

    Zero unless the page really does repeat a name, so the common element keeps
    the shortest possible identity and adding a second `Click` does not re-key
    the first.
    """
    positions = [i for i, e in enumerate(page_elements)
                 if normalised_name(e.name) == normalised_name(name)]
    return {pos: n for n, pos in enumerate(positions)}


def element_id_for(page: str, name: str, index: int = 0) -> str:
    """`(page, normalised name, index)` — the identity, not the authored id.

    **The authored `id` becomes display data**, which is the move D-8 already
    made for `name` and I-2 for a transition. Renaming `rl-archive` to
    `archive-btn` in the structure file must not produce a second node for the
    same button; and `records-list` already carries three elements named
    `click`, so a key without an index fuses them into one.
    """
    from metis_mcp.identity.keys import short

    return f"ui:{short(f'{page}|{normalised_name(name)}|{index}')}"


def element_display_name(name: str, index: int, total: int) -> str:
    """The element name, suffixed only where the page has more than one.

    `Click` stays `Click` on a page with one; a page with three gets `Click`,
    `Click 2`, `Click 3`. One-based after the first, because "Click 2" is what a
    person calls the second one and "Click 1" implies there is a zeroth.
    """
    if total <= 1 or index == 0:
        return name
    return f"{name} {index + 1}"


def page_id_for(component: str, page: str) -> str:
    """The id `landing` writes a Page with, so the two agree (I-2).

    `landing.plan_landing` writes `{model_id}::page::{name}`. This planned edges
    against the BARE name, so `Page-[:HAS_ELEMENT]->Form` matched nothing even
    when the page was there — the namespacing trap, in the one place both
    writers touch the same node.
    """
    return f"{component}::page::{page}" if component else page


def pending_selectors(structure: Structure) -> list:
    """One `element_selector` proposal per authored element (X-19).

    **The last hand-made join.** Until now the authored element and the
    extracted selector were married in `test_scaffold.py` by a dict — which
    meant the Page Object a test asserted on was one the engine could not
    produce. This is the same deferred-join machinery the data layer uses, so
    the answer is the same three-way one: confirmed where the web intake found
    a selector, refuted where it ran and found none, and still proposed where it
    has not run. Those are different facts and a reviewer needs to know which.
    """
    from metis_mcp.resolution import PendingJoin

    out = []
    for page, roots in sorted(structure.pages.items()):
        walked = [e for root in roots for e in root.walk()]
        by_name: dict[str, list] = {}
        for element in walked:
            by_name.setdefault(normalised_name(element.name), []).append(element)
        for join_name, group in sorted(by_name.items()):
            for index, element in enumerate(group):
                out.append(PendingJoin(
                    kind="element_selector",
                    from_id=element_id_for(page, element.name, index),
                    to_ref=join_name,
                    basis=f"element name {element.name!r} on page {page!r}",
                    detail=element.kind))
    return out


def pending_routes(routes) -> list:
    """One `route_page` proposal per frontend route (X-19).

    `RENDERS` was declared in the ontology with **no writer at all** — the third
    relationship in that state, alongside `USES` and `LINKS_TO`. It is a name
    join between two intakes that arrive separately, which is exactly what the
    resolution engine is for, so it becomes a proposal rather than a writer.

    `routes` is `[{"path": ..., "screen": ...}]` as the web intake reports them.
    A route whose screen the router did not name is skipped: there is nothing to
    join on, and proposing against an empty string would marry every such route
    to whichever page also has none.
    """
    from metis_mcp.resolution import PendingJoin

    out = []
    for route in routes or ():
        path = route.get("path") if isinstance(route, dict) else str(route)
        screen = route.get("screen", "") if isinstance(route, dict) else ""
        if not path or not screen:
            continue
        out.append(PendingJoin(
            kind="route_page", from_id=path, to_ref=normalised_page_name(screen),
            basis=f"router screen {screen!r} for route {path!r}",
            detail=screen))
    return out


def route_resolution(structure: Structure | None, routes):
    """Settle `Route -[:RENDERS]-> Page`. `(Resolution, [(route, page)])`.

    `structure` is None where the structure intake has not run, which leaves
    every proposal `proposed` rather than refuting it.
    """
    from metis_mcp.resolution import resolve

    pending = pending_routes(routes)
    if structure is None:
        return resolve(pending, {}), []

    by_basis = {normalised_page_name(page): page for page in structure.pages}
    resolution = resolve(pending, {"structure": set(by_basis)})
    return resolution, [(join.from_id, by_basis[join.to_ref])
                        for join, _ in resolution.confirmed]


def selector_resolution(structure: Structure, extracted: dict | None):
    """Run the deferred join. `(Resolution, {element_id: selector})`.

    `extracted` is `{normalised name: selector}` from the web intake, or **None
    where that intake has not run** — and the difference is the whole point of
    routing this through `resolve` rather than a `dict.get`. An absent intake
    leaves every proposal `proposed`; a present one that lacks the name
    `refutes` it. A dict collapses those into the same empty string, and a
    reviewer never learns which of the two they are looking at.
    """
    from metis_mcp.resolution import properties_for, resolve

    pending = pending_selectors(structure)
    available = {} if extracted is None else {"web": set(extracted)}
    resolution = resolve(pending, available)
    values = properties_for(
        resolution, lambda ref: (extracted or {}).get(ref, ""))
    return resolution, {from_id: value for _, from_id, _, value in values}


def elements_for(structure: Structure, page: str, selectors: dict) -> list[dict]:
    """The flat element list a Page Object is rendered from.

    Identity and display name come from the same helpers `plan_structure` uses,
    so what is rendered and what is landed cannot disagree.
    """
    walked = [e for root in structure.pages.get(page, ()) for e in root.walk()]
    by_name: dict[str, list] = {}
    for element in walked:
        by_name.setdefault(normalised_name(element.name), []).append(element)

    out = []
    for group in by_name.values():
        for index, element in enumerate(group):
            node_id = element_id_for(page, element.name, index)
            out.append({
                "id": node_id, "kind": element.kind,
                "name": element_display_name(element.name, index, len(group)),
                "selector": selectors.get(node_id, ""),
                "on_event": element.on_event,
                "navigates_to": element.navigates_to,
            })
    return sorted(out, key=lambda e: e["name"])


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
        # Identity is `(page, normalised name, index)`, so the walk has to be
        # materialised before any node is written: the index of the first
        # `Click` depends on whether a second one exists further down.
        walked = [e for root in roots for e in root.walk()]
        by_name: dict[str, list] = {}
        for element in walked:
            by_name.setdefault(normalised_name(element.name), []).append(element)
        identity: dict[int, tuple[str, str, str]] = {}
        for group in by_name.values():
            for index, element in enumerate(group):
                identity[id(element)] = (
                    element_id_for(page, element.name, index),
                    element_display_name(element.name, index, len(group)),
                    normalised_name(element.name))

        for root in roots:
            for element in root.walk():
                node_id, display, join_name = identity[id(element)]
                add_node(element.kind, {
                    "id": node_id, "source_episode_id": episode_id,
                    "name": display, "element_type": element.kind,
                    "page": page, "lifecycle_state": QUARANTINE,
                    # What the authored file called it. Display data now, and
                    # kept so a reviewer can find the entry that produced this.
                    "authored_id": element.id,
                    # The basis the extracted selector joins on (X-19).
                    "join_name": join_name,
                })
                for child in element.contains:
                    add_edge(element.kind, node_id, "HAS_ELEMENT",
                             child.kind, identity[id(child)][0])
                # `Action -[:ON_EVENT]-> Event` — catalogued since the Web
                # layer landed, read out of the file into `Element.on_event`,
                # and never written. The interaction that invokes an action is
                # what a generated Page Object method actually performs, so
                # without it the graph holds the button and not the click.
                if element.on_event:
                    add_edge(element.kind, node_id, "ON_EVENT",
                             "Event", element.on_event)
                if element.kind == "Navigation" and element.navigates_to:
                    add_edge("Navigation", node_id, "NAVIGATES_TO",
                             "Page", page_id_for(component, element.navigates_to))
            add_edge("Page", page_id_for(component, page), "HAS_ELEMENT",
                     root.kind, identity[id(root)][0])

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
