"""The test documentation standards, and which part of a design answers each.

**Why a map rather than more sections.** ISO/IEC/IEEE 29119-3 names six design-time
work products and IEEE 829 names eight documents. Métis already carries most of
their *content* across the sections `sections.py` serves; what it lacked was
the standard's
vocabulary, so a reader asking "does this satisfy 29119-3?" had to answer by
reading the whole document and deciding for themselves.

Fragmenting a design into one file per work product produces less deterministic
output, not more — a dozen mostly-empty annexes. So the sections stay, and this
maps them.

**`out-of-scope` is a real answer and three products get it.** A Test Log, a Test
Incident Report and a Test Summary Report are execution and reporting artefacts.
Claiming them here would be claiming C-10's ledger and C-11's correctness figure
in one move, which is the conflation the whole coverage design exists to prevent.
Each says where it actually lives.

**Every claim is checkable in both directions.** A work product naming a section
that does not exist fails a test; a section claimed by no work product and not
listed in `METIS_OWN` fails the other one. That is the property that stops this
becoming a hand-maintained index — `docs/academy/10-where-a-thing-belongs.md` is
explicit that those rot and generated ones do not.

**What this module does NOT claim.** That a design *satisfies* a standard. It says
which section answers which work product, and where the answer is partial it says
what is missing. Whether the result is sufficient for an audit is a person's
judgement about their obligations, not a property Métis can compute.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The two standards this maps. IEEE 829 is superseded by 29119-3 and is still
#: the common naming reference, which is why both are carried rather than one.
ISO_29119_3 = "ISO/IEC/IEEE 29119-3"
IEEE_829 = "IEEE 829-2008"

#: How completely a design answers a work product.
FULL, PARTIAL, OUT_OF_SCOPE = "full", "partial", "out-of-scope"
COVERAGE = (FULL, PARTIAL, OUT_OF_SCOPE)


@dataclass(frozen=True)
class WorkProduct:
    """One named document from a standard, and where Métis answers it."""

    code: str
    name: str
    standard: str
    #: What the standard asks the product to contain.
    purpose: str
    #: Design sections that answer it. Empty exactly when `out-of-scope`.
    sections: tuple[str, ...]
    coverage: str
    #: Why, wherever the answer is not `full`. Mandatory on `partial` and
    #: `out-of-scope`, and asserted so — a gap with no reason is indistinguishable
    #: from one nobody looked at.
    because: str = ""


WORK_PRODUCTS: tuple[WorkProduct, ...] = (
    WorkProduct(
        "TP", "Test Plan", ISO_29119_3,
        "scope, approach, resources and schedule for a set of test activities",
        ("basis", "compliance", "uncertainty"), PARTIAL,
        "TD-2: a design is not a test plan. The scope, the basis it rests on and "
        "the entry/exit criteria are carried; schedule, estimate and resourcing "
        "are not, and Métis has no input that would let it invent them. The "
        "uncertainty ledger goes the other way and exceeds the element it "
        "answers: the standard's risks-and-contingencies assumes the plan's "
        "inputs exist, and that ledger is a list of the ones that do not"),
    WorkProduct(
        "TDS", "Test Design Specification", ISO_29119_3,
        "the test approach for a feature: its test conditions, the coverage "
        "items they yield, and the pass/fail criteria",
        # `verification` belongs here rather than in `METIS_OWN`: box
        # transparency and what a test at that depth establishes IS the test
        # approach, which is what a TDS documents. Its sibling `validation` is
        # NOT here -- 29119-3 designs tests against a specification and cannot
        # ask whether the specification came from the need or from the code.
        ("conditions", "technique", "dimensions", "verification", "security",
         "performance", "contract", "journey"), FULL),
    WorkProduct(
        "TCS", "Test Case Specification", ISO_29119_3,
        "concrete inputs, preconditions and expected results for a condition",
        (), OUT_OF_SCOPE,
        "rendered by `metis-test-generate` from an approved model (§7), not by "
        "the design. TD-4: a design that could feed generation would let an "
        "edited document become the source of what gets tested"),
    WorkProduct(
        "TPR", "Test Procedure Specification", ISO_29119_3,
        "the ordered steps that execute one or more test cases",
        (), OUT_OF_SCOPE,
        "`metis-test-generate` renders a `.feature` file as specification. "
        "Binding it to a runner is R8's seam and belongs to whoever executes"),
    WorkProduct(
        "TDR", "Test Data Requirements", ISO_29119_3,
        "what the data must satisfy for each coverage item",
        ("data",), FULL),
    WorkProduct(
        "TER", "Test Environment Requirements", ISO_29119_3,
        "the environments, access and configuration execution needs",
        ("setup", "levels"), PARTIAL,
        "the cost of reaching each behaviour is computed from the setup chain; "
        "which environments exist is an `asked` input, so a level can be "
        "assigned and not scheduled until somebody answers it"),
    WorkProduct(
        "TITR", "Test Item Transmittal Report", IEEE_829,
        "identifies the exact items being delivered for test",
        ("basis", "machine"), PARTIAL,
        "the claims and the recovered behaviour in scope are named with their "
        "provenance and lifecycle state; a build or delivery identifier is not "
        "something Métis observes. The drawn machine exceeds what the product "
        "asks for — no documentation standard requests one, because none of "
        "them assumes a model was recovered rather than written"),
    WorkProduct(
        "TL", "Test Log", IEEE_829,
        "a chronological record of what was executed and observed",
        (), OUT_OF_SCOPE,
        "an execution artefact. Métis ingests execution results at Quarantine "
        "(§8.7) and C-10 keeps them out of the coverage ledger; producing the "
        "log is the runner's job"),
    WorkProduct(
        "TIR", "Test Incident Report", IEEE_829,
        "records an anomaly encountered during execution",
        (), OUT_OF_SCOPE,
        "a defect is filed from observed failure evidence, which a design has "
        "none of. See the defect route"),
    WorkProduct(
        "TSR", "Test Summary Report", IEEE_829,
        "summarises testing activity and results against exit criteria",
        (), OUT_OF_SCOPE,
        "`coverage_report` and `metis-release-readiness` own it. A design states "
        "what should be tested; what happened is a different claim (C-11)"),
)


#: Sections that answer **no** named work product at all, each with the reason.
#: **The list is the honest half of the map**: without it, a section absent from
#: every work product would be indistinguishable from one somebody forgot to map,
#: and the both-directions test could not tell them apart either.
#:
#: A section that *partially* answers a product does not belong here — its
#: beyond-the-standard character goes in that product's `because` line instead,
#: so a reader is never told two different things about one section.
METIS_OWN: dict[str, str] = {
    "validation": "whether a behaviour can be validated at all. Neither "
                  "standard has a work product for this, and 29119-3 could "
                  "not: it documents the design of tests against a "
                  "specification, and this asks whether the specification "
                  "itself was written from the need or from the code (S-19). "
                  "ISO/IEC/IEEE 12207 §6.4.8 is where validation lives, and "
                  "that is a life-cycle process rather than a document",
    "mirror": "candidates for criteria nobody wrote. Neither standard has a "
              "work product for this: 29119-3 documents the conditions derived "
              "from a specification, and this proposes the ones the "
              "specification is missing. Claiming it as part of a Test Design "
              "Specification would present proposals as derived conditions, "
              "which is the merge C-11 forbids one domain over",
    "obligations": "what an endpoint's own shape obliges it to do, judged "
                   "against the outcomes actually recovered. The standards "
                   "describe deriving conditions from a specification; this "
                   "derives them from the implementation and asks",
    "profile": "the defect-proneness factors behind a risk band. 29119-2 makes "
               "risk the basis of the test process and does not say what to "
               "measure; this says, from what extraction recovered",
}


class UnknownWorkProduct(Exception):
    """Raised for a code that names no declared work product."""


def by_code(code: str) -> WorkProduct:
    try:
        return next(w for w in WORK_PRODUCTS if w.code == code)
    except StopIteration:
        raise UnknownWorkProduct(
            f"no work product {code!r}. Known: "
            f"{', '.join(w.code for w in WORK_PRODUCTS)}") from None


def products_for(section: str) -> tuple[WorkProduct, ...]:
    """Every work product a design section contributes to."""
    return tuple(w for w in WORK_PRODUCTS if section in w.sections)


def code_for(section: str) -> str:
    """The work-product code a section's rows carry, or `""`.

    A section contributing to several products takes the first, which is the
    ordering `WORK_PRODUCTS` declares rather than an arbitrary one — and a row's
    code is a *classification*, never a second identity. Ids stay content-derived
    (TD-32).
    """
    found = products_for(section)
    return found[0].code if found else ""


def describe() -> dict:
    """The map, for a tool and for a test."""
    return {
        "work_products": [
            {"code": w.code, "name": w.name, "standard": w.standard,
             "purpose": w.purpose, "sections": list(w.sections),
             "coverage": w.coverage, "because": w.because}
            for w in WORK_PRODUCTS],
        "metis_own": [{"section": key, "because": why}
                      for key, why in sorted(METIS_OWN.items())],
        "standards": sorted({w.standard for w in WORK_PRODUCTS}),
        "means": (
            "which section answers which named work product, and where the "
            "answer is partial, what is missing. It does NOT claim the design "
            "satisfies a standard — whether the result meets an obligation is a "
            "judgement about that obligation, not a property Métis computes"),
    }
