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

from dataclasses import dataclass

from metis_mcp.mbt.model import IMPLEMENTED, QUARANTINE, Model, State, Transition

# One model is one <journey>-<surface> machine (spec M-1). `functional_areas`
# carries the journey (M-4) and `surface` the other half of the identity.
STATES_CYPHER = """
MATCH (s:State)
WHERE $journey IN s.functional_areas AND s.surface = $surface
RETURN s.id             AS id,
       s.name           AS name,
       s.surface        AS surface,
       s.is_initial     AS is_initial,
       s.lifecycle_state AS lifecycle_state
ORDER BY s.id
"""

TRANSITIONS_CYPHER = """
MATCH (src:State)-[:WHEN]->(t:Transition)-[:THEN]->(tgt:State)
WHERE $journey IN t.functional_areas AND t.surface = $surface
RETURN t.id                    AS id,
       src.id                  AS source,
       t.trigger               AS trigger,
       tgt.id                  AS target,
       t.guard_expression      AS guard,
       t.implementation_status AS implementation_status,
       t.lifecycle_state       AS lifecycle_state
ORDER BY t.id
"""

# Cross-surface invocation (spec M-5a). Loaded separately because it spans two
# models and therefore cannot belong to either one's node set.
INVOKES_CYPHER = """
MATCH (ui:Transition)-[:INVOKES]->(api:Transition)
WHERE $journey IN ui.functional_areas
RETURN ui.id AS ui_transition, api.id AS api_transition
ORDER BY ui.id
"""


# The guard a UI transition INHERITS from the API transition it invokes (M-5c).
# One hop, because the guard lives on the far side of the edge: a UI model loaded
# on its own contains the transitions but not the conditions that determine them.
INHERITED_GUARDS_CYPHER = """
MATCH (ui:Transition)-[:INVOKES]->(api:Transition)
WHERE $journey IN ui.functional_areas
  AND api.guard_expression IS NOT NULL AND api.guard_expression <> ''
RETURN ui.id AS ui_transition, api.guard_expression AS guard
ORDER BY ui.id
"""


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
