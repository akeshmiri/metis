"""
Team/RBAC scoping (BS-005's "re-check-team-scope-at-every-hop" principle,
REQ-METIS-CPT-03's "cross-team pinned-block access is denied even with a
known node id"). This is the Community-edition-compatible path PLAN.md
Phase 6 names as the fallback to Neo4j Enterprise's native property-based
RBAC (`schema/metis-graph-03-single-db-consolidation.cypher`'s
`GRANT ... WHERE n.owner_team = ...` pattern, left commented-out /
illustrative there since its exact syntax needs verifying against the
deployed Enterprise version) -- an explicit equivalent check against
owner_team properties, enforced in application code rather than assumed
enforced by a database feature that was never actually exercised.

Every scoped read goes through here, not just the entry point -- "even
with a known node id" means an attacker (or a buggy caller) who already
has a real node's id cannot bypass scoping by querying it directly.
"""
from dataclasses import dataclass

from metis_mcp.oauth2 import TokenValidationResult


@dataclass
class ScopedAccessResult:
    allowed: bool
    node: dict | None
    reason: str


def get_scoped_node(session, token: TokenValidationResult, node_id: str) -> ScopedAccessResult:
    if not token.valid:
        return ScopedAccessResult(allowed=False, node=None, reason=token.reason)

    rec = session.run(
        "MATCH (n {id: $id}) WHERE n.owner_team IS NOT NULL "
        "RETURN n.id AS id, n.owner_team AS owner_team, labels(n) AS labels, properties(n) AS props",
        id=node_id,
    ).single()
    if rec is None:
        return ScopedAccessResult(allowed=False, node=None, reason="Node not found or not owner_team-scoped.")

    if rec["owner_team"] != token.owner_team:
        # Deliberately does NOT say "node not found" -- REQ-METIS-CPT-03 is
        # about denying cross-team access, not obscuring node existence;
        # conflating the two would make the actual guardrail behavior
        # untestable/unverifiable from outside.
        return ScopedAccessResult(
            allowed=False, node=None,
            reason=f"Node belongs to team '{rec['owner_team']}', token is scoped to team "
                   f"'{token.owner_team}' -- access denied (REQ-METIS-CPT-03).",
        )

    return ScopedAccessResult(allowed=True, node=rec["props"], reason="Same-team access granted.")
