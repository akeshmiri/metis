"""
The workflow layer (application spec §3.2, §3.4, F-4, F-8, F-9, F-10).

These tests exist mostly to pin the things Atlas got wrong, because each of them
is a *silent* failure -- the kind that leaves a green run behind:

  * a check that names no implementation must break the build, not print itself;
  * a handler that names no implementation must do the same;
  * advancing must verify prior stages passed, AND that they passed against the
    input that is still there;
  * a gate must halt distinguishably from a failure;
  * a failed run must never call itself complete.
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import replace

from metis_mcp.mbt.model import APPROVED, QUARANTINE, Model, State, Transition
from metis_mcp.workflow import (
    EXIT_FAILED,
    EXIT_HALTED,
    EXIT_OK,
    FAILED,
    HALTED,
    PASSED,
    Context,
    RunRecord,
    StageOutcome,
    WORKFLOWS,
    format_lint,
    lint_all,
    run,
)
from metis_mcp.workflow.lint import lint_workflow
from metis_mcp.workflow.stages import Stage, Workflow, handler


def tiny_model(approved: bool = False) -> Model:
    lifecycle = APPROVED if approved else QUARANTINE
    return Model(
        id="tiny-api",
        states={
            "Ready": State(id="Ready", name="Ready", surface="api",
                           is_initial=True, lifecycle_state=lifecycle),
            "Ok200": State(id="Ok200", name="Ok200", surface="api",
                           lifecycle_state=lifecycle),
        },
        transitions={
            "t1": Transition(id="t1", source="Ready", trigger="GET /thing",
                             target="Ok200", guard="", lifecycle_state=lifecycle),
        },
    )


# --------------------------------------------------------------------------
# The lint. Atlas's equivalent never checks that a reference resolves, which is
# why its manifest carries a `next_stages` entry pointing at a stage that does
# not exist and its agents name ~25 skills with no directory.
# --------------------------------------------------------------------------

def test_the_shipped_workflows_are_consistent():
    errors = lint_all()
    assert errors == [], format_lint(errors)


def test_a_check_with_no_implementation_fails_the_lint():
    """The central correction. Atlas prints these strings and calls it validation."""
    broken = Workflow(
        code="broken", summary="names a check nobody wrote",
        stages=(Stage("only", 1, "report", "s", checks=("no_such_check",)),))
    errors = lint_workflow(broken)
    assert any("no_such_check" in e and "not registered" in e for e in errors), errors


def test_a_handler_with_no_implementation_fails_the_lint():
    broken = Workflow(
        code="broken", summary="names work nobody wrote",
        stages=(Stage("only", 1, "no_such_handler", "s"),))
    errors = lint_workflow(broken)
    assert any("no_such_handler" in e for e in errors), errors


def test_a_stage_cannot_depend_on_one_that_runs_later():
    broken = Workflow(
        code="broken", summary="backwards",
        stages=(Stage("first", 1, "report", "s", requires=("second",)),
                Stage("second", 2, "report", "s")))
    errors = lint_workflow(broken)
    assert any("cannot depend on one that runs later" in e for e in errors), errors


def test_ordinals_must_be_contiguous_from_one():
    broken = Workflow(
        code="broken", summary="gap",
        stages=(Stage("a", 1, "report", "s"), Stage("b", 3, "report", "s")))
    assert any("ordinals must be exactly" in e for e in lint_workflow(broken))


def test_every_workflow_has_at_most_the_two_gates_the_spec_allows():
    """§3.4: 'Two, and only two.' Not two per stage — two kinds, G1 and G2."""
    for code, workflow in WORKFLOWS.items():
        gates = [s for s in workflow.stages if s.is_gate]
        assert len(gates) <= 1, (
            f"{code} declares {len(gates)} gates; a workflow crossing both G1 and "
            f"G2 should be two workflows, so each halt has one meaning")


# --------------------------------------------------------------------------
# Ordering and staleness — the two checks Atlas's `validate_stage_gate` omits.
# --------------------------------------------------------------------------

def test_a_stage_may_not_run_when_its_prerequisite_did_not():
    record = RunRecord(run_id="r", workflow="w", scope="s")
    stage = Stage("second", 2, "report", "s", requires=("first",))
    ok, why = record.may_advance_to(stage, "fp")
    assert not ok and "has not run" in why


def test_a_stage_may_not_run_when_its_prerequisite_failed():
    record = RunRecord(run_id="r", workflow="w", scope="s")
    record.record(StageOutcome("first", 1, FAILED, detail="broke"))
    stage = Stage("second", 2, "report", "s", requires=("first",))
    ok, why = record.may_advance_to(stage, "fp")
    assert not ok and "broke" in why


def test_a_stage_may_not_run_on_input_that_moved_since_its_prerequisite_passed():
    """The check a naive engine leaves out.

    'Every prior stage passed' is a claim about the past. Without the
    fingerprint, a run that halts on Tuesday resumes on Thursday straight past a
    validation result describing a model somebody edited on Wednesday.
    """
    record = RunRecord(run_id="r", workflow="w", scope="s")
    record.record(StageOutcome("first", 1, PASSED, input_fingerprint="aaaa"))
    stage = Stage("second", 2, "report", "s", requires=("first",))
    ok, why = record.may_advance_to(stage, "bbbb")
    assert not ok
    assert "aaaa" in why and "bbbb" in why and "N-14" in why


def test_the_same_input_advances():
    record = RunRecord(run_id="r", workflow="w", scope="s")
    record.record(StageOutcome("first", 1, PASSED, input_fingerprint="aaaa"))
    stage = Stage("second", 2, "report", "s", requires=("first",))
    assert record.may_advance_to(stage, "aaaa")[0]


def test_a_model_hashes_the_same_however_it_was_loaded():
    """Landing namespaces ids by model; that is storage, not substance (I-2).

    Leaving the prefix in made a workflow that extracted from a file and resumed
    against the graph see its own earlier stages as stale, and refuse to continue
    over a change that had not happened.
    """
    from metis_mcp.review.state import source_fingerprint

    bare = tiny_model()
    namespaced = Model(
        id=bare.id,
        states={f"tiny-api::{k}": replace(v, id=f"tiny-api::{v.id}")
                for k, v in bare.states.items()},
        transitions={f"tiny-api::{k}": replace(
            v, id=f"tiny-api::{v.id}", source=f"tiny-api::{v.source}",
            target=f"tiny-api::{v.target}") for k, v in bare.transitions.items()},
    )
    assert source_fingerprint(bare) == source_fingerprint(namespaced)


# --------------------------------------------------------------------------
# Run outcomes.
# --------------------------------------------------------------------------

def test_a_failed_run_never_reports_itself_complete():
    """F-10: a partial result is never presented as a complete one."""
    record = RunRecord(run_id="r", workflow="w", scope="s")
    record.record(StageOutcome("a", 1, FAILED, detail="nope"))
    record.fail("nope")
    assert record.failed and not record.is_complete


def test_a_halted_run_is_blocked_not_finished():
    record = RunRecord(run_id="r", workflow="w", scope="s")
    record.record(StageOutcome("gate", 1, HALTED, detail="waiting"))
    assert record.is_blocked and not record.is_complete and not record.failed


def test_halting_and_failing_have_different_exit_codes():
    """CI must tell 'a human has not decided' from 'the pipeline is broken'."""
    assert EXIT_HALTED != EXIT_FAILED != EXIT_OK
    # And neither may collide with the CLI's existing meanings (1 generic,
    # 2 ApprovalRequired, 3 GraphNotConfigured, 4 ValidationFailed).
    assert EXIT_HALTED not in (0, 1, 2, 3, 4)


def test_a_run_record_survives_a_round_trip():
    record = RunRecord(run_id="r", workflow="w", scope="s")
    record.record(StageOutcome("a", 1, PASSED, input_fingerprint="aaaa",
                               outstanding=["x"], next_command="do x"))
    record.record(StageOutcome("gate", 2, HALTED, detail="waiting"))
    again = RunRecord.from_json(record.to_json())
    assert again.blocked_on == "gate"
    assert again.outcome_for("a").input_fingerprint == "aaaa"
    assert again.outcome_for("a").next_command == "do x"


# --------------------------------------------------------------------------
# The engine, end to end, on a throwaway workflow.
# --------------------------------------------------------------------------

@handler("_test_pass")
def _h_pass(context) -> tuple:
    context.model = tiny_model(approved=context.expect_prior_approval)
    return PASSED, "did the thing", (), ""


@handler("_test_report_finding")
def _h_report(context) -> tuple:
    return FAILED, "found 3 gaps", (), ""


@handler("_test_boom")
def _h_boom(context) -> tuple:
    raise RuntimeError("the handler exploded")


def _tmp_run(workflow, context):
    with tempfile.TemporaryDirectory() as root:
        return run(workflow, context, root=root)


def test_a_reporting_stage_that_finds_something_does_not_stop_the_run():
    """F-4: reconciliation NEVER blocks — its findings are the output.

    F-9 says a failed stage stops the pipeline, and F-4 says this one does not.
    `blocking=False` is what keeps the two rules from contradicting each other;
    without it the one stage whose job is to surface gaps looks like the broken
    one.
    """
    wf = Workflow(code="rep", summary="reports", stages=(
        Stage("work", 1, "_test_pass", "s"),
        Stage("findings", 2, "_test_report_finding", "s", blocking=False),
    ))
    outcome = _tmp_run(wf, Context(workflow="rep", scope="s"))
    assert outcome.exit_code == EXIT_OK
    assert outcome.record.is_complete
    # The finding is kept, not discarded and not promoted into a blocker.
    assert "found 3 gaps" in outcome.record.outcome_for("findings").detail


def test_a_blocking_stage_that_fails_stops_the_run():
    wf = Workflow(code="blk", summary="blocks", stages=(
        Stage("work", 1, "_test_report_finding", "s"),
    ))
    outcome = _tmp_run(wf, Context(workflow="blk", scope="s"))
    assert outcome.exit_code == EXIT_FAILED
    assert outcome.record.failed and not outcome.record.is_complete


def test_a_handler_that_raises_is_reported_not_recovered_from():
    """F-9: no retry, no alternative path, no substitute artefact."""
    wf = Workflow(code="boom", summary="raises", stages=(
        Stage("work", 1, "_test_boom", "s"),
    ))
    outcome = _tmp_run(wf, Context(workflow="boom", scope="s"))
    assert outcome.exit_code == EXIT_FAILED
    assert "the handler exploded" in outcome.record.outcomes[0].detail


def test_an_unregistered_check_fails_the_run_rather_than_being_skipped():
    """A skipped check is a decorative check — Atlas's exact state."""
    wf = Workflow(code="ghost", summary="ghost check", stages=(
        Stage("work", 1, "_test_pass", "s", checks=("not_a_real_check",)),
    ))
    outcome = _tmp_run(wf, Context(workflow="ghost", scope="s"))
    assert outcome.exit_code == EXIT_FAILED
    assert "not registered" in outcome.record.outcomes[0].detail


