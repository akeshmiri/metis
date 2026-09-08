"""What the sibling practice does, and what Métis does about each of it.

**Why this is data rather than a document.** Métis was ported from a sibling
project — Atlas — and the port was partial by design: some of what Atlas does is
infrastructure Métis has no business owning, some is a practice Métis
deliberately refuses, and some is a real gap. Until now none of that was written
down anywhere, so "have we compared them?" was answerable only by doing the
comparison again, and every answer was somebody's recollection.

`docs/academy/10-where-a-thing-belongs.md` has the general form of this failure
twice over: a hand-maintained index rots and a generated one does not. So the
comparison is a registry with a test on both ends — every `covered` entry must
name a Métis surface that exists, and every entry must carry a reason.

**Three verdicts, and `open` is the only one that is a to-do.**

- `covered` — Métis does this, and the entry names where.
- `refused` — Métis deliberately does not, and the entry says why. A refusal is
  a decision that has been made, not a gap that has been ignored.
- `open` — a real gap, with the **condition that would close it**. Recording the
  condition is what stops an open item becoming a permanent complaint.

**What a `covered` verdict does not claim.** That the two implementations are
equivalent, or that Métis's is better. Atlas's `test-designer` and Métis's
`metis-test-design` answer the same question and disagree about several answers;
`covered` means the question has an owner here, and the entries name the
disagreements that matter.

**The names are Atlas's own skill-directory names**, quoted so a reader can find
the thing being compared. They are identifiers in a sibling repository, not
claims about anybody's product.
"""
from __future__ import annotations

from dataclasses import dataclass

COVERED, REFUSED, OPEN = "covered", "refused", "open"
VERDICTS = (COVERED, REFUSED, OPEN)


@dataclass(frozen=True)
class Entry:
    """One capability of the sibling practice, and Métis's answer to it."""

    #: The Atlas skill directory, or a capability name where it is not a whole
    #: skill (`use-case-diagrams`).
    name: str
    verdict: str
    #: For `covered`: the Métis skill, tool or CLI verb that answers it. Empty
    #: for `refused` and `open`.
    answered_by: tuple[str, ...]
    #: Why. Mandatory on every entry — a verdict with no reason is a vote.
    because: str
    #: For `open` only: what would have to be true to close it.
    condition: str = ""


