"""
Phase 8: State-machine well-formedness checks (CONST-048/049,
REQ-METIS-BM-04) -- determinism, completeness, reachability, implemented
as real Cypher queries against a real Transition graph, per
metis-standards-integration.md §2's UML Behavior State Machine grounding.
Deterministic graph algorithms, not LLM judgment, per §9's code-vs-LLM
allocation ("reachability is literally graph traversal").

MicroRequirement decomposition (metis_mcp/microrequirement.py) and the
Layer 6 LLM-as-judge (metis_mcp/llm_judge.py) are built separately -- both
genuinely need a real model call, made via the `claude` CLI (no
ANTHROPIC_API_KEY needed; see metis_mcp/llm_client.py). This module covers
the deterministic checks specifically, per §9's code-vs-LLM allocation.

REQ-METIS-BM-01's code-graph corroboration (below,
`corroborate_transition`) is also deterministic -- it checks whether a
Transition's claimed implementing Method actually has the real CALLS
edges it claims, via cognify/code_graph_archaeology.py's real graph. A
mismatch is a real disagreement between spec and code, surfaced the same
way as any other contradiction (CONST-046/049) -- never silently resolved
toward either side.

Entities/relationships (schema-01 declares State/Transition as real
labels; Trigger/Guard were removed as separate node types in a later
session -- both are attributes of exactly one Transition, not their own
entities, so they live as plain properties on Transition instead).
WHEN/THEN (renamed from FROM_STATE/TO_STATE, then LAUNCHES/LANDS_IN, in a
later session -- mirrors the Given/When/Then shape a Transition already
structurally is: the State it's reached from is the implicit "Given",
WHEN it fires is this edge, THEN this State results is the other) read
as one continuous forward path, State to State, through the Transition --
not two edges both originating at the Transition:
  (:State)-[:WHEN]->(:Transition)-[:THEN]->(:State)
  (:Transition {trigger, guard_expression})

Per CONST-049: a determinism/completeness violation is surfaced as a
Disputed-adjacent flag on the affected nodes (lifecycle_state='Disputed',
reusing Phase 4's own vocabulary), never silently resolved by picking one
interpretation.
"""
import re
from dataclasses import dataclass, field

_THRESHOLD_RE = re.compile(r"^\s*(?P<var>\w+)\s*(?P<op>>=|<=|==|>|<)\s*(?P<num>-?\d+(?:\.\d+)?)\s*$")


def _parse_guard(expression: str):
    """Returns (var, op, num) for a simple '<var> <op> <num>' guard, or
    None if the expression doesn't match this shape -- callers must treat
    None as 'cannot verify', not 'assume safe' (fail-closed, matching this
    project's classification_gate.py precedent)."""
    m = _THRESHOLD_RE.match(expression)
    if not m:
        return None
    return m.group("var"), m.group("op"), float(m.group("num"))


@dataclass
class _Bound:
    lower: float
    lower_inclusive: bool
    upper: float
    upper_inclusive: bool


def _interval_for(op: str, num: float) -> _Bound:
    if op == ">":
        return _Bound(num, False, float("inf"), True)
    if op == ">=":
        return _Bound(num, True, float("inf"), True)
    if op == "<":
        return _Bound(float("-inf"), True, num, False)
    if op == "<=":
        return _Bound(float("-inf"), True, num, True)
    return _Bound(num, True, num, True)  # ==


def _intervals_overlap(a: _Bound, b: _Bound) -> bool:
    """Real number-line overlap, respecting strict vs. non-strict bounds --
    a real bug found while testing this: treating '<' and '<=' as the same
    (both closed) meant 'confidence < 0.6' and 'confidence >= 0.6' -- a
    clean, non-overlapping partition exactly at 0.6 -- were wrongly
    reported as overlapping at the boundary point."""
    if a.lower > b.upper or b.lower > a.upper:
        return False
    if a.lower == b.upper and not (a.lower_inclusive and b.upper_inclusive):
        return False
    if b.lower == a.upper and not (b.lower_inclusive and a.upper_inclusive):
        return False
    return True


@dataclass
class GuardOverlapFinding:
    transition_a: str
    transition_b: str
    trigger: str
    guard_a: str
    guard_b: str
    verifiably_overlapping: bool
    reason: str


@dataclass
class DeterminismResult:
    deterministic: bool
    findings: list[GuardOverlapFinding] = field(default_factory=list)


