"""Test-case rendering (application spec §7)."""
from metis_mcp.rendering.payload import UNRECOVERABLE, build_payload, unrecoverable_fields
from metis_mcp.rendering.test_case import (
    TIER_ACCEPTANCE_CRITERION,
    TIER_GENERATED_PROSE,
    TIER_VERBATIM,
    RenderResult,
    Step,
    TestCase,
    format_case,
    humanise,
    render,
    render_path,
)

__all__ = [
    "TestCase", "Step", "RenderResult", "render", "render_path", "format_case", "humanise",
    "TIER_ACCEPTANCE_CRITERION", "TIER_GENERATED_PROSE", "TIER_VERBATIM",
    "build_payload", "unrecoverable_fields", "UNRECOVERABLE",
]
