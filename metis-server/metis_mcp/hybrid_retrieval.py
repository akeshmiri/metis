"""
§8.2 Hybrid retrieval -- four explicit modes (REQ-METIS-MEM-02: results
merged and reranked, not just concatenated).

  Graph traversal        REAL. Multi-hop structural traversal over the
                          real ontology (CITES/HAS_AC/IMPLEMENTS/VERIFIES/
                          TRACES_TO/COVERS), same relationship set schema-02
                          already declares as bi-temporal structural edges.
  BM25/keyword            REAL. schema-01 already declares
                          `metis_graph_fulltext` (Requirement/
                          AcceptanceCriterion/BusinessRule/
                          MicroRequirement/Constitution/Defect/Incident) --
                          created but, before this module, never actually
                          queried by any code in this codebase (verified
                          by grep). This is that first real query path.
  Semantic/vector          BLOCKED, disclosed, not faked. schema-01 also
                          declares 4 real HNSW vector indexes
                          (metis_graph_embedding_*, 1536-dim, cosine), but
                          nothing anywhere in this codebase ever computes
                          or writes an `embedding` property (verified: no
                          Ollama, no sentence-transformers installed, no
                          OpenAI-compatible embedding call). Querying a
                          vector index with a fabricated/zero vector would
                          silently return meaningless nearest-neighbors
                          that look like real results -- semantic_vector_
                          search() refuses to do that and says so, per
                          this project's no-fabrication discipline.
  Temporal point-in-time   REAL. Delegates to metis_mcp/temporal.py's
                          as_of() (§5.4) -- explicit mode, not a post-hoc
                          filter, exactly as the spec requires.

REQ-METIS-MEM-02's reranker is described as "Hindsight-derived
cross-encoder" -- no such model (or any ML reranking model) is available
in this environment, same real constraint as the vector index above. What
IS built: a real, deterministic, disclosed weighted-score merge across
whichever modes actually ran, not a fabricated cross-encoder score.
"""
from dataclasses import dataclass, field

# Real edge types schema-02 declares as structural/bi-temporal (§8's own
# traversal target) -- CITES is the dogfooding corpus's own cross-reference
# edge (neo4j_graph_store.py's REL), included so graph traversal works
# against both the dogfooding and production ontologies.
_TRAVERSAL_RELS = "CITES|HAS_AC|IMPLEMENTS|VERIFIES|TRACES_TO|COVERS"

_MODE_WEIGHTS = {"graph_traversal": 0.4, "bm25": 0.35, "temporal": 0.25}


@dataclass
class RetrievalHit:
    id: str
    modes: list = field(default_factory=list)   # which mode(s) surfaced this hit
    mode_scores: dict = field(default_factory=dict)  # mode -> its own normalized 0-1 score
    merged_score: float = 0.0


def graph_traversal_search(session, anchor_id: str, max_hops: int = 2) -> list[dict]:
    """Precise multi-hop structural search from a real anchor node.
    Score = 1 / (1 + hop_distance) -- closer is more relevant, a real,
    simple, disclosed distance-based score, not a learned ranking.

    Excludes :DogfoodingItem explicitly: schema-01's id-uniqueness
    constraints are per-label, not global, and :DogfoodingItem (the
    self-referential dogfooding corpus's shadow copy) is verified to
    share real ids with the production ontology (e.g. both a
    :DogfoodingItem and a :Constitution node can be {id: 'CONST-046'} --
    found for real in metis_mcp/temporal.py, same root cause here)."""
    rows = session.run(
        f"""
        MATCH (anchor {{id: $anchor_id}}) WHERE NOT anchor:DogfoodingItem
        MATCH p = (anchor)-[:{_TRAVERSAL_RELS}*1..{max_hops}]-(other)
        WHERE other.id IS NOT NULL AND other.id <> $anchor_id AND NOT other:DogfoodingItem
        WITH other, min(length(p)) AS hops
        RETURN other.id AS id, hops
        ORDER BY hops ASC
        """,
        anchor_id=anchor_id,
    ).data()
    return [{"id": r["id"], "hops": r["hops"], "score": round(1 / (1 + r["hops"]), 4)} for r in rows]


def bm25_search(session, query: str, top_k: int = 10) -> list[dict]:
    """Real Lucene BM25-backed full-text search via the real
    metis_graph_fulltext index. Scores are Lucene's native relevance
    scores, normalized here to 0-1 against the top hit in this result set
    (not a global constant -- Lucene scores aren't bounded/comparable
    across different queries)."""
    # Cypher param named 'q', not 'query' -- neo4j's Session.run(query, ...)
    # treats a keyword arg literally named 'query' as colliding with its own
    # first positional parameter (the Cypher text itself): real
    # TypeError('got multiple values for argument 'query'') caught writing
    # this test, not a hypothetical.
    rows = session.run(
        "CALL db.index.fulltext.queryNodes('metis_graph_fulltext', $q) "
        "YIELD node, score RETURN node.id AS id, score ORDER BY score DESC LIMIT $top_k",
        q=query, top_k=top_k,
    ).data()
    if not rows:
        return []
    max_score = max(r["score"] for r in rows) or 1.0
    return [{"id": r["id"], "raw_score": r["score"], "score": round(r["score"] / max_score, 4)} for r in rows]


