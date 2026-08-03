"""
Stage 3 of the Behavior Model test pipeline (docs/metis-behavior-model-test-pipeline.md
§3): "before generating anything, query what already exists for this
Transition's implementing Method" -- generation must be additive on top of
whatever unit/integration coverage already exists, never redundant with it.

REQ-METIS-PG-01: generation never fires for a layer that's already covered.

Session 10: TestCase.type is now a real 6-value taxonomy (`unit`,
`integration`, `api_functional`, `web_functional`, `e2e`, `performance`)
-- previously neither :TestCase nor :Method carried an explicit `layer`
property anywhere in this schema or any connector that writes them, so
this module used a purely heuristic signal. That heuristic isn't gone --
it's now the disclosed FALLBACK for real, already-ingested data that
predates this taxonomy (`connectors/test_suite_connector.py` never sets
`.type` at all):

  unit / integration:  prefer TestCase.type == 'unit'/'integration' when
                        set; fall back to the original id-prefix heuristic
                        (same "repo:path" match as the implementing
                        Method's id) when `.type` is absent.
  api_functional /
  web_functional / e2e: TestCase --VERIFIES--> AcceptanceCriterion
                        <--HAS_AC-- Requirement <--IMPLEMENTS-- implementing
                        Method (VERIFIES targets AcceptanceCriterion, never
                        Requirement directly -- Requirement<-VERIFIES-TestCase
                        with no HAS_AC in between is the exact anti-pattern
                        metis_mcp/layer8_heuristics.py's DQ-018 check
                        already flags as suspicious), split by real
                        TestCase.type. A match with no `.type` set at all
                        (real legacy data) defaults to `api_functional` --
                        a disclosed, deliberate legacy mapping (test_suite_
                        connector.py ingests this platform's own backend
                        Python test suite, not browser/UI tests), not a
                        guess presented as precise.
  performance:          TestCase.type == 'performance' (locust-performance
                        connector tags this -- connectors/locust_performance_connector.py)
                        anywhere in the same repository as the implementing Method.
                        Unchanged from before this session.

Realistic test-pyramid economics, not "every layer for every transition":
`unit`/`integration`/one functional layer are always relevant (gap-checked
for every determinable Transition); `e2e`/`performance` only matter for a
Transition on a critical/hot path -- `performance_sla_critical` is reused
here to also mean "critical path", not only "needs a performance test"
(a deliberate, disclosed extension of what that property already meant,
not a new property).

Every result reports `determinable=False` (not a false "no coverage")
when the Transition carries no `implementing_method_id` claim at all --
absence of a claim is a different, honest fact from absence of coverage.
"""
from dataclasses import dataclass, field


LAYERS = ("unit", "integration", "api_functional", "web_functional", "e2e", "performance")
_FUNCTIONAL_LAYERS = ("api_functional", "web_functional", "e2e")


@dataclass
class PyramidGapResult:
    transition_id: str
    determinable: bool
    reason: str
    implementing_method_id: str | None = None
    performance_sla_critical: bool = False
    coverage: dict = field(default_factory=dict)       # layer -> bool
    covering_test_ids: dict = field(default_factory=dict)  # layer -> list[str]
    gaps: list = field(default_factory=list)            # layers needing generation


def _parse_repo_path(node_id: str) -> tuple[str, str] | None:
    """Method/TestCase ids are both real "repo:path:name" strings (verified
    against cognify/structural_extraction.py and connectors/test_suite_connector.py/
    locust_performance_connector.py) -- split(':', 2) recovers repo/path
    without needing a separate source_file property, which isn't
    consistently set on TestCase nodes."""
    parts = node_id.split(":", 2)
    if len(parts) != 3:
        return None
    return parts[0], parts[1]


