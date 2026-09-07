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

import pathlib

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


def land_intake(path: str, job_id: str = "mcp", author: str = "",
                actor: str = "", role: str = "") -> dict:
    """Carry a UIF document into the graph: an `Episode` and its source anchor.

    **The S-13 behaviour is the point, and it is preserved exactly.** A UIF whose
    text is free prose -- most tracker titles -- lands as a `Finding` pointing at
    `knowledge-capture`, NOT as a `Requirement`, because `ears_pattern` has no
    empty form and guessing one is precisely what `ac_mining` refuses to do. A
    tool that quietly promoted prose to a Requirement would file somebody's Jira
    title as a stated requirement, with an author who never wrote it.

    Claimed acceptance criteria are never trusted into `AcceptanceCriterion`
    nodes: a criterion asserted by the document that raised the requirement is
    not independent evidence of it.

    Everything lands at `Quarantine` (S-4). Intake is not agreement.
    """
    from metis_mcp.mbt.graph_session import session
    from metis_mcp.model_sources import intake_landing as intake
    from metis_mcp.model_sources.landing import land

    grant = policy.authorise(PROPOSE, actor, role)

    try:
        document = intake.load(path)
    except intake.IntakeRefused as e:
        return {"ok": False, "refused": f"{path}: {e}"}

    # Reported before anything is written, for the same reason the CLI prints it
    # at the door: "this landed as a Finding, not a Requirement" is the single
    # most surprising thing this intake does, and counting nodes afterwards is a
    # bad way to discover it.
    checked = intake.conformance(document)

    try:
        plan = intake.plan_intake(document, job_id=job_id,
                                  proposed_by=author or grant.identity.name)
    except intake.IntakeRefused as e:
        return {"ok": False, "refused": str(e)}

    if not plan.is_legal:
        return {"ok": False,
                "refused": f"{len(plan.errors)} validation error(s) — nothing "
                           f"was written",
                "errors": plan.errors[:8]}

    with session() as s:
        result = land(s, plan)

    state, audit_path = policy.audit_state(plan.episode_id, path)
    policy.record(grant, state, plan.episode_id, "landed",
                  {"source": path}, rationale="intake landed via mcp")
    policy.save_audit(state, audit_path)

    return _outcome(result, {
        "episode_id": plan.episode_id,
        "lifecycle": "Quarantine — intake is not agreement (S-4)",
        # A list, and it stays even when empty would prune: an advisory saying
        # "this became a Finding" is the difference between a landed requirement
        # and a landed note about one.
        "advisories": list(checked.advisories) or "none",
        "audit": str(audit_path),
        "next": "review_queue, then approve_elements",
    })


