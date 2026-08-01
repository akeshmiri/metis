"""
script/build_site.py -- generation logic ONLY, no content decisions.
Thin CLI wrapper over the real implementation, metis_mcp/site_renderer.py's
render_site.
"""
import os
import sys

from neo4j import GraphDatabase

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))

from metis_mcp.config_manager import ConfigManager
from metis_mcp.site_renderer import render_site


def main():
    if len(sys.argv) < 2:
        print("Usage: build_site.py <output_dir>", file=sys.stderr)
        sys.exit(1)
    output_dir = sys.argv[1]

    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    password = os.environ.get(neo4j_cfg.get("password_env", ""))
    driver = None
    session = None
    if password:
        driver = GraphDatabase.driver(neo4j_cfg["uri"], auth=(neo4j_cfg["user"], password))
        session = driver.session()
    try:
        result = render_site(output_dir, session=session)
    finally:
        if driver:
            driver.close()

    print(f"Site written: {result['output_dir']} ({len(result['academy_pages'])} Academy page(s) + index).",
          file=sys.stderr)


if __name__ == "__main__":
    main()
