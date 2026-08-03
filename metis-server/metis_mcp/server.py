"""
Métis MCP server -- dogfooding pilot, stdio transport.

Implements the 12 tools from metis-mcp-tool-contracts.json against the
LocalGraphStore (this platform's own real REQ-METIS-*/CONST-*/DQ-*/AF-*/BS-*
corpus). This is the fastest honest path to testing on Claude first, per
§11.5 of the master spec -- stdio transport needs no OAuth2, no Streamable
HTTP, no Kubernetes deployment. The production path (Streamable HTTP + OAuth2,
§11.2, deployed via the Helm chart's mcp-server component) is unchanged and
still the target for real multi-team rollout -- this server is the Phase 0
dogfooding step, not a replacement for that design.

Honesty notes on where dogfooding-mode necessarily adapts the production
contract, rather than silently pretending it's identical:
  - metis_impact_analysis's real contract takes `changed_files`/`diff` (code-
    level input, §9.2's design). The dogfooding corpus has no code graph --
    only this platform's own text documents. Adapted here to accept a
    `node_id` directly as a practical stand-in, clearly labeled as such in
    the tool's response, not disguised as the full production behavior.
  - metis_propose_test_skeleton and metis_submit_episode have no meaningful
    real behavior against a text-only self-referential corpus (there's no
    Transition/TestCase ontology populated here) -- both return an honest
    "not applicable in dogfooding mode" response rather than a fabricated one.
  - metis_quality_score's composite is computed from real, available
    corpus-wide statistics (orphan rate by kind) -- a genuine subset of the
    full DQ framework (metis-data-quality-framework.md's 22 metrics), not
    a fabricated full score. Its `scope` input is a plain string, not the
    contract's object (oneOf release_id/service_id/requirement_id/
    project_wide) -- graph.backend=neo4j computes the real thing
    (metis_mcp/dq_metrics.py) but still under a different top-level shape
    (quality_score/components, not composite_score/dimension_breakdown/
    gate_status).

CONST-062 (docs/metis-gap-remediation.md §7) requires real contract tests
against metis-mcp-tool-contracts.json -- test_mcp_contracts.py is that
test, and building it surfaced more than the three adaptations above:
**every one of the 12 tools currently deviates from the full production
contract shape in some way** when run against this Phase 0 server (the
three newest, metis_generate_quality_report/metis_generate_release_report/
metis_generate_test_design_report, need the real Requirement/Service/
Release/Intent/TestDesign ontology graph.backend=neo4j provides -- same
"adapted" pattern as metis_propose_test_skeleton/metis_submit_episode
already used against a text-only corpus). Most of
that (metis_explain_decision/metis_explain_answer's decisions[]/sources[]
shape, metis_get_context's graded-fact/pinned-context shape which needs
§8.1/§8.2 -- not yet built, metis_get_traceability's chain[] shape and
up/down vs upstream/downstream enum, metis_check_coverage's missing
`stale` field) was NOT previously disclosed here. test_mcp_contracts.py's
own CASES dict is now the accurate, current, per-tool record of exactly
what conforms and what doesn't and why -- this docstring summarizes it,
that file is the source of truth if the two ever disagree. None of this
is a defect to silently patch over: the full production shape depends on
retrieval/provenance machinery (§8.1 pinned memory, §8.2 hybrid retrieval,
full Episode-backed decision tracking) that doesn't exist yet against a
text-only self-referential corpus -- reproducing the contract's exact
shape here would mean fabricating fields with no real data behind them,
exactly what this project's no-fabrication discipline exists to prevent.
"""
import os
import sys
import glob as glob_module

from mcp.server.fastmcp import FastMCP
from metis_mcp.graph_store import LocalGraphStore
from metis_mcp.neo4j_graph_store import Neo4jGraphStore
from metis_mcp.config_manager import ConfigManager
from metis_mcp.test_skeleton_generator import propose_test_skeletons
from metis_mcp.token_optimization import compress_response_headroom, stabilize_temporal_fields
from metis_mcp.academy import next_step_guidance

# No hardcoded corpus path here -- resolved entirely from Métis's config
# manager (project-level .metis/config.yaml, or host-level ~/.metis/config.yaml).
# If neither exists, ConfigManager() raises ConfigNotFoundError -- deliberately
# not caught here, since a missing config is a setup gap to fix, not
# something the server should paper over with an assumed default.
_config = ConfigManager()
_corpus_glob = _config.get_corpus_glob()
if not _corpus_glob:
    raise ValueError(
        "corpus.glob is not set in the resolved Métis config "
        f"({_config.effective_path}) -- see metis.config.example.yaml."
    )
