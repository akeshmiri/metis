"""Risks derivable from what Métis already knows about a requirement or a release.

Pure: every function takes facts a caller gathered and returns candidates. The
gathering lives in `server.py`, where the tools and the graph session are, so
that everything here is testable with a dict.

**What makes these different from `candidates.py`.** That module turns a
`change_review` finding into a register row — one tool, one observation. These
join *several* tools into a judgement about one requirement or one release, and
the join is where a system starts overstating. Three rules keep it honest:

- **Every candidate names the tool that produced its evidence** (`derived_by`),
  so a reader can disagree with the input rather than only the conclusion.
- **No candidate is created from a fact Métis did not gather.** A missing input
  produces an entry in `missing_inputs`, never a risk and never silence.
  `inputs.completeness` owns that half.
- **`probability` stays null.** Unchanged from `candidates.py` and the reason
  this is an *observation* rather than an assessment until a person rates it.

**The trap this avoids.** It is tempting to score a requirement — "3 of 9 checks
failed, risk 33%". That number would be arithmetic over incommensurable checks,
and it would rank a requirement with no acceptance criteria alongside one whose
anchor is missing. They are not comparable, and the honest output is a list of
named observations with the evidence for each.
"""
from __future__ import annotations

from metis_mcp.risk.candidates import _candidate

# Impact by what the observation means, not by how many checks failed. Each is
# the answer to "how bad is it if this one thing is true", asked once here so two
# runs cannot disagree.
_UNVALIDATABLE = 5      # nothing can ever assert this requirement
_UNAPPROVED = 4         # nothing may be generated from it (D-10)
_SELF_CONFIRMING = 4    # documentation agreeing with itself (S-19)
_UNTESTED = 4
_AMBIGUOUS = 3
_BROKEN_CHAIN = 3
_STALE = 3
_UNANCHORED = 2


def for_requirement(facts: dict) -> list[dict]:
    """Candidates from the gathered facts about one requirement.

    `facts` carries only what was actually gathered. A key that is absent
    produces NO candidate — its absence is reported by `inputs.completeness`,
    because "we did not check" and "we checked and it was fine" are different
    answers and a risk list cannot hold the first.
    """
    found: list[dict] = []
    n = 0

    # **Process categories, not project ones.** These observations are about
    # the quality work — a requirement nothing can validate is a `Requirements`
    # risk and a criterion written from its own code is a `Test design` one.
    # Filing them as `Quality` put every software observation into the single
    # nearest entry of a ten-category PROJECT taxonomy, where no row is
    # addressable by anybody in particular.
    def add(description, impact, detail, derived_by, category="Requirements"):
        nonlocal n
        n += 1
        found.append(_candidate(
            rid=f"RM-RQ-{n:03d}", description=description, category=category,
            impact=impact, detail=detail, derived_by=derived_by))

    count = facts.get("criteria_count")
    if count == 0:
        add("requirement has no acceptance criteria, so nothing can validate it",
            _UNVALIDATABLE,
            "a requirement no criterion asserts cannot be tested, generated "
            "from, or shown to have been met", "get_requirement")

    provenance = facts.get("criteria_provenance") or {}
    if count and provenance.get("intent") == 0:
        add("every criterion was written from the code it checks",
            _SELF_CONFIRMING,
            "a code-derived criterion can only report agreement — coverage, "
            "never correctness (S-19, spec 4.1). The requirement is validated "
            "by a restatement of the implementation", "get_requirement",
            category="Test design")

    if facts.get("ears_conformance") is False:
        add("requirement wording is not EARS-conformant",
            _AMBIGUOUS,
            "the wording has no testable trigger/response structure, so two "
            "readers can satisfy it differently (S-13)", "check_ears")

    for finding in facts.get("criterion_quality") or ():
        add(f"acceptance criterion is not precisely assertable: {finding}",
            _AMBIGUOUS,
            "an unmeasurable qualifier or a non-atomic criterion cannot be "
            "turned into a passing or failing test", "ac_quality",
            category="Test design")

    state = facts.get("lifecycle_state")
    if state and state != "Approved":
        add(f"requirement is at `{state}`, not `Approved`",
            _UNAPPROVED,
            "generation reads only Approved (D-10), so nothing downstream may "
            "be produced from this requirement while it sits here",
            "get_requirement", category="Requirements")

    if facts.get("superseded") is True:
        add("requirement has been superseded by a newer wording",
            _STALE,
            "this is a closed claim; work planned against it is work against "
            "the past (I-17/I-18)", "get_requirement", category="Requirements")

    coverage = facts.get("coverage")
    if isinstance(coverage, (int, float)) and coverage <= 0:
        add("no covering test case reaches the behaviour this requirement describes",
            _UNTESTED,
            "coverage says untested, and only that — it is not a statement "
            "that the behaviour is broken (C-11)", "coverage_report",
            category="Test design")

    for hop in facts.get("trace_breaks") or ():
        add(f"the justification chain breaks at {hop}",
            _BROKEN_CHAIN,
            "D-4's chain is what makes a test auditable back to a requirement; "
            "a break means the link is asserted rather than recorded", "trace")

    for claim in facts.get("contradictions") or ():
        add(f"another claim in the graph may contradict this: {claim}",
            _AMBIGUOUS,
            "two claims that disagree cannot both be satisfied, and neither is "
            "wrong until a person says which", "search_knowledge")

    if facts.get("anchor") == "":
        add("requirement has no anchor to a source artefact",
            _UNANCHORED,
            "nothing outside Métis records who asked for this, so it cannot be "
            "taken back to its origin when challenged",
            "get_requirement", category="Requirements")

    return found


