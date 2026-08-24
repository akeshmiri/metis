"""
Authoring through the agent surface. **Everything here lands at Quarantine.**

S-4 is the rule that makes a writing agent surface tolerable: authoring is not
approving, no source writes `Approved`, and generation reads only `Approved`
(D-10). So the worst a tool in this module can do is add a candidate somebody
has to review — which is what a person with the CLI could already do, recorded
the same way.

**No function here writes Cypher.** Each builds a plan and hands it to
`model_sources.landing.land`, which is what makes three separate guarantees
apply to an agent's write for free:

  * the ontology catalogue refuses an uncatalogued triple before anything runs;
  * `landing.namespaced_id` and `transition_label_for` are used to plan, so an
    edge written against `:Transition` cannot silently match nothing;
  * counts come back from the database rather than `len(rows)`, and the
    shortfall is reported as `unmatched`.

That last one is why every return value below carries `unmatched`. A plan that
"landed" while matching nothing is this codebase's documented failure mode, and
a tool that reported only `nodes_written` would reproduce it exactly.
"""
from __future__ import annotations

from metis_mcp import policy
from metis_mcp.review.roles import PROPOSE


def _outcome(result, extra: dict | None = None) -> dict:
    """One shape for every landing, with the honest fields kept."""
    payload = {
        "ok": result.ok,
        "episode_id": result.episode_id,
        "nodes_written": result.nodes_written,
        "edges_written": result.edges_written,
        "lifecycle_state": "Quarantine",
        "means": "landed for review — authoring is not approving (S-4)",
    }
    if result.refused:
        payload["refused"] = result.refused
    if result.unmatched:
        # Never summarised away. The counts above can look healthy while this is
        # non-empty, and that combination is the bug, not the exception.
        payload["unmatched"] = [
            {"edge": edge, "shortfall": shortfall, "why": why}
            for edge, shortfall, why in result.unmatched
        ]
        payload["warning"] = (
            "some planned edges matched no endpoints — the graph does not hold "
            "what the plan described")
    payload.update(extra or {})
    return payload


def land_model(source: str = "authored", path: str = "", journey: str = "",
               surface: str = "api", endpoints: str = "", service: str = "",
               job_id: str = "mcp", actor: str = "", role: str = "") -> dict:
    """Produce a model from a source and land it at Quarantine.

    `source` is one of `sources` — authored, code, web, ac-mined, openapi. For
    `code`, `path` is the behaviour pack's report and `endpoints` the structural
    one; `service` scopes a multi-module report to one deployable and omitting it
    on a monorepo report produces one model wearing one service's name.
    """
    from metis_mcp.mbt.graph_session import session
    from metis_mcp.model_sources import get as get_source
    from metis_mcp.model_sources import land, plan_landing

    grant = policy.authorise(PROPOSE, actor, role)

    producer = get_source(source)
    if not producer.available:
        return {"ok": False, "refused": f"source {source!r} is unavailable — "
                                        f"{producer.why_unavailable()}"}
    produced = producer.produce(path=path, author=grant.identity.name,
                                endpoints=endpoints, service=service,
                                journey=journey, surface=surface)

    # §17: a human edit is a layered fact, and landing that read the raw source
    # dropped it -- the correction validated clean on the file and reached the
    # graph without the edit. Applied here for the same reason `cli land` does.
    if path:
        from metis_mcp.overrides import OverrideLog, apply_overrides, default_log_path

        log = OverrideLog.load(default_log_path(path))
        if log.entries:
            produced.model = apply_overrides(produced.model, log).model

    plan = plan_landing(produced, journey=journey, job_id=job_id)
    if not plan.is_legal:
        return {"ok": False,
                "refused": f"{len(plan.errors)} validation error(s) — nothing "
                           f"was written",
                "errors": plan.errors[:8]}

    with session() as s:
        result = land(s, plan)

    state, audit_path = policy.audit_state(produced.model.id, path)
    evidence = {"source": source, "extraction_method": produced.extraction_method,
                "states": len(produced.model.states),
                "transitions": len(produced.model.transitions),
                "skipped": [list(pair) for pair in produced.skipped]}
    policy.record(grant, state, produced.model.id, "landed", evidence,
                  rationale=f"landed via mcp from source {source!r}")
    policy.save_audit(state, audit_path)

    return _outcome(result, {
        "model_id": produced.model.id,
        "extraction_method": produced.extraction_method,
        "states": len(produced.model.states),
        "transitions": len(produced.model.transitions),
        "skipped": [{"id": i, "reason": r} for i, r in produced.skipped],
        "audit": str(audit_path),
        "next": "review_queue, then approve_elements",
    })


