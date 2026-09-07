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
# **The teens were the hole this guard fell through.** `spelled()` returned None
# for them and the recogniser below listed `_SMALL` plus twenty-and-up, so the
# word "nineteen" was neither an accepted spelling nor recognised as a count at
# all — it fell into the "prose, not a claim" branch and was skipped in silence.
# README, CLAUDE.md and QUICKSTART all said "nineteen read-only tools" while
# there were 28, and this file passed the whole time. A guard with a blind spot
# in the range the number actually occupied is the failure it was written to
# prevent, one level up.
_TEENS = {13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen",
          17: "seventeen", 18: "eighteen", 19: "nineteen"}


def spelled(n: int) -> str | None:
    """`62` -> `sixty-two`, or None where prose would not spell it.

    Anything past ninety-nine is written as digits, and returning a wrong word
    for it would make the test reject correct prose — which it did:
    `_TENS[19 // 10]` raised `KeyError: 1` for the nineteen read-only tools. The
    fix at the time was to return None for the teens, which stopped the crash
    and left the number unguarded; they are spelled here now.
    """
    if n in _SMALL:
        return _SMALL[n]
    if n in _TEENS:
        return _TEENS[n]
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
    from metis_mcp.agent_generator import read_skills
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
        # The README said "the five skills" while the plugin shipped thirteen
        # SKILL.md files. `test_skills.py` guards the count in the three plugin
        # MANIFESTS and nothing watched the prose, so the two guards each
        # covered the half the other did not.
        "skills": len(read_skills()),
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
    # **The plugin READMEs, which nothing watched.** `plugins/metis-mcp/README.md`
    # said "Twelve, all read-only" and hand-listed twelve tools while the server
    # exposed thirty-one. It is the first thing somebody installing the plugin
    # reads, and it sat outside both this scan and `test_skills.py`'s manifest
    # guard — which covers the three `.json` files and no prose.
    docs += sorted((REPO / "plugins").glob("*/README.md"))
    return [d for d in docs if d.exists()]


def _claim_documents() -> list[Path]:
    """Every tracked markdown file — a wider net than the count scanner uses.

    **The two scanners want different scopes, and conflating them broke both.**
    Counts are excluded from the specification on purpose (see this module's
    docstring): it states true things about the past — "the v1 ontology carried
    ~45 labels" — and scanning it for counts would force correct sentences to be
    reworded to satisfy a test.

    A safety claim has no such defence. "Métis never executes anything against
    the System Under Test" is not true-about-the-past, it is an assertion about
    what the system will not do, and `_is_historical` already exempts a sentence
    that marks itself as history. So this one scans everything.

    It had to. `_documents()` returns 24 files and the specification — the
    document CLAUDE.md and the README both call authoritative — was not among
    them, so §5's X-7a paragraph asserted an absolute prohibition that
    `execution.TIERS` lifted, and nothing failed.
    """
    import subprocess

    out = subprocess.run(["git", "ls-files", "-z", "*.md"], cwd=REPO,
                         capture_output=True, text=True, check=True).stdout
    return [REPO / name for name in out.split("\0") if name]


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
    ("CLAUDE.md", "six", "labels"):
        "the execution/operational layer reinstated from STAGED_OUT — a named "
        "subset of the 43, not the total",
    ("docs/academy/02-the-shape-of-the-model.md", "Six", "labels"):
        "the same six, named in the lesson that lists the layers",
    ("docs/academy/PROPOSAL-requirement-hierarchy.md", "three", "labels"):
        "the three labels the proposal ASKS for and recommends refusing "
        "(Epic, Goal, Capability) — a request, not the catalogue",
    ("docs/academy/11-which-skill-and-why.md", "two", "workflows"):
        "'two workflows scoring equally' is a tie, not the total",
    ("docs/academy/11-which-skill-and-why.md", "three", "skills"):
        "the three skills the word 'coverage' appears in — a figure, an "
        "adequacy judgement, a readiness call — named as a subset. The same "
        "lesson states the real total, thirteen, twice",
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
                    or claim in _TEENS.values()
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


