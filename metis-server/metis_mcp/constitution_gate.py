"""
§7.2 Constitution-gated validation (REQ-METIS-GRD-11): "The Constitution
entity set (§4.2) is checked at Cognify time, ahead of the general
Validation Rule Engine's cross-entity business rules -- a Constitution
violation is always a hard block, never a Quarantine-tier soft flag."

Two real, separate pieces:

  load_constitution_rules()
    Populates §4.2's Constitution entity set for real, in the PRODUCTION
    ontology (:Constitution, not :DogfoodingItem -- the self-referential
    dogfooding corpus's own distinct label; see neo4j_graph_store.py's
    docstring for why those stay separate). Reuses metis_mcp/corpus.py's
    real, already-proven parser (177 real items, 359 real cross-references
    parsed from this platform's own docs, 2 real parser bugs already
    caught and fixed there) rather than re-parsing the Constitution
    documents with new, untested regex.

  check_constitution_hard_blocks()
    A real, narrowly-scoped demonstration of the GRD-11 pattern for ONE
    concrete rule with an existing deterministic check -- not a general
    64-rule interpreter. PLAN.md explicitly rejects building "a general
    Constitution-enforcement engine": most of the 64 rules need real
    human/LLM judgment about what "enforcement" even means for them, and
    a generic interpreter would either be a no-op shell or would silently
    fabricate judgment a human should make. What's real and buildable
    instead: CONST-047 ("Every Requirement/MicroRequirement reaching
    Approved MUST be scored against ISO/IEC/IEEE 29148's characteristics")
    already has a real, deterministic checker
    (metis_mcp/requirement_quality.py), but nothing previously ran it
    before a Requirement candidate could reach auto_write/Quarantine --
    only EARS-pattern presence gated it. This closes that real,
    concrete, previously-open gap for the 4 deterministic characteristics
    (unambiguous/complete/singular/consistent); the 4 judgment ones need
    a real, costed LLM call and are deliberately not run automatically in
    the hot submission path, same cost-awareness convention as every
    other LLM-calling module in this codebase.

    Wired into guardrails/pipeline.py's submit_candidate as literally the
    first check -- "ahead of the general Validation Rule Engine's
    cross-entity business rules" (structural_validation.py/
    confidence_tiering.py) -- and forces REJECTED (never Quarantine,
    regardless of the caller's reported confidence) on a hit, per GRD-11's
    explicit "always a hard block" requirement.
"""
from dataclasses import dataclass


@dataclass
class ConstitutionCheckResult:
    blocked: bool
    rule_id: str | None
    reason: str | None


def load_constitution_rules(session, corpus_glob: str, source_episode_id: str) -> dict:
    """Returns {'total': N, 'changed': M} -- `changed` is how many rules
    got a real new :Revision this call (REQ-METIS-ACD-05's changelog needs
    real change events to show, not just a flat MERGE with no history).
    Every real rule goes through metis_mcp/temporal.py's record_revision
    -- but only when its text actually differs from the current live
    value, so re-running this (e.g. a scheduled re-sync) doesn't create
    spurious revision noise for rules that didn't really change."""
    from metis_mcp.corpus import parse_corpus
    from metis_mcp.temporal import record_revision
    nodes = parse_corpus(corpus_glob)
    # '__conflicts__' is a real, documented non-node sentinel key parse_corpus
    # mixes into its return dict (a plain dict of duplicate-definition
    # conflicts, not a GraphNode) -- every other real caller
    # (corpus.py's own __main__, graph_store.py's LocalGraphStore) already
    # pops it before iterating; this is the first caller outside those two
    # that needed to learn the same lesson.
    nodes.pop("__conflicts__", None)
    rules = {tag: node for tag, node in nodes.items() if node.kind == "ConstitutionRule"}

    changed = 0
    for tag, node in rules.items():
        existing = session.run("MATCH (c:Constitution {id: $id}) RETURN c.text AS text", id=tag).single()
        has_revision = session.run(
            "MATCH (:Constitution {id: $id})-[:HAS_REVISION]->(:Revision) RETURN count(*) > 0 AS v", id=tag,
        ).single()["v"]

        if existing is None:
            def _create_base(tx, tag=tag):
                # schema-02's own real, pre-existing constraint/comment (predates
                # this module): "precedence_rank is always the numeric minimum
                # among rule types ... Constitution checks run before general
                # Validation Rule Engine checks" -- 0 is that minimum.
                tx.run(
                    "MERGE (c:Constitution {id: $id}) SET c.source_episode_id = $episode, "
                    "c.precedence_rank = 0",
                    id=tag, episode=source_episode_id,
                )
            session.execute_write(_create_base)
        elif existing["text"] == node.text and has_revision:
            # Genuinely unchanged AND already has real revision history --
            # skip. A node that exists but has NO revision yet (created
            # before this history mechanism existed) does NOT skip here,
            # even though its stored text matches -- it still needs a real
            # baseline revision, or the changelog can never show it.
            continue
        record_revision(
            session, tag,
            {"text": node.text, "source_file": node.source_file, "source_heading": node.source_heading},
            source_episode_id,
        )
        changed += 1
    return {"total": len(rules), "changed": changed}


