"""
The academy as a browsable site — the delivery half of a corpus that reads well.

**The gap this closes.** `docs/academy/` is seventeen authored lessons and the
operator track (12-17) is written for a business analyst, a product owner or a
QA lead who does not read code. It was delivered as markdown files in a git
repository, which is not a delivery mechanism for that reader however good the
writing is. The other route in — `ask` over the landed corpus — returns the
right lesson first for about four questions in ten, and both obvious levers were
measured and moved it by roughly one (see `retrieval.search_text_for`).

So: a static site. An index that shows the two tracks, one page per lesson, a
search box, and the two reference pages an operator actually returns to — the
glossary and the refusal list. Nothing here is authored; every word comes from
the lessons, which stay the source of truth.

**No dependency, and a deliberately small markdown subset.** Métis has four
runtime dependencies and a markdown library would be a fifth, paid for by
everyone who never renders the academy. `render_markdown` implements exactly
what the corpus uses, counted rather than guessed: headings, paragraphs, tables
(116 rows — the academy leans on them), fenced code, blockquotes, unordered and
ordered lists, rules, links, and inline code/bold/italic. **No nested lists**,
because the corpus has none; `test_academy_site.py` asserts that, so a lesson
that grows one fails a test rather than rendering as flat text.

**The site is generated, never authored** — the same rule `docs/guide/` follows.
Editing a page here is meaningless: the next run overwrites it.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")

# A lesson linking to a sibling writes the markdown filename, because in the
# repository that is what resolves. On the site it is a dead link, and there
# were ELEVEN of them -- including every "Next:" in the operator track, which is
# the one path a non-technical reader is told to follow end to end.
_LESSON_HREF = re.compile(r"^(\d{2}-[a-z0-9-]+)\.md(#.*)?$")


def _href(target: str) -> str:
    """A markdown link rewritten for the site, or left exactly as it was."""
    match = _LESSON_HREF.match(target)
    return f"{match.group(1)}.html{match.group(2) or ''}" if match else target


def _aligned_fold(text: str) -> str:
    """A lowercased, accent-folded copy the SAME LENGTH as its original.

    **Why not `retrieval.fold` directly, which is the normalisation everything
    else uses.** The search finds an offset in the folded body and slices the
    excerpt out of the original, so the two must agree character for character.
    `fold` does not: `…` becomes `...`, one character into three, and a lesson
    with three ellipses drifts its own excerpts by six. The test that caught it
    asserts the lengths are equal, which is the property actually relied on.

    So this folds per character and keeps the fold only where it is 1→1 —
    every accent, which is the whole point — and leaves anything that would
    change length alone. Nobody searches for an ellipsis.
    """
    from metis_mcp.retrieval import fold

    return "".join(
        folded if len(folded := fold(character)) == 1 else character
        for character in text).lower()


def _inline(text: str) -> str:
    """Inline markup, escaped first so a lesson cannot inject markup.

    Code spans are extracted BEFORE escaping and reinserted after, because a
    guard written verbatim in a lesson — `attempts >= 3` — must render as
    itself rather than as `&gt;=`, and must not then be re-scanned for emphasis:
    `*` inside a code span is an asterisk.
    """
    spans: list[str] = []

    def stash(match):
        spans.append(match.group(1))
        return f"\x00{len(spans) - 1}\x00"

    text = _INLINE_CODE.sub(stash, text)
    text = html.escape(text)
    text = _LINK.sub(lambda m: f'<a href="{html.escape(_href(m.group(2)), quote=True)}">'
                               f"{m.group(1)}</a>", text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    for index, span in enumerate(spans):
        text = text.replace(f"\x00{index}\x00",
                            f"<code>{html.escape(span)}</code>")
    return text


def _table(rows: list[str]) -> str:
    """A GitHub pipe table. The second row is the alignment rule and is dropped."""
    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    head = cells(rows[0])
    body = [cells(r) for r in rows[2:]]
    thead = "".join(f"<th>{_inline(c)}</th>" for c in head)
    tbody = "".join(
        "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
        for r in body)
    return (f'<div class="scroll"><table><thead><tr>{thead}</tr></thead>'
            f"<tbody>{tbody}</tbody></table></div>")


def render_markdown(source: str) -> str:
    """The subset the academy uses. See the module docstring for why it is a subset."""
    out: list[str] = []
    lines = source.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            i += 1
            block = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            out.append(f'<pre class="scroll"><code>'
                       f"{html.escape(chr(10).join(block))}</code></pre>")
            continue

        if not line.strip():
            i += 1
            continue

        if line.strip() in ("---", "***", "___"):
            out.append("<hr>")
            i += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            text = _inline(heading.group(2))
            # Anchors on h2 so the in-page contents can link to sections.
            slug = re.sub(r"[^a-z0-9]+", "-",
                          heading.group(2).lower()).strip("-")
            out.append(f'<h{level} id="{slug}">{text}</h{level}>')
            i += 1
            continue

        if line.startswith("|"):
            table = []
            while i < len(lines) and lines[i].startswith("|"):
                table.append(lines[i])
                i += 1
            out.append(_table(table) if len(table) >= 2
                       else f"<p>{_inline(table[0])}</p>")
            continue

        if line.startswith("> "):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip(">").strip())
                i += 1
            out.append(f"<blockquote>{_inline(' '.join(quote))}</blockquote>")
            continue

        bullet = re.match(r"^([-*])\s+(.*)$", line)
        ordered = re.match(r"^(\d+)\.\s+(.*)$", line)
        if bullet or ordered:
            tag = "ul" if bullet else "ol"
            pattern = r"^([-*])\s+(.*)$" if bullet else r"^(\d+)\.\s+(.*)$"
            items = []
            while i < len(lines):
                match = re.match(pattern, lines[i])
                if match:
                    items.append(match.group(2))
                    i += 1
                # A continuation line is indented and belongs to the item above.
                elif lines[i].startswith("  ") and lines[i].strip() and items:
                    items[-1] += " " + lines[i].strip()
                    i += 1
                else:
                    break
            body = "".join(f"<li>{_inline(t)}</li>" for t in items)
            out.append(f"<{tag}>{body}</{tag}>")
            continue

        paragraph = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{1,6} |\||> |```|[-*] |\d+\. |---$)", lines[i]):
            paragraph.append(lines[i])
            i += 1
        out.append(f"<p>{_inline(' '.join(paragraph))}</p>")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# The site
# ---------------------------------------------------------------------------
#
# Two tracks, taken from the lessons' own `topics:` frontmatter rather than from
# a list here -- the same rule `lessons.topics_of` follows, and for the same
# reason: a title is not a topic and neither is a guess. A lesson declaring a
# topic this file has never heard of appears under it without an edit.

# Which track a topic belongs to, and what to call it. Ordered, because the
# operator track is the one a non-technical reader needs first and burying it
# under "concepts" would repeat the delivery failure this page exists to fix.
TRACKS = (
    ("operator", "Using Métis",
     "For a business analyst, product owner, QA lead or reviewer. "
     "Assumes no programming. Start at the top."),
    ("concepts", "How it thinks, and why",
     "For somebody extending Métis or deciding whether to trust it."),
    ("practice", "Adding to Métis",
     "For somebody writing a tool, a skill or an agent here."),
)

_CSS = """
:root {
  --ground:#eef1f5; --card:#fff; --ink:#181b23; --ink2:#4c5464; --ink3:#6f7788;
  --rule:#d3d9e2; --accent:#2b5c8f; --code:#f2f5f8;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root { --ground:#0f1117; --card:#171a22; --ink:#e5e8ee; --ink2:#a3aaba;
          --ink3:#7d8496; --rule:#2c313d; --accent:#7fa8d6; --code:#1c202a; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--ground); color:var(--ink);
       font:16px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif; }
