"""
Wires the Constitution gate (constitution_gate.py, REQ-METIS-GRD-11), Layer 2
(structural_validation.py), and Layer 3 (confidence_tiering.py) together
against a real Neo4j instance -- this is the actual Load-stage gate (§6.1's
"Cognify -> Load" boundary): a candidate entity either gets written with a
real lifecycle_state/risk_tag, or it doesn't get written at all.

Layer 5 (contradiction detection) isn't built yet -- has_contradiction is
always False here, honestly not a fabricated check. Layer 6 (LLM-as-judge)
also isn't built -- confidence is a caller-supplied input, not computed
here (see confidence_tiering.py's docstring for the same scope note).
"""
from dataclasses import dataclass

from metis_mcp.academy import get_why_link
from metis_mcp.confidence_tiering import ConfidenceTier, ConfidenceTiering, TieringResult
from metis_mcp.constitution_gate import check_constitution_hard_blocks, ConstitutionCheckResult
from metis_mcp.structural_validation import StructuralValidator, ValidationResult


@dataclass
class SubmissionResult:
    tiering: TieringResult
    validation: ValidationResult | None
    written: bool
    constitution: ConstitutionCheckResult | None = None
    # REQ-METIS-ACD-03: inline "why" annotation -- a real Academy page link
    # for this rejection's reason, when one exists (metis_mcp/academy.py's
    # disclosed, real reason->page mapping); None for a reason this
    # project doesn't have matching Academy content for yet, never a
    # guessed/generic link.
    academy_link: str | None = None


def _episode_exists_check(session):
    def _check(episode_id: str) -> bool:
        rec = session.run(
            "MATCH (e:Episode {id: $id}) RETURN e LIMIT 1", id=episode_id
        ).single()
        return rec is not None
    return _check


def submit_candidate(session, label: str, entity: dict, confidence: float,
                      source_count: int = 1, risk_tag: str | None = None) -> SubmissionResult:
    # REQ-METIS-GRD-11: checked first, ahead of the general Layer 2/3
    # pipeline below -- a Constitution violation is always a hard block
    # (REJECTED), regardless of the caller's reported confidence, never
    # allowed to land at Quarantine tier.
    constitution = check_constitution_hard_blocks(session, label, entity)
    if constitution.blocked:
        tiering = TieringResult(tier=ConfidenceTier.REJECTED, lifecycle_state="Rejected",
                                 reason=constitution.reason)
        return SubmissionResult(tiering=tiering, validation=None, written=False, constitution=constitution,
                                 academy_link=get_why_link(constitution.reason))

    validator = StructuralValidator(episode_exists=_episode_exists_check(session))
    validation = validator.validate(label, entity)

    tiering_engine = ConfidenceTiering()
    tiering = tiering_engine.evaluate(
        confidence=confidence, structural_valid=validation.valid,
        has_contradiction=False, source_count=source_count,
    )

    if not tiering.written_to_graph:
        reason = "; ".join(validation.reasons) if validation.reasons else tiering.reason
        return SubmissionResult(tiering=tiering, validation=validation, written=False,
                                 academy_link=get_why_link(reason))

    def _write(tx):
        # label is interpolated directly into the query (Cypher doesn't support
        # parameterized labels) -- safe here specifically because reaching this
        # line requires tiering.written_to_graph, which requires
        # validation.valid, which is only True for label in KNOWN_LABELS (a
        # fixed, closed set of ontology strings, never arbitrary user input).
        props = dict(entity)
        props["lifecycle_state"] = tiering.lifecycle_state
        if risk_tag is not None:
            props["risk_tag"] = risk_tag
        tx.run(
            f"MERGE (n:{label} {{id: $id}}) SET n += $props",
            id=entity["id"], props=props,
        )

    session.execute_write(_write)
    return SubmissionResult(tiering=tiering, validation=validation, written=True)
