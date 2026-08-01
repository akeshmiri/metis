"""
§8.3 Sleep-time consolidation (REQ-METIS-MEM-03): "A nightly background
job summarizes low-signal episode chains into rollup episodes (never
deletes raw episodes -- non-lossy) and proposes (never auto-applies)
near-duplicate Requirement/AcceptanceCriterion merges for human review.
Runs interruptibly per §10's resume protocol."

Two independent real mechanisms:

  Rollup summarization
    A batch of low-signal Episodes (age-based: older than a real cutoff,
    the simplest honest 'low-signal' proxy available without a real
    importance-scoring model) get a single :RollupEpisode created,
    SUMMARIZES-linked to every real Episode it covers -- the raw Episodes
    are never deleted or modified (REQ-METIS-MEM-03's non-lossy
    requirement; Episode is already documented elsewhere in this codebase
    as "the atomic, immutable ingestion unit ... never deleted even after
    extraction"). Resumable the same way
    connectors/application_code_connector.py's checkpoint works: a
    dedicated checkpoint Episode records the last t_recorded actually
    rolled up, so a killed run resumes from there, never reprocessing
    already-summarized episodes and never silently skipping unprocessed
    ones.

  Near-duplicate merge proposals
    Real lexical Jaccard similarity over word sets of Requirement/
    AcceptanceCriterion text -- NOT semantic/embedding similarity (no
    embedding model is available in this environment, same real
    constraint as metis_mcp/hybrid_retrieval.py's semantic_vector_search).
    A pair above `threshold` gets a real :MergeProposal node, status
    'PendingReview' -- proposals are written to the graph for a human to
    act on; nothing here ever merges/deletes either candidate. This is
    also DQ-016's real data source (near-duplicate density).
"""
import re
from dataclasses import dataclass, field

CHECKPOINT_CONNECTOR = "sleep-time-consolidation"
_WORD_RE = re.compile(r"[a-z0-9]+")


def _word_set(text: str) -> set:
    return set(_WORD_RE.findall(text.lower()))


def jaccard_similarity(text_a: str, text_b: str) -> float:
    words_a, words_b = _word_set(text_a), _word_set(text_b)
    if not words_a and not words_b:
        return 0.0
    union = words_a | words_b
    if not union:
        return 0.0
    return round(len(words_a & words_b) / len(union), 4)


@dataclass
class MergeProposal:
    id_a: str
    id_b: str
    similarity: float
    label: str


def find_near_duplicates(session, label: str, threshold: float = 0.7) -> list[MergeProposal]:
    """O(n^2) pairwise comparison -- fine at real-world Requirement/
    AcceptanceCriterion volumes for a nightly batch job, not a live-query
    path. Never compares an entity against itself, never double-reports
    the same pair in both orders."""
    rows = session.run(f"MATCH (n:{label}) WHERE n.text IS NOT NULL RETURN n.id AS id, n.text AS text").data()
    proposals = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            sim = jaccard_similarity(rows[i]["text"], rows[j]["text"])
            if sim >= threshold:
                proposals.append(MergeProposal(id_a=rows[i]["id"], id_b=rows[j]["id"], similarity=sim, label=label))
    return proposals


def write_merge_proposals(session, proposals: list[MergeProposal], source_episode_id: str) -> list[str]:
    """Writes real :MergeProposal nodes, status='PendingReview' -- never
    auto-applies (REQ-METIS-MEM-03's explicit constraint). Idempotent by a
    deterministic id (id_a, id_b sorted) so re-running the detector doesn't
    duplicate an already-pending proposal."""
    proposal_ids = []

    def _write(tx):
        for p in proposals:
            a, b = sorted([p.id_a, p.id_b])
            proposal_id = f"merge-proposal:{a}:{b}"
            tx.run(
                """
                MERGE (mp:MergeProposal {id: $id})
                ON CREATE SET mp.source_episode_id = $episode, mp.status = 'PendingReview',
                    mp.candidate_a = $a, mp.candidate_b = $b, mp.similarity = $similarity,
                    mp.label = $label, mp.created_at = datetime()
                """,
                id=proposal_id, episode=source_episode_id, a=a, b=b,
                similarity=p.similarity, label=p.label,
            )
            proposal_ids.append(proposal_id)
    session.execute_write(_write)
    return proposal_ids


