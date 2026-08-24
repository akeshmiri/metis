"""
The agent / MCP surface (application spec §9.5, N-8).

**Read-only, and structurally so.** N-8 says no decision may be taken through
this surface, because a decision requires the evidence presentation N-3
specifies and an agent session cannot provide it. That is enforced here by
composition rather than by discipline: every tool below calls a *query*
function, none imports `review.decisions`, `publishing.publish` or
`model_sources.landing`, and `test_mcp_server.py` asserts that no write-path
module is reachable from this one.

The distinction matters because the failure it prevents is quiet. A tool that
approves a model from a chat session would produce exactly the artefact the two
human gates exist to prevent, and it would look like helpfulness.

**Why this file was missing.** `plugins/metis-mcp/.mcp.json` has pointed at
`metis_mcp.server` since the plugin was written, and the module went away with
the v1 engine -- so anyone installing the plugin got a server that failed at
startup. Six skills called tools it used to expose. This restores the surface
against the current engine rather than deleting the plugin, because §9.5 is a
specified interface and the query functions it needs all exist.
"""
from __future__ import annotations

import json
import os
import sys

from mcp.server.fastmcp import FastMCP

from metis_mcp.mbt.graph_loader import load_from_graph
from metis_mcp.mbt.graph_session import GraphNotConfigured, session

mcp = FastMCP("metis")

# What a read-only surface says when it cannot reach the graph. Distinct from
# "nothing found", which is a different answer with a different consequence.
_NOT_CONFIGURED = {
    "ok": False,
    "reason": ("no graph is configured — set METIS_NEO4J_URI / METIS_NEO4J_USER "
               "and provide METIS_NEO4J_PASSWORD in the environment (PLT-005: "
               "never as an argument)"),
}


# `ok` is the one field a refusal cannot afford to lose, and `ok: false` is
# exactly what pruning False removes. Every error response was going out without
# it -- a caller reading `payload["ok"]` got a KeyError, and the test that was
# meant to catch this asserted on the dict rather than on the serialised bytes.
#
# `may_author` and `may_decide` join it for the same reason one step further on:
# they are answers to "can I write here", and `false` is the answer that matters.
# Pruned, `describe_policy` reported `may_decide: null` on a surface that
# definitely could not decide -- a reader cannot tell "no" from "not mentioned",
# and this is the one tool whose entire job is to be unambiguous about that.
_ALWAYS_KEPT = frozenset({"ok", "may_author", "may_decide"})


def _prune(value):
    """Drop what carries no information, recursively.

    Measured on the largest demo model (11 states, 46 transitions): `security`
    was an empty list on 46 transitions out of 46, and `source_state_unresolved`
    false on 43. Serialising those cost about a fifth of the response and told a
    reader nothing that its absence does not.

    Absent therefore means null, empty, or false -- except for the status field
    `ok`, which is always carried. Every tool below says so in its own
    description, because a convention a caller has to infer is a convention that
    will be inferred wrongly.
    """
    if isinstance(value, dict):
        return {k: _prune(v) for k, v in value.items()
                if k in _ALWAYS_KEPT
                or (v is not None and v != "" and v != [] and v is not False)}
    if isinstance(value, list):
        return [_prune(v) for v in value]
    return value


def _json(payload) -> str:
    """Compact, pruned JSON.

    `indent=2` was 27% of every response — about 2,900 tokens on one
    `get_model` call — spent on whitespace for a reader that does not need it.
    """
    return json.dumps(_prune(payload), separators=(",", ":"))


def _load(journey: str, surface: str):
    with session() as s:
        return load_from_graph(s, journey, surface)


def _no_such_model(s, journey: str, surface: str) -> dict:
    """The refusal for a `<journey>-<surface>` the graph does not hold.

    Necessary because an empty `Model` is what a typo produces, and every tool
    downstream of it reports cheerfully on nothing: `get_model` returned
    `ok: true` with zero states, and `coverage` returned a structurally complete
    ledger with `uncovered: 0` — which reads as "nothing is uncovered". The
    available pairs are listed because the mistake is nearly always a near-miss.
    """
    from metis_mcp.mbt.graph_loader import available_models

    pairs = available_models(s)
    return {
        "ok": False,
        "reason": (f"no model '{journey}-{surface}' — the graph holds no state "
                   f"or transition for journey {journey!r} on surface "
                   f"{surface!r}"),
        "available": [{"journey": j, "surface": sf} for j, sf in pairs],
        "note": ("`journey` is the journey, not the model id: pass 'mfa', not "
                 "'mfa-api'" if journey.endswith(f"-{surface}") else ""),
    }


