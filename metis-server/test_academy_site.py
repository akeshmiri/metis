"""
The academy as a browsable site (`metis academy`).

**What this defends.** The operator track is written for a reader who does not
code, and it was delivered as markdown in a git repository. The site is the
delivery mechanism; these tests are about it being *correct*, because a
generated page that silently drops a table or emits a dead link is worse than no
page — the reader cannot tell which half they are missing.
"""
from __future__ import annotations

import json
import re

import pytest

from metis_mcp.academy_site import build, check, render_markdown, stale, write
from metis_mcp.model_sources.lessons import read_lessons

ACADEMY = "../docs/academy"


@pytest.fixture(scope="module")
def lessons():
    return read_lessons(ACADEMY)


@pytest.fixture(scope="module")
def pages(lessons):
    return build(lessons)


# ---------------------------------------------------------------------------
# The markdown subset
# ---------------------------------------------------------------------------


def test_every_lesson_renders_without_raising(lessons):
    for lesson in lessons:
        assert render_markdown(lesson["text"]), lesson["path"]


def test_no_markdown_survives_into_the_output(lessons):
    """The failure that is invisible in a byte count.

    A renderer that quietly passes `**bold**` or a `| pipe | table |` through
    produces a page that looks generated and reads as source.
    """
    everything = "".join(render_markdown(l["text"]) for l in lessons)
    # Code blocks are excluded: a fenced shell snippet legitimately begins a
    # line with `# `, and a guard that cannot tell a heading from a comment is
    # one somebody switches off.
    outside_code = re.sub(r"<pre.*?</pre>", "", everything, flags=re.S)
    assert not re.search(r"\*\*[^*<]{1,60}\*\*", outside_code)
    assert not re.search(r"^\| ", outside_code, re.M)
    assert not re.search(r"^#{1,6} ", outside_code, re.M)


def test_the_corpus_still_uses_only_the_subset_that_is_implemented(lessons):
    """**A lesson that grows a nested list must fail here, not render flat.**

    `render_markdown` implements what the academy uses, counted rather than
    guessed. That is a legitimate trade only while the count holds, and the way
    it stops holding is somebody writing perfectly ordinary markdown that this
    silently mangles.
    """
    unsupported = []
    for lesson in lessons:
        for number, line in enumerate(lesson["text"].split("\n"), start=1):
            if re.match(r"^ {2,}[-*+] ", line):
                unsupported.append(f"{lesson['path']}:{number}: nested list")
            if re.match(r"^\s{4,}\S", line) and not line.lstrip().startswith("|"):
                continue        # continuation lines are handled
    assert not unsupported, (
        "the academy now uses markdown `render_markdown` does not implement:\n  "
        + "\n  ".join(unsupported))


def test_a_code_span_is_not_re_scanned_for_emphasis():
    """A guard written verbatim must survive. `*` inside code is an asterisk."""
    out = render_markdown("The guard is `a * b` and **this** is bold.")
    assert "<code>a * b</code>" in out
    assert "<strong>this</strong>" in out


def test_a_code_span_is_not_html_escaped_into_nonsense():
    out = render_markdown("`attempts >= 3`")
    assert "attempts &gt;= 3" in out          # escaped for HTML
    assert "&amp;gt;" not in out              # but not double-escaped


def test_a_table_renders_with_its_header_and_drops_the_rule():
    out = render_markdown("| a | b |\n|---|---|\n| 1 | 2 |")
    assert "<th>a</th>" in out and "<td>1</td>" in out
    assert "---" not in out


def test_wide_content_can_scroll_without_the_page_doing_so(lessons):
    """Tables and code are the two things that overflow a phone."""
    everything = "".join(render_markdown(l["text"]) for l in lessons)
    assert everything.count("<table") == everything.count('class="scroll"><table')
    assert everything.count("<pre") == everything.count('<pre class="scroll"')


# ---------------------------------------------------------------------------
# The site
# ---------------------------------------------------------------------------


def test_every_lesson_gets_a_page_and_the_index_links_all_of_them(lessons, pages):
    for lesson in lessons:
        name = f"{lesson['ordinal']:02d}-{lesson['slug']}.html"
        assert name in pages, f"{lesson['path']} has no page"
        assert f'href="{name}"' in pages["index.html"], (
            f"{name} exists and the index does not link it — a lesson invisible "
            f"from the index is the delivery failure this site exists to fix")


