"""What a risk assessment rests on, and which half of it Métis can supply.

**The rule this module exists for: an assessment missing a required input reports
`incomplete`, never a clean bill.**

It is `depth_consulted` one domain over. `change_review` reports whether coverage
depth was consulted because a short finding list means *nobody looked* just as
often as it means *nothing is wrong*, and the two must not render alike. Risk has
the same failure in a more dangerous place: Métis can gather nine facts about a
requirement and none of them is business criticality, so an assessment built from
what is reachable will look thorough and be missing the input that decides the
answer.

So every input is declared, with its source:

- **`gathered`** — Métis has a tool that supplies it. The tool is named, so a
  reader can go and disagree with the input rather than only with the conclusion.
- **`asked`** — a person supplies it, and the exact words to put to them are
  written down. Not a topic ("business impact") but a question somebody can
  answer.

`absent_means` is mandatory on every input and is asserted never to say "no
risk". That string is the one a report prints where the value should have been,
and the whole design fails if it ever reads as reassurance.

**Why the split is not negotiable.** A gathered fact and an answered question are
different kinds of claim, exactly as `derived_from: authored | model` separates
them in the register. Coverage says *this behaviour is untested*; a person saying
*this requirement is critical to billing* is a different assertion with a
different owner. Merging them produces a number that looks like a measurement and
is half judgement — C-11 one more domain over.

**What is deliberately NOT here.** No weighting, no scoring of completeness, no
"7 of 12 inputs present, confidence 58%". A percentage over a set of
incommensurable inputs invents precision, and worse, it makes a missing critical
input look like a small deduction rather than a hole. The report names what is
missing; it does not score it.
"""
from __future__ import annotations

from dataclasses import dataclass

GATHERED, ASKED = "gathered", "asked"
SOURCES = (GATHERED, ASKED)

#: The two assessments this module describes.
REQUIREMENT, RELEASE = "requirement", "release"

COMPLETE, INCOMPLETE = "complete", "incomplete"


class UnknownAssessment(Exception):
    """Raised for an assessment name that has no declared inputs."""


@dataclass(frozen=True)
class Input:
    """One thing an assessment needs, and where it comes from."""

    name: str
    #: What this input DECIDES. Never "context" — an input that decides nothing
    #: is one nobody will supply, and it dilutes the list of the ones that matter.
    why: str
    source: str
    #: `gathered`: the MCP tool that supplies it, so the claim is traceable.
    tool: str = ""
    #: `asked`: the exact words to put to a person. A topic is not a question;
    #: "business impact" gets a shrug and "if this is wrong or unbuilt, what does
    #: the business lose?" gets an answer.
    question: str = ""
    required: bool = True
    #: What it means when this is absent. Printed where the value should have
    #: been, and never permitted to read as reassurance.
    absent_means: str = ""

    def describe(self) -> str:
        where = f"via `{self.tool}`" if self.source == GATHERED else "ask a person"
        return f"[{self.source}] {self.name} — {self.why} ({where})"


