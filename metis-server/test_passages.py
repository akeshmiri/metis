"""
Chunked retrieval: `Passage`, and the roll-up that hides it (D-2).

**Why the label exists.** A document embedded as one vector answers questions
about its subject and loses questions about its sections. Measured over the
academy's 36 questions, changing only the unit that carries a vector:

    whole-document   26/36 top-1
    per-section      32/36 top-1

and through the shipped commands, fused with keyword, 33/36. The clearest case
is `why is a selector a property and not a node` — a verbatim `##` heading in
lesson 04, which lesson 03 won.

Free to run: `sections_of` is pure and the roll-up takes a stub session.
"""
from __future__ import annotations

from metis_mcp.mbt.graph_loader import roll_up_passages
from metis_mcp.model_sources.lessons import sections_of
from metis_mcp.retrieval import RetrievalRefused, check_vector, load_provider

DOC = """# 4 · Joins that cannot be made yet

A preamble sentence.

## Three outcomes, and the difference matters

Body of the first section.

## Why a selector is a property and not a node

Body of the second section.
"""


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------

def test_text_before_the_first_heading_is_not_lost():
    """Otherwise the title and preamble are unreachable by similarity — and the
    title is often the most answer-shaped sentence in the document."""
    sections = sections_of(DOC)
    assert sections[0][0].startswith("4 ·")
    assert "A preamble sentence." in sections[0][1]


def test_each_heading_becomes_its_own_section():
    headings = [h for h, _ in sections_of(DOC)]
    assert headings[1:] == ["Three outcomes, and the difference matters",
                            "Why a selector is a property and not a node"]


def test_the_heading_stays_inside_the_body():
    """`Why a selector is a property and not a node` is a question and its own
    answer. A vector built from the prose alone loses it."""
    _, body = sections_of(DOC)[2]
    assert body.startswith("## Why a selector is a property")


def test_a_document_with_no_headings_is_one_section():
    assert len(sections_of("# Title\n\nJust prose.\n")) == 1


def test_blank_input_yields_nothing_rather_than_an_empty_section():
    assert sections_of("") == []
    assert sections_of("\n\n   \n") == []


# ---------------------------------------------------------------------------
# The roll-up
# ---------------------------------------------------------------------------

class _StubSession:
    """Answers only `PASSAGE_PARENT_CYPHER`, from a passage -> parent map."""

    def __init__(self, parents: dict[str, str]):
        self.parents = parents
        self.calls = 0

    def run(self, _cypher, params=None, **kw):
        self.calls += 1
        ids = (params or kw).get("ids", [])
        return [{"passage_id": pid, "id": self.parents[pid], "label": "Lesson",
                 "name": f"parent of {pid}", "body": "", "lifecycle_state": "Quarantine"}
                for pid in ids if pid in self.parents]


def _row(identifier, label):
    return {"id": identifier, "label": label, "name": identifier, "body": "",
            "lifecycle_state": "Quarantine"}


def test_a_passage_is_replaced_by_the_document_that_contains_it():
    session = _StubSession({"lesson:04#02": "lesson:04"})
    out = roll_up_passages(session, [_row("lesson:04#02", "Passage")])
    assert [r["id"] for r in out] == ["lesson:04"]
    assert out[0]["label"] == "Lesson"


def test_the_matched_passage_is_carried_so_a_caller_can_say_why():
    session = _StubSession({"lesson:04#02": "lesson:04"})
    out = roll_up_passages(session, [_row("lesson:04#02", "Passage")])
    assert out[0]["matched_passage"] == "lesson:04#02"


def test_rank_order_is_preserved():
    """A lesson whose third section matched at rank 1 IS the rank-1 answer."""
    session = _StubSession({"lesson:04#03": "lesson:04"})
    out = roll_up_passages(session, [_row("lesson:04#03", "Passage"),
                                     _row("lesson:01", "Lesson")])
    assert [r["id"] for r in out] == ["lesson:04", "lesson:01"]


def test_several_sections_of_one_document_collapse_to_its_best_position():
    session = _StubSession({"lesson:04#01": "lesson:04", "lesson:04#05": "lesson:04"})
    out = roll_up_passages(session, [_row("lesson:04#01", "Passage"),
                                     _row("lesson:04#05", "Passage")])
    assert [r["id"] for r in out] == ["lesson:04"], "the same document twice"


def test_a_document_already_present_is_not_duplicated_by_its_own_passage():
    session = _StubSession({"lesson:04#01": "lesson:04"})
    out = roll_up_passages(session, [_row("lesson:04", "Lesson"),
                                     _row("lesson:04#01", "Passage")])
    assert [r["id"] for r in out] == ["lesson:04"]


def test_an_orphan_passage_is_dropped_rather_than_shown_bare():
    """`CONTAINS` is the only edge it has, so a parentless passage is a landing
    defect. The honest place to see it is what landed, not a search result."""
    session = _StubSession({})
    assert roll_up_passages(session, [_row("lesson:04#01", "Passage")]) == []


def test_rows_with_no_passages_do_not_query_at_all():
    session = _StubSession({})
    rows = [_row("lesson:01", "Lesson")]
    assert roll_up_passages(session, rows) == rows
    assert session.calls == 0, "a round trip for nothing"


# ---------------------------------------------------------------------------
# Provider loading and vector hygiene
# ---------------------------------------------------------------------------

def test_a_provider_spec_must_name_a_module_and_an_attribute():
    for bad in ("nocolon", "metis_mcp.retrieval:NoSuchAttr", "no.such.module:X"):
        try:
            load_provider(bad)
        except RetrievalRefused:
            continue
        raise AssertionError(f"{bad!r} was accepted")


def test_something_that_is_not_a_provider_says_which_members_are_missing():
    try:
        load_provider("metis_mcp.retrieval:RRF_K")
    except RetrievalRefused as e:
        assert "model" in str(e) and "dimensions" in str(e) and "embed" in str(e)
    else:
        raise AssertionError("an int was accepted as a provider")


def test_a_non_finite_vector_is_refused_rather_than_stored():
    """A NaN does not error; the node is indexed and never ranks, and the symptom
    is 'semantic search does not seem to help' rather than a failure."""
    try:
        check_vector([float("nan"), 1.0], dimensions=2, what="n1")
    except RetrievalRefused as e:
        assert "non-finite" in str(e)
    else:
        raise AssertionError("a NaN vector was accepted")


def test_the_wrong_width_is_refused_because_the_index_fixes_it():
    try:
        check_vector([1.0, 2.0], dimensions=3, what="n1")
    except RetrievalRefused as e:
        assert "dimensions" in str(e)
    else:
        raise AssertionError("a short vector was accepted")


def test_a_clean_vector_comes_back_as_floats():
    assert check_vector([1, 2, 3], dimensions=3) == [1.0, 2.0, 3.0]
