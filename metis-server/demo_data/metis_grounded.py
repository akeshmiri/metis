"""
The "grounded" layer of the demo dataset: real Métis project content, not
fictional-company synthesis. Adds ~18 real Goals (one per REQ-METIS-*
subsystem prefix actually found in this repo's own corpus/*.md) and, for
every one of the 75 real REQ-METIS-* tags found there, one genuinely
EARS-conformant Requirement.

Why paraphrased rather than the raw corpus sentence: metis_mcp/
ears_checker.py's conformance check is a strict literal regex ("The X
shall Y.", etc.) -- real corpus prose (often mid-table-row text, or
multi-sentence paragraphs) essentially never matches it verbatim. Every
GROUNDED_PARAPHRASES entry below was hand-written by reading that tag's
real sentence (via the same metis_mcp.corpus.parse_corpus() this module
calls at generation time, not a hardcoded copy) and phrasing its actual
substantive content into one of the five real patterns -- curated, not
fabricated: each one is traceable back to a real tag, real source_file,
and real source_heading, carried as `derived_from`/`source_file`/
`source_heading` properties on the written Requirement. Every single one
is still re-validated through the real, unmodified `check_ears_conformance`
and `ConfidenceTiering.evaluate()` at generation time -- same no-force-tag
discipline as the fully-synthetic layer, just applied to real content.

IMPLEMENTS edges point at the REAL, already-existing (non-demo) Method
pool this repo's own earlier Cognify run already populated -- matched by
real module filename per subsystem (see MODULE_KEYWORDS). Some prefixes
(RES, MTX, ING, SKL, CG) have no real code in that pool -- this is not a
bug to paper over: it matches this project's own documented "genuinely
open items" (REQ-METIS-RES-01..04, REQ-METIS-MTX-01..03 are explicitly
not-yet-built per CLAUDE.md). Those Requirements are written with no
IMPLEMENTS edge, honestly, rather than a fabricated match.
"""
import glob
import os
import random

from metis_mcp.confidence_tiering import ConfidenceTiering
from metis_mcp.corpus import parse_corpus
from metis_mcp.ears_checker import check_ears_conformance

GROUNDED_GOALS = {
    "ACD": "Academy, Site & PPTX Reporting",
    "ARCH": "Single-Database Architecture",
    "BM": "Behavior Model Determinism & Corroboration",
    "CG": "Code Graph Archaeology",
    "CONN": "Connector Architecture & Manifests",
    "COST": "Cost Governance & RPI Calibration",
    "CPT": "Copilot & Multi-Client Integration",
    "DQ": "Data Quality Metrics",
    "GRD": "Guardrail Confidence-Tiering & Constitution Gate",
    "ING": "Data Ingestion Pipeline",
    "MEM": "Memory & Hybrid Retrieval",
    "MTX": "Athena Metrics Integration",
    "ONT": "Requirements Ontology & EARS Conformance",
    "PG": "Pyramid Gap Coverage Check",
    "RES": "Connector Resumability",
    "SKL": "Skill Router",
    "SLD": "Deck (PPTX) Rendering",
    "TMP": "Temporal Versioning & Precedence",
}

# prefix -> real metis_mcp/*.py filenames actually present in the live
# (non-demo) Method pool this repo's own Cognify run already populated --
# queried, not assumed; verified via a direct Neo4j check before writing
# this list. Empty lists are deliberate, honest gaps (see module docstring).
MODULE_KEYWORDS = {
    "GRD": ["confidence_tiering.py", "constitution_gate.py", "structural_validation.py",
            "layer8_heuristics.py", "llm_judge.py", "vagueness.py", "classification_gate.py",
            "contract_validator.py"],
    "ACD": ["academy.py", "site_renderer.py", "pptx_renderer.py"],
    "CPT": ["copilot_integration.py"],
    "ONT": ["ears_checker.py", "requirement_quality.py"],
    "COST": ["cost_gate.py"],
    "CONN": ["manifest_validator.py"],
    "BM": ["behavior_model.py"],
    "RES": [],
    "MEM": ["pinned_memory.py", "hybrid_retrieval.py", "sleep_time_consolidation.py", "memify.py"],
    "SLD": ["pptx_renderer.py"],
    "MTX": [],
    "ING": [],
    "ARCH": ["graph_store.py", "neo4j_graph_store.py", "config_manager.py"],
    "TMP": ["temporal.py"],
    "SKL": [],
    "CG": [],
    "PG": ["pyramid_gap_check.py"],
    "DQ": ["dq_metrics.py"],
}