def test_a_gate_halts_and_resume_continues_once_the_decision_is_recorded():
    wf = Workflow(code="gated", summary="has a gate", stages=(
        Stage("work", 1, "_test_pass", "s"),
        Stage("gate", 2, "g1", "the gate", requires=("work",), is_gate=True,
              checks=("model_is_approved",)),
    ))
    with tempfile.TemporaryDirectory() as root:
        context = Context(workflow="gated", scope="s")
        context.args = type("A", (), {"journey": "", "surface": "api",
                                      "model": "m.json"})()
        first = run(wf, context, root=root)
        assert first.exit_code == EXIT_HALTED
        assert first.record.blocked_on == "gate"
        # The halt must say what is outstanding and how to record it (§9.1).
        halted = first.record.outcome_for("gate")
        assert halted.outstanding and halted.next_command

        # The human decides, and the context is RECONSTITUTED from durable
        # state — the same thing `cli._workflow_context` does by re-loading the
        # model from the graph. A resumed run does not replay `work`, because
        # replaying a passed stage would re-do its external effects as a side
        # effect of resuming.
        resumed_context = Context(workflow="gated", scope="s",
                                  model=tiny_model(approved=True))
        resumed_context.args = context.args
        second = run(wf, resumed_context, root=root, resume=True)
        assert second.exit_code == EXIT_OK, second.message
        assert second.record.is_complete


def test_resume_with_no_prior_run_is_an_error_not_a_fresh_start():
    """Silently starting over would discard a decision somebody already made."""
    wf = WORKFLOWS["coverage-report"]
    with tempfile.TemporaryDirectory() as root:
        outcome = run(wf, Context(workflow=wf.code, scope="nothing-here"),
                      root=root, resume=True)
    assert outcome.exit_code == EXIT_FAILED
    assert "no run to resume" in outcome.message


def test_a_precondition_stops_a_workflow_before_its_first_stage():
    """Cross-workflow ordering, declared and evaluated rather than remembered."""
    wf = WORKFLOWS["test-generate"]
    context = Context(workflow=wf.code, scope="s", model=tiny_model(approved=False))
    outcome = _tmp_run(wf, context)
    assert outcome.exit_code == EXIT_FAILED
    assert "cannot start" in outcome.message
    assert outcome.record.outcomes[0].stage == "preconditions"


def test_every_stage_of_the_specs_pipeline_appears_in_a_workflow():
    """§3.2's seven stages must all be reachable, or the engine has quietly
    become a second, shorter definition of the pipeline."""
    names = {s.name for w in WORKFLOWS.values() for s in w.stages}
    for required in ("validate", "reconcile", "generate-paths", "render", "publish"):
        assert required in names, f"§3.2 stage {required!r} is in no workflow"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:                                    # noqa: BLE001
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)


# --------------------------------------------------------------------------
# Durability. A resumed run skips stages that passed — so a stage whose product
# lives only in memory leaves the next one with nothing. This is not
# hypothetical: `publish` failed with "nothing to publish" the first time it ran
# after a resume, because `render` had been skipped as already-passed.
# --------------------------------------------------------------------------

@handler("_test_gate")
def _h_gate(context) -> tuple:
    """A gate that halts until `--confirm` is present, without the real G2's
    dependency on rendered case objects."""
    if getattr(context.args, "confirm", "") == "publish":
        return PASSED, "confirmed", (), ""
    return HALTED, "waiting for the literal confirmation", ["one case"], "re-run --confirm"


@handler("_test_produces")
def _h_produces(context) -> tuple:
    context.cases = ["a", "b"]
    return PASSED, "produced 2", (), ""


@handler("_test_consumes")
def _h_consumes(context) -> tuple:
    if not context.cases:
        return FAILED, "nothing to consume", (), ""
    return PASSED, f"consumed {len(context.cases)}", (), ""


