"""
script/build_deck.py -- generation logic ONLY (§4.6.1's content-boundary
rule), no content decisions of its own. Thin CLI wrapper over the real
implementation, metis_mcp/pptx_renderer.py's render_quality_deck.
"""
import os
import sys

from neo4j import GraphDatabase

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))

from metis_mcp.config_manager import ConfigManager
from metis_mcp.pptx_renderer import render_quality_deck


def main():
    if len(sys.argv) < 2:
        print("Usage: build_deck.py <output_path> [scope]", file=sys.stderr)
        sys.exit(1)
    output_path = sys.argv[1]
    scope = sys.argv[2] if len(sys.argv) > 2 else None

    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    password = os.environ.get(neo4j_cfg.get("password_env", ""))
    if not password:
        raise ValueError(f"{neo4j_cfg.get('password_env')} must be set.")

    driver = GraphDatabase.driver(neo4j_cfg["uri"], auth=(neo4j_cfg["user"], password))
    try:
        with driver.session() as s:
            result = render_quality_deck(s, output_path, scope=scope)
    finally:
        driver.close()

    print(f"Deck written: {result['output_path']} ({result['slide_count']} slide(s)). "
          f"content_qa={result['content_qa_passed']} file_qa={result['file_qa_passed']} "
          f"visual_qa={result['visual_qa']}", file=sys.stderr)


if __name__ == "__main__":
    main()