REQUIREMENT_INPUTS: tuple[Input, ...] = (
    Input("ears_conformance", "whether the wording is testable at all",
          GATHERED, tool="check_ears",
          absent_means="the wording was not checked, so ambiguity is unassessed"),
    Input("criterion_quality",
          "unmeasurable qualifiers and non-atomic criteria, which no test can assert",
          GATHERED, tool="ac_quality",
          absent_means="criterion wording was not checked"),
    Input("criteria_count",
          "a requirement with no acceptance criteria cannot be validated by anything",
          GATHERED, tool="get_requirement",
          absent_means="unknown whether anything validates this requirement"),
    Input("criteria_provenance",
          "criteria written from the code can only report agreement — coverage, "
          "never correctness (S-19)",
          GATHERED, tool="get_requirement",
          absent_means="unknown whether the criteria are independent of the code"),
    Input("lifecycle_state",
          "only `Approved` generates (D-10); anything else is a claim nobody has accepted",
          GATHERED, tool="get_requirement",
          absent_means="approval state unknown"),
    Input("superseded",
          "a superseded requirement is a closed claim, and acting on it is acting on the past",
          GATHERED, tool="get_requirement",
          absent_means="unknown whether a newer wording has replaced this"),
    Input("coverage", "whether the behaviour it describes is tested at all",
          GATHERED, tool="coverage_report",
          absent_means="coverage was not measured — which is not the same as zero coverage"),
    # OPTIONAL, and the reason is a real limit rather than an oversight: `trace`
    # walks from a TestCase forward, so the chain is reachable when you hold a
    # case id and not when you hold only a requirement. Marking it required
    # would make every requirement assessment permanently incomplete, which
    # would teach readers to ignore the word.
    Input("trace_complete",
          "where the justification chain breaks between a test and this requirement",
          GATHERED, tool="trace", required=False,
          absent_means="the chain was not walked — pass a test case to `trace` "
                       "to see where it breaks"),
    Input("contradictions", "another claim in the graph that says the opposite",
          GATHERED, tool="search_knowledge", required=False,
          absent_means="no search was run; contradictions are not ruled out"),
    Input("anchor", "the artefact in the world this came from, if any",
          GATHERED, tool="get_requirement", required=False,
          absent_means="unknown whether this traces to a source outside Métis"),

    Input("business_criticality",
          "the impact rating — everything downstream depends on it",
          ASKED,
          question="If this requirement is wrong, or never built, what does the "
                   "business actually lose? Name the consequence, not a severity word.",
          absent_means="IMPACT IS UNRATED — no exposure can be computed, and a "
                       "short risk list here means nobody has said what is at stake"),
    Input("volatility", "the probability side of the exposure",
          ASKED,
          question="How settled is this requirement? Who could still change it, "
                   "and has anything like it changed before?",
          absent_means="PROBABILITY IS UNRATED — Métis does not forecast, and no "
                       "exposure exists without a person supplying this"),
    Input("regulatory_exposure",
          "whether being wrong is a compliance event rather than a defect",
          ASKED,
          question="Is this requirement subject to an external obligation — "
                   "regulation, contract, audit commitment?",
          absent_means="regulatory exposure unknown; an unasked compliance "
                       "question is not an absent one"),
    Input("stakeholder_agreement",
          "whether the wording is agreed, or one person's reading of a conversation",
          ASKED,
          question="Has the person who asked for this confirmed this exact "
                   "wording, or is it somebody's write-up of what they said?",
          absent_means="agreement unknown — Métis holds the text, never the consensus"),
    Input("external_dependency",
          "whether delivery depends on somebody outside this codebase",
          ASKED, required=False,
          question="Does this depend on a team, supplier or system outside this "
                   "repository to be delivered or verified?",
          absent_means="external dependencies unexamined"),
)


