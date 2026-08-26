"""
Retrieval misses as findings (`finding_writer.findings_from_retrieval`).

**The loop this closes.** `CLAUDE.md` records the intent that `ask` answer a
question about Métis the way it answers one about a product — and that a lesson
which reads badly through `ask` becomes a finding about the *tools*. The
benchmark measured that from the day the academy landed; nothing recorded it, so
it lived in whoever last ran the command.

Free to run: the conversion is pure, and `plan_findings` builds statements
without a session.
"""
from __future__ import annotations

import pytest

from metis_mcp.mbt.finding_writer import (
    RETRIEVAL_ABSENT,
    RETRIEVAL_RANK,
    findings_from_retrieval,
    plan_findings,
    validate_plan,
)
from metis_mcp.retrieval import BenchmarkReport, Miss

RANKED = Miss(question="when does Metis stop for a human",
              expected="lesson:05-the-two-gates", rank=2,
              got=("lesson:01-what-metis-does-not-do",))
ABSENT = Miss(question="what colour is the graph",
              expected="lesson:02-the-shape-of-the-model", rank=None, got=())


def _report(*misses) -> BenchmarkReport:
    return BenchmarkReport(total=15, top1=10, top3=14,
                           absent=sum(1 for m in misses if m.rank is None),
                           misses=tuple(misses))


def test_a_ranking_miss_and_an_absent_answer_are_different_findings():
    """`retrieval.score` refuses to collapse these into one number, and so does
    this: one is fixed by the analyzer, the other means the node cannot be
    reached at all."""
    records = findings_from_retrieval(_report(RANKED, ABSENT))
    assert {r.finding_type for r in records} == {RETRIEVAL_RANK, RETRIEVAL_ABSENT}


def test_a_finding_is_about_the_node_that_should_have_won():
    """Not about what won instead: the expected node is what a reader looks up."""
    record, = findings_from_retrieval(_report(RANKED))
    assert record.about_id == "lesson:05-the-two-gates"
    assert record.about_label == "Lesson"


def test_the_question_is_carried_so_the_finding_can_be_reproduced():
    record, = findings_from_retrieval(_report(RANKED))
    assert "when does Metis stop for a human" in record.detail
    assert "rank" in record.detail.lower() or "ranks" in record.detail


def test_everything_is_advisory():
    """A ranking miss blocks nothing. Reporting it at a severity that suggests
    otherwise would put it beside a validation failure that stops generation."""
    records = findings_from_retrieval(_report(RANKED, ABSENT))
    assert {r.severity for r in records} == {"advisory"}


def test_the_remedy_never_says_to_write_prose_that_matches_the_query():
    """The one remedy that must not be suggested.

    Editing a lesson to contain the query's words would raise the score and make
    the corpus worse, and the benchmark would then be grading text written to
    satisfy it. The finding says so out loud, because the obvious fix is the
    wrong one.
    """
    record, = findings_from_retrieval(_report(RANKED))
    assert "NOT a reason to edit" in record.remedy
    assert "analyzer" in record.remedy or "embedding" in record.remedy


def test_no_misses_produces_no_findings():
    assert findings_from_retrieval(_report()) == []


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------

def test_an_about_id_is_used_verbatim_and_not_namespaced():
    """A `Lesson` id is already the id it was landed with.

    `plan_load` namespaces `about_id` as `{model_id}::{element_id}` because
    landing rewrites element ids that way. Doing that here would prefix a lesson
    with a model that does not exist, and the `ABOUT` edge would match nothing —
    silently, which is the failure this module's comments were written about.
    """
    plan = plan_findings(findings_from_retrieval(_report(RANKED)))
    about = [p for kind, _, p in plan.statements if kind == "about"]
    assert about and about[0]["about_id"] == "lesson:05-the-two-gates"
    assert "::" not in about[0]["about_id"]


def test_the_plan_passes_the_ontology_gate_it_will_be_loaded_through():
    """`Finding` requires `source_episode_id` and `Episode` requires three more.

    The first version of `plan_findings` set none of them and `load` refused —
    correctly, and only because the gate exists. This is that gate, run early.
    """
    plan = plan_findings(findings_from_retrieval(_report(RANKED, ABSENT)))
    assert validate_plan(plan) == []


def test_the_episode_is_validated_and_not_merely_written():
    """`validate_plan` skips any statement kind absent from `_WRITES_NODE`, so an
    unregistered `episode` kind would be written unchecked."""
    plan = plan_findings(findings_from_retrieval(_report(RANKED)))
    kinds = {kind for kind, _, _ in plan.statements}
    assert "episode" in kinds

    broken = [(k, c, dict(p)) for k, c, p in plan.statements]
    for _kind, _cypher, params in broken:
        params.pop("t_recorded", None)
    plan.statements = broken
    assert validate_plan(plan), "a malformed Episode passed the gate"


def test_the_episode_id_is_content_derived_so_a_repeat_is_a_no_op():
    """D-8. The same misses re-landed are the same episode, not a second record
    of one measurement."""
    first = plan_findings(findings_from_retrieval(_report(RANKED)))
    second = plan_findings(findings_from_retrieval(_report(RANKED)),
                           t_recorded="2020-01-01T00:00:00+00:00")
    ids = [next(p["id"] for k, _, p in plan.statements if k == "episode")
           for plan in (first, second)]
    assert ids[0] == ids[1], "the episode id moved with the clock"


def test_a_different_set_of_misses_is_a_different_episode():
    one = plan_findings(findings_from_retrieval(_report(RANKED)))
    two = plan_findings(findings_from_retrieval(_report(RANKED, ABSENT)))
    ids = [next(p["id"] for k, _, p in plan.statements if k == "episode")
           for plan in (one, two)]
    assert ids[0] != ids[1]


def test_an_empty_report_plans_nothing_at_all():
    """Not even an Episode: a run that found nothing should leave no trace."""
    plan = plan_findings(findings_from_retrieval(_report()))
    assert plan.statements == [] and plan.findings == 0
