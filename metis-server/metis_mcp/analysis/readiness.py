"""Reading one stated intent from four directions, before it reaches the graph.

**Intent is a pre-processor, and this is the check that makes that true.**
`intake` ran fetch, validate, land, *then* assessed risk: the first moment
anybody saw what was wrong with a claim was after it was already a node. Nothing
consulted the intent validator, the wording checkers, the design ledger and the
risk ledger together, and each of the four sees a hole the other three cannot.

So this composes them. It is the analysis a business analyst does, made
checkable: what is the need, is it stated so it can be satisfied twice the same
way, could anything ever test it, and does anybody know what being wrong costs.

**Pure, and it reads a document rather than a graph.** Two shapes go in -- an
`IntentFile` a person authored, or a UIF a tracker produced -- and both are
reduced to the same thing: subjects with statements. The graph-reading half
(`design_report`, `requirement_risk`) is supplied by the caller as already-
gathered `missing_required` lists, which is what keeps this module database-free
and testable with no Neo4j.

**It answers "can this be represented", never "is this right".** Deciding is
S-4's business and it happens at G1 with a person. A `ready` verdict here means
the claim can be landed at Quarantine honestly, carrying every reported gap with
it -- not that anybody has agreed with it.

**What it deliberately does not do.** No score, no readiness percentage, no
"4 of 6 aspects clean". The aspects are not commensurable: an intent with no
statement and an intent whose environments are unlisted are not two-thirds and
five-sixths ready, and averaging them would let the first hide behind the second.
"""
from __future__ import annotations

from dataclasses import dataclass

from metis_mcp.analysis import gaps
from metis_mcp.model_sources.intent import NO_SPECIFICATION as _NO_SPECIFICATION


@dataclass(frozen=True)
class Subject:
    """One claim under analysis: an id, its words, and what specifies it."""

    id: str
    statement: str
    #: Specification statements attached to this need. Empty is the blocking
    #: case, and `gaps.no_specification` is why.
    specifications: tuple[str, ...] = ()
    #: Acceptance criteria already claimed for it. A UIF may carry these and
    #: they are NOT trusted into nodes (S-13); counted here only so the absence
    #: of any can be reported.
    criteria: tuple[str, ...] = ()


def subjects_of(document) -> list[Subject]:
    """The claims in an `IntentFile` or a UIF document, in a stable order.

    Two shapes, one reduction. Which one arrived is decided by structure rather
    than by a flag, because a caller that had to say would eventually say wrong.
    """
    # An `IntentFile`: intents, each with the specifications that point at it.
    if hasattr(document, "intents") and hasattr(document, "specifications"):
        by_intent: dict[str, list[str]] = {}
        for spec in document.specifications:
            by_intent.setdefault(spec.intent_id, []).append(spec.statement)
        return [Subject(id=intent.id, statement=intent.statement,
                        specifications=tuple(by_intent.get(intent.id, ())))
                for intent in document.intents]

    # A UIF document: one stated requirement, with whatever it claims about
    # itself. The claimed criteria are counted and never trusted (S-13).
    if isinstance(document, dict):
        scope = document.get("scope") or {}
        specifications = document.get("specifications") or {}
        claimed = specifications.get("acceptance_criteria") or []
        statement = (document.get("summary") or document.get("title")
                     or scope.get("summary") or "")
        described = document.get("description") or ""
        return [Subject(
            id=str(scope.get("source_key") or document.get("id") or "<no id>"),
            statement=statement,
            specifications=(described,) if described else (),
            criteria=tuple(str(c) for c in claimed))]

    return []


def analyse(document, *, wording=None, design_missing=None, risk_missing=None,
            intent_problems=None, untestable_reasons=None,
            consumers_unknown=0, consumers_total=0) -> dict:
    """Every gap the four aspects find, and whether this may be imported.

    `wording` maps a subject id to `(ears_conformant, quality_findings)`.
    `design_missing` and `risk_missing` are the `missing_inputs` lists the
    design and risk ledgers already produce -- passed in rather than fetched, so
    this module needs no graph.

    `untestable_reasons` maps a subject id to a reason nothing could ever
    observe it. **Supplied by a person or a skill, never inferred**: deciding
    that a claim has no observable outcome is judgement, and a heuristic that got
    it wrong would block a real requirement at the door.
    """
    found: list[gaps.Gap] = list(gaps.from_intent(intent_problems or ()))
    subjects = subjects_of(document)

    # **Two readers, one fact, and only one row.** `intent.validate` already
    # reports a need with no specification, so re-deriving it here filed every
    # such need twice -- once in the validator's words and once in ours. A
    # duplicated gap is worse than a missing one: it inflates the count a reader
    # judges the claim by, and the second row looks like a second problem.
    already = {getattr(problem, "entry_id", "")
               for problem in (intent_problems or ())
               if getattr(problem, "kind", "") == _NO_SPECIFICATION}

    for subject in subjects:
        if not subject.specifications and subject.id not in already:
            found.append(gaps.no_specification(subject.id))

        conformant, quality = (wording or {}).get(subject.id, (True, ()))
        found += gaps.from_wording(subject.id, conformant, quality)

        if not subject.criteria:
            found.append(gaps.no_criteria(subject.id))

        reason = (untestable_reasons or {}).get(subject.id)
        if reason:
            found.append(gaps.untestable(subject.id, reason))

    # The design and risk halves are about the scope, not about one claim, so
    # they are filed once under the document rather than repeated per subject.
    scope = subjects[0].id if len(subjects) == 1 else "<this scope>"
    found += gaps.from_design(scope, design_missing)
    found += gaps.from_risk(scope, risk_missing)
    # Counts rather than a model: this module stays pure, and the classification
    # is done by the caller that holds the graph — the same split the design and
    # risk halves already use.
    found += gaps.from_consumers(scope, consumers_unknown, consumers_total)

    verdict = gaps.readiness(found)
    return {
        "subjects": [{"id": s.id, "statement": s.statement,
                      "specifications": len(s.specifications),
                      "criteria_claimed": len(s.criteria)} for s in subjects],
        "aspects": list(gaps.ASPECTS),
        **verdict,
        "aspects_mean": (
            "five readers, each seeing a hole the others cannot: whether there "
            "is a need here at all, whether its wording can be satisfied twice "
            "the same way, whether anything could ever test it, whether anybody "
            "has said what being wrong costs, and who reads what it produces"),
    }
