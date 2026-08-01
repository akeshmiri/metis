"""
Minimal mock of Grafana's real alert/incident API shape
(connectors/metis-connector-grafana.json's mcp_config names the real
mcp-grafana tools: list_alert_rules, list_incidents). No real Grafana
instance is available in this environment -- same disclosed-mock pattern
as Phase 2's mock Athena Postgres (connectors/mock_athena_schema.sql),
not a different shape invented from scratch. Swap this server for a real
Grafana MCP client and grafana_connector.py's ingestion logic processes
real alerts/incidents identically -- this mock exists only to give that
real logic something real-shaped to poll.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

# Disclosed test data -- clearly not real production alerts, structurally
# matches what a real Grafana instance's API actually returns.
ALERTS = [
    {"uid": "alert-001", "title": "Neo4j bolt connection latency high", "state": "alerting",
     "labels": {"severity": "warning", "service": "metis-neo4j"}, "startsAt": "2026-07-29T10:00:00Z"},
    {"uid": "alert-002", "title": "Guardrail corpus runner CronJob missed schedule", "state": "normal",
     "labels": {"severity": "critical", "service": "metis-guardrail-corpus-runner"}, "startsAt": "2026-07-28T03:00:00Z"},
]
INCIDENTS = [
    {"incidentID": "inc-001", "title": "Mock Athena connection pool exhausted", "status": "resolved",
     "severity": "minor", "createdAt": "2026-07-27T14:22:00Z"},
]


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/alerts":
            self._send_json(ALERTS)
        elif self.path == "/api/incidents":
            self._send_json(INCIDENTS)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass


def main():
    import os
    port = int(os.environ.get("METIS_MOCK_GRAFANA_PORT", "8422"))
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
