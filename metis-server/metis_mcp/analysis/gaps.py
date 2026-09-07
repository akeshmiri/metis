"""What is missing from a stated intent, found from four different directions.

**The rule this module exists for: an intent is not imported until it has been
looked at from every aspect that can see a different kind of hole.**

A half-formed intent fails in four unrelated ways, and each is invisible to the
readers that catch the other three:

    intent       the need is a label, or nobody said how it behaves
    requirement  the wording cannot be satisfied the same way twice
    design       nothing about it could be tested, whatever anybody builds
    risk         nobody has said what being wrong costs

Métis already held a reader for each -- `model_sources.intent.validate`,
`ears_checker` and `ac_quality`, `design.inputs`, `risk.inputs` -- and nothing
consulted them together, or before landing. `intake` ran fetch, validate, land,
*then* assessed risk, so the first moment anybody saw what was wrong with a claim
was after it was a node in the graph.

**Every gap names the aspect that found it and what would close it.** A gap with
no `closes_with` is a complaint; naming the skill or tool that closes it is what
makes the ledger a work list rather than a verdict. `test_analysis.py` asserts
both fields are present on every gap and that the closer is a real skill or a
real tool.

**`blocks_import` is the only judgement here, and it is narrow.** A gap blocks
when the claim cannot be *represented* honestly -- a need with no statement, a
specification belonging to no need. Everything else is reported and imported: a
requirement whose business criticality nobody has stated is a normal state of
affairs, and refusing it would mean Métis only ever accepted claims that were
already finished, which is not what intake is for.

**Nothing here decides whether a claim is true.** It reports whether it can be
acted on. Deciding is S-4's business, and it happens at G1 with a person.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The four directions a stated intent is read from. Ordered: `intent` asks
#: whether there is anything here at all, and the later three are only
#: meaningful once it says yes.
INTENT, REQUIREMENT, DESIGN, RISK = "intent", "requirement", "design", "risk"
ASPECTS = (INTENT, REQUIREMENT, DESIGN, RISK)

READY, NOT_READY = "ready", "not-ready"


@dataclass(frozen=True)
class Gap:
    """One thing missing from a stated intent, and what would close it."""

    aspect: str
    subject: str
    #: What is missing. Stated as an observation, never as a verdict on the
    #: person who wrote it.
    what: str
    #: The skill, tool or verb that closes it. A gap with no closer is a
    #: complaint, and this field is what stops one being filed.
    closes_with: str
    #: Whether the claim can be represented honestly without this. Narrow on
    #: purpose -- see the module docstring.
    blocks_import: bool = False

    def describe(self) -> str:
        mark = "BLOCKS" if self.blocks_import else "report"
        return f"[{self.aspect:<11} {mark:<6}] {self.subject}: {self.what}"


# ---------------------------------------------------------------------------
# The intent aspect: is there anything here to import?
# ---------------------------------------------------------------------------

#: **Every validator problem blocks, and that is one definition rather than
#: two.** The first version of this module kept its own set of "serious" intent
#: problems, which immediately went wrong: deduplicating a gap moved a missing
#: specification onto a row the set did not name, and a need nobody had
#: specified came back `ready`.
#:
#: The rule that cannot drift is the one the landing path already enforces:
#: `cmd_intent_land` refuses the file if `validate` returns anything at all. So
#: a validator problem blocks here because it will block there, and this module
#: has no second opinion to keep in step.
_VALIDATOR_PROBLEMS_BLOCK = True


def from_intent(problems) -> list[Gap]:
    """`model_sources.intent.validate`'s problems, as gaps.

    The reader was reachable only from `metis intent check` on the CLI, so
    nothing in a workflow ever consulted it. Translating rather than
    re-implementing is what keeps one definition of a malformed intent file.
    """
    out: list[Gap] = []
    for problem in problems:
        kind = getattr(problem, "kind", "")
        out.append(Gap(
            aspect=INTENT,
            subject=getattr(problem, "entry_id", "") or "<no id>",
            what=getattr(problem, "detail", "") or kind,
            closes_with=("edit the intent file — `metis intent check` names "
                         "every problem in it"),
            blocks_import=_VALIDATOR_PROBLEMS_BLOCK,
        ))
    return out


def no_specification(intent_id: str) -> Gap:
    """A need nobody has said the behaviour of.

    Blocking, and it is the one gap this module would refuse over even if
    nothing else did: landing it would put a node in the graph that nothing can
    ever be checked against, which is the dangling reference D-1 prevents.
    """
    return Gap(
        aspect=INTENT, subject=intent_id,
        what=("a need with no specification. Nothing states how it behaves, so "
              "nothing can ever be compared against it"),
        closes_with="metis-business-analyst-intent — state the behaviour, then "
                    "`metis intent check`",
        blocks_import=True)


# ---------------------------------------------------------------------------
# The requirement aspect: can two people satisfy this the same way?
# ---------------------------------------------------------------------------

def from_wording(subject: str, conformant: bool, quality) -> list[Gap]:
    """EARS conformance and criterion quality, as gaps.

    **Neither blocks, and that is deliberate.** Free prose is a real thing
    somebody wrote, and `intake land` already has the right answer for it: it
    lands as a `Finding` pointing at knowledge-capture rather than as a
    `Requirement` (S-13). Refusing the import as well would delete the record of
    what was asked for, which is the opposite of what intake is for.
    """
    out: list[Gap] = []
    if not conformant:
        out.append(Gap(
            aspect=REQUIREMENT, subject=subject,
            what=("not EARS-conformant, so two readers can satisfy it "
                  "differently. It will land as a Finding rather than a "
                  "Requirement (S-13)"),
            closes_with="metis-knowledge-capture — restate it in an EARS pattern"))
    for finding in quality or ():
        text = finding.describe() if hasattr(finding, "describe") else str(finding)
        out.append(Gap(
            aspect=REQUIREMENT, subject=subject, what=text,
            closes_with="metis-knowledge-capture — `ac_quality` names each one"))
    return out


def no_criteria(subject: str) -> Gap:
    """A claim nothing can validate. Reported, never blocking.

    Criteria are what `metis-knowledge-capture` exists to produce, and requiring
    them before import would mean an intent could only enter Métis once the work
    Métis does had already been done by hand.
    """
    return Gap(
        aspect=REQUIREMENT, subject=subject,
        what=("no acceptance criteria. Nothing states what correct is, so "
              "nothing can validate this"),
        closes_with="metis-knowledge-capture — mine criteria and reconcile them")


# ---------------------------------------------------------------------------
# The design aspect: could this be tested at all?
# ---------------------------------------------------------------------------

def from_design(subject: str, missing_required) -> list[Gap]:
    """Required design inputs nobody supplied, as gaps.

    **This is the aspect that catches the expensive mistake**, and it is the one
    an intake process normally has no reader for: a claim that is well worded,
    agreed and impossible to verify. Asking it before the work starts costs one
    question; asking it after costs the build.

    Reported rather than blocking. "Nobody has said which environments exist" is
    a fact about the organisation, not a defect in the claim.
    """
    out: list[Gap] = []
    for missing in missing_required or ():
        name = missing.get("name") if isinstance(missing, dict) else str(missing)
        means = missing.get("absent_means", "") if isinstance(missing, dict) else ""
        question = missing.get("question", "") if isinstance(missing, dict) else ""
        out.append(Gap(
            aspect=DESIGN, subject=subject,
            what=f"{name} — {means}" if means else name,
            closes_with=(f"metis-test-design — ask: {question}" if question
                         else "metis-test-design — `design_inputs` names the tool")))
    return out


def untestable(subject: str, reason: str) -> Gap:
    """A claim nothing could ever assert, whatever is built.

    Blocking, and it is the only design gap that is. A need whose behaviour has
    no observable outcome is not a hard requirement -- it is one that cannot be
    stated as a requirement at all, and importing it produces a node that will
    sit at Quarantine for ever.
    """
    return Gap(
        aspect=DESIGN, subject=subject,
        what=f"nothing could observe whether this holds: {reason}",
        closes_with="metis-business-analyst-intent — restate it as an outcome "
                    "somebody could see",
        blocks_import=True)


# ---------------------------------------------------------------------------
# The risk aspect: what does being wrong cost?
# ---------------------------------------------------------------------------

def from_risk(subject: str, missing_required) -> list[Gap]:
    """Required risk inputs nobody answered, as gaps.

    Reported, never blocking, for the reason `risk/inputs.py` gives: an
    unanswered required input makes an assessment `incomplete`, and incomplete
    is a state to report rather than a reason to refuse the claim it is about.
    """
    out: list[Gap] = []
    for missing in missing_required or ():
        name = missing.get("name") if isinstance(missing, dict) else str(missing)
        means = missing.get("absent_means", "") if isinstance(missing, dict) else ""
        question = missing.get("question", "") if isinstance(missing, dict) else ""
        out.append(Gap(
            aspect=RISK, subject=subject,
            what=f"{name} — {means}" if means else name,
            closes_with=(f"metis-risk-manager-requirement-risk — ask: {question}"
                         if question else
                         "metis-risk-manager-requirement-risk")))
    return out


# ---------------------------------------------------------------------------
# The verdict.
# ---------------------------------------------------------------------------

def readiness(found: list[Gap]) -> dict:
    """Whether this intent may be imported, and precisely what is in the way.

    **`ready` is not `good`.** It means the claim can be represented honestly in
    the graph, at Quarantine, for a person to decide on at G1. A ready intent may
    still carry a dozen reported gaps, and the document lists every one of them
    above the verdict rather than below it.
    """
    blocking = [g for g in found if g.blocks_import]
    by_aspect = {aspect: [g for g in found if g.aspect == aspect]
                 for aspect in ASPECTS}
    return {
        "status": NOT_READY if blocking else READY,
        "blocking": [g.describe() for g in blocking],
        "counts": {aspect: len(gaps) for aspect, gaps in by_aspect.items()},
        "gaps": [{"aspect": g.aspect, "subject": g.subject, "what": g.what,
                  "closes_with": g.closes_with, "blocks_import": g.blocks_import}
                 for g in found],
        "means": (
            "THIS INTENT CANNOT BE IMPORTED AS IT STANDS. The blocking gaps "
            "above are claims that cannot be represented honestly — not claims "
            "that are wrong" if blocking else
            "this can be imported. It lands at Quarantine like every other "
            "source (S-4), and `ready` says it can be represented — not that "
            "anybody has agreed with it"),
    }
