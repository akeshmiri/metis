"""
Running a workflow from the agent surface (spec §3.2, §3.4, F-8).

**A gate halts the run; it does not prompt.** That is already how the engine
behaves and it is exactly what an agent needs: the run writes down where it got
to, says what decision is outstanding, and exits. `approve_elements` records the
decision, `resume_workflow` picks it up. Nothing here can advance past a gate,
and `exit_code == EXIT_HALTED` is the designed outcome of one — reporting it as
a failure would teach an agent to retry, which is the one thing that must not
happen at a gate.

**The context is built by the CLI's own `_workflow_context`.** That import is
heavy — `mbt.cli` reaches every write path in the codebase — and it is still the
right call: N-1 says no surface has a privileged path, and a second
context-builder here would be a second set of defaults that drifts from the one
the CLI uses. It is imported inside the function, so a read-only server never
loads it.
"""
from __future__ import annotations

from argparse import Namespace

from metis_mcp import policy
from metis_mcp.review.roles import PROPOSE

# Mirrors the `workflow run` parser. Every field the stage handlers read must be
# present: several reach `context.args.journey` directly rather than through
# `getattr`, and a missing attribute there is an AttributeError halfway through
# a run that has already written to the graph.
_DEFAULTS = {
    "model": None, "journey": None, "surface": "api", "source": "authored",
    "author": "", "endpoints": None, "service": None, "glossary": None,
    "knowledge": None, "job_id": "mcp", "state": None, "overrides": None,
    "criterion": "all-transitions", "max_setup": 10,
    # Never populated from this surface. `_drive` accepts no `confirm`, so a
    # gate reached through an agent halts and stays halted.
    "confirm": "",
    "as_user": "", "allow_unverifiable": False, "uri": None, "user": None,
    "divergence_against": None,
}


def _namespace(workflow: str, scope: str, overrides: dict) -> Namespace:
    values = dict(_DEFAULTS, workflow=workflow, scope=scope)
    values.update({k: v for k, v in overrides.items() if v is not None})
    return Namespace(**values)


def _report(outcome, workflow: str) -> dict:
    from metis_mcp.workflow import EXIT_HALTED, EXIT_OK

    record = outcome.record
    blocked = record.outcome_for(record.blocked_on) if record.is_blocked else None
    halted = outcome.exit_code == EXIT_HALTED
    return {
        # A halt is not a failure. `ok` says the run did what it was asked to;
        # `halted` says a human owes a decision (F-8).
        "ok": outcome.exit_code in (EXIT_OK, EXIT_HALTED),
        "halted": halted,
        "run_id": record.run_id,
        "workflow": workflow,
        "scope": record.scope,
        "complete": record.is_complete,
        "blocked_on": record.blocked_on,
        "failed_reason": record.failed_reason,
        "message": outcome.message,
        "stages": [{"ordinal": o.ordinal, "stage": o.stage,
                    "outcome": o.outcome, "detail": o.detail}
                   for o in record.outcomes],
        "outstanding": list(blocked.outstanding) if blocked else [],
        "next": (blocked.next_command if blocked else
                 ("nothing — the run is complete" if record.is_complete else "")),
        "means": ("halted at a gate: a human decision is outstanding, which is "
                  "the designed outcome, not a failure (F-8). Do not retry — "
                  "record the decision, then resume_workflow"
                  if halted else ""),
    }


def _drive(workflow_code: str, scope: str, resume: bool, actor: str, role: str,
           **overrides) -> dict:
    from metis_mcp.mbt.cli import _workflow_context
    from metis_mcp.workflow import get as get_workflow
    from metis_mcp.workflow import run as run_engine

    grant = policy.authorise(PROPOSE, actor, role)

    workflow = get_workflow(workflow_code)
    if workflow is None:
        from metis_mcp.workflow import WORKFLOWS

        return {"ok": False,
                "refused": f"unknown workflow {workflow_code!r}",
                "known": sorted(WORKFLOWS)}

    args = _namespace(workflow_code, scope, overrides)
    args.author = args.author or grant.identity.name
    outcome = run_engine(workflow, _workflow_context(args), resume=resume)
    report = _report(outcome, workflow_code)

    audit, audit_path = policy.audit_state(
        f"{workflow_code}--{scope}",
        overrides.get("model") or "")
    policy.record(grant, audit, report["run_id"],
                  "resumed" if resume else "ran",
                  evidence={"stages": [s["stage"] for s in report["stages"]],
                            "blocked_on": report["blocked_on"]},
                  rationale=f"workflow {workflow_code} over {scope} via mcp")
    policy.save_audit(audit, audit_path)
    report["audit"] = str(audit_path)
    return report


def run_workflow(workflow: str, scope: str, journey: str = "",
                 surface: str = "api", source: str = "authored",
                 model: str = "", endpoints: str = "", service: str = "",
                 knowledge: str = "", glossary: str = "",
                 criterion: str = "all-transitions",
                 allow_unverifiable: bool = False,
                 actor: str = "", role: str = "") -> dict:
    """Start a workflow. It halts at its gate rather than prompting.

    `workflow` is one of `list_workflows`. The run records where it got to, so a
    later `resume_workflow` continues rather than restarting — and a resumed run
    does not replay the stages that already passed.

    A halt is reported as `halted: true` with `ok: true`. That is not a failure
    and must not be retried: record the decision, then resume.
    """
    return _drive(workflow, scope, False, actor, role, journey=journey or None,
                  surface=surface, source=source, model=model or None,
                  endpoints=endpoints or None, service=service or None,
                  knowledge=knowledge or None, glossary=glossary or None,
                  criterion=criterion, allow_unverifiable=allow_unverifiable)


def resume_workflow(workflow: str, scope: str, journey: str = "",
                    surface: str = "api", source: str = "authored",
                    model: str = "", endpoints: str = "", service: str = "",
                    knowledge: str = "", glossary: str = "",
                    criterion: str = "all-transitions",
                    allow_unverifiable: bool = False,
                    actor: str = "", role: str = "") -> dict:
    """Continue a run that halted, once the decision it waited for is recorded.

    **This deliberately takes no `confirm`.** It used to, so that a resumed run
    could carry a gate's literal — which means an agent calling this tool could
    have supplied G2's `publish` itself. T-18 was written against a human
    forgetting to confirm; it says nothing about a caller that confirms on the
    human's behalf, because when it was written there was no such caller.

    A run that halts at G2 is therefore finished from the CLI, by whoever is
    actually accountable for the external write. This tool can start and resume
    work; it cannot authorise anything leaving Métis.
    """
    return _drive(workflow, scope, True, actor, role, journey=journey or None,
                  surface=surface, source=source, model=model or None,
                  endpoints=endpoints or None, service=service or None,
                  knowledge=knowledge or None, glossary=glossary or None,
                  criterion=criterion,
                  allow_unverifiable=allow_unverifiable)
