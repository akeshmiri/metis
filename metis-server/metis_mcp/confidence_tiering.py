"""
REQ-METIS-GRD-03 (Layer 3, §7 of metis-specification.md): confidence
tiering -- the state machine only, per PLAN.md Phase 4's explicit scope
("without the judge-call logic yet -- that needs an LLM, deferred to a
later phase"). No model call happens in this module; confidence is an
input the caller supplies (from the extraction step, itself out of scope
here), not computed here.

Exact rule from the spec, implemented verbatim:
  >= 0.9 + single reliable source + passes L2       -> auto_write (Draft)
  0.6-0.9                                            -> quarantine (Quarantine)
  < 0.6, OR L2-fail, OR contradiction                -> rejected (Rejected), logged only

lifecycle_state values (Draft/Quarantine/Rejected/...) match the scheme
already declared in schema/metis-graph-03-single-db-consolidation.cypher's
review-queue-as-a-query design (`WHERE n.lifecycle_state = 'Quarantine'`).
"""
from dataclasses import dataclass
from enum import Enum

AUTO_WRITE_MIN_CONFIDENCE = 0.9
QUARANTINE_MIN_CONFIDENCE = 0.6


class ConfidenceTier(str, Enum):
    AUTO_WRITE = "auto_write"
    QUARANTINE = "quarantine"
    REJECTED = "rejected"


LIFECYCLE_STATE_FOR_TIER = {
    ConfidenceTier.AUTO_WRITE: "Draft",
    ConfidenceTier.QUARANTINE: "Quarantine",
    ConfidenceTier.REJECTED: "Rejected",
}


@dataclass
class TieringResult:
    tier: ConfidenceTier
    lifecycle_state: str
    reason: str

    @property
    def written_to_graph(self) -> bool:
        """Rejected items are 'logged only' per REQ-METIS-GRD-03 -- never
        written as a graph entity at all, not even in a Rejected state."""
        return self.tier != ConfidenceTier.REJECTED


class ConfidenceTiering:
    def evaluate(self, confidence: float, structural_valid: bool,
                  has_contradiction: bool, source_count: int = 1) -> TieringResult:
        if not structural_valid:
            return TieringResult(
                tier=ConfidenceTier.REJECTED,
                lifecycle_state=LIFECYCLE_STATE_FOR_TIER[ConfidenceTier.REJECTED],
                reason="Failed Layer 2 structural validation -- rejected regardless of "
                       "confidence score (REQ-METIS-GRD-03).",
            )

        if has_contradiction:
            return TieringResult(
                tier=ConfidenceTier.REJECTED,
                lifecycle_state=LIFECYCLE_STATE_FOR_TIER[ConfidenceTier.REJECTED],
                reason="Contradicts existing graph state -- rejected regardless of "
                       "confidence score (REQ-METIS-GRD-03); see Layer 5 contradiction "
                       "detection for the Disputed-tracking path this feeds, not built here.",
            )

        if confidence >= AUTO_WRITE_MIN_CONFIDENCE and source_count >= 1:
            return TieringResult(
                tier=ConfidenceTier.AUTO_WRITE,
                lifecycle_state=LIFECYCLE_STATE_FOR_TIER[ConfidenceTier.AUTO_WRITE],
                reason=f"Confidence {confidence:.2f} >= {AUTO_WRITE_MIN_CONFIDENCE} with a "
                       f"single reliable source and passing Layer 2 -- auto-written as Draft "
                       f"(never authoritative without further review).",
            )

        if confidence >= QUARANTINE_MIN_CONFIDENCE:
            return TieringResult(
                tier=ConfidenceTier.QUARANTINE,
                lifecycle_state=LIFECYCLE_STATE_FOR_TIER[ConfidenceTier.QUARANTINE],
                reason=f"Confidence {confidence:.2f} is between {QUARANTINE_MIN_CONFIDENCE} "
                       f"and {AUTO_WRITE_MIN_CONFIDENCE} -- quarantined for human review "
                       f"(Layer 7), not auto-written.",
            )

        return TieringResult(
            tier=ConfidenceTier.REJECTED,
            lifecycle_state=LIFECYCLE_STATE_FOR_TIER[ConfidenceTier.REJECTED],
            reason=f"Confidence {confidence:.2f} < {QUARANTINE_MIN_CONFIDENCE} -- rejected, "
                   f"logged only, never written to the graph (REQ-METIS-GRD-03).",
        )
