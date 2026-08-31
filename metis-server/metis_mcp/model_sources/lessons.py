"""
The academy, landed (D-1's writer for `Lesson`; the reader is `SEARCH_TARGETS`).

**Why a document about Métis is in the graph at all.** Every other label describes
a system under test. This one describes this system, and the argument for the
exception is in `docs/academy/PROPOSAL-landing-the-academy.md`: a lesson that
reads badly through `ask` is a finding about the tools rather than about the
writing. Landed, the academy becomes a standing test of the retrieval surface
against content whose correct answer is known.

**It lands at Quarantine like everything else (S-4).** The academy is not exempt
from the rule it teaches. A lesson is authored text, not agreed fact, and nothing
here writes `Approved`.

**Identity is content-derived (D-8).** Re-landing an unchanged academy writes
nothing new, and an edited lesson lands as the same node with new text rather
than as a second lesson — the file path is the natural key, because that is what
a reader follows and what does not change when a title is reworded.
"""
from __future__ import annotations


import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from metis_mcp.retrieval import search_text_for

QUARANTINE = "Quarantine"

# `NN-slug.md`. The number is the reading order the README already publishes, and
# taking it from the filename rather than from front matter means the order
# cannot disagree with the directory listing a reader sees.
_LESSON_FILE = re.compile(r"^(\d{2})-(.+)\.md$")

# `N · Title`, which is the convention every lesson uses. Narrow on purpose: the
# earlier pattern also accepted `1. ` and `1 - `, forms this directory has never
# contained, and support for a convention nobody writes is a claim the code
# cannot back up.
_ORDINAL_PREFIX = re.compile(r"^\d+\s*·\s*")


class LessonsRefused(Exception):
    """The academy could not be read as lessons."""


def _title_of(body: str, fallback: str) -> str:
    """The first `# ` heading, or the filename made readable.

    A lesson without a heading is a formatting mistake rather than a reason to
    refuse the whole directory, so this degrades to something legible instead of
    raising — but it does not invent a title that looks authored.
    """
    for line in body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            # The academy's headings are `N · Title`, and the number is already a
            # property. Carrying it in the name too would mean re-ordering the
            # course silently disagreed with every stored title.
            return _ORDINAL_PREFIX.sub("", title).strip()
    return fallback.replace("-", " ").capitalize()


