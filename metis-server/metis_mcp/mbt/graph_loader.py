"""
Load a Model from the graph (application spec §16.1 job 1).

The graph *is* the model -- states are nodes, transitions are edges, so loading is
a projection rather than a reassembly. That is the first of the three jobs §16.1
gives the graph database, and this module is where it pays off.

Split deliberately into a **pure mapper** and a **thin reader**:

    rows_to_model(...)          pure; no session; fully unit-testable
    load_from_graph(session,..) three queries, then delegates to the mapper

Same discipline as requirement_landing.py's planner/writer split, for the same
reason: the interesting part -- shape, ordering, error handling -- is provable
without a container, and only the query text needs a live database to verify.

Lifecycle is read from the graph here, unlike the file loader: in the graph,
`lifecycle_state` *is* where human decisions live (spec §8.6), so there is no
separate overlay to apply.
"""
from __future__ import annotations

import json

from dataclasses import dataclass

from metis_mcp.mbt.coverage import ComponentRef
from metis_mcp.mbt.model import (
    CONSTRUCTED,
    IMPLEMENTED,
    QUARANTINE,
    Model,
    State,
    GuardCheck,
    Transition,
)
from metis_mcp.ontology.labels import label_expression

# One model is one <journey>-<surface> machine (spec M-1). `functional_areas`
# carries the journey (M-4) and `surface` the other half of the identity.
# ---------------------------------------------------------------------------
# Bi-temporal reads (see ontology.labels.VALIDITY_LABELS)
# ---------------------------------------------------------------------------

def valid_where_it_applies(alias: str) -> str:
    """Present-tense, for a read spanning labels that do not all carry validity.

    Search covers six labels and only four have a window, so a bare
    `valid_to = ''` drops `BusinessEntity` and `Lesson` entirely — measured: a
    search for a term in a landed lesson returned nothing at all.

    This asks the question per node instead: a label with no window passes, and
    one that has a window must have an open one. It is NOT the `IS NULL`
    tolerance that was removed — that accepted a validity-carrying node with no
    window, which is the ambiguity `backfill-validity` exists to end. This
    accepts only labels for which a window was never defined.
    """
    from metis_mcp.ontology.labels import VALIDITY_LABELS

    carries = " OR ".join(f"l = '{label}'" for label in VALIDITY_LABELS)
    return (f"(NOT any(l IN labels({alias}) WHERE {carries}) "
            f"OR {alias}.valid_to = '')")


def currently_valid(*aliases: str) -> str:
    """The clause that keeps a read in the present tense.

    **Every validity-carrying node is required to have a window**, so this asks
    for one rather than tolerating its absence. It used to accept `valid_to IS
    NULL` as "still valid", which kept a graph readable across the release that
    introduced validity — and made a node whose window was never set
    indistinguishable from one deliberately left open.

    `metis backfill-validity` is what closes that gap on an existing graph, and
    it must be run BEFORE this build reads one: a node with no `valid_from` now
    drops out of every read, and the query still succeeds while it does.

    Composed rather than f-string-interpolated into the query bodies: those
    contain literal Cypher maps (`{id: ac.id, ...}`), and an f-string would need
    every brace doubled — a silent corruption waiting for whoever edits next.
    """
    return " AND ".join(f"({a}.valid_to = '')" for a in aliases)


STATES_CYPHER = """
MATCH (s:State)
WHERE $journey IN s.functional_areas AND s.b_surface = $surface
RETURN s.id             AS id,
       s.name           AS name,
       s.b_surface        AS surface,
       s.b_is_initial     AS is_initial,
       s.lifecycle_state AS lifecycle_state,
       s.x_name_tier      AS name_tier,
       // Written by landing since the Web surface was added, and never read
       // back. `condition` is what a state MEANS ("no metric exists") where its
       // name says only what it is called, so a spec rendered from a
       // graph-loaded model fell back to the code convention for every Given.
       s.p_condition      AS condition,
       s.p_page           AS page
ORDER BY s.id
"""

# What a refusal offers instead. A wrong journey is nearly always a near-miss --
# the model id for the journey, a surface that was never built -- so listing the
# real pairs turns a dead end into one more call.
# The two-hop path from a transition to the conditions that selected it.
# `DERIVED_FROM` reaches the outcome the transition was recovered from, and
# `GUARDED_BY` the checks that chose that outcome over its siblings.
CHECKS_CYPHER = """
MATCH (t:Transition|ApiCall|UiAction)-[:DERIVED_FROM]->(:DeclaredOutcome)
      -[:GUARDED_BY]->(c:Check)
WHERE $journey IN t.functional_areas AND t.b_surface = $surface
RETURN t.id             AS transition,
       c.expression     AS expression,
       c.order          AS order,
       c.dimension_class AS dimension_class,
       c.anchor         AS anchor
ORDER BY t.id, c.order, c.expression
"""

AVAILABLE_CYPHER = """
MATCH (s:State)
WHERE s.functional_areas IS NOT NULL AND s.b_surface IS NOT NULL
UNWIND s.functional_areas AS journey
RETURN DISTINCT journey AS journey, s.b_surface AS surface
ORDER BY journey, surface
"""

