"""
Copilot connection (docs/metis-multi-client-integration.md §2) -- built
now per explicit user direction ("yes, build it now"), config-only: no
real GitHub Copilot instance exists in this environment to connect
against and verify live, same disclosed limitation as every other
environment-blocked item in this project (no ANTHROPIC_API_KEY originally,
no git repo, no embedding model). What IS real here: the actual discovery
artifact Copilot's Agent mode reads (a `spec-aware.agent.md` file with
YAML frontmatter), generated from this project's real, resolved config
rather than hand-typed with unresolved placeholders baked in -- REQ-METIS-
CPT-04's "reachable only in Copilot Agent mode" constraint is Copilot's
own, not something this generator can satisfy or fake.

§0's core design point carries through unchanged: Copilot uses the exact
same Streamable HTTP + OAuth2 mcp-server component Claude does (§11.2) --
this module produces Copilot's client-side discovery convention only, not
a second server or a different permission model.
"""
import yaml

# The doc's own explicit read-only set (§1's metis:read scope, §2's tool
# list) -- Copilot's agent file gets exactly this set, never the write tool
# (metis_submit_episode) or the two tools the doc doesn't name for Copilot
# (metis_propose_test_skeleton, metis_quality_score) -- matching what's
# actually documented as the Copilot-facing contract, not the full 9.
COPILOT_READ_ONLY_TOOLS = [
    "metis_get_context", "metis_get_traceability", "metis_check_coverage",
    "metis_impact_analysis", "metis_explain_decision", "metis_explain_answer",
]

UNRESOLVED_URL_PLACEHOLDER = "https://REPLACE-metis-host.example.com/mcp"


def generate_agent_file(public_url: str | None, name: str = "spec-aware") -> str:
    """Real YAML-frontmatter markdown generation -- not a static template
    with a hand-typed placeholder. `public_url=None` (the honest default
    until a real hostname/OAuth2 provider is chosen, per that doc's own
    §4 'genuinely still open' item) falls back to the same disclosed
    REPLACE-shaped placeholder the doc already uses, so the generated file
    is never silently wrong-looking -- it's visibly a placeholder, the
    same way it would be if a human had typed it by hand."""
    frontmatter = {
        "name": name,
        "tools": COPILOT_READ_ONLY_TOOLS,
        "mcp_server": public_url or UNRESOLVED_URL_PLACEHOLDER,
        "auth": "oauth2",
    }
    yaml_block = yaml.dump(frontmatter, sort_keys=False, default_flow_style=False).strip()
    return f"---\n{yaml_block}\n---\n"


def write_agent_file(config, output_path: str) -> str:
    """`config`: a ConfigManager instance -- resolves the real public_url
    if one has been set (get_server_public_url()), never guesses one."""
    content = generate_agent_file(config.get_server_public_url())
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content
