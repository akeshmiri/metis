"""
Phase 5: a minimal, explicitly-scoped HTTP JSON API for the reviewer UI --
NOT the production Streamable HTTP MCP transport (that's Phase 6's OAuth2/
token-lifecycle work, sequenced after this on purpose). This exists only to
give docs/metis-review-queue-ui.html something real to fetch from, since
the MCP server itself is still stdio-only until Phase 6 lands. Built on
Python's stdlib http.server -- no new framework dependency for something
this narrow (2 endpoints).

GET  /api/quarantine  -> real items with lifecycle_state='Quarantine',
                          the exact query schema/metis-graph-03-single-
                          db-consolidation.cypher documents as replacing a
                          separate review-queue table.
POST /api/decision     -> per PLAN.md Phase 5's explicit instruction, the
                          write path (REQ-METIS-CPT-01) stays disabled here
                          -- same behavior/message as the metis_submit_episode
                          MCP tool. The decision is acknowledged, not
                          recorded, and the UI must show that honestly
                          rather than pretending persistence happened.
GET  /                 -> serves the review UI HTML itself, same-origin,
                          so the browser fetch above isn't a file://
                          cross-origin request (which browsers restrict
                          inconsistently).

GET  /api/demo-data/status -> current real demo node count (0 if none loaded).
POST /api/demo-data/load   -> one-click Demo Data load (demo_data/generate_demo_data.py,
                              ~12,000 nodes / ~11,000 relationships by default, real
                              EARS-checked and confidence-tiered, ~2s). Runs synchronously
                              -- fast enough at this scale that a background job would be
                              over-engineering for what's still a local dev tool.
POST /api/demo-data/wipe   -> removes only is_demo_data:true nodes, never real data.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from neo4j import GraphDatabase

from demo_data.generate_demo_data import generate, wipe_demo_data, Scale
from metis_mcp.config_manager import ConfigManager

UI_HTML_PATH = Path(__file__).resolve().parent.parent / "docs" / "metis-review-queue-ui.html"

QUARANTINE_QUERY = """
MATCH (n) WHERE n.lifecycle_state = 'Quarantine'
RETURN labels(n) AS labels, n.id AS id, n.name AS name, n.source_file AS source_file,
       n.lineno AS lineno, n.risk_tag AS risk_tag, n.triage_reason AS triage_reason,
       n.source_episode_id AS source_episode_id
ORDER BY coalesce(n.risk_tag, 'Unknown') DESC
"""


def _neo4j_creds() -> tuple[str, str, str]:
    config = ConfigManager()
    cfg = config.get_neo4j_config()
    password = os.environ.get(cfg.get("password_env", ""))
    if not password:
        raise ValueError(f"{cfg.get('password_env')} is not set.")
    return cfg["uri"], cfg["user"], password


class Handler(BaseHTTPRequestHandler):
    driver = None  # set in main()
    neo4j_creds = None  # set in main() -- (uri, user, password), for demo_data's standalone driver

    def _send_json(self, status: int, payload: dict | list):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/quarantine":
            with self.driver.session() as session:
                items = session.run(QUARANTINE_QUERY).data()
            self._send_json(200, items)
        elif self.path == "/api/demo-data/status":
            with self.driver.session() as session:
                count = session.run(
                    "MATCH (n {is_demo_data: true}) RETURN count(n) AS c"
                ).single()["c"]
            self._send_json(200, {"demo_nodes": count})
        elif self.path == "/":
            html = UI_HTML_PATH.read_text(encoding="utf-8")
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/demo-data/load":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length)) if length else {}
            scale = float(payload.get("scale", 1.0))
            try:
                summary = generate(*self.neo4j_creds, scale=Scale(factor=scale))
                self._send_json(200, {"ok": True, "summary": summary})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
        elif self.path == "/api/demo-data/wipe":
            try:
                result = wipe_demo_data(*self.neo4j_creds)
                self._send_json(200, {"ok": True, **result})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
        elif self.path == "/api/decision":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length)) if length else {}
            # REQ-METIS-CPT-01: write path disabled by default, regardless of
            # caller -- same honest behavior as the metis_submit_episode MCP
            # tool. Not a bug: this is the deliberate, non-silent choice
            # PLAN.md's Phase 5 instructed for this exact fork.
            self._send_json(200, {
                "accepted": False,
                "id": payload.get("id"),
                "decision_noted": payload.get("decision"),
                "reason": "Recording is disabled by default (REQ-METIS-CPT-01) until the "
                          "guardrail stack has a production track record. Your decision was "
                          "noted but NOT written to the graph -- this is a phase-gate, not a bug.",
            })
        else:
            self._send_json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}", file=sys.stderr)


def main():
    Handler.neo4j_creds = _neo4j_creds()
    Handler.driver = GraphDatabase.driver(Handler.neo4j_creds[0], auth=(Handler.neo4j_creds[1], Handler.neo4j_creds[2]))
    port = int(os.environ.get("METIS_REVIEW_API_PORT", "8420"))
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Review API server on http://127.0.0.1:{port} "
          f"(UI: http://127.0.0.1:{port}/, API: /api/quarantine, /api/decision, "
          f"/api/demo-data/status|load|wipe)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        Handler.driver.close()


if __name__ == "__main__":
    main()
