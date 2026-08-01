"""
Phase 7 (extended): the atlassian-prod connector
(connectors/metis-connector-atlassian-prod.json) -- real ingestion code
against connectors/mock_jira_server.py (a disclosed mock; no real
Atlassian instance is available in this environment). Lands all 4 of the
manifest's real source shapes: Jira Story/Epic -> Requirement, Jira
Bug/JSM Service Management request -> Defect, Confluence page ->
Document-sourced content (Episode-only, same real ontology gap flatfiles_
connector.py already documents -- "Document-sourced content" has no
corresponding label in the closed 49-label ontology), Compass
component/API metadata -> Service.

Per the manifest's real pitfall ("must use the changelog/history API, not
diff-by-polling... a naive poll-and-diff connector misattributes all
changes since last poll to 'now'"): t_recorded is each item's own real
`updated`/`version.when` field, never this connector's own fetch time.

A Story/Epic whose description isn't EARS-conformant is honestly NOT
submitted as a Requirement (structural_validation.py's real Layer 2 gate
would reject it outright for a missing ears_pattern) -- logged as skipped,
not force-fit or silently dropped.
"""
import sys
import urllib.request
import json

from guardrails.pipeline import submit_candidate
from metis_mcp.ears_checker import check_ears_conformance

SOURCE_CONNECTOR = "atlassian-prod"
CONFIDENCE = 0.95  # system_of_record per the manifest


def _fetch_json(base_url: str, path: str) -> dict:
    with urllib.request.urlopen(f"{base_url}{path}", timeout=10) as r:
        return json.loads(r.read())


def _fetch_issues(base_url: str) -> list[dict]:
    return _fetch_json(base_url, "/rest/api/2/search")["issues"]


def _land_confluence_pages(base_url: str, session, episode_id: str) -> int:
    """Confluence page -> Document-sourced content (§5.2): Episode-only,
    same real gap already disclosed in flatfiles_connector.py -- free-text
    structural extraction into typed entities is judgment/LLM work per
    §6.3, not deterministic Cognify, so no typed node is fabricated here.

    Episode id is version-independent (one Episode per real page, MERGE-
    updated on every run) -- schema-03's real (source_connector, unit_id)
    uniqueness constraint would reject a second episode for the same
    unit_id under a different (version-suffixed) id the moment a page's
    version changed; version is tracked as a property, not baked into the
    id, matching every other connector's "one episode per real external
    unit" convention (flatfiles' path-keyed episode, application_code's
    source_file-keyed episode)."""
    pages = _fetch_json(base_url, "/wiki/rest/api/content")["results"]
    landed = 0
    for page in pages:
        page_episode_id = f"atlassian-prod:confluence:{page['id']}"
        raw_content = page["body"]["storage"]["value"]

        def _write(tx, pid=page_episode_id, p=page, content=raw_content):
            tx.run(
                """
                MERGE (e:Episode {id: $id})
                SET e.source_connector = $connector, e.unit_id = $unit_id, e.job_id = $job_id,
                    e.t_recorded = datetime($updated), e.checkpoint_status = 'complete',
                    e.episode_type = 'DocumentIngested', e.confluence_page_id = $page_id,
                    e.confluence_version = $version, e.title = $title, e.raw_content = $content,
                    e.event_time_confidence = 'verified'
                """,
                id=pid, connector=SOURCE_CONNECTOR, unit_id=f"confluence:{p['id']}", job_id=episode_id,
                updated=p["version"]["when"], page_id=p["id"], version=p["version"]["number"],
                title=p["title"], content=content,
            )
        session.execute_write(_write)
        landed += 1
    return landed


def _land_jsm_requests(base_url: str, session, episode_id: str) -> int:
    """JSM Service Management request -> Defect -- identical target shape
    to a Jira Bug per the manifest, different source_shape/API."""
    requests_ = _fetch_json(base_url, "/rest/servicedeskapi/request")["values"]
    landed = 0
    for req in requests_:
        entity_id = f"atlassian-prod:{req['issueKey']}"
        result = submit_candidate(
            session, "Defect", {"id": entity_id, "source_episode_id": episode_id}, confidence=CONFIDENCE,
        )
        if result.written:
            session.execute_write(lambda tx, did=entity_id, r=req: tx.run(
                "MATCH (n:Defect {id: $id}) SET n.jira_key = $key, n.summary = $summary, "
                "n.description = $description, n.jira_updated = $updated, n.source = 'jsm'",
                id=did, key=r["issueKey"], summary=r["summary"],
                description=r["description"], updated=r["updated"],
            ).consume())
            landed += 1
    return landed


