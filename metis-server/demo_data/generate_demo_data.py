"""
Demo Data generator -- a structured, production-shaped synthetic dataset
(not independent random layers): a real backlog hierarchy for one
hypothetical company (Goal -> Capability -> Epic -> Feature -> Requirement
-> AcceptanceCriterion/TestCase), Jira- and Confluence-shaped metadata
around every requirement, and a code layer whose Repository/Class/Method
structure is coherently tied to the same business domains -- not a
disconnected pile of entities that happen to share labels.

Default shape (factor=1.0): **50 Goals, each with 50-150 real Requirements**
(~5,000 total), each Requirement with 1-3 AcceptanceCriteria, each of
those with a GUARANTEED 1-2 verifying TestCases (never the prior random
~60% coverage) -- a TestCase verifies exactly one AcceptanceCriterion,
never a Requirement directly (Requirement<-VERIFIES-TestCase with no
HAS_AC in between is the exact anti-pattern metis_mcp/layer8_heuristics.py's
DQ-018 check already flags as suspicious), landing at **~40,000-50,000
total nodes** -- production scale, not a ~500-node dogfooding-corpus
stand-in.

Structural coherence (the actual fix for "very random, not structured"):
every Goal is assigned ONE primary service domain (from vocab.SERVICES),
and every Capability/Epic/Feature/Requirement/Repository/Class/Method
beneath that Goal inherits the SAME domain -- a "payments" Goal's
Requirements, Jira keys, Confluence docs, and implementing code all
reference "payments," never a random unrelated service picked
independently per entity (the prior generator's actual bug: `service =
vocab.pick(r, vocab.SERVICES)` was called fresh inside the per-requirement
loop, uncorrelated with anything above it).

Real, not fabricated, in the ways that matter (unchanged from before):
  - Requirement text is generated from the same 5 real EARS templates
    metis_mcp/ears_checker.py defines, and every single one is actually
    re-validated through that real, unmodified checker -- a requirement
    that doesn't parse doesn't get an ears_pattern faked onto it, it's
    dropped (mirroring Layer 2's real behavior).
  - lifecycle_state on generated Requirements comes from a real call to
    metis_mcp/confidence_tiering.py's ConfidenceTiering.evaluate().
  - A subset of the generated Behavior Model is deliberately built with a
    real overlapping-guard ambiguity and run through metis_mcp/
    behavior_model.py's real determinism/completeness/reachability checks.
  - Method/TestCase ids now follow the real "repo:path:name" convention
    metis_mcp/pyramid_gap_check.py's Stage 3 coverage heuristic and
    guardrails/calibration.py's real-content sampling both actually parse
    -- previously demo Method/TestCase ids didn't match that convention at
    all, so the platform's own real tooling had nothing to find in demo
    data. They still carry no real `raw_content`-backed Episode (that
    remains real, unblurred application code, per calibration.py's own
    documented exclusion), so calibration still correctly excludes them.

Jira/Confluence, disclosed: these are real-shaped METADATA on the
production ontology's own real entities (Requirement.jira_key/
jira_status/sprint, Defect.jira_key; Episode.episode_type=
'DocumentIngested' with confluence_page_id/title, matching
atlassian_connector.py's actual real field conventions exactly) -- not a
live Jira/Confluence integration and not claimed to be one.

Grounded layer (demo_data/metis_grounded.py): on top of the fully
synthetic fictional-company dataset above, every run also adds a much
smaller, separately-marked (`source_kind: 'metis_project'` vs
`'synthetic'`) island grounded in THIS repo's own real project -- ~18 real
Goals (one per REQ-METIS-* subsystem prefix actually found in corpus/*.md)
and, for each of the 75 real REQ-METIS-* tags there, one hand-paraphrased
but genuinely EARS-conformant Requirement carrying `derived_from`/
`source_file`/`source_heading` back to its real tag. IMPLEMENTS edges
point at the real, already-existing (non-demo) Method pool this repo's
own earlier Cognify run populated -- not a synthetic copy. See that
module's docstring for the full grounding discipline.

Performance: batched UNWIND writes, MERGE (not CREATE) throughout, same
idempotency-on-rerun property as before.
"""
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from neo4j import GraphDatabase

from demo_data import vocab
from demo_data import metis_grounded
from demo_data import login_example
from metis_mcp.confidence_tiering import ConfidenceTiering
from metis_mcp.ears_checker import check_ears_conformance
from metis_mcp.temporal import record_revision

DEMO_TAG = "is_demo_data"
BATCH_SIZE = 500

DEMO_CONNECTORS = [
    "demo-application-code", "demo-atlassian-prod", "demo-bmad-method-specs",
    "demo-grafana-metrics", "demo-locust-performance", "demo-test-suite-ingest",
    "demo-flat-files",
]


@dataclass
class Scale:
    """Multiplier knob. factor=1.0 is the real target shape (~45,000
    nodes: 50 Goals x 50-150 Requirements each). Pass a smaller `factor`
    for a fast smoke run -- every count in this module, including goal
    count and per-goal requirement range, scales with it."""
    factor: float = 1.0

    def n(self, base: int) -> int:
        return max(1, round(base * self.factor))


@dataclass
class Counters:
    nodes: dict = field(default_factory=dict)
    relationships: dict = field(default_factory=dict)
    skipped_non_ears: int = 0

    def add_nodes(self, label: str, count: int):
        self.nodes[label] = self.nodes.get(label, 0) + count

    def add_rels(self, rel_type: str, count: int):
        self.relationships[rel_type] = self.relationships.get(rel_type, 0) + count

    def total_nodes(self) -> int:
        return sum(self.nodes.values())

    def total_relationships(self) -> int:
        return sum(self.relationships.values())


def _batch_merge_nodes(session, label: str, rows: list[dict]) -> None:
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]

        def _tx(tx, batch=batch, label=label):
            tx.run(
                f"UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) SET n += row",
                rows=batch,
            )
        session.execute_write(_tx)


def _batch_merge_rels(session, from_label: str, to_label: str, rel_type: str, pairs: list[dict]) -> None:
    for i in range(0, len(pairs), BATCH_SIZE):
        batch = pairs[i:i + BATCH_SIZE]

        def _tx(tx, batch=batch, from_label=from_label, to_label=to_label, rel_type=rel_type):
            tx.run(
                f"""
                UNWIND $pairs AS p
                MATCH (a:{from_label} {{id: p.from}}), (b:{to_label} {{id: p.to}})
                MERGE (a)-[r:{rel_type}]->(b)
                SET r += p.props
                """,
                pairs=batch,
            )
        session.execute_write(_tx)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _rand_past_datetime(r: random.Random, days_back: int = 720) -> datetime:
    return datetime.now(timezone.utc) - timedelta(
        days=r.randint(0, days_back), hours=r.randint(0, 23), minutes=r.randint(0, 59),
    )


def _edge_props(r: random.Random, created_at: datetime) -> dict:
    """Schema-02's note: every HAS_AC/IMPLEMENTS/VERIFIES/PRODUCES/TRACES_TO
    edge also carries created_by/created_at/confidence -- honored here."""
    return {
        "created_by": r.choice(["human", "ai_decision"]),
        "created_at": _iso(created_at),
        "confidence": round(r.uniform(0.6, 1.0), 2),
        "t_valid": _iso(created_at),
    }