def guards_conflict(guard_a: str, guard_b: str) -> tuple[bool, str]:
    """Real, bounded overlap check for simple numeric-threshold guards
    (the shape this project's own confidence-tiering boundaries use, e.g.
    'confidence >= 0.9'). Guards outside this shape are conservatively
    flagged as unverifiable-but-potentially-ambiguous, never silently
    assumed safe -- fail-closed, same discipline as classification_gate.py."""
    parsed_a, parsed_b = _parse_guard(guard_a), _parse_guard(guard_b)
    if parsed_a is None or parsed_b is None:
        return True, (
            f"Guard '{guard_a}' or '{guard_b}' is not a simple threshold expression this "
            f"checker can verify as mutually exclusive -- flagged conservatively, not assumed safe."
        )
    var_a, op_a, num_a = parsed_a
    var_b, op_b, num_b = parsed_b
    if var_a != var_b:
        return True, f"Guards reference different variables ('{var_a}' vs '{var_b}') -- cannot verify exclusivity."
    overlap = _intervals_overlap(_interval_for(op_a, num_a), _interval_for(op_b, num_b))
    if overlap:
        return True, f"'{guard_a}' and '{guard_b}' have overlapping satisfying ranges for '{var_a}'."
    return False, f"'{guard_a}' and '{guard_b}' are provably mutually exclusive on '{var_a}'."


def _guard_coverage_gap(guards: list[str]) -> str | None:
    """The completeness-side sibling of guards_conflict()'s atomicity
    check: given guard expressions that all share the same (from_state,
    trigger), returns a gap-description string if they do NOT jointly
    cover the full range of their variable, or None if they do. Reuses
    the same interval representation guards_conflict() builds -- checking
    for a GAP is the natural complement of checking for an OVERLAP. Same
    fail-closed discipline: an unparseable guard, or guards on different
    variables, is flagged as unverifiable, never assumed complete."""
    parsed = [(g, _parse_guard(g)) for g in guards]
    unparseable = [g for g, p in parsed if p is None]
    if unparseable:
        return (f"guard(s) not simple threshold expressions this checker can verify as jointly "
                 f"exhaustive: {unparseable} -- flagged conservatively, not assumed complete")
    variables = {p[0] for _, p in parsed}
    if len(variables) > 1:
        return f"guards reference different variables ({sorted(variables)}) -- cannot verify joint completeness"
    var = next(iter(variables))
    intervals = sorted(
        (_interval_for(op, num) for _, (_, op, num) in parsed),
        key=lambda b: (b.lower, 0 if b.lower_inclusive else 1),
    )
    frontier, frontier_inclusive = float("-inf"), True
    for iv in intervals:
        gap = iv.lower > frontier or (
            iv.lower == frontier and not frontier_inclusive and not iv.lower_inclusive
        )
        if gap:
            return f"gap in guard coverage for '{var}' around {frontier} -- a real input there matches no transition"
        if (iv.upper, iv.upper_inclusive) > (frontier, frontier_inclusive):
            frontier, frontier_inclusive = iv.upper, iv.upper_inclusive
    if frontier != float("inf"):
        return f"no guard covers '{var}' above {frontier} -- a real input there matches no transition"
    return None


@dataclass
class GuardCoverageGap:
    from_state: str
    trigger: str
    transition_ids: list[str]
    guards: list[str]
    reason: str


def check_guard_completeness(session) -> list[GuardCoverageGap]:
    """Not one of CONST-048/049's original determinism/completeness
    checks -- a real, requested extension: for every (from_state,
    trigger) with >=2 real Transitions, verifies their guards jointly
    cover the whole domain, not just that they don't overlap
    (check_determinism's job). A real input matching none of the guards
    would silently match no transition at all -- undefined behavior
    that's currently invisible anywhere in the graph. Only ever checks
    groups of >=2 -- a lone transition's guard has nothing to jointly
    cover WITH, and "does every state/trigger have a transition at all"
    is check_completeness()'s job, not this one's."""
    rows = session.run(
        """
        MATCH (s:State)-[:WHEN]->(t:Transition)
        WHERE t.trigger IS NOT NULL AND t.guard_expression IS NOT NULL
        RETURN s.id AS from_state, t.trigger AS trigger, t.id AS transition_id,
               t.guard_expression AS guard
        """
    ).data()

    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row["from_state"], row["trigger"]), []).append(row)

    findings = []
    for (from_state, trigger), members in groups.items():
        if len(members) < 2:
            continue
        reason = _guard_coverage_gap([m["guard"] for m in members])
        if reason:
            findings.append(GuardCoverageGap(
                from_state=from_state, trigger=trigger,
                transition_ids=[m["transition_id"] for m in members],
                guards=[m["guard"] for m in members], reason=reason,
            ))
    return findings


