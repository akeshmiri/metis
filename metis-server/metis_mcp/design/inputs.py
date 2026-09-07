"""What a test design rests on, and which half of it Métis can supply.

**The rule this module exists for: a design missing a required input reports
`incomplete`, never a finished design.** It is `risk/inputs.py` one domain over,
and the reason it is a second ledger rather than a third assessment inside the
first is that the *asked* half is entirely different. A risk assessment asks what
being wrong costs. A test design asks what the system is made of, where it runs,
and what data it may be given -- and Métis holds none of those.

**Architecture and the design specification are ASKED, and that is the decision
worth stating.** Métis recovers behaviour from code. It could describe an
architecture by summarising what it recovered, and that description would be a
restatement of the implementation wearing the clothes of intent -- S-19's defect
in a new place, where a design derived from the code can only ever report that
the code agrees with itself. So the architecture is a question, its absence is
recorded, and the design says which sections it therefore could not state.

**Every input names what its absence MEANS**, and none of those strings may read
as reassurance. `test_design_sections.py` asserts it, the same way
`test_risk.py` does: the string is printed where the value should have been, and
a design whose gaps read as "fine" is worse than one with no gaps section at all.

**What is deliberately NOT here.** No completeness percentage. A design missing
`environments` and a design missing an optional contradiction search are not 40%
and 90% finished; they are a design that cannot be executed and a design that
can. A percentage over incommensurable inputs invents precision and makes a hole
look like a deduction.
"""
from __future__ import annotations

from dataclasses import dataclass

GATHERED, ASKED = "gathered", "asked"
SOURCES = (GATHERED, ASKED)

COMPLETE, INCOMPLETE = "complete", "incomplete"


class UnknownSection(Exception):
    """Raised for a section name that has no declared inputs."""


@dataclass(frozen=True)
class Input:
    """One thing a design needs, and where it comes from."""

    name: str
    #: What this input DECIDES. Never "context": an input that decides nothing is
    #: one nobody will supply, and it dilutes the list of the ones that matter.
    why: str
    source: str
    #: `gathered`: the MCP tool that supplies it, so the claim is traceable to
    #: something a reader can go and disagree with.
    tool: str = ""
    #: `asked`: the exact words to put to a person. A topic gets a shrug.
    question: str = ""
    required: bool = True
    #: What it means when this is absent. Printed where the value should have
    #: been, and never permitted to read as reassurance.
    absent_means: str = ""
    #: Which sections stop being statable without it. Empty means every section.
    decides_sections: tuple[str, ...] = ()

    def describe(self) -> str:
        where = f"via `{self.tool}`" if self.source == GATHERED else "ask a person"
        return f"[{self.source}] {self.name} — {self.why} ({where})"


#: The basis: what somebody said the system should do, and what Métis recovered.
#: Every one of these is gathered, which is the half that made a design look
#: finished when the asked half below was untouched.
BASIS_INPUTS: tuple[Input, ...] = (
    Input("requirement", "the claim the design is meant to demonstrate",
          GATHERED, tool="get_requirement",
          absent_means="no stated requirement is in scope — the design can only "
                       "describe what the code does, which is not a test of "
                       "anything (S-19)",
          decides_sections=("basis",)),
    Input("ears_conformance", "whether the wording is testable at all",
          GATHERED, tool="check_ears",
          absent_means="the wording was not checked, so two readers may satisfy "
                       "this design differently (S-13)",
          decides_sections=("basis",)),
    Input("acceptance_criteria",
          "the sentences a case is allowed to assert against",
          GATHERED, tool="get_requirement",
          absent_means="nothing states what 'correct' is, so every assertion in "
                       "this design would be one Métis chose",
          decides_sections=("basis", "technique")),
    Input("criteria_provenance",
          "criteria written from the code can only report agreement (S-19)",
          GATHERED, tool="get_requirement",
          absent_means="unknown whether the criteria are independent of the code "
                       "they would be testing",
          decides_sections=("basis",)),
    Input("criterion_quality",
          "unmeasurable qualifiers and non-atomic criteria, which no case can assert",
          GATHERED, tool="ac_quality",
          absent_means="criterion wording was not checked",
          decides_sections=("basis",)),
    Input("specification",
          "how the need behaves, stated so it can be checked (§4.1)",
          GATHERED, tool="get_spec",
          absent_means="no specification is in scope — a need nobody has stated "
                       "the behaviour of cannot be designed against",
          decides_sections=("basis",)),
    Input("model",
          "the states, transitions and guards the design walks",
          GATHERED, tool="get_model",
          absent_means="no recovered behaviour — there is nothing to design over",
          decides_sections=()),
    Input("model_is_approved",
          "only Approved may be generated from (D-10)",
          GATHERED, tool="test_cases",
          absent_means="approval state unknown; a design over unreviewed "
                       "behaviour is a preview, never a plan",
          decides_sections=("basis",)),
    Input("validation_findings",
          "a model with blocking findings cannot support a design (M-18)",
          GATHERED, tool="validate_model",
          absent_means="model well-formedness unknown",
          decides_sections=("basis",)),
)