.wrap { max-width:52rem; margin:0 auto; padding:2rem 1.25rem 5rem; }
a { color:var(--accent); }
h1 { font-size:1.9rem; line-height:1.2; margin:0 0 .4rem; text-wrap:balance; }
h2 { font-size:1.25rem; margin:2.2rem 0 .6rem; text-wrap:balance; }
h3 { font-size:1.05rem; margin:1.6rem 0 .4rem; }
p, ul, ol, blockquote { margin:0 0 1rem; }
li { margin-bottom:.35rem; }
code { background:var(--code); border:1px solid var(--rule); border-radius:3px;
       padding:.05em .3em; font-size:.87em;
       font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
pre { background:var(--code); border:1px solid var(--rule); border-radius:6px;
      padding:.9rem 1rem; }
pre code { background:none; border:none; padding:0; font-size:.82rem; }
blockquote { border-left:3px solid var(--accent); padding-left:1rem;
             color:var(--ink2); font-style:italic; }
table { border-collapse:collapse; width:100%; font-size:.92rem; }
th,td { text-align:left; padding:.5rem .7rem; border-bottom:1px solid var(--rule);
        vertical-align:top; }
th { color:var(--ink3); font-size:.78rem; text-transform:uppercase;
     letter-spacing:.06em; }
.scroll { overflow-x:auto; margin:0 0 1rem; }
hr { border:none; border-top:1px solid var(--rule); margin:2rem 0; }
nav.top { display:flex; gap:1rem; font-size:.86rem; margin-bottom:2rem;
          padding-bottom:.8rem; border-bottom:1px solid var(--rule);
          flex-wrap:wrap; }
.track { margin:0 0 2.5rem; }
.track h2 { margin-top:0; }
.track .why { color:var(--ink2); font-size:.92rem; margin:0 0 1rem; }
.lesson-list { list-style:none; padding:0; margin:0; }
.lesson-list li { margin:0; border-bottom:1px solid var(--rule); }
.lesson-list a { display:flex; gap:.9rem; padding:.7rem .2rem;
                 text-decoration:none; align-items:baseline; }
.lesson-list a:hover { background:var(--card); }
.lesson-list .n { color:var(--ink3); font-variant-numeric:tabular-nums;
                  font-size:.82rem; min-width:1.6rem; }
.lesson-list .t { color:var(--ink); }
.lead { color:var(--ink2); font-size:1.05rem; margin-bottom:1.6rem; }
#q { width:100%; padding:.6rem .8rem; font:inherit; border-radius:6px;
     border:1px solid var(--rule); background:var(--card); color:var(--ink); }