# Resolve relative to the config file's own directory, not the process's cwd,
# so "corpus/*.md" means "next to this config file" regardless of where the
# server is launched from.
if not os.path.isabs(_corpus_glob):
    CORPUS_GLOB = str(_config.effective_path.parent.parent / _corpus_glob)
else:
    CORPUS_GLOB = _corpus_glob

mcp = FastMCP("metis")

# Backend selection resolved entirely through config (graph.backend), not a
# raw env var read here -- consistent with the no-config-in-code rule the
# rest of this file already follows for the corpus path above.
_graph_backend = _config.get_graph_backend()
if _graph_backend == "local":
    store = LocalGraphStore(CORPUS_GLOB)
elif _graph_backend == "neo4j":
    _neo4j_cfg = _config.get_neo4j_config()
    _uri = _neo4j_cfg.get("uri")
    _user = _neo4j_cfg.get("user")
    _password_env = _neo4j_cfg.get("password_env")
    if not (_uri and _user and _password_env):
        raise ValueError(
            f"graph.neo4j.{{uri,user,password_env}} must all be set in "
            f"{_config.effective_path} when graph.backend is 'neo4j'."
        )
    _password = os.environ.get(_password_env)
    if not _password:
        raise ValueError(f"Environment variable {_password_env} is not set.")
    store = Neo4jGraphStore(_uri, _user, _password)
else:
    raise ValueError(
        f"Unknown graph.backend '{_graph_backend}' in {_config.effective_path} "
        f"-- expected 'local' or 'neo4j'."
    )

# §9.1 Headroom-style compression: opt-in (REQ-METIS-COST-01 calls this a
# guardrail-boundary control, not a silent default). Applied only to the
# 3 tools the spec table names (metis_get_context, metis_get_traceability,
# metis_impact_analysis) -- never to metis_explain_decision/_answer (their
# `explanation`/`rationale` text IS the user-facing content, not RAG
# scaffolding around it) or to write/score tools.
_token_opt_cfg = _config.get_token_optimization_config()
_HEADROOM_ENABLED = bool(_token_opt_cfg.get("headroom_enabled", False))


def _apply_headroom(response: dict) -> dict:
    if not _HEADROOM_ENABLED:
        return response
    return compress_response_headroom(stabilize_temporal_fields(response))


@mcp.tool()
def metis_get_context(anchor: str, client: str = "claude", include_draft_tier: bool = False) -> dict:
    """Retrieve context for a given anchor (a REQ-METIS-*/CONST-*/DQ-*/AF-*/BS-* id)."""
    node = store.get_node(anchor)
    if not node:
        # REQ-METIS-ACD-04: a concrete next action, not just a flag.
        return {"found": False, "anchor": anchor, "note": "No matching item in the dogfooding corpus.",
                "next_step": next_step_guidance("not_found")}
    return _apply_headroom({
        "found": True,
        "id": node.id,
        "kind": node.kind,
        "text": node.text,
        "source_file": node.source_file,
        "source_heading": node.source_heading,
        "references": node.references,
        "referenced_by": node.referenced_by,
        "client": client,
    })


@mcp.tool()
def metis_get_traceability(node_id: str, direction: str = "both") -> dict:
    """Full upstream/downstream traceability chain for a node, real BFS over the corpus."""
    chain = store.traceability_chain(node_id)
    if chain is None:
        return {"found": False, "node_id": node_id, "next_step": next_step_guidance("not_found")}
    # Same key on both branches -- found via test_mcp_contracts.py (CONST-062):
    # a caller reading response["node_id"] unconditionally would KeyError on
    # the found path, which used "id" instead.
    result = {"found": True, "node_id": node_id, "id": node_id}
    if direction in ("both", "upstream"):
        result["upstream"] = chain["upstream"]
    if direction in ("both", "downstream"):
        result["downstream"] = chain["downstream"]
    return _apply_headroom(result)


@mcp.tool()
def metis_check_coverage(target_id: str) -> dict:
    """Is this item referenced by anything else in the corpus (a real proxy for coverage)?"""
    neighbors = store.neighbors(target_id)
    if neighbors is None:
        return {"found": False, "target_id": target_id, "next_step": next_step_guidance("not_found")}
    covered = len(neighbors["referenced_by"]) > 0
    return {
        "found": True,
        "target_id": target_id, "id": target_id,
        "covered": covered,
        "covering_items": neighbors["referenced_by"],
        "note": "Coverage here means 'cited by another real item in the dogfooding corpus' -- "
                "a text-level proxy, not the production test-coverage meaning (§4, DQ-008).",
        # REQ-METIS-ACD-04: a concrete next action when there's a real gap.
        "next_step": next_step_guidance("no_traceability") if not covered else None,
    }


