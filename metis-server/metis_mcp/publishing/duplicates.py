"""Am I about to create a second copy of this test case?

**Ported in substance from Atlas** (`.agents/skills/shared/scripts/duplicate_guard.py`),
whose four-verdict vocabulary Métis already carries as prose in
`plugins/metis/skills/shared/knowledge/duplicate-guard.md`. What that file did
not have was a checker: the rule said `unknown` blocks, and nothing computed a
verdict, so whether it held depended on a model remembering to apply it.

    no_match       nothing like it exists      -> creation may proceed
    exact_match    the same item exists        -> STOP, ask a person
    similar_match  something close exists      -> STOP, ask a person
    unknown        the lookup could not run    -> STOP, never read as no_match

**The fourth verdict is the whole point, and Métis had exactly this defect.**
Nothing ever wrote `PublicationLedger.published` — only deserialisation and the
tests did — so `compare` read the resulting empty map and reported "no published
case for this path", a confident claim of absence built on no information. Under
`DryRunTransport` that is invisible, because nothing is sent either way. The
moment a live transport ran against such a ledger, every case would read as new
and be created a second time. `drift.record_publication` gave the ledger
something to see and `live_publications` makes "cannot tell" say so; this module
is what turns that into an answer a caller gets before publishing rather than a
property somebody has to know about.

What this does not do, and will not pretend to
----------------------------------------------
**There is no title similarity against published content.** Atlas can do that
because it queries Zephyr and gets titles back. `PublishedCase` retains
`case_id`, `published_id`, `content_hash` and `published_status` — no title, no
steps. Fuzzy-matching against a hash is not possible, and inventing a similarity
score from what is here would be the fabricated-confidence failure the `unknown`
verdict exists to prevent. So `similar_match` is reported for the one similarity
that IS computable and IS a real duplicate: two cases in the same batch that
render identically. What cannot be checked is named in `not_checked` rather than
left for a reader to assume was covered.

This is not `drift.compare`. That asks whether published content *moved* — a
model change versus a human edit, T-13's three-way question. This asks the
narrower mechanical one at T-15's edge: does this item already exist at all.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass

from metis_mcp.publishing.drift import PublicationLedger
from metis_mcp.rendering.test_case import TestCase

def body_hash(case: TestCase) -> str:
    """What a reader would see, WITHOUT the case id.

    `drift.content_hash` cannot be reused here and the reason is the bug this
    function was written to fix. That hash includes `case.id`, correctly — it
    answers "did this case's content move", and identity is part of what it
    pins. Reusing it for twin detection made `similar_match` **unreachable**:
    two cases with different ids can never share a hash that contains the id, so
    the branch looked like a check and could not fire. Found by running it, not
    by reading it.
    """
    steps = [(s.description, s.expected_result, s.guard_verbatim, s.is_assertion)
             for s in (*case.precondition_steps, case.act_step)]
    basis = json.dumps({
        "name": case.name, "objective": case.objective,
        "model_id": case.model_id, "steps": steps,
        "data_requirements": [(d.condition, sorted(d.steps))
                              for d in case.data_requirements],
    }, sort_keys=True)
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


NO_MATCH = "no_match"
EXACT_MATCH = "exact_match"
SIMILAR_MATCH = "similar_match"
UNKNOWN = "unknown"

# The only verdict that proceeds. Written as a set of one rather than an
# equality test so the asymmetry is visible: three of the four stop.
PROCEEDS = frozenset({NO_MATCH})


@dataclass(frozen=True)
class Verdict:
    case_id: str
    verdict: str
    detail: str
    published_id: str = ""

    @property
    def proceeds(self) -> bool:
        return self.verdict in PROCEEDS


def check(cases: list[TestCase], ledger: PublicationLedger) -> list[Verdict]:
    """One verdict per case, in the batch's own order.

    A blind ledger short-circuits everything: when nothing has ever been recorded
    as sent, no per-case reasoning is possible and pretending otherwise is the
    defect. Every case comes back `unknown` with the same reason.
    """
    if not ledger.can_see_published_content:
        return [Verdict(case.id, UNKNOWN,
                        "the ledger has never recorded a live publication, so "
                        "an absent entry is not evidence of absence "
                        "(live_publications is 0)")
                for case in cases]

    by_content: dict[str, list[str]] = defaultdict(list)
    for case in cases:
        by_content[body_hash(case)].append(case.id)

    verdicts: list[Verdict] = []
    for case in cases:
        published = ledger.published.get(case.id)
        if published is not None:
            verdicts.append(Verdict(
                case.id, EXACT_MATCH,
                f"already published as {published.published_id!r} "
                f"(status {published.published_status})",
                published.published_id))
            continue

        twins = [other for other in by_content[body_hash(case)]
                 if other != case.id]
        if twins:
            verdicts.append(Verdict(
                case.id, SIMILAR_MATCH,
                "renders identically to another case in this same batch: "
                + ", ".join(sorted(twins))))
            continue

        verdicts.append(Verdict(case.id, NO_MATCH,
                                "no published entry and no twin in this batch"))
    return verdicts


def summarise(verdicts: list[Verdict]) -> dict:
    """The batch-level answer, and the counts behind it.

    `may_proceed` is true only when every case may. A batch is not partially
    safe to publish: the decision a person is being asked for is about the batch,
    and a rollup that said "mostly fine" would be read as permission.
    """
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v.verdict] = counts.get(v.verdict, 0) + 1
    blocked = [v for v in verdicts if not v.proceeds]
    return {
        "may_proceed": bool(verdicts) and not blocked,
        "counts": counts,
        "blocked": len(blocked),
    }
