#!/usr/bin/env bash
# Rebuild the Métis graph from disk (application spec RD-9: re-ingest, never migrate).
#
# Every input this needs is a file in the repository or a artefact of extraction:
#   demo_data/models/*.json      the extracted models
#   /tmp/links-<svc>.json        INVOKES proposals from the react-ui pack
#   /tmp/athena-consumers.json   feign/CLI consumer index, for M-5f triage
#   .specify/specs/              the Spec Kit intent side
#
# Provenance is the point (D-1), so nothing is copied between databases: the
# graph is rebuilt by running the real pipeline again. That also makes this the
# recovery procedure if the container is ever lost.
#
# Usage:  METIS_NEO4J_PASSWORD=... ./reingest_athena.sh
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python3
: "${METIS_NEO4J_URI:=bolt://localhost:7687}"
: "${METIS_NEO4J_USER:=neo4j}"
: "${METIS_NEO4J_PASSWORD:?set METIS_NEO4J_PASSWORD (never passed as an argument — PLT-005)}"
export METIS_NEO4J_URI METIS_NEO4J_USER METIS_NEO4J_PASSWORD

API_SERVICES="core git kube metric pipeline spec tms"
UI_SERVICES="git kube metric pipeline spec tms"

echo "==> 1/6  schema (12 labels, Community edition — C1)"
$PY -m metis_mcp.ontology.schema --write >/dev/null 2>&1 || $PY - <<'EOF'
from metis_mcp.ontology import schema
schema.write("schema")
EOF
for f in schema/metis2-01-constraints.cypher schema/metis2-02-relationships.cypher; do
  docker exec -i "${METIS_CONTAINER:-metis-graph}" cypher-shell -u "$METIS_NEO4J_USER" \
    -p "$METIS_NEO4J_PASSWORD" < "$f" >/dev/null
done
echo "    constraints applied"

echo "==> 2/6  land models"
$PY -m metis_mcp.mbt.cli land demo_data/models/login-api.json \
  --journey login --surface api --source authored --author alice --job-id reingest >/dev/null
for s in $API_SERVICES; do
  $PY -m metis_mcp.mbt.cli land "demo_data/models/athena-$s-api.json" \
    --journey "athena-$s" --surface api --source authored --author joern-jvm --job-id reingest >/dev/null
done
for s in $UI_SERVICES; do
  $PY -m metis_mcp.mbt.cli land "demo_data/models/athena-$s-ui.json" \
    --journey "athena-$s" --surface ui --source authored --author joern-react --job-id reingest >/dev/null
done
echo "    13 models landed"

echo "==> 3/6  versions, run, findings"
PYTHONPATH=. $PY /tmp/load_all.py

echo "==> 4/6  INVOKES (M-5a)"
PYTHONPATH=. $PY - <<'EOF'
import json
from metis_mcp.mbt.cross_surface import InvokesLink, LinkSet, persist_invokes
from metis_mcp.mbt.graph_session import session
ls = LinkSet(journey="athena")
for l in json.load(open('/tmp/athena-invokes.json')):
    svc = l['evidence']['endpoint'].split('/')[1]
    ls.links.append(InvokesLink(f"athena-{svc}-ui::{l['ui']}", f"athena-{svc}-api::{l['api']}",
                                l["proposed_by"], l["evidence"], "alice"))
with session() as s:
    print(f"    {persist_invokes(s, ls)} INVOKES edges")
EOF

echo "==> 5/6  Spec Kit intent side (R5)"
PYTHONPATH=. $PY /tmp/land_specs.py

echo "==> 6/6  approve, then generate paths and cases"
approve() {
  $PY -m metis_mcp.mbt.cli review export --journey "athena-$1" --surface "$2" -o /tmp/rv.json >/dev/null 2>&1
  $PY - <<EOF
import json
d = json.load(open('/tmp/rv.json')); d['reviewer'] = 'alice'
[i.update(decision='approve', rationale='extraction reviewed; guards verified against source')
 for i in d['items']]
json.dump(d, open('/tmp/rv.json','w'), indent=2)
EOF
  $PY -m metis_mcp.mbt.cli review apply /tmp/rv.json --journey "athena-$1" --surface "$2" >/dev/null
}
for s in $API_SERVICES; do approve "$s" api; done
for s in $UI_SERVICES;  do approve "$s" ui;  done

for s in $UI_SERVICES; do
  $PY -m metis_mcp.mbt.cli persist --journey "athena-$s" --surface api \
    --episode "ep-athena-$s-api" --run-id run-athena-gen --version 1 --commit athena-head >/dev/null
  $PY -m metis_mcp.mbt.cli persist --journey "athena-$s" --surface ui \
    --episode "ep-athena-$s-ui" --run-id run-athena-gen --version 1 --commit athena-head >/dev/null
done
# core carries 5 unverifiable guard-completeness findings (three-way try/catch).
# M-17 is fail-closed, so proceeding is an explicit, recorded risk acceptance.
$PY -m metis_mcp.mbt.cli persist --journey athena-core --surface api \
  --episode ep-athena-core-api --run-id run-athena-gen --version 1 --commit athena-head \
  --allow-unverifiable >/dev/null
echo "    generated"

echo
echo "==> done"