TRANSITIONS_CYPHER = """
MATCH (src:State)-[:WHEN]->(t:Transition|ApiCall|UiAction)-[:THEN]->(tgt:State)
WHERE $journey IN t.functional_areas AND t.b_surface = $surface
RETURN t.id                    AS id,
       src.id                  AS source,
       t.c_trigger               AS trigger,
       tgt.id                  AS target,
       t.b_guard_expression      AS guard,
       t.b_implementation_status AS implementation_status,
       t.lifecycle_state       AS lifecycle_state,
       t.c_outcome_status        AS outcome_status,
       t.x_guard_anchor          AS guard_anchor,
       t.x_source_state_unresolved AS source_state_unresolved,
       t.c_inputs           AS inputs_json,
       t.c_security         AS security_json,
       t.x_outcome_source        AS outcome_source,
       t.x_guard_claim           AS guard_claim,
       t.data_requirements     AS data_requirements,
       t.c_response_body         AS response_body,
       t.c_media_types           AS media_types,
       t.x_name_tier             AS name_tier,
       t.x_guard_wording         AS guard_wording,
       t.x_guard_tier            AS guard_tier
ORDER BY t.id
"""

# Cross-surface invocation (spec M-5a). Loaded separately because it spans two
# models and therefore cannot belong to either one's node set.
# **Confirmed links only (M-5g, F-7).** An `INVOKES` edge may exist as a
# *proposal* so a reviewer can see and decide it; an unconfirmed proposal must
# not behave like a fact. Without this filter a stored proposal would credit
# cross-surface coverage and lend its guard to a UI transition, which is a
# machine guess raising a coverage number — the exact thing "proposed, never
# asserted" exists to prevent.
INVOKES_CYPHER = """
MATCH (ui:Transition|ApiCall|UiAction)-[r:INVOKES]->(api:Transition|ApiCall|UiAction)
WHERE $journey IN ui.functional_areas
  AND r.confirmed_by IS NOT NULL AND r.confirmed_by <> ''
RETURN ui.id AS ui_transition, api.id AS api_transition
ORDER BY ui.id
"""


# The guard a UI transition INHERITS from the API transition it invokes (M-5c).
# One hop, because the guard lives on the far side of the edge: a UI model loaded
# on its own contains the transitions but not the conditions that determine them.
INHERITED_GUARDS_CYPHER = """
MATCH (ui:Transition|ApiCall|UiAction)-[r:INVOKES]->(api:Transition|ApiCall|UiAction)
WHERE $journey IN ui.functional_areas
  AND r.confirmed_by IS NOT NULL AND r.confirmed_by <> ''
  AND api.b_guard_expression IS NOT NULL AND api.b_guard_expression <> ''
RETURN ui.id AS ui_transition, api.b_guard_expression AS guard
ORDER BY ui.id
"""


# What a UI action **starts**. One-to-many by nature: opening a page fires every
# panel's request at once.
#
# Kept out of the `{ui: api}` map on purpose. That map is one-to-one, and when it
# held both kinds a page that opened three calls stored one and **silently
# dropped two** — the loss was invisible because a dict does not complain about
# being overwritten.
TRIGGERS_CYPHER = """
MATCH (ui:Transition|ApiCall|UiAction)-[r:TRIGGERS]->(api:Transition|ApiCall|UiAction)
WHERE $journey IN ui.functional_areas
  AND r.confirmed_by IS NOT NULL AND r.confirmed_by <> ''
RETURN ui.id AS ui_transition, api.id AS api_transition
ORDER BY ui.id, api.id
"""


# P-16's other half: which version a coverage figure is about.
#
# `Component` identity is `(component, commit)` (spec D-6), so a component with
# several commits has several nodes. The newest one is the version a report about
# "now" refers to; ordering is by `version` then `id` rather than a timestamp
# because `id` is content-derived and therefore stable, and a tie on `version` is
# broken deterministically instead of arbitrarily.
COMPONENT_CYPHER = f"""
MATCH (c:{label_expression("Component")})
WHERE c.journey = $journey AND c.b_surface = $surface
RETURN c.id AS id, c.component AS component, c.version AS version,
       c.commit_sha AS commit_sha
ORDER BY c.version DESC, c.id
LIMIT 1
"""

# `AcceptanceCriterion -[:VALIDATES]-> Transition` is the ONLY traceability edge
# into behaviour (D-4), which is what makes criterion coverage answerable at all
# without any execution data (C-10).
#
# The label disjunction comes from `label_expression`, not from a literal, so a
# new `Transition` specialisation cannot silently fall out of the result: a
# specialisation is written INSTEAD of its parent, so a hardcoded `:Transition`
# would return only the unclassified ones.
VALIDATING_CRITERIA_CYPHER = f"""
MATCH (ac:AcceptanceCriterion)-[:VALIDATES]->(t:{label_expression("Transition")})
WHERE $journey IN t.functional_areas AND t.b_surface = $surface
  AND {currently_valid("ac")}
RETURN t.id AS transition_id, ac.id AS criterion_id
ORDER BY t.id, ac.id
"""