# tag -> hand-authored EARS paraphrase of that tag's real content (see
# module docstring for the grounding/curation discipline). 75 entries,
# matching the 75 real REQ-METIS-* tags found in corpus/*.md as of this
# writing -- if the real corpus grows, parse_corpus() will surface new
# tags with no paraphrase, which build_grounded_layer() skips (logged,
# not force-tagged with placeholder text).
GROUNDED_PARAPHRASES = {
    # ACD -- Academy, Site & PPTX
    "REQ-METIS-ACD-01": "The academy module shall explain the retrieval path, sources, and confidence tier behind any prior answer via the metis_explain_answer tool.",
    "REQ-METIS-ACD-02": "The academy module shall provide versioned, progressive-disclosure documentation covering graph model basics, traceability chains, confidence tiers, and EARS authoring.",
    "REQ-METIS-ACD-03": "If a submitted requirement is vague or lacks EARS conformance, then the academy module shall block it before it propagates rather than relying on later review.",
    "REQ-METIS-ACD-04": "When a Requirement is rejected or quarantined, the academy module shall attach an inline why annotation citing the specific guardrail rule that fired.",
    "REQ-METIS-ACD-05": "If a lookup tool returns no traceability match, then the academy module shall provide real next-step guidance rather than a bare empty result.",
    "REQ-METIS-ACD-06": "The academy module shall keep all Academy content versioned alongside the current ontology schema, never describing a schema version that is no longer live.",
    "REQ-METIS-ACD-07": "The academy module shall serve as the single canonical content-authoring layer, with the Site and PPTX outputs implemented as thin renderers rather than separate content authors.",
    "REQ-METIS-ACD-08": "The academy module shall share the same content-gathering stage between the Site and PPTX renderers rather than duplicating content-authoring logic per output format.",
    "REQ-METIS-ACD-09": "When a relevant graph change occurs, the academy module shall regenerate the static site to stay current.",
    # ARCH -- Single-Database Architecture
    "REQ-METIS-ARCH-01": "The architecture layer shall centralize graph state, episode provenance, and cost tracking in a single database rather than a federated multi-store design.",
    "REQ-METIS-ARCH-03": "The architecture layer shall use a single Neo4j Enterprise database as the sole authoritative store for graph state, episode provenance, review-queue state, cost tracking, and RBAC.",
    "REQ-METIS-ARCH-04": "The architecture layer shall store only aggregate values on MetricsSnapshot nodes, referencing back to Athena's own data for drill-down rather than duplicating raw execution rows.",
    # BM -- Behavior Model
    "REQ-METIS-BM-01": "If a proposed Transition passes structural validation and either a second textual source agrees or the code graph corroborates its guard and action shape, then the behavior model service shall raise it to the auto_write tier.",
    "REQ-METIS-BM-02": "If a proposed Transition's guard condition disagrees with the code graph's actual implementation, then the behavior model service shall record a ContradictionDetected episode and hold the Transition as Disputed.",
    "REQ-METIS-BM-03": "The behavior model service shall retain a generated test's GeneratedTest provenance permanently after it converges with the real, ingested TestCase on merge.",
    "REQ-METIS-BM-04": "The behavior model service shall implement reachability and completeness checks as deterministic Cypher queries rather than LLM judgment.",
    "REQ-METIS-BM-05": "When a human resolves a completeness violation's missing behavior, the behavior model service shall generate a corresponding functional test asserting that resolved behavior.",
    # CG -- Code Graph Archaeology
    "REQ-METIS-CG-01": "The code graph archaeology service shall extract Method-to-Method CALLS edges using deterministic call-chain analysis rather than an LLM.",
    "REQ-METIS-CG-02": "When a generated test converges with a real, ingested TestCase on merge, the code graph archaeology service shall preserve the original code-graph corroboration evidence that justified generating it.",
    # CONN -- Connector Architecture
    "REQ-METIS-CONN-01": "The connector registry shall enable a new connector by accepting a validated manifest rather than requiring a change to pipeline code.",
    "REQ-METIS-CONN-02": "The connector registry shall subject every manifest, regardless of source, to the full guardrail stack rather than treating a vendor-maintained MCP server as an inherently trustworthy content source.",
    "REQ-METIS-CONN-03": "The connector registry shall allow the application-code connector's manifest to declare an additional MCP tool allowlist for call-chain analysis tools.",
    "REQ-METIS-CONN-04": "If a Transition tagged performance-SLA-critical has no corresponding performance-type TestCase, then the connector registry shall automatically queue it for performance-test generation.",
    "REQ-METIS-CONN-06": "The connector registry shall attach the target project's own configured traceability-ID indicator to every generated test, linking it back to the Requirement or Transition it verifies.",
    # COST -- Cost Governance
    "REQ-METIS-COST-01": "The cost gate shall apply Caveman-style micro-directive compression to Cognify extraction prompts and Layer 6 judge prompts, never to user-facing Copilot output or stored specification content.",
    "REQ-METIS-COST-06": "If fewer than half of the produced items directly serve the locked scope, then the cost gate shall discard the batch and re-derive rather than pass drifted output downstream.",
    "REQ-METIS-COST-07": "If a Gate 3, Gate 4, or guardrail Layer 2 through 6 check fails, then the cost gate shall hard-stop the pipeline and prompt for a fix rather than silently continuing.",
    "REQ-METIS-COST-08": "If an action's estimated cost or blast radius is materially larger than typical, then the cost gate shall present an extra plain-language confirmation step before proceeding.",
    "REQ-METIS-COST-09": "The cost gate shall read the Cognify, judge, and reranker model names from configuration rather than hardcoding them in pipeline code.",
    # CPT -- Copilot & Multi-Client
    "REQ-METIS-CPT-01": "The copilot integration shall not request the metis write scope until the organization has explicitly opted into the write path.",
    "REQ-METIS-CPT-02": "The copilot integration shall keep OAuth2 scoping, RBAC, and tool contracts identical across Claude and Copilot clients, varying only the client-side registration configuration.",
    "REQ-METIS-CPT-03": "If a user's OAuth2 token does not carry the matching Service owner-team RBAC assignment, then the copilot integration shall deny cross-team pinned-block access even with a known node id.",
    "REQ-METIS-CPT-04": "The copilot integration shall discover the deployed mcp-server via a prebuilt spec-aware agent file rather than a raw mcp.json entry.",
    "REQ-METIS-CPT-05": "The copilot integration shall negotiate traversal depth and retrieval top-k per client connection, granting Copilot a 2-hop default and Claude a 3-hop default.",
    "REQ-METIS-CPT-06": "The copilot integration shall enforce spec conformance via a GitHub required status check that behaves identically for human, Copilot, and Claude Code-authored pull requests.",
    # DQ -- Data Quality
    "REQ-METIS-DQ-01": "The data quality layer shall expose the composite quality score and its full metric breakdown via a read-only metis_quality_score tool enabled by default.",
    # GRD -- Guardrails
    "REQ-METIS-GRD-01": "The guardrail pipeline shall require every entity and edge to carry a source_episode_id and source_span, enforced by the schema with no exceptions.",
    "REQ-METIS-GRD-02": "If a candidate entity fails structural validation, then the guardrail pipeline shall quarantine it rather than auto-create a node to satisfy a dangling reference.",
    "REQ-METIS-GRD-03": "Where confidence is at least 0.9 with a single reliable source and a passing structural check, the guardrail pipeline shall auto-write the candidate as Draft.",
    "REQ-METIS-GRD-04": "If a Risk=High Requirement, BusinessRule, or security-relevant guard lacks at least two independent corroborating sources, then the guardrail pipeline shall block its promotion from Reviewed to Approved.",
    "REQ-METIS-GRD-05": "The guardrail pipeline shall continuously run temporal and logical contradiction detection as background processes.",
    "REQ-METIS-GRD-06": "If the LLM-as-judge disagrees that a source span supports its associated claim, then the guardrail pipeline shall block promotion of that claim.",
    "REQ-METIS-GRD-07": "The guardrail pipeline shall never auto-promote a quarantined item on review timeout, leaving it quarantined indefinitely until a human reviews it.",
    "REQ-METIS-GRD-08": "The guardrail pipeline shall detect EARS non-conformance, circular traceability, orphan claims, and vagueness as fabrication and invalid-spec heuristics.",
    "REQ-METIS-GRD-09": "The guardrail pipeline shall run a quarterly held-out adversarial document set and track false-acceptance rate as its primary metric.",
    "REQ-METIS-GRD-10": "When a rollback is requested, the guardrail pipeline shall close t_valid and restore the prior state rather than destructively overwriting it.",
    "REQ-METIS-GRD-11": "If a candidate violates a Constitution rule, then the guardrail pipeline shall hard-block it before any other validation rule runs.",
    "REQ-METIS-GRD-12": "If fewer than half the entities and edges extracted by Cognify trace to the locking episode, then the guardrail pipeline shall discard the extraction and re-derive it.",
    # ING -- Ingestion
    "REQ-METIS-ING-01": "The ingestion pipeline shall populate t_recorded on every connector using its source system's native timestamp rather than a generic now default.",
    "REQ-METIS-ING-02": "The ingestion pipeline shall make every connector idempotent, using the unit_id scheme to avoid creating duplicate records on re-run.",
    "REQ-METIS-ING-03": "The ingestion pipeline shall perform structural extraction such as AST, migration, and OpenAPI parsing as deterministic code, reserving LLM extraction for free-text sources only.",
    # MEM -- Memory
    "REQ-METIS-MEM-01": "The memory layer shall inject active_constraints, open_incidents, and pinned_business_rules unconditionally into agent context, bypassing retrieval ranking.",
    "REQ-METIS-MEM-02": "The memory layer shall merge results from graph traversal, semantic, BM25, and temporal point-in-time retrieval modes and pass them through a cross-encoder reranker.",
    "REQ-METIS-MEM-03": "The memory layer shall propose near-duplicate Requirement and AcceptanceCriterion merges for human review rather than auto-applying them.",
    "REQ-METIS-MEM-04": "When a human overrides an AI-inferred fact, the memory layer shall fire an ExtractionCorrected episode and adjust the default confidence for that extraction rule, entity type, and connector triple.",
    # MTX -- Metrics
    "REQ-METIS-MTX-01": "The metrics integration shall expose guardrail and platform metrics as new objects in Athena's existing schema catalog rather than a standalone graph-only surface.",
    "REQ-METIS-MTX-02": "The metrics integration shall read Git, Jira, and OpenAPI data directly from Athena's existing tables as a live, ongoing integration rather than a one-time backfill.",
    "REQ-METIS-MTX-03": "The metrics integration shall extend Athena's schema-catalog pattern to also cover Métis's own evolving graph ontology.",
    # ONT -- Ontology
    "REQ-METIS-ONT-01": "The ontology layer shall require every Requirement and AcceptanceCriterion to carry a corroboration_count property reflecting how many independent sources support it.",
    "REQ-METIS-ONT-02": "If a Transition's APIs Called edge references an ExternalSystem, then the ontology layer shall require it to resolve to a corroborated ExternalAPISpec before reaching Approved.",
    "REQ-METIS-ONT-03": "The ontology layer shall schema-enforce 100 percent source-grounding completeness, requiring every node to carry a non-null source_episode_id.",
    "REQ-METIS-ONT-04": "The ontology layer shall check every submitted Requirement against the five EARS sentence patterns as a structural requirement-quality gate.",
    "REQ-METIS-ONT-05": "The ontology layer shall require every Requirement and AcceptanceCriterion to carry an integer revision property.",
    # PG -- Pyramid Gap
    "REQ-METIS-PG-01": "If a test layer already has passing coverage, then the pyramid gap check shall skip generation for that layer regardless of how long ago the coverage was written.",
    # RES -- Resumability
    "REQ-METIS-RES-01": "The resumability mechanism shall derive every unit_id deterministically from its inputs rather than from an auto-incrementing counter.",
    "REQ-METIS-RES-02": "The resumability mechanism shall tag every edit episode with an explicit delta_type of ADDED, MODIFIED, or REMOVED.",
    "REQ-METIS-RES-03": "When a long-running artifact's full atomic write, including guardrail checks, succeeds, the resumability mechanism shall flip its checkpoint_status to COMMITTED.",
    "REQ-METIS-RES-04": "The resumability mechanism shall apply the same resume algorithm uniformly to Cognify extraction batches, long technical-document generation, and sleep-time consolidation runs.",
    # SKL -- Skill Router
    "REQ-METIS-SKL-01": "The skill router shall organize every Métis skill using the agents skills SKILL.md file-layout convention adopted from Atlas's house style.",
    "REQ-METIS-SKL-02": "The skill router shall register Métis skills in Métis's own independent router, built on the same Quick Routing pattern as Atlas's without modifying Atlas's actual table.",
    # SLD -- Deck Rendering
    "REQ-METIS-SLD-01": "The deck renderer shall never ship a generated slide whose claim lacks a source_episode_id.",
    "REQ-METIS-SLD-02": "The deck renderer shall version its script and templates directories independently, so a template redesign never requires touching generation logic.",
    "REQ-METIS-SLD-03": "When deck generation completes, the deck renderer shall pause for human review before the QA gate is presented as complete.",
    # TMP -- Temporal
    "REQ-METIS-TMP-01": "The temporal layer shall track t_event, t_recorded, t_ingested, and t_valid and t_invalid as four distinct timestamp fields on every episode.",
    "REQ-METIS-TMP-02": "The temporal layer shall store the cross-source precedence table as versioned, editable graph data rather than hardcoding it in pipeline code.",
}


