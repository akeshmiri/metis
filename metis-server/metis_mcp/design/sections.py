"""The test design's shape: its groups, its sections, and every column in each.

**The template is data here, and it is rendered by Python.** That is the whole
point of the module. A design "template" written as prose in a `SKILL.md` is a
shape a model imitates, and two runs imitate it differently -- different column
order, a heading dropped, a vocabulary widened by one plausible word. Declaring
it here makes the shape a fact the renderer applies and a test asserts, and it
leaves the skills to carry only what is genuinely not determinate.

**Vocabularies are closed and they are borrowed, never restated.** Every
`allowed` tuple below is imported from the module that already owns it --
`viability`'s three viability verdicts and three performance verdicts,
`test_levels`'s six levels and three grades, `design`'s technique names,
`exposure`'s four bands. A second copy of one of those lists is how a design
starts reporting a level the coverage ledger has never heard of.

**Every section renders, including the empty ones.** An absent section is
something a reader has to interpret, and the two things it could mean --
*nothing here* and *nobody looked* -- are exactly the pair this codebase keeps
having to separate. So a section whose inputs were not supplied renders with
`absent_means` where its rows would be, naming the input it is waiting for.

**Nothing here computes anything.** `builder` names a function in
`design/builders.py`; this module knows its name and its columns and not what it
does. Keeping the registry free of the computation is what lets
`test_design_sections.py` assert the registry's own coherence -- every builder
resolves, every column key is unique, every section claims a specialist that
exists on disk -- without needing a model.
"""
from __future__ import annotations

from dataclasses import dataclass

from metis_mcp.mbt.dimensions import (
    AUTHENTICATION,
    AUTHORIZATION,
    BUSINESS,
    VALIDATION,
)
from metis_mcp.mbt.design import (
    BOUNDARY_VALUE,
    DECISION_TABLE,
    EQUIVALENCE_PARTITION,
    PAIRWISE,
)
from metis_mcp.mbt.test_levels import COVERED, LEVELS, OUTCOME_UNPROVEN, UNCOVERED
from metis_mcp.risk.exposure import BANDS
from metis_mcp.viability import (
    AUTOMATE,
    DEFER,
    FULL,
    FUNCTIONAL_ONLY,
    MANUAL_ONLY,
    NO_BASIS,
    PARTIAL,
    PERFORMANCE_CANDIDATE,
    POSITIVE_ONLY,
)

#: How a section is rendered. **A diagram is not a table and must not pretend to
#: be one**: the merge reads cells by position, so a section with no columns has
#: nothing to preserve and nothing to lose. Declaring the mode is what lets the
#: renderer, the merge and `verify` each do the right thing without any of them
#: guessing from an empty column list.
TABLE, DIAGRAM = "table", "diagram"

#: Above this many transitions a state diagram stops being readable and starts
#: being a wall. The cap is REPORTED when it trips rather than silently
#: truncating (P-3b) — a diagram showing forty of fifty-six transitions with no
#: note is worse than no diagram, because it looks complete.
MAX_DIAGRAM_TRANSITIONS = 40

#: Who fills a cell. The distinction the merge is built on: `COMPUTED` is
#: rewritten every run, `HUMAN` is preserved and never written by Métis.
COMPUTED, HUMAN = "computed", "human"

#: State-transition testing is a technique in ISO/IEC/IEEE 29119-4 and is not a
#: constant in `mbt/design.py`, because there it is the *criterion* machinery
#: (`all-transitions`, `all-transition-pairs`) rather than a named technique.
#: Declared here, beside the four that are imported, with that difference noted.
STATE_TRANSITION = "state-transition"

TECHNIQUES = (EQUIVALENCE_PARTITION, BOUNDARY_VALUE, DECISION_TABLE, PAIRWISE,
              STATE_TRANSITION)

#: The eight condition classes from
#: `plugins/metis/skills/shared/knowledge/requirement-condition-coverage.md`.
#: **Declared here rather than imported**, because the source of truth is that
#: prose rule and there is no module that owns it — which is precisely why the
#: rule was applied by a model and checked by nothing until this section
#: existed. `test_design_sections.py` asserts the tuple matches the file, so the
#: two cannot drift.
CONDITION_CLASSES = ("allowed", "prohibited", "partition", "boundary",
                     "state-transition", "authorization", "dependency-failure",
                     "non-goal")