def load_component(session, journey: str, surface: str = "api") -> ComponentRef | None:
    """The `Component` a `<journey>-<surface>` coverage figure refers to (P-16).

    `None` when no version has been persisted for this model -- a real state,
    not an error, and one the report names rather than papering over.
    """
    row = session.run(COMPONENT_CYPHER, journey=journey, surface=surface).single()
    if row is None:
        return None
    return ComponentRef(
        id=row["id"] or "",
        component=row["component"] or f"{journey}-{surface}",
        # `version` is written as an int by `plan_persist`; the ref carries it as
        # display text, so normalise here rather than at three call sites.
        version=str(row["version"]) if row["version"] is not None else "",
        commit_sha=row["commit_sha"] or "",
    )


def load_validating_criteria(session, journey: str,
                             surface: str = "api") -> dict[str, list[str]]:
    """`{transition_id: [criterion_id, ...]}` -- who validates what."""
    out: dict[str, list[str]] = {}
    for row in session.run(VALIDATING_CRITERIA_CYPHER, journey=journey, surface=surface):
        out.setdefault(row["transition_id"], []).append(row["criterion_id"])
    return out


def load_triggers(session, journey: str) -> dict[str, list[str]]:
    """`{ui_transition_id: [api_transition_id, ...]}` — every one of them."""
    out: dict[str, list[str]] = {}
    for row in session.run(TRIGGERS_CYPHER, journey=journey):
        out.setdefault(row["ui_transition"], []).append(row["api_transition"])
    return out


def load_inherited_guards(session, journey: str) -> dict[str, str]:
    """`{ui_transition_id: inherited guard}` for `validate(..., inherited=...)`."""
    return {r["ui_transition"]: r["guard"]
            for r in session.run(INHERITED_GUARDS_CYPHER, journey=journey)}


@dataclass
class LoadReport:
    """What was loaded, and what was skipped and why.

    Skips are reported rather than counted: a transition dropped because its
    source state was filtered out is a modelling problem, and silently shrinking
    the model would hide it.
    """

    model: Model
    skipped: list[tuple[str, str]]  # (transition id, reason)
    invokes: dict[str, str]
    # Whether the graph held anything for this `<journey>-<surface>` at all.
    #
    # An empty `Model` is what both a typo and a real-but-empty journey produce,
    # and the two need different answers: `get_model("mfa-api")` -- the model id
    # rather than the journey -- returned `ok: true` with zero states, and
    # `coverage` returned a complete report with `uncovered: 0`. A reader, or an
    # agent, takes that for "nothing is uncovered". The distinction is made here
    # because this is the only layer that saw the rows.
    found: bool = True


def rows_to_model(model_id: str, state_rows: list[dict], transition_rows: list[dict],
                  invokes_rows: list[dict] | None = None,
                  check_rows: list[dict] | None = None) -> LoadReport:
    """Pure mapper: rows in, Model out. No session, no I/O.

    Rows are taken as already ordered by the queries; ordering is re-asserted
    here anyway, because generation determinism (spec P-7) must not depend on a
    driver preserving result order.
    """
    states: dict[str, State] = {}
    for row in sorted(state_rows, key=lambda r: r["id"]):
        states[row["id"]] = State(
            id=row["id"],
            name=row.get("name") or row["id"],
            surface=row.get("surface") or "api",
            is_initial=bool(row.get("is_initial")),
            lifecycle_state=row.get("lifecycle_state") or QUARANTINE,
            name_tier=row.get("name_tier") or "",
            condition=row.get("condition") or "",
            page=row.get("page") or "",
        )

    # `GUARDED_BY`, grouped by the transition it reaches. The query orders by
    # `c.order`, so a check's position in this tuple IS its evaluation order.
    checks_by_transition: dict[str, list[GuardCheck]] = {}
    for row in check_rows or []:
        if not (row.get("expression") or "").strip():
            continue          # a Check with no expression states nothing
        checks_by_transition.setdefault(row["transition"], []).append(GuardCheck(
            expression=row["expression"],
            order=int(row.get("order") or 0),
            dimension_class=row.get("dimension_class") or "",
            anchor=row.get("anchor") or ""))
    for group in checks_by_transition.values():
        group.sort(key=lambda c: (c.order, c.expression))

    transitions: dict[str, Transition] = {}
    skipped: list[tuple[str, str]] = []
    for row in sorted(transition_rows, key=lambda r: r["id"]):
        source, target = row.get("source"), row.get("target")
        if source not in states:
            skipped.append((row["id"], f"source state {source!r} not in this model"))
            continue
        if target not in states:
            skipped.append((row["id"], f"target state {target!r} not in this model"))
            continue
        if not row.get("trigger"):
            # A transition without a trigger cannot be exercised; it is a model
            # defect, not something to fill in with a placeholder.
            skipped.append((row["id"], "no trigger"))
            continue
        transitions[row["id"]] = Transition(
            checks=tuple(checks_by_transition.get(row["id"], ())),
            id=row["id"],
            source=source,
            trigger=row["trigger"],
            target=target,
            guard=row.get("guard") or "",
            implementation_status=row.get("implementation_status") or IMPLEMENTED,
            lifecycle_state=row.get("lifecycle_state") or QUARANTINE,
            # Read back, not dropped. The workflow loads its model from the
            # graph, so anything lost here is lost to every generated case --
            # a `POST` would render with no request data even though the pack
            # recovered it, which is the defect this whole chain exists to fix.
            outcome_status=row.get("outcome_status"),
            guard_anchor=row.get("guard_anchor") or "",
            source_state_unresolved=bool(row.get("source_state_unresolved")),
            outcome_source=row.get("outcome_source") or CONSTRUCTED,
            guard_claim=row.get("guard_claim") or "",
            data_requirements=tuple(row.get("data_requirements") or ()),
            response_body=row.get("response_body") or "",
            media_types=tuple(row.get("media_types") or ()),
            name_tier=row.get("name_tier") or "",
            guard_wording=row.get("guard_wording") or "",
            guard_tier=row.get("guard_tier") or "",
            inputs=tuple(_json_rows(row.get("inputs_json"))),
            security=tuple(_json_rows(row.get("security_json"))),
        )

    invokes = {
        r["ui_transition"]: r["api_transition"]
        for r in sorted(invokes_rows or [], key=lambda r: r["ui_transition"])
    }

    return LoadReport(
        model=Model(id=model_id, states=states, transitions=transitions),
        skipped=skipped,
        invokes=invokes,
        found=bool(state_rows or transition_rows),
    )


