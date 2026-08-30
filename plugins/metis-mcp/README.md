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

3. For the graph-backed tools, the connection resolves in this order:
   explicit arguments, then `METIS_NEO4J_URI` / `_USER` / `_PASSWORD`, then a
   JSON config file — `METIS_CONFIG_PATH` if set, otherwise
   `.metis/config.json` then `~/.metis/config.json`. First found wins; there is
   no merge. A password is never an argument (PLT-005): in a config file, name
   the variable with `graph.neo4j.password_env` and keep the secret in the
   environment. A literal `graph.neo4j.password` is read too, but only from a
   file the owner alone can read, and the run says so on stderr.

4. Restart your client and confirm the tools are listed. `list_workflows` is
   the cheapest check: it reads the workflow registry and needs no graph.

## The tools

Twelve, all read-only:

| Tool | Answers | Needs a graph |
|---|---|---|
| `list_workflows` | What workflows exist, their stages, and where each stops for a human | no |
| `route_request` | Which workflow a request maps to — `null` rather than a guess | no |
| `why_read_only` | Why this surface cannot approve, land or publish (N-8) | no |
| `get_model` | One model's states and transitions as they stand | yes |
| `validate_model` | Well-formedness, split into blocking / unverifiable / advisory | yes |
| `coverage` | The coverage ledger, with the version and commit it refers to (P-16) | yes |
| `run_status` | Where a workflow run got to and what it is waiting for | no |
| `search_knowledge` | Entities, requirements and criteria matching a term, grouped by which matched | yes |
| `list_entities` | Every business noun Métis knows, optionally within one area | yes |
| `get_entity` | One entity: what it is, what acting on it changes, and the criteria that touch it | yes |
| `get_requirement` | One requirement, its criteria, and the artefact it came from | yes |
| `get_spec` | The stored stakeholder specification for one journey | yes |

## Transport

`stdio` by default, which is what a local client launches. Set
`METIS_MCP_TRANSPORT` to `streamable-http` or `sse` for a networked server, with
`METIS_HTTP_HOST` (default `127.0.0.1`) and `METIS_HTTP_PORT` (default `8090`).
An unrecognised value halts rather than falling back to stdio — a container that
"starts fine" and is unreachable is the failure that behaviour causes.

Read-only is not the same as safe to expose. These tools cannot approve or
publish, but they will read out every requirement, criterion and specification
in the graph to whoever reaches them, and there is no authentication here. A
non-loopback bind is warned about; publish the port on loopback unless something
authenticating sits in front.

## Read-only, structurally

**No decision may be taken through this surface (§9.5, N-8).** That is enforced
by composition, not by discipline: every tool calls a query function, and none
imports `review.decisions`, `publishing.publish` or `model_sources.landing`.
Landing, approval and publication go through
`metis`, where the two gates are.

A tool that cannot reach the graph says so with the variable to set — distinct
from "nothing found", which is a different answer with a different consequence.

See `metis-server/QUICKSTART.md` for the full setup, and the plugin `metis`
for the skills that use these tools.
