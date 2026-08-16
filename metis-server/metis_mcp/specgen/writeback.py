"""
Writing a generated specification back to the product repository (spec §18.4,
T-15..T-21, SP-8).

A specification that only lives in Métis is a specification the team does not
read. The athena estate already practises spec-driven development with GitHub
Spec Kit, so the generated document belongs beside the ones people already open:
`<repo>/.specify/specs/<feature>/spec.md`.

**This is an external write, and it is treated as one.** It goes through the same
single owner as test-case publication (`publishing/publish.py`) -- literal
affirmative confirmation, no default-yes, no timeout-implies-yes, one decision
per batch (T-18/T-19/T-20). There is deliberately no second write path: T-20's
value is that there is exactly one place to assert against, and adding a
"convenience" writer here would destroy it.

**A hand-edited target is never overwritten.** Three-way drift
(`publishing/drift.py`) already distinguishes "Métis changed" from "a human
changed" for test cases; the same distinction matters more for a spec, because a
product team editing its own spec file is doing exactly what it should. The
`metis-source-hash` marker -- the idea borrowed from Atlas's `check_design_sync.py`
-- records what Métis last wrote, so an edit is detectable rather than assumed.

**Nothing here decides whether the content is right.** It writes what §18
generated, and §18 writes what the model says. If the model is wrong, this
faithfully publishes a wrong document -- which is why SP-4's marks on unapproved
rules matter, and why this refuses to write a specification whose rules are not
approved unless told to.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from metis_mcp.specgen.specification import Document, Specification

# The marker Métis leaves behind, so its own last output is recognisable.
HASH_MARKER = "metis-source-hash"
_MARKER_RE = re.compile(rf"<!--\s*{HASH_MARKER}:\s*([0-9a-f]+)\s*-->")

UNCHANGED = "unchanged"
NEW = "new"
CHANGED = "changed"
MANUALLY_EDITED = "manually_edited"


def content_hash(body: str) -> str:
    """Hash of the document body, excluding the marker line itself."""
    stripped = _MARKER_RE.sub("", body).strip()
    return hashlib.sha256(stripped.encode()).hexdigest()[:16]


def stamp(body: str) -> str:
    """Add the marker so the next run can tell its own output from an edit."""
    return f"<!-- {HASH_MARKER}: {content_hash(body)} -->\n{body}"


def recorded_hash(body: str) -> str | None:
    m = _MARKER_RE.search(body or "")
    return m.group(1) if m else None


@dataclass(frozen=True)
class WriteTarget:
    """One intended file write."""

    path: Path
    body: str
    classification: str
    detail: str = ""

    @property
    def may_write(self) -> bool:
        """T-15: a hand-edited file is never overwritten by regeneration."""
        return self.classification in (NEW, CHANGED)


@dataclass
class WritePlan:
    """Pure. Nothing reaches the filesystem until `apply` runs it."""

    targets: list[WriteTarget] = field(default_factory=list)
    withheld: list[tuple[str, str]] = field(default_factory=list)

    @property
    def writable(self) -> list[WriteTarget]:
        return [t for t in self.targets if t.may_write]

    @property
    def size(self) -> int:
        return len(self.writable)


def classify(path: Path, new_body: str) -> tuple[str, str]:
    """Compare what is on disk against what Métis last wrote (spec T-12/T-13).

    Three-way, for the same reason test-case drift is: without knowing what
    Métis last wrote, a product team's edit and a model change look identical,
    and the tool either destroys their work or refuses every real update.
    """
    if not path.exists():
        return NEW, "no specification at this path yet"

    current = path.read_text()
    last = recorded_hash(current)
    if last is None:
        return (MANUALLY_EDITED,
                "this file carries no Métis marker — it was authored by the team, "
                "not generated. Never overwritten (T-15)")
    if last != content_hash(current):
        return (MANUALLY_EDITED,
                "the file has been edited since Métis wrote it. Never overwritten "
                "by regeneration (T-15); decide it explicitly")
    if content_hash(current) == content_hash(new_body):
        return UNCHANGED, "identical to what Métis last wrote"
    return CHANGED, "the model moved since this was written"


def spec_path(repo_root: str | Path, feature: str) -> Path:
    """`<repo>/.specify/specs/<feature>/spec.md` — Spec Kit's own layout."""
    return Path(repo_root) / ".specify" / "specs" / feature / "spec.md"