def test_a_teen_count_is_recognised_and_spelled():
    """The specific hole: 13-19 were neither spellable nor recognisable.

    Without this, a documentation count anywhere in the teens is unguarded and
    the suite still passes — which is exactly what happened.
    """
    for n, word in _TEENS.items():
        assert spelled(n) == word, f"spelled({n}) must be {word!r}"
        assert word in _TEENS.values()
    assert _claims("the surface is nineteen read-only tools",
                   "read-only tools") == {"nineteen"}


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


# ---------------------------------------------------------------------------
# Claims, not only counts
# ---------------------------------------------------------------------------
#
# The count scanner above catches "sixty-one labels" when there are sixty-two.
# It cannot catch a sentence with no number in it, and the three most damaging
# pieces of stale prose in this repository had none:
#
#   "`DryRunTransport` is the only registered transport"
#       -- false once `zephyr-scale` landed. Wrong in the DANGEROUS direction:
#          it tells a reader Métis cannot write to their tracker when it can.
#   "No execution result is ingested, so none can be reported"
#       -- false once `execution_intake` landed six labels.
#   "Métis never touches the system under test"
#       -- false once METIS_EXECUTE became a tier with `observe` and `run`.
#
# All three were safety claims in the academy, which is the document a reader
# trusts most about what this system will not do. So each is paired here with a
# predicate that reads the live system: if the phrase is present and the
# predicate says it is false, the test fails and names the file.
#
# The phrases are deliberately narrow. A broad pattern would fire on a sentence
# explaining the history -- lesson 01 now describes what the old claim was --
# and a guard that cannot distinguish a claim from its own correction is one
# somebody switches off.


def _no_live_transport() -> bool:
    from metis_mcp.publishing import live_transports

    return not live_transports()


def _no_execution_labels() -> bool:
    from metis_mcp.ontology.labels import LABELS

    return not ({"TestExecution", "TestCycle", "Defect"} & set(LABELS))


def _no_sut_contact() -> bool:
    """True only if contact with the system under test is impossible at all tiers."""
    from metis_mcp import execution

    return set(getattr(execution, "TIERS", ())) <= {"off"}


def _claim_sources() -> list[tuple[str, str]]:
    """`(where, text)` for every place a safety claim can hide.

    **Markdown was not all of them, and the gap was not theoretical.** Four
    module docstrings carried claims this scanner exists to catch, every one
    found by reading rather than by a test:

        publish.py            "dry-run only in the first release"
        policy.py             the G2 text `describe_policy` returns
        sql_analysis.py       "Metis ingests no execution result"
        server.py             "no execution result is read, because none is
                              ingested" — in the docstring of the very tool a
                              reader asks for a readiness figure

    A docstring is not a comment: `describe_policy` and the MCP surface return
    theirs to callers, so a stale one is served as an answer.

    **Parsed, never imported**, the same discipline `knowledge_gen` uses and for
    the same reason: importing the package would need a configured graph and
    would drag write paths into a process that only wanted to read prose.

    Scoped to the CLAIMS scanner and never to the count scanner. Code comments
    legitimately carry historical counts — the specification is excluded from
    counts for exactly that reason — and forcing them to track the live value
    would break correct prose.
    """
    import ast
    import subprocess

    out: list[tuple[str, str]] = []
    for document in _claim_documents():
        out.append((str(document.relative_to(REPO)), document.read_text()))

    listed = subprocess.run(["git", "ls-files", "-z", "*.py"], cwd=REPO,
                            capture_output=True, text=True, check=True).stdout
    for name in (n for n in listed.split("\0") if n):
        path = REPO / name
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, OSError):
            continue          # not this guard's business to report
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef,
                                     ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            doc = ast.get_docstring(node)
            if doc:
                where = getattr(node, "name", "<module>")
                out.append((f"{name}:{where}", doc))
    return out


