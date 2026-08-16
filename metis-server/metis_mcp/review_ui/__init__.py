"""The review interface (spec §9.3): evidence assembly and the model view."""
from metis_mcp.review_ui.evidence import (
    DECISIONS,
    REQUIRED_EVIDENCE,
    BatchDecision,
    EvidenceMissing,
    Screen,
    approve_model_screen,
    batch,
    confirm_match_screen,
    confirm_publication_screen,
    decide_drift_screen,
    format_screen,
    name_state_screen,
    permitted,
    resolve_divergence_screen,
)
from metis_mcp.review_ui.view import (
    COVERED_DIRECT,
    COVERED_INDIRECT,
    EXCLUDED,
    UNCOVERED,
    Edge,
    Layout,
    Node,
    build_layout,
    layered_layout,
    render_html,
    render_svg,
)

__all__ = [
    "Screen", "BatchDecision", "EvidenceMissing", "DECISIONS", "REQUIRED_EVIDENCE",
    "approve_model_screen", "name_state_screen", "resolve_divergence_screen",
    "confirm_match_screen", "decide_drift_screen", "confirm_publication_screen",
    "batch", "permitted", "format_screen",
    "Layout", "Node", "Edge", "layered_layout", "build_layout",
    "render_svg", "render_html",
    "COVERED_DIRECT", "COVERED_INDIRECT", "UNCOVERED", "EXCLUDED",
]