def _json_rows(raw) -> list:
    """Decode a JSON-text property, tolerating absence and malformed text.

    Structure cannot be a Neo4j property (see `ontology/labels.py`), so these
    ride as JSON. A decode failure yields nothing rather than raising: a model
    that cannot be loaded at all is a worse outcome than one that reports no
    inputs, and `check_callability` already treats missing inputs as a finding.
    """
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def load_from_graph(session, journey: str, surface: str = "api") -> LoadReport:
    """Read one `<journey>-<surface>` model from the graph.

    Thin by design: three queries, then the pure mapper. Everything worth testing
    lives in `rows_to_model`.
    """
    params = {"journey": journey, "surface": surface}
    state_rows = [dict(r) for r in session.run(STATES_CYPHER, **params)]
    transition_rows = [dict(r) for r in session.run(TRANSITIONS_CYPHER, **params)]
    invokes_rows = [dict(r) for r in session.run(INVOKES_CYPHER, journey=journey)]
    check_rows = [dict(r) for r in session.run(CHECKS_CYPHER, **params)]
    return rows_to_model(f"{journey}-{surface}", state_rows, transition_rows,
                         invokes_rows, check_rows)


def available_models(session) -> list[tuple[str, str]]:
    """Every `(journey, surface)` the graph actually holds."""
    return [(r["journey"], r["surface"]) for r in session.run(AVAILABLE_CYPHER)]


# ---------------------------------------------------------------------------
# The business layer (§4.6a, D-13) — what an entity document is built from
# ---------------------------------------------------------------------------

ENTITIES_CYPHER = """
MATCH (e:BusinessEntity)
OPTIONAL MATCH (e)-[:BELONGS_TO]->(a:BusinessArea)
WHERE $area = '' OR a.id = $area OR a.name = $area
WITH e, a
WHERE $area = '' OR a IS NOT NULL
RETURN e.id AS id, e.name AS name, e.description AS description,
       e.impact AS impact, e.properties_json AS properties_json,
       a.id AS area, a.name AS area_name
ORDER BY e.name
"""

ENTITY_CYPHER = """
MATCH (e:BusinessEntity)
WHERE e.id = $name OR e.name = $name
OPTIONAL MATCH (e)-[:BELONGS_TO]->(a:BusinessArea)
RETURN e.id AS id, e.name AS name, e.description AS description,
       e.impact AS impact, e.properties_json AS properties_json,
       a.id AS area, a.name AS area_name
LIMIT 1
"""

# The criteria that touch one entity, each with the requirement above it and the
# behaviour below it. `label_expression` rather than `:Transition`: a classified
# transition carries `:ApiCall` or `:UiAction` INSTEAD of its parent, so a
# hardcoded parent label matches nothing and reports no error.
ENTITY_CRITERIA_CYPHER = f"""
MATCH (ac:AcceptanceCriterion)-[:REFERENCES]->(e:BusinessEntity)
WHERE e.id = $entity_id AND {currently_valid("ac")}
OPTIONAL MATCH (r:Requirement)-[:HAS_AC]->(ac)
WHERE {currently_valid("r")}
OPTIONAL MATCH (ac)-[:VALIDATES]->(t:{label_expression("Transition")})
RETURN ac.id AS id, ac.text AS text, ac.provenance AS provenance,
       ac.lifecycle_state AS lifecycle_state,
       r.id AS requirement_id,
       collect(DISTINCT t.id) AS transition_ids
ORDER BY ac.id
"""


def load_entities(session, area: str = "") -> list[dict]:
    """Every business entity, optionally within one area."""
    return [dict(row) for row in session.run(ENTITIES_CYPHER, area=area)]