# (phrase, predicate, what to say when the predicate disagrees)
CLAIMS = (
    (r"(only|sole) (registered )?`?Transport`?\b"
     r"|only transport registered"
     r"|publication is dry-run only"
     r"|dry-run is the only",
     _no_live_transport,
     "a live transport is registered — see publishing.TRANSPORTS"),
    (r"no execution result is ingested", _no_execution_labels,
     "execution_intake lands TestExecution/TestCycle/Defect"),
    (r"never (touch\w*|execut\w*( anything)?|call\w*|run\w*)"
     r"( against| on)? the system under test",
     _no_sut_contact,
     "METIS_EXECUTE has tiers beyond `off` — see execution.TIERS"),
)


@pytest.mark.parametrize("phrase,predicate,contradiction", CLAIMS,
                         ids=[c[0][:34] for c in CLAIMS])
def test_no_document_makes_a_claim_the_system_contradicts(phrase, predicate,
                                                          contradiction):
    """A safety claim in prose must still be true of the code.

    Scoped to the sentence, not the paragraph: a document may explain that a
    claim USED to hold, and several now do.
    """
    if predicate():
        return  # the claim is still true; nothing to check

    pattern = re.compile(phrase, re.I)
    guilty = []
    for where, text in _claim_sources():
        for line in text.splitlines():
            if pattern.search(line) and not _is_historical(line):
                guilty.append(f"{where}: {line.strip()[:100]}")

    assert not guilty, (
        f"documentation states a claim the system contradicts "
        f"({contradiction}):\n  " + "\n  ".join(guilty))


# Words that mark a sentence as describing the past rather than asserting the
# present. Kept short and explicit: a permissive list would excuse the very
# sentences this guard exists to find.
_PAST = ("used to", "no longer", "stopped being", "was true", "until",
         "for as long as", "said it did not", "asserted")


def _is_historical(line: str) -> bool:
    return any(marker in line.lower() for marker in _PAST)


def test_the_claim_guard_can_actually_fail():
    """Guarding the guard: at least one predicate must currently be FALSE.

    If every predicate returned True the parametrised test would pass by
    returning early, forever, and prove nothing. Today all three claims are
    contradicted by the system, which is why they had to be rewritten.
    """
    contradicted = [p.__name__ for _, p, _ in CLAIMS if not p()]
    assert contradicted, (
        "every claim predicate is satisfied, so the guard above short-circuits. "
        "That is legitimate only if the system genuinely went back to having no "
        "live transport, no execution ingest and no SUT contact — verify that "
        "before deleting this test.")


# ---------------------------------------------------------------------------
# The retrieval benchmark's answers must name real lessons
# ---------------------------------------------------------------------------
#
# `retrieval-bench` needs a live graph, so nothing in this suite runs it. What
# CAN be checked without one is that its expected answers exist — and that is
# the failure worth catching, because a question whose expected id names no
# lesson can never be answered correctly and drags the score down for a reason
# that has nothing to do with retrieval.
#
# It is also the failure this repository keeps finding in other forms: a check
# whose target does not exist reports a number that means nothing.

QUESTIONS = ACADEMY / "retrieval-questions.tsv"


# ---------------------------------------------------------------------------
# Transcripts, which claim to be real output
# ---------------------------------------------------------------------------
#
# Lesson 15 opens by promising "the outputs are what the commands actually
# print, not an illustration", and then showed `jira: 2 item(s)` for a fixture
# that had grown to three -- a DEMO-100 Epic was added and lists FIRST, so the
# very next line was wrong too.
#
# That is worse than an ordinary stale sentence, because the lesson's authority
# rests on the claim that it was not written by hand. And unlike most academy
# prose it is mechanically checkable: the fixture is in the repository.
#
# Deliberately narrow. It checks the item COUNT and the keys, not the whole
# block: asserting on formatting would fail every time a column widened and
# would be switched off within a month.

