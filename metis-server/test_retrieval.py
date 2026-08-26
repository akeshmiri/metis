"""
Hybrid retrieval: fusion, and the refusals that keep it honest.

Free to run. Fusion is arithmetic over rankings and the refusals are argument
checks — neither needs a database, and neither needs a model. That is the point
of the split: Neo4j performs both searches, so the only thing Python contributes
is a query vector, and everything around it can be tested without one.
"""
from __future__ import annotations

import pytest

from metis_mcp import retrieval


class _Provider:
    def __init__(self, model="test/model-1", dimensions=4):
        self._model, self._dimensions = model, dimensions

    @property
    def model(self): return self._model

    @property
    def dimensions(self): return self._dimensions

    def embed(self, text): return [0.0] * self._dimensions


# --------------------------------------------------------------------------
# Fusion by rank, not by score
# --------------------------------------------------------------------------

def test_a_document_both_retrievers_found_outranks_one_either_found_alone():
    """The whole reason to fuse. `b` is second in both lists and beats `a`,
    which is first in one and absent from the other."""
    fused = retrieval.reciprocal_rank_fusion(["a", "b"], ["z", "b"])
    assert fused[0] == "b"


def test_scores_are_never_compared_across_retrievers():
    """A Lucene score of 0.5 and a cosine similarity of 0.5 mean nothing to each
    other, so RRF reads POSITION only. Asserted by fusing lists whose scores, if
    they mattered, would invert the answer — there are no scores here at all."""
    first = retrieval.reciprocal_rank_fusion(["x", "y", "z"])
    assert first == ["x", "y", "z"]


def test_fusion_is_total_and_stable():
    """Two documents that fuse to the same score must still come back in the
    same order every run, or a diff of two searches is noise."""
    a = retrieval.reciprocal_rank_fusion(["p", "q"], ["q", "p"])
    b = retrieval.reciprocal_rank_fusion(["p", "q"], ["q", "p"])
    assert a == b == sorted(a)


def test_a_hit_records_which_retrievers_proposed_it():
    """Not decoration: a hit found by both is better evidence than one found by
    either, and a reviewer asking why something ranked where it did needs it."""
    keyword = [{"id": "AC-1", "label": "AcceptanceCriterion", "name": "n", "body": "b"}]
    semantic = [{"id": "AC-1", "label": "AcceptanceCriterion", "name": "n", "body": "b"},
                {"id": "AC-2", "label": "AcceptanceCriterion", "name": "m", "body": "c"}]
    hits = retrieval.fuse(keyword, semantic)
    both = [h for h in hits if h.id == "AC-1"][0]
    only = [h for h in hits if h.id == "AC-2"][0]
    assert set(both.sources) == {"keyword", "semantic"}
    assert only.sources == ("semantic",)
    assert both.rank < only.rank


def test_keyword_only_is_a_complete_answer_not_a_degraded_one():
    """The default deployment has no provider. Fusing one list must return that
    list, not an empty one or a warning."""
    keyword = [{"id": "R-1", "label": "Requirement", "name": "n", "body": "b"}]
    assert [h.id for h in retrieval.fuse(keyword, [])] == ["R-1"]


# --------------------------------------------------------------------------
# The refusals — an embedding is meaningless outside its model
# --------------------------------------------------------------------------

def test_a_model_mismatch_is_refused_rather_than_answered():
    """Query with a different model than wrote the vectors and every result is
    confidently wrong, with no error and no signal. That is the Joern 2.x/4.x
    break (X-3) in a different costume."""
    with pytest.raises(retrieval.RetrievalRefused, match="meaningless across models"):
        retrieval.require_matching_model(_Provider("a/model"), {"b/model"})


def test_a_half_embedded_corpus_is_refused():
    """Two models present means an interrupted re-embedding. Ranking what is
    there would make the rest silently unreachable — a search that cannot see
    half its data is worse than one that says so."""
    with pytest.raises(retrieval.RetrievalRefused, match="more than one model"):
        retrieval.require_matching_model(_Provider("a/model"), {"a/model", "b/model"})


def test_an_unembedded_corpus_is_refused():
    with pytest.raises(retrieval.RetrievalRefused, match="no node carries an embedding"):
        retrieval.require_matching_model(_Provider(), set())


