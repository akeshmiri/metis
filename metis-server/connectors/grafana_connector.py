"""
Phase 7 (extended): the grafana-metrics connector
(connectors/metis-connector-grafana.json) -- real polling/ingestion code
against connectors/mock_grafana_server.py (a disclosed mock; no real
Grafana instance is available in this environment). Lands Alert/Incident
entities per the manifest's real entity mapping. system_of_record
precedence (per the manifest), so these are landed at high confidence --
Grafana's own alert/incident timestamps are the real source of truth for
these entity types, not an inference.
"""
import sys
import urllib.request
import json

from guardrails.pipeline import submit_candidate

SOURCE_CONNECTOR = "grafana-metrics"
CONFIDENCE = 0.95  # system_of_record per the manifest -- Grafana's own event-sourced data


def _fetch(base_url: str, path: str) -> list[dict]:
    with urllib.request.urlopen(f"{base_url}{path}", timeout=10) as r:
        return json.loads(r.read())


def run(base_url: str, session, episode_id: str) -> dict:
    alerts = _fetch(base_url, "/api/alerts")
    incidents = _fetch(base_url, "/api/incidents")

    landed = {"alerts": 0, "incidents": 0}
    for a in alerts:
        entity_id = f"grafana:alert:{a['uid']}"
        result = submit_candidate(
            session, "Alert",
            {"id": entity_id, "source_episode_id": episode_id},
            confidence=CONFIDENCE,
        )
        if result.written:
            session.execute_write(lambda tx, aid=entity_id, a=a: tx.run(
                "MATCH (n:Alert {id: $id}) SET n.title = $title, n.state = $state, "
                "n.severity = $severity, n.started_at = $started_at",
                id=aid, title=a["title"], state=a["state"],
                severity=a["labels"].get("severity"), started_at=a["startsAt"],
            ).consume())
            landed["alerts"] += 1

    for i in incidents:
        entity_id = f"grafana:incident:{i['incidentID']}"
        result = submit_candidate(
            session, "Incident",
            {"id": entity_id, "source_episode_id": episode_id},
            confidence=CONFIDENCE,
        )
        if result.written:
            session.execute_write(lambda tx, iid=entity_id, i=i: tx.run(
                "MATCH (n:Incident {id: $id}) SET n.title = $title, n.status = $status, "
                "n.severity = $severity, n.created_at = $created_at",
                id=iid, title=i["title"], status=i["status"],
                severity=i["severity"], created_at=i["createdAt"],
            ).consume())
            landed["incidents"] += 1

    return landed


def main():
    import os
    from neo4j import GraphDatabase
    from metis_mcp.config_manager import ConfigManager

    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    password = os.environ.get(neo4j_cfg.get("password_env", ""))
    if not password:
        raise ValueError(f"{neo4j_cfg.get('password_env')} must be set.")

    base_url = os.environ.get("METIS_MOCK_GRAFANA_URL", "http://127.0.0.1:8422")
    driver = GraphDatabase.driver(neo4j_cfg["uri"], auth=(neo4j_cfg["user"], password))
    try:
        with driver.session() as s:
            s.execute_write(lambda tx: tx.run(
                "MERGE (e:Episode {id: 'grafana-metrics:manual'}) "
                "SET e.t_recorded = datetime(), e.source_connector = 'grafana-metrics', e.job_id = 'manual'"
            ).consume())
            landed = run(base_url, s, "grafana-metrics:manual")
    finally:
        driver.close()
    print(f"Grafana: {landed['alerts']} alert(s), {landed['incidents']} incident(s) landed.", file=sys.stderr)


if __name__ == "__main__":
    main()
