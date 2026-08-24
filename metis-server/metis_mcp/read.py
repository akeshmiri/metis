"""
Queries the read surface did not have.

`server.py` already answers "what is in this model" and "what does this
requirement say". What it could not answer is **"why does this transition claim
what it claims"** — the guard's own source line, the parameters it sends, the
endpoint and declared outcome it was recovered from. That is the evidence layer,
and it exists in the graph precisely so a Transition can say what it was
`DERIVED_FROM` instead of pointing at a JSON file under /tmp.

An agent asked to review a transition without it is reading a claim and calling
it evidence.
"""
from __future__ import annotations

from metis_mcp.ontology.labels import label_expression

# One query, because the evidence is only useful assembled: a guard with no
# anchor, or an outcome with no `link`, is a different fact from the same guard
# with them, and a reviewer weighs them differently.
TRANSITION_CYPHER = f"""
MATCH (t:{label_expression("Transition")} {{id: $id}})
OPTIONAL MATCH (src:State)-[:WHEN]->(t)
OPTIONAL MATCH (t)-[:THEN]->(tgt:State)
OPTIONAL MATCH (t)-[:DERIVED_FROM]->(e:Endpoint)
OPTIONAL MATCH (t)-[:DERIVED_FROM]->(o:DeclaredOutcome)
OPTIONAL MATCH (t)-[:EXERCISES]->(p:Parameter)
OPTIONAL MATCH (t)-[:REQUIRES]->(pt:Class|Enum)
OPTIONAL MATCH (t)-[:CONSTRAINED_BY]->(c:Check)
// `GUARDED_BY` is the STRONGER claim and was not read at all: `CONSTRAINED_BY`
// says a condition was found near this transition, `GUARDED_BY` says this
// condition selected this outcome over its siblings. Kept apart rather than
// merged, because a reviewer approves the two differently.
OPTIONAL MATCH (o)-[:GUARDED_BY]->(g:Check)
OPTIONAL MATCH (ac:AcceptanceCriterion)-[:VALIDATES]->(t)
RETURN t AS transition,
       labels(t) AS labels,
       src.name AS source_state,
       tgt.name AS target_state,
       collect(DISTINCT {{method: e.http_method, path: e.path}}) AS endpoints,
       collect(DISTINCT {{signature: o.signature, status: o.status,
                          link: o.link}}) AS outcomes,
       collect(DISTINCT {{name: p.name, location: p.location,
                          required: p.required}}) AS parameters,
       collect(DISTINCT {{type: pt.name, fields: pt.fields,
                          properties: properties(pt)}}) AS payload_types,
       collect(DISTINCT {{expression: c.expression,
                          dimension: c.dimension_class}}) AS checks,
       collect(DISTINCT {{expression: g.expression, order: g.order,
                          dimension: g.dimension_class,
                          anchor: g.anchor}}) AS guarding_checks,
       collect(DISTINCT {{id: ac.id, text: ac.text,
                          provenance: ac.provenance}}) AS criteria
"""


def _expand_fields(payload_type: dict) -> dict:
    """The flat `f_<name>_*` properties as the nested document they encode.

    Shared with the encoder in `ontology.facts` so the two cannot disagree about
    the shape — which is the failure mode this codebase keeps finding.
    """
    from metis_mcp.ontology.facts import expand_fields

    props = payload_type.get("properties") or {}
    expanded = expand_fields({**props, "fields": payload_type.get("fields") or []})
    return {"type": payload_type.get("type"), "fields": expanded.get("fields", {})}


def _clean(rows) -> list:
    """Drop the all-null rows `collect` over an OPTIONAL MATCH produces."""
    return [r for r in rows if any(v is not None for v in r.values())]


def get_transition(transition_id: str) -> dict:
    """One transition in full, with the evidence it was recovered from.

    Takes the **namespaced** id — `{model}::{element}`. A bare id matches no
    node, which is the single most common way a query here returns nothing and
    reports success.

    `criteria` carries each validating criterion's provenance grade. A
    `code_derived` criterion was written from the code it is checking, so its
    agreeing with the code is evidence of coverage and never of correctness
    (§4.1) — which is the distinction that decides whether this transition has
    actually been specified by anyone.
    """
    from metis_mcp.mbt.graph_session import session

    with session() as s:
        row = s.run(TRANSITION_CYPHER, id=transition_id).single()

    if row is None:
        return {
            "ok": False,
            "reason": (f"no transition {transition_id!r}. Ids are namespaced "
                       f"`<model>::<element>` — a bare id matches nothing."),
        }

    node = dict(row["transition"])
    return {
        "ok": True,
        "id": node.get("id"),
        # The specialisation, not the parent: a classified transition carries
        # `:ApiCall` or `:UiAction` INSTEAD of `:Transition`, and a bare
        # `:Transition` means nobody has established its surface.
        "labels": sorted(row["labels"]),
        "trigger": node.get("trigger"),
        "guard": node.get("guard_expression"),
        # `file:line@commit` for the guard's own source. A guard nobody can
        # trace to a line is a claim taken on trust (§8.5).
        "guard_anchor": node.get("guard_anchor"),
        "guard_tier": node.get("guard_tier"),
        "source_state": row["source_state"],
        "target_state": row["target_state"],
        "source_state_unresolved": node.get("source_state_unresolved"),
        "outcome_status": node.get("outcome_status"),
        # constructed = the outcome was seen being BUILT; declared = it was only
        # asserted on an annotation. A reviewer approves them differently.
        "outcome_source": node.get("outcome_source"),
        "lifecycle_state": node.get("lifecycle_state"),
        "extraction_method": node.get("extraction_method"),
        "implementation_status": node.get("implementation_status"),
        "evidence": {
            "endpoints": _clean(row["endpoints"]),
            "declared_outcomes": _clean(row["outcomes"]),
            "parameters": _clean(row["parameters"]),
            # X-6d: a field is a property of its type, not a node, so what comes
            # back is the type with its fields expanded rather than a flat list.
            "payload_types": [_expand_fields(t) for t in _clean(row["payload_types"])],
            "checks": _clean(row["checks"]),
            # Ordered, because the order is the fact: checks short-circuit, so
            # a fixture aimed at the third condition never reaches it unless
            # the first two already hold.
            "guarding_checks": sorted(
                _clean(row["guarding_checks"]),
                key=lambda c: (c.get("order") or 0, c.get("expression") or "")),
        },
        "criteria": _clean(row["criteria"]),
        "means": ("a code_derived criterion agreeing with this transition is "
                  "evidence of coverage, never of correctness (§4.1)"),
    }