RELEASE_INPUTS: tuple[Input, ...] = (
    Input("coverage", "what is tested, and what could not be measured at all",
          GATHERED, tool="coverage_report",
          absent_means="coverage was not measured — not the same as zero"),
    Input("unmeasured",
          "figures that could not be produced, split structural vs operational",
          GATHERED, tool="coverage_report",
          absent_means="unknown what could not be measured, which is the field "
                       "that makes the rest safe to read"),
    Input("confidence_capped_by", "the weakest input the coverage figure rests on",
          GATHERED, tool="coverage_report",
          absent_means="unknown what caps confidence in these figures"),
    Input("validation_findings",
          "a model with blocking findings cannot support a release claim (M-18)",
          GATHERED, tool="validate_model",
          absent_means="model well-formedness unknown"),
    Input("execution_evidence",
          "whether anything was actually RUN — the only input that supports a verdict",
          GATHERED, tool="describe_execution",
          absent_means="no observed run. Coverage alone supports no verdict "
                       "(C-11): covered-and-failing is a real state"),
    Input("change_exposure", "what this diff puts at risk that nothing validates",
          GATHERED, tool="change_review", required=False,
          absent_means="the diff was not reviewed against the model"),
    Input("open_model_risks", "risks already recorded against this scope",
          GATHERED, tool="risk_report", required=False,
          absent_means="the register was not read"),

    Input("release_appetite",
          "the threshold this release is judged against — without it a band is decoration",
          ASKED,
          question="What are we willing to ship broken this time, and what would "
                   "stop the release outright?",
          absent_means="NO THRESHOLD — nothing here can say whether the findings "
                       "are acceptable, only what they are"),
    Input("rollback",
          "how bad a wrong call is, which is most of the impact rating",
          ASKED,
          question="Can this be rolled back? How long does it take, and who "
                   "does it?",
          absent_means="ROLLBACK UNKNOWN — the cost of being wrong is unrated"),
    Input("external_commitment",
          "whether the date is negotiable, which decides whether delay is an option",
          ASKED,
          question="Is there a customer, contractual or regulatory date attached "
                   "to this release?",
          absent_means="unknown whether the date can move"),
    Input("support_readiness",
          "whether somebody can respond when it goes wrong",
          ASKED,
          question="Who is on call for this, and do they know what changed?",
          absent_means="support readiness unexamined"),
    Input("accepted_known_issues",
          "the difference between a defect nobody saw and one somebody signed for",
          ASKED, required=False,
          question="Which open defects are we shipping deliberately, and who "
                   "accepted each?",
          absent_means="unknown which known issues are accepted"),
)


ASSESSMENTS: dict[str, tuple[Input, ...]] = {
    REQUIREMENT: REQUIREMENT_INPUTS,
    RELEASE: RELEASE_INPUTS,
}


def inputs_for(assessment: str) -> tuple[Input, ...]:
    try:
        return ASSESSMENTS[assessment]
    except KeyError:
        raise UnknownAssessment(
            f"no inputs declared for {assessment!r}. Known: "
            f"{', '.join(sorted(ASSESSMENTS))}") from None


def plan(assessment: str) -> dict:
    """What this assessment needs, split by who can supply it."""
    declared = inputs_for(assessment)
    return {
        "assessment": assessment,
        "gathered": [
            {"name": i.name, "why": i.why, "tool": i.tool,
             "required": i.required, "absent_means": i.absent_means}
            for i in declared if i.source == GATHERED],
        "asked": [
            {"name": i.name, "why": i.why, "question": i.question,
             "required": i.required, "absent_means": i.absent_means}
            for i in declared if i.source == ASKED],
        "means": (
            "the `asked` half cannot be derived from code, a graph or a test "
            "run. An assessment that omits them is not a low-risk assessment, "
            "it is an unfinished one"),
    }


def completeness(assessment: str, gathered: dict | None = None,
                 answers: dict | None = None) -> dict:
    """Whether the assessment has what it needs, and precisely what is missing.

    A value counts as supplied when its key is present and not None. An empty
    string counts as supplied: "no external dependency" is an answer, and
    treating it as absence would ask the same question forever.
    """
    have_gathered = gathered or {}
    have_answers = answers or {}
    missing: list[dict] = []

    for item in inputs_for(assessment):
        supplied = (have_gathered if item.source == GATHERED else have_answers)
        if item.name in supplied and supplied[item.name] is not None:
            continue
        missing.append({
            "name": item.name,
            "source": item.source,
            "required": item.required,
            "absent_means": item.absent_means,
            **({"question": item.question} if item.source == ASKED else
               {"tool": item.tool}),
        })

    blocking = [m for m in missing if m["required"]]
    return {
        "assessment": assessment,
        # The field the whole module exists for. `_ALWAYS_KEPT` carries it so it
        # cannot be pruned when it is the interesting value.
        "status": INCOMPLETE if blocking else COMPLETE,
        "missing_inputs": missing,
        "missing_required": [m["name"] for m in blocking],
        "means": (
            "REQUIRED INPUTS ARE MISSING. This is not a low-risk result — it is "
            "an unfinished assessment, and the gaps below say what nobody has "
            "answered yet" if blocking else
            "every declared input was supplied. The findings rest on all of "
            "them, not on the half that was reachable"),
    }
