"""Source -> UIF orchestrator and CLI entry point.

**All six sources, ported from Atlas.** This was Jira-only, and the docstring was
honest about it -- the other five were "removed rather than left as dead
branches, so `extract()` cannot be called with a source this skill does not
really support." Right while they were absent; wrong to stay that way, because
Confluence, Swagger, Zephyr Scale, code and database are exactly the sources
Requirements have to be built from, and reaching into another project for them is
the coupling this port removes.

The refusal below is kept and still real: an unknown source raises rather than
silently producing an empty UIF.

One output mode, and one that refuses:

  --out <path>   write the UIF JSON for inspection -- this is the deliverable
  --land         REFUSES. The UIF->Episode path went through
                 metis_mcp/uif_intake.py, which was removed with the v1 engine.
                 The flag is kept so the refusal is explicit: a caller who asks
                 to land a source is told it did not happen, rather than being
                 left to infer it from an empty graph.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extractors import (
    CodeExtractor,
    ConfluenceExtractor,
    DatabaseExtractor,
    JiraExtractor,
    ScaleExtractor,
    SwaggerExtractor,
)
from validators import UIFValidator, validate_and_report


class IntakeProcessor:
    """Extract a real source into a UIF object."""

    def __init__(self, output_root: Optional[str] = None):
        # Métis convention: artifacts live under the project's own .metis tree,
        # not Atlas's ~/.atlas/tmp/uif.
        self.output_root = Path(output_root) if output_root else Path.home() / ".metis" / "tmp" / "uif"
        self.validator = UIFValidator()

    # One entry per extractor that really exists. A source is routable only
    # because something implements it -- the registry is the single list, so a
    # source cannot be advertised here and missing from `extractors/`.
    EXTRACTORS = {
        "jira": JiraExtractor,
        "confluence": ConfluenceExtractor,
        "swagger": SwaggerExtractor,
        "scale": ScaleExtractor,
        "code": CodeExtractor,
        "database": DatabaseExtractor,
    }

    def extract(self, source: str, **kwargs) -> Dict[str, Any]:
        extractor = self.EXTRACTORS.get(source)
        if extractor is None:
            raise ValueError(
                f"Unsupported source: {source!r}. Supported: "
                f"{', '.join(sorted(self.EXTRACTORS))} — this skill does not "
                f"silently accept a source it cannot extract."
            )
        return extractor().extract(**kwargs)

    def write(self, uif: Dict[str, Any], path: Optional[str] = None) -> Path:
        scope = uif.get("scope", {})
        target = Path(path) if path else self.output_root / "jira" / f"{scope.get('primary_id', 'unknown')}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(uif, indent=2), encoding="utf-8")
        return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Extract a Jira issue to UIF, optionally landing it in Métis.")
    parser.add_argument("key", help="Jira issue key, e.g. ACME-100001")
    parser.add_argument("--raw", help="Path to a cached Jira issue JSON (offline; no network call)")
    parser.add_argument("--out", help="Write the UIF JSON here")
    parser.add_argument("--land", action="store_true",
                        help="Land the UIF in the Métis graph as an Episode (requires metis-server on PYTHONPATH)")
    args = parser.parse_args(argv)

    raw_issue = json.loads(Path(args.raw).read_text(encoding="utf-8")) if args.raw else None
    processor = IntakeProcessor()
    uif = processor.extract("jira", key=args.key, raw_issue=raw_issue)

    if not validate_and_report(uif, f"UIF for {args.key}"):
        return 1

    if args.out or not args.land:
        print(f"wrote {processor.write(uif, args.out)}")

    if args.land:
        # Landing goes through the gated CLI, never from here. This script has
        # no graph credentials and no business acquiring any: `metis_mcp` owns
        # the ontology gate, the Quarantine default (S-4) and the unmatched
        # reporting, and a second writer would be a second set of rules.
        path = args.out or processor.write(uif, None)
        print(
            f"\nExtraction complete. Land it with the gated CLI:\n"
            f"  python3 -m metis_mcp.mbt.cli intake land {path} \\\n"
            f"      --job-id <run> --author <you>\n"
            f"\nIt creates an Episode (the ingestion) and a JiraItem (the "
            f"artefact), and\na Requirement only if the text is EARS-conformant "
            f"— free prose is reported\nrather than guessed at (S-13). Claimed "
            f"acceptance criteria are NOT trusted.",
            file=sys.stderr)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
