"""Project risk management: exposure, the register, the RBS, and what a model observes.

The arithmetic and the register work with no graph. `candidates` is the one half
that needs one, kept separate so the rest stays a generic toolkit.
"""
from metis_mcp.risk.candidates import (
    from_change_review,
    from_unmeasured,
)
from metis_mcp.risk.exposure import (
    BANDS,
    SCALE,
    Exposure,
    RiskInputRefused,
    band_for,
    emv,
    heat_map_cell,
    pert,
)

# `exposure` — the FUNCTION — is deliberately not re-exported here, though every
# other name is. It would shadow `metis_mcp.risk.exposure` the MODULE, so
# `from metis_mcp.risk import exposure` would silently hand back a function and
# every attribute access on it would fail with an AttributeError naming neither
# problem. Import it from its module: `from metis_mcp.risk.exposure import
# exposure`.
from metis_mcp.risk.rbs import (
    BOUNDARIES,
    CATEGORIES,
    UnknownCategory,
    distribution,
    validate_category,
)
from metis_mcp.risk.register import (
    AUTHORED,
    MODEL,
    OPPORTUNITY,
    OPPORTUNITY_RESPONSES,
    THREAT,
    THREAT_RESPONSES,
    UNKNOWN,
    Finding,
    summarise,
    validate,
    validate_risk,
)

__all__ = [
    "BANDS", "SCALE", "Exposure", "RiskInputRefused", "band_for", "emv",
    "heat_map_cell", "pert",
    "BOUNDARIES", "CATEGORIES", "UnknownCategory", "distribution",
    "validate_category",
    "AUTHORED", "MODEL", "OPPORTUNITY", "OPPORTUNITY_RESPONSES", "THREAT",
    "THREAT_RESPONSES", "UNKNOWN", "Finding", "summarise", "validate", "validate_risk",
    "from_change_review", "from_unmeasured",
]