def check_pyramid_gaps(session, transition_id: str) -> PyramidGapResult:
    rec = session.run(
        "MATCH (t:Transition {id: $id}) RETURN t.implementing_method_id AS method_id, "
        "t.performance_sla_critical AS perf_critical",
        id=transition_id,
    ).single()
    if rec is None:
        return PyramidGapResult(
            transition_id=transition_id, determinable=False,
            reason=f"No Transition '{transition_id}' exists in the graph.",
        )

    method_id = rec["method_id"]
    perf_critical = bool(rec["perf_critical"])
    if not method_id:
        return PyramidGapResult(
            transition_id=transition_id, determinable=False,
            reason="This Transition carries no implementing_method_id claim -- Stage 3 "
                   "cannot compute pyramid coverage without knowing which Method implements "
                   "it. This is a missing claim, not a claim of zero coverage.",
            performance_sla_critical=perf_critical,
        )

    repo_path = _parse_repo_path(method_id)
    if repo_path is None:
        return PyramidGapResult(
            transition_id=transition_id, determinable=False,
            reason=f"implementing_method_id '{method_id}' does not match the real "
                   f"'repo:path:name' id convention -- cannot derive repo/path for coverage lookup.",
            implementing_method_id=method_id, performance_sla_critical=perf_critical,
        )
    repo, path = repo_path

    coverage = {layer: False for layer in LAYERS}
    covering: dict = {layer: [] for layer in LAYERS}

    # unit: real TestCase.type == 'unit' ANYWHERE in the same repo (the
    # real property is authoritative, not scoped to an exact path -- a
    # real project may keep unit tests in a tests/unit/ folder separate
    # from src/), OR -- only for untyped legacy data -- the original
    # id-prefix heuristic (exact same repo:path as the implementing Method).
    unit_prefix = f"{repo}:{path}:"
    repo_prefix = f"{repo}:"
    for r in session.run(
        "MATCH (tc:TestCase) WHERE "
        "(tc.type = 'unit' AND tc.id STARTS WITH $repo_prefix) OR "
        "(tc.type IS NULL AND tc.id STARTS WITH $unit_prefix) "
        "RETURN tc.id AS id",
        repo_prefix=repo_prefix, unit_prefix=unit_prefix,
    ):
        coverage["unit"] = True
        covering["unit"].append(r["id"])

    # integration: real TestCase.type == 'integration' anywhere in the
    # repo, OR -- untyped legacy data only -- same repo, different path
    # (coarse, disclosed above).
    for r in session.run(
        "MATCH (tc:TestCase) WHERE "
        "(tc.type = 'integration' AND tc.id STARTS WITH $repo_prefix) OR "
        "(tc.type IS NULL AND tc.id STARTS WITH $repo_prefix AND NOT tc.id STARTS WITH $unit_prefix) "
        "RETURN tc.id AS id",
        repo_prefix=repo_prefix, unit_prefix=unit_prefix,
    ):
        coverage["integration"] = True
        covering["integration"].append(r["id"])

    # api_functional / web_functional / e2e: TestCase --VERIFIES--> AcceptanceCriterion
    # <--HAS_AC-- Requirement <--IMPLEMENTS-- implementing Method, split by
    # real TestCase.type -- untyped matches default to api_functional (see
    # module docstring for why that specific default, not a guess).
    for r in session.run(
        "MATCH (m:Method {id: $method_id})-[:IMPLEMENTS]->(req:Requirement)-[:HAS_AC]->(:AcceptanceCriterion)"
        "<-[:VERIFIES]-(tc:TestCase) "
        "RETURN DISTINCT tc.id AS id, tc.type AS type",
        method_id=method_id,
    ):
        layer = r["type"] if r["type"] in _FUNCTIONAL_LAYERS else "api_functional"
        coverage[layer] = True
        covering[layer].append(r["id"])

    # performance: only relevant when the Transition is SLA-critical (CONST-021/044).
    if perf_critical:
        for r in session.run(
            "MATCH (tc:TestCase {type: 'performance'}) WHERE tc.id STARTS WITH $repo_prefix "
            "RETURN tc.id AS id",
            repo_prefix=repo_prefix,
        ):
            coverage["performance"] = True
            covering["performance"].append(r["id"])

    # unit/integration/one-functional-layer are always relevant; e2e and
    # performance only for a critical-path Transition (performance_sla_critical
    # reused to mean "critical path" here, not only "needs a perf test").
    functional_layer_for_gap = "web_functional" if coverage["web_functional"] and not coverage["api_functional"] else "api_functional"
    relevant_layers = ["unit", "integration", functional_layer_for_gap]
    if perf_critical:
        relevant_layers += ["e2e", "performance"]
    gaps = [layer for layer in relevant_layers if not coverage[layer]]

    return PyramidGapResult(
        transition_id=transition_id, determinable=True,
        reason="Coverage computed from real TestCase.type (preferred) or id-prefix/"
               "IMPLEMENTS/HAS_AC/VERIFIES structure (fallback for untyped legacy data) "
               "-- per REQ-METIS-PG-01, gapped layers only are what's returned for "
               "generation; already-covered layers are skipped regardless of test age "
               "(DQ-009 staleness is a separate, not-yet-built check, not duplicated here).",
        implementing_method_id=method_id, performance_sla_critical=perf_critical,
        coverage=coverage, covering_test_ids=covering, gaps=gaps,
    )
