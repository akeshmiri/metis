"""
Graph store for the Métis dogfooding pilot.

This is the LOCAL, dogfooding-corpus-backed store -- not Neo4j. It exists so
the MCP server can be tested against real content (this platform's own
REQ-METIS-*/CONST-*/DQ-*/AF-*/BS-* items, parsed by corpus.py) before Neo4j
Enterprise is actually deployed via the Helm chart. The interface is written
so a Neo4jGraphStore implementing the same methods (get_node, neighbors,
traceability_chain, impact_analysis) could be swapped in later without
changing the tool layer above it -- see the NOTE at the bottom of this file.
"""
from metis_mcp.corpus import parse_corpus


class LocalGraphStore:
    def __init__(self, glob_pattern: str):
        all_nodes = parse_corpus(glob_pattern)
        self.conflicts = all_nodes.pop('__conflicts__')
        self.nodes = all_nodes

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    def get_node(self, node_id: str):
        return self.nodes.get(node_id)

    def neighbors(self, node_id: str) -> dict:
        """Immediate references (outgoing) and referenced_by (incoming) only."""
        node = self.nodes.get(node_id)
        if not node:
            return None
        return {
            "id": node.id,
            "references": list(node.references),
            "referenced_by": list(node.referenced_by),
        }

    def traceability_chain(self, node_id: str, max_hops: int = 3) -> dict | None:
        """
        Full upstream (references) and downstream (referenced_by) chains, up
        to max_hops -- this is real BFS traversal over the actual parsed
        corpus, not simulated depth.
        """
        node = self.nodes.get(node_id)
        if not node:
            return None

        def bfs(start: str, direction: str):
            visited = {start}
            frontier = [start]
            chain = []
            for hop in range(max_hops):
                next_frontier = []
                for current in frontier:
                    cur_node = self.nodes.get(current)
                    if not cur_node:
                        continue
                    edges = cur_node.references if direction == "up" else cur_node.referenced_by
                    for e in edges:
                        if e not in visited:
                            visited.add(e)
                            next_frontier.append(e)
                            chain.append({"id": e, "hop": hop + 1})
                frontier = next_frontier
                if not frontier:
                    break
            return chain

        return {
            "id": node_id,
            "upstream": bfs(node_id, "up"),      # what this node's own text cites
            "downstream": bfs(node_id, "down"),  # what cites this node
        }

    def impact_analysis(self, node_id: str, max_hops: int = 3) -> dict | None:
        """
        What would be affected if node_id changed -- the downstream
        (referenced_by) chain, since those are the items whose own text
        depends on / cites this one.
        """
        chain = self.traceability_chain(node_id, max_hops)
        if chain is None:
            return None
        return {"id": node_id, "affects": chain["downstream"]}

    def orphan_rate(self, kind: str | None = None) -> dict:
        """
        Real, computed metric: what fraction of nodes (optionally filtered by
        kind) have NEITHER an outgoing reference NOR an incoming
        referenced_by -- i.e. are isolated in the corpus. This is a genuine
        proxy for DQ-019 (orphan-code rate)'s spirit, computed against this
        platform's own self-referential documents, not simulated.
        """
        pool = [n for n in self.nodes.values() if (kind is None or n.kind == kind)]
        if not pool:
            return {"kind": kind, "total": 0, "orphans": 0, "orphan_rate": None}
        orphans = [n for n in pool if not n.references and not n.referenced_by]
        return {
            "kind": kind or "all",
            "total": len(pool),
            "orphans": len(orphans),
            "orphan_rate": round(len(orphans) / len(pool), 3),
            "orphan_ids": [n.id for n in orphans],
        }

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Plain substring search over node text -- a real, deterministic stand-in
        for what the production system's hybrid retrieval (§8.2) will do.
        Explicitly NOT semantic search; this is corroboration-through-actual-
        text-match, not a vector similarity guess.
        """
        q = query.lower()
        hits = []
        for n in self.nodes.values():
            if q in n.text.lower() or q in n.id.lower():
                hits.append(n)
        return [
            {"id": n.id, "kind": n.kind, "source_file": n.source_file, "snippet": n.text[:200]}
            for n in hits[:limit]
        ]


# NOTE on the production path (Neo4j):
# A Neo4jGraphStore with the identical method signatures (get_node, neighbors,
# traceability_chain, impact_analysis, orphan_rate, search) would run the same
# operations as real Cypher queries against the schema in
# metis-graph-01/02/03-*.cypher, instead of BFS over an in-memory dict. The
# MCP tool layer (server.py) is written against this interface, not against
# LocalGraphStore's internals, specifically so that swap is the only change
# needed to go from dogfooding-on-Claude to the real production deployment.
