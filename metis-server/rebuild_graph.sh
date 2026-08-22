#!/usr/bin/env bash
# Rebuild the graph from committed sources (application spec RD-9: re-ingest,
# never migrate).
#
# **This replaces `reingest_athena.sh`, which could not actually do it.** That
# script depended on two helpers under `/tmp` (`load_all.py`, `land_specs.py`)
# that no longer exist, so when the graph was lost the intent side -- 66
# acceptance criteria -- had no committed path back. A recovery procedure that
# depends on scratch files is not a recovery procedure.
#
# Everything this needs is in the repository or is a query pack's output:
#   demo_data/models/*.json                        the landed models
#   demo_data/land_spec_criteria.py                the criteria loader
#   <athena>/.specify/specs/                       the criteria themselves
#   /tmp/athena-{behaviour,invokes}.json           pack output (re-runnable)
#
# It deliberately stops at Quarantine. Approvals are human decisions (G1) and
# this script does not manufacture them -- the previous one approved all thirteen
# models in a loop with a canned rationale, which is how an estate ends up
# "approved" with nobody having read anything.
#
# Usage:  METIS_NEO4J_PASSWORD=... ./rebuild_graph.sh [--wipe]
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python3
: "${METIS_NEO4J_URI:=bolt://localhost:7687}"
: "${METIS_NEO4J_USER:=neo4j}"
: "${METIS_NEO4J_PASSWORD:?set METIS_NEO4J_PASSWORD (never as an argument — PLT-005)}"
export METIS_NEO4J_URI METIS_NEO4J_USER METIS_NEO4J_PASSWORD

ATHENA="${ATHENA_ROOT:-/Users/akeshmiri/Projects/real/athena}"
BEHAVIOUR="${BEHAVIOUR_REPORT:-/tmp/athena-behaviour.json}"
STRUCTURAL="${STRUCTURAL_REPORT:-/tmp/new-structural.json}"
CONTAINER="${METIS_CONTAINER:-metis-graph}"
UI_FACTS="${UI_FACTS:-/tmp/athena-ui-facts.json}"

API_SERVICES="core git kube metric pipeline spec tms"
UI_SERVICES="git kube metric pipeline spec tms"

cypher() { docker exec -i "$CONTAINER" cypher-shell -u "$METIS_NEO4J_USER" -p "$METIS_NEO4J_PASSWORD" "$@"; }

if [ "${1:-}" = "--wipe" ]; then
  # Deliberate, announced, and counted before and after -- a destructive step
  # that reports nothing is how a wipe goes unnoticed until something reads.
  before=$(cypher --format plain "MATCH (n) RETURN count(n) AS n;" | tail -1)
  echo "==> WIPE requested. Deleting $before node(s)."
  cypher "MATCH (n) DETACH DELETE n;" >/dev/null
  echo "    deleted; now $(cypher --format plain 'MATCH (n) RETURN count(n) AS n;' | tail -1)"
fi

# A classified transition carries `:ApiCall` or `:UiAction` and **not**
# `:Transition`, so the generic label is a worklist of transitions nothing has
# classified. Nodes landed before that rule carry both; strip the generic one so
# the worklist means what it says.
echo "==> 0/5  reconcile labels on any pre-existing nodes"
cypher "MATCH (t:Transition) WHERE t:ApiCall OR t:UiAction REMOVE t:Transition
        RETURN count(t) AS relabelled;" 2>/dev/null | tail -1 | sed 's/^/    stripped generic label from /'

echo "==> 1/5  schema"
$PY -c "from metis_mcp.ontology import schema; schema.write('schema')"
for f in schema/metis2-01-constraints.cypher schema/metis2-02-relationships.cypher; do
  [ -f "$f" ] && cypher < "$f" >/dev/null
done
echo "    constraints: $(cypher --format plain 'SHOW CONSTRAINTS YIELD name RETURN count(*) AS n;' | tail -1)"

echo "==> 1b/5  the evidence layer — the processed intake itself"
#
# **This must run BEFORE any model.** A derivation edge is written with two
# MATCHes, so a transition landing first would point at endpoints that do not
# exist yet and the edges would silently merge nothing (the writer now reports
# that rather than counting them as written).
if [ -f "$BEHAVIOUR" ] && [ -f "$STRUCTURAL" ]; then
  PYTHONPATH=. $PY - <<EOF | sed 's/^/    /'