def test_a_matching_model_is_permitted():
    retrieval.require_matching_model(_Provider("a/model"), {"a/model"})


# --------------------------------------------------------------------------
# The dependency posture
# --------------------------------------------------------------------------

def test_no_embedding_provider_is_bundled():
    """`EmbeddingProvider` is a Protocol and stays one. Shipping an
    implementation would mean either a network client and a key, or a local model
    and the hundreds of megabytes it arrives with — and a default install that
    cannot answer without a model is a different product from this one."""
    import inspect

    source = inspect.getsource(retrieval)
    assert "class EmbeddingProvider(Protocol)" in source
    for forbidden in ("import openai", "import torch", "sentence_transformers",
                      "import requests", "import httpx"):
        assert forbidden not in source, f"{forbidden} would change the install"


# --------------------------------------------------------------------------
# Measuring retrieval — pure, so the scoring is testable without a database
#
# Two findings from the academy corpus are why this exists: `Metis` returned
# NOTHING for a corpus about Métis, and a fix that was obviously going to help a
# particular query moved it not at all. Neither was visible without a set of
# questions whose right answers were written down first.
# --------------------------------------------------------------------------

def test_a_correct_first_answer_counts_once_in_both_bands():
    report = retrieval.score({"q": ["right", "other"]}, {"q": "right"})
    assert (report.top1, report.top3, report.absent) == (1, 1, 0)
    assert report.misses == ()


def test_an_absent_answer_is_counted_apart_from_a_bad_rank():
    """Different defects. A wrong order is a scoring problem; a missing answer
    means the document was not retrievable at all — which is what the
    accent-folding bug looked like, and no reranking would have fixed it."""
    report = retrieval.score(
        {"ranked-badly": ["a", "b", "wanted"], "missing": ["a", "b"]},
        {"ranked-badly": "wanted", "missing": "wanted"})
    assert report.top1 == 0
    assert report.top3 == 1, "rank 3 is still within top-3"
    assert report.absent == 1
    assert {m.rank for m in report.misses} == {3, None}


def test_a_miss_reports_what_won_instead():
    """A number alone does not tell you what to fix. What outranked the expected
    answer is the diagnosis — three of the academy's four misses turned out to
    share a shape, and that was only visible from this field."""
    report = retrieval.score({"q": ["wrong", "also-wrong", "right"]}, {"q": "right"})
    assert report.misses[0].got == ("wrong", "also-wrong")
    assert "right" not in report.misses[0].got


def test_the_expected_answer_is_never_listed_as_what_beat_it():
    report = retrieval.score({"q": ["right", "other"]}, {"q": "right"})
    assert not report.misses


def test_a_question_set_needs_an_expected_answer_per_line(tmp_path):
    """The format is deliberately dull, and malformed lines are refused rather
    than skipped: a skipped question is one nobody is measuring and nobody
    knows it."""
    path = tmp_path / "q.tsv"
    path.write_text("a question with no expected id\n")
    with pytest.raises(retrieval.RetrievalRefused, match="expected_id"):
        retrieval.load_questions(path)


def test_comments_and_blank_lines_are_ignored(tmp_path):
    path = tmp_path / "q.tsv"
    path.write_text("# a comment\n\nwhen does it stop\tlesson:05\n")
    assert retrieval.load_questions(path) == {"when does it stop": "lesson:05"}


def test_an_empty_question_set_is_refused(tmp_path):
    """Zero questions would score 0/0 and report success."""
    path = tmp_path / "q.tsv"
    path.write_text("# only comments\n")
    with pytest.raises(retrieval.RetrievalRefused, match="no questions"):
        retrieval.load_questions(path)


def test_the_shipped_question_set_names_lessons_that_exist():
    """The worked example has to stay true, or the first thing a reader runs
    reports a failure that is about this file rather than about retrieval."""
    from pathlib import Path

    from metis_mcp.model_sources.lessons import lesson_id, read_lessons

    academy = Path(__file__).parent.parent / "docs" / "academy"
    questions = retrieval.load_questions(academy / "retrieval-questions.tsv")
    known = {lesson_id(l["path"]) for l in read_lessons(academy)}
    unknown = sorted(set(questions.values()) - known)
    assert not unknown, f"the question set expects lessons that do not exist: {unknown}"
