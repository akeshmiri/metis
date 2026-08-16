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
   python3 -m venv .venv
   .venv/bin/pip install -e .
   ```

2. Create `~/.metis/config.json` — the server **refuses to start** without it,
   by design. Copy `metis-server/metis.config.example.json` and fill it in.

3. Replace both `REPLACE:` values in `.mcp.json` with absolute paths.

4. Restart your client and confirm the tools are listed. `metis_list_skills`
   is the cheapest check: it needs no graph backend.

## Backend note

Most tools require `graph.backend: neo4j`. Against the bundled dogfooding
corpus (`graph.backend: local`) the graph-dependent tools return an `adapted`
response explaining what is unavailable rather than failing — that is the
documented behaviour, not an error.

See `metis-server/QUICKSTART.md` for the full setup, and the plugin `metis`
for the skills that use these tools.
