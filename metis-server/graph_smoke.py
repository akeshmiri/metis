"""
The graph half, executed — the check no test in this repository can make.

**Why this is not a `test_*.py`.** The suite is database-free on purpose and that
property is load-bearing: models, criteria, path generation and coverage are pure,
so 2,000+ tests run with no service. `test_structure.py` asserts the two CI job
lists partition `test_*.py` exactly, so a third pytest file would have to be named
in both and would drag a Neo4j into the fast job. This runs beside them instead.

**What it is for.** Every graph test in the suite monkeypatches the driver, so
until this existed *nothing anywhere executed a single line of the generated
Cypher*. That is precisely the gap the worst bug in this project's history lived
in: a `VALIDATES` edge planned against `:Transition` passed the ontology check --
`is_allowed` walks the specialisation chain -- and then merged nothing, because
the node carries `:ApiCall`. `land` reports that as `unmatched`; it does not fail.
Both stages "landed", the counts looked plausible, the chain was broken.

`SPECIALISATION_IS_LIVE` below is that bug written as an assertion: a hardcoded
`:Transition` must match **nothing**, and `label_expression("Transition")` must
match the same nodes. A check that only asserted "some transitions exist" would
pass under the bug.

**It asserts what is true, not what would be nice** — and what is true changed.
When this was written there were ZERO `AcceptanceCriterion-[:VALIDATES]->` edges
in the demo corpus, so asserting them would have produced a check that could
never pass. That was not a quirk of the fixture: `ac_draft` wrote its drafts to
the context and nothing landed them, so the traceability edge every generated
agent named as missing was missing everywhere. It is landed now, and the check
below asserts it rather than excusing it.

Usage (needs METIS_NEO4J_URI / _USER / _PASSWORD, after `rebuild_graph.sh --demo`):

    uv run python graph_smoke.py
"""
from __future__ import annotations

import sys

from metis_mcp.ontology.labels import LABELS, label_expression


class Check:
    """One named assertion, with the query that produced its answer."""

    def __init__(self, name, cypher, verdict, why):
        self.name, self.cypher, self.verdict, self.why = name, cypher, verdict, why


