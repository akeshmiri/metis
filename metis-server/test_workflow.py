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
        "check", "mine", "compare", "land", "model-approval"]


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
