"""Stakeholder specification generation (spec §18)."""
from metis_mcp.specgen.specification import (
    EXPORT,
    LIVING,
    SPEC_VERSION,
    Document,
    Rule,
    Situation,
    Specification,
    build,
    dated_export,
    living_page,
    render_markdown,
)

__all__ = [
    "Specification", "Rule", "Situation", "Document",
    "build", "render_markdown", "living_page", "dated_export",
    "LIVING", "EXPORT", "SPEC_VERSION",
]