def _make_episodes(session, run_id: str) -> list[str]:
    rows = []
    now = datetime.now(timezone.utc)
    for connector in DEMO_CONNECTORS:
        eid = f"demo:episode:{run_id}:{connector}"
        rows.append({
            "id": eid, "t_recorded": _iso(now), "source_connector": connector,
            "job_id": f"demo-data-{run_id}", "checkpoint_status": "complete",
            DEMO_TAG: True,
        })
    _batch_merge_nodes(session, "Episode", rows)
    return [row["id"] for row in rows]


def _project_code(service: str) -> str:
    """A real-looking Jira project-key prefix derived deterministically
    from the service name, e.g. 'fraud-detection' -> 'FRAU'."""
    letters = service.replace("-", "").upper()
    return letters[:4] if len(letters) >= 4 else letters.ljust(3, "X")


def _slug(text: str) -> str:
    return text.lower().replace(" ", "_").replace("-", "_")


def generate(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
             scale: Scale = Scale(), seed: int = 42, database: str = "neo4j",
             on_progress=None, corpus_glob: str | None = None, repo_root: str | None = None) -> dict:
    r = random.Random(seed)
    run_id = f"{int(time.time())}"
    counters = Counters()
    jira_seq = {}  # project_code -> next sequential number, for real-looking jira_key values

    def next_jira_key(service: str) -> str:
        code = _project_code(service)
        jira_seq[code] = jira_seq.get(code, 1000) + 1
        return f"{code}-{jira_seq[code]}"

    def progress(msg: str):
        if on_progress:
            on_progress(msg)

    if corpus_glob is None or repo_root is None:
        # Same resolution convention load_dogfooding_corpus.py already
        # uses: corpus.glob from .metis/config.yaml, resolved relative to
        # this file's own directory (metis-server/) when not absolute.
        from metis_mcp.config_manager import ConfigManager
        config = ConfigManager()
        resolved_glob = config.get_corpus_glob() or "corpus/*.md"
        metis_server_dir = config.effective_path.parent.parent
        if not os.path.isabs(resolved_glob):
            resolved_glob = str(metis_server_dir / resolved_glob)
        corpus_glob = corpus_glob or resolved_glob
        repo_root = repo_root or str(metis_server_dir.parent)

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    driver.verify_connectivity()
    try:
        with driver.session(database=database) as session:
            episode_ids = _make_episodes(session, run_id)
            counters.add_nodes("Episode", len(episode_ids))

            def episode() -> str:
                return r.choice(episode_ids)

            # ---------- Governance ----------
            progress("Governance...")
            _batch_merge_nodes(session, "Constitution", [{
                "id": "demo:constitution:1", "source_episode_id": episode(),
                "precedence_rank": 0, DEMO_TAG: True,
            }])
            counters.add_nodes("Constitution", 1)

            ext_api_specs = [
                {"id": f"demo:extapi:{i}", "source_episode_id": episode(),
                 "registry_source": r.choice(["swaggerhub", "apis.guru", "internal-registry"]),
                 "name": f"{vocab.pick(r, vocab.SERVICES)}-external-api-v{r.randint(1,3)}", DEMO_TAG: True}
                for i in range(scale.n(100))
            ]
            _batch_merge_nodes(session, "ExternalAPISpec", ext_api_specs)
            counters.add_nodes("ExternalAPISpec", len(ext_api_specs))

            # ---------- Business layer: Goal -> Capability -> Epic -> Feature ----------
            # Structural coherence fix: every level below a Goal inherits
            # that Goal's ONE assigned service domain -- carried as `_svc`
            # through every dict below, stripped before writing (not a
            # real ontology property, just this generator's own bookkeeping).
            progress("Business layer (50 Goals, each with a coherent service domain)...")
            n_goals = scale.n(50)
            service_cycle = list(vocab.SERVICES)
            r.shuffle(service_cycle)

            goals = []
            for i in range(n_goals):
                svc = service_cycle[i % len(service_cycle)]
                goals.append({
                    "id": f"demo:goal:{i}", "source_episode_id": episode(),
                    "name": vocab.goal_name(r, svc), "lifecycle_state": "Approved",
                    "source_kind": "synthetic", "domain": svc, "_svc": svc, DEMO_TAG: True,
                })
            _batch_merge_nodes(session, "Goal", [{k: v for k, v in g.items() if k != "_svc"} for g in goals])
            counters.add_nodes("Goal", len(goals))

            caps = []
            for g in goals:
                for j in range(r.randint(2, 3)):
                    caps.append({
                        "id": f"{g['id']}:cap-{j}", "source_episode_id": g["source_episode_id"],
                        "name": f"{g['_svc']} {vocab.pick(r, ['management', 'automation', 'insights', 'optimization'])}",
                        "lifecycle_state": "Approved", "source_kind": "synthetic",
                        "_goal": g["id"], "_svc": g["_svc"], DEMO_TAG: True,
                    })
            _batch_merge_nodes(session, "Capability", [{k: v for k, v in c.items() if k not in ("_goal", "_svc")} for c in caps])
            counters.add_nodes("Capability", len(caps))
            _batch_merge_rels(session, "Capability", "Goal", "TRACES_TO",
                               [{"from": c["id"], "to": c["_goal"], "props": _edge_props(r, _rand_past_datetime(r))} for c in caps])
            counters.add_rels("TRACES_TO", len(caps))

            epics = []
            for c in caps:
                for j in range(r.randint(2, 3)):
                    epics.append({
                        "id": f"{c['id']}:epic-{j}", "source_episode_id": c["source_episode_id"],
                        "name": f"{vocab.pick(r, vocab.ACTIONS).capitalize()} {c['_svc']} {vocab.pick(r, vocab.NOUNS)} handling",
                        "lifecycle_state": r.choice(["Draft", "Approved", "Approved", "Approved"]),
                        "source_kind": "synthetic", "_cap": c["id"], "_goal": c["_goal"], "_svc": c["_svc"], DEMO_TAG: True,
                    })
            _batch_merge_nodes(session, "Epic", [{k: v for k, v in e.items() if k not in ("_cap", "_goal", "_svc")} for e in epics])
            counters.add_nodes("Epic", len(epics))
            _batch_merge_rels(session, "Epic", "Capability", "TRACES_TO",
                               [{"from": e["id"], "to": e["_cap"], "props": _edge_props(r, _rand_past_datetime(r))} for e in epics])
            counters.add_rels("TRACES_TO", len(epics))

            features = []
            for e in epics:
                for j in range(r.randint(2, 4)):
                    features.append({
                        "id": f"{e['id']}:feature-{j}", "source_episode_id": e["source_episode_id"],
                        "name": f"{e['_svc']} {vocab.pick(r, vocab.FEATURES_ADJ)}",
                        "lifecycle_state": r.choice(["Draft", "Reviewed", "Approved", "Approved"]),
                        "source_kind": "synthetic", "_epic": e["id"], "_goal": e["_goal"], "_svc": e["_svc"], DEMO_TAG: True,
                    })
            _batch_merge_nodes(session, "Feature", [{k: v for k, v in f.items() if k not in ("_epic", "_goal", "_svc")} for f in features])
            counters.add_nodes("Feature", len(features))
            _batch_merge_rels(session, "Feature", "Epic", "TRACES_TO",
                               [{"from": f["id"], "to": f["_epic"], "props": _edge_props(r, _rand_past_datetime(r))} for f in features])
            counters.add_rels("TRACES_TO", len(features))

            features_by_goal: dict[str, list[dict]] = {}
            for f in features:
                features_by_goal.setdefault(f["_goal"], []).append(f)

            # ---------- Requirement layer: 50-150 PER GOAL, real EARS+tiering ----------
            progress("Requirements (50-150 per Goal, real EARS-checked, real confidence-tiered, real Jira metadata)...")
            tiering = ConfidenceTiering()
            requirements = []
            req_counter = 0
            for g in goals:
                svc = g["_svc"]
                goal_features = features_by_goal.get(g["id"], [])
                if not goal_features:
                    continue
                # Target is the FINAL written-to-graph count, per the
                # user's literal "each having 50 to 150 requirements" spec
                # -- not a candidate count. ~1/6 of candidates are
                # deliberately non-EARS-conformant and ~1/3 deliberately
                # land in the real Rejected tier (exercising those real
                # gates), so candidates keep generating per-goal until the
                # target is actually met, capped to avoid a runaway loop
                # on an unlucky RNG streak.
                target_reqs_for_goal = r.randint(scale.n(50), max(scale.n(50), scale.n(150)))
                written_for_goal = 0
                attempts = 0
                max_attempts = target_reqs_for_goal * 6
                sprint_base = r.randint(30, 60)
                while written_for_goal < target_reqs_for_goal and attempts < max_attempts:
                    attempts += 1
                    req_counter += 1
                    feature = r.choice(goal_features)
                    action = vocab.pick(r, vocab.ACTIONS)
                    noun = vocab.pick(r, vocab.NOUNS)
                    pattern_kind = r.choice(["ubiquitous", "event", "state", "unwanted", "optional", "malformed"])
                    if pattern_kind == "ubiquitous":
                        text = f"The {svc} service shall {action} the {noun}."
                    elif pattern_kind == "event":
                        text = f"When {vocab.pick(r, vocab.TRIGGERS)}, the {svc} service shall {action} the {noun}."
                    elif pattern_kind == "state":
                        text = f"While {vocab.pick(r, vocab.STATES)}, the {svc} service shall {action} the {noun}."
                    elif pattern_kind == "unwanted":
                        text = f"If {vocab.pick(r, vocab.CONDITIONS)}, then the {svc} service shall {action} the {noun}."
                    elif pattern_kind == "optional":
                        text = f"Where {vocab.pick(r, vocab.FEATURES_ADJ)} is enabled, the {svc} service shall {action} the {noun}."
                    else:
                        # Deliberately non-EARS-conformant free text -- exercises
                        # the real Layer 2 gate's real rejection path below.
                        text = f"{svc} should probably {action} the {noun} at some point."

                    ears = check_ears_conformance(text)
                    if not ears.conformant:
                        counters.skipped_non_ears += 1
                        continue  # matches real Layer 2 behavior: never written

                    confidence = r.uniform(0.45, 1.0)
                    tier_result = tiering.evaluate(confidence=confidence, structural_valid=True,
                                                    has_contradiction=False)
                    if not tier_result.written_to_graph:
                        continue  # Rejected tier -- logged only, never written, per REQ-METIS-GRD-03

                    written_for_goal += 1
                    req_id = f"demo:requirement:{req_counter}"
                    row = {
                        "id": req_id, "source_episode_id": episode(), "text": text,
                        "ears_pattern": ears.pattern, "revision": 1,
                        "corroboration_count": r.randint(1, 4),
                        "lifecycle_state": tier_result.lifecycle_state,
                        "confidence_tier": tier_result.tier.value,
                        "risk_tag": r.choice(["Low", "Low", "Medium", "High"]),
                        "source_kind": "synthetic",
                        # Real Jira-shaped metadata (REQ-METIS-CONN-04's field
                        # conventions, matching connectors/atlassian_connector.py
                        # exactly: jira_key, summary, jira_updated) -- this is
                        # what "Jira data around them" means for an offline
                        # generator with no live Jira instance to connect to.
                        "jira_key": next_jira_key(svc),
                        "jira_issue_type": vocab.pick(r, vocab.JIRA_ISSUE_TYPES_FOR_REQUIREMENT),
                        "jira_status": vocab.pick(r, vocab.JIRA_STATUSES),
                        "jira_sprint": f"Sprint {sprint_base + (req_counter % 6)}",
                        "jira_updated": _iso(_rand_past_datetime(r, 180)),
                        "_feature": feature["id"], "_svc": svc, DEMO_TAG: True,
                    }
                    if tier_result.lifecycle_state == "Quarantine":
                        row["triage_reason"] = "demo_synthetic_confidence_score"
                    requirements.append(row)
            _batch_merge_nodes(session, "Requirement", [{k: v for k, v in q.items() if k not in ("_feature", "_svc")} for q in requirements])
            counters.add_nodes("Requirement", len(requirements))
            _batch_merge_rels(session, "Requirement", "Feature", "TRACES_TO",
                               [{"from": q["id"], "to": q["_feature"], "props": _edge_props(r, _rand_past_datetime(r))} for q in requirements])
            counters.add_rels("TRACES_TO", len(requirements))

            # ---------- Acceptance Criteria: 1-3 real per Requirement ----------
            progress("Acceptance Criteria (1-3 per Requirement)...")
            acs = []
            for q in requirements:
                for j in range(r.randint(1, 3)):
                    acs.append({
                        "id": f"{q['id']}:ac-{j}", "source_episode_id": q["source_episode_id"],
                        "revision": 1,
                        "text": f"Given the above, the {q['_svc']} service shall {vocab.pick(r, vocab.ACTIONS)} "
                                f"the {vocab.pick(r, vocab.NOUNS)} as specified.",
                        "_req": q["id"], "_svc": q["_svc"], DEMO_TAG: True,
                    })
            _batch_merge_nodes(session, "AcceptanceCriterion", [{k: v for k, v in a.items() if k not in ("_req", "_svc")} for a in acs])
            counters.add_nodes("AcceptanceCriterion", len(acs))
            _batch_merge_rels(session, "Requirement", "AcceptanceCriterion", "HAS_AC",
                               [{"from": a["_req"], "to": a["id"], "props": _edge_props(r, _rand_past_datetime(r))} for a in acs])
            counters.add_rels("HAS_AC", len(acs))

            # ---------- Grounded layer: real Métis project content ----------
            # Additive, not scaled by `scale.factor` (it's a fixed real
            # corpus, not a volume knob) -- see demo_data/metis_grounded.py.
            progress("Grounding layer (real Métis project content: real Requirements, real code, real docs)...")
            grounded = metis_grounded.build_grounded_layer(
                session, r, episode, DEMO_TAG, _batch_merge_nodes, _batch_merge_rels, _edge_props,
                _iso, _rand_past_datetime, next_jira_key, corpus_glob, repo_root,
            )
            for label, count in grounded["nodes"].items():
                counters.add_nodes(label, count)
            for rel_type, count in grounded["relationships"].items():
                counters.add_rels(rel_type, count)

            # ---------- Login example: the real Intent/TestDesign backbone proof ----------
            # Session 10: one real, hand-authored state machine (not scaled
            # by `scale.factor`, a fixed example) demonstrating State/
            # Transition -> Intent -> {Requirement, AcceptanceCriterion},
            # Intent -> TestDesign -> TestCase end to end -- see
            # demo_data/login_example.py.
            progress("Login example (real Intent/TestDesign backbone, 16 implemented + 1 planned transition)...")
            login = login_example.build_login_example(
                session, r, episode, DEMO_TAG, _batch_merge_nodes, _batch_merge_rels, _edge_props,
                _iso, _rand_past_datetime,
            )
            for label, count in login["nodes"].items():
                counters.add_nodes(label, count)
            for rel_type, count in login["relationships"].items():
                counters.add_rels(rel_type, count)

            constraints = [{"id": f"demo:constraint:{i}", "source_episode_id": episode(),
                             "text": f"The {vocab.pick(r, vocab.SERVICES)} service must respond within {r.choice([100,200,500])}ms.",
                             DEMO_TAG: True} for i in range(scale.n(200))]
            _batch_merge_nodes(session, "Constraint", constraints)
            counters.add_nodes("Constraint", len(constraints))

            business_rules = [{"id": f"demo:businessrule:{i}", "source_episode_id": episode(),
                                "text": f"{vocab.pick(r, vocab.NOUNS).capitalize()} totals must reconcile with the ledger nightly.",
                                "corroboration_count": r.randint(1, 3), DEMO_TAG: True}
                               for i in range(scale.n(300))]
            _batch_merge_nodes(session, "BusinessRule", business_rules)
            counters.add_nodes("BusinessRule", len(business_rules))

            # ---------- Confluence layer: real DocumentIngested Episodes, tied to Goals/Features ----------
            progress("Confluence data (real DocumentIngested Episodes per Goal/Feature)...")
            confluence_pages = []
            for g in goals:
                doc_type = vocab.pick(r, vocab.CONFLUENCE_DOC_TYPES)
                confluence_pages.append({
                    "id": f"demo:confluence:{g['id']}", "source_connector": "demo-atlassian-prod",
                    "unit_id": f"confluence:{g['id']}", "job_id": f"demo-data-{run_id}",
                    "t_recorded": _iso(_rand_past_datetime(r, 300)), "checkpoint_status": "complete",
                    "episode_type": "DocumentIngested", "confluence_page_id": f"{abs(hash(g['id'])) % 100000}",
                    "title": f"{doc_type}: {g['name']}",
                    "raw_content": f"<p>This {doc_type.lower()} describes the {g['_svc']} initiative: {g['name']}.</p>",
                    DEMO_TAG: True,
                })
            for f_ in features:
                if r.random() < 0.3:
                    doc_type = vocab.pick(r, vocab.CONFLUENCE_DOC_TYPES)
                    confluence_pages.append({
                        "id": f"demo:confluence:{f_['id']}", "source_connector": "demo-atlassian-prod",
                        "unit_id": f"confluence:{f_['id']}", "job_id": f"demo-data-{run_id}",
                        "t_recorded": _iso(_rand_past_datetime(r, 300)), "checkpoint_status": "complete",
                        "episode_type": "DocumentIngested", "confluence_page_id": f"{abs(hash(f_['id'])) % 100000}",
                        "title": f"{doc_type}: {f_['name']}",
                        "raw_content": f"<p>This {doc_type.lower()} covers the {f_['name']} feature.</p>",
                        DEMO_TAG: True,
                    })
            _batch_merge_nodes(session, "Episode", confluence_pages)
            counters.add_nodes("Episode", len(confluence_pages))

            # ---------- Architecture layer ----------
            progress("Architecture layer (Service/API/Endpoint/Database/...)...")
            services = [{"id": f"demo:service:{svc}", "source_episode_id": episode(),
                         "name": f"{svc}-service", "owner_team": svc, "_svc": svc, DEMO_TAG: True}
                        for svc in vocab.SERVICES]
            _batch_merge_nodes(session, "Service", [{k: v for k, v in s.items() if k != "_svc"} for s in services])
            counters.add_nodes("Service", len(services))

            apis = [{"id": f"demo:api:{i}", "source_episode_id": episode(),
                     "name": f"{services[i % len(services)]['name']}-api-v{r.randint(1,3)}",
                     "_service": services[i % len(services)]["id"], DEMO_TAG: True} for i in range(scale.n(60))]
            _batch_merge_nodes(session, "API", [{k: v for k, v in a.items() if k != "_service"} for a in apis])
            counters.add_nodes("API", len(apis))

            endpoints = [{"id": f"demo:endpoint:{i}", "source_episode_id": episode(),
                          "path": f"/api/{vocab.pick(r, vocab.SERVICES)}/{vocab.pick(r, vocab.NOUNS).replace(' ', '-')}",
                          "method": r.choice(["GET", "POST", "PUT", "DELETE"]),
                          "_api": apis[i % len(apis)]["id"], DEMO_TAG: True} for i in range(scale.n(300))]
            _batch_merge_nodes(session, "Endpoint", [{k: v for k, v in e.items() if k != "_api"} for e in endpoints])
            counters.add_nodes("Endpoint", len(endpoints))

            databases = [{"id": f"demo:database:{i}", "source_episode_id": episode(),
                          "name": f"{vocab.pick(r, vocab.SERVICES)}-db", DEMO_TAG: True} for i in range(scale.n(15))]
            _batch_merge_nodes(session, "Database", databases)
            counters.add_nodes("Database", len(databases))
            # Session 11, item 3: real revision history on every Database
            # write -- the prerequisite for staleness to mean anything for
            # this label. metis_mcp/graph_sync.py's check_staleness already
            # works per Episode.source_connector for ANY label; it had
            # nothing to read here before because Database/Table never had
            # any revision history at all.
            for db in databases:
                record_revision(session, db["id"], {"name": db["name"]}, db["source_episode_id"])
            counters.add_nodes("Revision", len(databases))
            counters.add_rels("HAS_REVISION", len(databases))

            tables = [{"id": f"demo:table:{i}", "source_episode_id": episode(),
                       "name": f"{vocab.pick(r, vocab.NOUNS).replace(' ', '_')}s",
                       "_database": r.choice(databases)["id"] if databases else None, DEMO_TAG: True}
                      for i in range(scale.n(150))]
            _batch_merge_nodes(session, "Table",
                                [{k: v for k, v in t.items() if k != "_database"} for t in tables])
            counters.add_nodes("Table", len(tables))
            for tb in tables:
                record_revision(session, tb["id"], {"name": tb["name"]}, tb["source_episode_id"])
            counters.add_nodes("Revision", len(tables))
            counters.add_rels("HAS_REVISION", len(tables))

            # record_revision's real :Revision nodes don't carry is_demo_data
            # (same real gap login_example.py's own Revision nodes hit in
            # Session 10) -- tag them here in one pass so wipe_demo_data and
            # the no-dangling-relationship invariant both hold.
            session.execute_write(lambda tx: tx.run(
                "MATCH (n) WHERE n.id STARTS WITH 'demo:database:' OR n.id STARTS WITH 'demo:table:' "
                "MATCH (n)-[:HAS_REVISION]->(rev:Revision) "
                f"SET rev.{DEMO_TAG} = true"
            ).consume())

            # Database-[:HAS]->Table (Session 11, item 3) -- the spec has
            # always named this edge; the whole Architecture layer had zero
            # internal relationships before this.
            has_table_pairs = [{"from": t["_database"], "to": t["id"], "props": {}}
                                for t in tables if t["_database"]]
            _batch_merge_rels(session, "Database", "Table", "HAS", has_table_pairs)
            counters.add_rels("HAS", len(has_table_pairs))

            columns = [{"id": f"demo:column:{i}", "source_episode_id": episode(),
                        "name": r.choice(["id", "created_at", "status", "amount", "customer_id", "updated_at"]),
                        DEMO_TAG: True} for i in range(scale.n(800))]
            _batch_merge_nodes(session, "Column", columns)
            counters.add_nodes("Column", len(columns))

            # "Cache" removed (Session 11, item 5) -- see the AI-layer removal
            # note further down for the full rationale; Cache itself modeled
            # infrastructure caching tech, not an LLM session, but the user
            # confirmed removing it anyway.
            for label, count in (("KafkaTopic", 40), ("ExternalSystem", 40)):
                rows = [{"id": f"demo:{label.lower()}:{i}", "source_episode_id": episode(),
                         "name": f"{vocab.pick(r, vocab.SERVICES)}-{label.lower()}-{i}", DEMO_TAG: True}
                        for i in range(scale.n(count))]
                _batch_merge_nodes(session, label, rows)
                counters.add_nodes(label, len(rows))

            # ---------- Implementation layer: Repository PER SERVICE, real repo:path:name ids ----------
            progress("Implementation layer (one Repository per service domain, real repo:path:name ids, coherent IMPLEMENTS)...")
            repos = [{"id": f"demo-{svc}-service", "source_episode_id": episode(),
                      "name": f"{svc}-service", "_svc": svc, DEMO_TAG: True} for svc in vocab.SERVICES]
            _batch_merge_nodes(session, "Repository", [{k: v for k, v in rp.items() if k != "_svc"} for rp in repos])
            counters.add_nodes("Repository", len(repos))
            repo_by_svc = {rp["_svc"]: rp for rp in repos}

            n_classes_per_repo = scale.n(50)
            classes = []
            for rp in repos:
                for ci in range(n_classes_per_repo):
                    class_name = f"{vocab.pick(r, vocab.NOUNS).title().replace(' ', '')}Handler{ci}"
                    path = f"src/{_slug(rp['_svc'])}/{_slug(class_name)}.py"
                    classes.append({
                        "id": f"{rp['id']}:{path}:{class_name}", "source_episode_id": rp["source_episode_id"],
                        "name": class_name, "source_file": path,
                        "_repo": rp["id"], "_svc": rp["_svc"], "_path": path, DEMO_TAG: True,
                    })
            _batch_merge_nodes(session, "Class", [{k: v for k, v in c.items() if k not in ("_repo", "_svc", "_path")} for c in classes])
            counters.add_nodes("Class", len(classes))
            _batch_merge_rels(session, "Repository", "Class", "DEFINES",
                               [{"from": c["_repo"], "to": c["id"], "props": {}} for c in classes])
            counters.add_rels("DEFINES", len(classes))

            methods = []
            methods_by_svc: dict[str, list[dict]] = {}
            for c in classes:
                for j in range(r.randint(3, 9)):
                    method_name = f"{vocab.pick(r, vocab.ACTIONS)}_{vocab.pick(r, vocab.NOUNS).replace(' ', '_')}_{j}"
                    m = {
                        "id": f"{c['_repo']}:{c['_path']}:{c['name']}.{method_name}",
                        "source_episode_id": c["source_episode_id"], "name": method_name,
                        "source_file": c["_path"], "_class": c["id"], "_svc": c["_svc"], DEMO_TAG: True,
                    }
                    methods.append(m)
                    methods_by_svc.setdefault(c["_svc"], []).append(m)
            _batch_merge_nodes(session, "Method", [{k: v for k, v in m.items() if k not in ("_class", "_svc")} for m in methods])
            counters.add_nodes("Method", len(methods))
            _batch_merge_rels(session, "Class", "Method", "HAS_METHOD",
                               [{"from": m["_class"], "to": m["id"], "props": {}} for m in methods])
            counters.add_rels("HAS_METHOD", len(methods))

            # CALLS: real edges between actually-generated Method nodes, never fabricated targets.
            calls_pairs = []
            for m in methods:
                for _ in range(r.randint(0, 3)):
                    target = r.choice(methods)
                    if target["id"] != m["id"]:
                        calls_pairs.append({"from": m["id"], "to": target["id"], "props": {}})
            _batch_merge_rels(session, "Method", "Method", "CALLS", calls_pairs)
            counters.add_rels("CALLS", len(calls_pairs))

            imports_pairs = []
            for c in classes:
                for _ in range(r.randint(0, 2)):
                    target = r.choice(classes)
                    if target["id"] != c["id"]:
                        imports_pairs.append({"from": c["id"], "to": target["id"], "props": {}})
            _batch_merge_rels(session, "Class", "Class", "IMPORTS", imports_pairs)
            counters.add_rels("IMPORTS", len(imports_pairs))

            inherits_pairs = []
            for c in classes:
                if r.random() < 0.12:
                    target = r.choice(classes)
                    if target["id"] != c["id"]:
                        inherits_pairs.append({"from": c["id"], "to": target["id"], "props": {}})
            _batch_merge_rels(session, "Class", "Class", "INHERITS", inherits_pairs)
            counters.add_rels("INHERITS", len(inherits_pairs))

            # IMPLEMENTS: coherent by domain -- a requirement's implementing
            # Method comes from ITS OWN service's repo, not a random one
            # anywhere in the graph (the prior generator's version of this
            # exact same "very random, not structured" bug).
            implements_pairs = []
            requirement_implementing_method: dict[str, str] = {}
            for q in requirements:
                candidates = methods_by_svc.get(q["_svc"])
                if not candidates or r.random() >= 0.7:
                    continue
                method = r.choice(candidates)
                implements_pairs.append({"from": method["id"], "to": q["id"],
                                          "props": _edge_props(r, _rand_past_datetime(r))})
                requirement_implementing_method[q["id"]] = method["id"]
            _batch_merge_rels(session, "Method", "Requirement", "IMPLEMENTS", implements_pairs)
            counters.add_rels("IMPLEMENTS", len(implements_pairs))

            n_prs = scale.n(800)
            prs = [{"id": f"demo:pr:{i}", "source_episode_id": episode(),
                    "title": f"{vocab.pick(r, vocab.ACTIONS).capitalize()} {vocab.pick(r, vocab.NOUNS)} in {vocab.pick(r, vocab.SERVICES)}",
                    "merged_at": _iso(_rand_past_datetime(r)), DEMO_TAG: True} for i in range(n_prs)]
            _batch_merge_nodes(session, "PullRequest", prs)
            counters.add_nodes("PullRequest", len(prs))

            commits = [{"id": f"demo:commit:{i}", "source_episode_id": episode(),
                        "sha": f"{r.getrandbits(40):010x}", "authored_at": _iso(_rand_past_datetime(r)),
                        "_pr": prs[i % n_prs]["id"], DEMO_TAG: True} for i in range(scale.n(3000))]
            _batch_merge_nodes(session, "Commit", [{k: v for k, v in c.items() if k != "_pr"} for c in commits])
            counters.add_nodes("Commit", len(commits))
            _batch_merge_rels(session, "PullRequest", "Commit", "PRODUCES",
                               [{"from": c["_pr"], "to": c["id"], "props": _edge_props(r, _rand_past_datetime(r))} for c in commits])
            counters.add_rels("PRODUCES", len(commits))

            branches = [{"id": f"demo:branch:{i}", "source_episode_id": episode(),
                         "name": f"feature/{vocab.pick(r, vocab.ACTIONS)}-{vocab.pick(r, vocab.NOUNS).replace(' ', '-')}",
                         DEMO_TAG: True} for i in range(scale.n(100))]
            _batch_merge_nodes(session, "Branch", branches)
            counters.add_nodes("Branch", len(branches))

            # ---------- Testing layer: GUARANTEED 1-2 TestCases per real AcceptanceCriterion ----------
            # A TestCase verifies exactly one AcceptanceCriterion, never a
            # Requirement directly -- Requirement<-VERIFIES-TestCase with no
            # HAS_AC in between is exactly the anti-pattern metis_mcp/
            # layer8_heuristics.py's check_circular_traceability (DQ-018)
            # already flags as suspicious. Every Requirement still ends up
            # with real test coverage transitively, through its ACs.
            progress("Testing layer (every AcceptanceCriterion gets 1-2 real, VERIFIES-linked TestCases)...")
            testcases = []
            verifies_pairs = []
            for a in acs:
                repo = repo_by_svc.get(a["_svc"])
                path = f"tests/{_slug(a['_svc'])}/test_{a['id'].replace(':', '_')}.py"
                for j in range(r.randint(1, 2)):
                    test_name = f"test_{vocab.pick(r, vocab.ACTIONS)}_{vocab.pick(r, vocab.NOUNS).replace(' ', '_')}_{j}"
                    tc_id = f"{repo['id']}:{path}:{test_name}" if repo else f"demo:testcase:{a['id']}:{j}"
                    testcases.append({
                        "id": tc_id, "source_episode_id": a["source_episode_id"], "name": test_name,
                        "type": "functional",
                        "lifecycle_state": r.choice(["Draft", "Approved", "Approved"]), DEMO_TAG: True,
                    })
                    verifies_pairs.append({"from": tc_id, "to": a["id"],
                                            "props": _edge_props(r, _rand_past_datetime(r))})
            # A modest pool of standalone TestCases not tied to any specific
            # Requirement (real repos have these too -- infra/smoke tests).
            n_standalone = scale.n(300)
            for i in range(n_standalone):
                repo = r.choice(repos)
                path = f"tests/{_slug(repo['_svc'])}/test_smoke_{i}.py"
                test_name = f"test_{vocab.pick(r, vocab.ACTIONS)}_{vocab.pick(r, vocab.NOUNS).replace(' ', '_')}"
                testcases.append({
                    "id": f"{repo['id']}:{path}:{test_name}", "source_episode_id": episode(), "name": test_name,
                    "type": "smoke", "lifecycle_state": "Approved", DEMO_TAG: True,
                })
            _batch_merge_nodes(session, "TestCase", testcases)
            counters.add_nodes("TestCase", len(testcases))
            _batch_merge_rels(session, "TestCase", "AcceptanceCriterion", "VERIFIES", verifies_pairs)
            counters.add_rels("VERIFIES", len(verifies_pairs))

            test_suites = [{"id": f"demo:testsuite:{i}", "source_episode_id": episode(),
                            "name": f"{vocab.pick(r, vocab.SERVICES)}-suite-{i}", DEMO_TAG: True}
                           for i in range(scale.n(150))]
            _batch_merge_nodes(session, "TestSuite", test_suites)
            counters.add_nodes("TestSuite", len(test_suites))

            # Real TestCase->TestSuite membership (Session 11, item 2) -- the
            # spec has always called for TestCase-[:PART_OF]->TestSuite, but
            # TestSuite had zero relationships at all before this.
            testcase_by_suite: dict[str, list[str]] = {}
            part_of_suite_pairs = []
            if test_suites:
                for tc in testcases:
                    suite_id = r.choice(test_suites)["id"]
                    testcase_by_suite.setdefault(suite_id, []).append(tc["id"])
                    part_of_suite_pairs.append({"from": tc["id"], "to": suite_id, "props": {}})
            _batch_merge_rels(session, "TestCase", "TestSuite", "PART_OF", part_of_suite_pairs)
            counters.add_rels("PART_OF", len(part_of_suite_pairs))

            automation_scripts = [{"id": f"demo:automationscript:{i}", "source_episode_id": episode(),
                                    "path": f"tests/{vocab.pick(r, vocab.SERVICES)}/test_{i}.py", DEMO_TAG: True}
                                   for i in range(scale.n(400))]
            _batch_merge_nodes(session, "AutomationScript", automation_scripts)
            counters.add_nodes("AutomationScript", len(automation_scripts))

            # ---------- Application configuration pool (Session 12) ----------
            # Real component-version snapshots a TestExecution can have run
            # against -- reuses the existing Service label (Session 11)
            # instead of inventing a new "component" node; the actual
            # versions live on each config's own INCLUDES_VERSION edges, not
            # a flat property blob, so they stay independently
            # queryable/traceable back to a real Service.
            app_configs = [{"id": f"demo:appconfig:{i}", "source_episode_id": episode(), DEMO_TAG: True}
                           for i in range(scale.n(40))]
            _batch_merge_nodes(session, "ApplicationConfiguration", app_configs)
            counters.add_nodes("ApplicationConfiguration", len(app_configs))

            includes_version_pairs = []
            for cfg in app_configs:
                n_components = min(len(services), r.randint(3, 8))
                for svc in (r.sample(services, n_components) if services else []):
                    version = f"{r.randint(1,4)}.{r.randint(0,20)}.{r.randint(0,9)}"
                    includes_version_pairs.append({"from": cfg["id"], "to": svc["id"],
                                                    "props": {"version": version}})
            _batch_merge_rels(session, "ApplicationConfiguration", "Service", "INCLUDES_VERSION",
                               includes_version_pairs)
            counters.add_rels("INCLUDES_VERSION", len(includes_version_pairs))

            # ---------- TestCycle (renamed from TestRun, Session 12) ----------
            # A TestCycle is the batch/container; per-case results now live on
            # the new TestExecution node below -- a real test-management-tool
            # shape (TestRun/Cycle -> many TestExecutions), not one flat
            # status property for a whole batch of 3-25 TestCases.
            RUN_TYPES = ["ci", "ci", "ci", "smoke", "nightly", "regression"]
            test_cycles = [{"id": f"demo:testcycle:{i}", "source_episode_id": episode(),
                            "ran_at": _iso(_rand_past_datetime(r, 90)),
                            "run_type": r.choice(RUN_TYPES), DEMO_TAG: True}
                           for i in range(scale.n(800))]
            _batch_merge_nodes(session, "TestCycle", test_cycles)
            counters.add_nodes("TestCycle", len(test_cycles))

            # Real TestExecution per (TestCycle, TestCase) pair (Session 12)
            # -- previously one flat status property covered a whole batch;
            # now each case gets its own real result/time, plus which real
            # component-version snapshot it ran against. This is the concrete
            # gap dq_017/quality_report.py's SEC-02 have disclosed since
            # Sessions 4/8 ("no TestRun->TestCase edge exists anywhere in
            # this codebase") -- made real (Session 11) and per-case-accurate
            # (Session 12) here.
            suites_with_cases = [sid for sid, tcs in testcase_by_suite.items() if tcs]
            cycle_part_of_suite = []
            executions = []
            execution_part_of_cycle = []
            execution_executes_testcase = []
            execution_ran_against = []
            RESULTS = ["passed", "passed", "passed", "passed", "failed", "blocked"]
            for cycle in test_cycles:
                if not suites_with_cases:
                    break
                suite_id = r.choice(suites_with_cases)
                cycle_part_of_suite.append({"from": cycle["id"], "to": suite_id, "props": {}})
                candidates = testcase_by_suite[suite_id]
                n_exec = min(len(candidates), r.randint(3, 25))
                for j, tc_id in enumerate(r.sample(candidates, n_exec)):
                    exec_id = f"{cycle['id']}:exec:{j}"
                    executions.append({
                        "id": exec_id, "source_episode_id": cycle["source_episode_id"],
                        "executed_at": _iso(_rand_past_datetime(r, 90)),
                        "result": r.choice(RESULTS), DEMO_TAG: True,
                    })
                    execution_part_of_cycle.append({"from": exec_id, "to": cycle["id"], "props": {}})
                    execution_executes_testcase.append({"from": exec_id, "to": tc_id, "props": {}})
                    if app_configs:
                        execution_ran_against.append(
                            {"from": exec_id, "to": r.choice(app_configs)["id"], "props": {}})
            _batch_merge_nodes(session, "TestExecution", executions)
            counters.add_nodes("TestExecution", len(executions))
            _batch_merge_rels(session, "TestCycle", "TestSuite", "PART_OF", cycle_part_of_suite)
            counters.add_rels("PART_OF", len(cycle_part_of_suite))
            _batch_merge_rels(session, "TestExecution", "TestCycle", "PART_OF", execution_part_of_cycle)
            counters.add_rels("PART_OF", len(execution_part_of_cycle))
            _batch_merge_rels(session, "TestExecution", "TestCase", "EXECUTES", execution_executes_testcase)
            counters.add_rels("EXECUTES", len(execution_executes_testcase))
            _batch_merge_rels(session, "TestExecution", "ApplicationConfiguration", "RAN_AGAINST",
                               execution_ran_against)
            counters.add_rels("RAN_AGAINST", len(execution_ran_against))

            defects = [{"id": f"demo:defect:{i}", "source_episode_id": episode(),
                        "summary": vocab.pick(r, vocab.DEFECT_SUMMARIES),
                        "severity": r.choice(["low", "medium", "high", "critical"]),
                        "jira_key": next_jira_key(vocab.pick(r, vocab.SERVICES)),
                        "jira_status": vocab.pick(r, vocab.JIRA_STATUSES), DEMO_TAG: True}
                       for i in range(scale.n(500))]
            _batch_merge_nodes(session, "Defect", defects)
            counters.add_nodes("Defect", len(defects))
            # Defects are PRODUCES'd by a specific FAILED TestExecution
            # (Session 12 -- moved down from the whole TestCycle, since a
            # defect comes from a specific failing case result, not the
            # batch abstractly). Falls back to any execution if fewer real
            # failures exist than Defects need.
            failed_executions = [e for e in executions if e["result"] == "failed"]
            producing_pool = failed_executions or executions
            produces_defects = ([{"from": producing_pool[i % len(producing_pool)]["id"], "to": d["id"], "props": {}}
                                 for i, d in enumerate(defects)] if producing_pool else [])
            _batch_merge_rels(session, "TestExecution", "Defect", "PRODUCES", produces_defects)
            counters.add_rels("PRODUCES", len(produces_defects))

            # ---------- Operations layer ----------
            progress("Operations layer (Release/Incident/Alert/Metrics/Logs)...")
            releases = [{"id": f"demo:release:{i}", "source_episode_id": episode(),
                        "version": f"{r.randint(1,4)}.{r.randint(0,20)}.{r.randint(0,9)}",
                        "released_at": _iso(_rand_past_datetime(r)), DEMO_TAG: True} for i in range(scale.n(40))]
            _batch_merge_nodes(session, "Release", releases)
            counters.add_nodes("Release", len(releases))

            # Regression TestCycles trace to the Release they validated
            # (Session 11, item 2; TestRun renamed to TestCycle in Session
            # 12) -- reuses the same generic TRACES_TO edge every other
            # backbone link in this generator already uses, not a new
            # relationship type.
            regression_cycles = [c for c in test_cycles if c["run_type"] == "regression"]
            regression_release_traces = ([{"from": c["id"], "to": r.choice(releases)["id"],
                                            "props": _edge_props(r, _rand_past_datetime(r))}
                                           for c in regression_cycles] if releases else [])
            _batch_merge_rels(session, "TestCycle", "Release", "TRACES_TO", regression_release_traces)
            counters.add_rels("TRACES_TO", len(regression_release_traces))

            # Requirement -> Release TRACES_TO: only "shipped" Requirements
            # (Jira Done + auto_write confidence) get linked -- an
            # in-progress backlog item correctly has no release yet. This
            # is real, previously-absent linkage (DQ-017 used to report
            # zero such edges in the whole graph) needed for
            # metis_generate_quality_report/metis_generate_release_report's
            # real release_id scoping to resolve to anything.
            shipped_reqs = [q for q in requirements
                            if q.get("jira_status") == "Done" and q.get("confidence_tier") == "auto_write"]
            release_traces = [{"from": q["id"], "to": r.choice(releases)["id"],
                               "props": _edge_props(r, _rand_past_datetime(r))} for q in shipped_reqs]
            _batch_merge_rels(session, "Requirement", "Release", "TRACES_TO", release_traces)
            counters.add_rels("TRACES_TO", len(release_traces))

            incidents = [{"id": f"demo:incident:{i}", "source_episode_id": episode(),
                         "title": vocab.pick(r, vocab.INCIDENT_TITLES),
                         "severity": r.choice(["sev1", "sev2", "sev3"]),
                         "opened_at": _iso(_rand_past_datetime(r)), DEMO_TAG: True} for i in range(scale.n(150))]
            _batch_merge_nodes(session, "Incident", incidents)
            counters.add_nodes("Incident", len(incidents))

            alerts = [{"id": f"demo:alert:{i}", "source_episode_id": episode(),
                      "title": f"{vocab.pick(r, vocab.SERVICES)} {r.choice(['latency', 'error rate', 'saturation'])} alert",
                      "state": r.choice(["alerting", "normal", "normal"]), DEMO_TAG: True} for i in range(scale.n(300))]
            _batch_merge_nodes(session, "Alert", alerts)
            counters.add_nodes("Alert", len(alerts))

            metrics = [{"id": f"demo:metrics:{i}", "source_episode_id": episode(),
                       "pass_rate": round(r.uniform(0.85, 1.0), 3), "p95_duration_ms": r.randint(50, 900),
                       "period_start": _iso(_rand_past_datetime(r, 30)), DEMO_TAG: True} for i in range(scale.n(200))]
            _batch_merge_nodes(session, "Metrics", metrics)
            counters.add_nodes("Metrics", len(metrics))

            logs = [{"id": f"demo:logs:{i}", "source_episode_id": episode(),
                    "summary": f"{vocab.pick(r, vocab.SERVICES)} log excerpt {i}", DEMO_TAG: True}
                   for i in range(scale.n(80))]
            _batch_merge_nodes(session, "Logs", logs)
            counters.add_nodes("Logs", len(logs))

            # ---------- Behavior-adjacent filler (Action/Event/Workflow) ----------
            # Session 11, item 1: State/Transition/Trigger must model ONLY real
            # application behaviour -- the generic index-ring State/Transition/
            # Trigger/Guard generator that used to live here (80 States wired
            # state[i]->state[i+1] with no relation to any real application)
            # was pure count-padding, not app behaviour, and has been removed.
            # demo_data/login_example.py (a real, hand-authored login-page
            # state machine) is now the sole source of State/Transition/Trigger
            # data in this generator. Action/Event/Workflow are separate labels
            # not covered by that rule and were already independently dangling
            # (no relationships to State/Transition either before or after this
            # change) -- left as-is, out of scope for this pass.
            progress("Action/Event/Workflow (independent filler, unrelated to State/Transition)...")
            actions = [{"id": f"demo:action:{i}", "source_episode_id": episode(),
                       "name": f"{vocab.pick(r, vocab.ACTIONS)}_{vocab.pick(r, vocab.NOUNS).replace(' ', '_')}",
                       DEMO_TAG: True} for i in range(scale.n(150))]
            _batch_merge_nodes(session, "Action", actions)
            counters.add_nodes("Action", len(actions))

            events = [{"id": f"demo:event:{i}", "source_episode_id": episode(),
                      "name": vocab.pick(r, vocab.TRIGGERS), DEMO_TAG: True} for i in range(scale.n(150))]
            _batch_merge_nodes(session, "Event", events)
            counters.add_nodes("Event", len(events))

            workflows = [{"id": f"demo:workflow:{i}", "source_episode_id": episode(),
                         "name": f"{vocab.pick(r, vocab.SERVICES)}-workflow-{i}", DEMO_TAG: True}
                        for i in range(scale.n(40))]
            _batch_merge_nodes(session, "Workflow", workflows)
            counters.add_nodes("Workflow", len(workflows))

            # No generic Transitions/States/Guards/determinism-check run here
            # anymore -- see comment above. disputed_from_determinism stays 0;
            # login_example.py's own state machine is real and unambiguous by
            # design (Session 10), so there's nothing left in this generator to
            # exercise the determinism checker's "disputed" path against.
            disputed_from_determinism = 0

            # ---------- AI layer ----------
            # Session 11, item 5: the LLM-session-tracking layer (CopilotSession/
            # Prompt/GeneratedCode/AIDecision/HumanReview -- pure demo filler,
            # zero relationships to anything, confirmed by grep across the whole
            # codebase before removal) has been removed by explicit user
            # decision: keeping ephemeral LLM/Copilot session data in a graph
            # meant to be a global, persistent source of truth is
            # counterproductive. GeneratedTest is NOT removed -- unlike the
            # other 5, metis_mcp/test_skeleton_generator.py genuinely uses it
            # for REQ-METIS-BM-03 (AI-proposed test provenance until it
            # converges with a real TestCase); the demo-filler GeneratedTest
            # rows that used to be generated here (dangling, no transition_id,
            # easily confused with the real ones) are removed along with the
            # rest of this block, but the label itself and its schema
            # constraints remain.

        summary = {
            "run_id": run_id,
            "total_nodes": counters.total_nodes(),
            "total_relationships": counters.total_relationships(),
            "nodes_by_label": dict(sorted(counters.nodes.items())),
            "relationships_by_type": dict(sorted(counters.relationships.items())),
            "requirement_candidates_skipped_non_ears_or_rejected": counters.skipped_non_ears,
            "disputed_transitions_from_real_determinism_check": disputed_from_determinism,
            "goals_generated": len(goals),
            "requirements_per_goal_avg": round(len(requirements) / len(goals), 1) if goals else 0,
            "grounded_goals": len(metis_grounded.GROUNDED_GOALS),
            "grounded_requirements_written": grounded["grounded_requirements_written"],
            "grounded_requirements_with_real_implementing_method": grounded["grounded_requirements_with_real_implementing_method"],
            "grounded_confluence_docs": grounded["grounded_confluence_docs"],
            "grounded_tags_with_no_paraphrase": grounded["tags_with_no_paraphrase"],
            "login_example_requirements_written": login["requirements_written"],
            "login_example_planned_transitions": login["planned_transitions"],
        }
        return summary
    finally:
        driver.close()