@mcp.tool()
def metis_impact_analysis(changed_files: list[str] | None = None, diff: str | None = None,
                           node_id: str | None = None) -> dict:
    """
    Production contract takes changed_files/diff (code-level). Dogfooding-mode
    adaptation: pass node_id directly since there's no code graph here.
    """
    if node_id is None:
        return {
            "adapted": True,
            "note": "Dogfooding mode has no code graph -- pass node_id directly "
                    "(e.g. a CONST-* or REQ-METIS-* id) instead of changed_files/diff.",
        }
    result = store.impact_analysis(node_id)
    if result is None:
        return {"found": False, "node_id": node_id}
    return _apply_headroom({"found": True, "adapted": True, **result})


@mcp.tool()
def metis_explain_decision(node_id: str) -> dict:
    """Explain where a piece of content actually came from -- real provenance, not a guess."""
    node = store.get_node(node_id)
    if not node:
        return {"found": False, "node_id": node_id}
    return {
        "found": True,
        "id": node.id,
        "explanation": node.text,
        "provenance": {"source_file": node.source_file, "source_heading": node.source_heading},
        "corroboration": {
            "cites": node.references,
            "cited_by": node.referenced_by,
            "corroboration_count": len(node.references) + len(node.referenced_by),
        },
    }


_KIND_TO_ACADEMY_PAGE = {
    "ConstitutionRule": "academy/confidence-tiers.html#constitution-gate",
    "Requirement": "academy/ears-authoring.html",
}


@mcp.tool()
def metis_explain_answer(prior_response_id: str | None = None, node_id: str | None = None) -> dict:
    """REQ-METIS-ACD-01: real retrieval-path explanation matching the
    contract's actual {explanation, sources, confidence_summary} shape
    (CONST-062's contract test previously found this tool forwarding to
    metis_explain_decision's different shape instead -- fixed here).

    graph.backend=neo4j: `sources` comes from the real Episode node
    (source_episode_id/source_connector/t_recorded) -- genuinely
    conformant. graph.backend=local: dogfooding-mode adaptation, disclosed
    via `adapted: true` -- these text documents have no formal Episode
    record, so `sources` carries the best real data available
    (source_file/source_heading), never a fabricated episode id."""
    target = node_id or prior_response_id
    if not target:
        return {"explanation": "", "sources": [], "confidence_summary": "",
                "found": False, "note": "Provide node_id (dogfooding-mode adaptation of prior_response_id)."}

    node = store.get_node(target)
    if not node:
        return {"explanation": "", "sources": [], "confidence_summary": "", "found": False,
                "node_id": target, "next_step": next_step_guidance("not_found")}

    adapted = True
    confidence_summary = "graph.backend=local has no confidence_tier/lifecycle_state tracking for " \
                          "dogfooding corpus items -- a real, disclosed gap, not a guess."
    sources = [{"source_file": node.source_file, "source_heading": node.source_heading}]

    if _graph_backend == "neo4j":
        with store.session() as session:
            # WHERE NOT n:DogfoodingItem -- id uniqueness is per-label, not
            # global; a colliding DogfoodingItem would otherwise pull in
            # unrelated lifecycle_state/confidence_tier data here (found
            # for real in metis_mcp/temporal.py, same root cause).
            rec = session.run(
                "MATCH (n {id: $id}) WHERE NOT n:DogfoodingItem "
                "OPTIONAL MATCH (e:Episode {id: n.source_episode_id}) "
                "RETURN n.lifecycle_state AS lifecycle_state, n.confidence_tier AS confidence_tier, "
                "e.id AS source_episode_id, e.source_connector AS source_connector, "
                "toString(e.t_recorded) AS t_recorded",
                id=target,
            ).single()
        if rec and rec["source_episode_id"]:
            sources = [{
                "source_episode_id": rec["source_episode_id"],
                "source_connector": rec["source_connector"] or "unknown",
                "t_recorded": rec["t_recorded"] or "",
            }]
            adapted = False
        if rec and rec.get("lifecycle_state"):
            confidence_summary = f"lifecycle_state={rec['lifecycle_state']}"
        elif rec and rec.get("confidence_tier"):
            confidence_summary = f"confidence_tier={rec['confidence_tier']}"
        else:
            confidence_summary = "No confidence_tier/lifecycle_state recorded for this node."

    academy_link = _KIND_TO_ACADEMY_PAGE.get(node.kind)

    return _apply_headroom({
        "found": True,
        "id": node.id,
        "explanation": node.text,
        "sources": sources,
        "confidence_summary": confidence_summary,
        "academy_links": [academy_link] if academy_link else [],
        "adapted": adapted,
    })