ENTRIES: tuple[Entry, ...] = (
    # ---------------------------------------------------------------- covered
    Entry("test-designer", COVERED, ("metis-test-design",),
          "the same question — what testing a scope involves — with a served "
          "template rather than a prose one, and sections Atlas has no "
          "equivalent for (`dimensions`, `uncertainty`, `compliance`). Three "
          "capabilities of Atlas's are still open below."),
    Entry("business-analyzer", COVERED, ("metis-business-analyst",),
          "reads a stated intent from four directions before it lands, and "
          "refuses the import only when the claim cannot be represented (D-1)"),
    Entry("jira-analyzer", COVERED, ("metis-intake-processor",),
          "a tracker issue becomes a UIF document with every field traced to "
          "the response it came from; nothing is inferred"),
    Entry("intake-processor", COVERED, ("metis-intake-processor",),
          "the same name and the same job. Métis validates against the "
          "published UIF schema between fetch and land, which is the step whose "
          "absence let its own producer emit documents the schema rejected"),
    Entry("downstream-analyzer", COVERED,
          ("metis-business-analyst", "analysis/"),
          "four readings that each see a hole the other three cannot, each gap "
          "naming the aspect that found it and what closes it"),
    Entry("code-explorer", COVERED, ("metis-model-build",),
          "a behaviour model recovered from a code property graph, which is a "
          "stronger claim than a schema registry scanned from source"),
    Entry("git-repository-analyzer", COVERED, ("metis-model-build",),
          "the same recovery, ending at the G1 approval gate rather than at a "
          "report"),
    Entry("git-repository-cloner", COVERED, ("fetch_repository",),
          "a single determinate call, so it is a tool and not a skill — the "
          "placement rule's first question"),
    Entry("report-generator", COVERED, ("metis-coverage-report",),
          "reports what is covered, what is not, and what could not be measured "
          "at all, which is the part that makes the rest safe to read"),
    Entry("sql-optimizer", COVERED, ("sql_review", "sql_confirm",
                                     "metis-model-build-code"),
          "review and confirm are two tools behind one specialist. The confirm "
          "half was granted to no skill until this pass, so the flow could be "
          "started and not finished"),
    Entry("test-case-reporter", COVERED,
          ("metis-test-generate", "publishing.TRANSPORTS"),
          "publication to Zephyr Scale behind two keys: the G2 literal in the "
          "run, and `METIS_ALLOW_EXTERNAL_WRITES=yes` on the installation"),
    Entry("merge-request-creator", COVERED, ("open_merge_request",),
          "one gated call. A skill around it would add a procedure where there "
          "is only a decision, which the placement rule puts in a tool"),
    Entry("atlas-academy", COVERED, ("docs/academy/", "metis lessons",
                                     "Lesson"),
          "nineteen authored lessons that land in the same graph as the product "
          "facts, so `ask` answers a question about Métis the way it answers "
          "one about a product"),

    # ---------------------------------------------------------------- refused
    Entry("test-developer", REFUSED, (),
          "Métis renders human-executable cases and a `.feature` file as "
          "specification; it does not author framework code, step definitions "
          "or payload samples (X-6e). A generated concrete value where the "
          "model states a space is the failure mode the whole rendering layer "
          "is built to avoid"),
    Entry("code-reviewer", REFUSED, (),
          "reviewing code for style and blockers is a different discipline from "
          "recovering what code does. Métis reports a contract deviation as a "
          "case and a question, never as a defect in someone's code"),
    Entry("use-case-diagrams", REFUSED, (),
          "Atlas mandates a use-case diagram and a flow chart on every design. "
          "Métis draws one picture — the `machine` section — and draws only "
          "what it recovered: **no actors**, because an actor is an `asked` "
          "input and inferring one from a route name is X-6"),
    Entry("atlas-config-manager", REFUSED, (),
          "installation and configuration management. `metis doctor` diagnoses "
          "the two real prerequisites and prints the repair; a config "
          "resolution layer is not Métis's to own"),
    Entry("atlas-lifecycle", REFUSED, (),
          "installing a runtime, configuring hosts and repairing drift is "
          "infrastructure. Métis is a library, a CLI and an MCP server"),
    Entry("dependency-installer", REFUSED, (),
          "downloading Java and Python is not Métis's job. `metis doctor` "
          "reports what is missing and how to fix it, which is the half that "
          "belongs here"),
    Entry("quick-start-guide", REFUSED, (),
          "`docs/guide/` is generated from the code and `metis guide --check` "
          "fails on a diff — a hand-written getting-started page is exactly the "
          "artefact that rots"),
    Entry("workflow-manager", REFUSED, (),
          "Atlas maintains HTML workflow pages. Métis's workflows are declared "
          "in `workflow/stages.py` and the router is generated from them"),
    Entry("caveman-compress", REFUSED, (),
          "compressing memory files to save tokens is a harness concern, and a "
          "lossy rewrite of a decision record is the opposite of what this "
          "project keeps its reasoning for"),
    Entry("caveman-stats", REFUSED, (),
          "session token accounting is a harness concern, and one Claude Code "
          "already reports. A second, estimating counter would be a figure "
          "nobody could reconcile against the first"),
    Entry("athena-analyzer", REFUSED, (),
          "a bridge to one organisation's analytics data product. Métis carries "
          "no company or customer name in a test, a fixture or a claim, and a "
          "skill named for one would be that"),

    # ------------------------------------------------------------------- open
    Entry("bug-reporter", COVERED,
          ("classify_failure", "file_defect", "metis-release-readiness"),
          "`classify_failure` is the read half `defects/classify.py` never had: "
          "it was reachable only through `file_defect`, a write-tier tool "
          "needing two keys, so the question could not be asked without filing. "
          "**No new skill was created**, which was this entry's own close "
          "condition: the classification is one determinate call, so the "
          "placement rule makes it a tool, and `metis-release-readiness` is "
          "where a failing behaviour is already being reasoned about"),
    Entry("locust-workflow", COVERED,
          ("metis-system-contact", "runners/"),
          "load runs at `METIS_EXECUTE=run`, behind the `metis[load]` extra and "
          "the literal `execute`. The skill states the tier before it acts and "
          "reports a run as an observation, never as a verdict — a passing run "
          "is one input to `release_verdict`, not a `Go`"),
    Entry("k8s-observer", COVERED,
          ("metis-system-contact", "observers/"),
          "cluster and SQL evidence at `METIS_EXECUTE=observe`. **One skill "
          "covers both this and the load runner** because the discipline is "
          "identical — state the tier, refuse at `off`, label the fact "
          "`observed_from_running_system` and never merge it with one recovered "
          "from source. Two skills would have been two near-identical documents, "
          "which `test_no_two_agents_are_the_same_document` exists to catch"),
    Entry("intake-extractor-developer", OPEN, (),
          "`connectors/intakes.json` declares every intake and "
          "`intakes.describe()` says which do not work. Authoring a new "
          "extractor is undocumented as a procedure",
          condition="a second person needing to add an intake — one author is a "
                    "task, two is a procedure"),
    Entry("release-verdict", COVERED,
          ("release_verdict", "metis-release-readiness"),
          "`risk/verdict.py` refuses `Go` on coverage alone and had no importer "
          "anywhere. The specialist meanwhile **restated the whole ladder in "
          "prose** — two tables and a bullet list — so a rule its own text "
          "called \"checked rather than remembered\" was enforced by a model "
          "copying a table correctly. The tool serves it; the restatement is "
          "gone"),
    Entry("source-fidelity", COVERED, ("metis coverage-gap",),
          "`rendering/fidelity.py` had the three verdicts — continue_as_is, "
          "improvement_needed, split_requested — and no importer anywhere. "
          "`metis coverage-gap` printed a distribution of grades without saying "
          "what to DO about the middle one, and \"a test reaches this endpoint "
          "but the outcome is unevidenced\" wants a different action from "
          "\"nothing exists\". A split now blocks with exit code 2 rather than "
          "as a line somebody has to notice"),
    Entry("design-overview-split", OPEN, (),
          "Atlas writes a coarse overview and a detailed design and machine-"
          "verifies that they agree. Métis renders one document, and the ported "
          "`check_design_sync.py` therefore compares artefacts nothing produces "
          "— it can only return `Missing high-level overview artifact`",
          condition="a design large enough that a reviewer cannot hold it. "
                    "Atlas's detailed template is 817 lines; Métis's document "
                    "is not there yet, and an overview nobody needs is a second "
                    "artefact to keep in step"),
    Entry("mirror-coverage", COVERED, ("metis-test-design", "mirror"),
          "the `mirror` section proposes specific missing-criterion candidates "
          "— partition complements, boundaries, factor pairs, rejection "
          "siblings, unauthorised variants — each carrying `derived_from: "
          "model`, `pending` until a person decides, and never counted with the "
          "authored criteria. Two categories, `dependency-failure` and "
          "`exclusion`, are reported as unreachable rather than left absent"),
    Entry("per-level-obligations", COVERED,
          ("metis-test-design-levels", "design/level_requirements.py"),
          "the `levels` section carries a `Level asks for` column built from "
          "obligations keyed on `mbt/test_levels.LEVELS` — imported, never a "
          "second copy. Each obligation names the module that checks it, or is "
          "marked as a person's; most are a person's, and the marker is what "
          "stops the column reading as a list of things Métis verified"),
)


def entries_with(verdict: str) -> tuple[Entry, ...]:
    return tuple(e for e in ENTRIES if e.verdict == verdict)


def entry_for(name: str) -> Entry | None:
    return next((e for e in ENTRIES if e.name == name), None)


def describe() -> dict:
    """The comparison, for a tool and for a test."""
    return {
        "entries": [
            {"name": e.name, "verdict": e.verdict,
             "answered_by": list(e.answered_by), "because": e.because,
             "condition": e.condition}
            for e in ENTRIES],
        "counts": {v: len(entries_with(v)) for v in VERDICTS},
        "means": (
            "what the sibling practice does and what Métis does about each. "
            "`covered` names a Métis surface, `refused` is a decision with its "
            "reason, and `open` is a gap carrying the condition that would "
            "close it"),
        "does_not_claim": (
            "that a covered capability is implemented equivalently, or better. "
            "It claims the question has an owner here"),
    }