def test_no_internal_link_is_dead(pages):
    """**Eleven of these shipped in the first build.**

    The lessons cross-link with `.md`, because in the repository that resolves.
    On the site every one of them was dead — including every "Next:" in the
    operator track, which is the single path a non-technical reader is told to
    follow end to end.
    """
    dead = []
    for name, body in pages.items():
        # Hrefs built by the search script at runtime are not links in the page.
        without_script = re.sub(r"<script>.*?</script>", "", body, flags=re.S)
        for href in re.findall(r'href="([^"]+)"', without_script):
            target = href.split("#")[0]
            if target and not target.startswith(("http", "mailto")) \
                    and target not in pages:
                dead.append(f"{name} -> {href}")
    assert not dead, "dead internal links:\n  " + "\n  ".join(dead)


def test_the_operator_track_comes_first(pages):
    """A non-technical reader must not have to scroll past two other tracks."""
    index = pages["index.html"]
    assert index.index("Using Métis") < index.index("How it thinks")


def test_the_glossary_and_the_refusals_have_their_own_pages(pages):
    """The two an operator returns to, reachable without knowing a number."""
    assert "glossary.html" in pages
    assert "refusals.html" in pages
    assert "Quarantine" in pages["glossary.html"]
    assert "BLOCKED" in pages["refusals.html"]


def test_every_page_carries_the_generated_notice(pages):
    """It is generated, never authored — the rule `docs/guide/` follows."""
    for name, body in pages.items():
        assert "metis academy" in body, name


# ---------------------------------------------------------------------------
# The search index
# ---------------------------------------------------------------------------


def _index(pages) -> list[dict]:
    script = re.search(r"<script>(.*?)</script>", pages["index.html"], re.S).group(1)
    return json.loads(re.search(r"const IDX = (\[.*?\]);", script, re.S).group(1))


def test_the_search_index_is_valid_json_and_covers_every_lesson(lessons, pages):
    entries = _index(pages)
    assert len(entries) == len(lessons)
    assert all(e["href"] in pages for e in entries)


def test_the_search_index_carries_folded_copies_for_matching(pages):
    """**`Métis` does not contain the substring `metis`.**

    Without folding, a reader typing the name without an accent — which is most
    of them — matched no title at all and every lesson ranked identically.
    `retrieval.fold` is the same normalisation the graph index uses.
    """
    entries = _index(pages)
    for e in entries:
        assert "ftitle" in e and "fbody" in e
        assert e["ftitle"] == e["ftitle"].lower()
    assert any("metis" in e["ftitle"] for e in entries), (
        "no folded title contains the unaccented name")


def test_the_folded_body_is_aligned_with_the_one_that_is_shown(pages):
    """The excerpt is sliced from the original using an offset found in the
    folded copy, so the two must stay the same length. If `fold` ever stops
    preserving length the highlight drifts, which is subtle and wrong."""
    for e in _index(pages):
        assert len(e["fbody"]) == len(e["body"]), e["href"]
        assert len(e["ftitle"]) == len(e["title"]), e["href"]


def test_the_search_body_is_prose_rather_than_markup(pages):
    """A hit reads as a sentence, not as pipes and hashes."""
    for e in _index(pages):
        assert "|" not in e["body"]
        assert "##" not in e["body"]


def test_the_script_contains_no_regexp_built_from_user_input(pages):
    """**This shipped broken once and failed silently.**

    Escaping a search term into a `new RegExp(...)` through a Python string
    literal produced an invalid character class: the script failed at parse and
    the search box did nothing at all, with no error a reader would see.
    Highlighting is done with `indexOf`, which cannot be malformed.
    """
    script = re.search(r"<script>(.*?)</script>", pages["index.html"], re.S).group(1)
    assert "new RegExp" not in script


def test_writing_the_site_produces_the_files_it_returns(tmp_path, lessons):
    written = write(tmp_path, lessons)
    assert written
    for path in written:
        assert path.exists() and path.read_text().startswith("<!doctype html>")


# ---------------------------------------------------------------------------
# The decision records
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def proposals():
    from metis_mcp.academy_site import read_proposals

    return read_proposals(ACADEMY)


def test_every_proposal_gets_a_page_and_the_index_links_it(lessons, proposals):
    """`read_lessons` excludes proposals deliberately — a decision record is not
    material to be taught. Excluding them from the SITE as well left them
    reachable only by browsing the repository, which is the delivery failure
    this site exists to fix, one document type over."""
    assert proposals, "no PROPOSAL-*.md found"
    pages = build(lessons, proposals)
    for proposal in proposals:
        assert proposal["page"] in pages, proposal["slug"]
        assert f'href="{proposal["page"]}"' in pages["index.html"]