def semantic_vector_search(session, query: str, top_k: int = 10) -> dict:
    """Honest refusal, not a fabricated result set: no embedding model is
    available in this environment to turn `query` into a real 1536-dim
    vector, so this never calls db.index.vector.queryNodes with a
    guessed/zero vector -- that would silently return meaningless nearest
    neighbors dressed up as real semantic matches."""
    populated = session.run(
        "MATCH (n) WHERE n.embedding IS NOT NULL RETURN count(n) AS c LIMIT 1"
    ).single()["c"]
    return {
        "available": False, "hits": [],
        "reason": "No embedding model is available in this environment (no Ollama, no "
                  "sentence-transformers, no OpenAI-compatible embedding endpoint) -- "
                  f"{populated} node(s) currently carry a real `embedding` property. The 4 "
                  "real HNSW vector indexes (metis_graph_embedding_*, schema-01) exist and "
                  "would work the moment a real embedding pipeline populates them; querying "
                  "them with a fabricated vector now would produce meaningless results "
                  "presented as real semantic matches, which this function refuses to do.",
    }


def temporal_point_in_time_search(session, entity_id: str, timestamp: str) -> dict:
    """§5.4's as_of(), reused directly -- explicit mode per the spec
    ('not a post-hoc filter'), not reimplemented here."""
    from metis_mcp.temporal import as_of
    result = as_of(session, entity_id, timestamp)
    if result is None:
        return {"id": entity_id, "timestamp": timestamp, "found": False}
    return {"id": entity_id, "timestamp": timestamp, "found": True,
            "revision": result.revision, "properties": result.properties}


def hybrid_search(session, query: str | None = None, anchor_id: str | None = None,
                   as_of_timestamp: str | None = None, top_k: int = 10) -> dict:
    """REQ-METIS-MEM-02: runs whichever modes have real inputs to run
    against (BM25 needs `query`, graph traversal needs `anchor_id`,
    temporal needs both `anchor_id` and `as_of_timestamp`; semantic never
    runs for real, see semantic_vector_search's docstring), merges hits by
    id, and reranks via a real, disclosed weighted-score sum -- not a
    fabricated cross-encoder score (no such model is available here)."""
    modes_run = []
    hits: dict[str, RetrievalHit] = {}

    def _record(mode: str, mode_hits: list[dict]):
        modes_run.append(mode)
        for h in mode_hits:
            hit = hits.setdefault(h["id"], RetrievalHit(id=h["id"]))
            hit.modes.append(mode)
            hit.mode_scores[mode] = h["score"]

    if anchor_id:
        _record("graph_traversal", graph_traversal_search(session, anchor_id))
    if query:
        _record("bm25", bm25_search(session, query, top_k=top_k))
    temporal_result = None
    if anchor_id and as_of_timestamp:
        temporal_result = temporal_point_in_time_search(session, anchor_id, as_of_timestamp)
        modes_run.append("temporal")
        if temporal_result["found"]:
            hit = hits.setdefault(anchor_id, RetrievalHit(id=anchor_id))
            hit.modes.append("temporal")
            hit.mode_scores["temporal"] = 1.0

    semantic = semantic_vector_search(session, query) if query else \
        {"available": False, "hits": [], "reason": "No query text given."}

    for hit in hits.values():
        total_weight = sum(_MODE_WEIGHTS[m] for m in hit.mode_scores)
        hit.merged_score = round(
            sum(hit.mode_scores[m] * _MODE_WEIGHTS[m] for m in hit.mode_scores) / total_weight, 4
        ) if total_weight else 0.0

    ranked = sorted(hits.values(), key=lambda h: h.merged_score, reverse=True)[:top_k]

    return {
        "modes_run": modes_run,
        "semantic_vector_mode": semantic,
        "results": [
            {"id": h.id, "merged_score": h.merged_score, "modes": h.modes, "mode_scores": h.mode_scores}
            for h in ranked
        ],
        "temporal_point_in_time": temporal_result,
        "reranker_note": "Real, deterministic weighted-score merge (graph_traversal=0.4, "
                          "bm25=0.35, temporal=0.25) -- REQ-METIS-MEM-02's 'Hindsight-derived "
                          "cross-encoder reranker' needs a real ML reranking model not "
                          "available in this environment; disclosed, not faked.",
    }
