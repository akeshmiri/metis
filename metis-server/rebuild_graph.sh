#!/usr/bin/env bash
# Rebuild the graph: restore from a project's stored Cypher when one matches
# this checkout, and re-ingest from committed sources when it does not.
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
# Usage:  METIS_NEO4J_PASSWORD=... ./rebuild_graph.sh [--wipe] [--academy-only|--demo]
#
# **A fresh database gets the academy and nothing else.** Creating a graph and
# filling it with `demo_project/` means a first `ask` or `search_knowledge` is
# answered out of fixtures -- Records, Contracts, a login example -- none of
# which the person asking has any reason to care about, and all of which rank
# alongside their real work once they land some. The demo corpus is what the
# TEST SUITE needs; it is not what a new install needs, and the two were the
# same thing only because one script did both.
#
# So: an EMPTY database defaults to academy-only, and says so. A non-empty one
# keeps the full rebuild, because that is a rebuild of something that already
# had the demo in it. `--demo` forces the full corpus into a fresh graph;
# `--academy-only` forces the short path into a populated one.
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

ACADEMY_ONLY=0
WANT_DEMO=0
WIPE=0
for arg in "$@"; do
  case "$arg" in
    --wipe)         WIPE=1 ;;
    --academy-only) ACADEMY_ONLY=1 ;;
    --demo)         WANT_DEMO=1 ;;
    *) echo "unknown option: $arg" >&2
       echo "usage: $0 [--wipe] [--academy-only|--demo]" >&2; exit 2 ;;
  esac
done
if [ "$ACADEMY_ONLY" = 1 ] && [ "$WANT_DEMO" = 1 ]; then
  echo "--academy-only and --demo contradict each other" >&2; exit 2
fi

if [ "$WIPE" = 1 ]; then
  # Deliberate, announced, and counted before and after -- a destructive step
  # that reports nothing is how a wipe goes unnoticed until something reads.
  before=$(cypher --format plain "MATCH (n) RETURN count(n) AS n;" | tail -1)
  echo "==> WIPE requested. Deleting $before node(s)."
  cypher "MATCH (n) DETACH DELETE n;" >/dev/null
  echo "    deleted; now $(cypher --format plain 'MATCH (n) RETURN count(n) AS n;' | tail -1)"
fi

# ---------------------------------------------------------------------------
# **Restore beats re-ingest when the file matches, and only then.**
#
# The old rule was re-ingest and never migrate, cited as RD-9. That citation was
# wider than the rule: RD-9 belonged to the v1 -> v2 engine migration (completed
# at 61814dc) and said "do not transform v1 nodes into v2 nodes, re-extract
# instead". It never said a project may not keep a restore file.
#
# `verify` is what makes this safe: it compares the export's commit and ontology
# against this checkout, and a mismatch falls through to re-ingest rather than
# restoring a graph that describes code nobody is running.
if [ -n "${METIS_RESTORE_FROM:-}" ]; then
  echo "==> restore: ${METIS_RESTORE_FROM}"
  if $PY -m metis_mcp.mbt.cli storage verify --project "${METIS_RESTORE_PROJECT:?set METIS_RESTORE_PROJECT alongside METIS_RESTORE_FROM}" \
       --out "$METIS_RESTORE_FROM" --commit "${METIS_RESTORE_COMMIT:-}" 2>&1 | sed 's/^/    /'; then
    $PY -m metis_mcp.mbt.cli storage restore --project "$METIS_RESTORE_PROJECT" \
        --out "$METIS_RESTORE_FROM" --commit "${METIS_RESTORE_COMMIT:-}" 2>&1 | sed 's/^/    /'
    echo
    echo "==> done. Restored from stored Cypher; no stage below was run."
    exit 0
  fi
  echo "    the export does not match this checkout — re-ingesting instead."
  echo
fi

# **Counted, not assumed.** "Is this database fresh" is a question with an
# answer in the database, and the alternative -- a marker file, a first-run
# flag -- would say "fresh" about a graph somebody else had already filled.
existing=$(cypher --format plain "MATCH (n) RETURN count(n) AS n;" | tail -1 | tr -d '[:space:]')
if [ "$WANT_DEMO" = 0 ] && [ "$ACADEMY_ONLY" = 0 ] && [ "${existing:-0}" = "0" ]; then
  ACADEMY_ONLY=1
  echo "==> fresh database ($existing nodes): landing the academy only."
  echo "    Pass --demo to build the demo corpus into it instead."
  echo
