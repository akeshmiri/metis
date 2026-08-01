"""
§8.1 Pinned core memory blocks (REQ-METIS-MEM-01): "active_constraints
(Risk=High, Approved), open_incidents (status=Open, <=2 hops), and
pinned_business_rules (explicitly human-pinned) are injected
unconditionally into agent context, bypassing retrieval ranking.
Size-capped at 2,000 tokens default; overflow triggers a visible warning
... never silent truncation."

"Bypassing retrieval ranking" is the key design constraint reflected here:
unlike metis_mcp/hybrid_retrieval.py's merge-and-rerank, these three
blocks are never scored, filtered, or reordered by relevance -- they're
either in scope (by the literal criteria the spec states) or not.

No real tokenizer is bundled in this environment (no tiktoken/model
tokenizer dependency) -- token count is approximated as
`len(text) / 4` (a commonly-used, disclosed rough English-text ratio,
not a precise count). REQ-METIS-MEM-01 cares about detecting overflow and
warning visibly, not billing-accurate token counts -- an approximation
that's honest about being one satisfies that; a fabricated precise count
would not.
"""
from dataclasses import dataclass, field

_CHARS_PER_TOKEN_ESTIMATE = 4  # disclosed approximation, see module docstring
DEFAULT_TOKEN_CAP = 2000

_SCOPE_HOP_RELS = "CITES|HAS_AC|IMPLEMENTS|VERIFIES|TRACES_TO|HAS_METHOD|COVERS"


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)


def get_active_constraints(session, scope_id: str | None = None) -> list[dict]:
    """Risk=High, Approved Constraint entities. Scoped to within 2 hops of
    `scope_id` (a Service/Repository) if given, else graph-wide.

    Excludes :DogfoodingItem explicitly -- schema-01's id-uniqueness
    constraints are per-label, not global, and :DogfoodingItem is verified
    to share real ids with the production ontology (same root cause found
    for real in metis_mcp/temporal.py)."""
    if scope_id:
        rows = session.run(
            f"""
            MATCH (scope {{id: $scope_id}}) WHERE NOT scope:DogfoodingItem
            MATCH (scope)-[:{_SCOPE_HOP_RELS}*0..2]-(c:Constraint)
            WHERE c.risk_tag = 'High' AND c.lifecycle_state = 'Approved'
            RETURN DISTINCT c.id AS id, c.text AS text
            """,
            scope_id=scope_id,
        ).data()
    else:
        rows = session.run(
            "MATCH (c:Constraint) WHERE c.risk_tag = 'High' AND c.lifecycle_state = 'Approved' "
            "RETURN c.id AS id, c.text AS text"
        ).data()
    return [{"id": r["id"], "text": r["text"] or ""} for r in rows]


def get_open_incidents(session, scope_id: str | None = None, max_hops: int = 2) -> list[dict]:
    """status=Open Incident entities within `max_hops` of scope_id. Same
    :DogfoodingItem exclusion as get_active_constraints above, same
    real reason."""
    if scope_id:
        rows = session.run(
            f"""
            MATCH (scope {{id: $scope_id}}) WHERE NOT scope:DogfoodingItem
            MATCH (scope)-[:{_SCOPE_HOP_RELS}*0..{max_hops}]-(i:Incident)
            WHERE i.status = 'Open'
            RETURN DISTINCT i.id AS id, i.text AS text, i.status AS status
            """,
            scope_id=scope_id,
        ).data()
    else:
        rows = session.run(
            "MATCH (i:Incident) WHERE i.status = 'Open' RETURN i.id AS id, i.text AS text, i.status AS status"
        ).data()
    return [{"id": r["id"], "text": r["text"] or "", "status": r["status"]} for r in rows]


def get_pinned_business_rules(session) -> list[dict]:
    """Explicitly human-pinned -- `pinned = true`, a real property set only
    by a deliberate human action (never inferred/defaulted true anywhere
    in this codebase's write paths)."""
    rows = session.run(
        "MATCH (b:BusinessRule) WHERE b.pinned = true RETURN b.id AS id, b.text AS text"
    ).data()
    return [{"id": r["id"], "text": r["text"] or ""} for r in rows]


def pin_business_rule(session, business_rule_id: str, pinned_by: str) -> None:
    """The one real, explicit human action that can add a BusinessRule to
    this block -- deliberately separate from any confidence-tiering or
    ingestion write path, since pinning is a curation decision, not an
    extraction outcome."""
    def _write(tx):
        tx.run(
            "MATCH (b:BusinessRule {id: $id}) SET b.pinned = true, b.pinned_by = $pinned_by, "
            "b.pinned_at = datetime()",
            id=business_rule_id, pinned_by=pinned_by,
        )
    session.execute_write(_write)


@dataclass
class PinnedContext:
    active_constraints: list = field(default_factory=list)
    open_incidents: list = field(default_factory=list)
    pinned_business_rules: list = field(default_factory=list)
    estimated_tokens: int = 0
    token_cap: int = DEFAULT_TOKEN_CAP
    overflow: bool = False
    overflow_warning: str | None = None


def assemble_pinned_context(session, scope_id: str | None = None,
                             token_cap: int = DEFAULT_TOKEN_CAP) -> PinnedContext:
    """Assembles all 3 blocks, unconditionally (no ranking/filtering by
    relevance -- that's the whole point of a pinned block). If the
    combined estimated size exceeds `token_cap`, this does NOT silently
    drop items -- it returns everything plus a visible, specific overflow
    warning, per REQ-METIS-MEM-01's explicit 'never silent truncation'
    requirement. The caller (e.g. a future metis_get_context integration)
    decides what to do with an overflowing block; this function's job is
    to make the overflow impossible to miss, not to resolve it silently
    on its own authority."""
    constraints = get_active_constraints(session, scope_id)
    incidents = get_open_incidents(session, scope_id)
    rules = get_pinned_business_rules(session)

    all_text = "".join(c["text"] for c in constraints) + "".join(i["text"] for i in incidents) \
        + "".join(r["text"] for r in rules)
    estimated_tokens = _estimate_tokens(all_text)
    overflow = estimated_tokens > token_cap

    return PinnedContext(
        active_constraints=constraints, open_incidents=incidents, pinned_business_rules=rules,
        estimated_tokens=estimated_tokens, token_cap=token_cap, overflow=overflow,
        overflow_warning=(
            f"Pinned context is ~{estimated_tokens} tokens, over the {token_cap}-token cap by "
            f"~{estimated_tokens - token_cap} -- all {len(constraints)} constraint(s), "
            f"{len(incidents)} incident(s), and {len(rules)} pinned rule(s) are still included "
            f"below; nothing was silently dropped. Surface this to the service owner "
            f"(REQ-METIS-MEM-01)."
        ) if overflow else None,
    )