def load_transition(session, transition_id: str, source_episode_id: str, from_state: str,
                     to_state: str, trigger: str, guard_expression: str,
                     implementing_method_id: str | None = None,
                     performance_sla_critical: bool = False) -> None:
    """MERGE-based, idempotent -- reusable for any real Transition set, not
    tied to a specific illustrative scenario.

    implementing_method_id (optional): the real Method this Transition's
    behavior is implemented by -- used by Stage 3's Pyramid-Gap Check
    (metis_mcp/pyramid_gap_check.py) to find existing test coverage via
    real CALLS/VERIFIES edges. Not validated against the graph here (that's
    REQ-METIS-BM-01's job, metis_mcp/behavior_model.py's own
    corroborate_transition) -- this just records the claim.

    performance_sla_critical: per metis-behavior-model-test-pipeline.md
    §3, gates whether Stage 3 also proposes a performance test skeleton."""
    def _write(tx):
        tx.run(
            """
            MERGE (from:State {id: $from_state}) ON CREATE SET from.source_episode_id = $episode
            MERGE (to:State {id: $to_state}) ON CREATE SET to.source_episode_id = $episode
            MERGE (t:Transition {id: $transition_id})
            SET t.source_episode_id = $episode,
                t.trigger = $trigger,
                t.guard_expression = $guard_expression,
                t.implementing_method_id = $implementing_method_id,
                t.performance_sla_critical = $performance_sla_critical
            MERGE (from)-[:WHEN]->(t)
            MERGE (t)-[:THEN]->(to)
            """,
            transition_id=transition_id, episode=source_episode_id, from_state=from_state,
            to_state=to_state, trigger=trigger, guard_expression=guard_expression,
            implementing_method_id=implementing_method_id,
            performance_sla_critical=performance_sla_critical,
        )
    session.execute_write(_write)


def check_determinism(session, state_id: str) -> DeterminismResult:
    """CONST-048/REQ-METIS-BM-04: no two Transitions from the same source
    State should fire on the same Trigger with overlapping Guards."""
    rows = session.run(
        """
        MATCH (s:State {id: $state_id})-[:WHEN]->(t1:Transition)
        MATCH (s)-[:WHEN]->(t2:Transition)
        WHERE t1.id < t2.id AND t1.trigger = t2.trigger
        RETURN t1.id AS t1_id, t2.id AS t2_id, t1.trigger AS trigger_id,
               t1.guard_expression AS g1_expr, t2.guard_expression AS g2_expr
        """,
        state_id=state_id,
    ).data()

    findings = []
    for row in rows:
        conflicts, reason = guards_conflict(row["g1_expr"], row["g2_expr"])
        if conflicts:
            findings.append(GuardOverlapFinding(
                transition_a=row["t1_id"], transition_b=row["t2_id"], trigger=row["trigger_id"],
                guard_a=row["g1_expr"], guard_b=row["g2_expr"],
                verifiably_overlapping=conflicts, reason=reason,
            ))

    if findings:
        # CONST-049: surfaced as Disputed, not silently resolved.
        def _mark(tx):
            for f in findings:
                tx.run(
                    "MATCH (t:Transition) WHERE t.id IN [$a, $b] "
                    "SET t.lifecycle_state = 'Disputed', t.dispute_reason = $reason",
                    a=f.transition_a, b=f.transition_b, reason=f.reason,
                )
        session.execute_write(_mark)

    return DeterminismResult(deterministic=not findings, findings=findings)


@dataclass
class CompletenessGap:
    state_id: str
    trigger_id: str


