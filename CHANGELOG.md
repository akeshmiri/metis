# Changelog

## 0.1.0 — unreleased

The first release. The engine was rebuilt from scratch for it; anything
describing the previous one lives in [`docs/historical/`](docs/historical/) and
describes nothing current.

### The engine

- **Behaviour recovery from code.** A Joern code property graph becomes states
  and transitions through a normalised contract — no engine type reaches the
  graph.
- **A closed ontology, and a schema generated from it.**
  `metis_mcp/ontology/labels.py` is the single source for the label set, the
  relationship catalogue, and the deliberately-excluded labels each with the
  trigger that would bring it back. The Cypher schema is generated from it, so
  the two cannot drift.
- **Two gates, and only two.** G1 before anything is generated, G2 before any
  external write. Nothing auto-approves and nothing auto-promotes on elapsed
  time. Every source lands at `Quarantine`; generation reads only `Approved`.
- **A read-only agent surface.** Nineteen MCP tools, none importing a write path
  (N-8). Landing, approval and publication go through the gated CLI.
- **Database-free by construction.** Models, criteria, path generation,
  coverage and validation are pure. The whole suite runs with no Neo4j.

### Known limitations

Named here rather than discovered on contact.

- **Intake lands, but does not invent.** All six sources produce a Unified
  Intake Format document, and `intake land` carries it into the graph as an
  `Episode` (the ingestion run) plus one `<Source>Item` anchor (the artefact —
  a Jira issue, a Confluence page, an OpenAPI document). Two things it
  deliberately will not do: a UIF's *claimed* acceptance criteria never become
  `AcceptanceCriterion` nodes, because an upstream extractor's labelling is not
  evidence; and free prose never becomes a `Requirement`, because
  `ears_pattern` has no empty form and inventing one produces a well-formed
  statement nobody wrote. Non-conformant text lands as a `Finding` naming what
  has to happen next.
- **Component-level vs system-level acceptance criteria.** An OpenAPI document
  gives the component level mechanically. The system level needs the
  preconditions that produce a given set of parameters, and those are not
  derivable from a contract. Not designed yet.
- **Publication is dry-run only.** `DryRunTransport` is the only transport
  registered in this release (T-21/C3). The `test-generate` workflow's `publish`
  stage builds the real payload, validates it, and makes no network call — so
  nothing reaches Zephyr, Jira or anywhere else. G2 still gates it, because the
  gate is what a real transport will sit behind unchanged.
- **Coverage answers one question.** *Is this behaviour tested?* — never *is it
  working?* (C-11). No execution result is ingested, so none is reported.
- **The review UI trusts its identity header** and binds loopback. That is
  honest for a localhost review tool and unacceptable for anything else.
- **Connector manifests have no reader.** `connectors/` holds seven manifests
  and the JSON Schema they validate against, describing sources Métis was
  designed to ingest from. No loader exists in this build. The schema is a real
  contract; the capability is not there yet — see `connectors/README.md`.
- **Repository classification and ZDR are declarations, not gates.** The
  `zdr` and `repositories` blocks in the shipped configuration record a policy
  decision and nothing reads them. The `CONST-051`–`053` rules they cited are v1
  constitution rules the current specification does not carry, and no module
  implements the fail-closed blocking the comments described. The comments now
  say so; the control still has to be built before the claim can be made.
- **Project-level `.metis/config.*` is not read.** There is one default,
  `~/.metis/config.json`, or one override, `METIS_CONFIG_PATH`, which when set is
  the only candidate — a per-repository override of a machine's connection makes
  "which database did that write go to" unanswerable from the command alone. A
  project-local file is *reported* rather than silently skipped, and the checked-in
  `metis-server/.metis/config.yaml` is a record, not a live setting.

### Packaging

- `pyproject.toml` declared ten dependencies; seven had no importer anywhere in
  the tree and are gone. The wheel shipped four modules and none of the twelve
  subpackages, because `packages` was a literal list — it is now a recursive
  find, and CI builds, installs and resolves the console script so this cannot
  regress unseen.
- The three Dockerfiles and Helm components that referenced directories the
  rebuild deleted have been removed.
- **Settings that nothing read have been removed from every shipped config.**
  `graph.backend` selected between the v1 LocalGraphStore and Neo4jGraphStore
  and offered a `local | neo4j` choice where one path exists;
  `token_optimization.headroom_enabled` configured a module three deleted tools
  used. `test_independence.py` now asserts no config file offers either, across
  all five files rather than the one that carried the old `atlas` block.