@mcp.tool()
def list_workflows() -> str:
    """Every defined workflow, its ordered stages, and where it stops for a human."""
    from metis_mcp.workflow.stages import WORKFLOWS

    return _json({
        "workflows": [
            {
                "code": code,
                "summary": w.summary,
                "stages": [
                    {"ordinal": s.ordinal, "name": s.name, "gate": s.is_gate,
                     "blocking": s.blocking}
                    for s in w.ordered
                ],
                "preconditions": list(w.preconditions),
                "entry_patterns": list(w.entry_patterns),
            }
            for code, w in sorted(WORKFLOWS.items())
        ]
    })


@mcp.tool()
def route_request(request: str) -> str:
    """Which workflow a request maps to. Returns null when it does not match one.

    A null is an answer, not a failure: guessing which workflow was meant is how
    a run lands in the wrong place and produces a confident artefact about the
    wrong thing.
    """
    from metis_mcp.workflow.routing import route

    code, why = route(request)
    return _json({"workflow": code, "why": why})


@mcp.tool()
def get_model(journey: str, surface: str = "api", detail: bool = False) -> str:
    """One model's states and transitions, as they stand in the graph.

    Returns a summary — counts, state names, transition ids — unless `detail` is
    true, which adds each transition's trigger, guard, outcome and inputs.
    Ask for detail when you need to reason about specific behaviour; the summary
    answers "what is in this model" for a tenth of the size.

    Fields that are null, empty or false are omitted.
    """
    try:
        with session() as s:
            report = load_from_graph(s, journey, surface)
            if not report.found:
                return _json(_no_such_model(s, journey, surface))
    except GraphNotConfigured:
        return _json(_NOT_CONFIGURED)

    model = report.model
    payload = {
        "ok": True,
        "model_id": model.id,
        "states": [
            {"id": s.id, "name": s.name, "is_initial": s.is_initial,
             "lifecycle_state": s.lifecycle_state}
            for s in model.states.values()
        ],
        # F-10: what was left out is named rather than quietly absent. Kept in
        # both shapes -- a summary that hides its own omissions is worse than no
        # summary.
        "skipped": [{"id": i, "reason": r} for i, r in report.skipped],
    }

    if not detail:
        # Deliberately NOT the transition ids. On a recovered model an id is a
        # fully-qualified method signature -- 46 of them were 7,397 of this
        # summary's 8,405 characters, which is the detail payload wearing a
        # summary's name. What orients a reader is how many transitions there
        # are and how their outcomes distribute; addressing a specific one
        # needs detail=true anyway.
        outcomes: dict[str, int] = {}
        for t in model.transitions.values():
            outcomes[t.outcome_status or "unclassified"] = (
                outcomes.get(t.outcome_status or "unclassified", 0) + 1)
        payload["counts"] = {"states": len(model.states),
                             "transitions": len(model.transitions)}
        payload["transitions_by_outcome"] = dict(sorted(outcomes.items()))
        payload["detail_available"] = (
            "call again with detail=true for each transition's id, trigger, "
            "guard, outcome and inputs")
        return _json(payload)

    payload["transitions"] = [
        {"id": t.id, "source": t.source, "trigger": t.trigger,
         "target": t.target, "guard": t.guard,
         "outcome_status": t.outcome_status,
         "guard_anchor": t.guard_anchor,
         "source_state_unresolved": t.source_state_unresolved,
         "inputs": list(t.inputs), "security": list(t.security),
         "lifecycle_state": t.lifecycle_state}
        for t in model.transitions.values()
    ]
    return _json(payload)


