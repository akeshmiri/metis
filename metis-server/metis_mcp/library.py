"""The document half of the MCP surface: skills as prompts, everything else as resources.

**Why this exists.** The server exposed thirty-one tools and nothing else. A tool
answers a question the engine computes; it cannot carry a procedure, and it
cannot hand a reader a document. So the two plugins split: `metis-mcp` shipped
the tools, `metis` shipped the thirteen skills, and neither declared the other —
install one and you get tools with no procedure, install the other and you get
skills naming tools that are not there.

MCP already has the two primitives that close this, and they map onto the
placement rule rather than against it (`docs/academy/10-where-a-thing-belongs.md`):

    tool      a question with a determinate answer the engine computes
    prompt    the procedure, its order, its gates, its refusals  -> a skill
    resource  a document somebody wrote, addressed by URI

**The rule is about layers, not transports.** A skill delivered as an MCP prompt
is still a skill: prose telling a model what to do where the answer is not
determinate. Nothing here computes anything, and nothing here becomes a tool.

**Progressive disclosure survives, and that was the risk.** `SKILL.md` is paid
for every time; `steps/` one at a time; `knowledge/` only when a step cites it.
A prompt that inlined a skill's whole directory would spend the budget the
folder tree exists to protect. So a prompt carries `SKILL.md` alone, and every
step, knowledge fragment and reference is a separate resource the reader fetches
when a step cites it — which is the same discipline, expressed in a protocol
that has a word for it.

**Read-only, and file-backed.** Nothing here touches the graph or imports a
write path. Resources are registered as concrete `FileResource`s from a
discovered list, never as URI templates over a caller-supplied path: the path is
fixed when the server starts, so there is no traversal surface to get wrong.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SCHEME = "metis"

# Sub-directories of a skill that hold readable documents, in the order the
# placement rule introduces them. `references/` is included even though only one
# skill has one — an absent directory is a fact about the tree, not about this.
SECTIONS = ("steps", "knowledge", "references")

# Document kinds, kept as constants because they are reported to a caller.
SKILL = "skill"
GUIDE = "guide"
ACADEMY = "academy"
SPEC = "spec"


class LibraryUnavailable(Exception):
    """The documents are not beside this package, so none can be served."""


def repo() -> Path:
    """The repository root: `metis_mcp/` -> `metis-server/` -> here.

    The same hop `agent_generator.REPO` makes, and it fails the same way — an
    installed package with no repository checked out beside it.
    """
    return Path(__file__).resolve().parents[2]


def available() -> tuple[bool, str]:
    """Whether documents can be served here, and what is missing if not.

    The skills ship in `plugins/`, the guide and the academy in `docs/`, and
    neither travels with the Python package. A `pip install metis-mcp-server`
    with no repository beside it has the tools and none of the procedure, and it
    must say so rather than presenting an empty library as a complete one — the
    same distinction `intakes.uif_schema_available` draws.
    """
    root = repo()
    missing = [str(p.relative_to(root)) for p in
               (root / "plugins" / "metis" / "skills", root / "docs")
               if not p.exists()]
    if missing:
        return False, (f"not beside this package: {', '.join(missing)} — the "
                       f"skills and documents ship with the repository, not "
                       f"with the Python distribution")
    return True, ""


@dataclass(frozen=True)
class Document:
    """One readable file, addressed by URI."""

    uri: str
    name: str
    description: str
    path: Path
    kind: str


def _title(path: Path) -> str:
    """The document's own first heading, or its filename.

    Read from the file rather than derived from the path: a step named
    `01-extract.md` says "Extract the model from a code property graph" at the
    top, and that is what a reader picking between resources needs to see.
    """
    try:
        for line in path.read_text(errors="ignore").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
    except OSError:
        pass
    return path.stem.replace("-", " ")


def _skill_documents(skill) -> list:
    """One skill's own file, then everything under it a step may cite."""
    found = [Document(
        uri=f"{SCHEME}://{SKILL}/{skill.name}",
        name=skill.name,
        description=_first_sentence(skill.description),
        path=skill.directory / "SKILL.md",
        kind=SKILL,
    )]
    for section in SECTIONS:
        directory = skill.directory / section
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            found.append(Document(
                uri=f"{SCHEME}://{SKILL}/{skill.name}/{section}/{path.stem}",
                name=f"{skill.name} · {section}/{path.stem}",
                description=_title(path),
                path=path,
                kind=section,
            ))
    return found


def _first_sentence(text: str) -> str:
    """The description a client shows in a list. Mirrors `agent_generator`."""
    match = re.search(r"(.+?\.)(\s|$)", (text or "").strip(), re.S)
    return (match.group(1) if match else (text or "").strip()).replace("\n", " ")


def documents() -> list:
    """Every document this deployment can serve, in a stable order.

    Raises rather than returning an empty list when the tree is absent: "nothing
    to serve" and "nothing was looked at" are different answers, and the second
    one dressed as the first is how a caller concludes a skill does not exist.
    """
    ok, why = available()
    if not ok:
        raise LibraryUnavailable(why)

    from metis_mcp.agent_generator import read_skills

    root = repo()
    found: list = []

    # Skills first: they are the procedures, and the rest is what a step cites.
    for skill in read_skills():
        if skill.directory is not None:
            found += _skill_documents(skill)

    # The generated guide. It is derived from `labels.py`, `stages.py` and the
    # CLI parser, and `metis guide --check` fails on a diff — so serving it here
    # cannot drift from the engine the way a hand-written page would.
    for path in sorted((root / "docs" / "guide").glob("*.md")):
        found.append(Document(
            uri=f"{SCHEME}://{GUIDE}/{path.stem}",
            name=f"guide/{path.stem}",
            description=_title(path),
            path=path,
            kind=GUIDE,
        ))

    # The academy: authored reasoning, labelled as such because it is not
    # checkable the way the guide is.
    for path in sorted((root / "docs" / "academy").glob("*.md")):
        if path.name == "README.md":
            continue
        found.append(Document(
            uri=f"{SCHEME}://{ACADEMY}/{path.stem}",
            name=f"academy/{path.stem}",
            description=_title(path),
            path=path,
            kind=ACADEMY,
        ))

    spec = root / "docs" / "metis-application-spec.md"
    if spec.exists():
        found.append(Document(
            uri=f"{SCHEME}://{SPEC}",
            name="application-spec",
            description=("The authoritative specification. Where this and the "
                         "code disagree, the code and the spec win over any "
                         "other description."),
            path=spec,
            kind=SPEC,
        ))

    return found


def describe() -> dict:
    """What the document surface holds, or why it holds nothing."""
    ok, why = available()
    if not ok:
        return {"ok": False, "available": False, "reason": why,
                "prompts": 0, "resources": 0}

    docs = documents()
    by_kind: dict = {}
    for doc in docs:
        by_kind[doc.kind] = by_kind.get(doc.kind, 0) + 1
    return {
        "ok": True,
        "available": True,
        "resources": len(docs),
        "by_kind": by_kind,
        "prompts": by_kind.get(SKILL, 0),
        "scheme": f"{SCHEME}://",
        "means": ("a prompt is a skill — the procedure and its gates; a "
                  "resource is a document somebody wrote. Neither computes "
                  "anything: the tools do that."),
    }
