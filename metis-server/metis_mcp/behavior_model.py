"""
Phase 8: State-machine well-formedness checks (§2.6,
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
edges it claims, via the evidence layer's `CALLS` edges. A
mismatch is a real disagreement between spec and code, surfaced the same
way as any other contradiction (I-8) -- never silently resolved
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
  (:State)-[:WHEN]->(:Transition|ApiCall|UiAction)-[:THEN]->(:State)
  (:Transition|ApiCall|UiAction {trigger, guard_expression})

Per M-17: a determinism/completeness violation is surfaced as a
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



# --------------------------------------------------------------------------
# Syntactic complementarity (spec M-17's other half)
# --------------------------------------------------------------------------
#
# The interval machinery below decides guards of the shape `<var> <op> <number>`.
# Real recovered guards are mostly not that shape -- `t.isEmpty()` versus
# `NOT (t.isEmpty())` -- and were therefore reported `unverifiable`: 135 of 223
# such findings on the the pilot estate estate alone.
#
# Those are decidable, and decidable *without interpretation*: two guards whose
# conjuncts are identical except that exactly one appears negated in one and
# positive in the other are mutually exclusive AND jointly exhaustive, whatever
# the atoms mean. That is propositional structure, not semantics -- the checker
# never has to know what `t.isEmpty()` does.
#
# This is deliberately narrow. It decides only exact complementarity and exact
# identity; anything else still falls through to the interval check and then to
# `unverifiable`, because M-17 is fail-closed and a partial syntactic match is
# not a proof.

_NOT_PREFIX = re.compile(r"^\s*NOT\s*\((.*)\)\s*$", re.IGNORECASE)


def _strip_parens(text: str) -> str:
    t = text.strip()
    while t.startswith("(") and t.endswith(")"):
        depth = 0
        balanced = True
        for i, ch in enumerate(t):
            depth += (ch == "(") - (ch == ")")
            if depth == 0 and i < len(t) - 1:
                balanced = False
                break
        if not balanced:
            break
        t = t[1:-1].strip()
    return t


def _literal(term: str) -> tuple[str, bool]:
    """`NOT (x)` -> (x, True); `x` -> (x, False). Only the outermost NOT."""
    t = _strip_parens(term)
    m = _NOT_PREFIX.match(t)
    if m:
        inner, _ = _literal(m.group(1))
        return inner, True
    if t.upper().startswith("NOT "):
        inner, _ = _literal(t[4:])
        return inner, True
    return t, False


def split_conjuncts(expression: str) -> list[str] | None:
    """Top-level ` AND ` parts, **in source order**. None if an OR is present.

    An OR makes the expression a disjunction, and deciding complementarity over
    disjunctions needs real boolean reasoning -- out of scope, and pretending
    otherwise is exactly what M-17 forbids.

    **Ordered, and that is why it is separate from `_conjuncts`.** The set that
    function returns is right for asking whether two guards oppose each other,
    and wrong for anything that GENERATES from the parts: Python randomises str
    hashing per process, so iterating the set would emit atomic criteria in a
    different order on every run and break TR-6's byte-identical guarantee.
    """
    text = _strip_parens(expression)
    if not text:
        return None
    if re.search(r"\bOR\b", text, re.IGNORECASE):
        return None
    parts, depth, current = [], 0, ""
    tokens = re.split(r"(\bAND\b)", text, flags=re.IGNORECASE)
    for token in tokens:
        if token.upper() == "AND" and depth == 0:
            parts.append(current)
            current = ""
            continue
        depth += token.count("(") - token.count(")")
        current += token
    parts.append(current)
    ordered = [p.strip() for p in parts if p.strip()]
    return ordered or None


def _conjuncts(expression: str) -> set[tuple[str, bool]] | None:
    """`split_conjuncts`, reduced to the (atom, negated) set relation needs."""
    ordered = split_conjuncts(expression)
    if ordered is None:
        return None
    out = {_literal(p) for p in ordered}
    return out or None


def syntactic_relation(guard_a: str, guard_b: str) -> str | None:
    """`"identical"`, `"complementary"`, `"exclusive"`, or None.

    **Exclusivity and exhaustiveness are different properties, and conflating
    them under-reports.** Two guards are mutually EXCLUSIVE as soon as any single
    atom appears positive in one and negated in the other -- they cannot both
    hold, whatever else differs. They are COMPLEMENTARY (exclusive *and* jointly
    exhaustive) only when that opposing atom is their sole difference.

    An earlier version required the sole-difference condition for both, so
    three-way try/catch guards differing in two literals -- plainly exclusive,
    since one demands `instanceof` and the other its negation -- were reported
    unverifiable. Exclusivity is what a determinism check needs; exhaustiveness
    is what a completeness check needs; they are now answered separately.
    """
    ca, cb = _conjuncts(guard_a), _conjuncts(guard_b)
    if ca is None or cb is None:
        return None
    if ca == cb:
        return "identical"

    opposed = {atom for atom, neg in ca if (atom, not neg) in cb}
    only_a, only_b = ca - cb, cb - ca
    if (len(only_a) == 1 and len(only_b) == 1 and len(opposed) == 1):
        return "complementary"
    if opposed:
        return "exclusive"
    return None


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
    relation = syntactic_relation(guard_a, guard_b)
    if relation == "exclusive":
        return False, (f"'{guard_a}' and '{guard_b}' are mutually exclusive: an atom "
                       f"appears positive in one and negated in the other, so they "
                       f"cannot both hold.")
    if relation == "complementary":
        return False, (f"'{guard_a}' and '{guard_b}' are complementary: identical "
                       f"conjuncts but for one literal, negated on one side. "
                       f"Mutually exclusive by propositional structure, whatever "
                       f"the atoms mean.")
    if relation == "identical":
        return True, (f"'{guard_a}' and '{guard_b}' are the SAME condition, so they "
                      f"always overlap -- this is certain, not unverifiable.")

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


# Sentinel: this guard set is not a pure boolean case-split, so the boolean pass
# has no opinion and the interval machinery decides. Distinct from `None`, which
# is a real verdict meaning "jointly exhaustive".
_NOT_BOOLEAN = object()

# 2**n assignments. Real recovered case-splits use two or three atoms; the cap
# only stops a pathological group from being enumerated.
_MAX_BOOLEAN_ATOMS = 10


def _boolean_coverage_gap(guards: list[str]):
    """Joint exhaustiveness of a boolean case-split, by truth table.

    `syntactic_relation` above decides the two-guard case. Three or more is the
    shape a rejection path produces and it was reported unverifiable:

        request_accepted AND t.isEmpty()          (204)
        request_accepted AND NOT (t.isEmpty())    (200)
        NOT (request_accepted)                    (400)

    Those cover the domain, provably: `NOT (request_accepted)` takes everything
    outside `request_accepted`, and inside it the two senses of `t.isEmpty()`
    partition what is left. No interpretation of either atom is required.

    **Completeness is proved here; incompleteness is not.** The atoms are opaque
    strings and may be semantically dependent -- `t.isEmpty()` and
    `t.isPresent()` look independent and cannot both hold. An assignment covered
    by no guard may therefore be an assignment that cannot occur, so an
    uncovered row is reported as *unverifiable with the row named*, never as a
    gap. The other direction is sound whatever the dependencies are: covering
    every assignment necessarily covers every reachable one.

    Numeric thresholds are handed straight back. Treating `attempts < 5` and
    `attempts >= 5` as independent booleans would invent an impossible row and
    report a gap the interval pass correctly does not see.
    """
    literals = [_conjuncts(g) for g in guards]
    if any(c is None or not c for c in literals):
        return _NOT_BOOLEAN                      # an OR, or an empty guard

    atoms = sorted({atom for clause in literals for atom, _ in clause})
    if not atoms or len(atoms) > _MAX_BOOLEAN_ATOMS:
        return _NOT_BOOLEAN
    if any(_parse_guard(atom) is not None for atom in atoms):
        return _NOT_BOOLEAN                      # intervals, not booleans

    index = {atom: i for i, atom in enumerate(atoms)}
    for row in range(1 << len(atoms)):
        def holds(clause) -> bool:
            return all(bool(row >> index[atom] & 1) is not negated
                       for atom, negated in clause)
        if any(holds(clause) for clause in literals):
            continue
        uncovered = " AND ".join(
            atom if row >> index[atom] & 1 else f"NOT ({atom})" for atom in atoms)
        # Worded to avoid `validation.py`'s two verifiable-severity phrases
        # ("gap in guard coverage", "no guard covers"), and deliberately so: this
        # row may be unreachable, and promoting it to a blocking finding would
        # assert a defect the checker cannot establish.
        return (f"no transition is guarded for the combination '{uncovered}' -- "
                f"either a real input there matches nothing, or these conditions "
                f"cannot hold together, which is not decidable from the text alone")
    return None


def _guard_coverage_gap(guards: list[str]) -> str | None:
    """The completeness-side sibling of guards_conflict()'s atomicity
    check: given guard expressions that all share the same (from_state,
    trigger), returns a gap-description string if they do NOT jointly
    cover the full range of their variable, or None if they do. Reuses
    the same interval representation guards_conflict() builds -- checking
    for a GAP is the natural complement of checking for an OVERLAP. Same
    fail-closed discipline: an unparseable guard, or guards on different
    variables, is flagged as unverifiable, never assumed complete."""
    if len(guards) == 2 and syntactic_relation(guards[0], guards[1]) == "complementary":
        # X and NOT X cover the whole domain between them, by structure.
        return None

    boolean = _boolean_coverage_gap(guards)
    if boolean is not _NOT_BOOLEAN:
        return boolean

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


def check_guard_completeness(session, state_machine_id: str | None = None) -> list[GuardCoverageGap]:
    """Not one of §2.6's original determinism/completeness
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
                MATCH (s:State)-[:WHEN]->(t:Transition|ApiCall|UiAction)
                WHERE t.c_trigger IS NOT NULL AND t.b_guard_expression IS NOT NULL
                    AND ($state_machine_id IS NULL OR t.state_machine_id = $state_machine_id)
        RETURN s.id AS from_state, t.c_trigger AS trigger, t.id AS transition_id,
               t.b_guard_expression AS guard
                """,
                state_machine_id=state_machine_id,
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


# `load_transition` was removed here. It MERGE-d `(:Transition {id: $transition_id})`
# with a bare id, while `model_sources/landing.py` -- the actual writer -- writes
# `:ApiCall`/`:UiAction` with `{model_id}::{id}`. Calling it against a landed
# model would therefore have created a SECOND node per transition rather than
# updating the first, and nothing would have reported it.
#
# It had no caller, which is the only reason it never did. A second writer for
# an element type is how two halves of one graph come to disagree, and the fix
# for an unwired one is to remove it, not to keep it correct in parallel.
# Transitions reach the graph through `landing.plan_landing` and nowhere else.


def check_determinism(session, state_id: str,
                      state_machine_id: str | None = None) -> DeterminismResult:
    """§2.6: no two Transitions from the same source
    State should fire on the same Trigger with overlapping Guards."""
    rows = session.run(
        """
                MATCH (s:State {id: $state_id})-[:WHEN]->(t1:Transition|ApiCall|UiAction)
        MATCH (s)-[:WHEN]->(t2:Transition|ApiCall|UiAction)
                WHERE t1.id < t2.id AND t1.c_trigger = t2.c_trigger
                    AND ($state_machine_id IS NULL OR (
                            t1.state_machine_id = $state_machine_id
                            AND t2.state_machine_id = $state_machine_id
                    ))
        RETURN t1.id AS t1_id, t2.id AS t2_id, t1.c_trigger AS trigger_id,
               t1.b_guard_expression AS g1_expr, t2.b_guard_expression AS g2_expr
        """,
        state_id=state_id, state_machine_id=state_machine_id,
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
        # M-17: surfaced as Disputed, not silently resolved.
        def _mark(tx):
            for f in findings:
                tx.run(
                    "MATCH (t:Transition|ApiCall|UiAction) WHERE t.id IN [$a, $b] "
                    "SET t.lifecycle_state = 'Disputed', t.dispute_reason = $reason",
                    a=f.transition_a, b=f.transition_b, reason=f.reason,
                )
        session.execute_write(_mark)

    return DeterminismResult(deterministic=not findings, findings=findings)


@dataclass
class CompletenessGap:
    state_id: str
    trigger_id: str


def check_completeness(session, state_machine_id: str | None = None) -> list[CompletenessGap]:
    """Every State should have a defined Transition for every Trigger used
    anywhere in the set. Operationalized exactly as §2 defines it: the
    full Trigger vocabulary is whatever's actually used across this
    Transition set (not an externally-imposed list)."""
    gaps = session.run(
        """
                MATCH (any:Transition|ApiCall|UiAction)
                WHERE any.trigger IS NOT NULL
                    AND ($state_machine_id IS NULL OR any.state_machine_id = $state_machine_id)
        WITH DISTINCT any.trigger AS trigger
        MATCH (s:State)
                WHERE ($state_machine_id IS NULL OR s.state_machine_id = $state_machine_id)
                    AND NOT EXISTS {
                        MATCH (s)-[:WHEN]->(t:Transition|ApiCall|UiAction)
                        WHERE t.c_trigger = trigger
                            AND ($state_machine_id IS NULL OR t.state_machine_id = $state_machine_id)
        }
        RETURN s.id AS state_id, trigger AS trigger_id
        ORDER BY state_id, trigger_id
                """,
                state_machine_id=state_machine_id,
        ).data()
    return [CompletenessGap(g["state_id"], g["trigger_id"]) for g in gaps]


def check_reachability(session, initial_state_id: str,
                       state_machine_id: str | None = None) -> list[str]:
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
    all_states = {r["id"] for r in session.run(
        "MATCH (s:State) WHERE $state_machine_id IS NULL OR s.state_machine_id = $state_machine_id "
        "RETURN s.id AS id",
        state_machine_id=state_machine_id,
    ).data()}
    edges = session.run(
        """
        MATCH (a:State)-[:WHEN]->(t:Transition|ApiCall|UiAction)-[:THEN]->(b:State)
        WHERE $state_machine_id IS NULL OR (
            a.state_machine_id = $state_machine_id
            AND t.state_machine_id = $state_machine_id
            AND b.state_machine_id = $state_machine_id
        )
        RETURN a.id AS from_id, b.id AS to_id
        """, state_machine_id=state_machine_id,
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