@mcp.tool()
def validate_model(journey: str, surface: str = "api") -> str:
    """Well-formedness findings, by severity (§2.6, M-17).

    The three severities are not synonyms. `unverifiable` means the property
    could not be *shown*, which is neither a pass nor a defect, and collapsing it
    into either is how an unparseable guard reads as fine.
    """
    from metis_mcp.mbt.validation import validate

    try:
        with session() as s:
            report = load_from_graph(s, journey, surface)
            if not report.found:
                return _json(_no_such_model(s, journey, surface))
    except GraphNotConfigured:
        return _json(_NOT_CONFIGURED)

    result = validate(report.model)
    return _json({
        "ok": True,
        "model_id": result.model_id,
        "checked": result.checked,
        "blocking": [f.describe() for f in result.blocking],
        "unverifiable": [f.describe() for f in result.unverifiable],
        "advisory": [f.describe() for f in result.advisory],
        "generation_would_be_blocked": not result.is_valid(),
    })


# Two fields on every row used to be `covered` and `how`, and `LedgerRow` has
# never had either -- so this tool raised `AttributeError` for any model that
# produced a single row, and no test caught it because none called it. Kept here
# rather than in the docstring: the docstring is loaded into every request, and
# this is repo history a caller cannot act on.
@mcp.tool()
def impact(changed_files: list[str]) -> str:
    """Which recovered behaviour a set of changed files touches.

    Pass what `git diff --name-only` prints. Returns the transitions recovered
    from those files, the evidence each was reached through, and the criteria
    that validate them — so a reviewer can see what a change puts at risk before
    merging it.

    **Read-only and safe pre-merge.** It queries the graph and never the
    repository, so it is current only as of the last extraction; the commits it
    matched against come back with the answer. A file that matched nothing is
    named rather than counted as "no impact" — those are different answers.

    Matching is on path suffix, because an anchor holds the path the CPG
    recorded and a diff path rarely shares its root.

    Fields that are null, empty or false are omitted.
    """
    from metis_mcp.impact import impact as _impact

    try:
        return _json(_impact(changed_files))
    except GraphNotConfigured:
        return _json(_NOT_CONFIGURED)


@mcp.tool()
def coverage(journey: str, surface: str = "api",
             criterion: str = "all-transitions",
             detail: bool = False) -> str:
    """The coverage ledger for a model under a criterion (§6.8b).

    Records **coverage, not outcome**: answers "is this behaviour tested?" and
    never "is it working?" (C-11). No execution result is read, because none is
    ingested (§8.7). States the version and commit the figure refers to (P-16).

    `mechanism` is direct / indirect / initiated, and the distinction is
    load-bearing: `initiated` is reported and never counted (C-1).

    Returns totals and the uncovered transitions unless `detail` is true, which
    adds a row per transition. Fields that are null, empty or false are omitted.
    """
    from metis_mcp.mbt.coverage import COVERING_MECHANISMS, build_ledger
    from metis_mcp.mbt.graph_loader import load_component, load_validating_criteria
    from metis_mcp.mbt.path_generation import generate

    # One session for all three reads. Two would be two chances for the graph to
    # change underneath a single reported figure.
    try:
        with session() as s:
            report = load_from_graph(s, journey, surface)
            if not report.found:
                return _json(_no_such_model(s, journey, surface))
            model = report.model
            component = load_component(s, journey, surface)
            validating = load_validating_criteria(s, journey, surface)
    except GraphNotConfigured:
        return _json(_NOT_CONFIGURED)

    result = generate(model, criterion, 10)
    ledger = build_ledger(model, result, component=component,
                          validating_criteria=validating)
    summary = ledger.summary()
    payload = {
        "ok": True,
        "model_id": model.id,
        "criterion": criterion,
        # P-16 -- null when no Component has been persisted for this model, which
        # is a reported state and not a silent omission. `_prune` would drop a
        # null, so the absence is spelled out instead.
        "component": summary["component"] or "not recorded (P-16)",
        "version": summary["version"] or "not recorded (P-16)",
        "commit": summary["commit"] or "not recorded (P-16)",
        "paths": len(result.paths),
        "paths_with_setup": sum(1 for p in result.paths if p.setup_length),
        "covered": summary["covered"],
        "uncovered": summary["uncovered"],
        "criteria_covered": ledger.criteria_covered(),
        "criteria_uncovered": ledger.criteria_uncovered(),
        # Never summarised away: an uncovered transition is the actionable half
        # of a coverage report, and a total alone is the number C-11 warns about.
        "uncovered_detail": [{"transition_id": t, "reason": why}
                             for t, why in ledger.uncovered],
        "means": "what is TESTED, not what is WORKING (C-11)",
    }

    if detail:
        payload["rows"] = [
            {"transition_id": r.transition_id,
             "mechanism": r.mechanism,
             "counts_as_covered": r.mechanism in COVERING_MECHANISMS,
             "test_case_id": r.test_case_id,
             "criterion_ids": list(r.criterion_ids),
             "note": r.note}
            for r in ledger.rows
        ]
    else:
        payload["rows"] = len(ledger.rows)
        payload["detail_available"] = "call again with detail=true for a row per transition"
    return _json(payload)


