"""
Three-way drift detection (application spec §7.6; T-12..T-16, A-20, A-21).

Regeneration performs a **three-way** comparison, not a two-way one:

    last generated       what Métis wrote the previous time
    currently published  what is in the test-management tool right now
    newly generated      what Métis would write now

**T-13 is the reason it must be three-way.** A two-way diff conflates two changes
that need opposite handling:

    newly generated  != last generated      the MODEL changed — behaviour moved
    currently published != last generated   a HUMAN edited the published case

With only "published vs new" those are indistinguishable, and the tool either
overwrites a tester's work or refuses every legitimate update.

**T-15 -- nothing is written without a decision, and a manually edited case is
never overwritten.** A tester's added steps, environment notes and data are real
work; silently destroying them teaches people not to trust the tool, which costs
far more than a missed update. **T-16 -- obsolete cases are deprecated, never
deleted**: their execution history is evidence.

`TestCase.last_generated_hash` (spec D-9) is what makes this possible, and it is
computed here rather than stored on the frozen dataclass so that rendering stays
free of publication concerns.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from metis_mcp.rendering.test_case import TestCase

LEDGER_VERSION = "metis.publication-ledger/1"

# Drift classes (spec T-14).
UNCHANGED = "unchanged"
NEW = "new"
CHANGED = "changed"
MANUALLY_EDITED = "manually_edited"
OBSOLETE = "obsolete"

# Default actions. `MANUALLY_EDITED` proposes **nothing** -- T-14 is explicit that
# it is surfaced for a human decision rather than resolved by a default.
PROPOSE_CREATE = "propose_create"
PROPOSE_UPDATE = "propose_update"
PROPOSE_DEPRECATE = "propose_deprecate"
PROPOSE_NOTHING = "propose_nothing"
NO_ACTION = "no_action"

_DEFAULT_ACTION = {
    UNCHANGED: NO_ACTION,
    NEW: PROPOSE_CREATE,
    CHANGED: PROPOSE_UPDATE,
    MANUALLY_EDITED: PROPOSE_NOTHING,
    OBSOLETE: PROPOSE_DEPRECATE,
}


def content_hash(case: TestCase) -> str:
    """Hash of what a reader of the case would see (spec D-9).

    Deliberately excludes `criterion`: T-10 makes the criterion metadata, not
    identity, so regenerating under a deeper criterion must not make every case
    look edited. Includes step wording and expected results, because those are
    exactly what a human would change by hand.
    """
    steps = [(s.description, s.expected_result, s.guard_verbatim, s.is_assertion)
             for s in (*case.precondition_steps, case.act_step)]
    basis = json.dumps({
        "id": case.id, "name": case.name, "objective": case.objective,
        "model_id": case.model_id, "steps": steps,
        "data_requirements": [(d.condition, sorted(d.steps))
                              for d in case.data_requirements],
    }, sort_keys=True)
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


@dataclass
class PublishedCase:
    """What the test-management tool currently holds.

    `content_hash` is of the *published* content, so a hand edit moves it away
    from `last_generated_hash` -- which is the whole detection mechanism.
    """

    case_id: str
    published_id: str
    content_hash: str
    published_status: str = "active"


@dataclass
class PublicationLedger:
    """What Métis last generated, per case (spec D-9).

    Separate from the review state and the override log: this records what was
    *sent outward*, which is a different fact from what was decided or edited.
    """

    version: str = LEDGER_VERSION
    model_id: str = ""
    last_generated: dict[str, str] = field(default_factory=dict)
    published: dict[str, PublishedCase] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "version": self.version,
            "model_id": self.model_id,
            "_note": ("What Métis last generated and what is currently published. "
                      "The third leg of §7.6's three-way comparison; without it a "
                      "model change and a manual edit are indistinguishable (D-9)."),
            "last_generated": self.last_generated,
            "published": {k: asdict(v) for k, v in self.published.items()},
        }, indent=2)

    @staticmethod
    def from_json(text: str) -> "PublicationLedger":
        data = json.loads(text)
        return PublicationLedger(
            version=data.get("version", LEDGER_VERSION),
            model_id=data.get("model_id", ""),
            last_generated=dict(data.get("last_generated", {})),
            published={k: PublishedCase(**v) for k, v in data.get("published", {}).items()},
        )

    @staticmethod
    def load(path: str | Path) -> "PublicationLedger":
        p = Path(path)
        return PublicationLedger.from_json(p.read_text()) if p.exists() else PublicationLedger()

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())


def default_ledger_path(model_path: str | Path) -> Path:
    """`login-api.json` -> `login-api.published.json`."""
    p = Path(model_path)
    return (p.with_suffix("").with_suffix(".published.json") if p.suffix
            else Path(f"{p}.published.json"))


@dataclass(frozen=True)
class DriftItem:
    case_id: str
    drift_class: str
    action: str
    detail: str
    published_id: str = ""
    diff: tuple[str, ...] = ()

    @property
    def needs_decision(self) -> bool:
        return self.action != NO_ACTION


@dataclass
class DriftReport:
    model_id: str
    items: list[DriftItem] = field(default_factory=list)

    def of(self, drift_class: str) -> list[DriftItem]:
        return [i for i in self.items if i.drift_class == drift_class]

    @property
    def summary(self) -> dict[str, int]:
        return {c: len(self.of(c)) for c in
                (UNCHANGED, NEW, CHANGED, MANUALLY_EDITED, OBSOLETE)}

    @property
    def actionable(self) -> list[DriftItem]:
        return [i for i in self.items if i.needs_decision]


def _diff_lines(a: TestCase | None, b: TestCase) -> tuple[str, ...]:
    """What actually moved, so T-14's "showing the diff" is real."""
    if a is None:
        return ()
    out = []
    if a.name != b.name:
        out.append(f"name: {a.name!r} -> {b.name!r}")
    if a.objective != b.objective:
        out.append(f"objective: {a.objective!r} -> {b.objective!r}")
    old_steps = [(s.description, s.expected_result, s.guard_verbatim)
                 for s in (*a.precondition_steps, a.act_step)]
    new_steps = [(s.description, s.expected_result, s.guard_verbatim)
                 for s in (*b.precondition_steps, b.act_step)]
    if len(old_steps) != len(new_steps):
        out.append(f"steps: {len(old_steps)} -> {len(new_steps)}")
    for i, (old, new) in enumerate(zip(old_steps, new_steps), start=1):
        if old != new:
            out.append(f"step {i}: {old} -> {new}")
    return tuple(out)


