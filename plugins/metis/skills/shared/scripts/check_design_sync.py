#!/usr/bin/env python3
"""
Ported from Atlas (`.agents/skills/test-designer/scripts/check_design_sync.py`).

**Worth taking because it is the one gate in Atlas that actually enforced
anything.** Atlas's declarative `validation_checks` are printed and never
evaluated, and its gate ledger records whatever status a caller asserts; this
script is deterministic, calls no model, touches no network, and exits 1 to hard
block. Métis already borrowed its hash-marker idea for specification write-back
(`metis_mcp/specgen/writeback.py`); this is the rest of it.

Atlas coupling was one join -- `.atlas/test-design/` -- now `.metis/`.
Deterministic sync check between the high-level and detailed test-design artifacts.

Run at Stage 08's Gate (see ``steps/08-design-synthesis.md``). This script performs NO LLM calls — it is a
cheap, regex/heading-based structural diff that keeps the two independently-authored documents honest:

    .metis/test-design/<scope-id>.overview.md   (Stage 06, high-level, Group IDs SG-01..N)
    .metis/test-design/<scope-id>.md            (Stage 08, detailed, scenarios tagged "Source Group: SG-xx")

Checks performed:
    1. Every Group ID declared in the overview's "Scenario Grouping" table is expanded by at least one
       "Source Group: SG-xx" reference in the detailed doc (no dropped groups).
    2. Every "Source Group: SG-xx" reference in the detailed doc points to a Group ID that actually exists in
       the overview (no invented/un-approved scope creep).
    3. The detailed doc embeds a ``<!-- overview-source-hash: <sha256> -->`` marker matching the overview's
       current content hash. If the marker is missing or stale, the overview was edited (or never linked) after
       the detailed doc was written.

Exit code 0 = pass. Exit code 1 = sync violation found (hard block — fix the minimal discrepancy, do not
regenerate the whole artifact).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

GROUP_ID_ROW_RE = re.compile(r"^\|\s*(SG-\d+)\s*\|", re.MULTILINE)
SOURCE_GROUP_REF_RE = re.compile(r"Source Group:[^\n]*?(SG-\d+)", re.IGNORECASE)
HASH_MARKER_RE = re.compile(r"<!--\s*overview-source-hash:\s*([0-9a-f]{64})\s*-->", re.IGNORECASE)


def _resolve_paths(scope_id: str, root: Path) -> tuple[Path, Path]:
    base = root / ".metis" / "test-design"
    return base / f"{scope_id}.overview.md", base / f"{scope_id}.md"


def _overview_source_hash(overview_text: str) -> str:
    return hashlib.sha256(overview_text.encode("utf-8")).hexdigest()


def check_design_sync(scope_id: str, root: Path) -> list[str]:
    """Return a list of violation messages (empty list means the docs are in sync)."""
    overview_path, detail_path = _resolve_paths(scope_id, root)
    violations: list[str] = []

    if not overview_path.exists():
        return [f"Missing high-level overview artifact: {overview_path}"]
    if not detail_path.exists():
        return [f"Missing detailed design artifact: {detail_path}"]

    overview_text = overview_path.read_text(encoding="utf-8")
    detail_text = detail_path.read_text(encoding="utf-8")

    overview_group_ids = set(GROUP_ID_ROW_RE.findall(overview_text))
    detail_group_refs = set(SOURCE_GROUP_REF_RE.findall(detail_text))

    dropped_groups = overview_group_ids - detail_group_refs
    invented_groups = detail_group_refs - overview_group_ids

    if dropped_groups:
        violations.append(
            "Group ID(s) declared in overview but never expanded in detailed doc: "
            + ", ".join(sorted(dropped_groups))
        )
    if invented_groups:
        violations.append(
            "Detailed doc references Group ID(s) not present in the confirmed overview "
            "(un-approved scope creep): " + ", ".join(sorted(invented_groups))
        )

    expected_hash = _overview_source_hash(overview_text)
    hash_match = HASH_MARKER_RE.search(detail_text)
    if hash_match is None:
        violations.append(
            "Detailed doc is missing the '<!-- overview-source-hash: ... -->' marker — "
            "add it to Specification Metadata when writing the detailed artifact."
        )
    elif hash_match.group(1).lower() != expected_hash.lower():
        violations.append(
            "Detailed doc's overview-source-hash marker is stale — the overview was edited after the "
            "detailed doc was written. Regenerate the marker (and re-verify Group ID coverage)."
        )

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-id", required=True, help="Scope id / ticket key, e.g. PROJ-100004")
    parser.add_argument(
        "--root",
        default=".",
        help="Project root containing the .metis/ directory (default: current directory)",
    )
    args = parser.parse_args()

    violations = check_design_sync(args.scope_id, Path(args.root))
    if violations:
        print("check_design_sync: FAIL")
        for v in violations:
            print(f"  - {v}")
        return 1

    print("check_design_sync: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