# ---------------------------------------------------------------------------
# The knowledge surface (§4.6a, §18; F-12)
#
# Documents live in the graph, not in files, so serving one is a query rather
# than a re-render. That is also why these belong here: a skill that carried
# document text would be a second copy of facts the graph already holds, paid
# for on every invocation.
#
# Every function below reads. None imports `specgen.documents`, which pulls in
# `model_sources.landing` -- `test_mcp_server.py` asserts that, and it is the
# reason `get_entity` reads a stored document instead of rendering one.
# ---------------------------------------------------------------------------

@mcp.tool()
def list_entities(area: str = "") -> str:
    """Every business noun Métis knows, optionally within one area.

    A business entity is what a criterion is *about* — `record`, `user`,
    `session` — carrying what it is, what changes when you act on it, and the
    properties it has. Narrow with `area` when a domain is known.

    Fields that are null, empty or false are omitted.
    """
    from metis_mcp.mbt.graph_loader import load_entities

    try:
        with session() as s:
            rows = load_entities(s, area=area)
    except GraphNotConfigured:
        return _json(_NOT_CONFIGURED)

    return _json({
        "ok": True,
        "count": len(rows),
        "area": area,
        "entities": [
            {"id": r.get("id"), "name": r.get("name"),
             "area": r.get("area_name") or r.get("area"),
             "description": r.get("description")}
            for r in rows
        ],
        "detail_available": "call get_entity(name) for one entity's full specification",
    })


@mcp.tool()
def get_entity(name: str, detail: bool = False) -> str:
    """One business entity: what it is, its properties, and what acting on it changes.

    By id or by name. Returns the definition by default; `detail` adds the
    rendered specification document, including every acceptance criterion that
    references this entity and the provenance grade of each.

    A criterion graded `code_derived` was written from the code, so its agreeing
    with the code is evidence of coverage and never of correctness (§4.1).

    Fields that are null, empty or false are omitted.
    """
    from metis_mcp.mbt.graph_loader import (
        load_entity, load_entity_criteria, load_entity_document,
    )

    try:
        with session() as s:
            entity = load_entity(s, name)
            if entity is None:
                return _json({"ok": False,
                              "reason": f"no business entity {name!r}"})
            criteria = load_entity_criteria(s, entity["id"])
            document = load_entity_document(s, name) if detail else None
    except GraphNotConfigured:
        return _json(_NOT_CONFIGURED)

    from metis_mcp.specgen.entity import build

    spec = build(entity, criteria, area_name=entity.get("area_name") or "")
    payload = {
        "ok": True,
        "id": spec.entity_id,
        "name": spec.name,
        "area": spec.area_name,
        "description": spec.description,
        "impact": list(spec.impact),
        "properties": [
            {"name": p.name, "meaning": p.meaning, "values": list(p.values)}
            for p in spec.properties
        ],
        "criteria_count": len(spec.rules),
        # The distinction that separates a coverage claim from a correctness one.
        "criteria_by_provenance": {
            "intent": len(spec.intent_rules),
            "code_derived": len(spec.code_derived_rules),
        },
        "means": "code_derived criteria give coverage, never correctness (§4.1)",
    }

    if not detail:
        payload["detail_available"] = (
            "call again with detail=true for the criteria and the rendered document")
        return _json(payload)

    payload["criteria"] = [
        {"id": r.criterion_id, "text": r.text, "provenance": r.provenance,
         "is_intent": r.is_intent, "lifecycle_state": r.lifecycle_state,
         "requirement_id": r.requirement_id,
         "validates": list(r.transition_ids)}
        for r in spec.rules
    ]
    if document is not None:
        payload["document"] = {
            "id": document.get("id"),
            "rendered_at": document.get("rendered_at"),
            "content_hash": document.get("content_hash"),
            "lifecycle_state": document.get("lifecycle_state"),
            "body_markdown": document.get("body_markdown"),
        }
    else:
        # F-10: named rather than quietly absent. "Not rendered yet" and "has no
        # content" are different answers with different next steps.
        payload["document"] = None
        payload["document_note"] = (
            "no entity document has been rendered — run `entity render`")
    return _json(payload)


