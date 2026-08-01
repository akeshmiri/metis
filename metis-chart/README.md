# Métis Helm Chart

Deploys Métis's own infrastructure: the MCP server (client-agnostic — Claude and
GitHub Copilot both connect the same way, see `metis-multi-client-integration.md`),
the ingestion worker (Cognify extraction against Athena's already-populated
tables, per the `athena_internal_read` protocol), the guardrail-corpus CI/replay
job (`CONST-057`/`058`), and Neo4j (Community for Phase 0, Enterprise once
budgeted — see the master spec's risk register, §15).

**Deliberately not in this chart:** Postgres (the episode log lives in Neo4j —
single-database decision) and Grafana (guardrail/DQ metrics are new panels on
Athena's already-running Grafana, §12.4 of the master spec) — both would be
redundant infrastructure, not missing infrastructure.

## Structure

Follows Athena's own real orchestration chart convention: one chart, a
`components:` map in `values.yaml`, shared Deployment/Service/CronJob
templates driven from that map (`templates/_objects.tpl`, `component.yaml`)
rather than one hand-written manifest per component.

## Prerequisites

- Helm 3.x, a Kubernetes cluster with a `StorageClass` for Neo4j's PVC
- Network connectivity from this cluster to Athena's existing Postgres instance
- An Anthropic API key, and — before ingesting any `Confidential`-tier
  repository — a confirmed Zero Data Retention agreement status (`CONST-051`–`053`)

## Install

```bash
# Add the real Neo4j chart repo (dependency)
helm repo add neo4j https://helm.neo4j.com/neo4j
helm dependency update

# Phase 0 / sandbox
helm install metis . -f values.yaml -f values-sbx.yaml \
  --set-string secrets.athenaDbPassword="$ATHENA_DB_PASSWORD" \
  --set-string secrets.neo4jPassword="$NEO4J_PASSWORD" \
  --set-string secrets.anthropicApiKey="$ANTHROPIC_API_KEY" \
  --set-string secrets.oauthClientSecret="$OAUTH_CLIENT_SECRET"

# Production (once Neo4j Enterprise licensing is budgeted, §15)
helm install metis . -f values.yaml \
  --set neo4j.edition=enterprise \
  --set neo4j.acceptLicenseAgreement=yes \
  --set-string secrets.athenaDbPassword="$ATHENA_DB_PASSWORD" \
  --set-string secrets.neo4jPassword="$NEO4J_PASSWORD" \
  --set-string secrets.anthropicApiKey="$ANTHROPIC_API_KEY" \
  --set-string secrets.oauthClientSecret="$OAUTH_CLIENT_SECRET"
```

## What's genuinely still open

- **Every `REPLACE` placeholder in `values.yaml`/`Chart.yaml`** — registry, image
  repository, ingress host, storage class, and the pinned Neo4j chart version —
  none of these are guessable from outside your actual infrastructure.
- **This chart could not be validated with `helm lint`/`helm template` in the
  environment that built it** — this sandbox's network allowlist doesn't reach
  Helm's own distribution (`get.helm.sh`, GitHub release assets for Helm itself).
  What *was* checked: `Chart.yaml` and `values.yaml` are valid plain YAML, and
  every `.tpl`/template file has balanced `{{ }}` delimiters. Full template
  rendering (`helm template .`) should be run in a real environment before
  applying this to a cluster — treat this chart as reviewed-by-construction,
  not test-deployed.
- **The three application images** (`metis-mcp-server`, `metis-ingestion-worker`,
  `metis-guardrail-corpus-runner`) don't exist yet — this chart deploys them,
  it doesn't build them. The MCP tool contracts (`metis-mcp-tool-contracts.json`)
  and connector manifests (bundled in `files/connectors/`) define their expected
  behavior; the actual service implementations are a separate build task.