def _land_compass_components(base_url: str, session, episode_id: str) -> int:
    """Compass component/API metadata -> Service -- :Service is a real
    closed-ontology label (schema-01), unlike Confluence's target."""
    components = _fetch_json(base_url, "/gateway/api/compass/v1/components")["components"]
    landed = 0
    for comp in components:
        entity_id = f"atlassian-prod:compass:{comp['id']}"
        result = submit_candidate(
            session, "Service", {"id": entity_id, "source_episode_id": episode_id}, confidence=CONFIDENCE,
        )
        if result.written:
            session.execute_write(lambda tx, sid=entity_id, c=comp: tx.run(
                "MATCH (n:Service {id: $id}) SET n.name = $name, n.compass_component_id = $comp_id, "
                "n.repository_link = $repo_link, n.compass_updated = $updated",
                id=sid, name=c["name"], comp_id=c["id"],
                repo_link=c.get("links", {}).get("repository"), updated=c["updated"],
            ).consume())
            landed += 1
    return landed


def run(base_url: str, session, episode_id: str) -> dict:
    issues = _fetch_issues(base_url)
    landed = {"requirements": 0, "defects": 0, "skipped_non_ears": 0}

    for issue in issues:
        if issue["issue_type"] in ("Story", "Epic"):
            ears = check_ears_conformance(issue["description"])
            if not ears.conformant:
                landed["skipped_non_ears"] += 1
                continue
            entity_id = f"atlassian-prod:{issue['key']}"
            result = submit_candidate(
                session, "Requirement",
                {"id": entity_id, "source_episode_id": episode_id, "revision": 1,
                 "corroboration_count": 1, "ears_pattern": ears.pattern},
                confidence=CONFIDENCE,
            )
            if result.written:
                session.execute_write(lambda tx, rid=entity_id, i=issue: tx.run(
                    "MATCH (n:Requirement {id: $id}) SET n.jira_key = $key, n.summary = $summary, "
                    "n.jira_updated = $updated", id=rid, key=i["key"], summary=i["summary"], updated=i["updated"],
                ).consume())
                landed["requirements"] += 1

        elif issue["issue_type"] == "Bug":
            entity_id = f"atlassian-prod:{issue['key']}"
            result = submit_candidate(
                session, "Defect",
                {"id": entity_id, "source_episode_id": episode_id},
                confidence=CONFIDENCE,
            )
            if result.written:
                session.execute_write(lambda tx, did=entity_id, i=issue: tx.run(
                    "MATCH (n:Defect {id: $id}) SET n.jira_key = $key, n.summary = $summary, "
                    "n.description = $description, n.jira_updated = $updated",
                    id=did, key=i["key"], summary=i["summary"],
                    description=i["description"], updated=i["updated"],
                ).consume())
                landed["defects"] += 1

    landed["defects"] += _land_jsm_requests(base_url, session, episode_id)
    landed["confluence_pages"] = _land_confluence_pages(base_url, session, episode_id)
    landed["compass_services"] = _land_compass_components(base_url, session, episode_id)
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

    base_url = os.environ.get("METIS_MOCK_JIRA_URL", "http://127.0.0.1:8424")
    driver = GraphDatabase.driver(neo4j_cfg["uri"], auth=(neo4j_cfg["user"], password))
    try:
        with driver.session() as s:
            s.execute_write(lambda tx: tx.run(
                "MERGE (e:Episode {id: 'atlassian-prod:manual'}) "
                "SET e.t_recorded = datetime(), e.source_connector = 'atlassian-prod', e.job_id = 'manual'"
            ).consume())
            landed = run(base_url, s, "atlassian-prod:manual")
    finally:
        driver.close()
    print(f"Atlassian: {landed['requirements']} requirement(s), {landed['defects']} defect(s) "
          f"(Jira Bug + JSM), {landed['confluence_pages']} Confluence page(s) (Episode-only), "
          f"{landed['compass_services']} Compass Service(s) landed, "
          f"{landed['skipped_non_ears']} non-EARS-conformant issue(s) skipped.", file=sys.stderr)


if __name__ == "__main__":
    main()