@mcp.tool()
def get_spec(journey: str, surface: str = "api", detail: bool = False) -> str:
    """The stored specification for one journey, as a stakeholder reads it.

    Generated from the model and landed in the graph, so this is a lookup rather
    than a re-render. Returns the document's identity and the component version
    it describes; `detail` adds the markdown body.

    Fields that are null, empty or false are omitted.
    """
    from metis_mcp.mbt.graph_loader import load_spec_document

    try:
        with session() as s:
            document = load_spec_document(s, journey, surface)
    except GraphNotConfigured:
        return _json(_NOT_CONFIGURED)

    if document is None:
        return _json({
            "ok": False,
            "reason": (f"no specification has been rendered for "
                       f"{journey}-{surface} — run `spec <model> --land`"),
        })

    payload = {
        "ok": True,
        "id": document.get("id"),
        "name": document.get("name"),
        "component_id": document.get("component_id"),
        "version": str(document.get("version") or "") or None,
        "commit": document.get("commit_sha"),
        "rendered_at": document.get("rendered_at"),
        "content_hash": document.get("content_hash"),
        "lifecycle_state": document.get("lifecycle_state"),
    }
    if detail:
        payload["body_markdown"] = document.get("body_markdown")
    else:
        payload["detail_available"] = "call again with detail=true for the document body"
    return _json(payload)


@mcp.tool()
def get_requirement(requirement_id: str, detail: bool = False) -> str:
    """One requirement, its acceptance criteria, and where it came from.

    Returns the requirement and its provenance counts by default; `detail` adds
    every acceptance criterion in full.

    `anchors` names the artefact in the world the requirement was derived from —
    a Jira issue, a Confluence page, an OpenAPI document. That is a different
    fact from the Episode that ingested it: an anchor survives its Requirement
    being rejected.

    Fields that are null, empty or false are omitted.
    """
    from metis_mcp.mbt.graph_loader import load_requirement

    try:
        with session() as s:
            row = load_requirement(s, requirement_id)
    except GraphNotConfigured:
        return _json(_NOT_CONFIGURED)

    if row is None:
        return _json({"ok": False, "reason": f"no requirement {requirement_id!r}"})

    criteria = row.get("criteria") or []
    intent = [c for c in criteria
              if c.get("provenance") in ("human_confirmed", "independently_authored")]
    payload = {
        "ok": True,
        "id": row.get("id"),
        "text": row.get("text"),
        "statement": row.get("statement"),
        "ears_pattern": row.get("ears_pattern"),
        "area": row.get("area"),
        "lifecycle_state": row.get("lifecycle_state"),
        "criteria_count": len(criteria),
        "criteria_by_provenance": {
            "intent": len(intent),
            "code_derived": len(criteria) - len(intent),
        },
        "anchors": [{"kind": a.get("label"), "id": a.get("id")}
                    for a in (row.get("anchors") or [])],
    }
    if detail:
        payload["criteria"] = criteria
    else:
        payload["detail_available"] = "call again with detail=true for the criteria"
    return _json(payload)


@mcp.tool()
def search_knowledge(query: str, limit: int = 20) -> str:
    """Find business entities, requirements and acceptance criteria by term.

    Which of the three matched is part of the answer: an entity tells you what a
    noun means, a requirement what was asked for, a criterion what must be true.
    Results are grouped rather than merged, because the next step differs.

    Fields that are null, empty or false are omitted.
    """
    from metis_mcp.mbt.graph_loader import search_knowledge as _search

    if not query.strip():
        return _json({"ok": False, "reason": "an empty query matches everything; "
                                             "give a term"})
    try:
        with session() as s:
            rows = _search(s, query, limit=limit)
    except GraphNotConfigured:
        return _json(_NOT_CONFIGURED)

    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row["label"], []).append({
            "id": row.get("id"),
            "name": row.get("name"),
            "body": (row.get("body") or "")[:200],
            "lifecycle_state": row.get("lifecycle_state"),
            "provenance": row.get("provenance"),
        })

    return _json({
        "ok": True,
        "query": query,
        "count": len(rows),
        "truncated": len(rows) >= limit,
        "results": grouped,
    })


