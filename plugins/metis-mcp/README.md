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

**Deliberately not listed here.** This section used to carry a hand-written
table of twelve, and the server had grown to thirty-one — nineteen missing,
including the whole authoring surface. That is the same defect
`test_no_manifest_names_a_tool_the_server_does_not_expose` was written against,
whose docstring says it plainly: *naming them at all is the problem; naming ones
that do not exist is the symptom.* The manifest was fixed and this file, which is
what somebody installing the plugin actually reads first, was not.

`docs/guide/mcp-tools.md` has the current list. It is **generated** from
`server.py` and `metis guide --check` fails on a diff, so it cannot drift the way
this section did.

What the surface is for, which does not change when a tool is added: read a model
and validate it; coverage and what could not be measured; traceability and where
the chain breaks; the cases a model would generate; what a change puts at risk;
specifications, requirements and the knowledge in the graph; and an authoring
surface that states the accepted space rather than a value (X-6e).

`list_workflows` is the cheapest thing to call first — it reads the workflow
registry and needs no graph.

## Skills, as prompts

**This section used to say there were none, and that was true until it wasn't.**
The split was real: this plugin registered the tools, the `metis` plugin
held the skills, and neither declared the other — so installing one gave
you tools with no procedure, and installing the other gave you skills naming
tools that were not there.

MCP has the primitives to close that, and they line up with the placement rule
(`docs/academy/10-where-a-thing-belongs.md`) rather than against it:

| Primitive | Holds | Which is |
|---|---|---|
| **tool** | a question with a determinate answer the engine computes | 34 of them |
| **prompt** | the procedure, its order, its gates, its refusals | the 39 skills |
| **resource** | a document somebody wrote, addressed by URI | 97 of them |

The rule is about **layers, not transports**. A skill delivered as a prompt is
still a skill — prose telling a model what to do where the answer is not
determinate. Nothing became a tool in the move, and nothing here computes.

**Progressive disclosure survives, which was the risk.** A prompt carries
`SKILL.md` and nothing else. Every step, knowledge fragment and reference is a
separate resource, fetched when a step cites it — the same discipline the folder
tree encodes, in a protocol that has a word for it. `test_library.py` asserts a
step's body is not inlined into its prompt.

Addressed as `metis://skill/<name>`, `metis://skill/<name>/steps/<step>`,
`metis://guide/<page>`, `metis://academy/<lesson>`, `metis://spec`.

**Prompts and resources need the repository on disk.** They are discovered from
`plugins/metis/skills/` and `docs/`, neither of which travels with the Python
distribution. A server installed without the repository beside it serves the
tools and no documents, and `describe_library` says so rather than presenting an
empty library as a complete one.

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
