"""
The workflow engine (application spec §3.2, §3.4, F-8, F-9, F-10).

Runs a workflow's stages in order, stops at the first failure, and **halts** at a
gate rather than prompting.

**Halt, not prompt.** Atlas's Stage Confirmation Protocol prints a
`[C]ontinue/[R]eview/[B]ack/[X]it` menu and blocks the process waiting for a
keystroke -- which cannot run in CI and loses the run if the terminal dies. F-8
already says the right thing: nothing auto-promotes on elapsed time, and an
unreviewed model stays unapproved indefinitely. So a gate writes down where it
got to, says what decision is outstanding and how to record it, and exits. A
later `resume` picks it up. An interactive menu, if ever wanted, is a thin front
end over this -- the reverse is not true.

**Status is derived from checks that ran.** Atlas's `gate --status passed` writes
whatever the caller asserts, and its `validate_stage_gate` then inspects only
that one stage's own entry -- it never verifies a prior stage passed. Both holes
are closed here: an outcome exists only because a handler produced it, and
`RunRecord.may_advance_to` refuses on a prior stage that did not pass *and* on
one that passed against an input that has since moved.

**Fail-fast, with no repair (F-9, F-10).** A failed stage stops the run and
reports what failed and what is required. There is no retry, no alternative
path, and no substitute artefact -- and a partial result is never presented as a
complete one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from metis_mcp.workflow import checks as checks_module
from metis_mcp.workflow.run import (
    EXIT_FAILED,
    EXIT_HALTED,
    EXIT_OK,
    FAILED,
    HALTED,
    PASSED,
    RunRecord,
    StageOutcome,
    run_id_for,
    run_path,
)
from metis_mcp.workflow.stages import Stage, Workflow, get_handler


@dataclass
class Context:
    """Everything the stages of one run share.

    Mutable on purpose: a stage's output is the next stage's input, and the
    alternative -- threading a growing tuple through every handler -- hides which
    stage produced what.

    **A resumed run does not replay the stages it already passed**, so anything a
    later stage needs must be reconstitutable from durable state rather than
    carried in memory. `cli._workflow_context` does exactly that: it re-loads the
    model from the graph before handing the context to `run(resume=True)`. This
    is deliberate -- replaying a passed stage to rebuild the context would re-do
    external work (landing, publishing) as a side effect of resuming, and the
    fingerprint check already guarantees the reconstituted input is the one the
    earlier stages actually ran against.
    """

    workflow: str
    scope: str
    args: Any = None
    model: Any = None
    drafts: list = field(default_factory=list)
    paths: Any = None
    cases: list = field(default_factory=list)
    inherited: dict | None = None
    allow_unverifiable: bool = False
    expect_prior_approval: bool = False
    notes: list[str] = field(default_factory=list)
    # knowledge-capture: the checked file, and what comparing it against the
    # current model found. Both are rebuilt on resume from the file itself,
    # which is why the file is the durable artefact and not this context.
    knowledge: Any = None
    delta: Any = None

    def fingerprint(self) -> str:
        """What the current stage is about to run against.

        Empty until a model exists, which is honest: a stage that runs before
        extraction has nothing to be stale against, and inventing a hash for it
        would make `may_advance_to` compare noise.
        """
        if self.model is None:
            return ""
        from metis_mcp.review.state import source_fingerprint
        return source_fingerprint(self.model)


@dataclass
class RunOutcome:
    record: RunRecord
    exit_code: int
    message: str = ""


def _run_stage(stage: Stage, context: Context) -> StageOutcome:
    """Run one stage: its handler, then its checks. Never raises."""
    fingerprint_before = context.fingerprint()
    handler = get_handler(stage.handler)
    if handler is None:
        return StageOutcome(
            stage=stage.name, ordinal=stage.ordinal, outcome=FAILED,
            input_fingerprint=fingerprint_before,
            detail=(f"stage {stage.name!r} names handler {stage.handler!r}, which "
                    f"is not registered. A workflow may not name work nothing "
                    f"implements"))

    try:
        outcome, detail, outstanding, next_command = handler(context)
    except Exception as e:                                        # noqa: BLE001
        # F-9: report it, do not attempt recovery. The exception text is the
        # finding -- `require_valid` and `_require_approved` both put the
        # actionable detail in theirs precisely so it can surface here.
        return StageOutcome(
            stage=stage.name, ordinal=stage.ordinal, outcome=FAILED,
            input_fingerprint=fingerprint_before,
            detail=f"{type(e).__name__}: {e}")

    result = StageOutcome(
        stage=stage.name, ordinal=stage.ordinal, outcome=outcome, detail=detail,
        # Recorded AFTER the handler ran, so it describes what the stage's
        # conclusion actually covers rather than what was there when it started.
        input_fingerprint=context.fingerprint() or fingerprint_before,
        outstanding=list(outstanding or ()), next_command=next_command or "")

    if result.outcome == PASSED and stage.checks:
        verdict = checks_module.run_all(stage.checks, context)
        if not verdict.ok:
            # A gate whose checks fail has not failed -- it is still waiting.
            # Collapsing the two would turn "the human has not decided yet" into
            # "the pipeline is broken", and CI could not tell them apart.
            result = StageOutcome(
                stage=stage.name, ordinal=stage.ordinal,
                outcome=HALTED if stage.is_gate else FAILED,
                detail=verdict.reason,
                input_fingerprint=result.input_fingerprint,
                outstanding=result.outstanding, next_command=result.next_command)
    return result


def run(workflow: Workflow, context: Context, root: str | None = None,
        resume: bool = False) -> RunOutcome:
    """Execute a workflow, or continue one that halted."""
    run_id = run_id_for(workflow.code, context.scope)
    path = run_path(run_id, root)

    record = RunRecord.load(path) if resume else None
    if resume and record is None:
        return RunOutcome(
            RunRecord(run_id=run_id, workflow=workflow.code, scope=context.scope),
            EXIT_FAILED,
            f"no run to resume for {workflow.code} over {context.scope} "
            f"(looked in {path})")
    if record is None:
        record = RunRecord(run_id=run_id, workflow=workflow.code,
                           scope=context.scope)

    precondition = checks_module.run_all(workflow.preconditions, context)
    if not precondition.ok:
        # Declared, not remembered: this is the "other workflows require other
        # areas before or after" relationship, evaluated rather than documented.
        outcome = StageOutcome(
            stage="preconditions", ordinal=0, outcome=FAILED,
            detail=(f"{workflow.code} cannot start — {precondition.reason}"))
        record.record(outcome)
        record.fail(outcome.detail)
        record.save(path)
        return RunOutcome(record, EXIT_FAILED, outcome.detail)

    for stage in workflow.ordered:
        done = record.outcome_for(stage.name)
        if done is not None and done.ok and stage.durable:
            continue                       # already satisfied, and it stuck

        allowed, why = record.may_advance_to(stage, context.fingerprint())
        if not allowed:
            outcome = StageOutcome(stage=stage.name, ordinal=stage.ordinal,
                                   outcome=FAILED, detail=why)
            record.record(outcome)
            record.fail(why)
            record.save(path)
            return RunOutcome(record, EXIT_FAILED, why)

        outcome = _run_stage(stage, context)
        record.record(outcome)

        if outcome.outcome == HALTED:
            record.save(path)
            return RunOutcome(record, EXIT_HALTED, outcome.detail)
        if outcome.outcome == FAILED and stage.blocking:
            # Only the engine knows a stage is blocking, so only the engine may
            # declare the run failed. The record deliberately does not infer it.
            record.fail(outcome.detail)
            record.save(path)
            return RunOutcome(record, EXIT_FAILED, outcome.detail)
        record.save(path)
        if outcome.outcome == FAILED:
            # F-4: a reporting stage's findings are its output. The run
            # continues and the finding is kept, rather than being either
            # discarded or promoted into a blocker.
            context.notes.append(f"{stage.name}: {outcome.detail}")

    record.finish()
    record.save(path)
    return RunOutcome(record, EXIT_OK, "")