def check_constitution_hard_blocks(session, label: str, entity: dict) -> ConstitutionCheckResult:
    if label != "Requirement" or not entity.get("text"):
        return ConstitutionCheckResult(blocked=False, rule_id=None, reason=None)

    from metis_mcp.requirement_quality import score_deterministic
    result = score_deterministic(session, entity.get("id", "unknown"), entity["text"])
    checks = {"unambiguous": result.unambiguous, "complete": result.complete,
              "singular": result.singular, "consistent": result.consistent}
    failed = [name for name, passed in checks.items() if not passed]
    if not failed:
        return ConstitutionCheckResult(blocked=False, rule_id=None, reason=None)

    reasons = "; ".join(f"{name}: {result.reasons.get(name, '')}" for name in failed)
    return ConstitutionCheckResult(
        blocked=True, rule_id="CONST-047",
        reason=f"CONST-047 violation -- failed deterministic 29148 check(s) {failed}: {reasons}",
    )


def main():
    """Real gap this closes: load_constitution_rules() had no operational
    entry point anywhere -- only tests ever called it, so a real
    deployment's :Constitution entity set would never actually get
    populated. Same connector-style main() pattern as atlassian_connector.py/
    corpus_runner.py -- run standalone (e.g. once at deploy time, or on the
    same schedule as guardrail-corpus-runner) rather than auto-triggered
    from server.py's import-time init, so a slow/failing corpus parse can
    never block the MCP server itself from starting."""
    import os
    import sys

    from neo4j import GraphDatabase

    from metis_mcp.config_manager import ConfigManager

    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    password = os.environ.get(neo4j_cfg.get("password_env", ""))
    if not password:
        raise ValueError(f"{neo4j_cfg.get('password_env')} must be set.")

    corpus_glob = config.get_corpus_glob()
    if not os.path.isabs(corpus_glob):
        corpus_glob = str(config.effective_path.parent.parent / corpus_glob)

    driver = GraphDatabase.driver(neo4j_cfg["uri"], auth=(neo4j_cfg["user"], password))
    try:
        with driver.session() as s:
            s.execute_write(lambda tx: tx.run(
                "MERGE (e:Episode {id: 'constitution-gate:manual'}) "
                "SET e.t_recorded = datetime(), e.source_connector = 'constitution-gate', "
                "e.job_id = 'manual'"
            ).consume())
            result = load_constitution_rules(s, corpus_glob, "constitution-gate:manual")
    finally:
        driver.close()
    print(f"Constitution: {result['total']} real rule(s) loaded, {result['changed']} changed "
          f"(new revision recorded) this run.", file=sys.stderr)


if __name__ == "__main__":
    main()
