"""The published standards Métis works against, and where each one is answered.

**Why a registry rather than more prose.** Métis named six standards and carried
a document for two of them. ISO/IEC/IEEE 29119-3 existed as a *tool*
(`design_standards`) with no reference file; 29119-4 and ISO/IEC 25010 were bare
mentions inside `SKILL.md` sentences; 29148 appeared only in engine docstrings,
where no skill could reach it; and ISO 31000 — the risk management standard —
was named nowhere at all, in a family that runs a full risk lifecycle across
thirteen specialists.

A reader asking "which standard governs this skill, and where do I read it?" had
to grep. That is the same hand-maintained-index failure
`docs/academy/10-where-a-thing-belongs.md` records twice, so the map is data and
`test_standards.py` asserts it in both directions: every registered standard has
a reference file on disk under a skill that exists, and every reference file
naming a standard is registered.

**Two surfaces, and the split is the placement rule, not a preference.** The
standard's own content — what the document says, which clauses exist, what a work
product is for — is `references/`: *it would still be true if Métis were
deleted*. What Métis computes against it, and what it refuses to claim, is
`knowledge/`, generated from a module docstring so it cannot drift. Neither half
is sufficient alone: a reference with no Métis reading is a photocopy, and a
reading with no reference is an assertion nobody can check.

**`refuses` is mandatory on every entry, and that is the load-bearing field.**
`design/standards.py` already forbids a `because` line that reads as a compliance
claim, for the reason it gives at length: Métis can say which section answers
which work product, and cannot say whether that satisfies anybody's obligation.
Extending the registry without extending that prohibition would produce exactly
the artefact the prohibition exists to prevent — a table that looks like a
certificate. So an entry with an empty `refuses` fails a test.

**What this module does not do.** It does not reproduce the standards; they are
copyrighted documents that must be purchased, and a paraphrase detailed enough to
substitute for one would be both a licence problem and a worse source than the
original. The reference files state the structure, the vocabulary and the mapping
— enough to place Métis's output against a clause somebody else is reading.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Standard:
    """One published standard, and the part of Métis that answers to it."""

    code: str
    title: str
    #: The skills whose procedure it governs. More than one is why a reference
    #: lives in `shared/references/` -- the promotion rule counts consumers.
    skills: tuple[str, ...]
    #: The reference file, relative to `plugins/metis/skills/`.
    reference: str
    #: What Métis actually computes against it. Each entry names the module or
    #: tool that does the computing, so a reader can go and disagree with it.
    #: **Empty is legal and means nothing computes it** — the alignment is a
    #: reading a person recorded. An entry that is empty must say so in
    #: `refuses`, which `test_standards.py` asserts.
    computes: tuple[str, ...]
    #: What Métis does NOT claim. Mandatory: an entry without one reads as a
    #: compliance claim, which is the single thing this registry must never be.
    refuses: str


STANDARDS: tuple[Standard, ...] = (
    Standard(
        code="ISO/IEC/IEEE 29119-2",
        title="Software testing — Test processes",
        skills=("metis-risk-manager",),
        reference="metis-risk-manager/references/iso-29119-2-risk-based-testing.md",
        computes=(
            "the risk-based test strategy the standard's organisational and "
            "test-management processes assume, in `risk/prioritisation.py`",
            "the product risk factors behind a band, in `risk/product.py`",
            "the risk breakdown taxonomy, in `risk/rbs.py`",
        ),
        refuses=(
            "It does not claim Métis implements the standard's test processes. "
            "29119-2 describes an organisation's test management, monitoring and "
            "control; Métis computes the risk arithmetic those processes consume "
            "and never runs the processes themselves."),
    ),
    Standard(
        code="ISO/IEC/IEEE 29119-3",
        title="Software testing — Test documentation",
        skills=("metis-test-design", "metis-test-generate"),
        reference="shared/references/iso-29119-3-test-documentation.md",
        computes=(
            "which design section answers each of the six design-time work "
            "products, in `design/standards.py`, served by `design_standards()` "
            "and rendered as the `compliance` section",
            "the test case and test procedure specifications, in "
            "`rendering/test_case.py`",
        ),
        refuses=(
            "It is a coverage map, never a compliance claim. Three work products "
            "— Test Log, Test Incident Report, Test Summary Report — are marked "
            "`out-of-scope` because they are execution and reporting artefacts, "
            "and claiming them would claim C-10's ledger and C-11's correctness "
            "figure in one move."),
    ),
    Standard(
        code="ISO/IEC/IEEE 29119-4",
        title="Software testing — Test techniques",
        skills=("metis-coverage-report", "metis-behavior-modeling",
                "metis-test-design-technique"),
        reference="shared/references/iso-29119-4-coverage-measures.md",
        computes=(
            "the coverage criteria and their measures, in `mbt/criteria.py`",
            "equivalence partitioning, boundary analysis, decision tables and "
            "pairwise selection, in `mbt/techniques.py` and `mbt/design.py`",
        ),
        refuses=(
            "A coverage measure answers *is this tested*, never *does it pass* "
            "(C-11). The standard's measures are computed over the recovered "
            "model, so a figure is bounded by what extraction reached — which "
            "`coverage_report`'s `unmeasured` states rather than hides."),
    ),
    Standard(
        code="ISO/IEC/IEEE 29148",
        title="Requirements engineering",
        skills=("metis-knowledge-capture", "metis-business-analyst",
                "metis-intake-processor", "metis-spec-writeback"),
        reference="shared/references/iso-29148-requirements.md",
        computes=(
            "the characteristics of a well-formed requirement, as EARS "
            "conformance, in `ears_checker.py` and the `check_ears` tool",
            "unmeasurable qualifiers and non-atomicity in an authored "
            "criterion, in the `ac_quality` tool — advisory, blocking nothing",
        ),
        refuses=(
            "Conformance to a sentence pattern is not correctness of a claim. "
            "`check_ears` decides whether text can be represented as a "
            "`Requirement`; whether the requirement is the right one is a "
            "person's judgement, and `ac_quality` is explicitly advisory (S-4)."),
    ),
    Standard(
        code="ISO/IEC 25010",
        title="Systems and software quality models",
        skills=("metis-risk-manager-product-risk",),
        reference="metis-risk-manager/references/iso-25010-quality-model.md",
        computes=(
            "the quality characteristics used as risk categories, in "
            "`risk/rbs.py`",
        ),
        refuses=(
            "Métis does not measure a quality characteristic. It uses the model "
            "as a taxonomy so that a register's categories are a closed "
            "vocabulary rather than free text — `risk_register_check` reports "
            "what is incoherent in a register, never whether a risk is real."),
    ),
    Standard(
        code="ISO 31000",
        title="Risk management — Guidelines",
        skills=("metis-risk-manager",),
        reference="metis-risk-manager/references/iso-31000-risk-management.md",
        computes=(
            "the lifecycle the family routes through — plan, identify, analyse, "
            "respond, monitor, close — in `workflow/stages.py`",
            "exposure, EMV and PERT, in `risk/exposure.py`, `risk/emv.py` and "
            "`risk/pert.py`",
            "a register's internal coherence, in `risk/register.py`",
        ),
        refuses=(
            "ISO 31000 is guidance, not a certifiable requirements standard, and "
            "Métis makes no conformance claim against it. It also never merges "
            "the two kinds of risk: one Métis derived from a model carries "
            "`derived_from: model` and `probability: null` until a person sets "
            "one, and is never averaged with a risk somebody asserted."),
    ),
    Standard(
        code="IEEE 829-2008",
        title="Software and system test documentation",
        skills=("metis-test-design",),
        reference="metis-test-design/references/ieee-829-work-products.md",
        computes=(
            "which design section answers each of the eight documents, in "
            "`design/standards.py`",
        ),
        refuses=(
            "829 is superseded by 29119-3 and is carried only because it remains "
            "the common naming reference. Answering an 829 document is not a "
            "claim to have produced it in the form 829 specifies."),
    ),
    Standard(
        code="ISO/IEC/IEEE 12207 and 15288",
        title="Life cycle processes — software, and systems",
        skills=("metis-test-design",),
        reference="metis-test-design/references/life-cycle-alignment.md",
        # **Empty on purpose, and the only entry that is.** Nothing computes a
        # life-cycle alignment: it is a reading a person did, recorded in the
        # reference. Naming a module here to satisfy the shape of the other
        # entries would put a fabricated citation where the honest answer is
        # "nobody computes this" -- which is the failure mode every `refuses`
        # field in this file exists to prevent.
        computes=(),
        refuses=(
            "Nothing computes this alignment; it is a reading a person recorded "
            "in the reference, and no tool checks it. "
            "Architecture and design definition is an `asked` input, not a "
            "recovered one. Métis could summarise the architecture it recovered, "
            "and that summary would be the implementation restated as its own "
            "intent — S-19 in a new place."),
    ),
)


def for_skill(skill: str) -> tuple[Standard, ...]:
    """Every standard governing one skill, parent or specialist."""
    return tuple(s for s in STANDARDS if skill in s.skills)


def by_code(code: str) -> Standard | None:
    return next((s for s in STANDARDS if s.code == code), None)


def describe() -> dict:
    """The map, for a tool and for a test."""
    return {
        "standards": [
            {"code": s.code, "title": s.title, "skills": list(s.skills),
             "reference": s.reference, "computes": list(s.computes),
             "refuses": s.refuses}
            for s in STANDARDS],
        "means": (
            "which published standard governs which skill, where to read it, "
            "what Métis computes against it, and what it refuses to claim. A "
            "coverage map, never a compliance claim: whether the result meets "
            "an obligation is a judgement about the obligation"),
        "does_not_include": (
            "the text of any standard. These are purchased documents; the "
            "references state structure, vocabulary and mapping so that Métis "
            "output can be placed against a clause somebody else is reading"),
    }
