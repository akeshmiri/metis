"""
Repair history — which files keep being fixed, and against which ticket.

**The strongest defect predictor there is, and the one Métis was asking for.**
`risk/product.py` declares `defect_history` as an `ASKED` input whose
`absent_means` reads "no history offered. Métis sees one snapshot of execution
results and cannot supply a trend". The repository is right there, and
`engine.changed_files` already shells out to git for a range; this is the read
that turns that asked input into a gathered one.

The empirical basis is not folklore. Relative code churn predicts defect density
(Nagappan & Ball), and fault-proneness concentrates hard — roughly 83% of faults
in the top 20% of files by predicted count. A file that has been repaired eleven
times this year is not more *important* than its neighbours; it is more likely to
need repairing again.

**What this refuses to do, and it is the whole reason the module has a shape.**

    Métis never creates a `Defect` from a commit message.

Matching `fix` against a subject line and writing a `Defect` would fill the graph
with faults nobody reported: real commit logs say "fix typo", "fix build", "fix
review comment". A `Defect` node means somebody observed a fault. A commit
message means somebody typed a word. `is_fix` is therefore a classification **of
the commit**, carrying `fix_basis` — the pattern that matched — so a reader can
disagree with the classification rather than only with the conclusion drawn from
it. Where a subject names a ticket key the edge is `FIXES` to the **item**,
because the item is the report. `test_history.py` asserts no `Defect` is ever
produced here.

**The window is stated and bounded.** History is read for an explicit range, the
same one `impact` takes. A count with no window is not a measurement: "eleven
fixes" means nothing without "since when", and an unbounded read on a five-year
repository makes the graph a second copy of git.

**No author, ever.** `Commit` carries no author field and this module does not
read one. A defect count per person is a management use of a quality signal, and
this system will not supply the column.

Returns `[]` on any git failure, like `changed_files`: a shallow clone, a missing
commit and a directory that is not a repository are all "I cannot tell you", and
the caller distinguishes that from "nothing was fixed" by having asked for a
range it believes in.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

PROVENANCE = "recovered_from_history"

#: What marks a subject as a repair. Deliberately narrow and deliberately
#: stated: a project whose conventions differ should change this in one place
#: rather than argue commit by commit, and `fix_basis` records which alternative
#: matched so the classification is auditable.
FIX_PATTERNS: dict[str, str] = {
    "conventional-commit": r"^\s*fix(\([^)]*\))?!?:",
    "subject-verb": r"\b(?:fix(?:e[sd])?|bugfix|hotfix|repair(?:ed)?)\b",
    "revert": r"^\s*revert\b",
}

#: A tracker key as trackers write them: `ABC-123`.
TICKET_KEY = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")

#: **Tokens with a ticket key's exact shape that are not tickets.** `UTF-8` and
#: `HTTP-2` match `[A-Z][A-Z0-9]+-\d+` because they *are* that shape — no regex
#: separates them from `ABC-1`, and pretending otherwise would put a standards
#: number in the graph as a fault report.
#:
#: So they are excluded by name. A short explicit list a reader can check beats a
#: cleverer pattern nobody can predict, and the real defence is downstream:
#: `plan_repairs` only edges to tickets the graph already holds, so a key from a
#: project Métis has never seen reaches nothing whatever this returns.
NOT_A_TICKET = frozenset({
    "UTF", "HTTP", "HTTPS", "ISO", "IEC", "IEEE", "RFC", "SHA", "MD", "AES",
    "RSA", "IPV", "TLS", "SSL", "ES", "PEP", "CVE", "JSR", "JEP", "OAUTH",
})

#: Subjects that match a fix pattern and are not about the product. Excluded by
#: name rather than by cleverness, because the list is short and a reader should
#: be able to see exactly what was skipped.
NOT_A_PRODUCT_FIX = re.compile(
    r"\bfix(?:e[sd])?\s+(?:typo|typos|lint|linting|formatting|whitespace|"
    r"indentation|spelling|comment|comments|test\s+name|import|imports)\b",
    re.IGNORECASE)

_SEPARATOR = "\x1e"
_FIELD = "\x1f"


@dataclass(frozen=True)
class Repair:
    """One commit classified as a repair, and what it touched."""

    sha: str
    subject: str
    committed_at: str
    is_fix: bool
    #: Which entry of `FIX_PATTERNS` matched, or "" when none did.
    fix_basis: str = ""
    #: Repo-relative, the same form `Anchor.file` stores.
    files: tuple[str, ...] = ()
    #: Tracker keys named in the subject. The edge target, never a Defect.
    tickets: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepairHistory:
    """Repairs in a window, and the window itself.

    The range is carried with the counts on purpose: a caller that reports
    "eleven fixes" without saying since when has reported a number, not a
    measurement.
    """

    since: str
    until: str
    repairs: tuple[Repair, ...] = ()
    #: Every commit read, so a fix rate has a denominator.
    commits_read: int = 0
    unavailable: str = ""

    def fixes_by_file(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for repair in self.repairs:
            if not repair.is_fix:
                continue
            for path in repair.files:
                counts[path] = counts.get(path, 0) + 1
        return counts


def classify(subject: str) -> tuple[bool, str]:
    """Whether a subject claims a repair, and which pattern decided.

    Order matters only for the basis it reports, not for the verdict: the first
    matching pattern is named so "why is this a fix" has one answer.
    """
    text = (subject or "").strip()
    if not text or NOT_A_PRODUCT_FIX.search(text):
        return False, ""
    for name, pattern in FIX_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return True, name
    return False, ""


def tickets_in(subject: str) -> tuple[str, ...]:
    """Tracker keys a subject names, in order and without duplicates.

    `NOT_A_TICKET` prefixes are dropped: they share a key's exact shape and are
    standards numbers, not reports.
    """
    found = TICKET_KEY.findall(subject or "")
    return tuple(dict.fromkeys(
        key for key in found
        if key.rsplit("-", 1)[0].upper() not in NOT_A_TICKET))


def read(repo: str | Path, since: str, until: str = "HEAD",
         limit: int = 2000) -> RepairHistory:
    """Repairs between two commits.

    `limit` bounds the read rather than the window: a range that turns out to
    span ten thousand commits is a range somebody chose badly, and truncating
    loudly is better than spending a minute in `git log`.
    """
    if not since:
        return RepairHistory(since, until, unavailable="no range given — a fix "
                                                       "count with no window is "
                                                       "not a measurement")

    command = [
        "git", "-C", str(repo), "log", f"{since}..{until}",
        f"--max-count={limit}", "--name-only", "--no-merges",
        f"--pretty=format:{_SEPARATOR}%H{_FIELD}%cI{_FIELD}%s",
    ]
    try:
        out = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return RepairHistory(since, until, unavailable=f"git could not be read: {e}")
    if out.returncode != 0:
        return RepairHistory(since, until,
                             unavailable=(out.stderr or "git failed").strip()[:200])

    repairs: list[Repair] = []
    read_count = 0
    for block in out.stdout.split(_SEPARATOR):
        if not block.strip():
            continue
        head, _, body = block.partition("\n")
        parts = head.split(_FIELD)
        if len(parts) != 3:
            continue
        sha, committed_at, subject = parts
        read_count += 1
        is_fix, basis = classify(subject)
        if not is_fix:
            continue
        files = tuple(line.strip() for line in body.splitlines() if line.strip())
        repairs.append(Repair(sha=sha.strip(), subject=subject.strip(),
                              committed_at=committed_at.strip(),
                              is_fix=True, fix_basis=basis, files=files,
                              tickets=tickets_in(subject)))

    return RepairHistory(since=since, until=until, repairs=tuple(repairs),
                         commits_read=read_count)