@mcp.tool()
def metis_propose_test_skeleton(transition_id: str) -> dict:
    """Stage 3 (Pyramid-Gap Check) + Stage 4 (skeleton generation) of
    metis-behavior-model-test-pipeline.md, real against graph.backend=neo4j
    (a real Transition/State/Guard/Trigger ontology exists there -- Phase 8 +
    demo data). Skeleton only -- never auto-commits (that's Stage 5,
    metis_mcp/test_skeleton_generator.py's commit_generated_test, a
    separate, explicit, human-review-gated step not reachable from this
    read-only tool)."""
    if _graph_backend != "neo4j":
        return {
            "applicable": False,
            "reason": "No Transition/TestCase ontology is populated against the 'local' backend -- "
                      "this platform's own dogfooding documents are Requirements/ConstitutionRules/"
                      "etc., not behavior-modeled Transitions. Real behavior requires "
                      "graph.backend: neo4j (see metis-behavior-model-test-pipeline.md).",
            "transition_id": transition_id,
        }
    with store.session() as session:
        return propose_test_skeletons(session, transition_id)


@mcp.tool()
def metis_submit_episode(episode_type: str, payload: dict, source_ref: str) -> dict:
    """Write path -- disabled by default per REQ-METIS-CPT-01, regardless of dogfooding/production."""
    return {
        "accepted": False,
        "reason": "metis_submit_episode is disabled by default (REQ-METIS-CPT-01) until the "
                  "guardrail stack has a production track record. This is a phase-gate, not a bug.",
    }


@mcp.tool()
def metis_quality_score(scope: str = "all", include_trend: bool = False) -> dict:
    """
    graph.backend=neo4j: the real §3.1 weighted composite quality_score,
    plus the full DQ-001..DQ-023 breakdown (REQ-METIS-DQ-01; DQ-023 is a
    Session 11 addition beyond the spec doc's original 22), computed
    against the actual production ontology -- metis_mcp/dq_metrics.py.
    graph.backend=local: falls back to the dogfooding corpus's structural
    orphan-rate proxy (no Requirement/AcceptanceCriterion/TestCase
    ontology exists there to compute the real 22 metrics against).
    """
    if _graph_backend == "neo4j":
        from metis_mcp.dq_metrics import compute_quality_score, compute_all_metrics
        with store.session() as session:
            score = compute_quality_score(session, scope=None if scope == "all" else scope)
            score["metrics"] = compute_all_metrics(session)
        return score

    kind = None if scope == "all" else scope
    result = store.orphan_rate(kind)
    result["note"] = (
        "This is a structural orphan-rate proxy computed from real cross-references in "
        "this platform's own documents -- not the full 22-metric DQ composite score "
        "(metis-data-quality-framework.md), which requires graph.backend: neo4j."
    )
    if result.get("conflicts_detected") is None and store.conflicts:
        result["duplicate_definition_conflicts"] = store.conflicts
    return result


@mcp.tool()
def metis_generate_quality_report(scope: dict, attributes: list[str] | None = None) -> dict:
    """
    A real, scoped quality report -- fixes metis_quality_score's own
    long-standing gap where `scope` was accepted but never actually used to
    filter anything (verified: every dq_XXX(session) call ignored it).

    `scope`: exactly one of {"requirement_id": ...}, {"service_id": ...},
    {"release_id": ...}, {"project_wide": true} -- the real production
    contract shape (mcp-contracts/metis-mcp-tool-contracts.json).

    `attributes`: subset of ["functional", "performance", "security"]
    (default: all three) -- NOT the DQ framework's own 6-dimension
    composite; a different, explicitly-requested breakdown built from a
    mix of existing DQ metrics and two new ones (SEC-01/PERF-01). See
    metis_mcp/quality_report.py's module docstring for exactly which real
    signal backs each one and which real gaps keep some honestly partial.

    Returns an executive-language summary plus a full per-metric detail
    breakdown (metis_mcp/quality_report.py). graph.backend=local (no real
    Requirement/Service/Release ontology exists there) returns an honest
    not-applicable response instead of a fabricated one.
    """
    if _graph_backend != "neo4j":
        return {
            "adapted": True,
            "note": "metis_generate_quality_report needs the real production ontology "
                    "(Requirement/Service/Release + real TRACES_TO structure) that only "
                    "graph.backend: neo4j provides -- not applicable against the dogfooding "
                    "corpus's LocalGraphStore.",
        }
    from metis_mcp.quality_report import build_report
    with store.session() as session:
        return build_report(session, scope, attributes)