def load_entity(session, name: str) -> dict | None:
    """One entity, by id or by name. `None` is an answer, not a failure."""
    row = session.run(ENTITY_CYPHER, name=name).single()
    return dict(row) if row is not None else None


def load_entity_criteria(session, entity_id: str) -> list[dict]:
    """The criteria referencing one entity, with requirement and transitions.

    `collect(DISTINCT t.id)` yields `[null]` rather than `[]` when a criterion
    validates nothing, so the nulls are stripped here -- a transition id of
    `None` would render as a citation to a transition that does not exist.
    """
    out = []
    for row in session.run(ENTITY_CRITERIA_CYPHER, entity_id=entity_id):
        item = dict(row)
        item["transition_ids"] = [t for t in (item.get("transition_ids") or []) if t]
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Documents and requirements — what the read-only surface serves (§9.5, F-12)
# ---------------------------------------------------------------------------

SPEC_DOCUMENT_CYPHER = f"""
MATCH (d:SpecDocument)-[:DESCRIBES]->(c:{label_expression("Component")})
WHERE c.journey = $journey AND c.b_surface = $surface
RETURN d.id AS id, d.name AS name, d.body_markdown AS body_markdown,
       d.content_hash AS content_hash, d.rendered_at AS rendered_at,
       d.lifecycle_state AS lifecycle_state,
       c.id AS component_id, c.version AS version, c.commit_sha AS commit_sha
ORDER BY d.rendered_at DESC
LIMIT 1
"""

ENTITY_DOCUMENT_CYPHER = """
MATCH (d:EntityDocument)-[:DESCRIBES]->(e:BusinessEntity)
WHERE e.id = $name OR e.name = $name
RETURN d.id AS id, d.name AS name, d.body_markdown AS body_markdown,
       d.content_hash AS content_hash, d.rendered_at AS rendered_at,
       d.lifecycle_state AS lifecycle_state, e.id AS entity_id
ORDER BY d.rendered_at DESC
LIMIT 1
"""

# Present tense by default. The criteria filter goes on the OPTIONAL MATCH, not
# in the outer WHERE: an outer clause would drop the whole requirement row when
# its only criterion is superseded, turning "this requirement has no current
# criteria" into "this requirement does not exist".
REQUIREMENT_CYPHER = """
MATCH (r:Requirement)
WHERE r.id = $requirement_id AND """ + currently_valid("r") + """
OPTIONAL MATCH (r)-[:HAS_AC]->(ac:AcceptanceCriterion)
WHERE """ + currently_valid("ac") + """
OPTIONAL MATCH (r)-[:BELONGS_TO]->(a:BusinessArea)
OPTIONAL MATCH (anchor)-[:REPRESENTS]->(r)
RETURN r.id AS id, r.text AS text, r.statement AS statement,
       r.ears_pattern AS ears_pattern, r.lifecycle_state AS lifecycle_state,
       a.name AS area,
       collect(DISTINCT {id: ac.id, text: ac.text, provenance: ac.provenance,
                         lifecycle_state: ac.lifecycle_state}) AS criteria,
       collect(DISTINCT {label: labels(anchor)[0], id: anchor.id}) AS anchors
LIMIT 1
"""

# One scan, three labels. A term matches a business noun, a requirement or a
# criterion, and which of the three it was is part of the answer -- collapsing
# them into one list would lose the only thing that tells a reader what to do
# next.
# Semantic neighbours. `db.index.vector.queryNodes` takes k up front, so the
# limit is the search rather than a filter after it — asking for 20 and then
# discarding 15 would have made the index do five times the work for the same
# answer.
#
# The model each vector was written with comes back so the caller can refuse a
# mismatch (`retrieval.require_matching_model`) instead of ranking nonsense.
VECTOR_SEARCH_CYPHER = """
CALL db.index.vector.queryNodes($index, $k, $vector) YIELD node AS n, score
WHERE """ + valid_where_it_applies("n") + """
RETURN labels(n)[0] AS label, n.id AS id,
       coalesce(n.name, '') AS name,
       coalesce(n.description, n.text, '') AS body,
       coalesce(n.lifecycle_state, '') AS lifecycle_state,
       n.embedding_model AS embedding_model,
       score
ORDER BY score DESC, label, id
"""

# Which models wrote the vectors currently in the graph. One value is healthy;
# several means an interrupted re-embedding, and none means semantic search has
# nothing to rank.
EMBEDDING_MODELS_CYPHER = """
MATCH (n)
WHERE n.embedding_model IS NOT NULL
RETURN DISTINCT n.embedding_model AS model
"""


def _searchable_labels() -> str:
    """`n:A OR n:B OR ...` from the ontology, never hand-written.

    The full-text index spans every searchable label, so a query naming a
    shorter list would silently discard hits the index went to the trouble of
    finding — and the shorter list is the one that rots when a label is added.
    """
    from metis_mcp.ontology.labels import SEARCH_TARGETS

    return " OR ".join(f"n:{label}" for label in sorted(SEARCH_TARGETS))