@mcp.tool()
def run_status(run_id: str) -> str:
    """Where a workflow run got to, and what it is waiting for."""
    from metis_mcp.workflow.run import RunRecord, run_path

    record = RunRecord.load(run_path(run_id))
    if record is None:
        return _json({"ok": False, "reason": f"no run {run_id!r}"})
    blocked = record.outcome_for(record.blocked_on) if record.is_blocked else None
    return _json({
        "ok": True,
        "run_id": record.run_id,
        "workflow": record.workflow,
        "scope": record.scope,
        "blocked_on": record.blocked_on,
        "failed_reason": record.failed_reason,
        "complete": record.is_complete,
        "stages": [
            {"ordinal": o.ordinal, "stage": o.stage, "outcome": o.outcome,
             "detail": o.detail}
            for o in record.outcomes
        ],
        "outstanding": list(blocked.outstanding) if blocked else [],
        "next_command": blocked.next_command if blocked else "",
    })


@mcp.tool()
def why_read_only() -> str:
    """Why this surface cannot approve, publish or land anything (N-8)."""
    return _json({
        "rule": "N-8",
        "statement": ("Read-only. No decision may be taken through the agent "
                      "surface — decisions require the evidence presentation of "
                      "N-3, which a chat session cannot provide."),
        "where_decisions_are_taken": [
            "the web review UI (§9.3), which blocks a decision it cannot evidence",
            "review export / review apply, as a diffable file (N-7)",
        ],
        "gates": {
            "G1": "model approval, between reconcile and generation",
            "G2": "publication, requiring a literal affirmative in the same run",
        },
    })


# Transports FastMCP offers. `stdio` stays the default: it is what a local MCP
# client launches, and it is the only one that needs no network at all.
TRANSPORTS = ("stdio", "sse", "streamable-http")
TRANSPORT_ENV = "METIS_MCP_TRANSPORT"
HOST_ENV = "METIS_HTTP_HOST"
PORT_ENV = "METIS_HTTP_PORT"


# ---------------------------------------------------------------------------
# Authoring: how to call it, and how it works (X-6e).
#
# Read-only, so these belong here rather than in the write half — the surface at
# `METIS_MCP_WRITE=off` is read-only **by construction**, and a query that writes
# nothing has no business behind a write switch. (`read.get_transition` is behind
# one for historical reasons its own comment admits to.)
# ---------------------------------------------------------------------------
from metis_mcp import authoring as _authoring

for _fn in (_authoring.call_recipe, _authoring.auth_facts,
            _authoring.payload_shape, _authoring.journey_walkthrough,
            _authoring.ask):
    mcp.tool()(_fn)


# ---------------------------------------------------------------------------
# The write half (the change to N-8).
#
# Registered only when `METIS_MCP_WRITE` says so, and `off` is the default — so
# an unconfigured server is exactly the read-only surface it has always been,
# and the nineteen read-only tools are unchanged. Enabling writes is a deployment
# decision somebody makes, never a consequence of upgrading.
#
# The tools are registered here rather than in the modules so that this file
# stays the whole inventory of what the surface exposes: `grep '@mcp.tool'` has
# to keep answering "what can an agent do", which is the question N-8 used to
# answer by construction and now answers by enumeration.
# ---------------------------------------------------------------------------