import json
from metis_mcp.model_sources.sources import _report_from_dict
from metis_mcp.model_sources.raw_landing import plan_raw_landing
from metis_mcp.model_sources.landing import land
from metis_mcp.mbt.graph_session import session

structural = _report_from_dict(json.load(open("$STRUCTURAL")))
behaviour = _report_from_dict(json.load(open("$BEHAVIOUR")))
try:
    ui = json.load(open("$UI_FACTS"))
except OSError:
    ui = None

plan = plan_raw_landing(structural, journey="athena", repo="athena",
                        behaviour=behaviour, ui_facts=ui, job_id="rebuild")
if not plan.is_legal:
    print(f"REFUSED — {len(plan.errors)} validation error(s): {plan.errors[0]}")
else:
    with session() as s:
        result = land(s, plan)
    print(f"{result.nodes_written} nodes, {result.edges_written} edges")
    for what, why in plan.skipped:
        print(f"{what}: {why}")
    for triple, count, why in result.unmatched:
        print(f"!! {triple}: {count} unmatched — {why}")
EOF
else
  echo "    !! pack reports missing — no evidence layer, so the models below will"
  echo "       land with no DERIVED_FROM edges and no parameters (reported, not silent)."
fi

echo "==> 2/5  API models, from the query pack (extraction_method: static_analysis)"
#
# `--allow-unverifiable` is deliberate, and it is narrower than it looks.
#
# Modelling the declared rejections (X-6a) gave every transition in an affected
# group a non-empty guard. `check_guard_completeness` skips any group containing
# an unguarded member, so those groups were previously not verified — they were
# SILENTLY SKIPPED. They are now checked, and 13 of them cannot be shown jointly
# exhaustive. Most are the M-6 unfolding interacting with the checker: after
# unfolding, `GET /metric/{id}` reaches Ok200 from `MetricPresent`, so at `Ready`
# the case `NOT (t.isEmpty())` is genuinely unreachable — the model is right and
# the checker does not know the state's invariant. The rest are outcomes the
# behaviour pack did not recover (a 208 beside a 201).
#
# What this flag does NOT do: approve anything. Everything still lands at
# Quarantine, every finding is recorded on the run, and generation stays gated
# separately by G1/`model_is_approved` (F-8). M-18 blocks *generation* from a
# model that is not well-formed, and that gate is untouched.
if [ -f "$BEHAVIOUR" ] && [ -f "$STRUCTURAL" ]; then
  for s in $API_SERVICES; do
    $PY -m metis_mcp.mbt.cli workflow run model-build --scope "athena-$s-api" \
      "$BEHAVIOUR" --endpoints "$STRUCTURAL" --service "$s" \
      --journey "athena-$s" --surface api --source code --job-id rebuild \
      --allow-unverifiable \
      >/dev/null 2>&1 || true      # halts at G1 by design; exit 5 is not failure
    echo "    athena-$s-api"
  done
else
  echo "    !! pack reports missing — falling back to the committed model files."
  echo "       These land as 'authored', which records that a PERSON wrote what a"
  echo "       static analyser inferred (M-13). Re-run the packs to avoid that."
  for s in $API_SERVICES; do
    $PY -m metis_mcp.mbt.cli land "demo_data/models/athena-$s-api.json" \
      --journey "athena-$s" --surface api --source authored --author rebuild-fallback \
      --job-id rebuild >/dev/null
  done
fi

echo "==> 3/5  UI models, from the frontend pack (extraction_method: static_analysis)"
if [ -f "$UI_FACTS" ]; then
  # Screens are grouped by the endpoints they call, so a page lands in the model
  # of the service it talks to. Previously these six were hand-derived
  # off-pipeline and landed `authored`, recording that a person wrote what the
  # pack inferred (M-13).
  PYTHONPATH=. $PY - <<'EOF' | sed 's/^/    /'
import collections, json, os
from metis_mcp.model_sources import get, land, plan_landing
from metis_mcp.mbt.graph_session import session

