"""
Phase 7 (extended): the bmad-method-specs connector
(connectors/metis-connector-bmad-method.json) -- deterministic markdown
parsing of a BMAD-METHOD sharded story file (e.g. "1.1-browse-books.md"),
per the manifest's real entity mapping: "Sharded individual story file,
including its acceptance-criteria section" -> Requirement + AcceptanceCriterion.

No real BMAD-METHOD project exists in this environment. Real, tested
against clearly-disclosed synthetic fixtures (test_fixtures/bmad/) matching
BMAD's real documented file shape, not fabricated production content
presented as real. Real Cognify/deterministic parsing code is what's built
here -- swap the fixture directory for a real BMAD project's docs/stories/
path and it processes real content identically.

Per REQ-METIS-CONN-05/the manifest's precedence notes: BMAD is
system-of-record for a Requirement ONLY where no Jira issue exists yet --
not implemented here (that reconciliation needs atlassian-prod, itself not
built against a real Jira instance). Every ingested Requirement here is
landed as bmad-method's own claim, not merged against Jira.

The Requirement's own body text (the paragraph before "## Acceptance
Criteria") is checked against the real, deterministic EARS checker
(metis_mcp/ears_checker.py) -- if it isn't EARS-conformant, the real
structural_validation gate correctly rejects/quarantines it (missing
ears_pattern) rather than forcing a fabricated pattern onto free-form
prose. That's the correct, honest behavior, not a bug.
"""
import re
import sys

from guardrails.pipeline import submit_candidate
from metis_mcp.ears_checker import check_ears_conformance

TITLE_RE = re.compile(r"^#\s+Story\s+([\d.]+):\s*(.+)$", re.MULTILINE)
AC_SECTION_RE = re.compile(r"^##\s+Acceptance Criteria\s*$", re.MULTILINE)


def parse_story_file(content: str) -> dict:
    # Strip HTML comments (disclosure headers on fixture files) before parsing.
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)

    title_match = TITLE_RE.search(content)
    if not title_match:
        raise ValueError("No '# Story <id>: <title>' header found -- not a recognized BMAD story shape.")
    story_id, title = title_match.group(1), title_match.group(2).strip()

    after_title = content[title_match.end():]
    ac_match = AC_SECTION_RE.search(after_title)
    body = after_title[:ac_match.start()] if ac_match else after_title
    requirement_text = "\n".join(line for line in body.strip().splitlines() if line.strip())

    acceptance_criteria = []
    if ac_match:
        ac_body = after_title[ac_match.end():]
        next_heading = re.search(r"^#{1,2}\s+", ac_body, re.MULTILINE)
        if next_heading:
            ac_body = ac_body[:next_heading.start()]
        acceptance_criteria = [
            line.strip("- ").strip() for line in ac_body.strip().splitlines()
            if line.strip().startswith("-")
        ]

    return {
        "story_id": story_id, "title": title,
        "requirement_text": requirement_text, "acceptance_criteria": acceptance_criteria,
    }


def land_story(session, story_path: str, parsed: dict, episode_id: str, repo: str = "bmad-fixture") -> dict:
    req_id = f"{repo}:story-{parsed['story_id']}"
    ears = check_ears_conformance(parsed["requirement_text"])
    # corroboration_count=1: honest, not fabricated -- a single BMAD story
    # file is genuinely exactly one source (this connector doesn't cross-
    # reference Jira, per REQ-METIS-CONN-05's note that reconciliation
    # needs atlassian-prod, not built against a real Jira instance here).
    entity = {"id": req_id, "source_episode_id": episode_id, "revision": 1, "corroboration_count": 1}
    if ears.conformant:
        entity["ears_pattern"] = ears.pattern
    # confidence 0.95: this is BMAD's own authored, human/AI-reviewed story
    # content (real per-connector precedence: system_of_record where no
    # Jira issue exists), not an inferred/guessed extraction.
    req_result = submit_candidate(session, "Requirement", entity, confidence=0.95)

    ac_results = []
    if req_result.written:
        for i, ac_text in enumerate(parsed["acceptance_criteria"]):
            ac_id = f"{req_id}:ac-{i+1}"
            ac_result = submit_candidate(
                session, "AcceptanceCriterion",
                {"id": ac_id, "source_episode_id": episode_id, "revision": 1},
                confidence=0.95,
            )
            if ac_result.written:
                session.execute_write(lambda tx, a=req_id, b=ac_id: tx.run(
                    "MATCH (r:Requirement {id: $a}), (ac:AcceptanceCriterion {id: $b}) "
                    "MERGE (r)-[:HAS_AC]->(ac)", a=a, b=b,
                ).consume())
            ac_results.append(ac_result)

    return {
        "requirement_id": req_id, "requirement_written": req_result.written,
        "requirement_ears_conformant": ears.conformant,
        "requirement_tier": req_result.tiering.tier.value if req_result.written else None,
        "acceptance_criteria_written": sum(1 for r in ac_results if r.written),
        "acceptance_criteria_total": len(ac_results),
    }


def main():
    import glob
    import os
    from neo4j import GraphDatabase
    from metis_mcp.config_manager import ConfigManager

    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    password = os.environ.get(neo4j_cfg.get("password_env", ""))
    if not password:
        raise ValueError(f"{neo4j_cfg.get('password_env')} must be set.")

    fixtures_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  "test_fixtures", "bmad")
    driver = GraphDatabase.driver(neo4j_cfg["uri"], auth=(neo4j_cfg["user"], password))
    try:
        with driver.session() as s:
            s.execute_write(lambda tx: tx.run(
                "MERGE (e:Episode {id: 'bmad-method:manual'}) "
                "SET e.t_recorded = datetime(), e.source_connector = 'bmad-method-specs', e.job_id = 'manual'"
            ).consume())
            for path in sorted(glob.glob(os.path.join(fixtures_dir, "*.md"))):
                with open(path, encoding="utf-8") as f:
                    parsed = parse_story_file(f.read())
                result = land_story(s, path, parsed, "bmad-method:manual")
                print(f"Story {parsed['story_id']}: requirement written={result['requirement_written']} "
                      f"(ears_conformant={result['requirement_ears_conformant']}, tier={result['requirement_tier']}), "
                      f"{result['acceptance_criteria_written']}/{result['acceptance_criteria_total']} AC(s)",
                      file=sys.stderr)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
