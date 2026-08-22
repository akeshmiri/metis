"""
The stage registry and the workflow definitions (application spec §3.2, §3.4).

**This is the single place that knows the order.** Before it, the ordering lived
in `reingest_athena.sh`, in two throwaway scripts under `/tmp`, in four
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
# Five. Atlas has eleven, and the other six have no Métis counterpart: R8 says
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
        Stage("render", 2, "render",
              "One path, one test case (§7.1).",
              requires=("generate-paths",), durable=False),
        Stage("publication-confirmation", 3, "g2",
              "G2 — a literal affirmative confirmation, in this run (T-18).",
              requires=("render",),
              is_gate=True),
        Stage("publish", 4, "publish",
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
        Stage("model-approval", 5, "g1",
              "G1 — a human approves, with the criteria in front of them.",
              requires=("land",),
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

WORKFLOWS: dict[str, Workflow] = {
    w.code: w for w in (MODEL_BUILD, KNOWLEDGE_CAPTURE, TEST_GENERATE,
                        COVERAGE_REPORT, SPEC_WRITEBACK)
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