#: What a person may decide about a condition class. `clarify` is the one that
#: matters: it is neither "we will test it" nor "it does not apply", and a class
#: sitting on it is an open question rather than a closed decision.
CONDITION_DECISIONS = ("test", "not-applicable", "clarify")

#: The negative behaviour an endpoint's own shape obliges it to have. Each is
#: derived from a recovered fact — a path parameter, a declared security
#: requirement, a body — never from a route that looks like it should have one.
OBLIGATIONS = ("not-found", "authorization-denied", "validation-error",
               "enum-variation")

#: Whether the model already carries the obligation. **`unmet` is not "the code
#: is broken".** It says no such outcome was recovered, and only a person can say
#: whether the behaviour is unhandled or extraction did not see it.
OBLIGATION_STATUS = ("satisfied", "unmet", "not-applicable")

#: Setup cost, from the setup chain rather than from a verb. Atlas's version of
#: this reads the business verb ("get", "create") and guesses; Métis computes the
#: chain a test must walk to reach the behaviour, which is the thing the guess
#: was standing in for.
COMPLEXITY = ("minimal", "moderate", "escalate")

#: Whether reaching the behaviour changes anything. `unknown` is a real value
#: and it is there because the alternative was a silent wrong answer: the effect
#: is read from an HTTP verb, and a UI action (`submit_valid_credentials`) has
#: none — so classifying it `read-only` would call a credential submission a
#: read, and put a cheap cost on it.
EFFECTS = ("read-only", "state-changing", "unknown")

#: The setup patterns, and every one of them is a HUMAN choice. Which is safe
#: depends on whether stable data exists in the environment and who owns
#: cleanup — neither of which Métis can see. It computes the cost; a person who
#: knows the environment picks the pattern.
SETUP_PATTERNS = ("reuse-existing", "query-or-create", "provision-isolated",
                  "reset-mutable-state", "per-test-provisioning")

#: The dimension classes, from the module that owns them. `""` is a real value
#: and belongs in the vocabulary: X-10c says an unclassified check keeps its
#: position in the chain, so a blank here is a recovered fact rather than a gap.
DIMENSION_CLASSES = (AUTHENTICATION, AUTHORIZATION, VALIDATION, BUSINESS, "")

#: The four bands, taken from the same tuple `risk_exposure` reports.
RISK_BANDS = tuple(name for _lo, _hi, name in BANDS)

#: What a person may decide about a designed row. Closed, because an open
#: decision column collects "ok", "yes", "fine" and "👍" and then cannot be
#: counted. `defer` is distinct from `drop`: one is a decision to come back.
DECISIONS = ("accept", "change", "drop", "defer")

#: What an open question's answer is worth. `accepted` is not `answered`:
#: somebody may accept an unanswered uncertainty, and that is a decision with an
#: owner rather than a gap that closed itself.
UNCERTAINTY_STATUS = ("open", "answered", "accepted")


@dataclass(frozen=True)
class Column:
    """One column of one section's table."""

    key: str
    heading: str
    filled_by: str
    #: A closed vocabulary, where one exists. Empty means free text.
    allowed: tuple[str, ...] = ()
    #: What the column is for. Rendered into the section's own legend, so a
    #: reader does not have to find this file to know what a column means.
    means: str = ""


@dataclass(frozen=True)
class Group:
    """A run of sections that answer one kind of question."""

    key: str
    heading: str
    ordinal: int
    purpose: str


@dataclass(frozen=True)
class Section:
    """One section of the design: a heading, a table, and who owns it."""

    key: str
    heading: str
    ordinal: int
    group: str
    #: The skill that owns this section's procedure. Checked in both directions
    #: against the skill tree, the way `risk/areas.py` is.
    specialist: str
    summary: str
    #: The function in `design/builders.py` that computes the rows.
    builder: str
    columns: tuple[Column, ...]
    #: What it means when this section could not be built. Never reassurance.
    absent_means: str
    #: What it means when the section built and found nothing. Distinct from the
    #: line above, and keeping them apart is the point.
    empty_means: str
    #: `TABLE` or `DIAGRAM`. A diagram section carries no columns, so nothing in
    #: it is a person's to edit and nothing is preserved across a regeneration.
    render: str = TABLE

    @property
    def human_columns(self) -> tuple[str, ...]:
        """The keys a person owns. Derived, so the merge cannot disagree."""
        return tuple(c.key for c in self.columns if c.filled_by == HUMAN)

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(c.heading for c in self.columns)

    @property
    def fields(self) -> tuple[str, ...]:
        """Field names in table order, excluding the id in the first column."""
        return tuple(c.key for c in self.columns[1:])


