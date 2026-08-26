"""
The authored documentation must agree with the system it describes.

**Why this is not covered by the checks that already exist.** `docs/guide/` is
generated and `metis guide --check` fails on a diff, so it cannot drift.
`test_guide.py` already asserts every rule id a lesson cites exists in the
specification. Neither notices a lesson that says *sixty-one labels* when there
are sixty-two, and both of those drifted in one session: lesson 02 kept the old
count when `Lesson` was added, and lesson 08 said five searchable labels when a
sixth had just joined the index.

A count in prose is exactly the kind of claim a reader trusts *because* it is
specific, and exactly the kind nothing was checking.

**Scope, and why the specification is excluded.** The spec deliberately carries
historical counts — "the v1 ontology carried ~45 labels", "where it landed:
fifty-six" — which are true statements about the past. Scanning it would force
those sentences to be reworded to satisfy a test, which is the tail wagging the
dog. Its label table is already pinned against the code by
`test_ontology.py::test_specification_document_lists_the_same_labels`.

So this covers the authored material that describes the system as it is **now**:
the academy, the README, and CLAUDE.md.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ACADEMY = REPO / "docs" / "academy"

_UNITS = ("", "-one", "-two", "-three", "-four", "-five", "-six", "-seven",
          "-eight", "-nine")
_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty",
         7: "seventy", 8: "eighty", 9: "ninety"}
_SMALL = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
          7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
          12: "twelve"}


def spelled(n: int) -> str | None:
    """`62` -> `sixty-two`, or None where prose would not spell it.

    Teens and anything past ninety-nine are written as digits, and returning a
    wrong word for them would make the test reject the correct prose — which it
    did: `_TENS[19 // 10]` raised `KeyError: 1` for the nineteen read-only tools.
    """
    if n in _SMALL:
        return _SMALL[n]
    if 20 <= n <= 99:
        return _TENS[n // 10] + _UNITS[n % 10]
    return None


def live_facts() -> dict[str, int]:
    """What the system actually is, read from the system.

    Read rather than restated: a table of expected values in a test file is one
    more place to forget, which is the failure this whole file is about.
    """
    import asyncio

    from metis_mcp import server
    from metis_mcp.ontology.labels import (
        ALLOWED_RELATIONSHIPS,
        LABELS,
        SEARCH_TARGETS,
    )
    from metis_mcp.workflow.stages import WORKFLOWS

    # Importing `sources` is what populates the registry: the `register(...)`
    # calls run at module import, so `registered()` is empty without it.
    from metis_mcp.model_sources import base, sources  # noqa: F401

    return {
        "labels": len(LABELS),
        "relationships": len(ALLOWED_RELATIONSHIPS),
        "searchable labels": len(SEARCH_TARGETS),
        "read-only tools": len(asyncio.run(server.mcp.list_tools())),
        "workflows": len(WORKFLOWS),
        # Both of these drifted unnoticed: the README said four sources when five
        # are registered (`openapi` was simply missing from the sentence), and
        # both root documents claimed seventy-two test files.
        #
        # The parametrised TEST total is deliberately not here. Deriving it means
        # a pytest collection from inside a pytest run, and an approximation --
        # counting `def test_` -- would be a number that agrees with nothing,
        # which is worse than no check. That figure stays unguarded prose.
        "registered sources": len(base.registered()),
        "test files": len(list(HERE.glob("test_*.py"))),
    }


# `<count> <phrase>` — the shape these claims take in prose. Both spellings are
# accepted because the academy writes words and the README writes digits.
#
# Longer phrases win. "six searchable labels" is a claim about SEARCHABLE labels
# and not about the ontology, and a naive scan read it as both — reporting that
# the documentation said six labels when it said sixty-two.
def _claims(text: str, phrase: str, longer: tuple[str, ...] = ()) -> set[str]:
    masked = text
    for other in longer:
        if phrase in other and phrase != other:
            masked = re.sub(re.escape(other), " ", masked, flags=re.IGNORECASE)
    # Commas belong INSIDE the captured token. Without this, "1,657 tests" was
    # read as a claim of `657` — the comma ended the match — so every count above
    # nine hundred and ninety-nine was either invisible or wrong. Nothing had
    # crossed a thousand while the only facts checked were labels and tools, so
    # the bug sat here harmlessly until a count did.
    #
    # A space still bounds the token, so "75 files, 1,657 tests" yields `1,657`
    # and not `files, 1,657`.
    pattern = re.compile(rf"\b([\w,-]+)\s+{re.escape(phrase)}\b", re.IGNORECASE)
    return {m.group(1).lower().replace(",", "") for m in pattern.finditer(masked)}


def _documents() -> list[Path]:
    # QUICKSTART and the changelog describe the surface as it is now, and both
    # drifted while this scanner watched only the academy and the two root
    # documents: QUICKSTART said *seven read-only tools* long after there were
    # nineteen, which is the first thing a new user reads.
    docs = sorted(ACADEMY.glob("*.md"))
    docs += [REPO / "README.md", REPO / "CLAUDE.md",
             REPO / "CHANGELOG.md", REPO / "metis-server" / "QUICKSTART.md"]
    return [d for d in docs if d.exists()]


# Sentences where a number sits next to one of these phrases and is not a count
# of the whole. Keyed by `(document, number, phrase)` rather than by the number
# alone: a blanket exemption for "two" would excuse a genuinely wrong "two
# workflows" somewhere else, which is how an exemption list stops meaning
# anything.
#
# Every entry carries its reason. If one cannot be given, the prose is probably
# wrong rather than the test.
NOT_A_TOTAL = {
    ("README.md", "two", "workflows"):
        "'a request matching two workflows equally' is a pair, not the total",
    ("CLAUDE.md", "45", "labels"):
        "the v1 ontology, named to say it is gone",
    ("docs/academy/01-what-metis-does-not-do.md", "forty-five", "labels"):
        "contrasts deliberately with the v1 ontology",
}


@pytest.mark.parametrize("phrase", sorted(live_facts()))
def test_every_count_the_documentation_states_is_the_real_one(phrase):
    """A number in the prose must be the number in the system.

    Parametrised per fact so a failure names which one drifted rather than
    handing back a wall of text — and so adding a fact to `live_facts` adds a
    test rather than lengthening one.
    """
    facts = live_facts()
    expected = facts[phrase]
    accepted = {str(expected)}
    word = spelled(expected)
    if word:
        accepted.add(word)
    others = tuple(facts)

    wrong = []
    for document in _documents():
        for claim in _claims(document.read_text(), phrase, others):
            key = (str(document.relative_to(REPO)), claim, phrase)
            if claim in accepted or key in NOT_A_TOTAL:
                continue
            # Only judge things that look like counts. "the labels", "these
            # workflows" and similar are prose, not claims.
            if not (claim.isdigit() or claim in _SMALL.values()
                    or re.fullmatch(r"(twenty|thirty|forty|fifty|sixty|seventy|"
                                    r"eighty|ninety)(-\w+)?", claim)):
                continue
            wrong.append(f"{document.relative_to(REPO)}: "
                         f"{claim!r} {phrase} (actual: {expected})")

    assert not wrong, (
        f"documentation states a count the system does not have:\n  "
        + "\n  ".join(sorted(wrong))
        + f"\n\nThe live value is {expected}. Update the prose, or — if the "
        f"number is genuinely not a count of the whole — add it to NOT_A_TOTAL "
        f"with its reason.")


def test_the_guard_can_actually_fail():
    """Guarding the guard.

    A scanner whose pattern silently matches nothing passes forever and proves
    nothing — which is precisely how the counts drifted in the first place.
    """
    facts = live_facts()
    assert facts, "no facts to check"
    assert all(value > 0 for value in facts.values())

    # The pattern must find a real claim in the real academy.
    found = set()
    for document in _documents():
        for phrase in facts:
            found |= _claims(document.read_text(), phrase, tuple(facts))
    assert found, "the claim pattern matched nothing anywhere in the docs"

    # And it must reject a wrong one.
    assert _claims("this system has ninety-nine labels", "labels") == {"ninety-nine"}


def test_the_academy_index_lists_every_lesson():
    """A lesson nobody can reach from the index is a lesson nobody reads, and
    the index is the one part of the academy a reader is guaranteed to see."""
    readme = (ACADEMY / "README.md").read_text()
    missing = [path.name for path in sorted(ACADEMY.glob("[0-9][0-9]-*.md"))
               if path.name not in readme]
    assert not missing, f"lessons absent from the academy index: {missing}"


def test_the_lesson_numbering_has_no_gaps_or_repeats():
    """The index publishes a reading order, and `lessons.py` lands the ordinal
    as a property. A gap or a duplicate makes the two disagree about what comes
    next."""
    ordinals = sorted(int(path.name[:2])
                      for path in ACADEMY.glob("[0-9][0-9]-*.md"))
    assert ordinals == list(range(1, len(ordinals) + 1)), (
        f"lesson ordinals are {ordinals}; expected a contiguous run from 1")


def test_every_lesson_is_landable():
    """The academy is a corpus, not just prose — `metis lessons` reads it and
    `Lesson` nodes are searchable. A lesson the writer refuses is one that
    silently never reaches the graph."""
    from metis_mcp.model_sources.lessons import plan_lessons, read_lessons

    lessons = read_lessons(ACADEMY)
    on_disk = len(list(ACADEMY.glob("[0-9][0-9]-*.md")))
    assert len(lessons) == on_disk, (
        f"{on_disk} lesson file(s) on disk, {len(lessons)} readable")

    plan = plan_lessons(ACADEMY, t_recorded="2026-01-01T00:00:00+00:00")
    assert plan.is_legal, plan.errors[:3]
    assert len(plan.by_label("Lesson")) == on_disk