def test_a_non_durable_stage_is_re_run_on_resume():
    wf = Workflow(code="dur", summary="durability", stages=(
        Stage("produce", 1, "_test_produces", "s", durable=False),
        Stage("gate", 2, "_test_gate", "the gate", requires=("produce",), is_gate=True),
        Stage("consume", 3, "_test_consumes", "s", requires=("gate",)),
    ))
    with tempfile.TemporaryDirectory() as root:
        args = type("A", (), {"confirm": "", "as_user": "alice"})()
        first = Context(workflow="dur", scope="s")
        first.args = args
        assert run(wf, first, root=root).exit_code == EXIT_HALTED

        # Resume in a FRESH context, as a new process would have.
        second = Context(workflow="dur", scope="s")
        second.args = type("A", (), {"confirm": "publish", "as_user": "alice"})()
        outcome = run(wf, second, root=root, resume=True)
        assert outcome.exit_code == EXIT_OK, outcome.message
        assert second.cases, "the non-durable stage must have re-run"


def test_a_durable_stage_is_not_re_run_on_resume():
    """`land` and `publish` write. Repeating them on every resume would write
    again, which is why durability is opt-out rather than the default."""
    ran: list[str] = []

    @handler("_test_counts")
    def _counted(context) -> tuple:
        ran.append("x")
        return PASSED, "ran", (), ""

    wf = Workflow(code="dur2", summary="durability", stages=(
        Stage("write", 1, "_test_counts", "s"),
        Stage("gate", 2, "_test_gate", "the gate", requires=("write",), is_gate=True),
    ))
    with tempfile.TemporaryDirectory() as root:
        first = Context(workflow="dur2", scope="s")
        first.args = type("A", (), {"confirm": "", "as_user": "alice"})()
        run(wf, first, root=root)
        second = Context(workflow="dur2", scope="s")
        second.args = type("A", (), {"confirm": "publish", "as_user": "alice"})()
        run(wf, second, root=root, resume=True)
    assert len(ran) == 1, "a durable stage must not repeat its write on resume"


# --------------------------------------------------------------------------
# knowledge-capture (§4.5, §4.6; S-13, I-5)
# --------------------------------------------------------------------------

def _knowledge_file(tmpdir, entries=None, model_id="admin-api"):
    import json
    from pathlib import Path
    statement = "if user has admin permission then it should be able to do 1"
    entries = entries if entries is not None else [{
        "id": "AC-001",
        "text": ("Given the user has admin permission, when they do 1, "
                 "then the request succeeds."),
        "requirement_id": "REQ-ADMIN-01",
        "polarity": "positive", "derived": "stated",
        "source_statement": statement,
    }]
    path = Path(tmpdir) / "knowledge.json"
    path.write_text(json.dumps({
        "knowledge_version": "metis.knowledge/1",
        "model_id": model_id, "surface": "api",
        "statement": statement, "initial_state": "",
        "entries": entries,
    }))
    return str(path)


def _knowledge_context(path):
    context = Context(workflow="knowledge-capture", scope="admin-api")
    context.args = type("A", (), {
        "knowledge": path, "model": None, "author": "tester",
        "journey": "admin", "surface": "api", "uri": None, "user": None,
        "job_id": "test", "confirm": "", "as_user": "tester"})()
    return context


def test_knowledge_capture_is_registered_and_lints():
    from metis_mcp.workflow.stages import get as get_workflow

    workflow = get_workflow("knowledge-capture")
    assert workflow is not None, "the workflow must exist to be routable"
    assert lint_workflow(workflow) == []
    assert [s.name for s in workflow.ordered] == [
        "check", "mine", "compare", "land", "requirement-risk",
        "model-approval"]


def test_the_compare_stage_never_blocks():
    """F-4's rule, applied here: a contradiction is the most valuable thing this
    run produces. Treating it as a failure would stop the run reporting it."""
    from metis_mcp.workflow.stages import get as get_workflow

    compare = get_workflow("knowledge-capture").stage("compare")
    assert compare.blocking is False


def test_a_compound_criterion_stops_the_run_before_anything_is_mined():
    """Blocking here, unlike `check_ac_atomicity`'s advisory finding on a model.

    A person is writing these, so a compound criterion is a correctable input —
    and letting it through would mine several behaviours into one transition,
    which no later stage can take apart again.
    """
    from metis_mcp.workflow.stages import get as get_workflow

    with tempfile.TemporaryDirectory() as d:
        path = _knowledge_file(d, entries=[{
            "id": "AC-001",
            "text": ("Given the user has admin permission, when they do 1, then "
                     "the request succeeds and an audit entry is written."),
            "polarity": "positive", "derived": "stated",
            "source_statement": "if user has admin permission then it can do 1",
        }])
        outcome = _tmp_run(get_workflow("knowledge-capture"), _knowledge_context(path))
    assert outcome.exit_code not in (0, EXIT_HALTED)
    assert "not_atomic" in outcome.record.failed_reason


def test_an_unlabelled_inference_stops_the_run():
    """S-13: a criterion nobody stated, presented as though somebody had."""
    from metis_mcp.workflow.stages import get as get_workflow

    statement = "if user has admin permission then it should be able to do 1"
    with tempfile.TemporaryDirectory() as d:
        path = _knowledge_file(d, entries=[{
            "id": "AC-002",
            "text": ("Given the user does not have admin permission, when they "
                     "do 1, then the request is rejected."),
            "polarity": "negative", "derived": "inferred_complement",
            "source_statement": statement,
        }])
        outcome = _tmp_run(get_workflow("knowledge-capture"), _knowledge_context(path))
    assert outcome.exit_code not in (0, EXIT_HALTED)
    assert "ungrounded_complement" in outcome.record.failed_reason


def test_a_missing_knowledge_file_fails_with_its_path():
    from metis_mcp.workflow.stages import get as get_workflow

    outcome = _tmp_run(get_workflow("knowledge-capture"),
                       _knowledge_context("/nonexistent/knowledge.json"))
    assert outcome.exit_code not in (0, EXIT_HALTED)
    assert "/nonexistent/knowledge.json" in outcome.record.failed_reason


def test_a_clean_file_mines_a_quarantine_model():
    """The check and mine stages run without any graph at all."""
    from metis_mcp.workflow.handlers import _knowledge_check, _knowledge_mine

    with tempfile.TemporaryDirectory() as d:
        context = _knowledge_context(_knowledge_file(d))
        assert _knowledge_check(context)[0] == PASSED
        outcome, detail, _, _ = _knowledge_mine(context)
    assert outcome == PASSED, detail
    assert len(context.model.transitions) == 1
    assert all(t.lifecycle_state == QUARANTINE
               for t in context.model.transitions.values()), (
        "S-4: a source produces candidates, never approved facts"
    )