TRACKER_FIXTURE = REPO / "metis-server" / "demo_project" / "trackers" / "jira.tracker.json"
_ITEM_COUNT = re.compile(r"^(\w+): (\d+) item\(s\)", re.M)


def test_a_transcript_naming_an_item_count_matches_the_fixture():
    """`jira: N item(s)` in the academy must be the N the fixture holds."""
    import json

    if not TRACKER_FIXTURE.exists():           # fixture moved; nothing to check
        return
    real = len(json.loads(TRACKER_FIXTURE.read_text())["items"])

    wrong = []
    for document in sorted(ACADEMY.glob("*.md")):
        text = document.read_text()
        for match in _ITEM_COUNT.finditer(text):
            if int(match.group(2)) != real:
                wrong.append(f"{document.relative_to(REPO)}: {match.group(0)!r} "
                             f"but the fixture holds {real}")
    assert not wrong, (
        "a transcript states an item count the demo fixture contradicts:\n  "
        + "\n  ".join(wrong))


def test_a_transcript_showing_tracker_keys_shows_all_of_them():
    """A lesson that lists the fixture's items must not omit one.

    The count check above would have passed a transcript that said `3 item(s)`
    and then listed two, which is the shape the drift actually took: the header
    and the body disagreed with the fixture independently.
    """
    import json

    if not TRACKER_FIXTURE.exists():
        return
    keys = {i["key"] for i in json.loads(TRACKER_FIXTURE.read_text())["items"]}

    missing = []
    for document in sorted(ACADEMY.glob("*.md")):
        text = document.read_text()
        if not _ITEM_COUNT.search(text):       # no transcript of this shape
            continue
        absent = sorted(k for k in keys if k not in text)
        if absent:
            missing.append(f"{document.relative_to(REPO)}: never mentions "
                           f"{', '.join(absent)}")
    assert not missing, (
        "a lesson transcribes the demo tracker but omits an item:\n  "
        + "\n  ".join(missing))


def _benchmark_rows() -> list[tuple[str, str]]:
    rows = []
    for line in QUESTIONS.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        question, _, expected = line.partition("\t")
        rows.append((question.strip(), expected.strip()))
    return rows


def test_every_benchmark_answer_names_a_lesson_that_exists():
    from metis_mcp.model_sources.lessons import lesson_id

    on_disk = {lesson_id(path.name)
               for path in ACADEMY.glob("[0-9][0-9]-*.md")}
    rows = _benchmark_rows()
    assert rows, "the benchmark is empty; this test proves nothing"

    unknown = sorted({expected for _, expected in rows if expected not in on_disk})
    assert not unknown, (
        f"the benchmark expects lessons that do not exist: {unknown}. A question "
        f"whose answer names no node can never be answered correctly, so it "
        f"lowers the score for a reason unrelated to retrieval.")


def test_the_benchmark_covers_every_lesson():
    """A lesson no question points at is a lesson whose findability is unmeasured.

    Not a formality: the operator track exists because the concepts track was
    unreadable for the audience it was meant to serve, and "unreadable" is
    exactly what a retrieval miss reports. Landing a track and measuring none of
    it would repeat the mistake one level up.
    """
    from metis_mcp.model_sources.lessons import lesson_id

    expected = {answer for _, answer in _benchmark_rows()}
    unmeasured = sorted(lesson_id(path.name)
                        for path in ACADEMY.glob("[0-9][0-9]-*.md")
                        if lesson_id(path.name) not in expected)
    assert not unmeasured, (
        f"no benchmark question expects these lessons: {unmeasured}. Add one "
        f"per lesson, written from the content BEFORE running the search — a "
        f"question written after seeing what search returns measures nothing.")


def test_no_two_questions_are_the_same():
    """A duplicate question weights one lesson twice and reads as a bigger corpus."""
    questions = [q for q, _ in _benchmark_rows()]
    duplicates = sorted({q for q in questions if questions.count(q) > 1})
    assert not duplicates, f"duplicated benchmark questions: {duplicates}"