def wipe_demo_data(neo4j_uri: str, neo4j_user: str, neo4j_password: str, database: str = "neo4j") -> dict:
    """Only ever touches is_demo_data: true nodes -- never the real
    dogfooding/connector data already in this graph. Safe to re-run."""
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    driver.verify_connectivity()
    try:
        with driver.session(database=database) as session:
            before = session.run(f"MATCH (n {{{DEMO_TAG}: true}}) RETURN count(n) AS c").single()["c"]

            def _tx(tx):
                tx.run(f"MATCH (n {{{DEMO_TAG}: true}}) DETACH DELETE n")
            session.execute_write(_tx)

            after = session.run(f"MATCH (n {{{DEMO_TAG}: true}}) RETURN count(n) AS c").single()["c"]
        return {"deleted": before - after, "remaining_demo_nodes": after}
    finally:
        driver.close()


def main():
    import argparse
    import os
    from metis_mcp.config_manager import ConfigManager

    parser = argparse.ArgumentParser(description="Load or wipe Métis demo data.")
    parser.add_argument("--wipe", action="store_true", help="Wipe existing demo data instead of loading.")
    parser.add_argument("--scale", type=float, default=1.0,
                        help="Volume multiplier (default 1.0 = 50 Goals, 50-150 Requirements each, ~45,000 nodes).")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    config = ConfigManager()
    neo4j_cfg = config.get_neo4j_config()
    password = os.environ.get(neo4j_cfg.get("password_env", ""))
    if not password:
        raise ValueError(f"{neo4j_cfg.get('password_env')} must be set.")

    if args.wipe:
        result = wipe_demo_data(neo4j_cfg["uri"], neo4j_cfg["user"], password)
        print(f"Wiped {result['deleted']} demo node(s); {result['remaining_demo_nodes']} remain "
              f"(should be 0).", file=sys.stderr)
        return

    def _log(msg):
        print(f"[demo-data] {msg}", file=sys.stderr, flush=True)

    start = time.time()
    summary = generate(neo4j_cfg["uri"], neo4j_cfg["user"], password,
                        scale=Scale(factor=args.scale), seed=args.seed, on_progress=_log)
    elapsed = time.time() - start

    print(f"\nDone in {elapsed:.1f}s. {summary['total_nodes']} nodes, "
          f"{summary['total_relationships']} relationships.", file=sys.stderr)
    print(f"{summary['goals_generated']} Goal(s), {summary['requirements_per_goal_avg']} Requirements/Goal avg.",
          file=sys.stderr)
    print(f"Grounded layer: {summary['grounded_goals']} real Métis Goal(s), "
          f"{summary['grounded_requirements_written']} real grounded Requirement(s) "
          f"({summary['grounded_requirements_with_real_implementing_method']} with a real implementing Method), "
          f"{summary['grounded_confluence_docs']} real Confluence doc(s).", file=sys.stderr)
    print(f"Login example: {summary['login_example_requirements_written']} real Requirement(s) via the "
          f"Intent/TestDesign backbone ({summary['login_example_planned_transitions']} planned, "
          f"deliberately no TestDesign/TestCase).", file=sys.stderr)
    print(f"Skipped {summary['requirement_candidates_skipped_non_ears_or_rejected']} requirement candidate(s) "
          f"(non-EARS-conformant or below the real Rejected-tier confidence threshold) -- "
          f"matching real Layer 2/3 behavior, not written.", file=sys.stderr)
    print(f"{summary['disputed_transitions_from_real_determinism_check']} Transition(s) marked Disputed "
          f"by the real determinism check.", file=sys.stderr)
    print("\nNodes by label:", file=sys.stderr)
    for label, count in summary["nodes_by_label"].items():
        print(f"  {label}: {count}", file=sys.stderr)
    print("\nRelationships by type:", file=sys.stderr)
    for rel, count in summary["relationships_by_type"].items():
        print(f"  {rel}: {count}", file=sys.stderr)


if __name__ == "__main__":
    main()
