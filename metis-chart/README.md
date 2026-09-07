# Métis Helm Chart

Deploys **one component**: the MCP server, over Streamable HTTP, plus Neo4j as a
subchart dependency.

The header here used to name an ingestion worker, a guardrail-corpus CI/replay
job and a source-Postgres connection, and cite `CONST-051`–`CONST-058`. None of
those exist: the ingestion worker and the guardrail corpus went with the v1
engine, the database layer was staged out in the 2026-08-31 re-baseline, and the
`CONST-*` family is v1 constitution rules the current specification does not
carry. `components:` has always held exactly one entry.

**Deliberately not here:** Postgres (the episode log lives in Neo4j — a single
database) and Grafana (metrics are panels on an already-running one).

## Structure

One chart, a `components:` map in `values.yaml`, shared Deployment/Service
templates driven from that map (`templates/_objects.tpl`, `component.yaml`)
rather than a hand-written manifest per component.

## Prerequisites

- Helm 3.x, and a cluster with a `StorageClass` for Neo4j's PVC
- A Neo4j password, supplied at install and never committed

No Anthropic key, and no source-database connectivity: Métis loads no model by
default (semantic search is a Protocol with no bundled implementation), and it
reads no database it does not own — `METIS_EXECUTE` is `off` by default and the
clients are optional extras a default install does not have.

## Install

```bash
helm repo add neo4j https://helm.neo4j.com/neo4j
helm dependency update

helm install metis . -f values.yaml -f values-sbx.yaml \
  --set-string secrets.neo4jPassword="$DEPLOYMENT_NEO4J_PASSWORD"
```

**One secret, because one is read.** `sourceDbPassword`, `anthropicApiKey` and
`oauthClientSecret` were required at install and opened by nothing — a secret
nothing reads is still a secret somebody has to rotate.

The mounted `config.json` **names** the password variable rather than carrying
the value (`password_env`, PLT-005). It used to hold the literal, and a
Kubernetes secret volume mounts 0644 by default, which
`graph_session._password_from_file` refuses outright — so the chart could not
authenticate at all. The volume is mounted `0400` as well; that is defence in
depth now rather than the fix.

## What this chart could not do, and what changed

It rendered cleanly and passed `helm lint` while being unable to start a working
pod for **four independent reasons**, each sufficient on its own. Worth reading
before trusting a chart that lints:

| Defect | Effect |
|---|---|
| `MCP_TRANSPORT` set; `METIS_MCP_TRANSPORT` is what is read | the container ran `stdio` — waiting on a stdin nobody was attached to, while publishing a port nothing listened on |
| `METIS_HTTP_HOST` never set | bound `127.0.0.1`, which inside a pod means the pod. The Service reached nothing |
| liveness probe on `/healthz` | that endpoint is on the HTTP API. `metis-mcp-server` 404s it, so every pod failed its probe and restarted in a loop |
| literal password in a 0644 mount | refused at startup, every time |

Fourteen of the sixteen environment variables this chart set had no reader at
all — the `OAUTH_*` family, the `METIS_SOURCE_DB_*` family (the database layer
was staged out in the 2026-08-31 re-baseline), `ANTHROPIC_API_KEY`,
`METIS_LOG_LEVEL`. A variable nothing reads looks exactly like a variable
something reads, which is how `MCP_TRANSPORT` sat beside the name that works.

`test_structure.py` now asserts the chart configures nothing without a reader,
sets the switches that decide what a deployment may do, keeps a literal secret
out of the committed config, and does not probe an endpoint this process lacks.
CI renders the chart on every push.

## What this does not do

**The MCP surface does not authenticate.** It cannot approve or publish (N-8),
and it will read out every requirement, criterion and specification in the graph
to whoever reaches it. Binding `0.0.0.0` is what makes the Service work and the
server prints a warning about it, correctly. What bounds it here is cluster
networking and nothing else.

For anything beyond a single trusted network, put the HTTP API's bearer-token
surface (`METIS_API_TOKENS`, digests never literals) in front of it. That is a
larger change than this chart.

**A real deployment is untested.** Everything above is verified by `helm lint`,
`helm template`, and by resolving the rendered config against the real
`graph_session` — not by running it on a cluster.

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
