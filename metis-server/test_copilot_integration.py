"""
Copilot discovery-file generation (docs/metis-multi-client-integration.md
§2) -- metis_mcp/copilot_integration.py. No live Copilot instance exists
in this environment (disclosed) -- what's tested here is real: the
generated file is valid YAML frontmatter with exactly the documented
shape and the documented read-only tool set.
"""
import sys
import tempfile
import os

import yaml

from metis_mcp.copilot_integration import (
    generate_agent_file, write_agent_file, COPILOT_READ_ONLY_TOOLS, UNRESOLVED_URL_PLACEHOLDER,
)
from metis_mcp.config_manager import ConfigManager


def _parse_frontmatter(content: str) -> dict:
    assert content.startswith("---\n")
    end = content.index("---\n", 4)
    return yaml.safe_load(content[4:end])


def test_generated_file_is_valid_yaml_frontmatter_with_documented_shape():
    content = generate_agent_file(public_url="https://metis.example.com/mcp")
    fm = _parse_frontmatter(content)
    assert fm["name"] == "spec-aware"
    assert fm["mcp_server"] == "https://metis.example.com/mcp"
    assert fm["auth"] == "oauth2"
    assert fm["tools"] == COPILOT_READ_ONLY_TOOLS


def test_read_only_tool_set_excludes_write_and_undocumented_tools():
    assert "metis_submit_episode" not in COPILOT_READ_ONLY_TOOLS
    assert "metis_propose_test_skeleton" not in COPILOT_READ_ONLY_TOOLS
    assert "metis_quality_score" not in COPILOT_READ_ONLY_TOOLS
    assert len(COPILOT_READ_ONLY_TOOLS) == 6


def test_unresolved_url_falls_back_to_a_visible_placeholder_not_a_guess():
    content = generate_agent_file(public_url=None)
    fm = _parse_frontmatter(content)
    assert fm["mcp_server"] == UNRESOLVED_URL_PLACEHOLDER
    assert "REPLACE" in fm["mcp_server"]


def test_write_agent_file_uses_real_config_manager_resolution():
    config = ConfigManager()  # this project's real .metis/config.yaml
    with tempfile.TemporaryDirectory() as d:
        out_path = os.path.join(d, "spec-aware.agent.md")
        content = write_agent_file(config, out_path)
        with open(out_path, encoding="utf-8") as f:
            written = f.read()
    assert written == content
    fm = _parse_frontmatter(written)
    # This project's config.yaml has no server.public_url set yet (real,
    # current, disclosed state) -- must fall back honestly, not guess.
    assert fm["mcp_server"] == UNRESOLVED_URL_PLACEHOLDER


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
