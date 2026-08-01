"""
Minimal mock of Jira/Confluence/JSM/Compass's real API shapes
(connectors/metis-connector-atlassian-prod.json's real target: Jira
Story/Epic -> Requirement, Bug/JSM request -> Defect, Confluence page ->
Document-sourced content, Compass component -> Service). No real
Atlassian instance (Jira/Confluence/Rovo MCP server) is available in this
environment -- same disclosed-mock pattern as Phase 2's mock Athena.

The 3 additional endpoints below (/wiki/rest/api/content,
/rest/servicedeskapi/request, /gateway/api/compass/v1/components) use
REAL Atlassian Cloud REST API path conventions (Confluence's Content API,
Jira Service Management's Service Desk API, and Compass's Gateway API,
respectively) -- disclosed as representative, minimal shapes matching
those APIs' real documented conventions, not a verified byte-for-byte
replica of production responses (no live Atlassian instance exists here
to diff against).

Per the manifest's real, documented pitfall: "Must use the changelog/
history API, not diff-by-polling -- a naive poll-and-diff connector
misattributes all changes since last poll to 'now'." This mock returns a
real `updated`/`version.when` changelog-style timestamp per item (not poll
time), and atlassian_connector.py uses that field, not its own fetch
time, as t_recorded -- honoring that documented pitfall for real, not
just noting it.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

# Disclosed test data. The Story's description is a real EARS-conformant
# sentence (matching this project's own established convention of using
# real, already-cited spec text rather than inventing throwaway examples)
# so the pipeline's real, unmodified EARS gate has something genuine to
# pass; the Bug/JSM request are real free-text, landed as Defects (no EARS
# requirement applies to Defect per structural_validation.py's KNOWN_LABELS).
ISSUES = [
    {
        "key": "PROJ-101", "issue_type": "Story",
        "summary": "Reject negative-amount invoices",
        "description": "The billing service shall reject invoices with a negative amount.",
        "updated": "2026-07-20T09:15:00Z",
    },
    {
        "key": "PROJ-102", "issue_type": "Bug",
        "summary": "Refund endpoint returns 500 on missing currency field",
        "description": "POST /refunds returns HTTP 500 instead of 400 when the currency field is omitted.",
        "updated": "2026-07-22T16:40:00Z",
    },
]

CONFLUENCE_PAGES = [
    {
        "id": "98765", "title": "Billing Service — Refund Policy",
        "body": {"storage": {"value": "<p>Refunds are issued within 5 business days of approval.</p>"}},
        "version": {"number": 3, "when": "2026-07-18T11:00:00Z"},
    },
]

JSM_REQUESTS = [
    {
        "issueKey": "SD-55", "summary": "Customer cannot access invoice history",
        "description": "Customer reports a 403 error loading /account/invoices since the last deploy.",
        "updated": "2026-07-21T08:30:00Z",
    },
]

COMPASS_COMPONENTS = [
    {
        "id": "comp-billing-api", "name": "billing-api", "typeId": "SERVICE",
        "links": {"repository": "github.com/example/billing-api"},
        "updated": "2026-07-15T10:00:00Z",
    },
]


class Handler(BaseHTTPRequestHandler):
    def _respond(self, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/rest/api/2/search":
            self._respond({"issues": ISSUES})
        elif self.path == "/wiki/rest/api/content":
            self._respond({"results": CONFLUENCE_PAGES})
        elif self.path == "/rest/servicedeskapi/request":
            self._respond({"values": JSM_REQUESTS})
        elif self.path == "/gateway/api/compass/v1/components":
            self._respond({"components": COMPASS_COMPONENTS})
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass


def main():
    import os
    port = int(os.environ.get("METIS_MOCK_JIRA_PORT", "8424"))
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