- **The last back-compat path in cross-surface analysis is gone.** An unhandled
  outcome is a direct `TRIGGERS` query. The same-trigger heuristic kept as a
  fallback for journeys predating the `INVOKES`/`TRIGGERS` split reported
  findings derived from the very conflation `TRIGGERS` exists to remove, without
  saying so; re-extraction is the fix for an old journey.

### The rebuild, which had never completed

`rebuild_graph.sh` reached its own last stage for the first time. Five defects,
each of which hid the next:

- **A correct refusal was fatal.** `records-page` mutates through signatures
  computed at run time, so `js-ui` recovers the handlers and refuses to name an
  observable outcome (§5.8). Under `set -e` that killed the run at stage 3b, so
  the login model, the acceptance criteria and the cross-surface proposals never
  ran. It is reported and non-fatal now, and the refusal itself is a condition in
  `test_extraction.py` so it cannot be "fixed" into a guess.
- **The whole intent side was refused at the gate.** `land_spec_criteria.py`
  hand-builds its rows and never set `search_text`, `valid_from` or `valid_to`,
  so all 24 `AcceptanceCriterion` writes were rejected and the demo graph had no
  criteria at all — the half a recovered model is meant to be compared against.
  Now covered by `test_spec_criteria_landing.py`, which reuses `ontology.validate`
  rather than naming the three properties, so a fourth cannot slip through.
- **Cross-surface proposals raised `TypeError` on two constructors** — `LinkSet`
  without `journey`, `InvokesLink` without `proposed_by` and with a string where
  a dict belongs. The stage had never once executed.
- **The join key could not match.** It compared a screen name against a
  transition id, which is an opaque namespaced hash — so the stage reported a
  confident `0 INVOKES`, which reads as "these surfaces share nothing" rather
  than "my join matched nothing". `triggers` was also never populated, so
  `persist_triggers` wrote zero while the caller printed it as a count.
- **The derivation now lives in `mbt/link_proposals.py`**, pure and tested
  (`test_link_proposals.py`). It returns its misses instead of folding them into
  a zero, so an unmatched screen is distinguishable from an unmatched endpoint.

### The academy is landed

`docs/academy/` — eight lessons — lands as `:Lesson` at stage 4b of the rebuild,
into the **same** graph as the product facts. Neo4j cannot join across databases
in one session, so a separate academy database would put the lessons where
`search_knowledge` could never see them beside a criterion; separation is by
label and episode instead. A single `/search?q=archive` now returns both an
`AcceptanceCriterion` and a `Lesson`.

Measured rather than asserted: `metis retrieval-bench` over the academy scores
**10/15 top-1, 14/15 top-3, 0/15 absent** on keyword alone. Nothing is
unreachable; ranking is the gap, and it is the case `--hybrid` exists for. The
expected answers were written from the content before any search was run.

**And a miss is now recordable, not just printable.** `retrieval-bench --land`
writes each miss as an advisory `Finding` `ABOUT` the node that should have won —
`retrieval_rank` where it was reached but out-ranked, `retrieval_absent` where it
was not reached at all, kept apart for the reason `score` keeps them apart. This
closes the loop the academy was landed for: a lesson that reads badly through
`ask` becomes a finding about the *tools*, rather than living in whoever last ran
the command.

Two properties of it worth stating. The episode id is content-derived, so
re-running after no change is a no-op rather than a second record of one
measurement. And the remedy says explicitly that the fix is **not** to edit the
material to contain the query's words — prose written to satisfy a search stops
being readable by people, and would leave the benchmark grading text written to
please it. No ontology change: `Finding` already exists and `ABOUT` already
targets any label.

### Configuration

- **`~/.metis/config.json` is the one config file**, or `METIS_CONFIG_PATH` when
  set, which is then the *only* candidate. Project-local `.metis/config.*` is
  reported rather than read. `QUICKSTART.md` had claimed there was no config file
  at all, and `metis-server/.metis/config.yaml`'s own header claimed it overrode
  the host — both the reverse of what `config_paths` does.
- **`rebuild_graph.sh` no longer demands the password in the environment.** It
  had a bare `:?` guard, so moving the secret into the config file — the
  arrangement the tool recommends — broke the rebuild while `metis` kept working.
  It asks `graph_session.resolve()` now: one resolver, not two.
- **Three `test_api.py` tests were passing by accident.** They delete
  `METIS_NEO4J_PASSWORD` and expect a 204, which only means "no graph" if the
  environment is the only password source. With a config file present `resolve()`
  succeeded and answered 200. They now neutralise ambient configuration the way
  `test_graph_session.py` already did.
