"""Model sources (application spec §4.2, R9)."""
from metis_mcp.model_sources.base import (
    AC_MINED,
    EXTRACTION_METHODS,
    HAND_AUTHORED,
    STATIC_ANALYSIS,
    ModelSource,
    SourceResult,
    availability,
    get,
    register,
    registered,
)
from metis_mcp.model_sources.landing import (
    LandingPlan,
    LandingResult,
    episode_id_for,
    land,
    plan_landing,
)
from metis_mcp.model_sources.sources import (
    ACMinedSource,
    CodeExtractedSource,
    HumanAuthoredSource,
)

__all__ = [
    "ModelSource", "SourceResult", "get", "register", "registered", "availability",
    "HAND_AUTHORED", "STATIC_ANALYSIS", "AC_MINED", "EXTRACTION_METHODS",
    "HumanAuthoredSource", "CodeExtractedSource", "ACMinedSource",
    "plan_landing", "land", "LandingPlan", "LandingResult", "episode_id_for",
]
