"""
Model-based test generation (application spec §6).

The component that exists in none of the three prior systems. Everything else in
the specification is either working code or a thin adapter over it; this derives
test paths through a model against explicit coverage criteria.

Deliberately database-free -- see model.py.
"""
from metis_mcp.mbt.criteria import (
    ALL_STATES,
    ALL_TRANSITION_PAIRS,
    ALL_TRANSITIONS,
    DEFAULT_CRITERION,
    GUARD_COVERAGE,
    CoverageTarget,
    CriterionResult,
    criterion_names,
    targets_for,
)
from metis_mcp.mbt.model import IMPLEMENTED, PLANNED, Model, State, Transition
from metis_mcp.mbt.path_generation import (
    DEFAULT_SETUP_CAP,
    GenerationResult,
    Path,
    Uncoverable,
    generate,
)

__all__ = [
    "Model", "State", "Transition", "IMPLEMENTED", "PLANNED",
    "CoverageTarget", "CriterionResult", "targets_for", "criterion_names",
    "ALL_STATES", "ALL_TRANSITIONS", "ALL_TRANSITION_PAIRS", "GUARD_COVERAGE",
    "DEFAULT_CRITERION",
    "generate", "Path", "GenerationResult", "Uncoverable", "DEFAULT_SETUP_CAP",
]
