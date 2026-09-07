"""
Skill `knowledge/`, generated from the module docstrings (the placement rule).

**Why this generator exists.** `metis_mcp/` carries 11,768 lines of docstring and
comment — 37% of its non-blank Python, and more than the spec, the whole skill
tree, the academy, the guide, CLAUDE.md and the README combined. That is the real
design knowledge, and it was addressed to a maintainer reading source. An agent
doing model-build loaded ~175 lines and saw none of it.

These assert the two properties that make generation safer than a rewrite: the
docstring stays the source of truth, and the copy cannot drift from it.
"""
from __future__ import annotations

import pathlib

import pytest

from metis_mcp import knowledge_gen
from metis_mcp.agent_generator import read_skills

SKILLS = knowledge_gen.SKILLS


def test_the_tree_is_current():
    """The same contract `docs/guide/` has: a stale copy fails the build."""
    assert knowledge_gen.check() == []


def test_every_skill_has_a_knowledge_index():
    """**Emptiness is a decision and it is recorded.** Ported from Atlas, where
    30 of 30 skills carry an index and several exist only to say why nothing was
    extracted. An absent directory is something a reader has to interpret."""
    for skill in read_skills():
        # `skill.directory`, not `SKILLS / name` — a specialist lives one level
        # deeper while its name stays flat, which is the whole point of the
        # nesting: ownership on disk, peer in discovery.
        index = (skill.directory or SKILLS / skill.name) / "knowledge" / "index.md"
        assert index.exists(), f"{skill.name} has no knowledge index"


def test_an_index_with_no_fragments_says_why():
    """The failure mode is a directory that looks unfinished rather than
    deliberately empty."""
    rendered = knowledge_gen.render_index("some-skill", [])
    assert "that is a decision" in rendered
    assert "SKILL.md" in rendered          # names where the content went instead


def test_a_fragment_names_the_module_it_came_from():
    """A reader who disagrees with a fragment must be able to find the source of
    truth and argue with it there, not edit the copy."""
    for path, content in knowledge_gen.generate().items():
        if path.name == "index.md":
            continue
        assert "metis_mcp/" in content, path
        assert "GENERATED" in content, path


def test_editing_the_docstring_makes_the_check_fail(tmp_path, monkeypatch):
    """**The property the whole design rests on.** If the copy could drift from
    the docstring, this would be duplication with extra steps."""
    fragment = next(p for p in knowledge_gen.generate()
                    if p.name != "index.md")
    original = fragment.read_text()
    try:
        fragment.write_text(original + "\nAn edit nobody made in the source.\n")
        problems = knowledge_gen.check()
        assert any(fragment.name in p for p in problems), problems
    finally:
        fragment.write_text(original)
    assert knowledge_gen.check() == []


def test_authored_shared_knowledge_is_never_reported_as_stale():
    """`shared/knowledge/` is prose somebody wrote and nothing derives. Reporting
    it as stale would invite deleting it — the opposite of the point."""
    shared = sorted((SKILLS / "shared" / "knowledge").glob("*.md"))
    assert shared, "no shared knowledge to protect"
    stale = {p.name for p in knowledge_gen.stale()}
    for path in shared:
        assert path.name not in stale, f"{path.name} reported as generated"


def test_no_fragment_buries_the_skill_it_serves():
    """Module docstrings only. Function docstrings are 7,579 lines and would make
    a `knowledge/` file more expensive than the SKILL.md it was meant to relieve.
    """
    for path, content in knowledge_gen.generate().items():
        lines = len(content.splitlines())
        assert lines < 120, f"{path.name} is {lines} lines — too heavy to cite"


def test_every_generated_fragment_is_reachable_from_its_skill():
    """A generated orphan is worse than a missing file: it is confidently
    current and nothing points at it."""
    for skill in read_skills():
        directory = SKILLS / skill.name / "knowledge"
        if not any(p.name != "index.md" for p in directory.glob("*.md")):
            continue
        body = (SKILLS / skill.name / "SKILL.md").read_text()
        assert "knowledge/index.md" in body, (
            f"{skill.name} generates knowledge no step cites")
