# metis-mcp

Registers the Métis MCP server with your client.

## Why this needs two absolute paths

`.mcp.json` ships with `REPLACE:` placeholders rather than a working default,
and that is deliberate — a fabricated path that silently fails to connect would
be worse than one that visibly demands configuration:

- **`command`** must be `metis-server/.venv/bin/python3`, not a bare `python3`.
  The server imports `neo4j`, `mcp` and `yaml`, which live in that virtualenv;
  a system interpreter fails at import.
- **`cwd`** must be the `metis-server` directory. It cannot be derived from
  `${CLAUDE_PLUGIN_ROOT}`, because once this plugin is installed from a
  marketplace it is copied out of the repository and any relative hop back to
  `metis-server` no longer resolves.

## Setup

1. Install the server's dependencies:

   ```bash
   cd /path/to/metis/metis-server
   uv venv
   uv pip install -e .
   ```

2. Replace both `REPLACE:` values in `.mcp.json` with absolute paths — an
   interpreter and a `cwd`. Both are absolute because a client launches the
   server from its own working directory.

3. For the graph-backed tools, set `METIS_NEO4J_PASSWORD` in the server's
   environment (never as an argument — PLT-005). `METIS_NEO4J_URI` and
   `METIS_NEO4J_USER` default to `bolt://localhost:7687` and `neo4j`. There is
   no config file; the v1 `~/.metis/config.json` requirement is gone.

4. Restart your client and confirm the tools are listed. `list_workflows` is
   the cheapest check: it reads the workflow registry and needs no graph.

## The tools

Seven, all read-only:

| Tool | Answers | Needs a graph |
|---|---|---|
| `list_workflows` | What workflows exist, their stages, and where each stops for a human | no |
| `route_request` | Which workflow a request maps to — `null` rather than a guess | no |
| `why_read_only` | Why this surface cannot approve, land or publish (N-8) | no |
| `get_model` | One model's states and transitions as they stand | yes |
| `validate_model` | Well-formedness, split into blocking / unverifiable / advisory | yes |
| `coverage` | The coverage ledger, with the version and commit it refers to (P-16) | yes |
| `run_status` | Where a workflow run got to and what it is waiting for | no |

## Read-only, structurally

**No decision may be taken through this surface (§9.5, N-8).** That is enforced
by composition, not by discipline: every tool calls a query function, and none
imports `review.decisions`, `publishing.publish` or `model_sources.landing`.
Landing, approval and publication go through
`python3 -m metis_mcp.mbt.cli`, where the two gates are.

A tool that cannot reach the graph says so with the variable to set — distinct
from "nothing found", which is a different answer with a different consequence.

See `metis-server/QUICKSTART.md` for the full setup, and the plugin `metis`
for the skills that use these tools.
