# Métis — Quickstart

## Install

`uv` is the supported route.

```bash
cd metis-server
uv venv
uv pip install -e ".[test]"
```

`uv venv` creates `.venv/` in the usual place, so `.venv/bin/python3` still works
wherever an absolute interpreter path is needed.

## Verify it before trusting it

```bash
uv run python -m pytest -q
```

78 test files — **no Neo4j, no model calls, no config file.** The engine is
deliberately database-free: models, criteria, path generation, coverage and
validation are all pure. If this does not pass, stop here.

One caveat on that command: 136 of those tests DO need Joern and a JDK, and
`conftest.py` fails rather than skips without them, deliberately — they are the
only behavioural test the query packs have. Run `metis doctor` first. To exercise
just the engine-free half, see the `--ignore` list in `CLAUDE.md`.

```bash
uv run python -m metis_mcp.mbt.cli workflow list
```

Five workflows, their ordered stages, and where each stops for a human.

## The graph, when you need one

Only landing, loading and reporting against a live graph need Neo4j.

```bash
docker run -d --name metis-graph -p 7687:7687 -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/<password> neo4j:5.26-community

export METIS_NEO4J_URI=bolt://localhost:7687     # optional; this is the default
export METIS_NEO4J_USER=neo4j                    # optional; this is the default
export METIS_NEO4J_PASSWORD=<password>           # required, and only from the environment
```

**The password is never read from an argument** (PLT-005), so it cannot reach
shell history or a process listing.

The environment is not the only source. There is one config file —
`~/.metis/config.json` — or one override, `METIS_CONFIG_PATH`, which when set is
the *only* candidate considered. It supplies `graph.neo4j.uri`/`user` and a
`password_env` naming the variable that holds the secret; the secret itself
never lives in the file. What went with the v1 engine is the *requirement* to
have one, and the project-local `.metis/config.*` that used to be tried first —
a per-repository override of a machine's connection makes "which database did
that write go to" unanswerable from the command alone. A project-local file is
reported rather than silently skipped, so it cannot go quiet on you.

Apply the schema — which is **generated** from `metis_mcp/ontology/labels.py`,
not hand-written:

```bash
uv run python -c "from metis_mcp.ontology import schema; schema.write('schema')"
```

Then run `schema/metis2-01-constraints.cypher` and `metis2-02-relationships.cypher`
against the database.

**Community only** (C1). There is no Enterprise variant: property-existence
constraints are an Enterprise feature, and generating a second schema that used
them meant two DDLs could disagree about what the database enforces — leaving
`metis_mcp/ontology/validation.py` load-bearing on one and redundant on the
other. It is the enforcement everywhere, and the generated DDL names it on each
constraint it does not create. The schema applies unchanged to an Enterprise
instance; it simply does not rely on being one.

## Connect an MCP client

`plugins/metis-mcp/.mcp.json` ships two `REPLACE:` placeholders — an absolute
interpreter path and an absolute `cwd`. Both are required, and both are absolute
on purpose: a client launches the server from its own working directory.

The surface is **nineteen read-only tools**, five of them the authoring
surface (X-6e). `list_workflows` is the cheapest check
that it is wired up: it reads the workflow registry and needs no graph.

## A first real run

```bash
# Is a state machine well-formed? Blocking / unverifiable / advisory, kept apart.
uv run python -m metis_mcp.mbt.cli validate --journey <journey> --surface api

# Coverage, always with the criterion and the version it refers to (P-4, P-16).
uv run python -m metis_mcp.mbt.cli report --journey <journey> --surface api

# Capture a stated requirement as atomic criteria, then compare it to the model.
uv run python -m metis_mcp.mbt.cli knowledge check <knowledge.json>
uv run python -m metis_mcp.mbt.cli knowledge compare <knowledge.json> --journey <j>

# The reviewer's screens (loopback only; this server does not authenticate).
uv run python -m metis_mcp.mbt.cli ui --journey <journey> --surface api
```

A workflow run exits `0` complete, **`5` blocked on a human decision — not a
failure**, anything else failed.

## What is genuinely still open

- No `Component` nodes exist in the live graph, so coverage honestly reports
  "version not recorded (P-16)" until `persist` has run.
- Intake creates a `Requirement` only from EARS-conformant text. `metis intake
  land` carries a UIF into the graph as an `Episode` plus a `<Source>Item`
  anchor; free prose — most Jira titles — lands as a `Finding` pointing at
  `knowledge-capture` instead, because `ears_pattern` has no empty form and
  guessing one is what `ac_mining` refuses to do (S-13).