def for_release(facts: dict) -> list[dict]:
    """Candidates from the gathered facts about a release scope.

    Reads what `coverage_report`, `validate_model` and `describe_execution`
    produced. It computes **no coverage figure of its own** — a second readiness
    engine would give two answers to one question, and
    `metis-release-readiness` already owns that one.
    """
    found: list[dict] = []
    n = 0

    def add(description, impact, detail, derived_by, category="Test design"):
        nonlocal n
        n += 1
        found.append(_candidate(
            rid=f"RM-RL-{n:03d}", description=description, category=category,
            impact=impact, detail=detail, derived_by=derived_by))

    for finding in facts.get("validation_findings") or ():
        add(f"blocking validation finding: {finding}",
            5,
            "stage 3 blocks on any failure (M-18); everything downstream "
            "assumes it passed", "validate_model")

    for entry in facts.get("unmeasured") or ():
        kind = (entry or {}).get("kind", "structural")
        figure = (entry or {}).get("figure", "a figure")
        add(f"{figure} could not be measured ({kind})",
            3,
            "a risk about the REPORT, not about the behaviour — which may be "
            "perfectly healthy and merely unmeasured. Reading it as a defect "
            "and reading it as safety are both wrong",
            "coverage_report", category="Test design")

    if facts.get("execution_evidence") in (None, False, 0, [], ""):
        add("no observed execution evidence for this scope",
            5,
            "coverage answers *is this tested*, never *did it pass* (C-11). "
            "Covered-and-failing is a real state and is exactly the state a "
            "coverage-derived verdict would call ready",
            # `Automation`, not `Quality`: nothing here says the software is
            # bad, it says nothing was observed running. That is a property of
            # the suite and the pipeline, and it is who has to fix it.
            "describe_execution", category="Automation")

    capped = facts.get("confidence_capped_by")
    if capped:
        add(f"confidence in the readiness figures is capped by: {capped}",
            3,
            "the report is worth no more than its weakest input, and this "
            "names it", "coverage_report", category="Test design")

    for finding in facts.get("change_exposure") or ():
        add(f"the change under review leaves behaviour unasserted: {finding}",
            4,
            "graded by change_review; the grade is that tool's and is not "
            "re-derived here", "change_review")

    if facts.get("execution_stale"):
        add(f"execution evidence is stale: {facts['execution_stale']}",
            4,
            "an outcome observed last month is not a fact about today, and a "
            "verdict resting on it inherits its age", "describe_execution")

    return found