def _register_write_tools() -> list[str]:
    """Register the author group, and return what was registered."""
    from metis_mcp import policy

    if not policy.may_author():
        # **The import stays inside the branch, and that is the point.** With
        # writes off, `metis_mcp.write` is never imported, so no write path
        # is reachable from this module at all -- N-8 still holds *by
        # construction* for the default deployment, and `test_mcp_server.py`'s
        # subprocess check still proves it. Importing at the top and branching
        # here would have quietly turned that proof into a policy check.
        return []

    from metis_mcp import write

    registered = []
    for fn in (write.land_model, write.land_knowledge, write.land_findings):
        mcp.tool()(_wrap_write(fn))
        registered.append(fn.__name__)

    # A read query, registered with the write group only because it did not
    # exist before this package did. It writes nothing.
    from metis_mcp import read

    mcp.tool()(_wrap_write(read.get_transition))
    registered.append(read.get_transition.__name__)

    from metis_mcp import flow

    for fn in (flow.run_workflow, flow.resume_workflow):
        mcp.tool()(_wrap_write(fn))
        registered.append(fn.__name__)

    if policy.may_decide():
        # `review_queue` rides with the gate group rather than with the read
        # tools on purpose: its whole output is the evidence for a decision, and
        # a surface that cannot decide would be handing out a fingerprint no
        # tool it exposes can spend.
        from metis_mcp import decide

        for fn in (decide.review_queue, decide.approve_elements,
                   decide.reject_elements, decide.defer_elements):
            mcp.tool()(_wrap_write(fn))
            registered.append(fn.__name__)
    return registered


def _wrap_write(fn):
    """Serialise like every read tool, and turn a refusal into an answer.

    A refused write is a *result* — "you are a contributor and may not approve"
    is information the caller can act on. Letting it propagate as an exception
    gives an agent a stack trace and no next step.
    """
    import functools

    from metis_mcp.policy import ConfirmationRefused, WriteDisabled
    from metis_mcp.review.roles import NotPermitted

    @functools.wraps(fn)
    def tool(*args, **kwargs) -> str:
        try:
            return _json(fn(*args, **kwargs))
        except (WriteDisabled, NotPermitted, ConfirmationRefused) as e:
            return _json({"ok": False, "refused": str(e),
                          "rule": type(e).__name__})
        except GraphNotConfigured:
            return _json(_NOT_CONFIGURED)

    return tool


@mcp.tool()
def describe_policy() -> str:
    """What this surface may write, what it may not, and which gates apply.

    Replaces `why_read_only` when writes are enabled. Read it before assuming a
    write will work: the answer depends on deployment configuration, on the
    role you pass, and — for the two gates — on a literal word.
    """
    from metis_mcp import policy

    described = policy.describe()
    described["registered_write_tools"] = _WRITE_TOOLS
    return _json(described)


_WRITE_TOOLS = _register_write_tools()


def main() -> None:
    """Serve the tools above, over stdio unless the environment says otherwise.

    **This used to be `mcp.run()` and nothing else, which made the container
    image undeliverable.** `Dockerfile.mcp-server` sets `ENV METIS_HTTP_PORT=8090`
    and `EXPOSE 8090`, and its `CMD` is this function — so a detached container
    published a port that nothing ever listened on, while the process sat waiting
    on a stdin no one was attached to. The Dockerfile was not wrong; it was
    describing an intent this function had never implemented.

    Read-only is unaffected (N-8). A transport changes who can reach the tools,
    not what they can do, and none of them writes.
    """
    transport = os.environ.get(TRANSPORT_ENV, "stdio").strip() or "stdio"
    if transport not in TRANSPORTS:
        # A halt, not a fallback to stdio: silently serving a transport the
        # operator did not ask for is how a container "starts fine" and is
        # unreachable, which is the failure this function just had.
        raise SystemExit(
            f"{TRANSPORT_ENV}={transport!r} is not one of {', '.join(TRANSPORTS)}."
        )

    if transport == "stdio":
        mcp.run()
        return

    host = os.environ.get(HOST_ENV, "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.environ.get(PORT_ENV, "8090"))
    if host not in ("127.0.0.1", "localhost", "::1"):
        # The same warning `review_ui.serve` prints, for the same reason and with
        # a different consequence: there is no authentication here either, and
        # while these tools cannot decide anything, they will read out every
        # requirement, criterion and specification in the graph to whoever asks.
        print(f"WARNING: binding {host}. This surface does not authenticate. It "
              f"cannot approve or publish (N-8), but it will read out the whole "
              f"knowledge graph to anyone who reaches it.", file=sys.stderr)
    mcp.settings.host = host
    mcp.settings.port = port
    print(f"metis MCP ({transport}) on {host}:{port}", file=sys.stderr)
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