#: What the model itself yields per section, and the risk wiring.
DERIVED_INPUTS: tuple[Input, ...] = (
    Input("guards", "the conditions a technique partitions and bounds",
          GATHERED, tool="get_model",
          absent_means="no guard text — equivalence partitioning and boundary "
                       "analysis have nothing to read, and a technique chosen "
                       "without them would be chosen on a name",
          decides_sections=("technique", "data")),
    Input("guard_dimensions",
          "the short-circuit chain that bounds the combinatorial cost (GD-1)",
          GATHERED, tool="get_model",
          absent_means="no guard check was recovered, so no chain could be "
                       "built. The reduction is unavailable and a count over "
                       "these conditions is the full product, not the bounded "
                       "one (GD-9)",
          decides_sections=("dimensions",)),
    Input("condition_inventory",
          "the eight condition classes, each with an explicit decision — the "
          "denominator a design's completeness is measured against",
          GATHERED, tool="get_model",
          absent_means="no condition inventory was built, so a positive case "
                       "counts as coverage for conditions it never asserts",
          decides_sections=("conditions",)),
    Input("negative_obligations",
          "the negative behaviour each endpoint's own shape obliges it to have",
          GATHERED, tool="get_model",
          absent_means="no obligation was derived, so an endpoint that takes a "
                       "path parameter and produces no not-found is "
                       "indistinguishable from one that does",
          decides_sections=("obligations",)),
    Input("risk_factors",
          "what is behind the band — a band says how much there is to get "
          "wrong and hides what, and the answer changes the response",
          GATHERED, tool="product_risk",
          absent_means="only the band is known, so 'test this more' is the only "
                       "response available and it is rarely the right one",
          decides_sections=("profile",)),
    Input("setup_cost",
          "what it takes to reach each behaviour, from the setup chain itself",
          GATHERED, tool="test_cases",
          absent_means="setup cost unexamined; what to automate first would be "
                       "decided by what is easy to describe rather than by what "
                       "is cheap to reach",
          decides_sections=("setup",)),
    Input("payload_shape", "the accepted space each input has (X-6e)",
          GATHERED, tool="payload_shape",
          absent_means="the accepted space is unknown, so data conditions cannot "
                       "be stated and would have to be invented (M-9)",
          decides_sections=("data",)),
    Input("auth_facts", "which identity and which authority each call requires",
          GATHERED, tool="auth_facts",
          absent_means="authorisation is unrecovered — an absent finding here is "
                       "'nobody looked', not 'nothing is exposed'",
          decides_sections=("security",)),
    Input("existing_coverage",
          "what a test already reaches, and whether it asserts the outcome",
          GATHERED, tool="coverage_report",
          absent_means="coverage was not measured — which is not the same as "
                       "zero coverage, and only one of them is a design gap",
          decides_sections=("levels",)),
    Input("viability", "whether behaviour can be automated at all, and why not",
          GATHERED, tool="test_design",
          absent_means="automatability unexamined; a design that skips it "
                       "automates things it cannot assert",
          decides_sections=("levels", "performance")),
    Input("contract", "the endpoint's own declaration, and where it deviates",
          GATHERED, tool="payload_shape", required=False,
          absent_means="no contract was read; deviation between the document and "
                       "the code is unexamined",
          decides_sections=("contract",)),
    Input("cross_surface", "which UI action invokes which call (M-5c)",
          GATHERED, tool="journey_walkthrough", required=False,
          absent_means="the UI and API halves were not joined, so a journey "
                       "section would describe two disconnected models",
          decides_sections=("journey",)),
    Input("risk_band",
          "which behaviour warrants depth — the whole basis of risk-based testing",
          GATHERED, tool="product_risk",
          absent_means="nothing was rated, so this design's order is the model's "
                       "order and not a priority anybody chose",
          decides_sections=()),
    Input("risk_priority", "the order to work in, by what would go unnoticed",
          GATHERED, tool="risk_priority",
          absent_means="no ordering was computed; the rows are in id order",
          decides_sections=()),
)