#hits { list-style:none; padding:0; margin:1rem 0 0; }
#hits li { padding:.5rem 0; border-bottom:1px solid var(--rule); }
#hits .ctx { color:var(--ink2); font-size:.87rem; }
mark { background:#ffe9a8; color:#000; }
.foot { margin-top:3rem; padding-top:1rem; border-top:1px solid var(--rule);
        color:var(--ink3); font-size:.85rem; }
.pager { display:flex; justify-content:space-between; gap:1rem; margin-top:2.5rem;
         padding-top:1rem; border-top:1px solid var(--rule); font-size:.9rem; }
"""

# The search is the one place this site needs scripting, and it earns it: a
# reader who meets `BLOCKED (G1)` wants to type it, not to guess which of
# seventeen lessons explains it. The index is inlined, so the page works from a
# file:// URL with no server.
_SEARCH_JS = r"""
const IDX = __INDEX__;
const q = document.getElementById('q'), hits = document.getElementById('hits');
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
// Highlighting without RegExp, deliberately. Building one from user input needs
// the term escaped, and getting that escape through Python's string literal and
// into the page is how this shipped BROKEN the first time -- an invalid
// character class, which fails at parse and makes the whole search silently do
// nothing. indexOf needs no escaping and cannot be malformed.
function mark(text, term){
  const lower = text.toLowerCase(), out = [];
  let at = 0;
  for (;;) {
    const i = lower.indexOf(term, at);
    if (i < 0) { out.push(esc(text.slice(at))); break; }
    out.push(esc(text.slice(at, i)));
    out.push('<mark>' + esc(text.slice(i, i + term.length)) + '</mark>');
    at = i + term.length;
  }
  return out.join('');
}
// Words, not a substring. A reader who meets a refusal types the phrase, but a
// reader who is lost types a QUESTION -- "what is metis for", "can I approve my
// own work" -- and a whole-phrase match returns nothing for both of those while
// the academy answers them on page one. So: every word must appear somewhere,
// and the words that are not noise decide the ranking.
const STOP = new Set(['a','an','and','are','as','at','be','can','do','does','for',
  'from','how','i','if','in','is','it','me','my','of','on','or','that','the',
  'this','to','what','when','where','which','who','why','will','with','you','your']);
function run(){
  const raw = q.value.trim().toLowerCase();
  hits.innerHTML = '';
  if (raw.length < 2) return;
  const words = raw.split(/\s+/).filter(Boolean);
  const strong = words.filter(w => !STOP.has(w));
  // An all-stopword query ("how do I") has nothing to rank on; say so rather
  // than returning the whole academy in file order.
  const needed = strong.length ? strong : words;
  const found = [];
  for (const d of IDX) {
    const body = d.fbody, title = d.ftitle;
    if (!needed.every(w => body.includes(w) || title.includes(w))) continue;
    // No scoring model: 17 documents do not need one, and an unexplainable
    // ranking is worse than a plain one.
    // Ranked on EVERY word of the query against the title, stopwords included
    // -- and that is the point. "what is metis for" reduces to the single
    // strong word `metis`, which every lesson contains, so the meaningful
    // words alone cannot tell "What Metis is for" from "What Metis does not
    // do". The little words are what distinguish a title; they are poor at
    // deciding whether a document matches at all, which is why `needed` still
    // gates membership and only the ranking sees them.
    const inTitle = words.filter(w => title.includes(w)).length / words.length;
    const anchor = needed.find(w => body.includes(w)) || needed[0];
    const i = body.indexOf(anchor);
    const at = Math.max(0, i - 60);
    const ctx = i < 0 ? d.body.slice(0, 140)
                      : d.body.slice(at, i + anchor.length + 90);
    found.push({d: d, ctx: ctx, term: anchor, score: -inTitle});
  }
  found.sort(function(a,b){ return a.score - b.score || a.d.n - b.d.n; });
  for (const f of found.slice(0, 25)) {
    const li = document.createElement('li');
    li.innerHTML = '<a href="' + f.d.href + '">' + esc(f.d.title) + '</a>' +
      '<div class="ctx">…' + mark(f.ctx, f.term) + '…</div>';
    hits.appendChild(li);
  }
  if (!found.length) hits.innerHTML =
    '<li class="ctx">Nothing in the academy matches that. ' +
    'It may still be something Métis does — the academy is reasoning, ' +
    'not a reference for every flag.</li>';
}
q.addEventListener('input', run);
"""


def _shell(title: str, body: str, *, depth: int = 0, script: str = "") -> str:
    up = "../" * depth
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body>"
        f'<div class="wrap">'
        f'<nav class="top"><a href="{up}index.html">The Métis academy</a>'
        f'<a href="{up}index.html#search">Search</a>'
        f'<a href="{up}glossary.html">Glossary</a>'
        f'<a href="{up}refusals.html">What a refusal means</a></nav>'
        f"{body}"
        f'<p class="foot">Generated from <code>docs/academy/</code> by '
        f"<code>metis academy</code>. The lessons are the source of truth; "
        f"editing a page here is overwritten by the next run.</p>"
        f"</div>{script}</body></html>")


def _page_name(lesson: dict) -> str:
    return f"{lesson['ordinal']:02d}-{lesson['slug']}.html"


def read_proposals(directory) -> list[dict]:
    """The D-2 decision records beside the lessons.

    `read_lessons` excludes these deliberately — a proposal is a record of a
    decision, not material to be taught, and landing one as a `Lesson` would put
    it in the same space as the reasoning it decided about. But excluding them
    from the SITE too left three of them reachable only by somebody browsing the
    repository, which is the delivery failure this site exists to fix, one
    document type over.
    """
    root = Path(directory)
    out = []
    for path in sorted(root.glob("PROPOSAL-*.md")):
        from metis_mcp.model_sources.lessons import parse_frontmatter

        _, body = parse_frontmatter(path.read_text())
        title = next((line.lstrip("# ").strip()
                      for line in body.split("\n") if line.startswith("# ")),
                     path.stem)
        out.append({"slug": path.stem, "title": title, "text": body,
                    "page": f"{path.stem.lower()}.html"})
    return out


def build(lessons: list[dict], proposals: list[dict] | None = None) -> dict[str, str]:
    """Every page of the site, as `{filename: html}`. Pure — writes nothing."""
    by_topic: dict[str, list[dict]] = {}
    for lesson in lessons:
        for topic in lesson["topics"] or ["concepts"]:
            by_topic.setdefault(topic, []).append(lesson)

    pages: dict[str, str] = {}
    ordered = sorted(lessons, key=lambda l: l["ordinal"])

    # ---- lesson pages, with a pager in reading order ----
    for position, lesson in enumerate(ordered):
        previous = ordered[position - 1] if position else None
        following = ordered[position + 1] if position + 1 < len(ordered) else None
        pager = '<div class="pager">'
        pager += (f'<a href="{_page_name(previous)}">← {html.escape(previous["title"])}</a>'
                  if previous else "<span></span>")
        pager += (f'<a href="{_page_name(following)}">{html.escape(following["title"])} →</a>'
                  if following else "<span></span>")
        pager += "</div>"
        pages[_page_name(lesson)] = _shell(
            lesson["title"],
            render_markdown(lesson["text"]) + pager)

    # ---- the index ----
    sections = []
    for topic, heading, why in TRACKS:
        in_track = sorted(by_topic.get(topic, []), key=lambda l: l["ordinal"])
        if not in_track:
            continue
        items = "".join(
            f'<li><a href="{_page_name(l)}">'
            f'<span class="n">{l["ordinal"]:02d}</span>'
            f'<span class="t">{html.escape(l["title"])}</span></a></li>'
            for l in in_track)
        sections.append(f'<section class="track"><h2>{html.escape(heading)}</h2>'
                        f'<p class="why">{html.escape(why)}</p>'
                        f'<ul class="lesson-list">{items}</ul></section>')

    # Any topic the frontmatter declares that TRACKS does not name. Listed
    # rather than dropped: a lesson invisible from the index is the delivery
    # failure this site exists to fix, one level down.
    named = {t for t, _, _ in TRACKS}
    for topic in sorted(set(by_topic) - named):
        in_track = sorted(by_topic[topic], key=lambda l: l["ordinal"])
        items = "".join(
            f'<li><a href="{_page_name(l)}">'
            f'<span class="n">{l["ordinal"]:02d}</span>'
            f'<span class="t">{html.escape(l["title"])}</span></a></li>'
            for l in in_track)
        sections.append(f'<section class="track"><h2>{html.escape(topic)}</h2>'
                        f'<ul class="lesson-list">{items}</ul></section>')

    # **Folded copies for matching, original text for showing.**
    #
    # `Metis` with an accent does not contain the substring `metis`, so a reader
    # who types the name without one -- which is most of them -- matched no
    # TITLE at all and every lesson ranked identically. `retrieval.fold` is the
    # same normalisation the graph index uses, so the site and `search_knowledge`
    # agree about what a word is. It is length-preserving for the accents this
    # corpus carries, which is what lets an offset found in the folded body slice
    # the original.
    def _plain(text: str) -> str:
        return re.sub(r"[#*`|>\-]+", " ", text)

    index = json.dumps([
        {"n": l["ordinal"], "title": l["title"], "href": _page_name(l),
         "body": _plain(l["text"]),
         "ftitle": _aligned_fold(l["title"]),
         "fbody": _aligned_fold(_plain(l["text"]))}
        for l in ordered])
    script = ("<script>"
              + _SEARCH_JS.replace("__INDEX__", index)
              + "</script>")

    pages["index.html"] = _shell(
        "The Métis academy",
        '<h1>The Métis academy</h1>'
        '<p class="lead">Métis recovers what a system <strong>does</strong> from '
        "its code, compares that against what somebody <strong>said it should "
        "do</strong>, and generates test cases from the part that survives "
        "review. These lessons explain that in plain language.</p>"
        '<section id="search"><h2>Search the academy</h2>'
        '<input id="q" type="search" placeholder="a phrase, or a message you saw '
        '— try: quarantine, BLOCKED, unverifiable" autocomplete="off">'
        '<ul id="hits"></ul></section>'
        + "".join(sections)
        # **Parenthesised, and it was not.** `a + b + (X) if c else ""` parses as
        # `(a + b + X) if c else ""`, so with no proposals the WHOLE index body
        # collapsed to an empty string -- every track silently gone from a page
        # that still rendered. The existing tests caught it; nothing about the
        # output looked wrong except that it was empty.
        + ((f'<section class="track"><h2>Decisions on the record</h2>'
           f'<p class="why">D-2 makes adding a label a reviewed change rather '
           f"than an edit. These are the arguments, kept so a decision can be "
           f"checked on its merits — including the ones that recommend "
           f"refusing.</p>"
           f'<ul class="lesson-list">'
           + "".join(
               f'<li><a href="{p["page"]}">'
               f'<span class="n">·</span>'
               # `_inline` rather than `escape`: a proposal titles itself with
               # the label it is about, in backticks, and an index that shows
               # them raw reads as unrendered source.
               f'<span class="t">{_inline(p["title"])}</span></a></li>'
               for p in (proposals or []))
           + "</ul></section>") if proposals else ""),
        script=script)

    # ---- the decision records ----
    for proposal in (proposals or []):
        pages[proposal["page"]] = _shell(
            # Backticks stripped for the browser tab: `<title>` renders no
            # markup, so a `<code>` tag would show literally and a backtick
            # reads as unrendered source. The heading in the body keeps them.
            proposal["title"].replace("`", ""),
            render_markdown(proposal["text"])
            + '<div class="pager"><a href="index.html">← the academy</a></div>')

    # ---- the two reference pages an operator returns to ----
    glossary = next((l for l in lessons if "words-we-use" in l["slug"]), None)
    if glossary is not None:
        pages["glossary.html"] = _shell(
            "Glossary", render_markdown(glossary["text"])
            + f'<div class="pager"><a href="{_page_name(glossary)}">'
              f"this is lesson {glossary['ordinal']:02d} →</a></div>")

    refusals = next((l for l in lessons if "refuses" in l["slug"]), None)
    if refusals is not None:
        pages["refusals.html"] = _shell(
            "What a refusal means", render_markdown(refusals["text"])
            + f'<div class="pager"><a href="{_page_name(refusals)}">'
              f"this is lesson {refusals['ordinal']:02d} →</a></div>")

    return pages


def stale(directory: str | Path, lessons: list[dict],
          proposals: list[dict] | None = None) -> list[Path]:
    """Pages in `directory` that the current corpus no longer produces.

    A renamed lesson is the case this exists for: `write` used to overwrite the
    pages it produces and leave everything else alone, so `08-finding-things.md`
    renamed to `08-search.md` left the old page sitting in the output with its
    old text, reachable by anyone who had the URL and linked from nothing.
    That is the `stale_agents` failure one directory over -- a dead generated
    file is worse than a missing one, because it is confidently wrong.
    """
    root = Path(directory)
    if not root.is_dir():
        return []
    expected = set(build(lessons, proposals))
    return sorted(p for p in root.glob("*.html") if p.name not in expected)


def check(directory: str | Path, lessons: list[dict],
          proposals: list[dict] | None = None) -> list[str]:
    """What differs between a rendered site and what this would generate now.

    **What this can and cannot catch.** `docs/academy-site/` is deliberately not
    committed (the reason is in `.gitignore`: every page inlines a ~90KB search
    index, which would land in every diff that touches a lesson). So there is no
    committed copy for CI to compare against, and this is not the guide's
    `--check`: it answers "is the site I rendered still current?" for whoever
    rendered it, not "does the repository agree with itself".

    The half that IS enforced everywhere lives in `test_academy_site.py`: every
    lesson and every proposal gets a page, and the index links all of them. What
    was missing is this half -- the site on somebody's disk silently ageing past
    the lessons it was rendered from, which is how a proposal page went missing
    and four pages went stale without anything saying so.
    """
    root = Path(directory)
    problems = []
    for name, content in sorted(build(lessons, proposals).items()):
        path = root / name
        if not path.exists():
            problems.append(f"{name}: missing")
        elif path.read_text() != content:
            problems.append(f"{name}: differs from what the lessons now render")
    for path in stale(directory, lessons, proposals):
        problems.append(f"{path.name}: no lesson or proposal produces this")
    return problems


def write(directory: str | Path, lessons: list[dict],
          proposals: list[dict] | None = None, prune: bool = True) -> list[Path]:
    """Render the whole site. Removes pages nothing produces unless told not to."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    if prune:
        for dead in stale(root, lessons, proposals):
            dead.unlink()
    written = []
    for name, body in build(lessons, proposals).items():
        path = root / name
        path.write_text(body)
        written.append(path)
    return sorted(written)
