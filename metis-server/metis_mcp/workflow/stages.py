"""
The stage registry and the workflow definitions (application spec §3.2, §3.4).

**This is the single place that knows the order.** Before it, the ordering lived
in `reingest_the pilot estate.sh`, in two throwaway scripts under `/tmp`, in four
`print("next: ...")` hints inside the CLI, and in the operator's memory. §3.2 has
described seven ordered stages and two gates since the specification was
approved; nothing executed them.

**Two gates, and only two (§3.4).** An earlier draft of this layer added a third
-- a criteria-review gate before landing -- and it could not work: `decisions.
promotion_for` fires only on `decision == APPROVE`, and there is nothing to
approve before elements are landed. So criteria are carried *into* G1 instead,
which is also where §3.4 already puts the decision.

**Ordinals are local and monotonic, not a shared global catalog.** Atlas's sparse
global ordinals earn their indirection because eleven workflows share fifteen
LLM phases there. Five workflows over one linear pipeline do not, and a global
catalog with three empty slots is a lint rule protecting nothing.

**A stage that reports is not a stage that failed.** F-9 says a failed stage
stops the run; F-4 says reconciliation never blocks, because its findings ARE its
output. `blocking=False` is what keeps those two rules from contradicting each
other -- without it the one stage whose job is to surface gaps looks like the
broken one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# A handler returns (outcome, detail, outstanding, next_command). It never
# decides whether the run continues -- the engine does, from the outcome plus
# `blocking`. Keeping that decision out of the handlers is what stops each one
# growing its own private idea of what a failure means.
Handler = Callable[..., tuple]


@dataclass(frozen=True)
class Stage:
    """One step of a workflow."""

    name: str
    ordinal: int
    handler: str
    summary: str
    # Stage names that must have passed, in this run, against the same input.
    requires: tuple[str, ...] = ()
    # A gate stops the run for a human rather than failing it (§3.4, F-8).
    is_gate: bool = False
    # False for a stage whose findings are the output and never block (F-4).
    blocking: bool = True
    # Registered predicate names, evaluated by the engine. Atlas prints these
    # and calls it validation; here an unregistered name is a lint failure
    # before the workflow can run at all.
    checks: tuple[str, ...] = ()
    # Whether this stage's product survives the process. A resumed run does not
    # replay stages that passed, so a stage whose output lives only in memory
    # leaves the next one with nothing -- which is exactly what happened the
    # first time `publish` ran after a resume: `render` was skipped as "already
    # passed" and `publish` found zero cases.
    #
    # `False` means "re-run me on resume", so it may only be set on a stage that
    # is safe and cheap to repeat. `land` and `publish` stay durable precisely
    # because repeating them writes again.
    durable: bool = True


@dataclass(frozen=True)
class Workflow:
    code: str
    summary: str
    stages: tuple[Stage, ...]
    # Names of registered predicates that must hold before the first stage runs.
    # This is how "other workflows require other areas before or after" is
    # declared rather than remembered.
    preconditions: tuple[str, ...] = ()
    entry_patterns: tuple[str, ...] = ()

    def stage(self, name: str) -> Stage | None:
        return next((s for s in self.stages if s.name == name), None)

    @property
    def ordered(self) -> tuple[Stage, ...]:
        return tuple(sorted(self.stages, key=lambda s: s.ordinal))


_HANDLERS: dict[str, Handler] = {}


def handler(name: str) -> Callable[[Handler], Handler]:
    """Register a stage handler under the name the workflow refers to."""
    def register(fn: Handler) -> Handler:
        _HANDLERS[name] = fn
        return fn
    return register


def get_handler(name: str) -> Handler | None:
    return _HANDLERS.get(name)


def registered_handlers() -> frozenset[str]:
    return frozenset(_HANDLERS)


# ---------------------------------------------------------------------------
# The workflows.
#
# Seven. Atlas has eleven, and the rest have no Métis counterpart: R8 says
# Métis emits test cases rather than executable test code, which removes both
# test-developer families; §12 excludes performance, defect and operational work;
# and the intake processor was dropped by an earlier decision. Inventing Métis
# workflows to match Atlas's count would advertise capability that does not
# exist, which is the failure this whole specification corrects.
# ---------------------------------------------------------------------------

MODEL_BUILD = Workflow(
    code="model-build",
    summary=("Recover behaviour from code, work out what it should do, and settle "
             "that with a human before anything is generated from it."),
    entry_patterns=("build a model for <scope>", "model <repo>",
                    "extract behaviour from <repo>"),
    stages=(
        Stage("extract", 1, "extract",
              "Recover states and transitions from the code property graph (§5).",
              checks=("model_is_wellformed",)),
        Stage("ac-draft", 2, "ac_draft",
              "Read existing acceptance criteria, then draft for the branches "
              "nothing covers (§4.5, S-19).",
              requires=("extract",),
              blocking=False,
              checks=("drafts_are_code_derived",)),
        Stage("land", 3, "land",
              "Land the model at Quarantine — authoring is not approving (S-4).",
              requires=("extract",),
              checks=("landed_at_quarantine",)),
        Stage("validate", 4, "validate",
              "Well-formedness. Any failure blocks (M-18).",
              requires=("land",),
              checks=("model_is_wellformed",)),
        Stage("reconcile", 5, "reconcile",
              "Match criteria to transitions, both directions (§3.3, F-4).",
              requires=("validate",),
              blocking=False),
        Stage("model-approval", 6, "g1",
              "G1 — a human approves the model, with the criteria in front of them.",
              requires=("validate",),
              is_gate=True,
              checks=("model_is_approved",)),
    ),
)

TEST_GENERATE = Workflow(
    code="test-generate",
    summary="Generate covering paths and render them as test cases.",
    entry_patterns=("generate tests for <scope>", "generate test cases for <scope>"),
    preconditions=("model_is_approved",),
    stages=(
        Stage("generate-paths", 1, "generate_paths",
              "Cover the transitions of interest under the chosen criterion (§6).",
              checks=("model_is_approved",), durable=False),
        # Risk-based test prioritisation (ISO/IEC/IEEE 29119-2). Blocking,
        # unlike the other risk stages, because this one REORDERS real output
        # rather than reporting on it -- a half-applied ordering would render a
        # batch in an order nobody chose.
        Stage("prioritise", 2, "prioritise",
              "Order the paths by what would go unnoticed, deterministically.",
              requires=("generate-paths",), durable=False),
        Stage("render", 3, "render",
              "One path, one test case (§7.1).",
              requires=("prioritise",), durable=False),
        Stage("publication-confirmation", 4, "g2",
              "G2 — a literal affirmative confirmation, in this run (T-18).",
              requires=("render",),
              is_gate=True),
        Stage("publish", 5, "publish",
              "Write to the test-management tool.",
              requires=("publication-confirmation",)),
    ),
)

KNOWLEDGE_CAPTURE = Workflow(
    code="knowledge-capture",
    summary=("Turn a stated requirement into atomic acceptance criteria, compare "
             "them against the model, and land what is new at Quarantine."),
    entry_patterns=("capture knowledge for <scope>", "record a requirement for <scope>",
                    "add a rule to <scope>"),
    stages=(
        Stage("check", 1, "knowledge_check",
              "The criteria are atomic, parseable and say what they were derived from.",
              checks=("criteria_are_atomic",),
              # Cheap, pure, and reads a file that must still be there on resume.
              # Re-running it is how a resumed run notices the file changed.
              durable=False),
        Stage("mine", 2, "knowledge_mine",
              "Mine a candidate model from the criteria (§4.5).",
              requires=("check",), durable=False),
        Stage("compare", 3, "knowledge_compare",
              "Already specified, contradicting, or new (I-5, I-8).",
              requires=("mine",),
              # F-4's rule: a stage whose findings ARE its output never blocks.
              # A contradiction is the most valuable thing this run can produce.
              blocking=False, durable=False),
        Stage("land", 4, "knowledge_land",
              "Land both stages at Quarantine: the documentation (Requirement, "
              "AcceptanceCriterion, HAS_AC) and the behaviour mined from it. "
              "Authoring is not approving (S-4).",
              requires=("compare",),
              checks=("landed_at_quarantine",)),
        # The same rule as `intake`: what was authored is assessed before the
        # person who has to approve it sees the gate.
        Stage("requirement-risk", 5, "requirement_risk",
              "The risk in the criteria just written, before approval.",
              requires=("land",), blocking=False, durable=False),
        Stage("model-approval", 6, "g1",
              "G1 — a human approves, with the criteria in front of them.",
              requires=("requirement-risk",),
              is_gate=True,
              checks=("model_is_approved",)),
    ),
)

# **The one major path with no workflow, no gate and no resumable run.**
#
# Requirement ingestion had `metis intake fetch` and `metis intake land` and
# nothing that knew their order, so there was no status to ask for, no resume
# after a failure, and no gate -- while model recovery and test generation both
# had full gated workflows. For a tool whose first job is requirement
# management, that asymmetry was backwards.
#
# It stops at G1 like the others, and for the same reason: a landed requirement
# is a claim somebody made, not a claim Métis agrees with (S-4).
INTAKE = Workflow(
    code="intake",
    summary=("Bring what a tracker or wiki SAYS the system should do into the "
             "graph as claims, and stop for a human."),
    entry_patterns=("intake <scope>", "pull requirements for <scope>",
                    "import the backlog for <scope>"),
    stages=(
        Stage("fetch", 1, "intake_fetch",
              "Tracker or wiki -> UIF documents, every field traced to the "
              "response it came from. Nothing is inferred.",
              # Reads a tracker or a captured response and writes files. Cheap
              # to repeat, and re-running it is how a resumed run notices the
              # source changed -- the same argument `knowledge_check` makes.
              durable=False),
        Stage("validate", 2, "intake_validate",
              "Each document against the UIF schema, before anything is landed.",
              requires=("fetch",),
              # F-4: a stage whose findings ARE its output never blocks. A
              # non-conformant document lands as a Finding, which is the honest
              # outcome and not a failure of the run.
              blocking=False, durable=False),
        # **The reading happens BEFORE landing, and that is the change.** This
        # workflow used to fetch, validate, land, THEN assess risk, so the first
        # moment anybody saw what was wrong with a claim was after it was a node.
        # Intent is a pre-processor; these two stages are what make that true.
        Stage("analysis", 3, "intent_analysis",
              "Read the document from four directions — intent, requirement, "
              "design, risk. Reporting: the gaps ARE this stage's output (F-4).",
              requires=("validate",), blocking=False, durable=False),
        # Blocking, not a gate — see `INTENT_REVIEW` for the argument. `intake`
        # keeps exactly one gate, and it stays `model-approval`.
        Stage("readiness", 4, "intent_readiness",
              "Whether this can be represented in the graph at all. A claim "
              "nobody has costed is `ready` and lands with that recorded; a "
              "need nobody has specified is not (D-1).",
              requires=("analysis",),
              checks=("intent_is_reviewed",)),
        Stage("land", 5, "intake_land",
              "Episode + <Source>Item anchor per document, and a Requirement "
              "only where the text is EARS-conformant. Free prose lands as a "
              "Finding pointing at knowledge-capture (S-13).",
              requires=("readiness",),
              checks=("landed_at_quarantine",)),
        # Requirements management goes through risk management: what was landed
        # is assessed BEFORE the gate, so the person deciding sees the risk
        # rather than being told afterwards. Reporting — a risky requirement is
        # a decision to take, not a failed run.
        Stage("requirement-risk", 6, "requirement_risk",
              "The risk in what was just landed, before anybody approves it.",
              requires=("land",), blocking=False, durable=False),
        Stage("model-approval", 7, "g1",
              "G1 — a human decides which claims to accept.",
              requires=("requirement-risk",),
              is_gate=True,
              checks=("model_is_approved",)),
    ),
)

COVERAGE_REPORT = Workflow(
    code="coverage-report",
    summary="Report coverage for a scope. Read-only; no gates.",
    entry_patterns=("coverage for <scope>", "how covered is <scope>"),
    stages=(
        Stage("report", 1, "report", "The coverage ledger (§6.8b).", blocking=False),
        # Risk-based coverage (ISO/IEC/IEEE 29119-2). Reporting, because a
        # concentration of uncovered behaviour in the high band is something to
        # act on rather than a failed run.
        Stage("risk-weighted", 2, "risk_weighted",
              "Whether the uncovered part is the part that matters.",
              requires=("report",), blocking=False),
    ),
)

SPEC_WRITEBACK = Workflow(
    code="spec-writeback",
    summary="Regenerate the stakeholder specification and write it back (§18).",
    entry_patterns=("write back the spec for <scope>", "update the spec for <scope>"),
    preconditions=("model_is_approved",),
    stages=(
        Stage("spec", 1, "spec", "Build the specification document (§18).",
              durable=False),
        Stage("write-back", 2, "writeback",
              "Write into the product's own .specify/specs/ — gated (T-18).",
              requires=("spec",),
              is_gate=True),
    ),
)

CHANGE_APPROVAL = Workflow(
    code="change-approval",
    summary=("Re-recover after a change, show which approvals it cost, and "
             "settle only what moved with a human."),
    entry_patterns=("approve the changes in <repo>", "what did <commit> change",
                    "review the change to <scope>"),
    stages=(
        Stage("extract", 1, "extract",
              "Re-recover states and transitions from the changed code (§5).",
              checks=("model_is_wellformed",)),
        # Before landing, because `land` is what carries the human facts across
        # and a reviewer wants the diff's blast radius while deciding whether to
        # land at all.
        Stage("change-impact", 2, "change_impact",
              "Which recovered behaviour the diff touches, and what validates "
              "it (`impact` + `change_review`).",
              requires=("extract",),
              blocking=False),
        Stage("land", 3, "land",
              "Land at Quarantine, carrying human decisions forward and revoking "
              "only where behaviour changed (I-17/I-18, S-4).",
              requires=("extract",),
              checks=("landed_at_quarantine",)),
        # I-18: determinism and guard completeness are properties of a
        # (state, trigger) GROUP, so adding one transition can break its
        # siblings while they stay approved. Revalidation after the carry is
        # what catches that, and it must block.
        Stage("validate", 4, "validate",
              "Re-check well-formedness — I-18 revalidates the whole "
              "(state, trigger) group, not just what changed.",
              requires=("land",),
              checks=("model_is_wellformed",)),
        Stage("change-review", 5, "change_review",
              "The approvals this change revoked and the renames it proposed — "
              "named, never counted (F-4).",
              requires=("land",),
              blocking=False),
        Stage("model-approval", 6, "g1",
              "G1 — a human re-approves what changed, with the revocations and "
              "their reasons in front of them.",
              requires=("validate",),
              is_gate=True,
              checks=("model_is_approved",)),
    ),
)

RISK_REVIEW = Workflow(
    code="risk-review",
    summary="Assess the risk a requirement or a release carries, gathering what "
            "Métis knows and asking for what it cannot.",
    entry_patterns=("assess the risk of <scope>", "risk review for <scope>",
                    "what is risky about <scope>"),
    # **Deliberately no preconditions.** A risk review of an UNAPPROVED model is
    # exactly when it is most useful — "what would we be accepting if we shipped
    # this" is a pre-approval question — so requiring G1 here would withhold the
    # assessment at the only moment it changes a decision.
    preconditions=(),
    stages=(
        Stage("gather", 1, "risk_gather",
              "Read every input Métis can supply, and record which tool "
              "supplied each.",
              durable=False),
        Stage("open-questions", 2, "risk_questions",
              "State what no tool can answer, in the words to ask. Never "
              "blocking: the questions ARE the output of this stage (F-4).",
              requires=("gather",), blocking=False, durable=False),
        Stage("assess", 3, "risk_assess",
              "Derive candidates from the gathered half only. Nothing is "
              "invented for an input nobody supplied.",
              requires=("gather",), durable=False),
        Stage("risk-acceptance", 4, "risk_gate",
              "A person accepts the assessment and owns the ratings. Without "
              "this the run would present the half Métis can see as the whole.",
              requires=("assess",),
              checks=("risk_is_accepted",),
              is_gate=True),
        Stage("document", 5, "risk_document",
              "Write the Markdown, preserving every edit already in it.",
              requires=("risk-acceptance",)),
    ),
)

TEST_DESIGN = Workflow(
    code="test-design",
    summary=("Design what to test and how, declaring what Métis gathered and "
             "what a person must still answer."),
    entry_patterns=("design tests for <scope>", "test design for <scope>",
                    "how should we test <scope>"),
    # **Deliberately no preconditions, and it is the same argument `risk-review`
    # makes.** Designing against an unapproved model is exactly when it is most
    # useful -- "what would testing this involve" is a pre-approval question --
    # and the design carries the approval state in its own basis section rather
    # than refusing to run. Generation is where D-10 bites; design is not
    # generation.
    preconditions=(),
    stages=(
        Stage("gather", 1, "design_gather",
              "Read every input Métis can supply, and record which tool "
              "supplied each.",
              durable=False),
        Stage("sections", 2, "design_sections_build",
              "Build each section, marking the ones that could not be stated "
              "and the ones built without all of their inputs.",
              requires=("gather",), durable=False),
        Stage("open-questions", 3, "design_questions",
              "State what no tool can answer, in the words to ask. Never "
              "blocking: the questions ARE the output of this stage (F-4).",
              requires=("gather",), blocking=False, durable=False),
        Stage("design-acceptance", 4, "design_gate",
              "A person accepts the design and owns its decisions. Without "
              "this the run would present what Métis could derive as the whole "
              "design.",
              requires=("sections",),
              checks=("design_is_accepted",),
              is_gate=True),
        Stage("document", 5, "design_document",
              "Write the Markdown, preserving every edit already in it.",
              requires=("design-acceptance",)),
    ),
)

# **The authored path's equivalent of `intake`.** A person writing an intent file
# has the same four questions to answer as a tracker item does, and had no
# workflow at all: `metis intent check` answered one of them and stopped.
INTENT_REVIEW = Workflow(
    code="intent-review",
    summary=("Read a stated intent from four directions — is there a need, can "
             "its wording be satisfied twice, could anything test it, does "
             "anybody know what being wrong costs — before it reaches the graph."),
    entry_patterns=("review the intent for <scope>", "analyse the intent for <scope>",
                    "is this requirement ready for <scope>"),
    preconditions=(),
    stages=(
        Stage("analysis", 1, "intent_analysis",
              "The four readings, consolidated. Reporting: the gaps ARE the "
              "output of this stage (F-4).",
              blocking=False, durable=False),
        # **Blocking, and NOT a gate.** A gate is where a person decides, and
        # this has no literal that passes it: a need nobody has specified is
        # fixed by specifying it, not by anybody agreeing to import it anyway.
        # So it is F-9's contract instead -- a stage that fails, names what
        # failed, and states the action required. §3.4 keeps one halt per
        # workflow precisely so each halt has one meaning.
        Stage("readiness", 2, "intent_readiness",
              "Whether this can be represented in the graph at all. Fails when "
              "it cannot — landing a need nobody has specified would create a "
              "node nothing can ever be checked against (D-1).",
              requires=("analysis",),
              checks=("intent_is_reviewed",)),
        Stage("document", 3, "intent_document",
              "Write the Markdown, preserving every edit already in it.",
              requires=("readiness",)),
    ),
)

WORKFLOWS: dict[str, Workflow] = {
    w.code: w for w in (MODEL_BUILD, CHANGE_APPROVAL, KNOWLEDGE_CAPTURE, INTAKE,
                        TEST_GENERATE, TEST_DESIGN, COVERAGE_REPORT,
                        SPEC_WRITEBACK, RISK_REVIEW, INTENT_REVIEW)
}


def get(code: str) -> Workflow | None:
    return WORKFLOWS.get(code)


def format_workflows() -> str:
    lines = ["Workflows", ""]
    for code, w in sorted(WORKFLOWS.items()):
        gates = sum(1 for s in w.stages if s.is_gate)
        lines.append(f"  {code:<18} {len(w.stages)} stage(s), {gates} gate(s)")
        lines.append(f"      {w.summary}")
        if w.preconditions:
            lines.append(f"      requires first: {', '.join(w.preconditions)}")
        for s in w.ordered:
            mark = "GATE" if s.is_gate else ("    " if s.blocking else "rep ")
            lines.append(f"        {mark} {s.ordinal}. {s.name}")
        lines.append("")
    lines += ["  A gate halts the run and waits. Nothing auto-advances past one,",
              "  and nothing auto-promotes on elapsed time (F-8)."]
    return "\n".join(lines)