# The three columns every section ends with. One shared tuple, so a reader
# learns the convention once and the merge is the same operation everywhere.
def _decision_columns() -> tuple[Column, ...]:
    return (
        Column("decision", "Decision", HUMAN, DECISIONS,
               means="yours. Métis proposes rows; it does not accept them"),
        Column("owner", "Owner", HUMAN,
               means="one named person. 'The team' is not an owner"),
        Column("notes", "Notes", HUMAN,
               means="preserved across regeneration, like the two beside it"),
    )


_ID = Column("id", "ID", COMPUTED, means="the join key. Stable across runs (P-7)")
_RISK = Column("risk_band", "Risk", COMPUTED, RISK_BANDS,
               means="derived from the model (`derived_from: model`). It says "
                     "how much there is to get wrong, never how likely a "
                     "failure is — this table carries no probability")


GROUPS: tuple[Group, ...] = (
    Group("basis", "What this design rests on", 1,
          "the claims being demonstrated, and the state of the model they were "
          "recovered from. A design whose basis is unstated is a list of test "
          "ideas"),
    Group("conditions", "What must be varied", 2,
          "the techniques the behaviour warrants and the data conditions they "
          "require. Conditions on data, never values (M-9)"),
    Group("execution", "Where it runs, and whether it can", 3,
          "the level each condition is asserted at, what already covers it, and "
          "what cannot be automated at all"),
    Group("quality", "The attributes behind the behaviour", 4,
          "authorisation and load. Both refuse rather than guess: an unrecovered "
          "check is not an absent one, and an unsized endpoint is `no-basis`"),
    Group("interfaces", "Across a boundary", 5,
          "the contract each call declares and the journeys that cross surfaces. "
          "Both depend on an architecture nobody has stated to Métis"),
    Group("uncertainty", "What we do not know", 6,
          "every unanswered input, what its absence means, and which section it "
          "silenced. This group is the reason the design can be trusted: it is "
          "where the design says what it is not"),
)