facts = json.load(open(os.environ.get("UI_FACTS", "/tmp/athena-ui-facts.json")))
by_journey = collections.defaultdict(set)
for call in facts.get("api_calls", ()):
    parts = (call.get("endpoint") or "").strip("/").split("/")
    if parts and parts[0]:
        by_journey[f"athena-{parts[0]}"].add(call["screen"])

source = get("web")
for journey in sorted(by_journey):
    try:
        result = source.produce(path=os.environ.get("UI_FACTS", "/tmp/athena-ui-facts.json"),
                                journey=journey,
                                screens=",".join(sorted(by_journey[journey])))
    except ValueError as e:
        print(f"{journey}: {e}")
        continue
    plan = plan_landing(result, journey=journey, job_id="rebuild")
    if not plan.is_legal:
        print(f"{journey}: REFUSED — {plan.errors[0]}")
        continue
    with session() as s:
        outcome = land(s, plan)
    pages = result.evidence.get("pages", "")
    print(f"{result.model.id}: {outcome.nodes_written} nodes, pages: {pages}")
EOF
else
  echo "    !! $UI_FACTS absent — falling back to the committed model files"
  for s in $UI_SERVICES; do
    $PY -m metis_mcp.mbt.cli land "demo_data/models/athena-$s-ui.json" \
      --journey "athena-$s" --surface ui --source authored --author rebuild-fallback \
      --job-id rebuild >/dev/null
  done
fi

echo "==> 3b/5  the login example"
$PY -m metis_mcp.mbt.cli land demo_data/models/login-api.json \
  --journey login --surface api --source authored --author alice --job-id rebuild >/dev/null
# atlas-site is a js-ui frontend: real click/scroll handlers, no API calls. It
# goes through the same web source as the React pages so its provenance is
# `static_analysis` too — landing it `authored` recorded a person as the author
# of what the pack recovered (M-13).
JS_FACTS="${JS_FACTS:-/tmp/ui-facts.json}"
if [ -f "$JS_FACTS" ]; then
  PYTHONPATH=. $PY - <<EOF | sed 's/^/    /'
from metis_mcp.mbt.graph_session import session
from metis_mcp.model_sources import get, land, plan_landing
result = get("web").produce(path="$JS_FACTS", journey="atlas-site")
plan = plan_landing(result, journey="atlas-site", job_id="rebuild")
with session() as s:
    outcome = land(s, plan)
print(f"{result.model.id}: {outcome.nodes_written} nodes via {result.extraction_method}")
EOF
else
  $PY -m metis_mcp.mbt.cli land demo_data/models/atlas-site-ui.json \
    --journey atlas-site --surface ui --source authored --author rebuild-fallback \
    --job-id rebuild >/dev/null
fi

echo "==> 4/5  acceptance criteria (the intent side)"
if [ -d "$ATHENA/.specify/specs" ]; then
  $PY demo_data/land_spec_criteria.py "$ATHENA/.specify/specs" | sed 's/^/    /'
else
  echo "    !! $ATHENA/.specify/specs not found — the graph will have models and no"
  echo "       criteria, which yields coverage and never correctness (S-3)."
fi

echo "==> 5/5  cross-surface INVOKES proposals (M-5a)"
# Guarded like every other stage. Without this the whole rebuild died here with a
# FileNotFoundError whenever the frontend pack had not been re-run -- so the one
# script that exists to recover the graph could not finish on a clean machine,
# and the failure came *after* the criteria had landed, which made it look like
# the run had succeeded until you read the tail.
if [ ! -f "$UI_FACTS" ]; then
  echo "    !! $UI_FACTS absent — no INVOKES proposals."
  echo "       The UI and API models will both be present and unlinked, which is"
  echo "       visible as zero INVOKES rather than as a wrong number."
else
# Derived from the frontend pack's own `api_calls` (screen -> endpoint), not from
# a mapping file. The previous rebuild read /tmp/athena-invokes.json, whose UI
# ids predate the current synthesiser: all 91 matched no transition, and the
# writer counted them as written anyway.
PYTHONPATH=. $PY - <<'EOF' | sed 's/^/    /'
import json, os, re
import re
from metis_mcp.mbt.cross_surface import (
    InvokesLink, LinkSet, persist_invokes, persist_triggers)
from metis_mcp.mbt.graph_session import session