def _project_code(prefix: str) -> str:
    return f"METIS{prefix}"[:6]


def build_grounded_layer(session, r: random.Random, episode_fn, DEMO_TAG: str,
                          batch_merge_nodes, batch_merge_rels, edge_props_fn,
                          iso_fn, rand_past_fn, next_jira_key_fn,
                          corpus_glob: str, repo_root: str) -> dict:
    """Returns {"nodes": {label: count}, "relationships": {rel_type: count},
    "grounded_requirements_written": int, "grounded_requirements_with_real_implementing_method": int,
    "grounded_confluence_docs": int, "tags_with_no_paraphrase": int}."""
    node_counts: dict[str, int] = {}
    rel_counts: dict[str, int] = {}

    def add_nodes(label, rows):
        if rows:
            batch_merge_nodes(session, label, rows)
        node_counts[label] = node_counts.get(label, 0) + len(rows)

    def add_rels(from_label, to_label, rel_type, pairs):
        if pairs:
            batch_merge_rels(session, from_label, to_label, rel_type, pairs)
        rel_counts[rel_type] = rel_counts.get(rel_type, 0) + len(pairs)

    real_nodes = parse_corpus(corpus_glob)
    real_nodes.pop("__conflicts__", None)

    tags_by_prefix: dict[str, list[str]] = {}
    for tag in GROUNDED_PARAPHRASES:
        prefix = tag.split("-")[2]
        tags_by_prefix.setdefault(prefix, []).append(tag)
    tags_with_no_paraphrase = sum(
        1 for tag in real_nodes if tag.startswith("REQ-METIS-") and tag not in GROUNDED_PARAPHRASES
    )

    # Real Method pool this repo's own earlier Cognify run already
    # populated -- queried once, matched per-prefix by real filename.
    real_methods_by_prefix: dict[str, list[str]] = {}
    for prefix, keywords in MODULE_KEYWORDS.items():
        if not keywords:
            real_methods_by_prefix[prefix] = []
            continue
        rows = session.run(
            "MATCH (m:Method) WHERE m.is_demo_data IS NULL AND ANY(kw IN $keywords WHERE m.source_file CONTAINS kw) "
            "RETURN m.id AS id",
            keywords=keywords,
        ).data()
        real_methods_by_prefix[prefix] = [row["id"] for row in rows]

    tiering = ConfidenceTiering()
    goals, caps, epics, features, requirements, acs, testcases = [], [], [], [], [], [], []
    # Edge pairs are only collected here, never written -- all node labels
    # below must be fully batch-written first (see the add_nodes block
    # after this loop), otherwise the MATCH half of _batch_merge_rels'
    # MERGE would silently match zero rows against not-yet-created nodes.
    cap_traces, epic_traces, feature_traces, req_traces, has_ac, verifies, implements_pairs = (
        [], [], [], [], [], [], [])
    written = 0
    with_method = 0

    for prefix, goal_name in GROUNDED_GOALS.items():
        tags = sorted(tags_by_prefix.get(prefix, []))
        if not tags:
            continue
        goal_id = f"demo:metis-goal:{prefix}"
        goals.append({"id": goal_id, "source_episode_id": episode_fn(), "name": goal_name,
                      "lifecycle_state": "Approved", "source_kind": "metis_project",
                      "domain": prefix.lower(), DEMO_TAG: True})
        cap_id = f"{goal_id}:cap-0"
        caps.append({"id": cap_id, "source_episode_id": goals[-1]["source_episode_id"],
                    "name": f"{goal_name} — core capability", "lifecycle_state": "Approved",
                    "source_kind": "metis_project", DEMO_TAG: True})
        epic_id = f"{cap_id}:epic-0"
        epics.append({"id": epic_id, "source_episode_id": goals[-1]["source_episode_id"],
                     "name": f"{goal_name} implementation", "lifecycle_state": "Approved",
                     "source_kind": "metis_project", DEMO_TAG: True})
        feature_id = f"{epic_id}:feature-0"
        features.append({"id": feature_id, "source_episode_id": goals[-1]["source_episode_id"],
                        "name": goal_name, "lifecycle_state": "Approved",
                        "source_kind": "metis_project", DEMO_TAG: True})
        cap_traces.append({"from": cap_id, "to": goal_id, "props": edge_props_fn(r, rand_past_fn(r))})
        epic_traces.append({"from": epic_id, "to": cap_id, "props": edge_props_fn(r, rand_past_fn(r))})
        feature_traces.append({"from": feature_id, "to": epic_id, "props": edge_props_fn(r, rand_past_fn(r))})

        sprint_base = r.randint(30, 60)
        for tag in tags:
            text = GROUNDED_PARAPHRASES[tag]
            ears = check_ears_conformance(text)
            if not ears.conformant:
                # Every paraphrase above was hand-written to conform; if one
                # doesn't, that's a real authoring bug -- skip it exactly
                # like the synthetic layer does for non-conformant text,
                # never force-tag.
                continue

            confidence = r.uniform(0.7, 1.0)
            tier_result = tiering.evaluate(confidence=confidence, structural_valid=True, has_contradiction=False)
            if not tier_result.written_to_graph:
                continue

            real = real_nodes.get(tag)
            req_id = f"demo:metis-requirement:{tag}"
            row = {
                "id": req_id, "source_episode_id": episode_fn(), "text": text,
                "ears_pattern": ears.pattern, "revision": 1,
                "corroboration_count": r.randint(2, 4),
                "lifecycle_state": tier_result.lifecycle_state,
                "confidence_tier": tier_result.tier.value,
                "risk_tag": r.choice(["Low", "Medium"]),
                "source_kind": "metis_project",
                "derived_from": tag,
                "source_file": real.source_file if real else "unknown",
                "source_heading": real.source_heading if real else "unknown",
                "jira_key": next_jira_key_fn(prefix.lower()),
                "jira_issue_type": "Story",
                "jira_status": r.choice(["To Do", "In Progress", "In Review", "Done", "Done"]),
                "jira_sprint": f"Sprint {sprint_base + (written % 6)}",
                "jira_updated": iso_fn(rand_past_fn(r, 180)),
                DEMO_TAG: True,
            }
            if tier_result.lifecycle_state == "Quarantine":
                row["triage_reason"] = "demo_synthetic_confidence_score"
            requirements.append(row)
            written += 1
            req_traces.append({"from": req_id, "to": feature_id, "props": edge_props_fn(r, rand_past_fn(r))})

            ac_ids_for_req = []
            for j in range(r.randint(1, 3)):
                ac_id = f"{req_id}:ac-{j}"
                acs.append({
                    "id": ac_id, "source_episode_id": row["source_episode_id"], "revision": 1,
                    "text": f"Given the above, {goal_name} shall satisfy this requirement as specified.",
                    DEMO_TAG: True,
                })
                has_ac.append({"from": req_id, "to": ac_id, "props": edge_props_fn(r, rand_past_fn(r))})
                ac_ids_for_req.append(ac_id)
            # A TestCase verifies exactly one AcceptanceCriterion, never a
            # Requirement directly -- same real convention as the synthetic
            # layer (see generate_demo_data.py's Testing layer comment).
            for ac_id in ac_ids_for_req:
                for j in range(r.randint(1, 2)):
                    tc_id = f"{ac_id}:tc-{j}"
                    testcases.append({"id": tc_id, "source_episode_id": row["source_episode_id"],
                                      "name": f"test_{tag.lower().replace('-', '_')}_{ac_id.rsplit('-', 1)[-1]}_{j}",
                                      "type": "functional", "lifecycle_state": "Approved",
                                      "source_kind": "metis_project", DEMO_TAG: True})
                    verifies.append({"from": tc_id, "to": ac_id, "props": edge_props_fn(r, rand_past_fn(r))})

            candidates = real_methods_by_prefix.get(prefix, [])
            if candidates:
                method_id = r.choice(candidates)
                implements_pairs.append({"from": method_id, "to": req_id,
                                         "props": edge_props_fn(r, rand_past_fn(r))})
                with_method += 1

    add_nodes("Goal", goals)
    add_nodes("Capability", caps)
    add_nodes("Epic", epics)
    add_nodes("Feature", features)
    add_nodes("Requirement", requirements)
    add_nodes("AcceptanceCriterion", acs)
    add_nodes("TestCase", testcases)
    add_rels("Capability", "Goal", "TRACES_TO", cap_traces)
    add_rels("Epic", "Capability", "TRACES_TO", epic_traces)
    add_rels("Feature", "Epic", "TRACES_TO", feature_traces)
    add_rels("Requirement", "Feature", "TRACES_TO", req_traces)
    add_rels("Requirement", "AcceptanceCriterion", "HAS_AC", has_ac)
    add_rels("TestCase", "AcceptanceCriterion", "VERIFIES", verifies)
    add_rels("Method", "Requirement", "IMPLEMENTS", implements_pairs)

    # Real Confluence-shaped Episodes, sourced from this repo's own real
    # markdown docs (README.md/PLAN.md/CLAUDE.md + docs/*.md), truncated
    # (not embedded whole) same as a real Confluence landing wouldn't
    # necessarily capture a full doc either.
    doc_paths = sorted(glob.glob(os.path.join(repo_root, "docs", "*.md")))
    for name in ("README.md", "PLAN.md", "CLAUDE.md"):
        p = os.path.join(repo_root, name)
        if os.path.isfile(p):
            doc_paths.append(p)
    confluence_pages = []
    for path in doc_paths:
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read(4000)
        except OSError:
            continue
        base = os.path.basename(path)
        confluence_pages.append({
            "id": f"demo:metis-confluence:{base}", "source_connector": "demo-atlassian-prod",
            "unit_id": f"confluence:metis:{base}", "job_id": "demo-metis-grounded",
            "t_recorded": iso_fn(rand_past_fn(r, 300)), "checkpoint_status": "complete",
            "episode_type": "DocumentIngested", "confluence_page_id": f"{abs(hash(base)) % 100000}",
            "title": base, "raw_content": content, "source_kind": "metis_project", DEMO_TAG: True,
        })
    add_nodes("Episode", confluence_pages)

    return {
        "nodes": node_counts,
        "relationships": rel_counts,
        "grounded_requirements_written": written,
        "grounded_requirements_with_real_implementing_method": with_method,
        "grounded_confluence_docs": len(confluence_pages),
        "tags_with_no_paraphrase": tags_with_no_paraphrase,
    }