# Lucene, not `CONTAINS`. Substring matching cannot rank, cannot tokenise, and
# cannot tell a name match from a body match — so "lock" missed "locking" and
# every result came back in id order, which is no order at all.
#
# `BusinessEntity` and `Lesson` carry no validity window, so the clause is
# applied only to the labels that do — a bare `valid_to = ''` would otherwise
# drop every one of them.
SEARCH_CYPHER = """
CALL db.index.fulltext.queryNodes($index, $query) YIELD node AS n, score
WHERE (""" + _searchable_labels() + """)
  AND """ + valid_where_it_applies("n") + """
RETURN labels(n)[0] AS label, n.id AS id,
       coalesce(n.name, '') AS name,
       coalesce(n.description, n.text, '') AS body,
       coalesce(n.lifecycle_state, '') AS lifecycle_state,
       coalesce(n.provenance, '') AS provenance,
       score
ORDER BY score DESC, label, id
LIMIT $limit
"""


def load_spec_document(session, journey: str, surface: str = "api") -> dict | None:
    """The stored journey specification. `None` means none has been rendered."""
    row = session.run(SPEC_DOCUMENT_CYPHER, journey=journey, surface=surface).single()
    return dict(row) if row is not None else None


def load_entity_document(session, name: str) -> dict | None:
    """The stored entity specification, by entity id or name."""
    row = session.run(ENTITY_DOCUMENT_CYPHER, name=name).single()
    return dict(row) if row is not None else None


def load_requirement(session, requirement_id: str) -> dict | None:
    """One requirement, its criteria, its area, and the artefacts it came from.

    `collect(DISTINCT {...})` yields a single all-null map rather than an empty
    list when the OPTIONAL MATCH finds nothing, so those are stripped -- a
    criterion with no id would render as a citation to nothing.
    """
    row = session.run(REQUIREMENT_CYPHER, requirement_id=requirement_id).single()
    if row is None:
        return None
    item = dict(row)
    item["criteria"] = [c for c in (item.get("criteria") or []) if c.get("id")]
    item["anchors"] = [a for a in (item.get("anchors") or []) if a.get("id")]
    return item


# Lucene reserves these. A user typing `auth:` or `lock~` is asking a question,
# not writing a query language, and an unescaped one raises a parse error that
# reads like the database is broken.
_LUCENE_SPECIAL = r'+-&|!(){}[]^"~*?:\\/'


def lucene_escape(text: str) -> str:
    """User input as a literal term, not as Lucene syntax."""
    out = []
    for ch in text:
        if ch in _LUCENE_SPECIAL:
            out.append("\\")
        out.append(ch)
    return "".join(out)


class SearchIndexMissing(RuntimeError):
    """The full-text index has not been created in this database."""


RELATED_BY_TOPIC_CYPHER = """
MATCH (d {id: $id})-[:BELONGS_TO]->(t:Topic)<-[:BELONGS_TO]-(other)
WHERE other.id <> $id
RETURN DISTINCT other.id AS id, labels(other)[0] AS label,
       coalesce(other.name, '') AS name,
       collect(DISTINCT t.name) AS topics
ORDER BY id
"""

TOPICS_OF_CYPHER = """
MATCH (d {id: $id})-[:BELONGS_TO]->(t:Topic)
RETURN t.name AS name ORDER BY name
"""


def related_by_topic(session, document_id: str) -> dict:
    """What else covers the ground this document covers.

    **The reader half of `Topic`'s D-1 bar.** A lesson used to have no edge to
    anything but its own sections, so "what else should I read" could only be
    answered by searching again with different words and hoping. This is a
    traversal: one hop out to the shared node, one hop back.

    Returns the topics as well as the documents, because a reader who gets three
    lessons back should be able to see WHY those three — a list with no shared
    term in it reads as a recommendation, which is exactly what this is not.

    A document with no topics comes back empty rather than falling back to
    similarity. "Nothing declares the same subject" is a different answer from
    "here are some documents that look alike", and only the first is a fact.
    """
    topics = [row["name"] for row in
              session.run(TOPICS_OF_CYPHER, {"id": document_id})]
    if not topics:
        return {"ok": True, "id": document_id, "topics": [], "related": [],
                "note": "this document declares no topic, so nothing shares one "
                        "with it. Topics are authored in the document's own "
                        "frontmatter and never inferred"}
    related = [dict(row) for row in
               session.run(RELATED_BY_TOPIC_CYPHER, {"id": document_id})]
    return {"ok": True, "id": document_id, "topics": topics, "related": related}


PASSAGE_PARENT_CYPHER = """
UNWIND $ids AS pid
MATCH (parent)-[:CONTAINS]->(p:Passage {id: pid})
RETURN pid AS passage_id, parent.id AS id, labels(parent)[0] AS label,
       coalesce(parent.name, '') AS name,
       coalesce(parent.description, parent.text, '') AS body,
       coalesce(parent.lifecycle_state, '') AS lifecycle_state
"""