def land_knowledge(path: str, journey: str = "", glossary: str = "",
                   job_id: str = "mcp", actor: str = "", role: str = "") -> dict:
    """Land a knowledge file: the documentation and the behaviour mined from it.

    Stages landed together and in this order (S-4, and the reason is
    mechanical): the glossary first when one is given, so `REFERENCES` has a
    target; then behaviour, because `VALIDATES` opens with two `MATCH`es and
    merges nothing when its target is absent.

    **`glossary` was declared here and never read.** A caller passing one got a
    successful-looking landing with the glossary silently dropped — the
    silent-success failure this project hunts for, and worse than an error
    because the counts came back plausible. It now does what the CLI's
    `workflow run --glossary` handler does, and refuses the same way: an
    unreadable or invalid glossary stops the whole landing before the first
    write rather than half-landing it.
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

    terms = None
    glossary_plan = None
    if glossary:
        from metis_mcp.model_sources.glossary import (
            GlossaryRefused, load as load_glossary, plan_glossary,
        )
        from metis_mcp.model_sources.glossary import validate as validate_glossary

        try:
            terms = load_glossary(glossary)
        except (OSError, ValueError, GlossaryRefused) as e:
            return {"ok": False, "refused": f"{glossary}: {e}"}
        problems = validate_glossary(terms)
        if problems:
            return {"ok": False,
                    "refused": f"{len(problems)} problem(s) in the glossary — "
                               f"nothing was written",
                    "errors": [p.describe() for p in problems[:8]]}
        glossary_plan = plan_glossary(terms, behaviour.episode_id)
        if not glossary_plan.is_legal:
            return {"ok": False,
                    "refused": f"{len(glossary_plan.errors)} error(s) in the "
                               f"glossary plan — nothing was written",
                    "errors": glossary_plan.errors[:8]}

    documentation = plan_documentation(
        knowledge, behaviour.episode_id,
        criterion_transitions=produced.evidence.get("criterion_transitions", {}),
        glossary=terms)
    if not documentation.is_legal:
        # Checked before the first write, so an illegal documentation plan does
        # not leave half the knowledge in the graph.
        return {"ok": False,
                "refused": f"{len(documentation.errors)} error(s) in the "
                           f"documentation plan — nothing was written",
                "errors": documentation.errors[:8]}

    with session() as s:
        glossary_result = None
        if glossary_plan is not None:
            glossary_result = land(s, glossary_plan)
            if not glossary_result.ok:
                return _outcome(glossary_result)
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
        # Absent when no glossary was passed; present with real counts when one
        # was, so "did my glossary land" is answerable from the response.
        "glossary": ({"areas": len(terms.areas),
                      "entities": len(terms.entities),
                      "nodes": glossary_result.nodes_written,
                      "edges": glossary_result.edges_written}
                     if glossary_result is not None else None),
        "audit": str(audit_path),
    })


def persist_version(journey: str, surface: str = "api",
                    criterion: str = "all-transitions", version: int = 1,
                    commit: str = "", actor: str = "", role: str = "") -> dict:
    """Record the `Component` a coverage figure refers to (P-16).

    **The loop this closes.** `coverage` and `coverage_report` report "not
    recorded (P-16)" and tell the reader to run `metis persist` — and until now
    that was the one instruction the MCP surface could not act on, so an agent
    following its own tool's advice hit a wall. Persisting is a write and belongs
    behind the write switch; it was never a decision, so it never belonged only
    on the CLI.

    A figure that names no version is a figure about nothing in particular.
    """
    from metis_mcp.mbt.coverage import build_ledger
    from metis_mcp.mbt.graph_session import session
    from metis_mcp.mbt.graph_writer import persist, plan_persist
    from metis_mcp.mbt.path_generation import generate

    grant = policy.authorise(PROPOSE, actor, role)

    from metis_mcp.mbt.graph_loader import load_from_graph

    with session() as s:
        report = load_from_graph(s, journey, surface)
        if not report.found:
            return {"ok": False,
                    "refused": f"no model for {journey!r}/{surface!r}"}
        model = report.model
        result = generate(model, criterion, 10)
        ledger = build_ledger(model, result)
        plan = plan_persist(model, ledger, version=version, commit=commit)
        if not plan.is_legal:
            return {"ok": False,
                    "refused": f"{len(plan.errors)} error(s) in the persist "
                               f"plan — nothing was written",
                    "errors": plan.errors[:8]}
        outcome = persist(s, plan)

    state, audit_path = policy.audit_state(model.id, f"version-{version}")
    policy.record(grant, state, model.id, "persisted",
                  {"version": version, "commit": commit},
                  rationale="component version recorded via mcp")
    policy.save_audit(state, audit_path)

    return {
        "ok": getattr(outcome, "ok", True),
        "model_id": model.id,
        "version": version,
        "commit": commit or "not supplied",
        "means": "coverage figures for this model can now name a version (P-16)",
        "audit": str(audit_path),
    }


def publication_drift(journey: str, surface: str = "api",
                      criterion: str = "all-transitions",
                      actor: str = "", role: str = "") -> dict:
    """What changed since the last publication, and who changed it (§7.6).

    **Behind the write switch although it only reads**, and the reason is
    structural rather than cautious: `PublicationLedger` lives in
    `metis_mcp.publishing`, which is in `test_mcp_server.WRITE_PATHS`. A
    read-tier tool importing it would put a write path on the read surface and
    turn N-8's "no write path is reachable" proof into a lie. The write tier
    already imports write paths, so here it costs nothing.

    **Reports whether it can see anything at all.** `MANUALLY_EDITED` and
    `OBSOLETE` read zero whenever nothing has been recorded as sent — which
    means "cannot tell", not "no drift".
    """
    from metis_mcp.mbt.graph_loader import load_from_graph
    from metis_mcp.mbt.graph_session import session
    from metis_mcp.mbt.path_generation import generate
    from metis_mcp.publishing import PublicationLedger, compare, default_ledger_path
    from metis_mcp.rendering import render

    policy.authorise(PROPOSE, actor, role)

    with session() as s:
        report = load_from_graph(s, journey, surface)
        if not report.found:
            return {"ok": False,
                    "refused": f"no model for {journey!r}/{surface!r}"}
        model = report.model

    cases = render(model, generate(model, criterion, 10).paths).cases
    ledger = PublicationLedger.load(default_ledger_path(model.id))
    result = compare(cases, ledger)

    by_class: dict[str, int] = {}
    for item in result.items:
        by_class[item.drift_class] = by_class.get(item.drift_class, 0) + 1

    return {
        "ok": True,
        "model_id": model.id,
        "classes": by_class,
        "items": [{"case_id": i.case_id, "drift_class": i.drift_class,
                   "action": i.action, "detail": i.detail}
                  for i in result.items],
        # The field that stops a zero being misread. A string, because `_prune`
        # deletes false and this is the answer that matters.
        "published_content_visible":
            "yes" if ledger.can_see_published_content else
            "no — nothing has been recorded as sent, so MANUALLY_EDITED and "
            "OBSOLETE read zero because they cannot tell, not because there is "
            "no drift",
    }


def duplicate_check(journey: str, surface: str = "api",
                    criterion: str = "all-transitions",
                    actor: str = "", role: str = "") -> dict:
    """Whether publishing this batch would create a second copy of anything.

    **Behind the write switch for the same structural reason as
    `publication_drift`**: it reads `PublicationLedger`, which lives in
    `metis_mcp.publishing` — a `test_mcp_server.WRITE_PATHS` entry. A read-tier
    tool importing it would put a write path on the read surface and turn N-8's
    "no write path is reachable" proof into a policy check. It is also only a
    meaningful question for a surface that can publish.

    **`unknown` blocks and is not a failure.** A ledger that has never recorded
    a live publication cannot tell you anything, and reporting `no_match` from
    it is how a second copy of everything gets created — invisible under
    `DryRunTransport`, because nothing is sent either way.

    This decides nothing. Where something already exists, a person chooses
    whether to update it or add another (T-15); approving a batch is not
    approving a replacement of work somebody edited by hand.
    """
    from metis_mcp.mbt.graph_loader import load_from_graph
    from metis_mcp.mbt.graph_session import session
    from metis_mcp.mbt.path_generation import generate
    from metis_mcp.publishing import PublicationLedger, default_ledger_path
    from metis_mcp.publishing.duplicates import check, summarise
    from metis_mcp.rendering import render

    policy.authorise(PROPOSE, actor, role)

    with session() as s:
        report = load_from_graph(s, journey, surface)
        if not report.found:
            return {"ok": False,
                    "refused": f"no model for {journey!r}/{surface!r}"}
        model = report.model

    cases = render(model, generate(model, criterion, 10).paths).cases
    ledger = PublicationLedger.load(default_ledger_path(model.id))
    verdicts = check(cases, ledger)
    summary = summarise(verdicts)

    return {
        "ok": True,
        "model_id": model.id,
        # A string, because `_prune` deletes false and this is the answer.
        "may_proceed": "yes" if summary["may_proceed"] else "no",
        "counts": summary["counts"],
        "verdicts": [{"case_id": v.case_id, "verdict": v.verdict,
                      "detail": v.detail, "published_id": v.published_id}
                     for v in verdicts],
        "not_checked": ("title similarity against published content — the "
                        "ledger retains hashes, not titles, so a case renamed "
                        "by hand in the tracker cannot be matched from here"),
    }


def land_executions(path: str, cycle: str = "", job_id: str = "execution",
                    actor: str = "", role: str = "") -> dict:
    """Land observed test results — what ran, and what it reported (§8.7).

    **The change this belongs to.** `TestExecution` and `TestCycle` were staged
    out against "execution results are ingested (spec C-10's trigger)". That
    trigger is pulled, and both rules survive it: nothing here touches the
    coverage ledger (C-10), and coverage still answers "is this behaviour
    tested?" (C-11). This adds the second half of a sentence — a transition may
    be fully covered and currently failing.

    Everything lands at `Quarantine` carrying
    `provenance: observed_from_running_system`, attached to the CASE that ran
    and never to the transition it covers.

    `path` is a JSON file of `{case_id, outcome, observed_at, detail}` records.
    An outcome the vocabulary does not carry is refused, never defaulted.
    """
    import json as _json

    from metis_mcp.execution_intake import IntakeRefused, plan_execution_landing
    from metis_mcp.mbt.graph_session import session
    from metis_mcp.model_sources.landing import land

    grant = policy.authorise(PROPOSE, actor, role)

    try:
        records = _json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError) as e:
        return {"ok": False, "refused": f"{path}: {e}"}
    if not isinstance(records, list):
        return {"ok": False,
                "refused": "expected a JSON list of execution records"}

    try:
        plan = plan_execution_landing(records, cycle=cycle, job_id=job_id)
    except IntakeRefused as e:
        return {"ok": False, "refused": str(e)}

    with session() as s:
        result = land(s, _as_landing_plan(plan))

    state, audit_path = policy.audit_state(job_id, path)
    policy.record(grant, state, job_id, "landed", plan["summary"],
                  rationale="execution results landed via mcp")
    policy.save_audit(state, audit_path)

    return _outcome(result, {
        "summary": plan["summary"],
        "lifecycle": plan["lifecycle"],
        "attaches_to": plan["attaches_to"],
        "audit": str(audit_path),
    })


def _as_landing_plan(plan: dict):
    """The dict form into the planner's own node/edge types."""
    from metis_mcp.model_sources.landing import PlannedEdge, PlannedNode, Plan

    return Plan(
        episode_id=plan["job_id"],
        nodes=[PlannedNode(label=n["label"], properties=n["properties"])
               for n in plan["nodes"]],
        edges=[PlannedEdge(from_label=e["from_label"], from_id=e["from_id"],
                           rel_type=e["rel_type"], to_label=e["to_label"],
                           to_id=e["to_id"])
               for e in plan["edges"]],
    )


def fetch_repository(remote: str, into: str, ref: str = "",
                     full_history: bool = False, replace: bool = False,
                     actor: str = "", role: str = "") -> dict:
    """Obtain a repository to model — a disposable, shallow checkout.

    **Behind the write switch because it writes to disk**, not because it is
    dangerous to the graph: it lands nothing. A checkout is an intake source and
    not the system under test (X-7a) — reading a repository is not calling the
    service it builds — so it needs no execution tier.

    Without this, an agent asked to "model this service" could run every stage
    of `model-build` except the one that gets the code, and the CLI was the only
    way to close that gap.

    A remote that is a transport helper (`ext::`) or an option
    (`--upload-pack=…`) is refused by shape: those are arbitrary command
    execution wearing a URL. A token never belongs in the remote (PLT-005).
    """
    from metis_mcp.checkout import CheckoutFailed, UnsafeRemote, clone

    policy.authorise(PROPOSE, actor, role)
    try:
        return clone(remote, into, ref=ref,
                     depth=0 if full_history else 1, replace=replace)
    except (UnsafeRemote, CheckoutFailed) as e:
        return {"ok": False, "refused": str(e)}


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
