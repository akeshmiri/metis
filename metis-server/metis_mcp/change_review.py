"""
Review findings a linter cannot make (Atlas's `code-reviewer`, narrowed).

**Metis does not review code, and this is not that.** Style, maintainability and
clarity belong to the linters and formatters a repository already runs; a second
opinion from here would duplicate them and be worse, because this has no
language server and no configuration. Atlas's reviewer covers that ground and it
is deliberately not ported.

What IS ported is the part Atlas's severity table exists for and the part only a
behaviour model can supply: **which of the behaviour a diff touches is now
unasserted**. A linter cannot know that a changed file implements a transition
whose only acceptance criterion was written from the code it checks, or that the
rejection branch of a guard has no case of its own. Metis holds the model, so it
can.

**It closes a loop that was half-open.** `outward_tools.open_merge_request`
refuses over `blocking_findings` and had no producer for them: the parameter
existed and nothing in Metis could fill it.

Severity, mapped to what the model can actually establish -- never to a guess:

  * `critical` -- behaviour is touched and nothing validates it. Merging changes
    something no criterion asserts.
  * `major`    -- touched behaviour is covered only on its positive path, so the
    complement has no oracle (the `positive-only` depth verdict).
  * `minor`    -- touched behaviour is validated only by `code_derived` criteria:
    documentation agreeing with itself, which is coverage and never correctness.
  * `question` -- a changed file matched no recovered behaviour. **Never
    "no impact"**: an unmatched file is one the model does not cover, which is
    exactly when a reviewer should look harder.
"""
from __future__ import annotations

CRITICAL = "critical"
MAJOR = "major"
MINOR = "minor"
QUESTION = "question"

# Atlas's ordering: blockers first, narrative after. A report that opens with a
# summary buries the thing somebody has to act on.
ORDER = (CRITICAL, MAJOR, MINOR, QUESTION)

BLOCKING = (CRITICAL, MAJOR)


def findings_for(impact: dict, depth: dict | None = None,
                 provenance: dict | None = None) -> list[dict]:
    """Grade what a change touches. Pure -- the caller supplies the reads.

    `impact` is `metis_mcp.impact.impact`'s payload, `depth` is
    `viability.classify_depth`, and `provenance` maps a transition id to the
    grades of the criteria validating it. Each is optional except the first, and
    a missing input REMOVES the findings it would have supported rather than
    downgrading them to a guess.
    """
    findings: list[dict] = []
    depth_by_id = {r["transition_id"]: r
                   for r in (depth or {}).get("rows", [])}

    for row in impact.get("impacted_transitions", []) or []:
        # `impacted_transitions` and `id` are the keys `impact.impact()` really
        # emits. This read `impact["transitions"]` and `row["transition"]` --
        # neither of which that payload has ever contained -- so the loop never
        # ran and CRITICAL, MAJOR and MINOR could not fire at all. `verdict`
        # came back "no blocking finding" for every diff, and the ten tests
        # below passed because their fixture invented the shape it wanted.
        tid = row.get("id") or ""
        criteria = row.get("criteria") or []

        if not criteria:
            findings.append({
                "severity": CRITICAL, "transition_id": tid,
                "what": "changed behaviour that nothing validates",
                "why": ("no AcceptanceCriterion validates this transition, so "
                        "merging changes something no criterion asserts (D-4)"),
            })
            continue

        # The criteria rows carry their own provenance (IMPACT_CYPHER collects
        # `{id, provenance}`), so the grade is available without a second read.
        # `provenance` stays an override for callers that computed it elsewhere;
        # before this it was the ONLY source, and `change_review` never passed
        # it, so MINOR was unreachable even once the loop above was fixed.
        inline = {c.get("provenance") for c in criteria if isinstance(c, dict)}
        grades = set((provenance or {}).get(tid, ())) or {g for g in inline if g}
        if grades and grades == {"code_derived"}:
            findings.append({
                "severity": MINOR, "transition_id": tid,
                "what": "validated only by criteria written from the code",
                "why": ("a criterion written from the code it checks can only "
                        "report agreement -- coverage, never correctness "
                        "(S-19, 4.1)"),
            })

        verdict = (depth_by_id.get(tid) or {}).get("verdict")
        if verdict == "positive-only":
            findings.append({
                "severity": MAJOR, "transition_id": tid,
                "what": "covered on the positive path only",
                "why": ("the guard's complement has no case of its own, and a "
                        "positive result does not cover a rejection"),
            })

    # Never "no impact": an unmatched file is one the model does not cover.
    for path in impact.get("files_unmatched", []) or []:
        findings.append({
            "severity": QUESTION, "file": path,
            "what": "changed file matched no recovered behaviour",
            "why": ("either it implements nothing modelled, or the model has "
                    "not been re-extracted since. Those are different answers "
                    "and this cannot tell them apart"),
        })

    findings.sort(key=lambda f: ORDER.index(f["severity"]))
    return findings


def summarise(findings: list[dict]) -> dict:
    """Blockers first, and the honest boundary of what was reviewed."""
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    blocking = [f for f in findings if f["severity"] in BLOCKING]

    return {
        "findings": findings,
        "counts": counts,
        # The list `open_merge_request` refuses over. Producing it here is the
        # whole reason this module exists.
        "blocking": [f"{f['severity']}: {f['what']} "
                     f"({f.get('transition_id') or f.get('file')})"
                     for f in blocking],
        "verdict": ("blockers present" if blocking else
                    "no blocking finding from the behaviour model"),
        "not_reviewed": ("style, maintainability, naming, structure, security "
                         "lint -- Metis has no language server and no lint "
                         "configuration, and a second opinion here would be "
                         "worse than the tools the repository already runs"),
        "means": ("what the model can establish about a diff, not a code "
                  "review. A clean result is not a statement that the change "
                  "is good"),
    }
