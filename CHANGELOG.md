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
- **A read-only agent surface.** Seven MCP tools, none importing a write path
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

### Packaging

- `pyproject.toml` declared ten dependencies; seven had no importer anywhere in
  the tree and are gone. The wheel shipped four modules and none of the twelve
  subpackages, because `packages` was a literal list — it is now a recursive
  find, and CI builds, installs and resolves the console script so this cannot
  regress unseen.
- The three Dockerfiles and Helm components that referenced directories the
  rebuild deleted have been removed.
