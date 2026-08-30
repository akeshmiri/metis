#!/usr/bin/env bash
# Rebuild the graph from committed sources (application spec RD-9: re-ingest,
# never migrate).
#
# **Everything this needs is in this repository.** That sentence was here before
# and it was not true: the script read a `.specify/specs` directory under a hardcoded
# absolute path into a private checkout, plus three pack reports it expected
# somebody to have left in `/tmp`. A recovery procedure that depends on another
# repository and on scratch files is not a recovery procedure — the same
# criticism this script was written to make of its predecessor.
#
# It now builds from `demo_project/`, the corpus the test suite uses, and runs
# the query packs itself rather than hoping for their output:
#
#   demo_project/records-service   the API surface (javasrc2cpg -> two JVM packs)
#   demo_project/records-ui        the React surface (jssrc2cpg -> react-ui)
#   demo_project/records-page      the plain-DOM surface (jssrc2cpg -> js-ui)
#   demo_project/specs             the acceptance criteria (the intent side)
#   demo_project/profile.json      the project profile, incl. its own annotations
#   demo_data/models/*.json        the authored models (login, records)
#
# It deliberately stops at Quarantine. Approvals are human decisions (G1) and
# this script does not manufacture them -- an earlier version approved every
# model in a loop with a canned rationale, which is how an estate ends up
# "approved" with nobody having read anything.
#
# Usage:  METIS_NEO4J_PASSWORD=... ./rebuild_graph.sh [--wipe]
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python3
: "${METIS_NEO4J_URI:=bolt://localhost:7687}"
: "${METIS_NEO4J_USER:=neo4j}"
# `cypher-shell` below needs the secret directly, so the script has to hold it —
# but it must not be a SECOND source of truth. `graph_session.resolve()` is the
# one resolver (environment, then ~/.metis/config.json), and asking it here means
# a password configured the supported way is found without being exported.
#
# This used to be a bare `:?` on the environment variable alone, which meant that
# moving the password into the config file — the arrangement the tool itself
# recommends — broke the rebuild while `metis` kept working.
if [ -z "${METIS_NEO4J_PASSWORD:-}" ]; then
  METIS_NEO4J_PASSWORD="$(PYTHONPATH=. $PY -c \
    'from metis_mcp.mbt.graph_session import resolve; print(resolve().password)' \
    2>/dev/null || true)"
fi
: "${METIS_NEO4J_PASSWORD:?no graph password: set METIS_NEO4J_PASSWORD, or configure graph.neo4j in ~/.metis/config.json (never as an argument — PLT-005)}"
export METIS_NEO4J_URI METIS_NEO4J_USER METIS_NEO4J_PASSWORD
CONTAINER="${METIS_NEO4J_CONTAINER:-metis-graph}"

DEMO=demo_project
WORK="${METIS_REBUILD_WORK:-$(mktemp -d)}"
STRUCTURAL="$WORK/structural.json"
BEHAVIOUR="$WORK/behaviour.json"
INVENTORY="$WORK/inventory.json"
UI_FACTS="$WORK/react.json"
DOM_FACTS="$WORK/dom.json"

cypher() { docker exec -i "$CONTAINER" cypher-shell -u "$METIS_NEO4J_USER" -p "$METIS_NEO4J_PASSWORD" "$@"; }

if [ "${1:-}" = "--wipe" ]; then
  # Deliberate, announced, and counted before and after -- a destructive step
  # that reports nothing is how a wipe goes unnoticed until something reads.
  before=$(cypher --format plain "MATCH (n) RETURN count(n) AS n;" | tail -1)
  echo "==> WIPE requested. Deleting $before node(s)."
  cypher "MATCH (n) DETACH DELETE n;" >/dev/null
  echo "    deleted; now $(cypher --format plain 'MATCH (n) RETURN count(n) AS n;' | tail -1)"
fi

# ---------------------------------------------------------------------------
echo "==> 0/5  extract from the demo corpus (the packs, not a scratch file)"
#
# Preflight ignores the graph check on purpose: extraction is database-free, and
# coupling "can I extract" to "is Neo4j up" made the answer depend on something
# that has nothing to do with it.
PYTHONPATH=. $PY - <<EOF | sed 's/^/    /'
import json, shutil
from code_analysis import engine

profile = json.load(open("$DEMO/profile.json"))
engine.preflight().require(ignore=("graph",))

api = engine.extract("$DEMO/records-service", language="javasrc",
                     project="demo-records", framework="spring-mvc",
                     project_annotations=profile["annotations"],
                     commit="rebuild", skip_preflight=True)
shutil.copy(api.structural, "$STRUCTURAL")
shutil.copy(api.behaviour, "$BEHAVIOUR")
if api.inventory:
    shutil.copy(api.inventory, "$INVENTORY")