facts = json.load(open(os.environ.get("UI_FACTS", "/tmp/athena-ui-facts.json")))
UI_ID = re.compile(r"^(?P<model>[^:]+)::ui::(?P<screen>[^:]+)::(?P<region>[^:]+)::")

with session() as s:
    # The specific labels, not `:Transition`. A classified transition no longer
    # carries the generic label, so matching on it here returned nothing at all
    # and the derivation silently proposed zero links.
    ui_rows = list(s.run("MATCH (t:UiAction) RETURN t.id AS id"))
    api_rows = list(s.run(
        "MATCH (t:ApiCall) "
        "RETURN t.id AS id, t.trigger AS trigger, t.outcome_status AS status"))

    # An endpoint is claimed by the API transitions whose trigger path ends with
    # it, both forms, because controllers are dual-mounted and the gateway
    # strips the prefix.
    def api_for(endpoint: str, journey: str, want_success: bool | None = None) -> list[str]:
        """API transitions for an endpoint, **scoped to the same service**.

        Path suffix matching alone crosses services: a bare `GET /trend` in one
        model tail-matches `/metric/trend` in another, and the link would credit
        one service's UI with another service's behaviour. That is the same
        contamination the test-inventory matcher was fixed for.
        """
        want = endpoint.rstrip("/") or "/"
        prefix = f"{journey}-api::"
        out = []
        for row in api_rows:
            if not row["id"].startswith(prefix):
                continue
            path = (row["trigger"] or "").split(None, 1)
            if len(path) != 2:
                continue
            p = path[1].rstrip("/") or "/"
            if not (p == want or p.endswith(want) or want.endswith(p)):
                continue
            if want_success is not None:
                # Polarity has to match, or the link claims the page's error
                # state renders a 200. A UI `=ready` corresponds to a 2xx and a
                # UI `=error` to a non-2xx; where the API model has no failing
                # outcome, the error state links to nothing — which is itself
                # worth seeing, not a reason to attach it to the success.
                status = row["status"] or 0
                if want_success != (200 <= status < 300):
                    continue
            out.append(row["id"])
        return out

    # Two claims, two edge kinds (M-5a).
    #
    #   TRIGGERS  the `open <Page>` action starts every call the page makes.
    #             One-to-many; the Web flow then continues on its own.
    #   INVOKES   a region's outcome transition rendered one API outcome.
    #             One-to-one, and only where the region names the endpoint.
    OPEN_ID = re.compile(r"^(?P<model>[^:]+)::ui::(?P<screen>[^:]+)::open$")
    links = LinkSet(journey="athena")
    for call in facts.get("api_calls", ()):
        screen, endpoint = call.get("screen"), call.get("endpoint")
        if not screen or not endpoint:
            continue
        evidence = {"endpoint": endpoint, "screen": screen}
        proposer = f"react-ui@{facts.get('pack_version','?')}"

        for row in ui_rows:
            opener = OPEN_ID.match(row["id"])
            if opener and opener.group("screen") == screen:
                journey = opener.group("model").rsplit("-", 1)[0]
                for api_id in api_for(endpoint, journey):
                    links.triggers.append(InvokesLink(
                        row["id"], api_id, proposer, evidence, ""))
                continue

            m = UI_ID.match(row["id"])
            # The region must be named in the endpoint, or this is a different
            # panel of the same screen. Linking every region of a screen to every
            # endpoint it calls would propose relationships nobody observed.
            if not m or m.group("screen") != screen:
                continue
            region = m.group("region")
            if region.lower() in endpoint.lower():
                journey = m.group("model").rsplit("-", 1)[0]
                wants_success = row["id"].endswith("::ready")
                for api_id in api_for(endpoint, journey, wants_success):
                    links.links.append(InvokesLink(
                        row["id"], api_id, proposer, evidence, ""))

    def dedupe(rows):
        seen, out = set(), []
        for link in rows:
            key = (link.ui_transition_id, link.api_transition_id)
            if key not in seen:
                seen.add(key)
                out.append(link)
        return out

    unique = LinkSet(journey="athena", links=dedupe(links.links),
                     triggers=dedupe(links.triggers))
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
echo "Review with:  python3 -m metis_mcp.mbt.cli review export --journey <j> --surface <s> -o r.json"