CHECKS = [
    # The schema is GENERATED from labels.py. Applying it to a real server is the
    # only thing that proves it is valid Cypher -- and that every label got one.
    Check("schema: one constraint per label",
          "SHOW CONSTRAINTS YIELD name RETURN count(*) AS n",
          lambda n: n >= len(LABELS),
          f"expected at least {len(LABELS)} constraints, one per label"),

    Check("landing: the graph is not empty",
          "MATCH (n) RETURN count(n) AS n",
          lambda n: n > 0,
          "rebuild_graph.sh --demo landed nothing"),

    Check("landing: edges exist",
          "MATCH ()-[r]->() RETURN count(r) AS n",
          lambda n: n > 0,
          "nodes landed with no relationships -- a MERGE that matched nothing "
          "reports `unmatched` and does not fail"),

    # THE ONE. See the module docstring.
    Check("specialisation: a hardcoded :Transition matches nothing",
          "MATCH (n:Transition) RETURN count(n) AS n",
          lambda n: n == 0,
          "a bare :Transition node exists, so the specialisation did not apply "
          "and `landing.transition_label_for` was bypassed"),

    Check("specialisation: label_expression finds them",
          f"MATCH (n) WHERE n:{' OR n:'.join(label_expression('Transition').split('|'))} "
          f"RETURN count(n) AS n",
          lambda n: n > 0,
          "label_expression('Transition') matched nothing -- extraction landed no "
          "transitions at all, or the labels drifted"),

    # S-4: no source writes Approved. A rebuild that approved its own output
    # would defeat the gate it ran through.
    Check("S-4: nothing landed above Quarantine",
          "MATCH (n) WHERE n.lifecycle_state IS NOT NULL "
          "AND n.lifecycle_state <> 'Quarantine' RETURN count(n) AS n",
          lambda n: n == 0,
          "a source wrote a lifecycle state other than Quarantine (S-4)"),

    # **The traceability edge, which had no instances anywhere.** `trace` walks
    # D-4 and needs `AcceptanceCriterion-[:VALIDATES]->Transition` to reach a
    # requirement; every generated agent reported there were none. There were
    # none because nothing landed the drafts, not because the corpus lacked
    # them. A regression here silently restores that.
    Check("traceability: drafted criteria reach their transitions",
          "MATCH (:AcceptanceCriterion)-[:VALIDATES]->() RETURN count(*) AS n",
          lambda n: n > 0,
          "no VALIDATES edge exists, so `trace` cannot reach a requirement from "
          "any transition. Landing reports a planned-but-unmatched edge as "
          "`unmatched` and does not fail, so this is the check that notices"),

    # **Scoped to DRAFTED criteria, and the first version was not.**
    #
    # It asked that no `code_derived` criterion be unjoined and failed on eight —
    # the hand-written ones in `demo_project/specs`, which are `code_derived`
    # because a criterion written from the code it checks is (S-19) and which
    # MUST NOT carry a VALIDATES edge: matching one to a transition is a
    # proposal a human confirms, never an assumption (X-18).
    #
    # The two are opposite cases, and conflating them made the check demand the
    # exact thing the intent/recovery split exists to forbid. A criterion
    # `ac_draft` minted is different: it was drafted FROM one transition, so
    # being joined to none means the edge missed.
    Check("traceability: every drafted criterion reaches its own transition",
          "MATCH (a:AcceptanceCriterion) "
          "WHERE a.name STARTS WITH 'DRAFT-' AND NOT (a)-[:VALIDATES]->() "
          "RETURN count(a) AS n",
          lambda n: n == 0,
          "a drafted criterion is joined to nothing. It was drafted from one "
          "transition, so the edge was planned against an id landing does not "
          "use — the failure that produced 13 criteria and 0 edges three "
          "times, reported as `unmatched` rather than as an error"),

    # **P-16: a coverage figure states what it refers to.** The version genuinely
    # does not exist before a generation — a `Component` is `persist`'s to write
    # and requires one — but the COMMIT does: landing knows it and reported it as
    # "not recorded" anyway, which was an omission dressed as an absence.
    #
    # It lives on the Episode rather than in the joined `evidence` string,
    # because the comment beside `proposed_by` says why depending on splitting
    # that string is a gate that stops working the first time a value contains a
    # comma.
    Check("P-16: the landing episode records the commit it extracted at",
          "MATCH (e:Episode) WHERE e.source_connector = 'code' "
          "AND (e.commit IS NULL OR e.commit = '') RETURN count(e) AS n",
          lambda n: n == 0,
          "a code episode landed without recording its commit, so every "
          "coverage figure from it says 'not recorded (P-16)' while the fact "
          "was available at landing time"),

    Check("academy: every lesson landed",
          "MATCH (n:Lesson) RETURN count(n) AS n",
          lambda n: n > 0,
          "no Lesson nodes -- stage 4b did not run"),

    # **The topic tree is two-level, and the first version of this check got it
    # wrong.** It asserted every Topic has a Lesson pointing at it, and failed on
    # `topic:metis` -- which is the CORPUS ROOT, reached through its subject
    # topics (`Topic-[:BELONGS_TO]->Topic`), never directly from a lesson. The
    # design is deliberate and `lessons.py` says so: a lesson reaches the root
    # through its own subjects, which is what stops `related_by_topic` returning
    # every document in the corpus.
    #
    # The real invariant is reachability: nothing may be pointed at by nothing.
    Check("academy: no unreachable Topic",
          "MATCH (t:Topic) WHERE NOT ()-[:BELONGS_TO]->(t) RETURN count(t) AS n",
          lambda n: n == 0,
          "a Topic has nothing pointing at it -- neither a Lesson nor a child "
          "Topic -- so it can never be reached by a traversal"),

    # **Every claim must have exactly one current revision.**
    #
    # `valid_to` is written ON CREATE only, so a claim whose text REVERTS to an
    # earlier wording produces a `claim_id` that already exists with its window
    # closed: the MERGE matches the closed node and does not reopen it, while
    # supersession closes the one that WAS current. The claim then has every
    # revision closed and none current -- invisible to every validity-respecting
    # read -- and the landing reports success and a new revision number.
    #
    # Unit tests could not catch this. Two were written against `_reopen` in
    # isolation and BOTH passed with the fix sabotaged, because they proved the
    # function worked and not that landing called it. This is a property of the
    # database after a real landing, so it is checked where that exists.
    Check("claims: no logical key has lost its current revision",
          "MATCH (n) WHERE n.valid_to IS NOT NULL AND n.id CONTAINS '@' "
          "WITH split(n.id, '@')[0] AS key, "
          "     sum(CASE n.valid_to WHEN '' THEN 1 ELSE 0 END) AS current "
          "WHERE current <> 1 RETURN count(*) AS n",
          lambda n: n == 0,
          "a claim has zero or several current revisions. Zero means every "
          "revision was closed and none reopened — the claim is invisible to "
          "any read that respects a validity window, and nothing failed"),

    Check("academy: the corpus root has subject topics under it",
          "MATCH (:Topic)-[:BELONGS_TO]->(root:Topic) RETURN count(DISTINCT root) AS n",
          lambda n: n > 0,
          "no Topic-[:BELONGS_TO]->Topic edge, so the corpus has no root and "
          "'what else covers this' cannot climb"),
]


def main() -> int:
    from metis_mcp.mbt.graph_session import session

    failures = []
    with session() as s:
        for check in CHECKS:
            n = s.run(check.cypher).single()[0]
            ok = check.verdict(n)
            print(f"  [{'ok  ' if ok else 'FAIL'}] {check.name}: {n}")
            if not ok:
                failures.append(f"{check.name} (got {n}) -- {check.why}\n"
                                f"      {check.cypher}")

    if failures:
        print("\nThe graph does not hold:")
        for f in failures:
            print(f"  * {f}")
        return 1
    print(f"\n{len(CHECKS)} check(s) passed against a real graph.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
