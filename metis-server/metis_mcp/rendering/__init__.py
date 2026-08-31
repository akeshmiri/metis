"""Test-case rendering (application spec §7).

**Rendering produces prose, not code.** The `generators/` package emitted REST
Assured and Playwright sources and `payload.py` built the machine-readable
runner payload they were assembled from; both are gone. Métis states what must
be verified and whether it is covered — producing the implementation is the job
of whatever executes the test.
"""
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
    "TestCase", "Step", "RenderResult", "render", "render_path", "format_case",
    "humanise",
    "TIER_ACCEPTANCE_CRITERION", "TIER_GENERATED_PROSE", "TIER_VERBATIM",
]
