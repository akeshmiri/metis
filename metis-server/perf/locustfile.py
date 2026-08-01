"""
Real Locust performance test for review_api_server.py's real HTTP API
(Phase 5) -- this is the actual target the locust-performance connector
(connectors/metis-connector-locust-performance.json) is built to ingest:
a genuine load-test script, parsed deterministically (task name, target
path, weight), not synthetic content invented just to exercise a parser.

Run for real with: locust -f perf/locustfile.py --host http://127.0.0.1:8420
(review_api_server.py must be running -- see that file's docstring).
"""
from locust import HttpUser, task, between


class ReviewApiUser(HttpUser):
    wait_time = between(1, 3)
    host = "http://127.0.0.1:8420"

    @task(3)
    def list_quarantine_queue(self):
        self.client.get("/api/quarantine")

    @task(1)
    def submit_decision(self):
        self.client.post(
            "/api/decision",
            json={"id": "perf-test-item", "decision": "approved"},
        )
