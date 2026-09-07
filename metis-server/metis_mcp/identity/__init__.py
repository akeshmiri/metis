"""Element identity, deduplication and incremental update (spec §14, R12, R13)."""
from metis_mcp.identity.keys import (
    CLAIM_SEPARATOR,
    claim_id,
    is_revision_of,
    logical_key_of,
    normalise_claim,
    business_entity_key,
    bare_id,
    keyed_states,
    keyed_transitions,
    normalise_guard,
    short,
    state_key,
    transition_key,
)
from metis_mcp.identity.matching import (
    ADDED,
    MODIFIED,
    REMOVED,
    RENAME_SIMILARITY,
    UNCHANGED,
    CarryResult,
    Change,
    Delta,
    RenameProposal,
    carry_human_facts,
    diff,
)

__all__ = [
    "business_entity_key",
    "state_key", "transition_key", "normalise_guard", "short",
    "keyed_states", "keyed_transitions",
    "claim_id", "logical_key_of", "normalise_claim", "is_revision_of",
    "CLAIM_SEPARATOR",
    "bare_id", "diff", "carry_human_facts", "Delta", "Change", "RenameProposal", "CarryResult",
    "ADDED", "MODIFIED", "REMOVED", "UNCHANGED", "RENAME_SIMILARITY",
]
