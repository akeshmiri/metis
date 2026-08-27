"""
`Topic` — the shared node that stops the academy being eight islands (D-2).

A `Lesson` had edges only to its own sections, so "what else covers this ground"
could only be answered by searching again with different words. A topic is ONE
node many documents point at, so the question becomes a traversal.

**The rule this file mostly exists to hold: a topic is authored, never
inferred.** Deriving one from a title or from the prose would read as somebody's
statement about the material while being Métis's opinion of it — the guess S-13
exists to prevent.

Free to run: parsing and planning are pure.
"""
from __future__ import annotations

from metis_mcp.model_sources.lessons import (
    parse_frontmatter, plan_lessons, topics_of)

WITH = "---\ntopics: practice, gates\n---\n# 5 · Title\n\nBody.\n"
WITHOUT = "# 5 · Title\n\nBody.\n"


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

def test_frontmatter_is_stripped_from_the_text():
    """It is metadata ABOUT the document, not part of it. Left in, `topics:
    practice` would appear in the prose a reader is shown and in the vector that
    ranks it."""
    fields, body = parse_frontmatter(WITH)
    assert fields == {"topics": "practice, gates"}
    assert body.startswith("# 5 · Title")
    assert "topics:" not in body


def test_a_document_without_frontmatter_is_not_an_error():
    """The absence is normal: it means nothing was declared."""
    assert parse_frontmatter(WITHOUT) == ({}, WITHOUT)


def test_an_unterminated_block_is_left_alone_rather_than_swallowing_the_document():
    """Treating the whole file as frontmatter would land an empty lesson, which
    is a silent failure — the node exists and has no content."""
    broken = "---\ntopics: practice\n# 5 · Title\n\nBody.\n"
    fields, body = parse_frontmatter(broken)
    assert fields == {} and body == broken


# ---------------------------------------------------------------------------
# What counts as a declared topic
# ---------------------------------------------------------------------------

def test_topics_are_split_on_commas_or_spaces_and_lowercased():
    assert topics_of({"topics": "Practice, Gates"}) == ["practice", "gates"]
    assert topics_of({"topics": "practice gates"}) == ["practice", "gates"]


def test_the_singular_key_is_accepted():
    """`topic:` and `topics:` are the same declaration; refusing one would be a
    spelling trap with no purpose."""
    assert topics_of({"topic": "practice"}) == ["practice"]


def test_order_is_kept_and_duplicates_collapse():
    assert topics_of({"topics": "b, a, b"}) == ["b", "a"]


def test_no_declaration_means_no_topics_and_nothing_is_inferred():
    """The whole point. A title, a filename and a body are all in scope for
    guessing, and none of them is a statement that the document is about X."""
    assert topics_of({}) == []
    assert topics_of({"topics": ""}) == []
    assert topics_of({"title": "The two gates"}) == [], "a title is not a topic"


# ---------------------------------------------------------------------------
# Landing
# ---------------------------------------------------------------------------

def _plan():
    return plan_lessons("../docs/academy")


def test_documents_declaring_the_same_topic_point_at_ONE_node():
    """Shared is the entire feature: eight lessons, two topics."""
    plan = _plan()
    ids = [n.properties["id"] for n in plan.nodes if n.label == "Topic"]
    assert len(set(ids)) < len(ids), "every lesson minted its own topic node"
    assert set(ids) == {"topic:concepts", "topic:practice"}


def test_every_lesson_gets_an_edge_to_what_it_declared():
    plan = _plan()
    edges = [e for e in plan.edges if e.rel_type == "BELONGS_TO"]
    lessons = [n for n in plan.nodes if n.label == "Lesson"]
    assert len(edges) == len(lessons)
    assert {e.to_label for e in edges} == {"Topic"}


def test_the_plan_passes_the_ontology_gate():
    """`Topic` carries `source_episode_id` like everything else — the first
    version did not, and landing refused it."""
    assert _plan().errors == []


def test_a_topic_node_is_not_a_passage_or_a_lesson():
    """Three labels, three jobs. A Topic with `text` would be a document; a
    Passage pointing at a Topic would make an implementation detail navigable."""
    plan = _plan()
    topics = [n for n in plan.nodes if n.label == "Topic"]
    assert topics and all("text" not in n.properties for n in topics)
    assert not [e for e in plan.edges
                if e.rel_type == "BELONGS_TO" and e.from_label == "Passage"]


# ---------------------------------------------------------------------------
# The `ask` route — the reader that makes any of this reachable
# ---------------------------------------------------------------------------

def test_a_bare_interrogative_does_not_route_to_the_academy():
    """`what is the meaning of this` has no answer anywhere, and an earlier
    version of the word list sent it to the academy because it matched
    `what is`. A word earns its place by being one somebody would use only when
    asking about Métis."""
    from metis_mcp.authoring import _ACADEMY_WORDS

    text = "what is the meaning of this"
    assert not any(w in text for w in _ACADEMY_WORDS)


def test_a_question_about_metis_itself_does_route():
    from metis_mcp.authoring import _ACADEMY_WORDS

    for question in ("when does metis stop for a human",
                     "what is the ontology",
                     "why is everything at quarantine"):
        assert any(w in question for w in _ACADEMY_WORDS), question


def test_a_product_question_is_not_captured_by_the_academy():
    """`call_recipe` is the more specific answer, and the academy route is
    checked last precisely so it cannot take one."""
    from metis_mcp.authoring import _ACADEMY_WORDS

    for question in ("how do I call the login endpoint",
                     "what does the payload look like",
                     "which header carries the token"):
        assert not any(w in question for w in _ACADEMY_WORDS), question
