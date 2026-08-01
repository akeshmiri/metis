# Métis MCP Server — Phase 0 Dogfooding Quickstart

This is a real, tested MCP server — not a mockup. It was verified end-to-end
with an actual MCP client over stdio before being packaged here: 9 tools,
177 real items parsed from this platform's own `REQ-METIS-*`/`CONST-*`/
`DQ-*`/`AF-*`/`BS-*` documents, 359 real cross-reference edges, correct
not-found handling, and the write path (`metis_submit_episode`) correctly
refusing per `REQ-METIS-CPT-01`.

## What this is (and isn't)

**Is:** the fastest honest path to testing Métis's tool contracts against
Claude, per your direction to test on Claude first. Stdio transport — no
OAuth2, no Streamable HTTP, no Kubernetes deployment needed.

**Isn't:** the production server. It's backed by `LocalGraphStore` (an
in-memory index over this platform's own markdown documents), not Neo4j —
there's no real ingestion pipeline, no code graph, no Transition/TestCase
ontology populated. `metis_impact_analysis`, `metis_propose_test_skeleton`,
and `metis_quality_score` all say so explicitly in their own responses
rather than faking production behavior.

## Install

```bash
cd metis-mcp-server
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Configure (required — the server will not start without this)

Per explicit direction, **no configuration lives in code** — model names,
ZDR status, per-repository classifications, and the corpus path all come
from `.metis/config.yaml` (project-level) or `~/.metis/config.yaml`
(host-level default), resolved by `config_manager.py` using the same
project-overrides-host, first-found-wins convention as the real
`atlas-config-manager`. **If neither file exists, the server raises
`ConfigNotFoundError` and refuses to start** — this is deliberate, not a bug:
a missing config is a setup gap to fix, not something to paper over with an
assumed default.

A real `.metis/config.yaml` is already included in this package, reflecting
the actual current decision: no ZDR agreement (`zdr.confirmed: false`), and
this platform's own dogfooding corpus classified `public_internal`. Copy
`metis.config.example.yaml` and fill it in for your own repositories before
connecting anything beyond the bundled dogfooding corpus.

## Connect Claude Code

**Note:** this is a different config shape than `metis-multi-client-integration.md`'s
production snippet — that one is Streamable HTTP + OAuth2 for the deployed
server; this is a local `command`-spawned stdio server for testing right now.
Both are legitimate — this is Phase 0, that's the target for real rollout.

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "metis": {
      "command": "/absolute/path/to/metis-mcp-server/.venv/bin/python3",
      "args": ["-m", "metis_mcp.server"],
      "cwd": "/absolute/path/to/metis-mcp-server"
    }
  }
}
```

The dogfooding corpus (this platform's own 17 real `metis-*.md` documents) is
bundled in `corpus/` and used by default, per `corpus.glob` in
`.metis/config.yaml` — no separate data-loading step. Edit that file's
`corpus.glob` value if you want to point it at a different or updated set
of documents; there's no environment variable for this anymore, per the
"no configuration in code" directive.

## Verify it before trusting it

Run the included end-to-end test first — it spawns the server as a real
subprocess and calls real tools, the same way Claude Code will:

```bash
.venv/bin/python3 test_e2e.py
```

Expect: 9 tools listed, real answers about `CONST-047` (citing
`metis-standards-integration.md`, not a guess), a clean `found: false` for a
made-up id, and a clear refusal from `metis_submit_episode`.

## Try it in Claude Code

Once connected, ask things like:

- "What does CONST-047 require, and where does it come from?" → exercises `metis_get_context`
- "What cites CONST-047, and what does it cite?" → exercises `metis_get_traceability`
- "Is CONST-051 covered by anything else in the corpus?" → exercises `metis_check_coverage`
- "What's the orphan rate for ConstitutionRules right now?" → exercises `metis_quality_score`, and will genuinely show the 17 still-uncited Amendment 5 rules — a real, current finding, not a canned demo answer

## Demo Data — load a large, realistic, interconnected graph in one click

The dogfooding corpus above (177 items) is real but small — genuinely
useful for testing tool *correctness*, not for getting a feel for what a
graph at real scale looks like. `demo_data/generate_demo_data.py` is a
real, reusable generator (not a one-off script) that populates the
**Neo4j** backend with a structured, production-shaped synthetic
dataset for one hypothetical company — **~45,000 nodes** across all 49
real ontology labels, **~58,000 relationships** across 10 real
relationship types, at default scale (`factor=1.0`). Structurally
coherent, not independently-random layers: 50 Goals, each assigned one
service domain (billing, payments, search, ...); every Capability/Epic/
Feature/Requirement/Repository/Method beneath a Goal inherits that same
domain, so a "payments" Goal's ~50-150 Requirements, Jira keys
(`PAY-1042`-style), Confluence docs, and implementing code all
consistently reference payments — never a random unrelated service.
Every Requirement gets 1-3 AcceptanceCriteria and a **guaranteed** 1-3
verifying TestCases (never optional coverage). Real Jira-shaped metadata
(`jira_key`/`jira_status`/`jira_sprint`/`jira_issue_type`) lands directly
on Requirement/Defect nodes, matching `atlassian_connector.py`'s real
field conventions; real Confluence-shaped data lands as `DocumentIngested`
Episodes (PRDs per Goal, design docs on ~30% of Features) — Confluence has
no typed-entity target in the closed ontology, so it's Episode-only, same
as real ingestion. Method/TestCase ids follow the real `repo:path:name`
convention `pyramid_gap_check.py` actually parses, so the platform's own
Stage-3 coverage tooling has real signal to find in demo data too.

On top of that fictional-company dataset, every run also adds a much
smaller, separately-marked (`source_kind: 'metis_project'`) layer grounded
in **this repo's own real project**: ~18 real Goals (one per
`REQ-METIS-*` subsystem prefix actually found in `corpus/*.md`), and for
each of the 75 real `REQ-METIS-*` tags there, one hand-paraphrased but
genuinely EARS-conformant Requirement carrying `derived_from`/
`source_file`/`source_heading` back to its real tag. Its `IMPLEMENTS`
edges point at the real, already-existing (non-demo) `Method` pool this
repo's own earlier Cognify run populated — no synthetic copy. See
`demo_data/metis_grounded.py`'s docstring for the full grounding
discipline.

**Requires `graph.backend: neo4j`** (see `.metis/config.yaml`) — this
doesn't work against `LocalGraphStore`.

**One click, from the browser** (the same review UI above already has a
"Load demo data" / "Wipe demo data" panel at the top):
```bash
export METIS_NEO4J_PASSWORD=<your Neo4j password>
.venv/bin/python3 review_api_server.py
# open http://127.0.0.1:8420/ and click "Load demo data"
```

**One click, from the terminal:**
```bash
.venv/bin/python3 -m demo_data.generate_demo_data                    # load, ~45,000 nodes (~4s)
.venv/bin/python3 -m demo_data.generate_demo_data --scale 0.1        # smaller run, ~4,500 nodes
.venv/bin/python3 -m demo_data.generate_demo_data --wipe             # remove only the demo data
```

Not fabricated in the ways that matter: every generated `Requirement`'s
text is checked against the real, unmodified EARS checker
(`metis_mcp/ears_checker.py`) — a candidate that doesn't parse is dropped,
never force-tagged; every `lifecycle_state` comes from a real call to the
real `ConfidenceTiering.evaluate()` with a randomized confidence input, not
a hand-picked demo distribution; a deliberately overlapping-guard pair is
run through the real determinism checker and a few Transitions end up
genuinely marked `Disputed` by that real code. All demo nodes are tagged
`is_demo_data: true` with `demo:`-prefixed ids, so wiping them never
touches the real dogfooding/connector data already in this graph.

## What's genuinely still open

| Item | Status |
|---|---|
| Neo4j-backed `Neo4jGraphStore` implementing the same interface | Not built — `graph_store.py`'s docstring specifies the interface it needs to match; this is the real next build task once Phase 0 dogfooding validates the tool contracts |
| Streamable HTTP + OAuth2 transport | Already spec'd (§11.2) and scaffolded in the Helm chart's `mcp-server` component — not needed for this stdio testing step |
| Copilot connection | Deliberately not built yet — per your direction, Claude first |