fi

if [ "$ACADEMY_ONLY" = 1 ]; then
  echo "==> academy-only: skipping extraction and every demo stage."
  echo "    Schema and docs/academy/ are all that will be written."
  echo
fi

# ---------------------------------------------------------------------------
# The demo stages. Bodies are left un-indented inside these guards on purpose:
# re-indenting a hundred lines would bury the one-line change that skips them.
if [ "$ACADEMY_ONLY" = 0 ]; then
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
fi   # end demo extraction (stage 0)

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

if [ "$ACADEMY_ONLY" = 0 ]; then
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

fi   # end demo models and criteria (stages 3, 3b, 3c, 4)

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

if [ "$ACADEMY_ONLY" = 0 ]; then
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

fi   # end cross-surface proposals (stage 5)

# **Unnumbered because it runs in BOTH modes and after all of them.** Vectors
# belong to whatever landed, and the academy-only path lands embeddable nodes
# (Lesson, Passage) just as the demo path lands criteria and specifications.
#
# **Why this stage exists.** A rebuild left every vector index live and empty, so
# `--hybrid` returned keyword results and said nothing about it — the exact
# silent success `cmd_embed`'s own docstring was written about, reintroduced one
# level up by the script that creates the graph. Measured on the academy: keyword
# ranks 23 of 36 questions first, hybrid 29.
echo
echo "==> embeddings"
# One resolver. `--provider` is required and `load_provider` never defaults, so
# the spec has to come from somewhere — and re-deriving "environment, then the
# config file" in shell would be a second answer to the question
# `configured_provider_spec` already answers, which is the mistake the password
# block at the top of this script exists to avoid.
SPEC="$(PYTHONPATH=. $PY -c \
  'from metis_mcp.retrieval import configured_provider_spec as f; print(f())' \
  2>/dev/null || true)"
if [ -z "$SPEC" ]; then
  # Reported, never silent -- and not an error. A default install has no
  # provider and keyword search is the supported answer, not a degradation.
  echo "    no embedding provider configured — skipped, and semantic search"
  echo "    will fall back to keyword until one is named:"
  echo "      export METIS_EMBEDDING_PROVIDER=metis_mcp.providers.static:Potion"
  echo "    or  \"embedding\": {\"provider\": \"...\"}  in ~/.metis/config.json"
  echo "    The bundled option needs its extra:  uv pip install -e \".[embeddings]\""
elif ! $PY -m metis_mcp.mbt.cli embed --provider "$SPEC" 2>&1 | sed 's/^/    /'; then
  # Non-fatal for the reason 3b and 4b are: a graph with no vectors is a graph
  # that answers by keyword, not a failed rebuild.
  echo "    !! embedding failed — the graph is landed and searchable by keyword"
fi

echo
echo "==> done. Everything is at Quarantine."
cypher --format plain "MATCH (n) RETURN labels(n) AS labels, count(*) AS n ORDER BY n DESC;"
echo

# The closing advice differs by mode because the next step does. Telling someone
# who has just built an academy-only graph to export a model review names a
# model that is not there.
if [ "$ACADEMY_ONLY" = 1 ]; then
  echo "This graph holds the academy and the schema. No model, no demo corpus."
  echo "Lessons land at Quarantine like every other source (S-4)."
  echo
  echo "Questions about Métis are answered through the MCP surface (\`ask\`,"
  echo "\`search_knowledge\`). To check what it retrieves:  metis retrieval-bench"
  echo "To build a model from a repository:  metis init <repo> && metis analyse <repo>"
else
  echo "Unclassified transitions (the :Transition worklist):"
  cypher --format plain "MATCH (t:Transition) RETURN count(t) AS needs_classifying;"
  echo
  echo "Nothing is approved, and that is correct: G1 is a human decision (F-8), and"
  echo "a rebuild that approved its own output would defeat the gate it ran through."
  echo "Review with:  metis review export --journey <j> --surface <s> -o r.json"
fi