#: The half no tool supplies. This is the list that makes a design `incomplete`,
#: and every question here is one somebody can actually answer.
ASKED_INPUTS: tuple[Input, ...] = (
    Input("runtime_architecture",
          "where the boundaries are, which decides what an integration test is",
          ASKED,
          question="What does this run as, and what does it talk to? Name the "
                   "processes, the datastores and the systems you do not own.",
          absent_means="INTEGRATION BOUNDARIES UNKNOWN — no integration or "
                       "contract design can be stated, and what is written here "
                       "describes one process as though it were the system",
          decides_sections=("contract", "journey", "levels")),
    Input("design_specification",
          "the intended internal design, where it differs from what was recovered",
          ASKED,
          question="Is there a design document for this, and where does the "
                   "intended design differ from what the code currently does?",
          absent_means="THE DESIGN UNDER TEST IS THE ONE RECOVERED FROM CODE. "
                       "It can only report that the implementation agrees with "
                       "itself (S-19), never that it is right",
          decides_sections=("basis", "technique")),
    Input("environments",
          "whether a level can be executed at all, as opposed to assigned",
          ASKED,
          question="Which environments exist for this, who owns each, and what "
                   "can actually be run in them?",
          absent_means="LEVELS CAN BE ASSIGNED BUT NOT EXECUTED — every level "
                       "below is a proposal, and none of it is schedulable",
          decides_sections=("levels", "setup")),
    Input("test_data_constraints",
          "whether a data condition can be turned into data by anybody",
          ASKED,
          question="Where does test data come from, what may not appear in it "
                   "(personal data, production extracts), and who provisions it?",
          absent_means="DATA CONDITIONS CANNOT BE SATISFIED. Métis states the "
                       "condition and never the value (M-9); without this nobody "
                       "knows who turns one into the other",
          decides_sections=("data", "setup")),
    Input("nfr_targets",
          "the threshold a performance case is judged against",
          ASKED,
          question="What load must this carry, and what response time or error "
                   "rate would count as a failure? Name a number or say there "
                   "is none.",
          absent_means="NO BASIS FOR PERFORMANCE DESIGN. Métis reports "
                       "`no-basis` rather than `functional-only`, because the "
                       "second reads as 'measured, and none qualify'",
          decides_sections=("performance",)),
    Input("dependency_behaviour",
          "what must happen when a required dependency fails — a class no "
          "static analysis draws",
          ASKED,
          question="What does this depend on that can fail — a database, a "
                   "queue, another service — and what must happen when it "
                   "does? Name the behaviour, not the error code.",
          absent_means="DEPENDENCY-FAILURE IS UNDRAWN. Métis recovers the happy "
                       "path and the branches in this code; what happens when "
                       "something outside it stops answering is not in the "
                       "source it read",
          decides_sections=("conditions",)),
    Input("security_obligations",
          "whether an authorisation defect is a compliance event or a bug",
          ASKED,
          question="Which roles may do what here, and is any of it subject to an "
                   "external obligation — regulation, contract, audit?",
          absent_means="AUTHORISATION CONDITIONS ARE UNRATED. The recovered "
                       "checks are listed; whether they are the right ones is "
                       "not a question static analysis can answer",
          decides_sections=("security",)),
    Input("entry_exit_criteria",
          "the threshold this design is judged against — without it, a band is decoration",
          ASKED,
          question="What has to be true before testing starts, and what would "
                   "make you stop? Name the residual risk you would accept.",
          absent_means="NO THRESHOLD — this design can say what it covers and "
                       "not whether that is enough",
          decides_sections=()),
    Input("out_of_scope",
          "what is deliberately not designed for, so a gap is not read as an oversight",
          ASKED, required=False,
          question="What is deliberately out of scope for this design, and who "
                   "decided?",
          absent_means="scope boundary unrecorded; every gap below reads as an "
                       "omission, and the `non-goal` condition class has nothing "
                       "to record",
          decides_sections=("conditions",)),
)


