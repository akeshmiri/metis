"""
The durable record of one workflow execution (application spec F-3, §3.2).

**Why a file and not the `Run` node.** `Run` requires `criterion`, which is
meaningless before path generation, and the relationship catalogue gives it
exactly one edge (`Run-[:PRODUCED]->Scenario`), so a workflow run has no legal
way to point at its own scope. Extending the ontology to fix that is a real
change and a separate decision; meanwhile every other durable human artefact in
this codebase is already a file beside the model -- `ReviewState`, `OverrideLog`,
`PublicationLedger`. This follows them, and the side effect is that halt-and-
resume works with no database at all, which is the right property for the thing
that has to survive a failed stage.

**Status is derived, never asserted.** Atlas's `stage-gate.json` takes a
`--status` argument and writes whatever the caller passes; nothing validates it
and nothing checks that a prior stage passed. The result is a ledger that agrees
with whoever wrote to it last. Here a `StageOutcome` can only be produced by
actually running the stage, and `RunRecord.may_advance_to` refuses on the two
things that ledger could not see: a prior stage that did not pass, and an input
that has moved since it did.

**The fingerprint is the part that is easy to leave out.** "Every prior stage
passed" is a statement about the past. A run halts at a gate on Tuesday, someone
edits the model on Wednesday, and Thursday's resume would walk straight past a
validation result that no longer describes anything. Each outcome therefore
records the fingerprint of what it ran against, and resuming re-computes it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# What running a stage can conclude. Three, not two: F-9 says a failed stage
# stops the pipeline, but F-4 says reconciliation NEVER blocks -- its findings
# are the output. Collapsing "produced findings" into "failed" would make the
# one stage whose whole job is to report gaps look like a broken one.
PASSED = "passed"
HALTED = "halted_at_gate"
FAILED = "failed"
OUTCOMES = (PASSED, HALTED, FAILED)

# Exit codes. `HALTED` is deliberately distinct from `FAILED`: a CI job needs to
# tell "waiting on a human, as designed" from "broken", and one non-zero code
# for both makes an unreviewed model indistinguishable from a crash.
#
# 5, not 3: the CLI already uses 1 generic, 2 ApprovalRequired, 3
# GraphNotConfigured and 4 ValidationFailed. Reusing 3 would make "waiting on a
# reviewer" and "no database configured" the same signal, which is precisely the
# distinction this code exists to draw.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_HALTED = 5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class StageOutcome:
    """What one stage concluded, and what it concluded it against."""

    stage: str
    ordinal: int
    outcome: str
    at: str = field(default_factory=_now)
    detail: str = ""
    # The fingerprint of the stage's inputs at the moment it ran. This is what
    # makes a later `resume` honest rather than merely ordered.
    input_fingerprint: str = ""
    # What a reader needs to act on a halt: the decision outstanding and the
    # exact command that records it. A gate that says only "blocked" makes the
    # human go and find out what it wants (§9.1 -- the interface is throughput).
    outstanding: list[str] = field(default_factory=list)
    next_command: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome == PASSED

    def to_dict(self) -> dict:
        return {
            "stage": self.stage, "ordinal": self.ordinal, "outcome": self.outcome,
            "at": self.at, "detail": self.detail,
            "input_fingerprint": self.input_fingerprint,
            "outstanding": list(self.outstanding), "next_command": self.next_command,
        }

    @staticmethod
    def from_dict(d: dict) -> "StageOutcome":
        return StageOutcome(
            stage=d["stage"], ordinal=int(d["ordinal"]), outcome=d["outcome"],
            at=d.get("at", ""), detail=d.get("detail", ""),
            input_fingerprint=d.get("input_fingerprint", ""),
            outstanding=list(d.get("outstanding", ())),
            next_command=d.get("next_command", ""),
        )


@dataclass
class RunRecord:
    """One execution of one workflow over one scope."""

    run_id: str
    workflow: str
    scope: str
    started_at: str = field(default_factory=_now)
    outcomes: list[StageOutcome] = field(default_factory=list)
    # Set when the run stops at a gate. Unlike Atlas's `blocked_on` -- which is
    # computed and then read by nothing -- this is what `resume` dispatches on.
    blocked_on: str | None = None
    finished_at: str | None = None
    failed_reason: str | None = None

    # ---- reading -------------------------------------------------------

    def outcome_for(self, stage: str) -> StageOutcome | None:
        for o in reversed(self.outcomes):
            if o.stage == stage:
                return o
        return None

    @property
    def completed_stages(self) -> set[str]:
        return {o.stage for o in self.outcomes if o.ok}

    @property
    def is_blocked(self) -> bool:
        return self.blocked_on is not None

    @property
    def is_complete(self) -> bool:
        """Complete means every stage ran and none of them blocked the run.

        Deliberately not "finished_at is set". An earlier version stamped
        `finished_at` whenever a stage failed and then reported the run as
        complete -- so a run that stopped dead at G1 printed `complete`, which is
        exactly the "partial result presented as a complete one" F-10 prohibits.
        Only `finish()` may declare completion, and the engine calls it only
        after the last stage.
        """
        return self.finished_at is not None and not self.is_blocked and not self.failed

    @property
    def failed(self) -> bool:
        return self.failed_reason is not None

    def may_advance_to(self, stage, current_fingerprint: str) -> tuple[bool, str]:
        """Whether `stage` may run now. Returns `(ok, reason_if_not)`.

        Two refusals, and the second is the one a naive engine omits:

        1. a prior stage in this workflow did not pass -- the ordering is not a
           suggestion;
        2. a prior stage passed against a *different* input -- its conclusion
           describes something that is no longer there.
        """
        for prior in stage.requires:
            outcome = self.outcome_for(prior)
            if outcome is None:
                return False, (
                    f"stage {stage.name!r} requires {prior!r}, which has not run "
                    f"in this run. Stages are ordered, and skipping one means "
                    f"acting on evidence nobody produced")
            if not outcome.ok:
                return False, (
                    f"stage {stage.name!r} requires {prior!r}, which ended "
                    f"{outcome.outcome!r}: {outcome.detail or 'no detail recorded'}")
            if (outcome.input_fingerprint and current_fingerprint
                    and outcome.input_fingerprint != current_fingerprint):
                return False, (
                    f"stage {prior!r} passed against input "
                    f"{outcome.input_fingerprint}, but the input is now "
                    f"{current_fingerprint}. Its conclusion describes a model "
                    f"that has since changed — re-run from {prior!r} rather than "
                    f"resuming past a result that no longer applies (N-14)")
        return True, ""

    # ---- writing -------------------------------------------------------

    def record(self, outcome: StageOutcome) -> None:
        """Append an outcome. Does **not** decide whether the run is over.

        Whether a failure ends the run depends on `Stage.blocking`, which is the
        engine's knowledge, not this record's -- F-4's reconciliation stage fails
        with findings and the run rightly continues.
        """
        self.outcomes.append(outcome)
        self.blocked_on = outcome.stage if outcome.outcome == HALTED else None
        if outcome.outcome != FAILED:
            self.failed_reason = None

    def fail(self, reason: str) -> None:
        self.failed_reason = reason
        self.blocked_on = None
        self.finished_at = _now()

    def finish(self) -> None:
        self.blocked_on = None
        self.failed_reason = None
        self.finished_at = _now()

    # ---- persistence ---------------------------------------------------

    def to_json(self) -> str:
        return json.dumps({
            "run_id": self.run_id, "workflow": self.workflow, "scope": self.scope,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "blocked_on": self.blocked_on, "failed_reason": self.failed_reason,
            "outcomes": [o.to_dict() for o in self.outcomes],
        }, indent=2)

    @staticmethod
    def from_json(text: str) -> "RunRecord":
        d = json.loads(text)
        return RunRecord(
            run_id=d["run_id"], workflow=d["workflow"], scope=d["scope"],
            started_at=d.get("started_at", ""), finished_at=d.get("finished_at"),
            blocked_on=d.get("blocked_on"), failed_reason=d.get("failed_reason"),
            outcomes=[StageOutcome.from_dict(o) for o in d.get("outcomes", ())],
        )

    @staticmethod
    def load(path: str | Path) -> "RunRecord | None":
        p = Path(path)
        return RunRecord.from_json(p.read_text()) if p.exists() else None

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json())


def runs_dir(root: str | Path | None = None) -> Path:
    """Where run records live: `$METIS_HOME/runs`, or under an explicit root.

    **This used to be `./.metis/runs`, relative to the working directory.** So a
    run started from the repository root and resumed from `metis-server/` looked
    up a different file, found nothing, and reported "no run to resume" for a
    run that plainly existed. Profiles and the CPG cache already live in
    `$METIS_HOME` for the same reason.

    `root` is still honoured, because tests want a `tmp_path` and the engine's
    resume path passes one.
    """
    if root is not None:
        return Path(root) / ".metis" / "runs"

    from code_analysis.project_profile import metis_home

    return metis_home() / "runs"


def run_path(run_id: str, root: str | Path | None = None) -> Path:
    return runs_dir(root) / f"{run_id}.json"


def run_id_for(workflow: str, scope: str) -> str:
    """Stable per `(workflow, scope)`, so resuming does not need a lookup.

    Content-derived rather than sequential, for D-8's reason: two invocations
    naming the same work converge on the same record instead of quietly starting
    a second run alongside the one that is already blocked.
    """
    return f"{workflow}--{scope}".replace("/", "-").replace(" ", "-")


def format_run(record: RunRecord) -> str:
    lines = [f"Run {record.run_id}  —  {record.workflow} over {record.scope}",
             f"  started {record.started_at}", ""]
    for o in record.outcomes:
        mark = {PASSED: "ok  ", HALTED: "HALT", FAILED: "FAIL"}.get(o.outcome, "?   ")
        lines.append(f"  {mark} {o.ordinal:>2}. {o.stage:<20} {o.detail}")
    if record.is_blocked:
        blocked = record.outcome_for(record.blocked_on)
        lines += ["", f"  BLOCKED at {record.blocked_on} — waiting on a human decision."]
        for item in (blocked.outstanding if blocked else [])[:12]:
            lines.append(f"      {item}")
        if blocked and len(blocked.outstanding) > 12:
            lines.append(f"      ... and {len(blocked.outstanding) - 12} more")
        if blocked and blocked.next_command:
            lines += ["", f"  Record the decision:", f"      {blocked.next_command}",
                      f"  Then:", f"      metis workflow "
                      f"resume {record.run_id}"]
        lines += ["",
                  "  Nothing auto-promotes on elapsed time (F-8). This run will wait "
                  "indefinitely,",
                  "  which is the safe failure: no tests generated beats tests "
                  "generated from an",
                  "  unreviewed model."]
    elif record.failed:
        lines += ["", f"  FAILED at {record.finished_at} — {record.failed_reason}",
                  "  Nothing was retried and no substitute artefact was produced (F-9)."]
    elif record.is_complete:
        lines += ["", f"  complete at {record.finished_at}"]
    return "\n".join(lines)
