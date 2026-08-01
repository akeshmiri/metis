"""
CONST-051/052/053 enforcement: the classification gate.

This is the actual code behind the policy decided in metis-gap-remediation.md
and the confirmation checklist in metis-const-053-confirmation-record.md --
not a description of the policy, the thing that enforces it.

Rules implemented here, matching the Constitution exactly:
  - CONST-051: content is classified Public/Internal, Confidential, or
    Restricted BEFORE it reaches an external LLM call. Confidential requires
    a confirmed ZDR agreement; Restricted never reaches an LLM call at all
    (unchanged from the existing security framework, BS-002).
  - CONST-052: classification is a per-repository/service property set
    during onboarding, never inferred per-file by the pipeline. An
    unclassified repository defaults to Confidential -- fail closed, not
    fail open.
  - CONST-053: the ZDR-confirmed flag itself defaults to False and must be
    explicitly, deliberately set True -- there is no code path that infers
    "probably fine" from partial information.
"""
from dataclasses import dataclass
from enum import Enum


class Classification(str, Enum):
    PUBLIC_INTERNAL = "public_internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    UNCLASSIFIED = "unclassified"  # not a real tier -- see _effective_classification


class GateDecision(str, Enum):
    ALLOW = "allow"
    BLOCK_NEEDS_ZDR = "block_needs_zdr"
    BLOCK_RESTRICTED = "block_restricted"


@dataclass
class GateResult:
    decision: GateDecision
    repository: str
    effective_classification: Classification
    reason: str

    @property
    def allowed(self) -> bool:
        return self.decision == GateDecision.ALLOW


class ClassificationGate:
    """
    Usage:
        gate = ClassificationGate(zdr_confirmed=False)
        gate.set_classification("payments-service", Classification.CONFIDENTIAL)
        result = gate.check("payments-service")
        if not result.allowed:
            # do NOT send this repository's content to the LLM call
            ...
    """

    def __init__(self, zdr_confirmed: bool = False):
        # CONST-053 -- defaults to False. This must be explicitly passed True
        # by the caller, which itself should only happen after
        # metis-const-053-confirmation-record.md's checklist is fully filled
        # in -- there is no automatic or inferred path to True in this class.
        self.zdr_confirmed = zdr_confirmed
        self._classifications: dict[str, Classification] = {}
        self._config_manager = None  # set only by from_config()

    @classmethod
    def from_config(cls, config_manager) -> "ClassificationGate":
        """
        Build the gate entirely from an external ConfigManager -- no
        classification or ZDR status is set via code anywhere in a real
        deployment. `config_manager.get_classification(repo)` is consulted
        lazily per-repository at check() time (see check() below), not
        pre-loaded, since the config manager doesn't enumerate "every
        repository that might ever be checked" -- it only needs to answer
        for the ones actually asked about.
        """
        gate = cls(zdr_confirmed=config_manager.get_zdr_confirmed())
        gate._config_manager = config_manager
        return gate

    def set_classification(self, repository: str, classification: Classification) -> None:
        if classification == Classification.UNCLASSIFIED:
            raise ValueError(
                "UNCLASSIFIED is not a settable classification -- it's the fail-closed "
                "default for repositories that were never explicitly classified. "
                "Set an actual tier (PUBLIC_INTERNAL, CONFIDENTIAL, or RESTRICTED)."
            )
        self._classifications[repository] = classification

    def _effective_classification(self, repository: str) -> Classification:
        # CONST-052 -- fail closed: an unclassified repository is treated as
        # Confidential, never as Public/Internal, regardless of how
        # innocuous its name looks.
        #
        # Resolution order: config manager (the real, external source of
        # truth in a from_config()-built gate) first; the in-memory
        # `_classifications` dict second (used directly only by tests and
        # by callers not using a config manager); the fail-closed default
        # last if neither has an answer.
        if self._config_manager is not None:
            raw = self._config_manager.get_classification(repository)
            if raw is not None:
                return Classification(raw)
        return self._classifications.get(repository, Classification.CONFIDENTIAL)

    def check(self, repository: str) -> GateResult:
        effective = self._effective_classification(repository)

        if effective == Classification.RESTRICTED:
            return GateResult(
                decision=GateDecision.BLOCK_RESTRICTED,
                repository=repository,
                effective_classification=effective,
                reason="Restricted-tier content never reaches an external LLM call "
                       "(unchanged from BS-002) -- this is not a ZDR question at all.",
            )

        if effective == Classification.CONFIDENTIAL:
            if self.zdr_confirmed:
                return GateResult(
                    decision=GateDecision.ALLOW,
                    repository=repository,
                    effective_classification=effective,
                    reason="Confidential-tier, but a Zero Data Retention agreement "
                           "is confirmed active -- proceeding.",
                )
            return GateResult(
                decision=GateDecision.BLOCK_NEEDS_ZDR,
                repository=repository,
                effective_classification=effective,
                reason="Confidential-tier content is blocked at the connector level "
                       "until a Zero Data Retention agreement is confirmed "
                       "(CONST-051/053) -- see metis-const-053-confirmation-record.md. "
                       "This includes repositories that were never explicitly classified "
                       "(CONST-052 fail-closed default).",
            )

        # PUBLIC_INTERNAL
        return GateResult(
            decision=GateDecision.ALLOW,
            repository=repository,
            effective_classification=effective,
            reason="Public/Internal-tier -- proceeds under standard API terms, no ZDR needed.",
        )