def test_a_proposal_title_renders_its_backticks(lessons, proposals):
    """They title themselves with the label they are about. An index showing
    `` `Lesson` `` raw reads as unrendered source."""
    index = build(lessons, proposals)["index.html"]
    assert "<code>Lesson</code>" in index or "<code>Release</code>" in index
    assert "`Lesson`" not in index


def test_a_proposal_tab_title_carries_no_markup(lessons, proposals):
    """`<title>` renders no markup, so a `<code>` tag shows literally."""
    pages = build(lessons, proposals)
    for proposal in proposals:
        title = re.search(r"<title>(.*?)</title>", pages[proposal["page"]]).group(1)
        assert "`" not in title and "<" not in title, title


def test_the_site_still_builds_with_no_proposals(lessons):
    """They are an addition, not a requirement: a corpus with none must render."""
    pages = build(lessons, [])
    assert "index.html" in pages
    assert "Decisions on the record" not in pages["index.html"]


# ---------------------------------------------------------------------------
# The staleness guard
#
# `docs/academy-site/` is deliberately NOT committed (`.gitignore` gives the
# reason: each page inlines a ~90KB search index). So there is no committed copy
# for CI to diff, and the guard is `metis academy --check` against a rendered
# site plus the coverage tests above.
#
# It exists because the real thing happened: a rendered site sat four pages
# behind the lessons and was missing a proposal page entirely, and nothing said
# so -- `metis guide --check` covers `docs/guide/` and had no counterpart here.
# ---------------------------------------------------------------------------


def test_a_freshly_written_site_is_reported_current(tmp_path, lessons, proposals):
    write(tmp_path, lessons, proposals)
    assert check(tmp_path, lessons, proposals) == []


def test_a_missing_page_is_reported(tmp_path, lessons, proposals):
    """The condition that actually occurred: a proposal was added and the
    rendered site predated it, so the page simply was not there."""
    write(tmp_path, lessons, proposals)
    gone = sorted(tmp_path.glob("*.html"))[0]
    gone.unlink()

    problems = check(tmp_path, lessons, proposals)
    assert [p for p in problems if p.startswith(f"{gone.name}: missing")], problems


def test_an_edited_page_is_reported(tmp_path, lessons, proposals):
    """A lesson changing is the ordinary case; the page must stop matching."""
    write(tmp_path, lessons, proposals)
    page = sorted(tmp_path.glob("*.html"))[0]
    page.write_text(page.read_text() + "<p>drifted</p>")

    assert any(p.startswith(f"{page.name}: differs") for p in
               check(tmp_path, lessons, proposals))


def test_a_page_no_lesson_produces_is_reported(tmp_path, lessons, proposals):
    """A renamed lesson leaves its old page behind. A dead generated page is
    worse than a missing one: it is confidently wrong and linked from nothing."""
    write(tmp_path, lessons, proposals)
    orphan = tmp_path / "42-a-lesson-that-was-renamed.html"
    orphan.write_text("<p>the old text</p>")

    assert orphan in stale(tmp_path, lessons, proposals)
    assert any("no lesson or proposal produces this" in p
               for p in check(tmp_path, lessons, proposals))


def test_writing_again_removes_the_page_nothing_produces(tmp_path, lessons, proposals):
    """Pruning is what makes the guard actionable: `metis academy` is the repair
    the failure message names, so it has to actually clear the finding."""
    write(tmp_path, lessons, proposals)
    orphan = tmp_path / "42-a-lesson-that-was-renamed.html"
    orphan.write_text("<p>the old text</p>")

    write(tmp_path, lessons, proposals)

    assert not orphan.exists()
    assert check(tmp_path, lessons, proposals) == []


def test_prune_can_be_declined(tmp_path, lessons, proposals):
    """The escape hatch `stale_agents`' caller has, for the same reason: a
    directory holding something else deliberately."""
    write(tmp_path, lessons, proposals)
    keep = tmp_path / "hand-written.html"
    keep.write_text("<p>mine</p>")

    write(tmp_path, lessons, proposals, prune=False)

    assert keep.exists()


def test_checking_a_directory_that_was_never_rendered_says_so(tmp_path, lessons,
                                                             proposals):
    """Every page missing, rather than a crash or a clean bill of health for an
    empty directory -- the failure mode that would make the guard useless."""
    problems = check(tmp_path / "never-rendered", lessons, proposals)

    assert problems, "an unrendered site must not report as current"
    assert all(p.endswith(": missing") for p in problems), problems
