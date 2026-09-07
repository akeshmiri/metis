"""Every client format that declares tools must have a way to reach them.

**The gap this closes shipped.** The agent surface carried thirteen agents whose
`tools:` frontmatter named MCP tools — `list_workflows`, `ask`, `get_model` —
and the repository held no MCP configuration Copilot could read. The agents were
correct against the server and the server was wired to one client, so Copilot
loaded thirteen agents declaring thirty-one tools it had no way to call.

`test_agents.py` could not catch it: it asserts an agent's tools exist on the
server, which was true. The missing assertion is one layer out — that the client
reading those agents can also reach that server.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Each client discovers configuration at a path it fixes; none is negotiable.
# Keyed by the wrapper the format uses, because the two disagree: Claude Code
# reads `mcpServers`, VS Code reads `servers`.
CONFIGS = {
    "claude-code": (REPO / ".mcp.json", "mcpServers"),
    "vscode-copilot": (REPO / ".vscode" / "mcp.json", "servers"),
}


def _declared_tools() -> set:
    """Every tool named in an agent's frontmatter.

    Reads `plugins/metis/agents/`, which is now the **only** agent surface. It
    read `.github/agents/` — a byte-identical second copy for Copilot — until
    agents moved to marketplace distribution for both clients, at which point
    scanning the deleted directory would have made this pass over an empty set.
    """
    declared = set()
    for path in (REPO / "plugins" / "metis" / "agents").glob("*.agent.md"):
        frontmatter = path.read_text().split("---")[1]
        declared |= set(re.findall(r"^- ([a-z_]+)", frontmatter, re.M))
    return declared


@pytest.mark.parametrize("client", sorted(CONFIGS))
def test_every_client_has_a_config_that_names_the_server(client):
    path, key = CONFIGS[client]
    assert path.exists(), (
        f"{client} has no MCP configuration at {path.relative_to(REPO)}, so it "
        f"cannot reach the server — while the agent surface declares tools "
        f"that only exist there")

    servers = json.loads(path.read_text()).get(key)
    assert servers, f"{path.relative_to(REPO)} has no {key!r} block"
    assert "metis" in servers, f"{path.relative_to(REPO)} does not define 'metis'"


@pytest.mark.parametrize("client", sorted(CONFIGS))
def test_no_config_needs_a_path_this_machine_alone_has(client):
    """A committed config must work on a clone.

    The plugin's own `.mcp.json` ships `REPLACE:` placeholders deliberately —
    it is copied out of the repository on install, so no relative path survives.
    These two are not: they sit in the repository and resolve from its root.
    """
    path, key = CONFIGS[client]
    server = json.loads(path.read_text())[key]["metis"]
    rendered = json.dumps(server)
    assert "REPLACE" not in rendered, f"{path.relative_to(REPO)} is unconfigured"
    assert "/Users/" not in rendered and "/home/" not in rendered, (
        f"{path.relative_to(REPO)} carries an absolute path from one machine")


def test_both_clients_launch_the_same_server():
    """Two formats, one server. A drift here gives the clients different tools."""
    launched = {}
    for client, (path, key) in CONFIGS.items():
        server = json.loads(path.read_text())[key]["metis"]
        launched[client] = (server["command"], tuple(server["args"]))
    assert len(set(launched.values())) == 1, (
        f"the clients launch different servers: {launched}")


def test_every_tool_an_agent_declares_is_one_the_server_exposes():
    """The assertion that would have caught the gap, stated for this surface."""
    from metis_mcp.agent_generator import exposed_tools

    declared = _declared_tools()
    assert declared, "no tools parsed from the agent surface — the scan is broken"
    missing = declared - set(exposed_tools())
    assert not missing, (
        f"agents declare tools the server does not expose: {sorted(missing)}")


def test_the_vscode_config_is_not_ignored():
    """`.vscode/` is gitignored, and git will not re-include a file whose PARENT
    is excluded — so `.vscode/` plus `!.vscode/mcp.json` silently keeps ignoring
    it. The rule has to exclude the contents instead. This failed once."""
    import subprocess

    result = subprocess.run(
        ["git", "check-ignore", "-v", ".vscode/mcp.json"],
        capture_output=True, text=True, cwd=REPO)
    # A matching NEGATION prints a rule beginning with `!`; a matching exclusion
    # does not. Exit status alone does not distinguish them.
    assert not result.stdout or "!" in result.stdout.split("\t")[0], (
        f"the VS Code MCP config is gitignored, so a clone has no Copilot "
        f"configuration: {result.stdout.strip()}")