SECTIONS: dict[str, Section] = {s.key: s for s in (
    Section(
        key="basis", heading="Basis", ordinal=1, group="basis",
        specialist="metis-test-design",
        summary="The requirement, its criteria, the specification and the model "
                "state this design is built on.",
        builder="build_basis",
        columns=(
            _ID,
            Column("claim", "Claim", COMPUTED,
                   means="the requirement or criterion, as written. Never "
                         "paraphrased — a reworded claim is a different claim"),
            Column("kind", "Kind", COMPUTED,
                   ("Requirement", "AcceptanceCriterion", "Specification"),
                   means="which node this came from"),
            Column("provenance", "Provenance", COMPUTED,
                   ("independently_authored", "human_confirmed", "code_derived"),
                   means="`code_derived` can only report that the code agrees "
                         "with itself (S-19)"),
            Column("lifecycle", "State", COMPUTED,
                   means="only `Approved` may be generated from (D-10)"),
            Column("quality", "Quality findings", COMPUTED,
                   means="unmeasurable qualifiers and non-atomicity. Advisory: "
                         "it blocks nothing (S-4)"),
            *_decision_columns(),
        ),
        absent_means="NO BASIS WAS GATHERED. Everything below describes what the "
                     "code does, with nothing stating what it should do",
        empty_means="no requirement or criterion is in scope for this journey — "
                    "the design has nothing to demonstrate, which is a finding "
                    "about the graph and not about the behaviour",
    ),
    Section(
        key="machine", heading="The behaviour being designed against", ordinal=2,
        group="basis", specialist="metis-test-design",
        summary="The state machine in scope, drawn from what was recovered. "
                "Every state and every transition, or a stated count of how "
                "many were left out.",
        builder="build_machine",
        columns=(),
        render=DIAGRAM,
        absent_means="NO MACHINE COULD BE DRAWN. There is no recovered "
                     "behaviour in scope, so every section below is about "
                     "nothing",
        empty_means="the model holds no transition — which is what both an "
                    "empty journey and a mistyped journey name produce, and "
                    "`validate` is what tells them apart",
    ),
    Section(
        key="conditions", heading="Condition completeness", ordinal=3,
        group="basis", specialist="metis-test-design",
        summary="Every behaviour against the eight condition classes, each with "
                "an explicit decision. This is the denominator the rest of the "
                "design is measured against.",
        builder="build_conditions",
        columns=(
            _ID,
            Column("subject", "Subject", COMPUTED,
                   means="the behaviour this class is being decided for"),
            Column("condition_class", "Class", COMPUTED, CONDITION_CLASSES,
                   means="every class gets a row, including the ones that do not "
                         "apply. A class that silently disappears is the failure "
                         "this section exists to prevent"),
            Column("found", "What Métis found", COMPUTED,
                   means="the recovered evidence, or the reason there is none"),
            Column("provenance", "Provenance", COMPUTED,
                   ("independently_authored", "human_confirmed", "code_derived", ""),
                   means="`code_derived` can only report that the code agrees "
                         "with itself (S-19); it is never intent"),
            Column("proposed", "Proposed", COMPUTED, CONDITION_DECISIONS,
                   means="Métis's reading, and only a proposal. `clarify` means "
                         "it could not reach the class at all"),
            Column("reason", "Reason", COMPUTED,
                   means="why the proposal is what it is. A `not-applicable` "
                         "with no reason is the row this section refuses to write"),
            _RISK,
            Column("decision", "Decision", HUMAN, CONDITION_DECISIONS,
                   means="yours, and it is the one that counts. A class left "
                         "undecided is an open question, not a closed one"),
            Column("owner", "Owner", HUMAN,
                   means="one named person. 'The team' is not an owner"),
            Column("notes", "Notes", HUMAN,
                   means="preserved across regeneration, like the two beside it"),
        ),
        absent_means="NO CONDITION INVENTORY. Without it a positive case counts "
                     "as coverage for the prohibited, boundary, partition, "
                     "state, authorisation and dependency-failure conditions it "
                     "never asserts — which is the single most common way a "
                     "test design overstates itself",
        empty_means="no behaviour is in scope, so there is nothing to decide "
                    "these classes for",
    ),
    Section(
        key="obligations", heading="Negative obligations", ordinal=4,
        group="conditions", specialist="metis-test-design",
        summary="The negative behaviour each endpoint's own shape obliges it to "
                "have, and whether the model carries it.",
        builder="build_obligations",
        columns=(
            _ID,
            Column("endpoint", "Endpoint", COMPUTED),
            Column("obligation", "Obligation", COMPUTED, OBLIGATIONS,
                   means="derived from a recovered fact — a path parameter, a "
                         "declared security requirement, a body — never from a "
                         "route that looks like it ought to have one"),
            Column("because", "Because", COMPUTED,
                   means="the fact that raised it, so a reader can disagree with "
                         "the input rather than only the obligation"),
            Column("recovered", "Outcomes recovered", COMPUTED,
                   means="every status this endpoint was seen to produce. The "
                         "obligation is judged against these and nothing else"),
            Column("satisfied_by", "Satisfied by", COMPUTED,
                   means="the transition that already carries it, named"),
            Column("status", "Status", COMPUTED, OBLIGATION_STATUS,
                   means="`unmet` says no such outcome was RECOVERED. Whether "
                         "the behaviour is unhandled or extraction did not see "
                         "it is a question, not a defect Métis declared"),
            _RISK,
            *_decision_columns(),
        ),
        absent_means="NO OBLIGATION WAS DERIVED. An endpoint taking a path "
                     "parameter and producing no not-found then reads exactly "
                     "like one that handles it",
        empty_means="no endpoint in scope carries a path parameter, a declared "
                    "security requirement, a body or an enumerated input — so "
                    "none of the four obligations applies to any of them",
    ),
    Section(
        key="technique", heading="Techniques and coverage items", ordinal=5,
        group="conditions", specialist="metis-test-design-technique",
        summary="Which technique each behaviour warrants, and the coverage items "
                "it yields. Chosen from the guard, never from a name.",
        builder="build_technique",
        columns=(
            _ID,
            Column("behaviour", "Behaviour", COMPUTED,
                   means="the transition, as `(state, trigger) -> outcome`"),
            Column("condition", "Condition", COMPUTED,
                   means="the guard atom this item varies. Métis states the "
                         "condition and never solves it (M-9)"),
            Column("technique", "Technique", COMPUTED, TECHNIQUES,
                   means="ISO/IEC/IEEE 29119-4's name for it"),
            Column("items", "Coverage items", COMPUTED,
                   means="how many distinct things this technique asks for here"),
            Column("unavailable", "Refused because", COMPUTED,
                   means="why a technique could not be applied. A guard with an "
                         "OR makes a decision table unavailable, and half a "
                         "table is worse than none (M-17)"),
            _RISK,
            *_decision_columns(),
        ),
        absent_means="NO TECHNIQUE COULD BE SELECTED — without guards there is "
                     "nothing to partition, and a technique picked without them "
                     "would be picked on a name (X-6)",
        empty_means="every guard in scope was unparseable or absent, so the "
                    "design falls back to state-transition coverage alone",
    ),
    Section(
        key="dimensions", heading="Guard dimensions and the reduction", ordinal=6,
        group="conditions", specialist="metis-test-design-technique",
        summary="The short-circuit chain each behaviour is guarded by, and what "
                "it costs to cover — bounded against the full product.",
        builder="build_dimensions",
        columns=(
            _ID,
            Column("behaviour", "Behaviour", COMPUTED),
            Column("condition", "Condition", COMPUTED,
                   means="the recovered check, verbatim. It is a condition on "
                         "the data, never a value (M-9)"),
            Column("dimension_class", "Class", COMPUTED, DIMENSION_CLASSES,
                   means="blank where the check matched no declared class. "
                         "X-10c: it keeps its position and participates in the "
                         "chain anyway — it simply cannot be marked cross-cutting"),
            Column("order", "Order", COMPUTED,
                   means="the EVALUATION order, from the framework chain and "
                         "control flow — never source line position (X-10d)"),
            Column("cases", "Cases", COMPUTED,
                   means="what this dimension contributes to the bounded count"),
            Column("reduction", "Chain", COMPUTED,
                   means="bounded against the full product. A request that fails "
                         "authentication never reaches authorisation, so varying "
                         "authorisation underneath it is unobservable (GD-3) — "
                         "which is what removes the product"),
            Column("anchor", "Anchor", COMPUTED,
                   means="`file:line@commit`. A condition a reviewer cannot "
                         "trace back to a line is one they must take on trust "
                         "(T-9a)"),
            Column("unavailable", "Refused because", COMPUTED,
                   means="GD-9: where precedence could not be recovered the "
                         "chain is neither assumed ordered nor assumed "
                         "independent. The explosion is reported, not generated"),
            _RISK,
            *_decision_columns(),
        ),
        absent_means="NO CHAIN COULD BE BUILT. Nothing bounds the combinatorial "
                     "cost, so a count over these conditions is the full product "
                     "rather than the reduced one — and most of that product is "
                     "unreachable",
        empty_means="no behaviour in scope carries a recovered guard check. That "
                     "is a statement about what extraction reached, not about "
                     "whether the code branches",
    ),
    Section(
        key="data", heading="Test data conditions", ordinal=7, group="conditions",
        specialist="metis-test-design-data",
        summary="The data each coverage item requires, stated as a condition on "
                "the accepted space. Never a value.",
        builder="build_data",
        columns=(
            _ID,
            Column("input", "Input", COMPUTED,
                   means="the parameter or field, by its recovered name"),
            Column("accepted_space", "Accepted space", COMPUTED,
                   means="`<string, length 3..40, required>` — the space, not a "
                         "value somebody could paste (X-6e)"),
            Column("condition", "Required condition", COMPUTED,
                   means="what must be true of the datum for this item. Still a "
                         "condition: turning it into data is a person's job"),
            Column("derivation", "Derived from", COMPUTED,
                   ("numeric_threshold", "boolean_predicate", "contract"),
                   means="how the condition was reached, so a reader can weigh it"),
            _RISK,
            *_decision_columns(),
        ),
        absent_means="DATA CONDITIONS COULD NOT BE STATED. The accepted space was "
                     "not recovered, and inventing one is exactly what M-9 forbids",
        empty_means="no input in scope carries a constraint, so every condition "
                    "here is 'any accepted value' — which is a real answer and a "
                    "thin one",
    ),
    Section(
        key="levels", heading="Levels, existing coverage and viability", ordinal=8,
        group="execution", specialist="metis-test-design-levels",
        summary="Where each condition is asserted, what already reaches it, and "
                "what cannot be automated at all.",
        builder="build_levels",
        columns=(
            _ID,
            Column("behaviour", "Behaviour", COMPUTED),
            Column("level", "Level", COMPUTED, LEVELS,
                   means="where the assertion sits in the pyramid, not what it "
                         "asserts"),
            Column("existing", "Already covered", COMPUTED,
                   (COVERED, OUTCOME_UNPROVEN, UNCOVERED),
                   means="the middle grade is the honest one: a test reaches the "
                         "endpoint and this outcome is not evidenced"),
            Column("viability", "Automatable", COMPUTED,
                   (AUTOMATE, MANUAL_ONLY, DEFER),
                   means="`automate` is never awarded on a name (X-6): it needs "
                         "recovered evidence pointing at a source line"),
            Column("depth", "Depth achievable", COMPUTED,
                   (FULL, PARTIAL, POSITIVE_ONLY),
                   means="what the model can support, which is a different "
                         "question from what the risk band warrants"),
            Column("warranted", "Depth warranted", COMPUTED,
                   means="what the band justifies. Where this exceeds the column "
                         "beside it, a person covers the difference another way"),
            _RISK,
            *_decision_columns(),
        ),
        absent_means="NO LEVEL CAN BE ASSIGNED, and nothing here is schedulable. "
                     "Assigning a level without knowing which environments exist "
                     "produces a plan nobody can run",
        empty_means="no behaviour in scope, so no level applies",
    ),
    Section(
        key="profile", heading="Defect-proneness factors", ordinal=9,
        group="execution", specialist="metis-test-design-levels",
        summary="What is behind the risk band, factor by factor — because the "
                "band says how much there is to get wrong and hides what.",
        builder="build_profile",
        columns=(
            _ID,
            Column("behaviour", "Behaviour", COMPUTED),
            Column("factor", "Factor", COMPUTED,
                   means="one of PRISMA's technical factors, or a note that it "
                         "was not measured"),
            Column("observed", "Observed", COMPUTED,
                   means="the raw count, which is what a reader disagrees with. "
                         "`not measured` is a row of its own — an unmeasured "
                         "factor contributes nothing to the band and is never "
                         "silently treated as its best value"),
            Column("rating", "Rating", COMPUTED,
                   means="1..5, from thresholds somebody chose. Ordinal: it "
                         "orders, it does not measure"),
            Column("response", "What it asks for", COMPUTED,
                   means="the design response the factor implies. High "
                         "branching wants more cases; high fan-in wants a "
                         "contract nobody may break — and 'test it more' is the "
                         "answer to neither"),
            _RISK,
            *_decision_columns(),
        ),
        absent_means="NO PROFILE WAS GATHERED, so only the band is available — "
                     "and 'test this more' becomes the only response, which is "
                     "rarely the right one",
        empty_means="no behaviour in scope could be profiled",
    ),
    Section(
        key="setup", heading="Setup cost and data complexity", ordinal=10,
        group="execution", specialist="metis-test-design-levels",
        summary="What it takes to reach each behaviour, computed from the setup "
                "chain — and the pattern choice that is a person's, not Métis's.",
        builder="build_setup",
        columns=(
            _ID,
            Column("behaviour", "Behaviour", COMPUTED),
            Column("effect", "Effect", COMPUTED, EFFECTS,
                   means="whether reaching this changes anything, from the "
                         "recovered verb"),
            Column("setup_depth", "Setup steps", COMPUTED,
                   means="how many transitions a test walks before the one it "
                         "asserts. Computed from the path, not guessed from a "
                         "verb"),
            Column("preconditions", "Preconditions", COMPUTED,
                   means="the setup chain itself. Paths sharing it share a "
                         "precondition (P-14a), which is what makes one setup "
                         "serve many cases"),
            Column("complexity", "Cost", COMPUTED, COMPLEXITY,
                   means="`escalate` is not a verdict that it is too hard — it "
                         "says split it, stage it, or make the cost visible"),
            Column("basis", "Basis", COMPUTED,
                   means="the two facts behind the cost, so a reader can "
                         "disagree with the input rather than only the answer"),
            _RISK,
            Column("pattern", "Setup pattern", HUMAN, SETUP_PATTERNS,
                   means="yours. Whether reuse is safe depends on stable data "
                         "and cleanup ownership, and Métis can see neither"),
            *_decision_columns(),
        ),
        absent_means="SETUP COST WAS NOT COMPUTED. What to automate first would "
                     "then be decided by what is easy to describe rather than by "
                     "what is cheap to reach",
        empty_means="no path could be generated for any behaviour in scope, so "
                    "there is no setup chain to cost",
    ),
    Section(
        key="security", heading="Authorisation and authentication", ordinal=11,
        group="quality", specialist="metis-test-design-security",
        summary="The identity and authority each call requires, from what was "
                "recovered — and what recovery cannot tell you.",
        builder="build_security",
        columns=(
            _ID,
            Column("call", "Call", COMPUTED),
            Column("authentication", "Authentication", COMPUTED,
                   means="what the recovered code requires. An absent value is "
                         "'nobody looked', not 'open'"),
            Column("authority", "Authority", COMPUTED,
                   means="the role or scope checked, by its recovered name"),
            Column("negative_case", "Negative condition", COMPUTED,
                   means="the complement: the identity that must be refused. A "
                         "check with no refusal case is asserted by nothing"),
            Column("obligation", "External obligation", HUMAN,
                   means="regulation, contract or audit commitment. Asked, "
                         "because static analysis cannot produce one"),
            _RISK,
            *_decision_columns(),
        ),
        absent_means="AUTHORISATION IS UNEXAMINED. An empty security section is "
                     "the most dangerous empty section in this document: it looks "
                     "identical whether nothing is exposed or nothing was read",
        empty_means="no authentication or authorisation was recovered on any call "
                    "in scope. Treat that as a finding to confirm, never as "
                    "evidence the surface is open by design",
    ),
    Section(
        key="performance", heading="Load and performance candidacy", ordinal=12,
        group="quality", specialist="metis-test-design-performance",
        summary="Which calls are worth driving under load, and the refusal where "
                "nobody has sized them.",
        builder="build_performance",
        columns=(
            _ID,
            Column("call", "Call", COMPUTED),
            Column("candidacy", "Candidacy", COMPUTED,
                   (PERFORMANCE_CANDIDATE, FUNCTIONAL_ONLY, NO_BASIS),
                   means="`no-basis` is not `functional-only`. The second reads "
                         "as 'measured, and none qualify'"),
            Column("basis", "Basis", COMPUTED,
                   means="the recovered fact behind the verdict — paging "
                         "parameters, a bulk type. Never an invented SLA"),
            Column("target", "Target", HUMAN,
                   means="the number a failure is judged against. Métis sets "
                         "none: inventing a threshold is the one thing this "
                         "classification must never do"),
            _RISK,
            *_decision_columns(),
        ),
        absent_means="NO PERFORMANCE DESIGN. Nobody has stated what load this "
                     "must carry, so there is no threshold and nothing to fail "
                     "against",
        empty_means="no call in scope carries a volume fact — `no-basis` across "
                    "the board, which says the model was not sized rather than "
                    "that the calls are cheap",
    ),
    Section(
        key="contract", heading="Contract and interface", ordinal=13,
        group="interfaces", specialist="metis-test-design-contract",
        summary="What each endpoint declares, and where the declaration and the "
                "code disagree.",
        builder="build_contract",
        columns=(
            _ID,
            Column("call", "Call", COMPUTED),
            Column("declared", "Declared", COMPUTED,
                   means="what the contract document says"),
            Column("recovered", "Recovered", COMPUTED,
                   means="what the code does. Where the two differ, the design "
                         "tests both and says which one somebody has to fix"),
            Column("deviation", "Deviation", COMPUTED,
                   means="the difference, as a condition. A deviation is a test "
                         "case and a question, never a defect Métis declared"),
            _RISK,
            *_decision_columns(),
        ),
        absent_means="NO CONTRACT WAS READ, and the boundaries were never stated. "
                     "Nothing here describes what crosses a process edge",
        empty_means="the document and the code agree everywhere they were "
                    "compared — which covers only what was compared",
    ),
    Section(
        key="journey", heading="Cross-surface journeys", ordinal=14,
        group="interfaces", specialist="metis-test-design-journey",
        summary="Which UI action invokes which call, and the guards a UI action "
                "inherits from the API beneath it (M-5c).",
        builder="build_journey",
        columns=(
            _ID,
            Column("action", "UI action", COMPUTED),
            Column("invokes", "Invokes", COMPUTED,
                   means="the API transition it reaches, where the link was "
                         "recovered rather than assumed"),
            Column("inherited_guard", "Inherited guard", COMPUTED,
                   means="M-5c: the UI action's condition may be the API call's"),
            Column("selector", "Selector", COMPUTED,
                   means="authored or absent. An element with no authored "
                         "selector raises rather than being guessed (X-6e)"),
            _RISK,
            *_decision_columns(),
        ),
        absent_means="THE SURFACES WERE NOT JOINED. A journey section built "
                     "without the link describes two disconnected models as "
                     "though they were one system",
        empty_means="no UI action in scope resolves to an API call — either "
                    "there is no UI half, or the links were never recovered, and "
                    "the drift report says which",
    ),
    Section(
        key="uncertainty", heading="Open questions and assumptions", ordinal=15,
        group="uncertainty", specialist="metis-test-design",
        summary="Every input nobody supplied, what its absence means, and which "
                "section it silenced.",
        builder="build_uncertainty",
        columns=(
            _ID,
            Column("question", "Question", COMPUTED,
                   means="the exact words to ask. A topic gets a shrug"),
            Column("decides", "Decides", COMPUTED,
                   means="what this answer settles"),
            Column("absent_means", "If unanswered", COMPUTED,
                   means="printed where the value should have been. Asserted "
                         "never to read as reassurance"),
            Column("silences", "Sections affected", COMPUTED,
                   means="which sections above could not be stated without it"),
            Column("answer", "Answer", HUMAN,
                   means="yours, and preserved. An answer given once is not "
                         "asked for again"),
            Column("owner", "Owner", HUMAN,
                   means="who owes the answer"),
            Column("status", "Status", HUMAN, UNCERTAINTY_STATUS,
                   means="`accepted` is a decision with an owner, not a gap that "
                         "closed itself"),
        ),
        absent_means="THE LEDGER ITSELF COULD NOT BE BUILT, which means this "
                     "document cannot say what it does not know. Do not act on "
                     "the sections above",
        empty_means="every declared input was supplied. This is the only empty "
                    "section in the document that is good news",
    ),
)}