def check_completeness(session) -> list[CompletenessGap]:
    """Every State should have a defined Transition for every Trigger used
    anywhere in the set. Operationalized exactly as §2 defines it: the
    full Trigger vocabulary is whatever's actually used across this
    Transition set (not an externally-imposed list)."""
    gaps = session.run(
        """
        MATCH (any:Transition) WHERE any.trigger IS NOT NULL
        WITH DISTINCT any.trigger AS trigger
        MATCH (s:State)
        WHERE NOT EXISTS {
            MATCH (s)-[:WHEN]->(t:Transition) WHERE t.trigger = trigger
        }
        RETURN s.id AS state_id, trigger AS trigger_id
        ORDER BY state_id, trigger_id
        """
    ).data()
    return [CompletenessGap(g["state_id"], g["trigger_id"]) for g in gaps]


def check_reachability(session, initial_state_id: str) -> list[str]:
    """Every State should be reachable from the initial State via some
    directed path of Transitions. Returns the ids of unreachable States.

    Implemented as one real Cypher query to fetch the actual (from, to)
    edge pairs, then BFS in Python, rather than a Cypher variable-length
    path pattern -- WHEN/THEN both point forward (State ->
    Transition -> State), so a directed multi-hop pattern would be valid
    here, but per-edge fetch + Python BFS is kept for one real reason
    beyond directionality: it lets the algorithm report the FULL set of
    unreachable states in one pass, where a Cypher shortestPath/reachability
    pattern would need a separate query per candidate state. Deterministic
    graph algorithm either way, not LLM judgment, per §9's allocation."""
    all_states = {r["id"] for r in session.run("MATCH (s:State) RETURN s.id AS id").data()}
    edges = session.run(
        """
        MATCH (a:State)-[:WHEN]->(t:Transition)-[:THEN]->(b:State)
        RETURN a.id AS from_id, b.id AS to_id
        """
    ).data()

    adjacency: dict[str, list[str]] = {}
    for e in edges:
        adjacency.setdefault(e["from_id"], []).append(e["to_id"])

    visited = {initial_state_id}
    frontier = [initial_state_id]
    while frontier:
        current = frontier.pop()
        for neighbor in adjacency.get(current, []):
            if neighbor not in visited:
                visited.add(neighbor)
                frontier.append(neighbor)

    return sorted(all_states - visited)


@dataclass
class CorroborationResult:
    corroborated: bool
    transition_id: str
    implementing_method_id: str
    reason: str
    missing_callees: list[str] = field(default_factory=list)


def corroborate_transition(session, transition_id: str, implementing_method_id: str,
                            expected_callees: list[str]) -> CorroborationResult:
    """REQ-METIS-BM-01: does a proposed Transition's claimed implementing
    Method actually call what the Transition's Guard/Action claims it
    does, per the REAL code graph (cognify/code_graph_archaeology.py's
    CALLS edges)? A mismatch is a real spec-vs-code disagreement -- per
    CONST-046/049, surfaced as Disputed, never silently resolved toward
    either the spec or the code."""
    method_exists = session.run(
        "MATCH (m:Method {id: $id}) RETURN m LIMIT 1", id=implementing_method_id
    ).single()
    if method_exists is None:
        return CorroborationResult(
            corroborated=False, transition_id=transition_id,
            implementing_method_id=implementing_method_id,
            reason=f"Implementing Method '{implementing_method_id}' does not exist in the code "
                   f"graph -- cannot corroborate a Transition against code that isn't there.",
            missing_callees=expected_callees,
        )

    real_callees = {
        r["callee_id"] for r in session.run(
            "MATCH (m:Method {id: $id})-[:CALLS]->(callee:Method) RETURN callee.id AS callee_id",
            id=implementing_method_id,
        )
    }
    missing = [c for c in expected_callees if c not in real_callees]

    if missing:
        reason = (
            f"Transition claims '{implementing_method_id}' calls {missing}, but the real code "
            f"graph shows no such CALLS edge(s) -- spec/code disagreement (REQ-METIS-BM-01)."
        )

        def _mark(tx):
            tx.run(
                "MATCH (t:Transition {id: $id}) SET t.lifecycle_state = 'Disputed', "
                "t.dispute_reason = $reason", id=transition_id, reason=reason,
            )
        session.execute_write(_mark)
        return CorroborationResult(
            corroborated=False, transition_id=transition_id,
            implementing_method_id=implementing_method_id, reason=reason, missing_callees=missing,
        )

    return CorroborationResult(
        corroborated=True, transition_id=transition_id, implementing_method_id=implementing_method_id,
        reason=f"All {len(expected_callees)} expected callee(s) confirmed in the real CALLS graph.",
    )
