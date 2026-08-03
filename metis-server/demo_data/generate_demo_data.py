"""
Demo Data generator -- centered on the two REAL data sources this project
actually has, not a large fictional-company simulation:

  1. demo_data/login_example.py -- a real, hand-authored login-page state
     machine (State/Transition -> Intent -> Requirement/AcceptanceCriterion,
     Intent -> TestDesign -> TestCase), 16 implemented + 1 planned
     Transition, every Requirement real EARS-conformant text.
  2. demo_data/metis_grounded.py -- 75 real Requirements, one per
     REQ-METIS-* tag actually found in this repo's own corpus/*.md, real
     EARS-conformant paraphrases, IMPLEMENTS edges into the real,
     pre-existing (non-demo) Method pool this repo's own Cognify run
     populated, real Confluence Episodes from this repo's own README/PLAN/
     CLAUDE.md/docs/*.md.

Everything else in this module is a SMALL, coherent gap-fill layer --
order of 10s per label, not 1,000s -- covering the ontology labels neither
real source above touches (Architecture, VCS, Testing-bulk, Operations,
Governance). It exists to give those labels SOME real-shaped data to
exercise, not to simulate a fictional company at production scale. Every
gap-fill Service is keyed to one of metis_grounded.GROUNDED_GOALS' own 18
real domain prefixes (owner_team = that prefix) -- there is no separate,
disconnected fictional-company vocabulary anymore.

History: Sessions 3-12 built a large, fully-synthetic ~50-Goal/~5,000-
Requirement/~40,000-50,000-node fictional company on top of a small real
grounded layer. Session 13 reset this: the synthetic Business layer
(Goal->Capability->Epic->Feature->Requirement), the vocab.SERVICES-keyed
Architecture layer, the per-service Implementation (Class/Method) pool,
the synthetic Testing/Operations bulk, and the fully-disconnected Action/
Event/Workflow filler are all removed -- login_example.py and
metis_grounded.py are unchanged and remain the real backbone of this
dataset; the rest is now proportionate to them, not a separate simulation.

Real, not fabricated, in the ways that matter (unchanged discipline):
  - login_example.py's/metis_grounded.py's Requirement text is checked
    through the real, unmodified metis_mcp/ears_checker.py -- a
    non-conformant candidate is dropped, never force-tagged.
  - lifecycle_state comes from a real call to metis_mcp/
    confidence_tiering.py's ConfidenceTiering.evaluate().
  - Method/TestCase ids follow the real "repo:path:name" convention
    metis_mcp/pyramid_gap_check.py's Stage 3 coverage heuristic parses.
  - This gap-fill layer's own Database/Table writes call the real
    metis_mcp/temporal.py record_revision() -- the same real provenance
    discipline every other real write path in this project uses.

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
    """Multiplier knob for the gap-fill layer's own small counts (login_example.py
    and metis_grounded.py are real, fixed-size sources and are never scaled
    by this -- they always write their full real content regardless of
    factor). factor=1.0 is the real default shape (order of 10s per
    gap-fill label); a smaller factor shrinks it further for fast tests."""
    factor: float = 1.0

    def n(self, base: int) -> int:
        return max(1, round(base * self.factor))


@dataclass
class Counters:
    nodes: dict = field(default_factory=dict)
    relationships: dict = field(default_factory=dict)

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


def _project_code(name: str) -> str:
    """A real-looking Jira project-key prefix derived deterministically
    from a name, e.g. 'fraud-detection' -> 'FRAU'."""
    letters = name.replace("-", "").upper()
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

    def next_jira_key(name: str) -> str:
        code = _project_code(name)
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

            # domain_prefixes: the real 18 REQ-METIS-* subsystem prefixes
            # metis_grounded.py already grounds in this repo's own
            # corpus/*.md -- this gap-fill layer's Architecture Service
            # pool is keyed to these SAME prefixes (owner_team = prefix,
            # lowercase) so Service.owner_team genuinely matches a real
            # Goal.domain, instead of an unrelated fictional vocabulary.
            domain_prefixes = list(metis_grounded.GROUNDED_GOALS.keys())

            # ---------- Governance ----------
            progress("Governance...")
            _batch_merge_nodes(session, "Constitution", [{
                "id": "demo:constitution:1", "source_episode_id": episode(),
                "precedence_rank": 0, DEMO_TAG: True,
            }])
            counters.add_nodes("Constitution", 1)

            ext_api_specs = [{"id": f"demo:extapi:{i}", "source_episode_id": episode(),
                               "registry_source": r.choice(["swaggerhub", "apis.guru", "internal-registry"]),
                               "name": f"{r.choice(domain_prefixes).lower()}-external-api-v{r.randint(1,3)}",
                               DEMO_TAG: True} for i in range(scale.n(5))]
            _batch_merge_nodes(session, "ExternalAPISpec", ext_api_specs)
            counters.add_nodes("ExternalAPISpec", len(ext_api_specs))

            constraints = [{"id": f"demo:constraint:{i}", "source_episode_id": episode(),
                             "text": f"The {r.choice(domain_prefixes).lower()} subsystem must respond within "
                                     f"{r.choice([100, 200, 500])}ms.",
                             DEMO_TAG: True} for i in range(scale.n(10))]
            _batch_merge_nodes(session, "Constraint", constraints)
            counters.add_nodes("Constraint", len(constraints))

            business_rules = [{"id": f"demo:businessrule:{i}", "source_episode_id": episode(),
                                "text": f"{vocab.pick(r, vocab.NOUNS).capitalize()} totals must reconcile nightly.",
                                "corroboration_count": r.randint(1, 3), DEMO_TAG: True}
                               for i in range(scale.n(10))]
            _batch_merge_nodes(session, "BusinessRule", business_rules)
            counters.add_nodes("BusinessRule", len(business_rules))

            micro_requirements = [{"id": f"demo:microrequirement:{i}", "source_episode_id": episode(),
                                    "text": f"The {r.choice(domain_prefixes).lower()} subsystem shall "
                                            f"{vocab.pick(r, vocab.ACTIONS)} the {vocab.pick(r, vocab.NOUNS)}.",
                                    DEMO_TAG: True} for i in range(scale.n(5))]
            _batch_merge_nodes(session, "MicroRequirement", micro_requirements)
            counters.add_nodes("MicroRequirement", len(micro_requirements))

            # ---------- Grounded layer: real Métis project content ----------
            # Fixed, real content -- not scaled by `scale.factor` (a real
            # corpus, not a volume knob). See demo_data/metis_grounded.py.
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
            # Also fixed, real content -- not scaled by `scale.factor`.
            # See demo_data/login_example.py.
            progress("Login example (real Intent/TestDesign backbone, 16 implemented + 1 planned transition)...")
            login = login_example.build_login_example(
                session, r, episode, DEMO_TAG, _batch_merge_nodes, _batch_merge_rels, _edge_props,
                _iso, _rand_past_datetime,
            )
            for label, count in login["nodes"].items():
                counters.add_nodes(label, count)
            for rel_type, count in login["relationships"].items():
                counters.add_rels(rel_type, count)

            # ---------- Architecture layer: keyed to the real 18 metis_grounded domains ----------
            progress("Architecture layer (Service per real domain, API/Endpoint/Database/Table/...)...")
            services = [{"id": f"demo:service:{p.lower()}", "source_episode_id": episode(),
                         "name": f"{p.lower()}-service", "owner_team": p.lower(), DEMO_TAG: True}
                        for p in domain_prefixes]
            _batch_merge_nodes(session, "Service", services)
            counters.add_nodes("Service", len(services))

            apis = []
            for svc in services:
                for j in range(scale.n(2)):
                    apis.append({"id": f"{svc['id']}:api-{j}", "source_episode_id": svc["source_episode_id"],
                                 "name": f"{svc['name']}-api-v{j + 1}", "_service": svc["id"], DEMO_TAG: True})
            _batch_merge_nodes(session, "API", [{k: v for k, v in a.items() if k != "_service"} for a in apis])
            counters.add_nodes("API", len(apis))

            endpoints = []
            for a in apis:
                for j in range(scale.n(2)):
                    endpoints.append({"id": f"{a['id']}:endpoint-{j}", "source_episode_id": a["source_episode_id"],
                                      "path": f"/api/{_slug(a['name'])}/{vocab.pick(r, vocab.NOUNS).replace(' ', '-')}",
                                      "method": r.choice(["GET", "POST", "PUT", "DELETE"]), DEMO_TAG: True})
            _batch_merge_nodes(session, "Endpoint", endpoints)
            counters.add_nodes("Endpoint", len(endpoints))

            databases = [{"id": f"demo:database:{i}", "source_episode_id": episode(),
                          "name": f"{r.choice(domain_prefixes).lower()}-db-{i}", DEMO_TAG: True}
                         for i in range(scale.n(3))]
            _batch_merge_nodes(session, "Database", databases)
            counters.add_nodes("Database", len(databases))
            # Real revision history on every Database/Table write -- the
            # prerequisite for metis_mcp/graph_sync.py's staleness check to
            # mean anything for these labels.
            for db in databases:
                record_revision(session, db["id"], {"name": db["name"]}, db["source_episode_id"])
            counters.add_nodes("Revision", len(databases))
            counters.add_rels("HAS_REVISION", len(databases))

            tables = [{"id": f"demo:table:{i}", "source_episode_id": episode(),
                       "name": f"{vocab.pick(r, vocab.NOUNS).replace(' ', '_')}s",
                       "_database": r.choice(databases)["id"] if databases else None, DEMO_TAG: True}
                      for i in range(scale.n(10))]
            _batch_merge_nodes(session, "Table", [{k: v for k, v in t.items() if k != "_database"} for t in tables])
            counters.add_nodes("Table", len(tables))
            for tb in tables:
                record_revision(session, tb["id"], {"name": tb["name"]}, tb["source_episode_id"])
            counters.add_nodes("Revision", len(tables))
            counters.add_rels("HAS_REVISION", len(tables))

            # record_revision's real :Revision nodes don't carry is_demo_data
            # -- tag them here in one pass so wipe_demo_data and the
            # no-dangling-relationship invariant both hold.
            session.execute_write(lambda tx: tx.run(
                "MATCH (n) WHERE n.id STARTS WITH 'demo:database:' OR n.id STARTS WITH 'demo:table:' "
                "MATCH (n)-[:HAS_REVISION]->(rev:Revision) "
                f"SET rev.{DEMO_TAG} = true"
            ).consume())

            has_table_pairs = [{"from": t["_database"], "to": t["id"], "props": {}}
                                for t in tables if t["_database"]]
            _batch_merge_rels(session, "Database", "Table", "HAS", has_table_pairs)
            counters.add_rels("HAS", len(has_table_pairs))

            columns = [{"id": f"demo:column:{i}", "source_episode_id": episode(),
                        "name": r.choice(["id", "created_at", "status", "amount", "customer_id", "updated_at"]),
                        DEMO_TAG: True} for i in range(scale.n(30))]
            _batch_merge_nodes(session, "Column", columns)
            counters.add_nodes("Column", len(columns))

            for label, count in (("KafkaTopic", 5), ("ExternalSystem", 5)):
                rows = [{"id": f"demo:{label.lower()}:{i}", "source_episode_id": episode(),
                         "name": f"{r.choice(domain_prefixes).lower()}-{label.lower()}-{i}", DEMO_TAG: True}
                        for i in range(scale.n(count))]
                _batch_merge_nodes(session, label, rows)
                counters.add_nodes(label, len(rows))

            app_configs = [{"id": f"demo:appconfig:{i}", "source_episode_id": episode(), DEMO_TAG: True}
                           for i in range(scale.n(5))]
            _batch_merge_nodes(session, "ApplicationConfiguration", app_configs)
            counters.add_nodes("ApplicationConfiguration", len(app_configs))

            includes_version_pairs = []
            for cfg in app_configs:
                n_components = min(len(services), r.randint(2, 5))
                for svc in (r.sample(services, n_components) if services else []):
                    version = f"{r.randint(1,4)}.{r.randint(0,20)}.{r.randint(0,9)}"
                    includes_version_pairs.append({"from": cfg["id"], "to": svc["id"], "props": {"version": version}})
            _batch_merge_rels(session, "ApplicationConfiguration", "Service", "INCLUDES_VERSION",
                               includes_version_pairs)
            counters.add_rels("INCLUDES_VERSION", len(includes_version_pairs))

            # ---------- VCS ----------
            progress("VCS (PullRequest/Commit/Branch)...")
            prs = [{"id": f"demo:pr:{i}", "source_episode_id": episode(),
                    "title": f"{vocab.pick(r, vocab.ACTIONS).capitalize()} {vocab.pick(r, vocab.NOUNS)} "
                             f"in {r.choice(domain_prefixes).lower()}",
                    "merged_at": _iso(_rand_past_datetime(r)), DEMO_TAG: True} for i in range(scale.n(10))]
            _batch_merge_nodes(session, "PullRequest", prs)
            counters.add_nodes("PullRequest", len(prs))

            n_prs = len(prs)
            commits = [{"id": f"demo:commit:{i}", "source_episode_id": episode(),
                        "sha": f"{r.getrandbits(40):010x}", "authored_at": _iso(_rand_past_datetime(r)),
                        "_pr": prs[i % n_prs]["id"], DEMO_TAG: True} for i in range(scale.n(20))] if prs else []
            _batch_merge_nodes(session, "Commit", [{k: v for k, v in c.items() if k != "_pr"} for c in commits])
            counters.add_nodes("Commit", len(commits))
            _batch_merge_rels(session, "PullRequest", "Commit", "PRODUCES",
                               [{"from": c["_pr"], "to": c["id"], "props": _edge_props(r, _rand_past_datetime(r))}
                                for c in commits])
            counters.add_rels("PRODUCES", len(commits))

            branches = [{"id": f"demo:branch:{i}", "source_episode_id": episode(),
                         "name": f"feature/{vocab.pick(r, vocab.ACTIONS)}-{vocab.pick(r, vocab.NOUNS).replace(' ', '-')}",
                         DEMO_TAG: True} for i in range(scale.n(10))]
            _batch_merge_nodes(session, "Branch", branches)
            counters.add_nodes("Branch", len(branches))

            # ---------- Testing bulk: reuses the REAL TestCases login_example.py/metis_grounded.py already wrote ----------
            # No new TestCase pool -- every real TestCase in this graph
            # already came from one of the two real sources above; this
            # layer only adds the batch/execution machinery around them
            # (TestSuite/TestCycle/TestExecution/AutomationScript).
            progress("Testing bulk (TestSuite/TestCycle/TestExecution around the real TestCase pool)...")
            real_testcase_ids = [row["id"] for row in session.run(
                f"MATCH (tc:TestCase {{{DEMO_TAG}: true}}) RETURN tc.id AS id"
            ).data()]

            test_suites = [{"id": f"demo:testsuite:{i}", "source_episode_id": episode(),
                            "name": f"{r.choice(domain_prefixes).lower()}-suite-{i}", DEMO_TAG: True}
                           for i in range(scale.n(10))]
            _batch_merge_nodes(session, "TestSuite", test_suites)
            counters.add_nodes("TestSuite", len(test_suites))

            testcase_by_suite: dict[str, list[str]] = {}
            part_of_suite_pairs = []
            if test_suites and real_testcase_ids:
                for tc_id in real_testcase_ids:
                    suite_id = r.choice(test_suites)["id"]
                    testcase_by_suite.setdefault(suite_id, []).append(tc_id)
                    part_of_suite_pairs.append({"from": tc_id, "to": suite_id, "props": {}})
            _batch_merge_rels(session, "TestCase", "TestSuite", "PART_OF", part_of_suite_pairs)
            counters.add_rels("PART_OF", len(part_of_suite_pairs))

            automation_scripts = [{"id": f"demo:automationscript:{i}", "source_episode_id": episode(),
                                    "path": f"tests/{r.choice(domain_prefixes).lower()}/test_{i}.py", DEMO_TAG: True}
                                   for i in range(scale.n(10))]
            _batch_merge_nodes(session, "AutomationScript", automation_scripts)
            counters.add_nodes("AutomationScript", len(automation_scripts))

            RUN_TYPES = ["ci", "ci", "smoke", "nightly", "regression"]
            test_cycles = [{"id": f"demo:testcycle:{i}", "source_episode_id": episode(),
                            "ran_at": _iso(_rand_past_datetime(r, 90)),
                            "run_type": r.choice(RUN_TYPES), DEMO_TAG: True}
                           for i in range(scale.n(15))]
            _batch_merge_nodes(session, "TestCycle", test_cycles)
            counters.add_nodes("TestCycle", len(test_cycles))

            suites_with_cases = [sid for sid, tcs in testcase_by_suite.items() if tcs]
            cycle_part_of_suite = []
            executions = []
            execution_part_of_cycle = []
            execution_executes_testcase = []
            execution_ran_against = []
            RESULTS = ["passed", "passed", "passed", "failed", "blocked"]
            for cycle in test_cycles:
                if not suites_with_cases:
                    break
                suite_id = r.choice(suites_with_cases)
                cycle_part_of_suite.append({"from": cycle["id"], "to": suite_id, "props": {}})
                candidates = testcase_by_suite[suite_id]
                n_exec = min(len(candidates), r.randint(2, 8))
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

            # ---------- Operations layer ----------
            progress("Operations layer (Release/Incident/Alert/Metrics/Logs/Defect)...")
            releases = [{"id": f"demo:release:{i}", "source_episode_id": episode(),
                        "version": f"{r.randint(1,4)}.{r.randint(0,20)}.{r.randint(0,9)}",
                        "released_at": _iso(_rand_past_datetime(r)), DEMO_TAG: True} for i in range(scale.n(5))]
            _batch_merge_nodes(session, "Release", releases)
            counters.add_nodes("Release", len(releases))

            regression_cycles = [c for c in test_cycles if c["run_type"] == "regression"]
            regression_release_traces = ([{"from": c["id"], "to": r.choice(releases)["id"],
                                            "props": _edge_props(r, _rand_past_datetime(r))}
                                           for c in regression_cycles] if releases else [])
            _batch_merge_rels(session, "TestCycle", "Release", "TRACES_TO", regression_release_traces)
            counters.add_rels("TRACES_TO", len(regression_release_traces))

            # Requirement -> Release TRACES_TO: the real substitute for the
            # removed synthetic layer's "shipped" Requirements -- draws from
            # metis_grounded.py's own real Requirements already carrying
            # jira_status: 'Done' (written above, not new). Needed for
            # metis_generate_release_report's real release_id scoping to
            # resolve to anything (dq_017's long-standing "zero such edges"
            # note).
            shipped_req_ids = [row["id"] for row in session.run(
                "MATCH (req:Requirement {source_kind: 'metis_project', jira_status: 'Done'}) "
                "RETURN req.id AS id"
            ).data()]
            release_traces = ([{"from": rid, "to": r.choice(releases)["id"],
                               "props": _edge_props(r, _rand_past_datetime(r))} for rid in shipped_req_ids]
                              if releases else [])
            _batch_merge_rels(session, "Requirement", "Release", "TRACES_TO", release_traces)
            counters.add_rels("TRACES_TO", len(release_traces))

            incidents = [{"id": f"demo:incident:{i}", "source_episode_id": episode(),
                         "title": vocab.pick(r, vocab.INCIDENT_TITLES),
                         "severity": r.choice(["sev1", "sev2", "sev3"]),
                         "opened_at": _iso(_rand_past_datetime(r)), DEMO_TAG: True} for i in range(scale.n(5))]
            _batch_merge_nodes(session, "Incident", incidents)
            counters.add_nodes("Incident", len(incidents))

            alerts = [{"id": f"demo:alert:{i}", "source_episode_id": episode(),
                      "title": f"{r.choice(domain_prefixes).lower()} {r.choice(['latency', 'error rate', 'saturation'])} alert",
                      "state": r.choice(["alerting", "normal", "normal"]), DEMO_TAG: True} for i in range(scale.n(5))]
            _batch_merge_nodes(session, "Alert", alerts)
            counters.add_nodes("Alert", len(alerts))

            metrics = [{"id": f"demo:metrics:{i}", "source_episode_id": episode(),
                       "pass_rate": round(r.uniform(0.85, 1.0), 3), "p95_duration_ms": r.randint(50, 900),
                       "period_start": _iso(_rand_past_datetime(r, 30)), DEMO_TAG: True} for i in range(scale.n(5))]
            _batch_merge_nodes(session, "Metrics", metrics)
            counters.add_nodes("Metrics", len(metrics))

            logs = [{"id": f"demo:logs:{i}", "source_episode_id": episode(),
                    "summary": f"{r.choice(domain_prefixes).lower()} log excerpt {i}", DEMO_TAG: True}
                   for i in range(scale.n(5))]
            _batch_merge_nodes(session, "Logs", logs)
            counters.add_nodes("Logs", len(logs))

            defects = [{"id": f"demo:defect:{i}", "source_episode_id": episode(),
                        "summary": vocab.pick(r, vocab.DEFECT_SUMMARIES),
                        "severity": r.choice(["low", "medium", "high", "critical"]),
                        "jira_key": next_jira_key(r.choice(domain_prefixes)),
                        "jira_status": vocab.pick(r, vocab.JIRA_STATUSES), DEMO_TAG: True}
                       for i in range(scale.n(10))]
            _batch_merge_nodes(session, "Defect", defects)
            counters.add_nodes("Defect", len(defects))
            # A Defect is PRODUCES'd by a specific FAILED TestExecution --
            # matches the real per-case-result convention (a defect comes
            # from a specific failing case, not a batch abstractly). Falls
            # back to any execution if fewer real failures exist than
            # Defects need.
            failed_executions = [e for e in executions if e["result"] == "failed"]
            producing_pool = failed_executions or executions
            produces_defects = ([{"from": producing_pool[i % len(producing_pool)]["id"], "to": d["id"], "props": {}}
                                 for i, d in enumerate(defects)] if producing_pool else [])
            _batch_merge_rels(session, "TestExecution", "Defect", "PRODUCES", produces_defects)
            counters.add_rels("PRODUCES", len(produces_defects))

        summary = {
            "run_id": run_id,
            "total_nodes": counters.total_nodes(),
            "total_relationships": counters.total_relationships(),
            "nodes_by_label": dict(sorted(counters.nodes.items())),
            "relationships_by_type": dict(sorted(counters.relationships.items())),
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
                        help="Multiplier for the small gap-fill layer only (default 1.0). "
                             "login_example.py/metis_grounded.py always write their full real content.")
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
    print(f"Grounded layer: {summary['grounded_goals']} real Métis Goal(s), "
          f"{summary['grounded_requirements_written']} real grounded Requirement(s) "
          f"({summary['grounded_requirements_with_real_implementing_method']} with a real implementing Method), "
          f"{summary['grounded_confluence_docs']} real Confluence doc(s).", file=sys.stderr)
    print(f"Login example: {summary['login_example_requirements_written']} real Requirement(s) via the "
          f"Intent/TestDesign backbone ({summary['login_example_planned_transitions']} planned, "
          f"deliberately no TestDesign/TestCase).", file=sys.stderr)
    print("\nNodes by label:", file=sys.stderr)
    for label, count in summary["nodes_by_label"].items():
        print(f"  {label}: {count}", file=sys.stderr)
    print("\nRelationships by type:", file=sys.stderr)
    for rel, count in summary["relationships_by_type"].items():
        print(f"  {rel}: {count}", file=sys.stderr)


if __name__ == "__main__":
    main()