def test_derivation_edges_join_the_model_to_its_evidence():
    """`Transition -[:DERIVED_FROM]-> Endpoint`, planned from the handler join.

    Landing both layers and linking neither produced 808 evidence nodes and 9
    model nodes with nothing between them: "which endpoint is this transition
    from" and "which endpoints have no behaviour" were both unanswerable, and
    the second is the question that makes "12 endpoints, 3 transitions" legible
    rather than alarming.

    The label matters as much as the id. A classified transition carries
    `:ApiCall` INSTEAD of `:Transition`, so an edge planned against the parent
    matches no node and is reported as unmatched rather than failing.
    """
    from types import SimpleNamespace

    from metis_mcp.mbt.model import Model, State, Transition
    from metis_mcp.model_sources.landing import LandingPlan
    from metis_mcp.workflow.handlers import _plan_derivation_edges

    handler = "com.example.Ctrl.get:org.springframework.http.ResponseEntity()"
    model = Model(
        id="records-api",
        states={"Ready": State(id="Ready", name="Ready", surface="api",
                               is_initial=True),
                "Ok200": State(id="Ok200", name="Ok200", surface="api")},
        transitions={f"{handler}::GET->Ok200": Transition(
            id=f"{handler}::GET->Ok200", source="Ready", trigger="GET /x",
            target="Ok200")})
    model.reindex()

    endpoint = SimpleNamespace(handler_method_id=handler, http_method="GET",
                               path="/x", anchor={"file": "svc/A.java"})
    report = SimpleNamespace(endpoints=[endpoint])
    plan = LandingPlan(episode_id="ep-1")

    planned = _plan_derivation_edges(
        plan, SimpleNamespace(model=model, args=SimpleNamespace(surface="api")),
        report, "demo")
    assert planned == 1
    edge = plan.edges[-1]
    assert edge.rel_type == "DERIVED_FROM"
    assert edge.from_label == "ApiCall", "the specialisation, not the parent"
    assert edge.to_label == "Endpoint"
    assert edge.from_id.startswith("records-api::"), "landing namespaces every id"


def test_a_transition_with_no_matching_endpoint_plans_no_edge():
    """An authored model has no code facts behind it. Planning an edge to an
    endpoint that does not exist would merge nothing and report success."""
    from types import SimpleNamespace

    from metis_mcp.mbt.model import Model, State, Transition
    from metis_mcp.model_sources.landing import LandingPlan
    from metis_mcp.workflow.handlers import _plan_derivation_edges

    model = Model(
        id="login-api",
        states={"A": State(id="A", name="A", surface="api", is_initial=True),
                "B": State(id="B", name="B", surface="api")},
        transitions={"t1": Transition(id="t1", source="A", trigger="click",
                                      target="B")})
    model.reindex()
    plan = LandingPlan(episode_id="ep-1")
    planned = _plan_derivation_edges(
        plan, SimpleNamespace(model=model, args=SimpleNamespace(surface="api")),
        SimpleNamespace(endpoints=[]), "demo")
    assert planned == 0 and not plan.edges


# --------------------------------------------------------------------------
# `spec-writeback`'s terminal stage.
#
# **It used to return `PASSED, "written back"` and write nothing.**
# `specgen.writeback.plan_writeback` and `.apply` existed, were fully tested, and
# were reachable only from `metis spec --write-back`, so the workflow reported a
# write it had never performed. No test covered the handler, which is why it
# survived. These are that test.
# --------------------------------------------------------------------------

def _writeback_context(tmp_path, **arg_overrides):
    import argparse

    import metis_mcp.workflow.handlers  # noqa: F401 -- registers the handlers
    from metis_mcp.workflow.engine import Context
    from metis_mcp.workflow.stages import get_handler

    args = argparse.Namespace(confirm="publish", repo=str(tmp_path),
                              feature="", as_identity="dana", batch_size=1,
                              allow_unapproved=True)
    for key, value in arg_overrides.items():
        setattr(args, key, value)
    context = Context(workflow="spec-writeback", scope="records", args=args)
    return context, get_handler("writeback")


def test_the_writeback_stage_does_not_claim_a_write_with_no_destination(tmp_path):
    """The original bug's shape: a confident `PASSED` with nothing behind it."""
    context, handler = _writeback_context(tmp_path, repo="")
    context.specification = None
    from metis_mcp.workflow.run import PASSED

    outcome = handler(context)
    assert outcome[0] != PASSED or "written back" not in outcome[1]


def test_the_writeback_stage_does_not_claim_a_write_with_no_specification(tmp_path):
    """`spec` runs before `writeback`. If it did not, there is nothing to write,
    and saying otherwise is the same lie in a different place."""
    context, handler = _writeback_context(tmp_path)
    context.specification = None
    outcome = handler(context)
    assert "written back" not in outcome[1]


def test_the_writeback_stage_still_halts_without_the_literal(tmp_path):
    """T-18: the gate is unchanged. Implementing the write must not open it."""
    context, handler = _writeback_context(tmp_path, confirm="")
    context.specification = None
    from metis_mcp.workflow.run import HALTED

    outcome = handler(context)
    assert outcome[0] == HALTED
    assert "publish" in outcome[1]


def test_the_writeback_stage_needs_the_installation_switch_too(tmp_path,
                                                               monkeypatch):
    """Writing into a product repository is an external write, gated the same
    way publication is: the literal AND `METIS_ALLOW_EXTERNAL_WRITES`. A
    confirmation an agent can type is not enough on its own."""
    from metis_mcp.specgen import build as build_spec

    monkeypatch.delenv("METIS_ALLOW_EXTERNAL_WRITES", raising=False)
    model = tiny_model(approved=True)
    context, handler = _writeback_context(tmp_path)
    context.model = model
    context.specification = build_spec(model)

    outcome = handler(context)
    assert "Nothing was written" in outcome[1]
    assert not list(tmp_path.rglob("*.md"))


def test_the_writeback_stage_actually_writes_a_file(tmp_path, monkeypatch):
    """The half that was missing: a real file on disk, not a returned sentence.

    This is the assertion the original handler could never have passed — it
    returned `PASSED, "written back"` without calling the writer at all."""
    from metis_mcp.specgen import build as build_spec
    from metis_mcp.workflow.run import PASSED

    monkeypatch.setenv("METIS_ALLOW_EXTERNAL_WRITES", "yes")
    model = tiny_model(approved=True)
    context, handler = _writeback_context(tmp_path)
    context.model = model
    context.specification = build_spec(model)

    outcome = handler(context)
    written = list(tmp_path.rglob("*.md"))
    assert outcome[0] == PASSED, outcome
    assert written, f"the stage reported {outcome[1]!r} and wrote no file"


# ---------------------------------------------------------------------------
# Intake as a workflow (§3.2 stages 1 and 2)
# ---------------------------------------------------------------------------
#
# Requirement ingestion was the only major path with no workflow, no gate and no
# resumable run: `metis intake fetch` and `metis intake land` existed and
# nothing knew their order. Model recovery and test generation both had full
# gated workflows, which is the wrong asymmetry for a tool whose first job is
# requirement management.

def test_intake_is_a_workflow_and_stops_for_a_human():
    from metis_mcp.workflow.stages import WORKFLOWS

    intake = WORKFLOWS["intake"]
    assert [s.name for s in intake.stages] == [
        "fetch", "validate", "analysis", "readiness", "land",
        "requirement-risk", "model-approval"]
    gates = [s for s in intake.stages if s.is_gate]
    assert len(gates) == 1 and gates[0].name == "model-approval", (
        "a landed requirement is a claim somebody made, not one Métis agrees "
        "with (S-4) — the gate is the whole point of it being a workflow")


def test_the_reading_happens_before_anything_is_landed():
    """**Intent is a pre-processor, and this is what makes that true.**

    This workflow used to fetch, validate, land, and only THEN assess risk — so
    the first moment anybody saw what was wrong with a claim was after it was a
    node in the graph. `analysis` and `readiness` sit before `land` now, and
    `land` requires the second of them.
    """
    from metis_mcp.workflow.stages import WORKFLOWS

    stages = {s.name: s for s in WORKFLOWS["intake"].stages}
    order = [s.name for s in WORKFLOWS["intake"].stages]
    assert order.index("analysis") < order.index("land")
    assert order.index("readiness") < order.index("land")
    assert "readiness" in stages["land"].requires, (
        "land must depend on readiness, or the order is decoration")


