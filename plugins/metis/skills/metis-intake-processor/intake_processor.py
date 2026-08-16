"""Jira -> UIF orchestrator and CLI entry point.

Scoped to Jira only. The Atlas original routed six sources; the others were
removed rather than left as dead branches, so `extract()` cannot be called with
a source this skill does not really support.

Two output modes, and the second is the point of the port:

  --out <path>   write the UIF JSON for inspection
  --land         land the UIF in the Métis graph as an Episode, after which
                 metis_mine_requirements derives Requirements and
                 AcceptanceCriteria from it

Landing requires the Métis server package on PYTHONPATH (metis-server/), since
it writes through metis_mcp/uif_intake.py rather than reimplementing the graph
write here.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extractors.jira_extractor import JiraExtractor
from validators import UIFValidator, validate_and_report


class IntakeProcessor:
    """Extract a Jira issue into a UIF object."""

    def __init__(self, output_root: Optional[str] = None):
        # Métis convention: artifacts live under the project's own .metis tree,
        # not Atlas's ~/.atlas/tmp/uif.
        self.output_root = Path(output_root) if output_root else Path.home() / ".metis" / "tmp" / "uif"
        self.validator = UIFValidator()

    def extract(self, source: str, **kwargs) -> Dict[str, Any]:
        if source != "jira":
            raise ValueError(
                f"Unsupported source: {source!r}. This skill processes Jira only — "
                "it does not silently accept a source it cannot extract."
            )
        return JiraExtractor().extract(key=kwargs["key"], raw_issue=kwargs.get("raw_issue"))

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
        # Imported lazily: the extract-and-inspect path must work without the
        # Métis server package present.
        from metis_mcp.config_manager import ConfigManager
        from metis_mcp.neo4j_graph_store import Neo4jGraphStore
        from metis_mcp.uif_intake import land_uif

        neo4j = ConfigManager().get_neo4j_config()
        store = Neo4jGraphStore(neo4j["uri"], neo4j["user"], neo4j["password"])
        with store.session() as session:
            result = land_uif(session, uif)
        print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
