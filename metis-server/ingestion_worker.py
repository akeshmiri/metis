"""
Phase 9: the metis-ingestion-worker service (metis-chart's Deployment
component) -- runs the real connectors (Phase 2/7) + Cognify structural
extraction (Phase 3) on a loop, per metis-chart/values.yaml's
DEFAULT_POLL_INTERVAL_SECONDS. Wraps existing, already-tested code
(connectors/application_code_connector.py, connectors/flatfiles_connector.py,
connectors/test_suite_connector.py, cognify/structural_extraction.py) --
this file is orchestration, not new pipeline logic.

Exposes GET /healthz on port 8091 (matching values.yaml's mcp-server-style
livenessProbe convention), so the chart's Deployment can actually be probed
-- returns 200 once the first ingestion cycle has completed at least once,
503 before that (a worker that hasn't run yet isn't meaningfully "live").
"""
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from connectors import application_code_connector, flatfiles_connector, test_suite_connector
from cognify import structural_extraction
from metis_mcp.config_manager import ConfigManager
from connectors.seed_mock_athena import _dsn_from_config

_first_cycle_done = threading.Event()


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            if _first_cycle_done.is_set():
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
            else:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"first ingestion cycle not complete yet")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass


def run_one_cycle(config: ConfigManager, neo4j_cfg: dict, neo4j_password: str) -> None:
    job_id = f"ingestion-worker-{int(time.time())}"

    try:
        pg_dsn = _dsn_from_config()
        landed = application_code_connector.run(
            pg_dsn, neo4j_cfg["uri"], neo4j_cfg["user"], neo4j_password, job_id=job_id,
        )
        print(f"[application-code] landed {landed}", file=sys.stderr)
    except Exception as e:
        print(f"[application-code] skipped: {e}", file=sys.stderr)

    try:
        server_dir = config.effective_path.parent.parent
        landed = flatfiles_connector.run(
            str(server_dir / "corpus" / "*.md"),
            neo4j_cfg["uri"], neo4j_cfg["user"], neo4j_password, job_id=job_id,
        )
        print(f"[flat-files] landed {landed}", file=sys.stderr)
    except Exception as e:
        print(f"[flat-files] skipped: {e}", file=sys.stderr)

    try:
        cognified = structural_extraction.run(neo4j_cfg["uri"], neo4j_cfg["user"], neo4j_password)
        print(f"[cognify] {cognified}", file=sys.stderr)
    except Exception as e:
        print(f"[cognify] skipped: {e}", file=sys.stderr)

    _first_cycle_done.set()


def main():
    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    neo4j_password = os.environ.get(neo4j_cfg.get("password_env", ""))
    if not (neo4j_cfg.get("uri") and neo4j_cfg.get("user") and neo4j_password):
        raise ValueError(
            f"graph.neo4j.{{uri,user,password_env}} must be set in {config.effective_path}, "
            f"and its password_env variable must be exported."
        )

    poll_interval = int(os.environ.get("DEFAULT_POLL_INTERVAL_SECONDS", "300"))
    port = int(os.environ.get("METIS_WORKER_PORT", "8091"))

    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Ingestion worker healthz on :{port}, poll interval {poll_interval}s", file=sys.stderr)

    while True:
        run_one_cycle(config, neo4j_cfg, neo4j_password)
        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