def test_readiness_is_a_blocking_stage_and_not_a_second_gate():
    """§3.4 keeps one halt per workflow so each halt has one meaning, and this
    is not a halt: there is no literal that passes it. A need nobody has
    specified is fixed by specifying it, not by anybody agreeing to import it
    anyway — which makes it F-9's contract, a failed stage that names the action
    required."""
    from metis_mcp.workflow.stages import WORKFLOWS

    for code in ("intake", "intent-review"):
        readiness = next(s for s in WORKFLOWS[code].stages
                         if s.name == "readiness")
        assert not readiness.is_gate, f"{code}: readiness must not be a gate"
        assert readiness.blocking, (
            f"{code}: readiness must block — a claim that cannot be represented "
            f"must not reach land")


def test_the_analysis_stage_does_not_block_the_run():
    """F-4 again: the gaps ARE this stage's output. A run that stopped here
    would withhold exactly the list somebody needs in order to close them."""
    from metis_mcp.workflow.stages import WORKFLOWS

    for code in ("intake", "intent-review"):
        analysis = next(s for s in WORKFLOWS[code].stages if s.name == "analysis")
        assert not analysis.blocking, f"{code}: analysis must not block"


def test_the_validate_stage_does_not_block_the_run():
    """F-4: a stage whose findings ARE its output never blocks.

    A non-conformant document lands as a Finding pointing at knowledge-capture,
    which is the honest outcome for free prose (S-13) and not a failure of the
    run. A blocking validate would make one bad ticket abandon a backlog.
    """
    from metis_mcp.workflow.stages import WORKFLOWS

    validate = next(s for s in WORKFLOWS["intake"].stages if s.name == "validate")
    assert not validate.blocking


def test_the_land_stage_is_checked_for_quarantine():
    from metis_mcp.workflow.stages import WORKFLOWS

    land = next(s for s in WORKFLOWS["intake"].stages if s.name == "land")
    assert "landed_at_quarantine" in land.checks


def test_intake_fetch_refuses_a_profile_with_no_requirements_block(tmp_path,
                                                                   monkeypatch):
    """A profile that says nothing about requirements is not an empty backlog.

    Reporting "0 documents" would be a silent success: nobody configured a
    source, and that is a different answer from a source that is empty.
    """
    import json as _json
    import types

    from metis_mcp.workflow import handlers
    from metis_mcp.workflow.run import FAILED

    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "bare.json").write_text(_json.dumps({
        "version": "metis.project-profile/1", "project": "bare",
        "language": "javasrc", "framework": "spring-mvc",
        "journeys": [{"journey": "j", "surface": "api", "modules": ["m"]}]}))
    monkeypatch.setenv("METIS_HOME", str(tmp_path))

    context = types.SimpleNamespace(
        args=types.SimpleNamespace(project="bare", out=str(tmp_path / "out")))
    status, detail, _, _ = handlers._intake_fetch(context)
    assert status == FAILED
    assert "requirements" in detail


def test_intake_fetch_writes_one_document_per_item_from_a_fixture(tmp_path,
                                                                  monkeypatch):
    """The batch path, end to end, with no tracker in existence.

    `demo_project/trackers/jira.tracker.json` carries both outcomes on purpose:
    DEMO-1 is EARS-conformant and becomes a Requirement, DEMO-2 is free prose
    and becomes a Finding. A corpus with only the happy case would prove the
    pipeline runs and nothing about what it decides.
    """
    import json as _json
    import types
    from pathlib import Path as _Path

    from metis_mcp.workflow import handlers
    from metis_mcp.workflow.run import PASSED

    trackers = _Path(__file__).parent / "demo_project" / "trackers"
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "demo.json").write_text(_json.dumps({
        "version": "metis.project-profile/1", "project": "demo",
        "language": "javasrc", "framework": "spring-mvc",
        "journeys": [{"journey": "j", "surface": "api", "modules": ["m"]}],
        "requirements": {"system": "jira", "fixture_dir": str(trackers),
                         "keys": ["DEMO-1", "DEMO-2"]}}))
    monkeypatch.setenv("METIS_HOME", str(tmp_path))

    out = tmp_path / "uif"
    context = types.SimpleNamespace(
        args=types.SimpleNamespace(project="demo", out=str(out)))
    status, detail, _, _ = handlers._intake_fetch(context)

    assert status == PASSED, detail
    written = sorted(p.name for p in out.glob("*.uif.json"))
    assert written == ["DEMO-1.uif.json", "DEMO-2.uif.json"]
    assert context.intake_documents


def test_a_key_that_matched_nothing_is_named(tmp_path, monkeypatch):
    """"This ticket does not exist" and "I did not look for it" are different
    answers, and only one of them is safe before a review."""
    import json as _json
    import types
    from pathlib import Path as _Path

    from metis_mcp.workflow import handlers

    trackers = _Path(__file__).parent / "demo_project" / "trackers"
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "demo.json").write_text(_json.dumps({
        "version": "metis.project-profile/1", "project": "demo",
        "language": "javasrc", "framework": "spring-mvc",
        "journeys": [{"journey": "j", "surface": "api", "modules": ["m"]}],
        "requirements": {"system": "jira", "fixture_dir": str(trackers),
                         "keys": ["DEMO-1", "DEMO-99"]}}))
    monkeypatch.setenv("METIS_HOME", str(tmp_path))

    context = types.SimpleNamespace(
        args=types.SimpleNamespace(project="demo", out=str(tmp_path / "uif")))
    _, detail, _, _ = handlers._intake_fetch(context)
    assert "DEMO-99" in detail


# ---------------------------------------------------------------------------
# A run that cannot find a divergence must say so (S-3/S-19)
# ---------------------------------------------------------------------------
#
# The failure this guards, measured on a real estate: eight services extracted,
# landed, validated and taken to the gate, every one ending at `reconcile -> no
# acceptance criteria in scope`. Clean runs, sound models, and the comparison
# that is the whole point of Metis had never executed -- because the profile
# declared no requirements source, so the only criteria in the graph were the
# ones drafted from the code they would be checked against.
#
# `reconcile` does say it, six stages later, phrased as a property of the scope
# rather than of the configuration. By then the summary reads like a result.


def _profile(configured: bool):
    """A stand-in profile whose requirements block is or is not configured."""
    import types as t

    return t.SimpleNamespace(
        requirements=t.SimpleNamespace(is_configured=configured))


def test_a_profile_with_no_requirements_source_is_told_it_cannot_diverge(
        monkeypatch):
    import types

    from code_analysis import project_profile
    from metis_mcp.workflow import handlers

    monkeypatch.setattr(project_profile, "load_project",
                        lambda name: _profile(configured=False))
    context = types.SimpleNamespace(args=types.SimpleNamespace(project="p"))

    findings = handlers._no_independent_source(context)
    assert findings, "a run that cannot possibly diverge reported nothing"
    # Named, not hinted: the reader must be able to act without reading source.
    assert "requirements" in findings[0]
    assert "code_derived" in findings[0]


