"""
Workflow orchestration (application spec §3.2, §3.4).

§3.2 has described seven ordered stages and two human gates since the
specification was approved. Nothing executed them: the ordering lived in a shell
script, two throwaway helpers under `/tmp`, four `print("next: ...")` hints, and
the operator's memory. This package is the part that was missing.

    stages.py    the workflows and the stage/handler registry — the only place
                 that knows the order
    handlers.py  thin bindings to work that already exists and is tested
    checks.py    named predicates that actually run
    engine.py    ordered execution, fail-fast, halt at a gate
    run.py       the durable record, so a halt survives the process
    lint.py      static consistency, run as a test

Importing this package registers the handlers, so `lint_all()` can see them.
"""
from metis_mcp.workflow import handlers as _handlers  # noqa: F401  (registration)
from metis_mcp.workflow.checks import CheckResult, registered as registered_checks
from metis_mcp.workflow.engine import Context, RunOutcome, run
from metis_mcp.workflow.lint import format_lint, lint_all
from metis_mcp.workflow.run import (
    EXIT_FAILED,
    EXIT_HALTED,
    EXIT_OK,
    FAILED,
    HALTED,
    PASSED,
    RunRecord,
    StageOutcome,
    format_run,
    run_id_for,
    run_path,
)
from metis_mcp.workflow.stages import (
    WORKFLOWS,
    Stage,
    Workflow,
    format_workflows,
    get,
    registered_handlers,
)

__all__ = [
    "WORKFLOWS", "Stage", "Workflow", "get", "format_workflows",
    "registered_handlers", "registered_checks", "CheckResult",
    "Context", "RunOutcome", "run",
    "RunRecord", "StageOutcome", "format_run", "run_id_for", "run_path",
    "PASSED", "HALTED", "FAILED", "EXIT_OK", "EXIT_FAILED", "EXIT_HALTED",
    "lint_all", "format_lint",
]
