"""
Neo4jGraphStore -- the real production graph backend, implementing the exact
same method signatures as LocalGraphStore (graph_store.py's NOTE at the
bottom): get_node, neighbors, traceability_chain, impact_analysis,
orphan_rate, search. The MCP tool layer (server.py) is written against this
interface, not against either store's internals, so this is a drop-in swap.

Runs real Cypher against the schema in schema/metis-graph-01/02/03-*.cypher
-- see docstring on load_dogfooding_corpus.py for why the dogfooding corpus
specifically is loaded under a `DogfoodingItem` label rather than the
production ontology's `Requirement` label: the schema's Requirement label
carries real existence constraints (source_episode_id, ears_pattern) that
this platform's own self-referential governance docs don't genuinely
satisfy -- they're not EARS-tagged requirements ingested from a real
connector, they're Métis's own Constitution/DQ/foolproof/security-boundary
corpus. Forcing them into :Requirement would either violate those
constraints or fabricate values for them, both worse than using a distinct
label honestly.
"""
import json
from dataclasses import dataclass, field

from neo4j import GraphDatabase


@dataclass
class GraphNodeView:
    """Same shape as corpus.py's GraphNode -- server.py's tool functions read
    node.id/kind/text/source_file/source_heading/references/referenced_by by
    attribute, regardless of which store produced it."""
    id: str
    kind: str
    text: str
    source_file: str
    source_heading: str
    references: list = field(default_factory=list)
    referenced_by: list = field(default_factory=list)


class Neo4jGraphStore:
    LABEL = "DogfoodingItem"
    REL = "CITES"

    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database
        self._driver.verify_connectivity()

    def close(self):
        self._driver.close()

    def _session(self):
        return self._driver.session(database=self._database)

    def session(self):
        """Public accessor for callers (e.g. server.py's metis_propose_test_skeleton)
        that need to run real Cypher not covered by this class's own fixed
        interface -- e.g. metis_mcp/test_skeleton_generator.py's Stage 3/4
        pipeline, which operates on Transition/TestCase/Method, not the
        DogfoodingItem shape this class's other methods are scoped to."""
        return self._session()

    @property
    def node_count(self) -> int:
        with self._session() as s:
            rec = s.run(f"MATCH (n:{self.LABEL}) RETURN count(n) AS c").single()
            return rec["c"] if rec else 0

    @property
    def conflicts(self) -> dict:
        """Duplicate-definition conflicts found by corpus.py's parser at load
        time, persisted on the bootstrap Episode node's own property (real
        data carried over from the actual parse, not recomputed/guessed)."""
        with self._session() as s:
            rec = s.run(
                "MATCH (e:Episode {source_connector: 'dogfooding-corpus-loader'}) "
                "RETURN e.duplicate_definition_conflicts AS c ORDER BY e.t_recorded DESC LIMIT 1"
            ).single()
            if not rec or not rec["c"]:
                return {}
            return json.loads(rec["c"])

    def get_node(self, node_id: str) -> GraphNodeView | None:
        with self._session() as s:
            rec = s.run(
                f"""
                MATCH (n:{self.LABEL} {{id: $id}})
                CALL (n) {{
                    OPTIONAL MATCH (n)-[:{self.REL}]->(ref)
                    RETURN collect(DISTINCT ref.id) AS refs
                }}
                CALL (n) {{
                    OPTIONAL MATCH (n)<-[:{self.REL}]-(refby)
                    RETURN collect(DISTINCT refby.id) AS refbys
                }}
                RETURN n.id AS id, n.kind AS kind, n.text AS text,
                       n.source_file AS source_file, n.source_heading AS source_heading,
                       refs, refbys
                """,
                id=node_id,
            ).single()
            if not rec:
                return None
            return GraphNodeView(
                id=rec["id"], kind=rec["kind"], text=rec["text"],
                source_file=rec["source_file"], source_heading=rec["source_heading"],
                references=[r for r in rec["refs"] if r is not None],
                referenced_by=[r for r in rec["refbys"] if r is not None],
            )

    def neighbors(self, node_id: str) -> dict | None:
        node = self.get_node(node_id)
        if node is None:
            return None
        return {
            "id": node.id,
            "references": node.references,
            "referenced_by": node.referenced_by,
        }

    def _bfs_hops(self, node_id: str, direction: str, max_hops: int) -> list[dict]:
        """Shortest-hop distance to every node reachable within max_hops, same
        semantics as LocalGraphStore's visited-once BFS (each node's first/
        shortest hop, never revisited). Neo4j doesn't allow parameterizing a
        variable-length relationship's hop bound, so max_hops (an internal
        int, never user text) is inlined into the pattern, not interpolated
        as a string from user input."""
        max_hops = int(max_hops)
        arrow = f"-[:{self.REL}*1..{max_hops}]->" if direction == "up" else f"<-[:{self.REL}*1..{max_hops}]-"
        query = f"""
            MATCH (start:{self.LABEL} {{id: $id}})
            OPTIONAL MATCH p = (start){arrow}(other)
            WHERE other IS NOT NULL AND other <> start
            WITH other, min(length(p)) AS hop
            RETURN other.id AS id, hop ORDER BY hop, id
        """
        with self._session() as s:
            return [{"id": r["id"], "hop": r["hop"]} for r in s.run(query, id=node_id)]

    def traceability_chain(self, node_id: str, max_hops: int = 3) -> dict | None:
        if self.get_node(node_id) is None:
            return None
        return {
            "id": node_id,
            "upstream": self._bfs_hops(node_id, "up", max_hops),
            "downstream": self._bfs_hops(node_id, "down", max_hops),
        }

    def impact_analysis(self, node_id: str, max_hops: int = 3) -> dict | None:
        if self.get_node(node_id) is None:
            return None
        return {"id": node_id, "affects": self._bfs_hops(node_id, "down", max_hops)}

    def orphan_rate(self, kind: str | None = None) -> dict:
        with self._session() as s:
            rec = s.run(
                f"""
                MATCH (n:{self.LABEL})
                WHERE $kind IS NULL OR n.kind = $kind
                OPTIONAL MATCH (n)-[:{self.REL}]-(other)
                WITH n, count(other) AS deg
                WITH collect({{id: n.id, deg: deg}}) AS rows
                RETURN size(rows) AS total,
                       size([r IN rows WHERE r.deg = 0]) AS orphans,
                       [r IN rows WHERE r.deg = 0 | r.id] AS orphan_ids
                """,
                kind=kind,
            ).single()
            total = rec["total"]
            orphans = rec["orphans"]
            if not total:
                return {"kind": kind, "total": 0, "orphans": 0, "orphan_rate": None}
            return {
                "kind": kind or "all",
                "total": total,
                "orphans": orphans,
                "orphan_rate": round(orphans / total, 3),
                "orphan_ids": rec["orphan_ids"],
            }

    def search(self, query: str, limit: int = 10) -> list[dict]:
        with self._session() as s:
            recs = s.run(
                f"""
                MATCH (n:{self.LABEL})
                WHERE toLower(n.text) CONTAINS toLower($q) OR toLower(n.id) CONTAINS toLower($q)
                RETURN n.id AS id, n.kind AS kind, n.source_file AS source_file,
                       substring(n.text, 0, 200) AS snippet
                LIMIT $limit
                """,
                q=query, limit=limit,
            )
            return [dict(r) for r in recs]