def test_a_profile_that_declares_a_requirements_source_is_left_alone(
        monkeypatch):
    """The guard must not fire on the configuration it is asking for.

    Without this the test above passes against a function that returns the
    finding unconditionally, which is the shape of guard that gets switched off.
    """
    import types

    from code_analysis import project_profile
    from metis_mcp.workflow import handlers

    monkeypatch.setattr(project_profile, "load_project",
                        lambda name: _profile(configured=True))
    context = types.SimpleNamespace(args=types.SimpleNamespace(project="p"))

    assert handlers._no_independent_source(context) == ()


def test_an_unreadable_profile_does_not_turn_into_a_second_wrong_message(
        monkeypatch):
    """A profile that cannot be read is somebody else's error to report."""
    import types

    from code_analysis import project_profile
    from metis_mcp.workflow import handlers

    def boom(name):
        raise project_profile.ProfileMissing("no such profile")

    monkeypatch.setattr(project_profile, "load_project", boom)
    context = types.SimpleNamespace(args=types.SimpleNamespace(project="p"))

    assert handlers._no_independent_source(context) == ()


def test_ac_draft_carries_the_finding_out_of_the_stage(monkeypatch):
    """End to end through the handler, not just the helper.

    The helper being right proves nothing if `_ac_draft` drops its return value
    -- which is exactly how `carry_findings` failed before: the mechanism built
    a list and the caller printed its length.
    """
    import types

    from code_analysis import project_profile
    from metis_mcp.workflow import handlers

    monkeypatch.setattr(project_profile, "load_project",
                        lambda name: _profile(configured=False))

    from dataclasses import replace as _replace

    # Guarded, so the stage reaches the drafting branch rather than the
    # no-branch-facts early return. Both paths carry the finding; this exercises
    # the one where a draft was actually produced.
    model = tiny_model()
    model = _replace(model, transitions={
        k: _replace(t, guard="account is not locked")
        for k, t in model.transitions.items()})
    context = types.SimpleNamespace(
        model=model, args=types.SimpleNamespace(project="p"))
    status, detail, findings, _ = handlers._ac_draft(context)

    assert status == PASSED
    assert any("cannot" in f or "never be found to DIVERGE" in f
               for f in findings), findings


# ---------------------------------------------------------------------------
# change-approval
# ---------------------------------------------------------------------------
#
# Every part of this workflow existed before it did and none of it was reachable
# in order: the carry runs inside `land`, the grading lives in `change_review`,
# the file->transition join in `impact`. Somebody wanting to approve a change
# re-ran `model-build` and read a summary line.


def test_change_approval_is_registered_with_one_gate():
    w = WORKFLOWS["change-approval"]
    assert [s.name for s in w.ordered] == [
        "extract", "change-impact", "land", "validate", "change-review",
        "model-approval"]
    assert sum(1 for s in w.stages if s.is_gate) == 1


def test_the_two_reporting_stages_never_block():
    """F-4: a stage whose findings ARE its output must not stop the run.

    `change-impact` grading a diff as `critical` is information for the gate,
    not a reason to refuse to reach it.
    """
    w = WORKFLOWS["change-approval"]
    by_name = {s.name: s for s in w.stages}
    assert by_name["change-impact"].blocking is False
    assert by_name["change-review"].blocking is False
    # validate MUST block: I-18 revalidates the whole (state, trigger) group,
    # and a group that no longer satisfies M-18 cannot go to a gate.
    assert by_name["validate"].blocking is True


def test_change_impact_refuses_without_a_commit_range():
    """An empty diff and an unresolvable one must not read the same.

    `changed_files` answers an unanswerable range with `[]`, so defaulting
    `--since` would turn "I could not tell" into "nothing changed".
    """
    import types

    from metis_mcp.workflow import handlers

    context = types.SimpleNamespace(
        model=None, args=types.SimpleNamespace(since="", repo="/tmp"))
    status, detail, _, _ = handlers._change_impact(context)
    assert status == FAILED
    assert "--since" in detail


def test_change_review_names_each_revoked_approval_rather_than_counting():
    """The failure this guards is one this repository has already made.

    `carry_human_facts` builds `revoked` as "<id>: <reason>" strings precisely
    so a reviewer can see which approvals went, and the first caller printed
    `len(...)`. A revocation a reviewer cannot see is a decision taken on their
    behalf.
    """
    import types

    from metis_mcp.workflow import handlers

    context = types.SimpleNamespace(
        carry_revocations=["t01: behaviour changed", "t07: behaviour changed"],
        carry_renames=[], change_findings=[])
    status, detail, outstanding, _ = handlers._change_review(context)

    assert status == PASSED
    assert len(outstanding) == 2
    assert any("t01" in o for o in outstanding), outstanding
    assert any("t07" in o for o in outstanding), outstanding


def test_change_review_says_a_clean_result_is_not_an_endorsement():
    """C-11 through the whole surface: covered is not correct, and a change the
    model cannot fault is not a change the model approves."""
    import types

    from metis_mcp.workflow import handlers

    context = types.SimpleNamespace(
        carry_revocations=[], carry_renames=[], change_findings=[])
    _, detail, outstanding, _ = handlers._change_review(context)
    assert outstanding == ()
    assert "not a statement that the change is good" in detail


def test_a_proposed_rename_is_reported_as_not_applied():
    """I-22: a rename is proposed, never assumed. Carrying identity across one
    silently would move an approval onto an element nobody approved."""
    import types

    from metis_mcp.workflow import handlers

    context = types.SimpleNamespace(
        carry_revocations=[],
        carry_renames=["state Old -> New (91% similar; confirm it ...)"],
        change_findings=[])
    _, _, outstanding, _ = handlers._change_review(context)
    assert outstanding and "NOT applied" in outstanding[0]


# ---------------------------------------------------------------------------
# S-4 and I-17 disagree about a re-ingest
# ---------------------------------------------------------------------------


def test_a_carry_that_brings_approvals_forward_permits_them_at_landing():
    """`Context.expect_prior_approval` existed and NOTHING ever set it.

    S-4 refuses a model landing with Approved elements, because a source that
    approves its own output has bypassed G1. I-17 says the opposite for an
    element whose behaviour did not change: its approval is RETAINED. Both are
    right, and the flag that reconciles them was dead code -- so the first team
    to approve a model and re-extract would have hit a hard FAIL at `land`
    accusing their source of bypassing the gate.

    It stayed invisible because nothing had ever been approved: the pilot estate
    carried 430 elements and every one of them was `defer`.
    """
    from metis_mcp.workflow.checks import run_all

    approved = tiny_model(approved=True)
    context = Context(workflow="change-approval", scope="s", args=None,
                      model=approved)

    assert not run_all(("landed_at_quarantine",), context).ok, (
        "a source landing its own output as Approved must still be refused (S-4)")

    context.expect_prior_approval = True
    assert run_all(("landed_at_quarantine",), context).ok, (
        "an approval carried from the graph on unchanged behaviour is I-17, "
        "not an S-4 violation")


def test_the_carry_itself_sets_the_flag_that_permits_those_approvals(monkeypatch):
    """The wiring, not just the check.

    The test above sets `expect_prior_approval` by hand and so passes against a
    `_carry_forward` that never sets it -- which was the bug. This drives the
    real function and asserts the flag arrives, so removing the two lines that
    set it fails here.
    """
    import types

    from metis_mcp.mbt import graph_loader, graph_session
    from metis_mcp.workflow import handlers

    previous = tiny_model(approved=True)
    candidate = tiny_model()                      # same shape, at Quarantine

    class _Session:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(graph_session, "session", lambda *a, **k: _Session())
    monkeypatch.setattr(graph_loader, "load_from_graph",
                        lambda *a, **k: types.SimpleNamespace(model=previous))

    context = Context(workflow="change-approval", scope="s",
                      args=types.SimpleNamespace(uri="", user="",
                                                 journey="j", surface="api"),
                      model=candidate)
    result = types.SimpleNamespace(model=candidate)

    note = handlers._carry_forward(context, result)

    assert "carried" in note, note
    assert context.expect_prior_approval is True, (
        "the carry brought approvals onto the candidate and did not say so, so "
        "`landed_at_quarantine` will refuse a legitimate re-ingest (S-4 vs I-17)")


