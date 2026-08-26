# Métis Helm Chart

Deploys Métis's own infrastructure: the MCP server (client-agnostic — Claude and
GitHub Copilot both connect the same way, see `metis-multi-client-integration.md`),
the ingestion worker (extraction against an already-populated source
database, catalogue only), the guardrail-corpus CI/replay
job (`CONST-057`/`058`), and Neo4j (Community for Phase 0, Enterprise once
budgeted — see the master spec's risk register, §15).

**Deliberately not in this chart:** Postgres (the episode log lives in Neo4j —
single-database decision) and Grafana (guardrail/DQ metrics are new panels on
an already-running Grafana) — both would be
redundant infrastructure, not missing infrastructure.

## Structure

Follows a conventional orchestration chart layout: one chart, a
`components:` map in `values.yaml`, shared Deployment/Service/CronJob
templates driven from that map (`templates/_objects.tpl`, `component.yaml`)
rather than one hand-written manifest per component.

## Prerequisites

- Helm 3.x, a Kubernetes cluster with a `StorageClass` for Neo4j's PVC
- Network connectivity from this cluster to the source Postgres instance
- An Anthropic API key
- A Zero Data Retention agreement confirmed before ingesting any
  `Confidential`-tier repository. **This is an organisational prerequisite, not
  an enforced one**: `zdr.confirmed` and the `repositories` classifications in
  `files/metis-config.yaml` are read by nothing in this build, and the
  `CONST-051`–`053` rules they cite are v1 constitution rules that the current
  specification does not carry. Nothing blocks an unclassified repository.

## Install

The chart renders a complete deployment `config.json` Secret from the install
values. The MCP server and ingestion worker read it through
`METIS_CONFIG_PATH`; they do not consume `NEO4J_URI`, `NEO4J_PASSWORD`, or
`METIS_NEO4J_*` runtime variables. Local MCP and Atlas usage are separate and
read `~/.metis/config.json`.

```bash
# Add the real Neo4j chart repo (dependency)
helm repo add neo4j https://helm.neo4j.com/neo4j
helm dependency update

# Phase 0 / sandbox
helm install metis . -f values.yaml -f values-sbx.yaml \
  --set-string secrets.sourceDbPassword="$METIS_SOURCE_DB_PASSWORD" \
  --set-string secrets.neo4jPassword="$DEPLOYMENT_NEO4J_PASSWORD" \
  --set-string secrets.anthropicApiKey="$ANTHROPIC_API_KEY" \
  --set-string secrets.oauthClientSecret="$OAUTH_CLIENT_SECRET"

# Production (once Neo4j Enterprise licensing is budgeted, §15)
helm install metis . -f values.yaml \
  --set neo4j.edition=enterprise \
  --set neo4j.acceptLicenseAgreement=yes \
  --set-string secrets.sourceDbPassword="$METIS_SOURCE_DB_PASSWORD" \
  --set-string secrets.neo4jPassword="$DEPLOYMENT_NEO4J_PASSWORD" \
  --set-string secrets.anthropicApiKey="$ANTHROPIC_API_KEY" \
  --set-string secrets.oauthClientSecret="$OAUTH_CLIENT_SECRET"
```

## What's genuinely still open

- **Every `REPLACE` placeholder in `values.yaml`/`Chart.yaml`** — registry, image
  repository, ingress host, storage class, and the pinned Neo4j chart version —
  none of these are guessable from outside your actual infrastructure.
- **Deployment publication remains external.** The four local images now build
  successfully with Podman at `0.1.0`:
  `metis-mcp-server`, `metis-ingestion-worker`,
  `metis-guardrail-corpus-runner`, and `metis-graph-sync`. They still need to be
  pushed to the real registry and wired to the real registry/repository values.
- **Chart validation is green locally.** `helm lint .` and
  `helm template metis .` both pass; the rendered manifest was checked before
  this release record was updated. A real cluster install remains an external
  deployment gate.

The local image build pattern is:

```bash
cd metis-server
podman build -f Dockerfile.mcp-server -t metis-mcp-server:0.1.0 .
podman build -f Dockerfile.ingestion-worker -t metis-ingestion-worker:0.1.0 .
podman build -f Dockerfile.guardrail-corpus-runner -t metis-guardrail-corpus-runner:0.1.0 .
podman build -f Dockerfile.graph-sync -t metis-graph-sync:0.1.0 .
```