def roll_up_passages(session, rows: list[dict]) -> list[dict]:
    """Replace each `Passage` hit with the document that contains it.

    **A passage is searched and never shown.** It exists so that similarity is
    computed against one section rather than a whole document — which is worth
    six of thirty-six questions — but nobody asks to see one, and a result list
    mixing documents with fragments of documents would make the caller learn
    about a node that is an implementation detail of ranking.

    Rank is preserved and duplicates collapse to their best position: a lesson
    whose third section matched at rank 1 IS the rank-1 answer, and its other
    sections matching further down add nothing.

    A passage whose parent is missing is dropped rather than shown bare. That is
    a landing defect (`CONTAINS` is the only edge it has), and the honest place
    to see it is the count of what landed, not a search result.
    """
    passage_ids = [r["id"] for r in rows if r.get("label") == "Passage"]
    if not passage_ids:
        return rows

    parents = {row["passage_id"]: dict(row)
               for row in session.run(PASSAGE_PARENT_CYPHER, {"ids": passage_ids})}

    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if row.get("label") == "Passage":
            parent = parents.get(row["id"])
            if parent is None:
                continue
            row = {k: v for k, v in parent.items() if k != "passage_id"}
            # Carried through so a caller can still say WHY this ranked.
            row["matched_passage"] = parent["passage_id"]
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        out.append(row)
    return out


def search_knowledge(session, query: str, limit: int = 20) -> list[dict]:
    """Entities, requirements and criteria matching a term.

    Parameters go in a dict rather than as keywords: the driver's own signature
    is `Session.run(query, parameters=None, **kwargs)`, so a Cypher parameter
    named `query` collides with it and raises `TypeError: got multiple values
    for argument 'query'`. Every other loader here uses keywords safely because
    none of their parameters share a name with the driver's.
    """
    from metis_mcp.ontology.labels import SEARCH_INDEX

    try:
        rows = session.run(SEARCH_CYPHER, {"index": SEARCH_INDEX,
                                           "query": lucene_escape(query),
                                           # Over-fetch: passages collapse into
                                           # their parents, so N hits can be
                                           # fewer than N answers.
                                           "limit": limit * 3})
        return roll_up_passages(session, [dict(row) for row in rows])[:limit]
    except Exception as exc:                       # noqa: BLE001 - re-raised below
        # **Reported, never silently degraded.** Falling back to `CONTAINS` here
        # would leave search working badly with no signal, which is the failure
        # this codebase refuses: the caller would get worse answers and no reason
        # to suspect them. An absent index is a schema that has not been applied,
        # and that is fixable in one command.
        if "no such fulltext schema index" in str(exc).lower() or \
                "there is no such fulltext schema index" in str(exc).lower():
            raise SearchIndexMissing(
                f"the full-text index {SEARCH_INDEX!r} does not exist in this "
                f"database. Apply schema/metis2-01-constraints.cypher — it is "
                f"generated from the ontology and creates it.") from exc
        raise


# ---------------------------------------------------------------------------
# The intent spine — what feature derivation reads (§4.1)
# ---------------------------------------------------------------------------

def valid_at(alias: str, parameter: str = "$at") -> str:
    """The same read, as of an instant. `valid_from <= at < valid_to`.

    The half-open interval is deliberate: a fact invalidated at T was true up to
    T and not at T, so an as-at query at exactly T must not return it. Closing
    both ends would make a fact briefly true and superseded at once.
    """
    return (f"({alias}.valid_from <= {parameter}) "
            f"AND ({alias}.valid_to = '' OR {alias}.valid_to > {parameter})")


# The same read, as of an instant. Derived from the query above by substituting
# the clause rather than by copying the body, so a change to what a requirement
# returns cannot apply to only one of them.
REQUIREMENT_AS_AT_CYPHER = (
    REQUIREMENT_CYPHER
    .replace(currently_valid("r"), valid_at("r"))
    .replace(currently_valid("ac"), valid_at("ac")))


SPECIFICATIONS_CYPHER = """
MATCH (s:Specification)
WHERE """ + currently_valid("s") + """
OPTIONAL MATCH (i:Intent)-[:SPECIFIED_BY]->(s)
WHERE """ + currently_valid("i") + """
RETURN s.id AS id, s.statement AS statement, s.provenance AS provenance,
       s.entities AS entities, s.contracts_json AS contracts_json,
       s.lifecycle_state AS lifecycle_state,
       i.id AS intent_id
ORDER BY s.id
"""

# Which component implements a specification, through the code side's own verb.
# `label_expression` because a Component is written as `:RestServer` or
# `:WebServer` when its surface is known -- a hardcoded `:Component` matches
# only the unclassified ones.
SPEC_IMPLEMENTATIONS_CYPHER = f"""
MATCH (c:{label_expression("Component")})-[:EXPOSES|HAS_PAGE]->(x)
MATCH (x)-[:IMPLEMENTS]->(s:Specification)
WHERE {currently_valid("s")}
RETURN s.id AS specification_id, c.component AS component
ORDER BY specification_id
"""

KNOWN_ENTITY_KEYS_CYPHER = """
MATCH (e:BusinessEntity) RETURN e.id AS id ORDER BY id
"""


def load_specifications(session) -> list[dict]:
    """Every specification, with the intent above it."""
    out = []
    for row in session.run(SPECIFICATIONS_CYPHER):
        item = dict(row)
        item["entities"] = list(item.get("entities") or [])
        out.append(item)
    return out