# ---------------------------------------------------------------------------
# The reconcile chain: three dead links in a row
# ---------------------------------------------------------------------------
#
# Every real run ended at `reconcile -> no acceptance criteria in scope`, and it
# was diagnosed as a missing requirements source. That was a third of it. Three
# separate things in one chain were built and never connected:
#
#   1. `ac_draft` wrote `context.drafts`; nothing landed them.
#   2. `_reconcile` read `context.criteria`; nothing in model-build set it.
#   3. `load_confirmed_matches` existed; nothing called it.
#
# Each of these is tested for the WIRING and not only for the function, because
# twice in this session a test of the function alone passed with the call site
# sabotaged.


class _ReconcileResult:
    """The four lists `_reconcile` formats. Named rather than a SimpleNamespace
    so a field renamed on the real result fails here instead of passing."""

    intent_matched: list = []
    documentation_matched: list = []
    unspecified_behaviour: list = []
    unimplemented: list = []


def test_the_land_stage_lands_the_drafted_criteria(monkeypatch):
    """Break 1. The stage reported `13/13 drafted` and the graph held none."""
    import types

    from metis_mcp.workflow import handlers

    landed: list = []

    class _Session:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("metis_mcp.mbt.graph_session.session",
                        lambda *a, **k: _Session())

    def fake_land(session, plan):
        landed.append(plan)
        return types.SimpleNamespace(nodes_written=len(plan.nodes),
                                     edges_written=len(plan.edges),
                                     unmatched=[], episode_id="ep-1",
                                     refused=None, superseded=[])

    monkeypatch.setattr("metis_mcp.model_sources.land", fake_land)

    model = tiny_model()
    context = Context(workflow="model-build", scope="s", model=model,
                      args=types.SimpleNamespace(uri="", user="", surface="api"))
    context.drafts = [types.SimpleNamespace(
        id="DRAFT-001", transition_id="t1", given="g", when="w", then="t",
        and_guard="", model_id=model.id, atomicity="atomic")]

    note = handlers._land_drafts(context, "ep-1")

    assert landed, "the drafts were never landed"
    assert "drafted criterion node(s)" in note
    assert landed[0].by_label("AcceptanceCriterion")


def test_the_land_STAGE_calls_the_draft_landing(monkeypatch):
    """**The wiring, and the test above does not cover it.**

    That one calls `_land_drafts` directly, so removing the call site from
    `_land` leaves it passing — which is precisely the hole that let the drafts
    go unlanded in the first place, and the third time in this session a test of
    a function passed while the call site was gone. This drives the STAGE.
    """
    import types

    from metis_mcp.workflow import handlers

    called = []
    monkeypatch.setattr(handlers, "_land_drafts",
                        lambda ctx, ep: called.append(ep) or "; 3 drafted")
    monkeypatch.setattr(handlers, "_land_evidence", lambda *a, **k: "")
    monkeypatch.setattr(handlers, "_carry_forward", lambda *a, **k: "")
    monkeypatch.setattr(handlers, "_land_stamped",
                        lambda *a, **k: types.SimpleNamespace(
                            ok=True, episode_id="ep-7", nodes_written=1,
                            edges_written=0, refused=None, superseded=[],
                            unmatched=[]))
    monkeypatch.setattr("metis_mcp.model_sources.plan_landing",
                        lambda *a, **k: types.SimpleNamespace(
                            is_legal=True, errors=[], nodes=[], edges=[]))

    class _Session:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("metis_mcp.mbt.graph_session.session",
                        lambda *a, **k: _Session())

    model = tiny_model()
    context = Context(workflow="model-build", scope="s", model=model,
                      args=types.SimpleNamespace(journey="j", job_id="x",
                                                 uri="", user="", surface="api"))
    context.source_result = types.SimpleNamespace(model=model)

    status, detail, _, _ = handlers._land(context)

    assert called == ["ep-7"], "the land stage never landed the drafts"
    assert "3 drafted" in detail, (
        "the drafted summary never reached the stage detail, so a run could "
        "land criteria and report nothing about them")


def test_landing_no_drafts_writes_nothing_and_says_nothing(monkeypatch):
    """A model-build with no drafts must not open a session or pad its summary."""
    import types

    from metis_mcp.workflow import handlers

    opened = []
    monkeypatch.setattr("metis_mcp.mbt.graph_session.session",
                        lambda *a, **k: opened.append(1))

    context = Context(workflow="model-build", scope="s", model=tiny_model(),
                      args=types.SimpleNamespace(uri="", user="", surface="api"))
    context.drafts = []
    assert handlers._land_drafts(context, "ep-1") == ""
    assert opened == []


def test_reconcile_reads_criteria_from_the_graph_when_the_context_has_none(
        monkeypatch):
    """Break 2. `_reconcile` looked only at `context.criteria`, which nothing in
    model-build set — so it reported "no acceptance criteria in scope" whatever
    the graph held, and phrased it as a property of the SCOPE."""
    import types

    from metis_mcp.workflow import handlers

    monkeypatch.setattr(handlers, "_criteria_in_scope",
                        lambda ctx: [types.SimpleNamespace(id="AC-1", text="t")])
    monkeypatch.setattr(handlers, "_confirmed_in_scope", lambda ctx: [])
    monkeypatch.setattr("metis_mcp.reconciliation.reconcile",
                        lambda *a, **k: _ReconcileResult())

    context = Context(workflow="model-build", scope="s", model=tiny_model(),
                      args=types.SimpleNamespace(journey="j", uri="", user=""))
    status, detail, _, _ = handlers._reconcile(context)

    assert status == PASSED
    assert "no acceptance criteria in scope" not in detail


def test_reconcile_still_says_so_when_the_graph_has_none_either(monkeypatch):
    """A run that looked and found nothing, and a run that could not look, both
    yield coverage rather than correctness — and neither may claim the
    comparison ran."""
    import types

    from metis_mcp.workflow import handlers

    monkeypatch.setattr(handlers, "_criteria_in_scope", lambda ctx: [])
    context = Context(workflow="model-build", scope="s", model=tiny_model(),
                      args=types.SimpleNamespace(journey="j", uri="", user=""))
    _, detail, _, _ = handlers._reconcile(context)
    assert "no acceptance criteria in scope" in detail


def test_reconcile_loads_the_validates_edges_as_confirmed_matches(monkeypatch):
    """Break 3. `load_confirmed_matches` existed and nothing called it, so a
    criterion already joined to its transition was reported as implementing
    nothing."""
    import types

    from metis_mcp.workflow import handlers

    seen = {}
    monkeypatch.setattr(handlers, "_criteria_in_scope",
                        lambda ctx: [types.SimpleNamespace(id="AC-1", text="t")])
    monkeypatch.setattr(handlers, "_confirmed_in_scope",
                        lambda ctx: ["a-confirmed-match"])

    def fake_reconcile(model, criteria, confirmed):
        seen["confirmed"] = confirmed
        return _ReconcileResult()

    monkeypatch.setattr("metis_mcp.reconciliation.reconcile", fake_reconcile)

    context = Context(workflow="model-build", scope="s", model=tiny_model(),
                      args=types.SimpleNamespace(journey="j", uri="", user=""))
    handlers._reconcile(context)

    assert seen["confirmed"] == ["a-confirmed-match"], (
        "the VALIDATES edges never reached reconcile")