# --------------------------------------------------------------------------
# The specification's diagrams.
#
# The spec's own diagram convention says every diagram is derived from
# something checkable and says which. That is a promise, and an unchecked
# promise about a document is exactly what `docs/academy/10-where-a-thing-belongs.md`
# says rots: the hand-maintained indexes drifted and the generated ones did not.
# --------------------------------------------------------------------------

SPEC = HERE.parent / "docs" / "metis-application-spec.md"

#: `A -->|REL| B`, where A and B are node IDS. A mermaid id is not its label —
#: `IN["Intent"]` declares id `IN` for label `Intent` — so the ids are resolved
#: through the declarations in the same block before anything is looked up. The
#: first version of this check compared the ids themselves, found no ontology
#: label among them, and reported that it was checking nothing. It was right.
_EDGE = re.compile(
    r'^\s*(?P<from>\w+)[^-|]*?\s*-\.?->\s*\|(?P<rel>[A-Z_]+)\|\s*'
    r'(?P<to>\w+)')

#: `ID["Label"]`, `ID{"Label"}` or `ID(["Label"])` anywhere in a block.
_DECL = re.compile(r'\b(?P<id>\w+)(?:\["|\{"|\(\[")(?P<label>[^"]*)"')


def _mermaid_blocks(text: str) -> list[str]:
    blocks, current = [], None
    for line in text.splitlines():
        if line.strip() == "```mermaid":
            current = []
            continue
        if current is not None and line.strip() == "```":
            blocks.append("\n".join(current))
            current = None
            continue
        if current is not None:
            current.append(line)
    return blocks


def test_the_specification_has_diagrams_to_check():
    """The guard on the guard below, which passes over a document with none."""
    assert _mermaid_blocks(SPEC.read_text()), "no mermaid diagram in the spec"


def test_every_labelled_edge_in_a_spec_diagram_is_a_real_relationship():
    """**A diagram that is nobody's output is prose with boxes.**

    Every `A -->|REL| B` drawn between two ontology labels must be an edge the
    ontology actually permits. Written after one of these diagrams claimed
    `Specification -[:IMPLEMENTS]-> ApiCall`, which is backwards: an `Endpoint`
    implements a `Specification`, and the direction is the whole of §4.1's
    comparison.
    """
    from metis_mcp.ontology.labels import LABELS, is_allowed

    offenders, checked = [], 0
    for block in _mermaid_blocks(SPEC.read_text()):
        # A node's label, by its id. A label carrying a `<br/>` is a display
        # string rather than one label name, so only its first line is taken.
        declared = {m.group("id"): m.group("label").split("<br/>")[0].strip()
                    for m in _DECL.finditer(block)}
        for line in block.splitlines():
            match = _EDGE.match(line)
            if not match:
                continue
            source = declared.get(match.group("from"), match.group("from"))
            target = declared.get(match.group("to"), match.group("to"))
            rel = match.group("rel")
            # Boxes that are not ontology labels are ordinary flow steps
            # ("fetch", "validate"), and this check has nothing to say about them.
            if source not in LABELS or target not in LABELS:
                continue
            checked += 1
            if not is_allowed(source, rel, target):
                offenders.append(f"{source} -[:{rel}]-> {target}")

    assert checked, (
        "no diagram edge joined two ontology labels — either the data-model "
        "diagram went away or the node ids stopped being label names, and "
        "either way this check is no longer checking anything")
    assert not offenders, (
        "these spec diagrams draw relationships the ontology does not allow: "
        + ", ".join(sorted(offenders)))


