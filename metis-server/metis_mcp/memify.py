"""
§8.4 Memify feedback loop (REQ-METIS-MEM-04): "ExtractionCorrected
episodes (fired on any human override of an AI-inferred fact) feed a
nightly aggregation job that adjusts default confidence per
(extraction-rule, entity-type, connector) triple -- a Bayesian-style
counting update, auditable and reversible, not model retraining."

Real Beta-Bernoulli posterior, not a fabricated ML update: every human
correction is evidence of whether this (extraction-rule, entity-type,
connector) triple tends to be UNDER- or OVER-confident. Each correction
that raised the confidence counts as one "success" (alpha), each that
lowered it counts as one "failure" (beta); the adjusted default is the
posterior mean alpha / (alpha + beta), Laplace-smoothed with a uniform
Beta(1,1) prior (start at exactly 0.5 with zero evidence -- no arbitrary
extraction-rule-specific bias assumed before any human has ever corrected
anything for it).

Auditable: every correction is a real, permanent Episode
(ExtractionCorrected) -- never deleted, same non-lossy Episode principle
as everything else in this codebase.
Reversible: the adjustment is RECOMPUTED FROM SCRATCH from the full
correction history every time, not a mutated running average -- deleting
or correcting a bad ExtractionCorrected episode (a human fixing their own
mistake) automatically un-does its effect on the next recomputation,
with no separate "undo" mechanism needed.
Not model retraining: nothing here touches Cognify's extraction model or
prompts -- this is a confidence-DEFAULT lookup table, consulted by
whatever assigns a starting confidence to a new extraction, per the
spec's own "not model retraining" clause.
"""
from dataclasses import dataclass


def _triple_key(extraction_rule: str, entity_type: str, connector: str) -> str:
    return f"{extraction_rule}::{entity_type}::{connector}"


def record_extraction_correction(session, entity_id: str, extraction_rule: str, entity_type: str,
                                  connector: str, original_confidence: float,
                                  corrected_confidence: float, corrected_by: str) -> str:
    """Fired on any human override of an AI-inferred fact -- a real,
    permanent Episode, never a mutation of the corrected entity's own
    history (that's temporal.py's job if the entity itself needs a new
    revision; this Episode is specifically the correction SIGNAL Memify
    aggregates)."""
    import uuid
    episode_id = f"extraction-corrected:{uuid.uuid4()}"

    def _write(tx):
        # MERGE, not CREATE -- episode_id is computed once in Python before
        # this (possibly-retried) transaction function runs; a real,
        # demonstrated Neo4j driver edge case (execute_write can retry
        # after a successful server-side commit -- found for real in
        # metis_mcp/temporal.py) would hit this exact id's uniqueness
        # constraint on CREATE. MERGE makes a retry a safe no-op instead.
        tx.run(
            """
            MERGE (ep:Episode {id: $episode_id})
            ON CREATE SET ep.t_recorded = datetime(), ep.source_connector = $connector,
                ep.unit_id = $episode_id, ep.job_id = $episode_id, ep.episode_type = 'ExtractionCorrected',
                ep.entity_id = $entity_id, ep.extraction_rule = $extraction_rule, ep.entity_type = $entity_type,
                ep.original_confidence = $original_confidence, ep.corrected_confidence = $corrected_confidence,
                ep.corrected_by = $corrected_by
            """,
            episode_id=episode_id, connector=connector, entity_id=entity_id,
            extraction_rule=extraction_rule, entity_type=entity_type,
            original_confidence=original_confidence, corrected_confidence=corrected_confidence,
            corrected_by=corrected_by,
        )
    session.execute_write(_write)
    return episode_id


@dataclass
class ConfidenceAdjustment:
    extraction_rule: str
    entity_type: str
    connector: str
    alpha: int
    beta: int
    adjusted_default: float
    correction_count: int


def compute_confidence_adjustment(session, extraction_rule: str, entity_type: str,
                                   connector: str) -> ConfidenceAdjustment:
    """Recomputed from the full, real ExtractionCorrected history every
    call -- see module docstring for why that's what makes this
    reversible without a separate undo mechanism."""
    rows = session.run(
        "MATCH (e:Episode {episode_type: 'ExtractionCorrected', extraction_rule: $rule, "
        "entity_type: $etype, source_connector: $connector}) "
        "RETURN e.original_confidence AS orig, e.corrected_confidence AS corrected",
        rule=extraction_rule, etype=entity_type, connector=connector,
    ).data()

    alpha = 1 + sum(1 for r in rows if r["corrected"] > r["orig"])
    beta = 1 + sum(1 for r in rows if r["corrected"] < r["orig"])
    adjusted_default = round(alpha / (alpha + beta), 4)

    return ConfidenceAdjustment(
        extraction_rule=extraction_rule, entity_type=entity_type, connector=connector,
        alpha=alpha, beta=beta, adjusted_default=adjusted_default, correction_count=len(rows),
    )


def apply_confidence_adjustment(session, adjustment: ConfidenceAdjustment) -> str:
    """Writes the current computed adjustment as a real, queryable node --
    MERGE-based (one node per real triple, not one per run), so
    'reversible' means the next apply_confidence_adjustment call (after
    recomputing from a corrected history) simply overwrites this node's
    value, not that any history is destroyed."""
    key = _triple_key(adjustment.extraction_rule, adjustment.entity_type, adjustment.connector)

    def _write(tx):
        tx.run(
            """
            MERGE (ca:ConfidenceAdjustment {id: $key})
            SET ca.extraction_rule = $rule, ca.entity_type = $etype, ca.connector = $connector,
                ca.alpha = $alpha, ca.beta = $beta, ca.adjusted_default = $adjusted_default,
                ca.correction_count = $count, ca.last_computed_at = datetime()
            """,
            key=key, rule=adjustment.extraction_rule, etype=adjustment.entity_type,
            connector=adjustment.connector, alpha=adjustment.alpha, beta=adjustment.beta,
            adjusted_default=adjustment.adjusted_default, count=adjustment.correction_count,
        )
    session.execute_write(_write)
    return key


def get_adjusted_confidence_default(session, extraction_rule: str, entity_type: str,
                                     connector: str, fallback_default: float) -> float:
    """Real lookup a caller (e.g. a connector's confidence-assignment step)
    would use. `fallback_default` is returned untouched if this triple has
    never had a ConfidenceAdjustment computed -- a triple with zero human
    corrections has no adjustment opinion, and must not silently default
    to the Beta(1,1) midpoint (0.5) as if that were a real signal."""
    rec = session.run(
        "MATCH (ca:ConfidenceAdjustment {id: $key}) RETURN ca.adjusted_default AS v",
        key=_triple_key(extraction_rule, entity_type, connector),
    ).single()
    return rec["v"] if rec else fallback_default


def run_nightly_memify_job(session) -> list[str]:
    """REQ-METIS-MEM-04's 'nightly aggregation job': recomputes and applies
    the adjustment for every real (extraction_rule, entity_type, connector)
    triple that has at least one ExtractionCorrected episode -- not a
    fixed list of triples to check, discovered from real data."""
    triples = session.run(
        "MATCH (e:Episode {episode_type: 'ExtractionCorrected'}) "
        "RETURN DISTINCT e.extraction_rule AS rule, e.entity_type AS etype, e.source_connector AS connector"
    ).data()
    updated_keys = []
    for t in triples:
        adjustment = compute_confidence_adjustment(session, t["rule"], t["etype"], t["connector"])
        updated_keys.append(apply_confidence_adjustment(session, adjustment))
    return updated_keys