def compare(new_cases: list[TestCase], ledger: PublicationLedger,
            previous_cases: dict[str, TestCase] | None = None) -> DriftReport:
    """The three-way comparison (spec T-12, T-14).

    `previous_cases` is optional and only enriches the diff text: the *class* is
    determined from hashes alone, so drift detection does not depend on retaining
    every prior rendering.
    """
    report = DriftReport(model_id=ledger.model_id)
    previous = previous_cases or {}
    seen: set[str] = set()

    for case in sorted(new_cases, key=lambda c: c.id):
        seen.add(case.id)
        new_hash = content_hash(case)
        last = ledger.last_generated.get(case.id)
        published = ledger.published.get(case.id)

        if last is None and published is None:
            report.items.append(DriftItem(
                case_id=case.id, drift_class=NEW, action=PROPOSE_CREATE,
                detail=f"{case.name}: no published case for this path"))
            continue

        # T-13, and the order matters: a manual edit is checked FIRST. A case
        # that was both hand-edited and model-changed must never be proposed for
        # update -- the edit is the fact that decides, because overwriting it is
        # the irreversible outcome.
        if published is not None and last is not None and published.content_hash != last:
            report.items.append(DriftItem(
                case_id=case.id, drift_class=MANUALLY_EDITED, action=PROPOSE_NOTHING,
                published_id=published.published_id,
                detail=(f"{case.name}: published content differs from what Métis last "
                        f"generated — someone edited it by hand. Proposing nothing; "
                        f"a human decides (T-15)"),
                diff=_diff_lines(previous.get(case.id), case)))
            continue

        if last != new_hash:
            report.items.append(DriftItem(
                case_id=case.id, drift_class=CHANGED, action=PROPOSE_UPDATE,
                published_id=published.published_id if published else "",
                detail=f"{case.name}: the model moved",
                diff=_diff_lines(previous.get(case.id), case)))
            continue

        report.items.append(DriftItem(
            case_id=case.id, drift_class=UNCHANGED, action=NO_ACTION,
            published_id=published.published_id if published else "",
            detail=f"{case.name}: unchanged"))

    # T-14/T-16: a published case whose path no longer generates.
    for case_id, published in sorted(ledger.published.items()):
        if case_id in seen or published.published_status == "deprecated":
            continue
        report.items.append(DriftItem(
            case_id=case_id, drift_class=OBSOLETE, action=PROPOSE_DEPRECATE,
            published_id=published.published_id,
            detail=("no path generates this case any more — propose deprecation. "
                    "It is never deleted: its execution history is evidence (T-16)")))

    return report


def record_generation(ledger: PublicationLedger, model_id: str,
                      cases: list[TestCase]) -> None:
    """Update what Métis *last generated*.

    Called after a successful publication, never at render time: recording it
    earlier would mean an abandoned run silently became the new baseline, and the
    next comparison would read a real manual edit as unchanged.
    """
    ledger.model_id = model_id
    for case in cases:
        ledger.last_generated[case.id] = content_hash(case)


def format_drift(report: DriftReport) -> str:
    s = report.summary
    lines = [f"Drift — {report.model_id}",
             f"  unchanged:        {s[UNCHANGED]}",
             f"  new:              {s[NEW]}",
             f"  changed:          {s[CHANGED]}   (the model moved)",
             f"  manually edited:  {s[MANUALLY_EDITED]}   (a human edited the published case)",
             f"  obsolete:         {s[OBSOLETE]}"]
    for cls, title in ((NEW, "NEW"), (CHANGED, "CHANGED"),
                       (MANUALLY_EDITED, "MANUALLY EDITED"), (OBSOLETE, "OBSOLETE")):
        items = report.of(cls)
        if not items:
            continue
        lines += ["", f"  {title}"]
        for item in items[:8]:
            lines.append(f"    {item.case_id}  [{item.action}]  {item.detail}")
            for d in item.diff[:4]:
                lines.append(f"        {d}")
    if report.of(MANUALLY_EDITED):
        lines += ["",
                  "  Manually edited cases are NEVER overwritten by regeneration (T-15).",
                  "  Nothing is proposed for them; decide each one explicitly."]
    return "\n".join(lines)
