"""
Static lint of the workflow definitions.

Ported from Atlas's `.agents/scripts/validate-determinism.py`, which is real,
executable, and genuinely useful -- it checks that every stage carries its
required keys, that ordinals are unique within a workflow, that skill orders form
an unbroken `1..N`, and that workflow codes do not collide.

**Two checks it does not have, and both matter more than the ones it does.**
Atlas never verifies that a declared reference resolves. A dangling
`next_stages: ["Evidence Acquisition"]` pointing at a stage that does not exist
in that workflow passes its lint silently, and its agent files reference roughly
twenty-five skill names with no directory behind them. So this adds:

  * every `checks:` entry names a **registered predicate**;
  * every `handler:` names a **registered handler**.

Those two are what make the manifest a contract instead of a description.

**Run as a test, not a command.** Atlas's lint is real and sits in no CI job and
no git hook -- which is exactly why its dangling reference survived. A lint
nobody runs is documentation with an exit code.
"""
from __future__ import annotations

from metis_mcp.workflow import checks as checks_module
from metis_mcp.workflow.stages import WORKFLOWS, Workflow, registered_handlers


def lint_workflow(workflow: Workflow) -> list[str]:
    errors: list[str] = []
    where = f"workflow {workflow.code!r}"

    if not workflow.code.strip():
        errors.append("a workflow must have a non-empty code")
    if not workflow.summary.strip():
        errors.append(f"{where}: needs a summary — an entry nobody can describe "
                      f"is one nobody can route to")
    if not workflow.stages:
        errors.append(f"{where}: has no stages")

    ordinals = [s.ordinal for s in workflow.stages]
    if len(set(ordinals)) != len(ordinals):
        dupes = sorted({o for o in ordinals if ordinals.count(o) > 1})
        errors.append(f"{where}: duplicate ordinal(s) {dupes} — the order would "
                      f"depend on dict insertion, not on the definition")
    if ordinals and sorted(ordinals) != list(range(1, len(ordinals) + 1)):
        errors.append(f"{where}: ordinals must be exactly 1..{len(ordinals)}; "
                      f"found {sorted(ordinals)}. A gap means a stage was removed "
                      f"and its dependents were not re-checked")

    names = [s.name for s in workflow.stages]
    if len(set(names)) != len(names):
        errors.append(f"{where}: duplicate stage name(s)")

    handlers = registered_handlers()
    known_checks = checks_module.registered()

    for stage in workflow.stages:
        at = f"{where}, stage {stage.name!r}"
        if stage.handler not in handlers:
            errors.append(
                f"{at}: handler {stage.handler!r} is not registered. A workflow "
                f"may not name work nothing implements (this is the check Atlas's "
                f"lint lacks, and why its manifest carries dangling references)")
        for name in stage.checks:
            if name not in known_checks:
                errors.append(
                    f"{at}: check {name!r} is not registered. A check that is not "
                    f"a predicate is a printed string — the defect this port "
                    f"exists to correct")
        for required in stage.requires:
            prior = workflow.stage(required)
            if prior is None:
                errors.append(f"{at}: requires {required!r}, which is not a stage "
                              f"of this workflow")
            elif prior.ordinal >= stage.ordinal:
                errors.append(
                    f"{at} (ordinal {stage.ordinal}) requires {required!r} at "
                    f"ordinal {prior.ordinal} — a stage cannot depend on one that "
                    f"runs later")
        if stage.is_gate and not stage.blocking:
            errors.append(f"{at}: a gate that does not block is not a gate")

    for name in workflow.preconditions:
        if name not in known_checks:
            errors.append(f"{where}: precondition {name!r} is not a registered check")

    return errors


def lint_all() -> list[str]:
    errors: list[str] = []
    for code, workflow in sorted(WORKFLOWS.items()):
        if code != workflow.code:
            errors.append(f"registry key {code!r} does not match workflow code "
                          f"{workflow.code!r}")
        errors.extend(lint_workflow(workflow))
    return errors


def format_lint(errors: list[str]) -> str:
    if not errors:
        return (f"Workflow definitions are consistent — {len(WORKFLOWS)} workflow(s), "
                f"every handler and check resolves.")
    lines = [f"{len(errors)} workflow definition error(s):", ""]
    lines.extend(f"  {e}" for e in errors)
    return "\n".join(lines)