@mcp.tool()
def metis_generate_release_report(release_id: str) -> dict:
    """
    A release-readiness report: metis_generate_quality_report scoped to a
    Release, plus a real changelog (metis_mcp/academy.py's actual :Revision
    history, not invented) and a deterministic, rule-based ship/hold/no-ship
    recommendation derived from the real gate_status -- never a model
    judgment call.

    graph.backend=local returns an honest not-applicable response (no real
    Release ontology exists in the dogfooding corpus).
    """
    if _graph_backend != "neo4j":
        return {
            "adapted": True,
            "note": "metis_generate_release_report needs the real production ontology "
                    "(Requirement/Release + real TRACES_TO structure) that only "
                    "graph.backend: neo4j provides -- not applicable against the dogfooding "
                    "corpus's LocalGraphStore.",
        }
    from metis_mcp.quality_report import build_release_report
    with store.session() as session:
        return build_release_report(session, release_id)


@mcp.tool()
def metis_generate_test_design_report(scope: dict) -> dict:
    """
    Session 10: the real Intent/TestDesign backbone (State/Transition ->
    Intent -> Requirement/AcceptanceCriterion, Intent -> TestDesign ->
    TestCase) made queryable as a report -- for the scoped Requirement(s),
    every AcceptanceCriterion, which real test-design technique(s)
    (Boundary Value Analysis, Equivalence Partitioning, State Transition
    Testing, Decision Table Testing, etc.) covered it, and which real
    TestCases (with real `.type`) resulted.

    `scope`: same real contract shape as metis_generate_quality_report --
    exactly one of {"requirement_id": ...}, {"service_id": ...},
    {"release_id": ...}, {"project_wide": true}.

    Requirements outside the Intent/TestDesign backbone (the bulk
    synthetic/grounded layers, which predate it) show up with an empty
    acceptance_criteria list -- an honest "not covered by this backbone
    yet" signal, not an error.

    graph.backend=local returns an honest not-applicable response.
    """
    if _graph_backend != "neo4j":
        return {
            "adapted": True,
            "note": "metis_generate_test_design_report needs the real production ontology "
                    "(Requirement/Intent/TestDesign + real TRACES_TO/COVERS structure) that "
                    "only graph.backend: neo4j provides -- not applicable against the "
                    "dogfooding corpus's LocalGraphStore.",
        }
    from metis_mcp.quality_report import build_test_design_report
    with store.session() as session:
        return build_test_design_report(session, scope)


def main():
    _source = CORPUS_GLOB if _graph_backend == "local" else _neo4j_cfg.get("uri")
    print(f"Métis MCP server ({_graph_backend} backend) -- loaded {store.node_count} real items "
          f"from {_source}", file=sys.stderr)
    if store.conflicts:
        print(f"  {len(store.conflicts)} duplicate-definition conflicts found: {store.conflicts}",
              file=sys.stderr)

    transport = _config.get_transport()
    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "streamable-http":
        # Phase 6: OAuth2-gated production transport. Requires graph.backend
        # == neo4j (the OAuth2/RBAC modules read real :User/:Token/owner_team
        # data from Neo4j -- there's no meaningful equivalent against
        # LocalGraphStore's in-memory dogfooding corpus).
        import uvicorn
        from metis_mcp.http_transport import OAuth2Middleware

        if _graph_backend != "neo4j":
            raise ValueError(
                "server.transport=streamable-http requires graph.backend=neo4j "
                "(OAuth2/RBAC need a real Neo4j-backed User/Token store)."
            )
        secret_env = _config.get_jwt_secret_env()
        secret = os.environ.get(secret_env or "")
        if not (secret_env and secret):
            raise ValueError(
                f"security.jwt_secret_env must be set in {_config.effective_path}, "
                f"and that environment variable must be exported."
            )
        app = mcp.streamable_http_app()

        async def _healthz(request):
            from starlette.responses import PlainTextResponse
            return PlainTextResponse("ok")

        # /healthz (metis-chart/values.yaml's livenessProbe) is exempted
        # inside OAuth2Middleware itself -- route registration order here
        # doesn't matter, middleware wraps the whole ASGI chain regardless.
        app.add_route("/healthz", _healthz, methods=["GET"])
        app.add_middleware(OAuth2Middleware, driver=store._driver, secret=secret)
        uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("METIS_HTTP_PORT", "8430")))
    else:
        raise ValueError(f"Unknown server.transport '{transport}' -- expected 'stdio' or 'streamable-http'.")


if __name__ == "__main__":
    main()