for line in api.log:
    print(line)

for repo, framework, target in (("$DEMO/records-ui", "react", "$UI_FACTS"),
                                ("$DEMO/records-page", "dom-events", "$DOM_FACTS")):
    ui = engine.extract(repo, language="jssrc", project=repo.rsplit("/", 1)[-1],
                        framework=framework, commit="rebuild", skip_preflight=True)
    shutil.copy(next(iter(ui.reports.values())), target)
    print(f"{repo}: {framework}")
EOF

# A classified transition carries `:ApiCall` or `:UiAction` and **not**
# `:Transition`, so the generic label is a worklist of transitions nothing has
# classified. Nodes landed before that rule carry both; strip the generic one so
# the worklist means what it says.
echo "==> 1/5  reconcile labels on any pre-existing nodes"
cypher "MATCH (t:Transition) WHERE t:ApiCall OR t:UiAction REMOVE t:Transition
        RETURN count(t) AS relabelled;" 2>/dev/null | tail -1 | sed 's/^/    stripped generic label from /'

echo "==> 2/5  schema"
$PY -c "from metis_mcp.ontology import schema; schema.write('schema')"
for f in schema/metis2-01-constraints.cypher schema/metis2-02-relationships.cypher; do
  [ -f "$f" ] && cypher < "$f" >/dev/null
done
echo "    constraints: $(cypher --format plain 'SHOW CONSTRAINTS YIELD name RETURN count(*) AS n;' | tail -1)"

# **The evidence layer is landed by the model-build workflow itself**, not here.
# It used to be a separate stage, on the reasoning that a derivation edge needs
# its endpoints to exist first — true, and the workflow's `land` stage already
# does both in that order (`_land_evidence` then `_plan_derivation_edges`).
# Running it here as well lands it TWICE under two different raw-intake episodes,
# because the episode id is a hash of its inputs and the two callers pass
# different ones. Measured on a real service: 24 Endpoint nodes for 12 endpoints,
# 10 ExceptionMapping for 5, and every transition carrying two DERIVED_FROM edges
# — every count doubled, nothing reported, because MERGE cannot dedupe ids that
# differ.

echo "==> 3/5  the API model, from the query packs (extraction_method: static_analysis)"
#
# `--allow-unverifiable` is deliberate and narrower than it looks.
# `check_guard_completeness` skips any outcome group containing an unguarded
# member, so before rejections were modelled those groups were SILENTLY SKIPPED.
# They are checked now, and a group the checker cannot show jointly exhaustive is
# reported rather than dropped.
#
# What this flag does NOT do: approve anything. Everything still lands at
# Quarantine, every finding is recorded on the run, and generation stays gated
# separately by G1/`model_is_approved` (F-8). M-18 blocks *generation* from a
# model that is not well-formed, and that gate is untouched.
$PY -m metis_mcp.mbt.cli workflow run model-build --scope "records-api" \
  "$BEHAVIOUR" --endpoints "$STRUCTURAL" \
  --journey records --surface api --source code --job-id rebuild \
  --allow-unverifiable \
  >/dev/null 2>&1 || true      # halts at G1 by design; exit 5 is not failure
echo "    records-api"

echo "==> 3b/5  the UI models, from the frontend packs"
# Both go through the same web source as the API side, so their provenance is
# `static_analysis` too -- landing them `authored` would record a person as the
# author of what a pack recovered (M-13).
for pair in "$UI_FACTS:records" "$DOM_FACTS:records-page"; do
  facts="${pair%%:*}"; journey="${pair#*:}"
  [ -f "$facts" ] || { echo "    !! $facts absent — no UI model for $journey"; continue; }
  # A surface that yields no model is REPORTED and does not stop the rebuild.
  # `records-page` is the case that proves this is needed: its mutations have
  # runtime-computed signatures, so `js-ui` recovers the handlers and can name no
  # observable outcome (§5.8). That is a correct refusal about a deliberately
  # hard corpus, not a failure of the run -- and because it was raised, three
  # later stages (the login model, the acceptance criteria, the report) were
  # skipped while the script still exited 0 through its own pipeline.
  PYTHONPATH=. $PY - <<EOF | sed 's/^/    /'
import sys
from metis_mcp.mbt.graph_session import session
from metis_mcp.model_sources import get, land, plan_landing
try:
    result = get("web").produce(path="$facts", journey="$journey")
except ValueError as refusal:
    print(f"!! $journey: no UI model — {refusal}")
    sys.exit(0)
plan = plan_landing(result, journey="$journey", job_id="rebuild")
with session() as s:
    outcome = land(s, plan)
