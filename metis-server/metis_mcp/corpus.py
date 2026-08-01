"""
Corpus parser for the Métis dogfooding pilot.

Extracts real, ID-tagged content (REQ-METIS-*, CONST-*, DQ-*, AF-*, BS-*) from
the actual markdown documents this platform produced about itself, per the
Phase 0 dogfooding decision (master spec §18.3, revised by the cost-review
document). This is NOT synthetic test data -- it parses the real files.

Each extracted item becomes a node with:
  - id: the tag itself (e.g. "REQ-METIS-BM-01", "CONST-047")
  - kind: inferred from the tag prefix
  - text: the actual sentence/paragraph the tag appeared in
  - source_file: which document it came from
  - source_heading: the nearest preceding heading (for context/traceability)

No fabrication: if a tag has no clear surrounding sentence, it's skipped
rather than guessed at.
"""
import re
import glob
import os
from dataclasses import dataclass, field

TAG_PATTERN = re.compile(
    r'\b(REQ-METIS-[A-Z]+-\d+|CONST-\d+|DQ-\d+|AF-\d+|BS-\d+)\b'
)
HEADING_PATTERN = re.compile(r'^(#{1,4})\s+(.*)$')

KIND_MAP = {
    'REQ-METIS': 'Requirement',
    'CONST': 'ConstitutionRule',
    'DQ': 'DataQualityMetric',
    'AF': 'FoolProofRule',
    'BS': 'SecurityBoundaryRule',
}


def _infer_kind(tag: str) -> str:
    for prefix, kind in KIND_MAP.items():
        if tag.startswith(prefix):
            return kind
    return 'Unknown'


@dataclass
class GraphNode:
    id: str
    kind: str
    text: str
    source_file: str
    source_heading: str
    # populated in a second pass once all nodes are known
    references: list = field(default_factory=list)   # other tag IDs mentioned in this node's text
    referenced_by: list = field(default_factory=list)


def _split_into_units(text: str):
    """Split a markdown file into (heading, paragraph_text) units."""
    current_heading = "(document start)"
    buf = []
    units = []
    for line in text.splitlines():
        m = HEADING_PATTERN.match(line.strip())
        if m:
            if buf:
                units.append((current_heading, "\n".join(buf).strip()))
                buf = []
            current_heading = m.group(2).strip()
            continue
        buf.append(line)
    if buf:
        units.append((current_heading, "\n".join(buf).strip()))
    return units


DEFINITIONAL_PATTERN = re.compile(
    r'\*\*(REQ-METIS-[A-Z]+-\d+|CONST-\d+|DQ-\d+|AF-\d+|BS-\d+)[.:]'
)


def _is_definitional(tag: str, sentence: str) -> bool:
    """
    True if this sentence looks like the tag's actual definition (bolded,
    tag at/near the start, e.g. "**CONST-047.** Content reaching...") rather
    than an incidental citation elsewhere ("...per CONST-047, this..." or
    "(`CONST-047`)"). Citations are real and useful (they populate
    `references`/`referenced_by`), but they must not be mistaken for the
    definition itself -- that was a real bug caught while testing this
    parser: CONST-047 was initially canonicalized from a citation in
    metis-specification.md's EARS section rather than its actual defining
    paragraph in metis-standards-integration.md, purely because that file
    sorts first alphabetically. Fixed by requiring this stronger pattern
    before accepting a sentence as canonical.
    """
    m = DEFINITIONAL_PATTERN.search(sentence)
    return bool(m and m.group(1) == tag)


def parse_corpus(glob_pattern: str) -> dict:
    """
    Returns {tag_id: GraphNode}. Parses every .md file matching glob_pattern.

    Canonical-source selection: a tag's definition is the sentence matching
    the DEFINITIONAL_PATTERN (bolded "**TAG.**"-style), not merely the first
    sentence any file happens to mention it in. If two or more files contain
    a definitional-pattern match for the same tag, that's a genuine
    duplicate-definition conflict -- surfaced in `conflicts`, not silently
    resolved by picking whichever sorts first (the same discipline the
    Constitution's own CONST-046/049 require of the platform itself).
    """
    definitional_candidates: dict[str, list[GraphNode]] = {}
    citation_only: dict[str, GraphNode] = {}
    all_mentions: dict[str, list[set]] = {}  # tag -> list of co-mentioned-tag-sets, across EVERY sentence it appears in anywhere in the corpus, definitional or not

    files = sorted(glob.glob(glob_pattern))
    for filepath in files:
        fname = os.path.basename(filepath)
        with open(filepath, encoding='utf-8') as f:
            content = f.read()

        for heading, para in _split_into_units(content):
            tags_in_para = TAG_PATTERN.findall(para)
            if not tags_in_para:
                continue
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for tag in set(tags_in_para):
                owning_sentences = [s for s in sentences if tag in s]
                text = " ".join(owning_sentences).strip() if owning_sentences else para.strip()
                if not text:
                    continue

                # Record co-mentions for cross-reference building regardless of
                # whether this occurrence is definitional -- a citation from a
                # different document is a real edge (e.g. metis-specification.md
                # citing CONST-047 in its EARS section), not something to drop
                # just because it isn't that tag's canonical definition.
                for s in owning_sentences:
                    co_mentioned = set(TAG_PATTERN.findall(s)) - {tag}
                    if co_mentioned:
                        all_mentions.setdefault(tag, []).append(co_mentioned)

                node = GraphNode(
                    id=tag, kind=_infer_kind(tag), text=text[:800],
                    source_file=fname, source_heading=heading,
                )

                if any(_is_definitional(tag, s) for s in owning_sentences):
                    definitional_candidates.setdefault(tag, []).append(node)
                elif tag not in citation_only:
                    citation_only[tag] = node  # keep first citation as fallback only

    nodes: dict[str, GraphNode] = {}
    conflicts: dict[str, list[str]] = {}

    for tag, candidates in definitional_candidates.items():
        nodes[tag] = candidates[0]
        if len(candidates) > 1:
            conflicts[tag] = [c.source_file for c in candidates]

    for tag, node in citation_only.items():
        if tag not in nodes:
            nodes[tag] = node  # no definitional pattern found anywhere -- fall back, but this
                                 # itself is worth surfacing (see __main__ output below)

    # Cross-reference resolution over ALL mentions found anywhere in the corpus,
    # not just each node's own canonical text -- this is the fix: a citation
    # living in a different document than the tag's definition must still count.
    for tag, co_mention_sets in all_mentions.items():
        if tag not in nodes:
            continue
        for co_mentioned in co_mention_sets:
            for m in co_mentioned:
                if m in nodes and m not in nodes[tag].references:
                    nodes[tag].references.append(m)
                    if tag not in nodes[m].referenced_by:
                        nodes[m].referenced_by.append(tag)

    nodes['__conflicts__'] = conflicts  # not a real node; surfaced separately by callers
    return nodes


if __name__ == "__main__":
    import sys
    pattern = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/outputs/*.md"
    result = parse_corpus(pattern)
    conflicts = result.pop('__conflicts__')
    print(f"Parsed {len(result)} real tagged items from {pattern}")
    by_kind = {}
    for n in result.values():
        by_kind[n.kind] = by_kind.get(n.kind, 0) + 1
    for kind, count in sorted(by_kind.items()):
        print(f"  {kind}: {count}")
    if conflicts:
        print(f"\n{len(conflicts)} genuine duplicate-definition conflicts found (surfaced, not silently resolved):")
        for tag, files in conflicts.items():
            print(f"  {tag}: defined in {files}")
