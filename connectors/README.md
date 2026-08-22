# Connector manifests

**Nothing reads these.** Seven manifests and the JSON Schema they validate
against, describing sources Métis was designed to ingest from. There is no
loader, no registry lookup, and no code path in `metis-server/` that opens this
directory.

They are kept because the design is real and the schema is a genuine contract —
not because the capability exists. This is the same category as UIF → Episode,
and it is stated here for the same reason: a directory of plausible
configuration implies a feature, and finding out by running it is worse than
being told.

## What is here

| Manifest | Protocol |
|---|---|
| `metis-connector-application-code.json` | `athena_internal_read` |
| `metis-connector-flatfiles.json` | `file_scan` |
| `metis-connector-atlassian-prod.json` · `-grafana` · `-bmad-method` · `-locust-performance` · `-test-suite` | `mcp_client` |
| `metis-connector-manifest-schema.json` | the JSON Schema all of the above validate against |

`metis-connector-manifest-schema.json` is the contract a reader would have to
satisfy. It is the useful artefact in this directory.

## What would have to exist

A loader that globs this directory, validates each manifest against the schema,
and dispatches on `protocol` — then a source registered in
`metis_mcp/model_sources/sources.py` so a connector's output lands like any
other source: as candidates at `Quarantine`, never `Approved` (S-4).

`docs/historical/design-notes-v1/metis-connector-architecture.md` is the design. Two things it describes
were removed with the v1 engine and would need rebuilding rather than wiring:
the ingestion worker that polled these on a schedule, and the Kubernetes
ConfigMap that mounted them.

## What used to be here

`bmad_method_connector.py` and `mock_athena_schema.sql` were deleted with the v1
engine. References to both survived in
`metis-server/test_fixtures/bmad/` and `metis-server/.metis/config.yaml` and
have been corrected.