def test_a_context_that_already_carries_criteria_is_not_overridden(monkeypatch):
    """knowledge-capture sets them itself. Reading the graph over the top would
    reconcile against a different set than the workflow assembled."""
    import types

    from metis_mcp.workflow import handlers

    called = []
    monkeypatch.setattr(handlers, "_criteria_in_scope",
                        lambda ctx: called.append(1) or [])
    monkeypatch.setattr(handlers, "_confirmed_in_scope", lambda ctx: [])
    monkeypatch.setattr("metis_mcp.reconciliation.reconcile",
                        lambda *a, **k: _ReconcileResult())

    context = Context(workflow="model-build", scope="s", model=tiny_model(),
                      args=types.SimpleNamespace(journey="j", uri="", user=""))
    context.criteria = [types.SimpleNamespace(id="AC-9", text="mine")]
    handlers._reconcile(context)
    assert called == [], "the graph was read over a context that already had criteria"


def test_neither_loader_needs_a_journey_to_fail_safely():
    """No journey means no scope. `[]` is the same shape as "none landed", which
    is correct: both yield coverage rather than correctness."""
    import types

    from metis_mcp.workflow import handlers

    context = Context(workflow="model-build", scope="s", model=tiny_model(),
                      args=types.SimpleNamespace(journey="", uri="", user=""))
    assert handlers._criteria_in_scope(context) == []
    assert handlers._confirmed_in_scope(context) == []


# --------------------------------------------------------------------------
# The evidence layer's second pass.
#
# **The silent failure this section exists for.** `plan_landing` plans all five
# kinds of evidence edge from a transition's own `evidence` tuple. The model
# plan is landed BEFORE `_land_evidence` creates the nodes two of those kinds
# point at, so those two MERGE against a node that does not exist yet — and
# `land` reports that as `unmatched` rather than failing.
#
# `Endpoint`, `Class` and `ExceptionMapping` survived because two planners
# re-plan them after the evidence layer exists. `DeclaredOutcome` and `Check`
# had no such pass. Measured on a real estate: 0 of 176 transitions carried a
# check, while 47 `Check` nodes and 88 `GUARDED_BY` edges sat in the same graph
# — which left `mbt/dimensions.py` with nothing to build a chain from.
# --------------------------------------------------------------------------

class _Args:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _EvidenceContext:
    def __init__(self, model):
        self.model = model
        self.args = _Args(surface="api", journey="records", job_id="test")


def _model_with_evidence():
    """A one-transition model carrying every kind of evidence a real one does."""
    model = tiny_model()
    model.transitions["t1"] = replace(
        model.transitions["t1"],
        evidence=(("Endpoint", "ep:abc"), ("Class", "cls:abc"),
                  ("DeclaredOutcome", "out:abc"), ("Check", "chk:abc"),
                  ("ExceptionMapping", "exm:abc")))
    return model


def test_the_deferred_evidence_edges_are_planned_after_their_nodes_exist():
    """The fix. Both kinds are read from the transition's own evidence tuple, so
    the ids agree with what `raw_landing` wrote by construction."""
    from metis_mcp.model_sources.landing import LandingPlan
    from metis_mcp.workflow.handlers import _plan_outcome_edges

    plan = LandingPlan(episode_id="ep-test")
    planned = _plan_outcome_edges(plan, _EvidenceContext(_model_with_evidence()),
                                  repo="records")

    assert planned == {"DeclaredOutcome": 1, "Check": 1}, planned
    by_target = {(e.rel_type, e.to_label, e.to_id) for e in plan.edges}
    assert ("DERIVED_FROM", "DeclaredOutcome", "out:abc") in by_target
    assert ("CONSTRAINED_BY", "Check", "chk:abc") in by_target


def test_the_second_pass_does_not_replan_what_the_other_two_already_do():
    """Planning `Endpoint` here as well would write the edge twice under two
    different derivations of its id — the defect `evidence_repo` documents."""
    from metis_mcp.model_sources.landing import LandingPlan
    from metis_mcp.workflow.handlers import _plan_outcome_edges

    plan = LandingPlan(episode_id="ep-test")
    _plan_outcome_edges(plan, _EvidenceContext(_model_with_evidence()),
                        repo="records")
    labels = {e.to_label for e in plan.edges}
    assert labels == {"DeclaredOutcome", "Check"}, (
        f"the second pass planned {sorted(labels)}; `Endpoint`, `Class` and "
        f"`ExceptionMapping` belong to the two planners beside it")


def test_a_transition_with_no_evidence_plans_nothing_rather_than_guessing():
    """An authored model has no code facts behind it. Silence is the correct
    output; an invented outcome id would point the edge at nothing."""
    from metis_mcp.model_sources.landing import LandingPlan
    from metis_mcp.workflow.handlers import _plan_outcome_edges

    plan = LandingPlan(episode_id="ep-test")
    assert _plan_outcome_edges(plan, _EvidenceContext(tiny_model()),
                               repo="records") == {}
    assert plan.edges == []


def test_every_evidence_label_written_by_the_raw_layer_has_a_second_pass():
    """**The guard on the class of bug, not on the one instance.**

    An evidence label whose nodes `raw_landing` creates cannot be landed by the
    model plan, because that plan runs first. Adding a sixth kind to
    `EVIDENCE_RELATIONSHIPS` without adding it to a second pass would repeat
    exactly this failure, and it would repeat it silently — the edge would be
    planned, reported `unmatched`, and nothing would say so.
    """
    from metis_mcp.model_sources.landing import EVIDENCE_RELATIONSHIPS
    from metis_mcp.workflow.handlers import DEFERRED_EVIDENCE_LABELS

    # The three the other two planners already cover, named here so a label
    # moving between passes has to be a deliberate edit.
    covered_elsewhere = {"Endpoint", "Class", "ExceptionMapping"}
    unhandled = (set(EVIDENCE_RELATIONSHIPS)
                 - covered_elsewhere - set(DEFERRED_EVIDENCE_LABELS))
    assert not unhandled, (
        f"these evidence labels are planned by the model plan and by no second "
        f"pass, so they MERGE against nodes that do not exist yet and land as "
        f"`unmatched`: {sorted(unhandled)}")


def test_the_loader_query_walks_the_path_the_second_pass_writes():
    """The two halves of one join, asserted to agree.

    `CHECKS_CYPHER` reaches a check through `DERIVED_FROM -> DeclaredOutcome
    -[:GUARDED_BY]-> Check`. If the edge the second pass writes ever stopped
    being the first hop of that path, the query would return zero rows for every
    transition and nothing would fail.
    """
    from metis_mcp.mbt.graph_loader import CHECKS_CYPHER
    from metis_mcp.model_sources.landing import EVIDENCE_RELATIONSHIPS

    assert EVIDENCE_RELATIONSHIPS["DeclaredOutcome"] == "DERIVED_FROM"
    assert "-[:DERIVED_FROM]->(:DeclaredOutcome)" in CHECKS_CYPHER.replace("\n", "")
    assert "-[:GUARDED_BY]->(c:Check)" in CHECKS_CYPHER.replace("\n", "")