#: Sections in the order they render. Ordinals are local and monotonic, the same
#: rule `workflow/stages.py` states for its own.
def ordered() -> tuple[Section, ...]:
    return tuple(sorted(SECTIONS.values(), key=lambda s: s.ordinal))


def sections_in(group: str) -> tuple[Section, ...]:
    return tuple(s for s in ordered() if s.group == group)


def group_for(key: str) -> Group | None:
    return next((g for g in GROUPS if g.key == key), None)


def describe() -> dict:
    """The registry, for a tool and for a test.

    This is what `design_sections()` returns, and it is why no `SKILL.md` needs
    to list a column: the shape is served, not restated.
    """
    return {
        "groups": [{"key": g.key, "heading": g.heading, "ordinal": g.ordinal,
                    "purpose": g.purpose,
                    "sections": [s.key for s in sections_in(g.key)]}
                   for g in sorted(GROUPS, key=lambda g: g.ordinal)],
        "sections": [{
            "key": s.key, "heading": s.heading, "ordinal": s.ordinal,
            "group": s.group, "specialist": s.specialist, "summary": s.summary,
            "builder": s.builder, "render": s.render,
            "absent_means": s.absent_means, "empty_means": s.empty_means,
            "human_columns": list(s.human_columns),
            "columns": [{"key": c.key, "heading": c.heading,
                         "filled_by": c.filled_by,
                         "allowed": list(c.allowed), "means": c.means}
                        for c in s.columns],
        } for s in ordered()],
        "means": (
            "the design's shape, served rather than restated. A skill that "
            "listed these columns in prose would be a second copy of a "
            "generated fact, and it is the copy nothing checks"),
    }