print(f"{result.model.id}: {outcome.nodes_written} nodes via {result.extraction_method}")
EOF
done

echo "==> 3c/5  the login example"
$PY -m metis_mcp.mbt.cli land demo_data/models/login-api.json \
  --journey login --surface api --source authored --author alice --job-id rebuild >/dev/null

echo "==> 4/5  acceptance criteria (the intent side)"
# Hand-written and checked in, so they can genuinely disagree with the code --
# which is the point of comparing the two. AC-4 says DELETE answers 204 while
# demo_project/openapi.json documents 200, and a person settles that.
$PY demo_data/land_spec_criteria.py "$DEMO/specs" | sed 's/^/    /'

echo "==> 4b/5  the academy (Métis's own material, as a source like any other)"
# `docs/academy/` lands as `Lesson` through the ordinary landing path, into the
# SAME graph as everything above. That is the point rather than an economy: the
# intent is that `ask` answers a question about Métis the way it answers one
# about a product, and Neo4j cannot join across databases in one session -- so a
# separate academy database would put the lessons somewhere `search_knowledge`
# could never see them next to a criterion. Separation is by label (`:Lesson`)
# and by its own Episode, which is what the ontology already gives.
#
# Reported and non-fatal, for the reason 3b now is: a checkout without the docs
# is a thin graph, not a reason to skip the stages after this one.
if ! $PY -m metis_mcp.mbt.cli lessons --job-id rebuild 2>&1 | sed 's/^/    /'; then
  echo "    !! the academy did not land — continuing; the demo graph is unaffected"
fi

echo "==> 5/5  cross-surface INVOKES proposals (M-5a)"
if [ ! -f "$UI_FACTS" ]; then
  echo "    !! $UI_FACTS absent — no INVOKES proposals."
  echo "       The UI and API models will both be present and unlinked, which is"
  echo "       visible as zero INVOKES rather than as a wrong number."
else
# Derived from the frontend pack's own `api_calls` (screen -> endpoint), not from
# a mapping file. An earlier rebuild read a mapping whose UI ids predated the
# current synthesiser: all 91 matched no transition, and the writer counted them
# as written anyway.
UI_FACTS="$UI_FACTS" PYTHONPATH=. $PY - <<'EOF' | sed 's/^/    /'
# The derivation itself lives in `metis_mcp/mbt/link_proposals.py`, where it is
# pure and therefore testable. It was inline here, and in that form carried four
# defects no test could see -- see that module's docstring for what they were.
import json, os
from metis_mcp.mbt.cross_surface import persist_invokes, persist_triggers
from metis_mcp.mbt.graph_session import session
from metis_mcp.mbt.link_proposals import propose

facts = json.load(open(os.environ["UI_FACTS"]))

with session() as s:
    # The specific labels, not `:Transition`: a classified transition no longer
    # carries the generic one, so matching on it returns nothing at all.
    ui_rows = list(s.run(
        "MATCH (t:UiAction) RETURN t.id AS id, t.name AS name, t.trigger AS trigger"))
    api_rows = list(s.run(
        "MATCH (t:ApiCall) RETURN t.id AS id, t.trigger AS trigger"))

    proposal = propose(ui_rows, api_rows, facts.get("api_calls", ()),
                       proposed_by="react-ui")
    for screen in proposal.unmatched_screens:
        print(f"!! no UiAction names screen {screen!r} — proposing nothing for it")
    for endpoint in proposal.unmatched_endpoints:
        print(f"!! no ApiCall path ends with {endpoint!r} — proposing nothing for it")

    unique = proposal.link_set("records")
    t_written, t_unmatched = persist_triggers(s, unique, confirmed_only=False)
    i_written, i_unmatched = persist_invokes(s, unique, confirmed_only=False)
    print(f"{t_written} TRIGGERS (the page starts the call), "
          f"{i_written} INVOKES (the page rendered the outcome)")
    if t_unmatched or i_unmatched:
        print(f"{len(t_unmatched) + len(i_unmatched)} link(s) matched no transition")
    print("both are proposals: they credit nothing until confirmed (M-5g, F-7)")
EOF
fi

echo
echo "==> done. Everything is at Quarantine."
cypher --format plain "MATCH (n) RETURN labels(n) AS labels, count(*) AS n ORDER BY n DESC;"
echo
echo "Unclassified transitions (the :Transition worklist):"
cypher --format plain "MATCH (t:Transition) RETURN count(t) AS needs_classifying;"
echo
echo "Nothing is approved, and that is correct: G1 is a human decision (F-8), and"
echo "a rebuild that approved its own output would defeat the gate it ran through."
echo "Review with:  metis review export --journey <j> --surface <s> -o r.json"