def test_every_new_section_of_the_spec_is_in_its_own_index():
    """The index at the top is hand-written, and a section missing from it is a
    section nobody finds. The two lists have to agree."""
    text = SPEC.read_text()
    numbered = {int(m) for m in re.findall(r"^## (\d+)\. ", text, re.M)}
    indexed = {int(m) for m in re.findall(r"^\| \*\*(\d+)\*\* \|", text, re.M)}
    assert numbered, "no numbered sections found"
    assert not (numbered - indexed), (
        f"sections not in the index: {sorted(numbered - indexed)}")
    assert not (indexed - numbered), (
        f"the index names sections that do not exist: {sorted(indexed - numbered)}")


# --------------------------------------------------------------------------
# Diagram structure, everywhere — not only in the spec.
#
# These were checked by hand each time one was added, which is exactly the
# arrangement this file exists to replace: a check somebody remembers to run is
# a check that stops being run.
# --------------------------------------------------------------------------

DOCS = HERE.parent / "docs"

#: Diagram types this repository draws. Closed on purpose, in `STAGED_OUT`'s
#: idiom: a typo (`flowhart`) renders as an error box in every viewer and as
#: nothing at all in a plain-text read, so it must fail here instead.
_DIAGRAM_TYPES = ("flowchart", "graph", "stateDiagram-v2", "sequenceDiagram",
                  "erDiagram", "classDiagram")


def _documents_with_diagrams():
    for path in sorted(DOCS.rglob("*.md")):
        if "academy-site" in path.parts:      # generated; its source is checked
            continue
        blocks = _mermaid_blocks(path.read_text())
        if blocks:
            yield path, blocks


def test_there_are_diagrams_across_the_documentation():
    found = list(_documents_with_diagrams())
    assert found, "no mermaid diagram anywhere under docs/"
    assert len(found) > 1, (
        "every diagram is in one file — this scan would not notice the academy "
        "growing one that does not parse")


def test_every_diagram_declares_a_type_this_repository_draws():
    offenders = []
    for path, blocks in _documents_with_diagrams():
        for index, block in enumerate(blocks, 1):
            first = next((line.strip() for line in block.splitlines()
                          if line.strip()), "")
            kind = first.split()[0] if first else ""
            if kind not in _DIAGRAM_TYPES:
                offenders.append(
                    f"{path.relative_to(DOCS.parent)} #{index}: {kind!r}")
    assert not offenders, (
        "a mermaid block with an unknown type renders as an error box in a "
        "viewer and as nothing in a plain-text read: " + ", ".join(offenders))


def test_every_diagram_is_structurally_balanced():
    """Brackets, quotes and `subgraph`/`end`.

    Not a parser — a real one would need the mermaid toolchain, which is a
    network dependency this suite does not take. What it catches is the class of
    breakage that actually happens when a diagram is edited by hand: a label
    missing its closing quote, a `subgraph` with no `end`.
    """
    offenders = []
    for path, blocks in _documents_with_diagrams():
        for index, block in enumerate(blocks, 1):
            body = block
            where = f"{path.relative_to(DOCS.parent)} #{index}"
            if body.count('"') % 2:
                offenders.append(f"{where}: odd number of quotes")
            for opener, closer in (("[", "]"), ("{", "}"), ("(", ")")):
                if body.count(opener) != body.count(closer):
                    offenders.append(
                        f"{where}: unbalanced {opener}{closer} "
                        f"({body.count(opener)}/{body.count(closer)})")
            opened = len(re.findall(r"^\s*subgraph\b", body, re.M))
            closed = len(re.findall(r"^\s*end\s*$", body, re.M))
            if opened != closed:
                offenders.append(f"{where}: {opened} subgraph, {closed} end")
    assert not offenders, "malformed diagrams: " + "; ".join(offenders)


def test_the_balance_check_would_catch_a_broken_diagram():
    """The sabotage check. Every assertion above passes over healthy documents,
    and a guard that has only ever passed is one nobody has seen work."""
    broken = ['flowchart LR', '  A["unclosed --> B']
    body = "\n".join(broken)
    assert body.count('"') % 2, "the scan would not notice an unclosed label"
    assert body.count("[") != body.count("]"), "nor an unbalanced bracket"