def land_knowledge(path: str, journey: str = "", glossary: str = "",
                   job_id: str = "mcp", actor: str = "", role: str = "") -> dict:
    """Land a knowledge file: the documentation and the behaviour mined from it.

    Two stages, landed together and in this order (S-4, and the reason is
    mechanical): behaviour first, because `VALIDATES` opens with two `MATCH`es
    and merges nothing when its target is absent.
    """
    from metis_mcp.mbt.graph_session import session
    from metis_mcp.model_sources import get as get_source
    from metis_mcp.model_sources import land, plan_landing
    from metis_mcp.model_sources.knowledge import load as load_knowledge
    from metis_mcp.model_sources.knowledge import plan_documentation

    grant = policy.authorise(PROPOSE, actor, role)

    knowledge = load_knowledge(path)
    produced = get_source("ac-mined").produce(path=path,
                                              author=grant.identity.name)
    journey = journey or knowledge.model_id.rpartition("-")[0]

    behaviour = plan_landing(produced, journey=journey, job_id=job_id)
    if not behaviour.is_legal:
        return {"ok": False,
                "refused": f"{len(behaviour.errors)} error(s) in the behaviour "
                           f"plan — nothing was written",
                "errors": behaviour.errors[:8]}

    documentation = plan_documentation(
        knowledge, behaviour.episode_id,
        criterion_transitions=produced.evidence.get("criterion_transitions", {}))
    if not documentation.is_legal:
        # Checked before the first write, so an illegal documentation plan does
        # not leave half the knowledge in the graph.
        return {"ok": False,
                "refused": f"{len(documentation.errors)} error(s) in the "
                           f"documentation plan — nothing was written",
                "errors": documentation.errors[:8]}

    with session() as s:
        behaviour_result = land(s, behaviour)
        if not behaviour_result.ok:
            return _outcome(behaviour_result)
        documentation_result = land(s, documentation)

    state, audit_path = policy.audit_state(knowledge.model_id, path)
    policy.record(grant, state, knowledge.model_id, "landed",
                  {"criteria": len(knowledge.criteria),
                   "transitions": len(produced.model.transitions)},
                  rationale="knowledge landed via mcp")
    policy.save_audit(state, audit_path)

    return _outcome(documentation_result, {
        "model_id": knowledge.model_id,
        "criteria": len(knowledge.criteria),
        "behaviour": {"nodes": behaviour_result.nodes_written,
                      "edges": behaviour_result.edges_written},
        "audit": str(audit_path),
    })


def land_findings(journey: str, surface: str = "api", version: int = 1,
                  commit: str = "", episode: str = "", run_id: str = "",
                  actor: str = "", role: str = "") -> dict:
    """Write this model's validation findings into the graph as `:Finding`.

    §8.2/F-12: a finding that exists only in a command's stdout has to be
    re-derived by everyone who wants it and cannot be linked to the element it
    concerns. A finding is evidence for a decision, never the decision — so this
    lands at Quarantine like everything else.
    """
    from metis_mcp.mbt.finding_writer import from_validation, load, plan_load
    from metis_mcp.mbt.graph_loader import load_from_graph
    from metis_mcp.mbt.graph_session import session
    from metis_mcp.mbt.validation import validate
    from metis_mcp.review.state import source_fingerprint

    grant = policy.authorise(PROPOSE, actor, role)
    episode = episode or f"mcp-findings-{journey}-{surface}"

    with session() as s:
        report = load_from_graph(s, journey, surface)
        model = report.model
        result = validate(model)
        records = from_validation(result, model)
        plan = plan_load(model, journey=journey, surface=surface,
                         version=version, commit=commit, episode=episode,
                         findings=records, run_id=run_id, engine="mcp",
                         source_fingerprint=source_fingerprint(model))
        written = load(s, plan)

    state, audit_path = policy.audit_state(model.id)
    policy.record(grant, state, model.id, "findings-landed",
                  {"blocking": len(result.blocking),
                   "unverifiable": len(result.unverifiable),
                   "advisory": len(result.advisory)},
                  rationale="validation findings landed via mcp")
    policy.save_audit(state, audit_path)

    return {
        "ok": True,
        "model_id": model.id,
        "written": written,
        "by_severity": {"blocking": len(result.blocking),
                        "unverifiable": len(result.unverifiable),
                        "advisory": len(result.advisory)},
        "means": ("unverifiable is a third outcome — neither a pass nor a "
                  "defect (M-17)"),
        "audit": str(audit_path),
    }