def load_spec_implementations(session) -> dict[str, str]:
    """`{specification_id: component}` — the code side of §4.1's comparison."""
    return {r["specification_id"]: r["component"]
            for r in session.run(SPEC_IMPLEMENTATIONS_CYPHER) if r["component"]}


def load_known_entity_keys(session) -> set[str]:
    """The glossary's own keys. A noun nobody defined must not become a feature."""
    return {r["id"] for r in session.run(KNOWN_ENTITY_KEYS_CYPHER)}


# ---------------------------------------------------------------------------
# Feature → Scenario: the last hop of the intent spine
# ---------------------------------------------------------------------------

# **The intent path.** A criterion of this feature's specification explicitly
# VALIDATES the transition the scenario asserts. That is somebody saying "this
# behaviour is what the capability means", so it is the stronger evidence.
FEATURE_SCENARIOS_BY_CRITERION_CYPHER = f"""
MATCH (f:Feature)<-[:REALISED_BY]-(s:Specification)-[:HAS_AC]->(ac:AcceptanceCriterion)
WHERE {currently_valid("s")} AND {currently_valid("ac")}
MATCH (ac)-[:VALIDATES]->(t:{label_expression("Transition")})
MATCH (sc:Scenario)-[c:COVERS {{is_validated: true}}]->(t)
RETURN DISTINCT f.id AS feature_id, sc.id AS scenario_id
ORDER BY feature_id, scenario_id
"""

# **The declared path.** The transition merely derives from an entry point that
# implements the specification -- true, and weaker: it says the code and the
# contract line up, not that anybody agreed this is what the capability means.
FEATURE_SCENARIOS_BY_IMPLEMENTATION_CYPHER = f"""
MATCH (f:Feature)<-[:REALISED_BY]-(s:Specification)<-[:IMPLEMENTS]-(x)
WHERE {currently_valid("s")}
MATCH (t:{label_expression("Transition")})-[:DERIVED_FROM]->(x)
MATCH (sc:Scenario)-[c:COVERS {{is_validated: true}}]->(t)
RETURN DISTINCT f.id AS feature_id, sc.id AS scenario_id
ORDER BY feature_id, scenario_id
"""

FEATURES_CYPHER = """
MATCH (f:Feature) RETURN f.id AS id, f.name AS name ORDER BY f.name
"""


def load_features(session) -> list[dict]:
    return [dict(r) for r in session.run(FEATURES_CYPHER)]


def load_feature_scenarios(session) -> tuple[dict, dict]:
    """`({feature: [scenario]}, {feature: [scenario]})` — intent path, then
    declared path. Kept apart because they are different strengths of evidence
    and merging them would lose the only thing that distinguishes them."""
    by_criterion: dict[str, list[str]] = {}
    by_implementation: dict[str, list[str]] = {}
    for row in session.run(FEATURE_SCENARIOS_BY_CRITERION_CYPHER):
        by_criterion.setdefault(row["feature_id"], []).append(row["scenario_id"])
    for row in session.run(FEATURE_SCENARIOS_BY_IMPLEMENTATION_CYPHER):
        by_implementation.setdefault(row["feature_id"], []).append(row["scenario_id"])
    return by_criterion, by_implementation


def embedding_models(session) -> set[str]:
    """Which models wrote the vectors in this graph."""
    return {row["model"] for row in session.run(EMBEDDING_MODELS_CYPHER)
            if row["model"]}


def hybrid_search(session, query: str, provider=None, limit: int = 20):
    """Keyword and semantic, fused by rank.

    `provider` absent means keyword only — which is the default deployment, and
    is a complete answer rather than a degraded one. Semantic search is added
    when somebody supplies a model, and refused rather than approximated when the
    model does not match what wrote the corpus.
    """
    from metis_mcp import retrieval
    from metis_mcp.ontology.labels import SEARCH_TARGETS, vector_index_for

    keyword = search_knowledge(session, query, limit=limit)
    if provider is None:
        return retrieval.fuse(keyword, [], limit=limit)

    retrieval.require_matching_model(provider, embedding_models(session))
    vector = list(provider.embed(query))

    # One index per label (Neo4j rejects the multi-label form for vector
    # indexes), so each is queried and the rankings are merged. Sorted by score
    # before fusing: RRF reads position, and concatenating three per-label lists
    # without re-ordering would let label order stand in for relevance.
    semantic = []
    for label in sorted(SEARCH_TARGETS):
        rows = session.run(VECTOR_SEARCH_CYPHER, {
            "index": vector_index_for(label), "k": limit, "vector": vector})
        semantic.extend(dict(r) for r in rows)
    semantic.sort(key=lambda r: (-r["score"], r["label"], r["id"]))
    # Rolled up AFTER sorting by score, so a document is ranked by its BEST
    # section rather than by whichever section the index happened to return
    # first — which is the whole reason passages carry vectors at all.
    semantic = roll_up_passages(session, semantic)

    return retrieval.fuse(keyword, semantic, limit=limit)