def parse_frontmatter(body: str) -> tuple[dict, str]:
    """`(fields, remaining_text)` from a leading `---` block.

    A deliberately small reader: `key: value` lines only, no nesting, no lists,
    no YAML. The academy needs one field, and importing a parser to read it
    would add a dependency to the runtime for a format nobody asked for.

    A document with no frontmatter is normal and returns `({}, body)` — the
    absence is not an error, it means nothing was declared.
    """
    if not body.startswith("---\n"):
        return {}, body
    end = body.find("\n---", 4)
    if end == -1:
        # An unterminated block is the author's typo, and treating the whole
        # document as frontmatter would silently land an empty lesson.
        return {}, body
    fields = {}
    for line in body[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            fields[key.strip().lower()] = value.strip()
    return fields, body[end + len("\n---"):].lstrip("\n")


def topics_of(fields: dict) -> list[str]:
    """The topics a document DECLARES, in order, de-duplicated.

    Never derived from the title or the prose. A lesson that declares none has
    none — see the `Topic` LabelSpec for why inferring one would be a guess
    wearing somebody else's authority.
    """
    raw = fields.get("topics") or fields.get("topic") or ""
    seen, out = set(), []
    for part in raw.replace(",", " ").split():
        slug = part.strip().lower()
        if slug and slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out


def read_lessons(directory: str | Path) -> list[dict]:
    """Every numbered lesson in reading order.

    `README.md` and the proposal are deliberately excluded: the index is
    navigation and the proposal is a decision record, and landing either as a
    lesson would put a table of contents into the same space as the material it
    points at.
    """
    root = Path(directory)
    if not root.is_dir():
        raise LessonsRefused(f"no academy at {root}")

    lessons = []
    for path in sorted(root.glob("*.md")):
        match = _LESSON_FILE.match(path.name)
        if not match:
            continue
        ordinal, slug = match.group(1), match.group(2)
        raw = path.read_text()
        fields, body = parse_frontmatter(raw)
        lessons.append({
            "ordinal": int(ordinal),
            "slug": slug,
            "path": path.name,
            "title": _title_of(body, slug),
            # The frontmatter is stripped: it is metadata about the document,
            # not part of it, and leaving it in would put `topics: practice`
            # into the text a reader is shown and the vector that ranks it.
            "text": body,
            "topics": topics_of(fields),
        })
    if not lessons:
        raise LessonsRefused(
            f"{root} contains no `NN-slug.md` lessons; nothing would be landed")
    return lessons


def episode_id_for(lessons: list[dict]) -> str:
    """Content-derived (D-8): re-landing an unchanged academy is a no-op."""
    digest = hashlib.sha256()
    for lesson in lessons:
        digest.update(f"{lesson['path']}|{lesson['text']}".encode("utf-8"))
    return "ep-lessons-" + digest.hexdigest()[:16]


def lesson_id(path: str) -> str:
    """The natural key is the FILE, not the title.

    A title gets reworded; the file a reader follows does not. Keying on the
    title would make a copy-edit look like a new lesson and leave the old one
    behind, which is the duplicate-node failure content-derived identity exists
    to prevent.
    """
    return "lesson:" + path.removesuffix(".md")


def sections_of(text: str) -> list[tuple[str, str]]:
    """`(heading, body)` per `##` section, body including its own heading.

    The heading is kept IN the body as well as beside it: it is often the most
    answer-shaped sentence in the section — `Why a selector is a property and
    not a node` is a question and its own answer — and a vector built from the
    prose alone loses it.

    Text before the first `##` (the title and any preamble) becomes the first
    section, so nothing in the document is unreachable by similarity.
    """
    import re

    parts = re.split(r"\n(?=## )", text)
    out: list[tuple[str, str]] = []
    for part in parts:
        body = part.strip()
        if not body:
            continue
        first = body.splitlines()[0].strip()
        heading = first.lstrip("# ").strip() or "(preamble)"
        out.append((heading, body))
    return out


class SystemNotDeclared(LessonsRefused):
    """The corpus does not say which system it documents."""


def system_of(directory: str | Path) -> str:
    """The system this corpus documents, from its index's own frontmatter.

    **Named after the SYSTEM, not the folder.** An academy is about something,
    and the root of its topic tree should say what — `topic:metis`, not
    `topic:academy`. Two corpora in folders both called `academy` document
    different systems and must not merge into one root; the same corpus moved to
    a different folder must not split into two.

    Declared in `README.md` as `system: <name>`, and REFUSED when absent. An
    earlier version took the directory name, which is a guess wearing a fact's
    clothing: it is real information about where the files sit and no
    information at all about what they are about. The same rule `topics_of`
    follows — authored, never inferred — applies here, and this is the more
    important place for it, because every document in the corpus hangs off it.
    """
    index = Path(directory) / "README.md"
    if index.is_file():
        fields, _ = parse_frontmatter(index.read_text())
        declared = (fields.get("system") or "").strip().lower()
        if declared:
            return declared
    raise SystemNotDeclared(
        f"{Path(directory)}/README.md does not declare `system: <name>` in its "
        f"frontmatter. The root of the topic tree is named after the system the "
        f"corpus documents, and naming it after the folder would be a guess — "
        f"two academies about different systems would then share one root.")


def plan_lessons(directory: str | Path, *, job_id: str = "manual",
                 proposed_by: str = "academy",
                 t_recorded: str | None = None):
    """`Episode` + one `Lesson` per file. Pure: no session, no writes."""
    from metis_mcp.model_sources.landing import (
        LandingPlan, PlannedEdge, PlannedNode)
    from metis_mcp.ontology.validation import validate

    lessons = read_lessons(directory)
    recorded = t_recorded or datetime.now(timezone.utc).isoformat(timespec="seconds")
    episode_id = episode_id_for(lessons)
    plan = LandingPlan(episode_id=episode_id)

    def add_node(label: str, props: dict) -> bool:
        outcome = validate(label, props)
        if not outcome.valid:
            plan.errors.extend(outcome.errors)
            return False
        plan.nodes.append(PlannedNode(label=label, properties=props))
        return True

    # The root of this collection. Created once, before any lesson, so the
    # topics below have something to attach to whatever order they arrive in.
    corpus = system_of(directory)
    # The corpus names the system it documents, and that is exactly the project
    # these nodes belong to — declared once in the corpus README, so `m_project`
    # and the root of the topic tree cannot disagree about what this is.
    plan.project = corpus
    corpus_topic_id = f"topic:{corpus}"
    add_node("Topic", {"id": corpus_topic_id, "name": corpus,
                       "source_episode_id": episode_id})

    add_node("Episode", {
        "id": episode_id,
        "name": f"academy: {len(lessons)} lesson(s)",
        "t_recorded": recorded,
        "source_connector": "lessons",
        "job_id": job_id,
    })

    for lesson in lessons:
        add_node("Lesson", {
            "id": lesson_id(lesson["path"]),
            "source_episode_id": episode_id,
            "name": lesson["title"],
            "text": lesson["text"],
            "ordinal": lesson["ordinal"],
            "path": lesson["path"],
            # The folded copy, indexed beside the original so `Metis` finds
            # a corpus about `Métis` (see retrieval.fold).
            "search_text": search_text_for(lesson["title"], lesson["text"]),
            # S-4. The academy is not exempt from the rule it teaches.
            "lifecycle_state": QUARANTINE,
        })

        # One shared Topic node per declared subject, so two lessons on the
        # same ground point at the SAME node and "what else covers this" is a
        # traversal rather than a second search. `add_node` is a MERGE by id, so
        # the eighth lesson declaring `practice` reuses the node the fifth made.
        #
        # Each of those then sits under the CORPUS topic (`topic:academy`), so
        # the collection has a root: "what is in the academy" is one hop, and a
        # second corpus landed later does not mix into it. A lesson still points
        # only at its own subjects — it reaches the root through them, which is
        # what keeps `related_by_topic` on a lesson from returning every document
        # in the corpus.
        for topic in lesson["topics"]:
            # The episode is whichever landing run first created it. A shared
            # node cannot carry one provenance per document pointing at it, and
            # the per-document provenance is on the edge's endpoints anyway.
            if add_node("Topic", {"id": f"topic:{topic}", "name": topic,
                                  "source_episode_id": episode_id}):
                plan.edges.append(PlannedEdge(
                    from_label="Lesson", from_id=lesson_id(lesson["path"]),
                    rel_type="BELONGS_TO",
                    to_label="Topic", to_id=f"topic:{topic}"))
                if topic != corpus:
                    plan.edges.append(PlannedEdge(
                        from_label="Topic", from_id=f"topic:{topic}",
                        rel_type="BELONGS_TO",
                        to_label="Topic", to_id=corpus_topic_id))

        # One Passage per `##` section, each carrying its own vector.
        #
        # The lesson keeps its own full text: a question about the document as a
        # whole should still match the document, and dropping that in favour of
        # sections alone would trade one dilution for the opposite one.
        parent = lesson_id(lesson["path"])
        for ordinal, (heading, body) in enumerate(sections_of(lesson["text"]), start=1):
            passage_id = f"{parent}#{ordinal:02d}"
            if add_node("Passage", {
                "id": passage_id,
                "source_episode_id": episode_id,
                "name": heading,
                "text": body,
                "ordinal": ordinal,
                "search_text": search_text_for(heading, body),
            }):
                plan.edges.append(PlannedEdge(
                    from_label="Lesson", from_id=parent,
                    rel_type="CONTAINS",
                    to_label="Passage", to_id=passage_id))

    return plan