def _rollup_checkpoint(session) -> str | None:
    rec = session.run(
        "MATCH (e:Episode {source_connector: $connector, source_kind: 'rollup_checkpoint'}) "
        "RETURN e.last_rolled_up_t_recorded AS t ORDER BY e.t_recorded DESC LIMIT 1",
        connector=CHECKPOINT_CONNECTOR,
    ).single()
    return rec["t"] if rec else None


def summarize_low_signal_episodes(session, older_than_days: int, summary_text_fn,
                                   batch_size: int = 500) -> dict:
    """`summary_text_fn(episode_rows: list[dict]) -> str` is supplied by the
    caller (deterministic string-joining by default is fine; a real LLM
    call could be substituted deliberately, same cost-awareness convention
    as llm_judge.py -- never wired in automatically here).

    Resumable: reads the checkpoint before selecting episodes (WHERE
    t_recorded > checkpoint), writes the new checkpoint only after the
    rollup Episode is successfully created -- a kill between those two
    steps leaves the checkpoint at its last good value, and the next run
    naturally reprocesses only what wasn't actually rolled up (same
    at-least-once, no-silent-gap property as application_code_connector.py)."""
    checkpoint = _rollup_checkpoint(session)
    rows = session.run(
        """
        MATCH (e:Episode)
        WHERE NOT e:RollupEpisode AND e.source_connector <> $checkpoint_connector
          AND e.t_recorded < datetime() - duration({days: $days})
          AND ($checkpoint IS NULL OR e.t_recorded > datetime($checkpoint))
        RETURN e.id AS id, e.t_recorded AS t_recorded, e.episode_type AS episode_type
        ORDER BY e.t_recorded ASC LIMIT $batch_size
        """,
        checkpoint_connector=CHECKPOINT_CONNECTOR, days=older_than_days,
        checkpoint=checkpoint, batch_size=batch_size,
    ).data()

    if not rows:
        return {"rolled_up": 0, "rollup_episode_id": None, "covered_episode_ids": []}

    covered_ids = [r["id"] for r in rows]
    summary = summary_text_fn(rows)
    latest_t_recorded = max(r["t_recorded"] for r in rows)
    rollup_id = f"rollup:{covered_ids[0]}:{covered_ids[-1]}:{len(covered_ids)}"

    def _write(tx):
        tx.run(
            """
            MERGE (ru:RollupEpisode:Episode {id: $id})
            SET ru.source_connector = 'sleep-time-consolidation', ru.source_kind = 'rollup',
                ru.job_id = $id, ru.t_recorded = datetime(), ru.episode_type = 'RollupSummary',
                ru.summary = $summary, ru.covered_count = $count
            WITH ru
            UNWIND $covered_ids AS cid
            MATCH (raw:Episode {id: cid})
            MERGE (ru)-[:SUMMARIZES]->(raw)
            """,
            id=rollup_id, summary=summary, count=len(covered_ids), covered_ids=covered_ids,
        )
        # MERGE, not CREATE -- same real, demonstrated execute_write retry
        # edge case as metis_mcp/temporal.py's record_revision.
        tx.run(
            "MERGE (chk:Episode {id: $chk_id}) "
            "ON CREATE SET chk.source_connector = $connector, chk.source_kind = 'rollup_checkpoint', "
            "chk.job_id = $chk_id, chk.t_recorded = datetime(), "
            "chk.last_rolled_up_t_recorded = toString($latest)",
            chk_id=f"{CHECKPOINT_CONNECTOR}:checkpoint:{rollup_id}", connector=CHECKPOINT_CONNECTOR,
            latest=latest_t_recorded,
        )
    session.execute_write(_write)

    return {"rolled_up": len(covered_ids), "rollup_episode_id": rollup_id, "covered_episode_ids": covered_ids}


def default_summary_text_fn(episode_rows: list[dict]) -> str:
    """Deterministic, non-LLM default: a real, verifiable count/type
    breakdown -- not a fabricated narrative summary. A caller wanting an
    LLM-written prose summary can pass its own summary_text_fn (a
    deliberate, explicit choice, per this codebase's cost-awareness
    convention for LLM calls)."""
    by_type: dict = {}
    for r in episode_rows:
        by_type[r["episode_type"] or "unknown"] = by_type.get(r["episode_type"] or "unknown", 0) + 1
    breakdown = ", ".join(f"{count}x {etype}" for etype, count in sorted(by_type.items()))
    return f"Rollup of {len(episode_rows)} low-signal episode(s): {breakdown}."