def plan_writeback(repo_root: str | Path, documents: dict[str, Document],
                   allow_unapproved: bool = False,
                   specs: dict[str, Specification] | None = None) -> WritePlan:
    """Build the write plan. **Pure** -- nothing leaves here.

    A specification with unapproved rules is withheld by default: SP-4 marks them
    in the body, but publishing an unreviewed extraction into the team's own spec
    directory gives a machine guess the standing of a decision (SP-5). The
    override exists and is explicit.
    """
    plan = WritePlan()
    for feature, document in sorted(documents.items()):
        spec = (specs or {}).get(feature)
        if spec is not None and not spec.is_fully_settled and not allow_unapproved:
            plan.withheld.append((
                feature,
                f"{spec.unsettled} rule(s) are not approved — publishing this into "
                f"the team's spec directory would give an unreviewed extraction the "
                f"standing of a decision (SP-5). Use --allow-unapproved to override"))
            continue

        path = spec_path(repo_root, feature)
        body = stamp(document.body)
        classification, detail = classify(path, document.body)
        target = WriteTarget(path=path, body=body,
                             classification=classification, detail=detail)
        plan.targets.append(target)
        if not target.may_write:
            plan.withheld.append((feature, f"{classification}: {detail}"))
    return plan


def apply(plan: WritePlan, confirmation=None) -> dict:
    """Write. Refuses without a literal confirmation (spec T-18).

    The confirmation type is `publishing.publish.Confirmation` -- the same one
    test-case publication uses, so there is one gate and one thing to assert
    against, not two that can drift apart (T-20).
    """
    from metis_mcp.publishing.publish import AFFIRMATIVE

    if confirmation is None:
        return {"ok": False, "written": [],
                "refused": (f"no confirmation given — nothing was written. Writing "
                            f"into a product repository requires the literal word "
                            f"{AFFIRMATIVE!r} in this run (T-18)"),
                "withheld": list(plan.withheld)}

    if confirmation.batch_size != plan.size:
        return {"ok": False, "written": [],
                "refused": (f"confirmation was given for {confirmation.batch_size} "
                            f"file(s), but this plan writes {plan.size}. Re-confirm "
                            f"against what is actually being written (T-19)"),
                "withheld": list(plan.withheld)}

    written = []
    for target in plan.writable:
        target.path.parent.mkdir(parents=True, exist_ok=True)
        target.path.write_text(target.body)
        written.append(str(target.path))
    return {"ok": True, "written": written, "refused": "",
            "confirmed_by": confirmation.confirmed_by,
            "withheld": list(plan.withheld)}


def format_plan(plan: WritePlan) -> str:
    from metis_mcp.publishing.publish import AFFIRMATIVE

    lines = [f"Specification write-back — {plan.size} file(s) would be written"]
    for target in plan.targets:
        flag = "" if target.may_write else "   [WITHHELD]"
        lines.append(f"  {target.classification:<16} {target.path}{flag}")
        lines.append(f"      {target.detail}")
    if plan.withheld:
        lines += ["", f"  {len(plan.withheld)} withheld:"]
        for feature, why in plan.withheld:
            lines.append(f"    {feature}: {why}")
    lines += ["",
              f"  Nothing has been written. To write, confirm with the literal word "
              f"{AFFIRMATIVE!r}.",
              "  A file the team has edited is never overwritten (T-15)."]
    return "\n".join(lines)
