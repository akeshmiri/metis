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
    Transition,
)
from metis_mcp.ontology.labels import label_expression

# One model is one <journey>-<surface> machine (spec M-1). `functional_areas`
# carries the journey (M-4) and `surface` the other half of the identity.
STATES_CYPHER = """
MATCH (s:State)
WHERE $journey IN s.functional_areas AND s.surface = $surface
RETURN s.id             AS id,
       s.name           AS name,
       s.surface        AS surface,
       s.is_initial     AS is_initial,
       s.lifecycle_state AS lifecycle_state,
       s.name_tier      AS name_tier,
       // Written by landing since the Web surface was added, and never read
       // back. `condition` is what a state MEANS ("no metric exists") where its
       // name says only what it is called, so a spec rendered from a
       // graph-loaded model fell back to the code convention for every Given.
       s.condition      AS condition,
       s.page           AS page
ORDER BY s.id
"""

TRANSITIONS_CYPHER = """
MATCH (src:State)-[:WHEN]->(t:Transition|ApiCall|UiAction)-[:THEN]->(tgt:State)
WHERE $journey IN t.functional_areas AND t.surface = $surface
RETURN t.id                    AS id,
       src.id                  AS source,
       t.trigger               AS trigger,
       tgt.id                  AS target,
       t.guard_expression      AS guard,
       t.implementation_status AS implementation_status,
       t.lifecycle_state       AS lifecycle_state,
       t.outcome_status        AS outcome_status,
       t.guard_anchor          AS guard_anchor,
       t.source_state_unresolved AS source_state_unresolved,
       t.inputs_json           AS inputs_json,
       t.security_json         AS security_json,
       t.outcome_source        AS outcome_source,
       t.guard_claim           AS guard_claim,
       t.data_requirements     AS data_requirements,
       t.response_body         AS response_body,
       t.media_types           AS media_types,
       t.name_tier             AS name_tier,
       t.guard_wording         AS guard_wording,
       t.guard_tier            AS guard_tier
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
  AND api.guard_expression IS NOT NULL AND api.guard_expression <> ''
RETURN ui.id AS ui_transition, api.guard_expression AS guard
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
WHERE c.journey = $journey AND c.surface = $surface
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
WHERE $journey IN t.functional_areas AND t.surface = $surface
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


def rows_to_model(model_id: str, state_rows: list[dict], transition_rows: list[dict],
                  invokes_rows: list[dict] | None = None) -> LoadReport:
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
    return rows_to_model(f"{journey}-{surface}", state_rows, transition_rows, invokes_rows)


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
WHERE e.id = $entity_id
OPTIONAL MATCH (r:Requirement)-[:HAS_AC]->(ac)
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
WHERE c.journey = $journey AND c.surface = $surface
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

REQUIREMENT_CYPHER = """
MATCH (r:Requirement)
WHERE r.id = $requirement_id
OPTIONAL MATCH (r)-[:HAS_AC]->(ac:AcceptanceCriterion)
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
SEARCH_CYPHER = """
MATCH (n)
WHERE (n:BusinessEntity OR n:Requirement OR n:AcceptanceCriterion)
  AND (toLower(coalesce(n.name, '')) CONTAINS toLower($query)
       OR toLower(coalesce(n.text, '')) CONTAINS toLower($query)
       OR toLower(coalesce(n.description, '')) CONTAINS toLower($query))
RETURN labels(n)[0] AS label, n.id AS id,
       coalesce(n.name, '') AS name,
       coalesce(n.description, n.text, '') AS body,
       coalesce(n.lifecycle_state, '') AS lifecycle_state,
       coalesce(n.provenance, '') AS provenance
ORDER BY label, id
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


def search_knowledge(session, query: str, limit: int = 20) -> list[dict]:
    """Entities, requirements and criteria matching a term.

    Parameters go in a dict rather than as keywords: the driver's own signature
    is `Session.run(query, parameters=None, **kwargs)`, so a Cypher parameter
    named `query` collides with it and raises `TypeError: got multiple values
    for argument 'query'`. Every other loader here uses keywords safely because
    none of their parameters share a name with the driver's.
    """
    rows = session.run(SEARCH_CYPHER, {"query": query, "limit": limit})
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# The intent spine — what feature derivation reads (§4.1)
# ---------------------------------------------------------------------------

SPECIFICATIONS_CYPHER = """
MATCH (s:Specification)
OPTIONAL MATCH (i:Intent)-[:SPECIFIED_BY]->(s)
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
