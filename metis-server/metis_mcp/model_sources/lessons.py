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
        body = path.read_text()
        lessons.append({
            "ordinal": int(ordinal),
            "slug": slug,
            "path": path.name,
            "title": _title_of(body, slug),
            "text": body,
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


def plan_lessons(directory: str | Path, *, job_id: str = "manual",
                 proposed_by: str = "academy",
                 t_recorded: str | None = None):
    """`Episode` + one `Lesson` per file. Pure: no session, no writes."""
    from metis_mcp.model_sources.landing import LandingPlan, PlannedNode
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

    return plan