INPUTS: tuple[Input, ...] = BASIS_INPUTS + DERIVED_INPUTS + ASKED_INPUTS

#: Name -> input, built once. A duplicate name would silently shadow, so
#: `test_design_sections.py` asserts the names are unique.
BY_NAME: dict[str, Input] = {i.name: i for i in INPUTS}


def inputs_for(section: str = "") -> tuple[Input, ...]:
    """Every declared input, or only those a named section depends on.

    An input with no `decides_sections` is cross-cutting and belongs to every
    section: the model itself, the risk band and the exit criteria are not any
    one section's business.
    """
    if not section:
        return INPUTS
    from metis_mcp.design.sections import SECTIONS

    if section not in SECTIONS:
        raise UnknownSection(
            f"no section named {section!r}. Known: {', '.join(sorted(SECTIONS))}")
    return tuple(i for i in INPUTS
                 if not i.decides_sections or section in i.decides_sections)


def plan(section: str = "") -> dict:
    """What this design needs, split by who can supply it."""
    declared = inputs_for(section)
    return {
        "section": section or "all",
        "gathered": [
            {"name": i.name, "why": i.why, "tool": i.tool,
             "required": i.required, "absent_means": i.absent_means,
             "decides_sections": list(i.decides_sections)}
            for i in declared if i.source == GATHERED],
        "asked": [
            {"name": i.name, "why": i.why, "question": i.question,
             "required": i.required, "absent_means": i.absent_means,
             "decides_sections": list(i.decides_sections)}
            for i in declared if i.source == ASKED],
        "means": (
            "the `asked` half cannot be derived from code, a graph or a test "
            "run. Architecture and the design specification are there on "
            "purpose: describing them from what was recovered would restate the "
            "implementation as its own intent (S-19). A design that omits them "
            "is not a low-risk design, it is an unfinished one"),
    }


def completeness(gathered: dict | None = None, answers: dict | None = None,
                 section: str = "") -> dict:
    """Whether the design has what it needs, and precisely what is missing.

    A value counts as supplied when its key is present and not None. An empty
    string counts as supplied: "nothing is out of scope" is an answer, and
    treating it as absence would ask the same question for ever.
    """
    have_gathered = gathered or {}
    have_answers = answers or {}
    missing: list[dict] = []

    for item in inputs_for(section):
        supplied = (have_gathered if item.source == GATHERED else have_answers)
        if item.name in supplied and supplied[item.name] is not None:
            continue
        missing.append({
            "name": item.name,
            "source": item.source,
            "required": item.required,
            "absent_means": item.absent_means,
            "decides_sections": list(item.decides_sections),
            **({"question": item.question} if item.source == ASKED else
               {"tool": item.tool}),
        })

    blocking = [m for m in missing if m["required"]]
    return {
        "section": section or "all",
        # The field this module exists for.
        "status": INCOMPLETE if blocking else COMPLETE,
        "missing_inputs": missing,
        "missing_required": [m["name"] for m in blocking],
        "means": (
            "REQUIRED INPUTS ARE MISSING. This is not a lean design — it is an "
            "unfinished one, and the entries above say what nobody has supplied "
            "yet" if blocking else
            "every declared input was supplied. What follows rests on all of "
            "them, not on the half that was reachable"),
    }


def unstatable(missing_required: list[str]) -> dict[str, list[str]]:
    """Section -> the required inputs it is missing.

    The join that turns a ledger into something a document can act on: a section
    whose inputs were not supplied still renders, and it renders saying which
    answer it is waiting for rather than looking empty.
    """
    out: dict[str, list[str]] = {}
    for name in missing_required:
        item = BY_NAME.get(name)
        if item is None:
            continue
        for section in item.decides_sections:
            out.setdefault(section, []).append(name)
    return {k: sorted(v) for k, v in sorted(out.items())}
