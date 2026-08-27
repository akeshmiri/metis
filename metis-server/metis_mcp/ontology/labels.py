"""
The ontology (application spec §8.2, §8.3).

Sixty-three labels in eight layers: a **control-flow** model (State, Transition and
friends), the **evidence** layer it is derived from (Endpoint, Parameter, Class,
Field, Method, DeclaredOutcome, Check, ExceptionMapping, Route), a small
**business** layer (BusinessArea, BusinessEntity) giving the nouns a criterion
uses a definition of their own, the **Web structure** (UiElement and its ten
specialisations) and **data** (Datasource, Database, Schema, DbObject, Column)
layers holding what a test acts on and what it must set up, the **intake
anchors** (JiraItem and its five siblings) recording which artefact in the world
a requirement came from, and the **documents** (SpecDocument, EntityDocument)
that are rendered into the graph rather than into files beside it.

**This module is the single source for two of the four governance places** the
spec's D-2 rule names: the structural validator reads it directly, and the Cypher
schema is *generated* from it (see schema.py). Two places that cannot drift is
strictly better than two places kept in step by discipline.

The remaining two -- the catalogue in §8.2/§8.3 of the specification, and this
docstring -- are human-readable and are checked against this module by
test_ontology.py.

Why sixty-three, and why that number should worry you: see D-1 and the note in
`test_ontology`. A label is included only when something writes it AND something
reads it -- the second half is the one that is easy to skip, and a writer alone
is how an ontology accretes. §8.7 lists the deliberately-excluded labels with
the trigger that would bring each back.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Spec D-8: every node carries these. `name` is display data, not identity.
BASELINE_REQUIRED = ("id", "source_episode_id", "name")

# The one exception, and it is structural rather than a concession: an Episode is
# the provenance record every other node points at, so it cannot point at one.
BASELINE_EXEMPT = {"Episode"}

# Lifecycle values (spec §8.6). Generation reads only `Approved` (D-10).
LIFECYCLE_STATES = ("Quarantine", "Approved", "Disputed", "Rejected", "Deprecated")

# ---- Bi-temporal validity -------------------------------------------------
#
# **A second axis, not a refinement of the first.** `lifecycle_state` answers
# "has a human looked at this"; validity answers "was this ever true, and is it
# still". They are independent: a criterion can be `Approved` and no longer
# valid, and collapsing them loses both answers. A system whose entire job is
# comparing what the code does NOW against what somebody said THEN could not
# express "true until release 4.2" with either one alone.
#
# `valid_to` is required-but-may-be-empty rather than optional, which is what
# `may_be_empty` exists for. "" is the honest representation of "still true";
# ABSENT would be indistinguishable from "nobody recorded it", and that is the
# conflation `Transition.guard_expression` already refuses.
#
# **Invalidation SETS `valid_to`. Nothing is deleted.** The superseded fact
# staying answerable is the entire point -- "what did we believe in March" is a
# question the graph should answer, not one it should have forgotten.
#
# `valid_to` is indexed because the overwhelmingly common read is "currently
# valid", i.e. `valid_to = ""`, which is a filter over every node of the label
# rather than a lookup of one.
VALIDITY_REQUIRED = ("valid_from", "valid_to")
VALIDITY_MAY_BE_EMPTY = ("valid_to",)

# Applied where "true until" means something. Deliberately NOT in
# `BASELINE_REQUIRED`: an `Episode` is already immutable and content-addressed,
# and structural evidence (a `Method`, a `Class`) is a fact about a commit rather
# than a claim that can stop being true.
VALIDITY_LABELS = ("Intent", "Specification", "Requirement", "AcceptanceCriterion")

# ---- Free text search -----------------------------------------------------
#
# Declared beside the catalogue rather than inside the query, because the index
# and the query must name the same labels and the same properties. Two lists in
# two files is precisely the drift this catalogue exists to prevent — the schema
# is GENERATED from here for the same reason.
#
# Neo4j Community ships Lucene full-text indexes, so this costs no dependency and
# replaces substring matching with real scoring, tokenisation and phrase support.
# A property named for a label that does not carry it is simply not indexed, so
# the lists do not have to be uniform.
# ---- Semantic search ------------------------------------------------------
#
# **Neo4j does the vector search; Python only has to produce the vector.** That
# split is deliberate and it is what keeps this affordable: the index, the
# similarity function and the query are all database features, so the capability
# costs no dependency at all. Only EMBEDDING needs a provider, and that stays
# behind one pluggable seam that a default install never loads.
#
# `vector.dimensions` is fixed when the index is created and must match the model
# that produced the vectors. A mismatch is not an error Neo4j can catch — it is
# silently meaningless results, which is the same failure mode X-3 pins the Joern
# version against. `retrieval.EmbeddingModel` records which model wrote a vector
# so the mismatch is detectable rather than merely possible.
# One index PER LABEL, unlike the full-text one. Neo4j accepts `(n:A|B|C)` for a
# full-text index and rejects it for a vector index — measured, not assumed: the
# multi-label form raised `Invalid input '|': expected ')'`. The loader queries
# each and fuses the rankings, which rank fusion handles natively.
VECTOR_INDEX_PREFIX = "metis_vector"


def vector_index_for(label: str) -> str:
    """The vector index name for one searchable label."""
    import re
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", label).lower()
    return f"{VECTOR_INDEX_PREFIX}_{snake}"


VECTOR_PROPERTY = "embedding"
VECTOR_MODEL_PROPERTY = "embedding_model"
# 1536 is OpenAI's text-embedding-3-small and a common default. Changing the
# model means changing this AND rebuilding the index; the two cannot drift
# silently because `retrieval` refuses a query whose model does not match what
# the nodes were written with.
VECTOR_DIMENSIONS = 1536
VECTOR_SIMILARITY = "cosine"

SEARCH_INDEX = "metis_search"

# The ASCII-folded copy of whatever a label searches over, indexed beside the
# original. Neo4j's `english` analyzer stems and does not fold; `standard-folding`
# folds and does not stem. Measured: with `english`, searching `Metis` returned
# NOTHING for a corpus about Métis; with `standard-folding`, `locks` stopped
# matching `locking`. Indexing both forms gets both, because the analyzer applies
# to every property in the index.
#
# Required on every searchable label, so a writer cannot quietly omit it and
# leave its nodes findable only by somebody who types the accent.
SEARCH_TEXT = "search_text"

SEARCH_TARGETS = {
    "BusinessEntity": ("name", "description", SEARCH_TEXT),
    "Requirement": ("name", "text", "statement", SEARCH_TEXT),
    "AcceptanceCriterion": ("name", "text", SEARCH_TEXT),
    # The intent spine. Both carry the sentence somebody actually wrote, and
    # leaving them out meant a search for a business phrase could find the
    # criterion derived from a need and not the need itself — the half of §4.1
    # that says what the system is FOR.
    "Intent": ("name", "statement", SEARCH_TEXT),
    "Specification": ("name", "statement", SEARCH_TEXT),
    # The reader half of D-1's bar for `Lesson`. One entry, and the academy is
    # searchable beside the product it teaches.
    "Lesson": ("name", "text", SEARCH_TEXT),
    # A passage is searched, never shown: both search paths roll a hit up to the
    # document that contains it, so the reader still gets a lesson. It is here
    # because this table drives BOTH indexes, and the vector index is the point.
    "Passage": ("name", "text", SEARCH_TEXT),
}

# The states in which a human still owes a decision. `Approved`, `Rejected` and
# `Deprecated` are settled; `Quarantine` has never been looked at and `Disputed`
# has been looked at and contested. Both still want a person.
#
# This is the definition `NeedReview` is kept in step with -- see its LabelSpec.
NEEDS_REVIEW_STATES = ("Quarantine", "Disputed")
NEED_REVIEW = "NeedReview"

# Acceptance-criterion provenance (spec S-19). Defined here, in the ontology,
# rather than beside the matching logic that reads it: a grade the graph cannot
# store is a grade that does not exist. `reconciliation.matching` imports these.
#
# Only the last two are INTENT. A criterion written FROM the code and used to
# check that code can only ever report agreement (§4.1), so `code_derived` gives
# coverage and never correctness. The default is the weakest grade, for the same
# fail-closed reason a model source lands at Quarantine (S-4).
CODE_DERIVED = "code_derived"
HUMAN_CONFIRMED = "human_confirmed"
INDEPENDENTLY_AUTHORED = "independently_authored"
PROVENANCE_GRADES = (CODE_DERIVED, HUMAN_CONFIRMED, INDEPENDENTLY_AUTHORED)

# A target of `*` means the relationship is deliberately not scoped to a fixed
# label. Only two are: revision history applies to every label, and a finding can
# concern anything. Both are documented exceptions, not unenforced holes.
ANY_LABEL = "*"


def specialisations_of(label: str) -> tuple[str, ...]:
    """Every label that specialises `label`, plus `label` itself.

    One definition of "any transition", so the ~30 Cypher sites that used to say
    `:Transition` cannot drift apart as specialisations are added.
    """
    return (label, *sorted(n for n, spec in LABELS.items()
                           if spec.specialises == label))


def label_expression(label: str) -> str:
    """`Transition|ApiCall|UiAction` -- a Cypher label disjunction.

    Needed because a specialisation *replaces* its parent label: a query that
    still said `:Transition` would silently return only the unclassified ones,
    which is the failure mode of making the generic label mean something.
    """
    return "|".join(specialisations_of(label))


@dataclass(frozen=True)
class LabelSpec:
    name: str
    purpose: str
    required: tuple[str, ...] = ()          # beyond BASELINE_REQUIRED
    # Required to be *present*, but legitimately empty. The motivating case is
    # `Transition.guard_expression`: an unguarded transition is normal (three of
    # the login model's seventeen), and "" is the honest representation of it.
    # Conflating "absent" with "empty" would either reject real transitions or
    # let a genuinely missing property through.
    may_be_empty: tuple[str, ...] = ()
    enums: dict[str, tuple[str, ...]] = field(default_factory=dict)
    indexed: tuple[str, ...] = ()
    # A label this one specialises. The specialisation is written **instead of**
    # its parent, not alongside it: a node that is known to be an `ApiCall` does
    # not also carry `:Transition`.
    #
    # That leaves the generic label meaning something useful -- **unclassified**.
    # `MATCH (t:Transition)` is then a worklist of transitions whose surface
    # nothing has established, rather than a synonym for "all of them", and a
    # query can find and resolve them.
    #
    # A specialisation inherits its parent's required properties rather than
    # restating them, so the two cannot drift.
    specialises: str = ""

    @property
    def is_specialisation(self) -> bool:
        return bool(self.specialises)

    @property
    def all_required(self) -> tuple[str, ...]:
        base = () if self.name in BASELINE_EXEMPT else BASELINE_REQUIRED
        inherited = ()
        if self.specialises:
            inherited = LABELS[self.specialises].all_required
        return tuple(dict.fromkeys((*base, *inherited, *self.required)))

    @property
    def all_may_be_empty(self) -> tuple[str, ...]:
        """Inherited too — an unguarded `ApiCall` is normal, exactly as an
        unguarded `Transition` is, and forgetting to inherit this rejects every
        transition whose guard is legitimately empty."""
        inherited = (LABELS[self.specialises].all_may_be_empty
                     if self.specialises else ())
        return tuple(dict.fromkeys((*inherited, *self.may_be_empty)))

    @property
    def all_enums(self) -> dict:
        merged = dict(LABELS[self.specialises].all_enums) if self.specialises else {}
        merged.update(self.enums)
        return merged


LABELS: dict[str, LabelSpec] = {
    spec.name: spec for spec in (
        # ------------------------------------------------------------------
        # The review marker. Carried ALONGSIDE a node's real label.
        # ------------------------------------------------------------------
        #
        # **The fifty-sixth label, and D-2 makes that a reviewed change.** It is
        # here because of one question the property cannot answer: `MATCH
        # (n:NeedReview)` is "everything a human still owes a decision on",
        # across every label at once. `lifecycle_state` is indexed on 54 labels,
        # so per-label lookup was never the problem; there is simply no way to
        # ask it of all of them without scanning every node in the graph.
        #
        # **`lifecycle_state` stays authoritative and this is never consulted to
        # decide anything.** It is a marker maintained FROM that property, added
        # by `landing.land` when a node arrives in a NEEDS_REVIEW_STATES state
        # and removed when a decision settles it. Two representations of one
        # fact is this codebase's most common defect, so the two are written by
        # one place and `test_ontology` asserts they cannot disagree.
        #
        # D-1's writer and reader: written by `model_sources.landing.land` and
        # `mbt.finding_writer.load`; read by `review queue` and the review UI's
        # queue screen, which is the cross-label question that motivated it.
        #
        # It carries no properties of its own. The node's real label carries
        # them, and a marker that accreted properties would become a second
        # place to look for a fact.
        LabelSpec(
            NEED_REVIEW,
            "Marker: a human still owes a decision on this node "
            "(lifecycle_state is Quarantine or Disputed)",
        ),
        LabelSpec(
            "Episode", "Immutable record of one ingested unit; everything derived points here",
            required=("t_recorded", "source_connector", "job_id"),
            indexed=("source_connector", "job_id", "checkpoint_status"),
            # **Deliberately in no relationship, and this is the decision rather
            # than an oversight.** Every other node reaches it through the
            # `source_episode_id` property, which is one of three baseline
            # requirements and is now indexed on every non-exempt label -- so
            # "everything this ingestion produced" is a fast property lookup.
            #
            # An `Episode -[:PRODUCED]-> *` edge was the alternative: one edge
            # per node, restating a fact the node already carries, and two
            # representations of one thing that can disagree. That class of
            # defect -- two vocabularies, two minting rules, two writers for one
            # node -- is where nearly every real bug in this codebase has come
            # from. D-1 asks for a named reader; the reader is the property, and
            # it is named here.
        ),
        LabelSpec(
            "JiraItem", "Evidence anchor for one Jira issue; survives its Requirement being rejected",
            required=("jira_key", "issue_type"),
            indexed=("jira_key",),
        ),
        # ---- The other five intake anchors (§3.2 stage 2) ----
        #
        # An anchor answers "what artefact in the world is this about", which is
        # a different question from the one `Episode` answers ("which run
        # produced this, and can I re-run it"). Conflating them costs the thing
        # `JiraItem`'s own purpose line names: an anchor SURVIVES its Requirement
        # being rejected, where an Episode is minted afresh whenever content
        # changes. Rejecting a claim must never destroy the evidence it came
        # from.
        #
        # One label per source rather than one generic `SourceItem`: a query for
        # "every Confluence page behind an approved requirement" is then a label
        # match rather than a property filter, and each carries the identifier
        # its own system actually uses.
        #
        # Deliberately NOT named `Confluence`/`Database`/`OpenApi` bare:
        # `Database`, `Schema`, `Table`, `View` and `Column` already exist and
        # mean the data-structure source (§5.2b) -- a real database being
        # analysed. One label meaning two things is how a closed ontology stops
        # being closed.
        LabelSpec(
            "ConfluenceItem", "Evidence anchor for one Confluence page",
            required=("page_id",),
            indexed=("page_id", "space"),
        ),
        LabelSpec(
            "OpenApiItem", "Evidence anchor for one OpenAPI/Swagger document",
            required=("document_id",),
            indexed=("document_id", "api_version"),
        ),
        LabelSpec(
            "ZephyrItem", "Evidence anchor for one Zephyr Scale item",
            required=("zephyr_key",),
            indexed=("zephyr_key", "item_type"),
            # Zephyr Scale is one tool. `source_system` is `scale` and the
            # product is Zephyr Scale, so "Scale" and "Zephyr" are the same
            # source and get one label, not two.
        ),
        LabelSpec(
            "DatasourceItem", "Evidence anchor for one analysed database schema",
            required=("datasource_id",),
            indexed=("datasource_id",),
            # Beside `Datasource` (the configured connection) and `Database`
            # (the instance), not instead of either: this is the intake record
            # of having read one, which outlives any particular reading.
        ),
        LabelSpec(
            "CodeItem", "Evidence anchor for one analysed source tree at one revision",
            required=("repo_id",),
            indexed=("repo_id", "revision"),
        ),
        LabelSpec(
            "RestServer", "A Component serving an API surface",
            specialises="Component",
            enums={"surface": ("api",)},
            # Specialisations of `Component`, not new roots. A root would have to
            # restate `version`, `commit_sha` and `journey` -- which P-16 depends
            # on ("which version does this coverage figure refer to") -- and
            # would not inherit `EXPOSES` or `HAS_PAGE`, both of which already
            # exist on the parent. This way "every REST server" is a label match
            # AND the version contract is one definition.
            #
            # Written INSTEAD of `:Component`, like every specialisation. Use
            # `label_expression("Component")` to match any of them.
        ),
        LabelSpec(
            "WebServer", "A Component serving a web surface",
            specialises="Component",
            enums={"surface": ("ui",)},
        ),
        # ---- Rendered documents (§18) ----
        #
        # The graph is the single point of truth and a document is a node in it,
        # not a `.md` file beside it. Two copies of a specification is the exact
        # thing a single point of truth exists to prevent, and a file cannot
        # carry an edge to the behaviour it describes.
        #
        # `body_markdown` is text, not nodes, on `Transition.inputs`' reasoning:
        # the reader renders the whole document and nothing queries a paragraph.
        # `content_hash` is what makes re-rendering unchanged input a no-op
        # (D-8), so a regeneration that changes nothing writes nothing.
        LabelSpec(
            "SpecDocument", "One rendered journey specification (§18)",
            required=("body_markdown", "content_hash", "rendered_at"),
            indexed=("content_hash", "lifecycle_state"),
            enums={"lifecycle_state": LIFECYCLE_STATES},
        ),
        LabelSpec(
            "EntityDocument", "One rendered business-entity specification",
            required=("body_markdown", "content_hash", "rendered_at"),
            indexed=("content_hash", "lifecycle_state"),
            enums={"lifecycle_state": LIFECYCLE_STATES},
        ),
        # **The one label that describes Métis rather than a system under test.**
        #
        # Added under D-2 with the argument written out in
        # `docs/academy/PROPOSAL-landing-the-academy.md`, including the case
        # against. D-1 requires a named writer and a named reader, and the reader
        # is why this is worth a label at all: a lesson joins the full-text index
        # alongside the five labels already in `SEARCH_TARGETS`, so `ask` answers
        # questions about Métis as it answers questions about a product — and a
        # lesson that reads badly through `ask` becomes a finding about the tools
        # rather than about the writing.
        #
        # Writer: `model_sources.lessons`. Reader: `SEARCH_TARGETS`, and every
        # surface that searches.
        #
        # No validity window (D-15): a lesson is a document about this system, not
        # a claim about a product that stops being true. It carries a lifecycle
        # state because it lands at Quarantine like everything else (S-4) — the
        # academy is not exempt from the rule it teaches.
        LabelSpec(
            "Lesson", "One authored academy lesson about Métis itself",
            required=("text", "ordinal", "path", SEARCH_TEXT),
            indexed=("ordinal", "lifecycle_state"),
            enums={"lifecycle_state": LIFECYCLE_STATES},
        ),
        # Added under D-2, on a measurement rather than a hunch.
        #
        # **The argument.** A document embedded as ONE vector answers questions
        # about its subject and loses questions about its sections: the rest of
        # the text dilutes the part that matches. Measured over the academy's 36
        # retrieval questions, same model and same corpus, changing only the unit
        # that carries a vector:
        #
        #     whole-document vectors   26/36 top-1
        #     per-section vectors      32/36 top-1
        #
        # The clearest case is `why is a selector a property and not a node` --
        # a VERBATIM `##` heading in lesson 04, which lesson 03 nonetheless won.
        # That is not a model failing to understand a question; it is a vector
        # that is not about the question. Chunking was worth roughly twice what
        # enabling semantic search was worth at all (+3), so this is the larger
        # half of the only lever that moves ranking.
        #
        # **The case against, since D-2 asks for it.** It is a second node per
        # section -- 8 lessons became 46 passages -- and a node with no
        # independent meaning: nobody asks to see a passage, and it exists only
        # to be matched. That is exactly the argument `Field` was STAGED OUT on
        # (a property of its type, not a node). The difference is the index: a
        # Neo4j vector index carries ONE vector per node, so per-section
        # similarity is not expressible as a property. `Field` had an alternative
        # shape and this has none.
        #
        # Writer: `model_sources.lessons`. Reader: both search paths in
        # `mbt.graph_loader`, which roll a passage up to its parent so the answer
        # shape does not change.
        #
        # No validity window (D-15), for the same reason as `Lesson`: it is part
        # of a document about this system, not a claim about a product.
        LabelSpec(
            "Passage", "One section of a document, embedded on its own",
            required=("text", "ordinal", SEARCH_TEXT),
            indexed=("ordinal",),
        ),
        # ------------------------------------------------------------------
        # The intent spine (§4.1's comparison, made structural)
        # ------------------------------------------------------------------
        LabelSpec(
            "Intent", "One stated need, before anybody has specified how it behaves",
            required=("statement", SEARCH_TEXT) + VALIDITY_REQUIRED,
            may_be_empty=VALIDITY_MAY_BE_EMPTY,
            indexed=("lifecycle_state", "valid_to"),
            enums={"lifecycle_state": LIFECYCLE_STATES},
        ),
        LabelSpec(
            "Specification", "One specified behaviour — where intent and code meet",
            required=("statement", "provenance", SEARCH_TEXT) + VALIDITY_REQUIRED,
            may_be_empty=VALIDITY_MAY_BE_EMPTY,
            indexed=("provenance", "lifecycle_state", "valid_to"),
            # **One label, and the grade is what keeps the comparison alive.**
            # Intent reaches this node one way and the code reaches it another,
            # which is the point: §4.1 says a model extracted from code and used
            # to test that code proves only that the code does what the code
            # does. If both sides landed indistinguishable specifications, that
            # argument would quietly stop being checkable.
            #
            # So the SAME grades `AcceptanceCriterion` already carries ride here,
            # and they are indexed for the same reason: "which specifications in
            # this scope are still code_derived" is the filter that separates a
            # coverage claim from a correctness one. A code-derived spec and a
            # human-authored one are one label and never one fact.
            enums={"provenance": PROVENANCE_GRADES,
                   "lifecycle_state": LIFECYCLE_STATES},
        ),
        LabelSpec(
            "Feature", "One user-facing capability, grouping the scenarios that show it",
            required=("name",),
            indexed=("lifecycle_state",),
            enums={"lifecycle_state": LIFECYCLE_STATES},
        ),
        LabelSpec(
            "Requirement", "One requirement statement",
            required=("ears_pattern", "revision", SEARCH_TEXT) + VALIDITY_REQUIRED,
            may_be_empty=VALIDITY_MAY_BE_EMPTY,
            indexed=("ears_pattern", "lifecycle_state", "valid_to"),
        ),
        LabelSpec(
            "AcceptanceCriterion", "One atomic, testable condition",
            required=("revision", SEARCH_TEXT) + VALIDITY_REQUIRED,
            may_be_empty=VALIDITY_MAY_BE_EMPTY,
            indexed=("lifecycle_state", "provenance", "valid_to"),
            # `provenance` is S-19's grade, and it is indexed because the
            # question it answers is a filter, not a lookup: "which criteria in
            # this scope are still code_derived" is what separates a coverage
            # claim from a correctness one. Without this property the grade was
            # computed by the review path and had nowhere to go.
            enums={"provenance": PROVENANCE_GRADES,
                   "lifecycle_state": LIFECYCLE_STATES},
        ),
        LabelSpec(
            "State", "One observable situation on one surface (spec M-3)",
            required=("surface",),
            enums={"surface": ("ui", "api"), "lifecycle_state": LIFECYCLE_STATES},
            indexed=("surface", "lifecycle_state", "functional_areas", "name_tier"),
        ),
        LabelSpec(
            "Transition", "One interaction: trigger, guard, source and target state",
            required=("trigger", "guard_expression", "implementation_status", "surface"),
            may_be_empty=("guard_expression",),
            enums={
                "surface": ("ui", "api"),
                "implementation_status": ("implemented", "planned"),
                "extraction_method": ("hand_authored", "static_analysis",
                                     "ac_mined", "declared_contract"),
                "lifecycle_state": LIFECYCLE_STATES,
                # Whether the outcome was seen being BUILT or only DECLARED on an
                # annotation. Both are real user paths; only one of them was
                # observed, and a reviewer approves them differently.
                "outcome_source": ("constructed", "declared"),
            },
            indexed=("surface", "lifecycle_state", "implementation_status",
                     "extraction_method", "functional_areas",
                     "source_state_unresolved", "outcome_status", "requires_body",
                     # "show me every path whose precondition is still vague" has
                     # to be one query, or the weaker rejections are invisible
                     # rather than reviewable.
                     "outcome_source", "guard_claim",
                     # "which endpoints return this DTO" is one query, which is
                     # what makes the expected response usable for generation
                     # rather than just displayable.
                     "response_body",
                     # X-8, and the reason it is indexed: "show me everything
                     # still in the implementation's words" has to be one query,
                     # or the cascade has no worklist to drive it.
                     "name_tier", "guard_tier"),
            # Three additions, and one shape decision worth stating.
            #
            # `guard_anchor` (§8.5) is `file:line@commit` for the guard's own
            # source — a guard nobody can trace to a line is a claim taken on
            # trust. `source_state_unresolved` (§5.8) is how "no source state was
            # recoverable" gets said at all, instead of being papered over with a
            # guessed one. `outcome_status` holds the response, so it survives a
            # target state being renamed for what it actually is.
            #
            # **`inputs` is stored as JSON text, not as structure.** Neo4j
            # properties are primitives or arrays of primitives, so a list of
            # parameter records cannot be a property at all. Promoting each
            # parameter to its own node would be the alternative, and D-1 rules
            # it out until something actually queries one. `requires_body` and
            # `input_count` carry the parts worth filtering on, so the JSON is
            # never parsed just to answer a question Cypher should answer.
        ),
        LabelSpec(
            "ApiCall", "A Transition on the api surface: one call and its outcome",
            specialises="Transition",
            enums={"surface": ("api",)},
            # Written **instead of** `:Transition`, not alongside it --
            # `landing.plan_landing` calls `add_node(transition_label, ...)` with
            # no `also`, so the node carries this label only. That leaves the
            # generic `:Transition` meaning "unclassified", and therefore
            # findable, which is the whole point of the split.
            #
            # This comment used to say the opposite, and so did the spec. It is
            # the one semantic that fails silently: a query or a planned edge
            # written against `:Transition` matches nothing and reports success.
            # Use `label_expression("Transition")` to match any of them, and
            # `landing.transition_label_for(surface)` to plan an edge into one.
        ),
        LabelSpec(
            "UiAction", "A Transition on the ui surface: one interaction or observation",
            specialises="Transition",
            enums={"surface": ("ui",)},
            # A `UiAction` either **starts** an API flow (`TRIGGERS`) or
            # **observes** one of its outcomes (`INVOKES`). It never becomes the
            # API transition: the Web flow continues on its own, and a failing
            # call frequently produces no UI transition at all.
        ),
        LabelSpec(
            "Component", "One deployable component at one commit (spec D-6)",
            required=("journey", "surface", "version", "component"),
            enums={"surface": ("ui", "api")},
            indexed=("component", "journey", "surface", "version", "commit_sha"),
            # Was `ModelVersion`, which named Métis's bookkeeping rather than the
            # thing in the world: `records-api v1` at a commit IS a
            # deployable component, and everything downstream — which version a
            # test ran against, what an incident touched — wants to say
            # "component", not "model version".
            #
            # **Identity is (component, commit), and `component` carries the
            # stable half.** A node per commit is what D-6 needs (elements are
            # shared across versions where unchanged), but without the stable key
            # you could not ask "every version of records-api" — the estate
            # would read as 13 components today and 26 after the next commit.
        ),
        LabelSpec(
            "Page", "One screen of a web surface; its states are the conditions it shows",
            required=("component",),
            indexed=("component", "surface"),
            enums={"surface": ("ui",)},
            # D-1 demands a writer and a reader, and both are real.
            #
            # **Writer:** `code_analysis/react_ui_synthesis.py`, from the 9 real
            # screens the react-ui pack recovers. **Reader:** the Web pattern
            # query — "which pages does this component have, and what condition
            # is each in" — which is the question the surface exists to answer
            # and which nothing could ask while the screen name survived only as
            # a substring inside a transition id.
            #
            # A Page is a *grouping* node, deliberately not a link in the
            # `State -> Transition -> State` spine: a walk never passes through
            # one, so path generation stays surface-agnostic.
        ),
        # ------------------------------------------------------------------
        # The Web structure layer: what is ON a page (spec §5.2a).
        # ------------------------------------------------------------------
        #
        # The Web counterpart of the API evidence layer. `Endpoint`/`Parameter`/
        # `Field` are what an API call is made OF; these are what a UI
        # interaction is made of, and a `UiAction` transition points at one with
        # `DERIVED_FROM` exactly as an `ApiCall` points at its `Endpoint`.
        #
        # **Writer:** `model_sources.web_structure`, from a checked-in file --
        # the same discipline as the glossary, and for the same reason. No pack
        # identifies component TYPES: `react-ui` recovers screens, routes and
        # status variables, `js-ui` recovers `addEventListener` bindings whose
        # element selector its own comment calls "frequently NOT recoverable",
        # and neither can tell a `<DataGrid>` from a hand-rolled
        # `<div role="table">`. A person knows; the file is where they say so.
        #
        # **Reader:** the Gherkin renderer, which shows a Feature the controls
        # its scenarios act on; the impact query; and -- the strongest one --
        # test design. A paginated table needs boundary cases and a sortable
        # column needs order cases, which is a question `mbt.techniques` can only
        # ask if the structure is in the graph.
        #
        # **One family, ten specialisations, on the `Transition` precedent.** A
        # specialisation is written INSTEAD of its parent, so `MATCH (t:Table)`
        # is exact, `label_expression("UiElement")` is "every element", and a
        # bare `:UiElement` keeps meaning something useful -- an element whose
        # type nobody has established, which is a worklist rather than a synonym
        # for all of them.
        LabelSpec(
            "UiElement", "One thing on a page whose type has not been established",
            required=("element_type",),
            indexed=("element_type", "page", "lifecycle_state"),
            enums={"lifecycle_state": LIFECYCLE_STATES},
        ),
        LabelSpec("Menu", "A navigation or command grouping", specialises="UiElement"),
        LabelSpec(
            "UiTable", "A tabular listing of records on a page",
            specialises="UiElement",
            # `Table` unqualified is the DATABASE table, which is what it means
            # in this repo's history and in most of engineering. The UI one is
            # qualified because it is the newer claim on the word, and because
            # `MATCH (t:Table)` returning page controls would be a trap.
        ),
        LabelSpec("Form", "A set of inputs submitted together", specialises="UiElement"),
        LabelSpec("Dialog", "A modal surface raised over a page", specialises="UiElement"),
        LabelSpec(
            "Row", "One record's line in a table, and the controls it carries",
            specialises="UiElement",
            # Not a data row. A `Row` node per record would be data masquerading
            # as structure; this is the row TEMPLATE -- what every row offers,
            # which is what a test needs to know.
        ),
        LabelSpec(
            "Pagination", "A table's paging control",
            specialises="UiElement",
            # Its own label because it is a test-design dimension, not decoration:
            # a paginated listing has first/last/empty/overflow cases that an
            # unpaginated one does not, and nothing could ask which tables
            # paginate while this was a boolean inside a description.
        ),
        LabelSpec("Sort", "A table's ordering control", specialises="UiElement"),
        LabelSpec(
            "Action", "An affordance a person can invoke — the thing a click lands on",
            specialises="UiElement",
            # What a `UiAction` transition is DERIVED_FROM. The transition is the
            # behaviour; this is the button.
        ),
        LabelSpec(
            "Event", "The interaction that invokes an action (click, submit, change)",
            specialises="UiElement",
        ),
        LabelSpec(
            "Navigation", "A control that moves to another page",
            specialises="UiElement",
            # Distinct from `Route`, which is the frontend's URL definition. A
            # `Route` says the path `/records/{id}` renders a page; a
            # `Navigation` is the link on some other page that goes there.
        ),

        # ------------------------------------------------------------------
        # The data layer: what a test has to set up, and what it disturbs.
        # ------------------------------------------------------------------
        #
        # **Writer:** `model_sources.data_structure`, from a checked-in file --
        # a catalogue read from a live database is the obvious future writer and
        # is not this. **Reader:** the impact query ("which criteria touch this
        # column"), and test design: a case whose Given is "a record exists in
        # Archived state" needs to know where that state is stored, and nothing
        # could answer it while the schema lived outside the graph.
        #
        # `DbObject` is the base and the same argument `UiElement` makes: the
        # user's list ends in "and other database elements like function, view,
        # ...", and an open-ended list is exactly what a specialisation hierarchy
        # handles well -- an object whose kind nobody classified stays
        # `:DbObject` and is a worklist, rather than forcing a new label per
        # object type the moment one appears.
        LabelSpec(
            "Datasource", "A configured connection through which statements run",
            required=("dialect",),
            indexed=("dialect",),
            # Separate from `Database` because they are not one thing: several
            # datasources (read-write, read-replica, a test fixture) commonly
            # address one database, and which one a test used is a real fact
            # about that test.
        ),
        LabelSpec("Database", "One database instance", indexed=("name",)),
        LabelSpec("Schema", "A named grouping of objects within a database",
                  indexed=("name",)),
        LabelSpec(
            "DbObject", "A database object whose kind has not been established",
            required=("object_type",),
            indexed=("object_type", "name"),
        ),
        LabelSpec("Table", "A stored relation", specialises="DbObject"),
        LabelSpec("View", "A derived relation", specialises="DbObject"),
        LabelSpec("Function", "A callable routine", specialises="DbObject"),
        LabelSpec(
            "Column", "One column, with the constraints declared on it",
            required=("data_type",),
            indexed=("name", "data_type"),
            # The same role `Field` plays for a payload: these are the variants a
            # fixture must satisfy or violate (GD-3), on the storage side.
        ),

        LabelSpec(
            "Scenario", "One covering walk: setup plus a single validated transition",
            required=("criterion", "generator_version"),
            indexed=("criterion",),
        ),
        LabelSpec(
            "TestCase", "One rendered, human-executable artefact",
            required=("content_hash", "steps_json", "expected_result"),
            indexed=("content_hash", "published_id", "published_status", "level"),
            # **The case carries what a person executes**, not just a name and an
            # objective. It used to land `id`, `name`, `objective`,
            # `content_hash` -- so the node was a `Scenario` with an objective,
            # and the steps a tester needs existed only in the renderer's
            # dataclass. F-12 makes the graph the interface consumers query:
            # a case without its steps forces every reader to re-render it,
            # which is the re-derivation F-12 exists to end.
            #
            # `steps_json` is text, on `Transition.inputs`' reasoning -- Neo4j
            # properties are primitives, a list of step records cannot be one,
            # and promoting each step to a node is ruled out by D-1 until
            # something queries a single step. The two facts worth filtering on
            # are lifted out as their own properties: `expected_result` (what
            # the assertion claims) and `step_count`.
            #
            # `precondition_count` is separate from `step_count` because T-1a's
            # rule is that exactly ONE step asserts. A reader checking that
            # invariant should not have to parse JSON to do it.
            # `level` is where the case sits in the pyramid, not what it asserts.
            # Without it, generation cannot be additive: nothing distinguishes a
            # case Métis wrote from an integration test that already covers the
            # same behaviour (REQ-METIS-PG-01).
            enums={"level": ("unit", "integration", "api_functional",
                             "web_functional", "e2e", "performance")},
        ),
        # ------------------------------------------------------------------
        # The business layer: what the nouns in a criterion actually mean.
        # ------------------------------------------------------------------
        #
        # D-1 needs a writer and a reader for each, and both are real.
        #
        # **Writer:** `model_sources.glossary`, from a checked-in glossary file —
        # the same authoring discipline as the knowledge file, and reviewable
        # before anything reaches a database.
        #
        # **Reader:** `specgen.gherkin`, which prints the entities a Feature
        # touches beside its Scenarios, and the impact query — "which criteria
        # touch this entity, and what else is in its area" — which nothing could
        # ask while a business noun existed only as words inside AC prose.
        #
        # **Deliberately not `Class`/`Field`.** Those are the evidence layer:
        # what the code declares. A `BusinessEntity` is what the business means,
        # and the two disagree regularly — that disagreement is a finding, not a
        # modelling error to smooth over by sharing one label.
        LabelSpec(
            "BusinessArea", "One business domain grouping entities and requirements",
            indexed=("name",),
            # No `owner` property. Who owns an area is org data that goes stale
            # faster than anything else here, and nothing reads it.
        ),
        LabelSpec(
            "BusinessEntity", "One business noun: what it is, and what acting on it changes",
            required=("description", SEARCH_TEXT),
            indexed=("name",),
            # `properties_json` and `impact` are the "characteristics" half.
            #
            # **Properties are JSON text, not nodes**, on the same reasoning
            # `Transition.inputs` records: a Neo4j property is a primitive or an
            # array of them, so a list of records cannot be one, and D-1 rules
            # out a node per property until something actually queries one. The
            # reader here renders them all into a glossary block; it does not ask
            # about one. If "which criteria touch Record.state" becomes a real
            # question, promote it then — exactly as `Parameter` was promoted out
            # of `inputs_json` when the EXERCISES edge gave it a reader.
        ),

        LabelSpec(
            "Finding", "A divergence, gap, unverifiable guard, or drift item",
            required=("finding_type",),
            indexed=("finding_type", "severity", "resolution"),
        ),

        # ------------------------------------------------------------------
        # The evidence layer (spec §8.7's staged labels, D-11's trigger met).
        # ------------------------------------------------------------------
        #
        # §8.7 lists `Repository`, `Class`, `Method`, `Endpoint` as returning
        # "when impact analysis needs code structure in the graph, not just
        # anchors", and D-11 calls that list "the staging plan, not a rejection".
        #
        # **X-2 still holds and decides the SHAPE of these.** The engine's graph
        # is never merged; what lands is `code_analysis.contract`'s dataclasses,
        # which are already normalised and engine-independent — that is the
        # entire reason the contract module exists. No Joern node type, id or
        # schema enters the graph, so an engine upgrade still touches only the
        # pack.
        #
        # Why they are here at all: every one of these facts previously lived in
        # a JSON file under /tmp, so a Transition could not say which endpoint
        # it came from, and "which transitions send a field constrained
        # @NotNull" was not a query. D-1's test is a named writer and a named
        # reader; the writer is `raw_landing.py` and the reader is the
        # control-flow layer's derivation edges.
        LabelSpec(
            "Endpoint", "One HTTP entry point as recovered from code (Layer 2)",
            required=("http_method", "path"),
            indexed=("http_method", "path", "handler_type", "validated"),
            # `path` may be `__unresolved__` — a route that exists and could not
            # be read is a different fact from no route at all (T-9d), and
            # collapsing them is what hid the dual-mount defect.
        ),
        LabelSpec(
            "Parameter", "One input an endpoint reads: where it rides and what it must be",
            required=("location",),
            # Kept in step with `code_analysis.contract.PARAMETER_LOCATIONS`,
            # which is the vocabulary the adapter maps into. `cookie` was added
            # there and not here, so a document the adapter read cleanly was
            # then refused by the ontology gate — two lists for one fact, and
            # the failure lands at the boundary between them.
            enums={"location": ("path", "query", "header", "body", "form", "cookie")},
            indexed=("location", "required"),
            # Promoted from `Transition.inputs_json` — a JSON *string*, because
            # a list of records cannot be a Neo4j property. D-1 held this back
            # "until something actually queries one"; the control-flow layer's
            # EXERCISES edge is that reader.
        ),
        LabelSpec(
            "Class", "One declared type: a controller, a service, or a payload schema",
            indexed=("package",),
            # **Deliberately doubles as the payload schema.** A DTO *is* a class;
            # reaching `RecordDto` as a parameter's type and reaching it as
            # `RecordController`'s neighbour must arrive at one node, or the
            # graph says two different things about one type.
        ),
        LabelSpec(
            "Enum", "A declared type whose instances are a closed set of named "
                    "constants — its `constants` ARE its equivalence partitions",
            specialises="Class",
            indexed=("package",),
            # **Written instead of `:Class`, like every other specialisation.**
            # Queries over types must use `label_expression("Class")`; a
            # hardcoded `:Class` silently skips every enum.
            #
            # The fifty-seventh label, and D-2 makes that a reviewed change.
            # It earns its own label because an enum is the one type whose value
            # space is fully known from the source. A `String` field needs a
            # boundary analysis; a field of this type has exactly N partitions
            # and they are enumerable — which is a different kind of test-design
            # input, not a variation on the same one.
        ),
        # ------------------------------------------------------------------
        # What the application asks the database (X-19a).
        # ------------------------------------------------------------------
        LabelSpec(
            "Query", "One thing the application asks a database, with the "
                     "statement it sends",
            required=("query", "form"),
            may_be_empty=("query",),
            indexed=("dialect", "form", "confidence"),
            enums={"form": ("derived", "native", "jpql", "opaque"),
                   "confidence": ("catalogue-confirmed",
                                  "naming-strategy-proposed", "unresolved")},
            # **Written as its dialect**, never as `:Query` — see the
            # specialisations below. `query` may be empty on an opaque one: the
            # statement is genuinely unknown, and "" is the honest form of that
            # where a guessed SQL string would look runnable and be wrong.
        ),
        # A dialect per label, so `MATCH (q:Oracle)` reads as it should. They
        # specialise `Query` so `label_expression("Query")` answers the
        # estate-wide question — twice in one week a hardcoded parent label
        # matched nothing here and both times it cost a real edge, and a service
        # that talks to two databases is the normal case rather than the odd one.
        LabelSpec("Postgres", "A query sent to PostgreSQL", specialises="Query"),
        LabelSpec("Oracle", "A query sent to Oracle", specialises="Query"),
        LabelSpec("MySql", "A query sent to MySQL", specialises="Query"),
        LabelSpec(
            "JpaQuery", "A repository call whose statement could not be "
                        "recovered — carried raw, for a person to complete",
            specialises="Query",
            # The tier that exists so nothing is guessed. A derived name Métis
            # cannot parse, or JPQL whose entity the catalogue has not confirmed,
            # lands here with its reason rather than as invented SQL.
        ),
        LabelSpec(
            "Method", "One method, from Layer 1's structural pass",
            indexed=("type_name",),
        ),
        LabelSpec(
            "DeclaredOutcome", "One observable result of an entry point, as recovered",
            required=("signature",),
            indexed=("status", "link", "discriminator"),
            # The raw fact behind a Transition's outcome. `link` records how it
            # was established — `declared` is an annotation and `name-match` is a
            # disclosed heuristic, and a reviewer weighs them differently.
        ),
        LabelSpec(
            "Check", "One condition evaluated on a path — a guard's own evidence",
            required=("expression",),
            indexed=("dimension_class", "order"),
        ),
        LabelSpec(
            "ExceptionMapping", "An @ExceptionHandler's exception → status mapping",
            required=("exception_type", "status"),
            indexed=("exception_type", "status"),
            # What makes "which exception becomes a 400" evidence rather than
            # inference: the pilot estate maps four distinct exceptions onto 400 and only
            # one of them is bean validation.
        ),
        LabelSpec(
            "Route", "One frontend route: the path that renders a page",
            required=("path",),
            indexed=("path",),
        ),
    )
}

KNOWN_LABELS = frozenset(LABELS)


@dataclass(frozen=True)
class RelationshipSpec:
    from_label: str
    rel_type: str
    to_label: str
    meaning: str
    properties: tuple[str, ...] = ()


ALLOWED_RELATIONSHIPS: tuple[RelationshipSpec, ...] = (
    RelationshipSpec("JiraItem", "REPRESENTS", "Requirement", "System-of-record source"),
    # The other five anchors carry the same edge, for the same reason: it is what
    # makes "which artefact is this requirement about" answerable, and what lets
    # a rejected Requirement leave its evidence standing.
    RelationshipSpec("ConfluenceItem", "REPRESENTS", "Requirement", "System-of-record source"),
    RelationshipSpec("OpenApiItem", "REPRESENTS", "Requirement", "System-of-record source"),
    RelationshipSpec("ZephyrItem", "REPRESENTS", "Requirement", "System-of-record source"),
    RelationshipSpec("DatasourceItem", "REPRESENTS", "Requirement", "System-of-record source"),
    RelationshipSpec("CodeItem", "REPRESENTS", "Requirement", "System-of-record source"),
    # A document describes exactly one thing and cites the criteria it renders.
    # `CITES` is what makes the round trip checkable: a rendered rule can be
    # traced back to the criterion it came from without parsing the markdown.
    RelationshipSpec("SpecDocument", "DESCRIBES", "Component",
                     "The component version this specification renders"),
    RelationshipSpec("EntityDocument", "DESCRIBES", "BusinessEntity",
                     "The business noun this specification defines"),
    RelationshipSpec("SpecDocument", "CITES", "AcceptanceCriterion",
                     "A rule rendered in this document"),
    RelationshipSpec("EntityDocument", "CITES", "AcceptanceCriterion",
                     "A criterion that touches this entity"),
    # **Catalogued, written by nothing.** D-1 asks for a named writer AND a
    # named reader; this has neither. It stays because the UIF a Jira intake
    # produces carries `issuelinks` and `intake_landing` is where they would
    # land — but until something writes it, a query for "what does this issue
    # link to" returns nothing and cannot tell that from "it links to nothing".
    # Named here so the gap is stated rather than discovered.
    RelationshipSpec("JiraItem", "LINKS_TO", "JiraItem",
                     "A real Jira issue link — provenance, not traceability"),
    # ---- the intent spine ----
    RelationshipSpec("Intent", "SPECIFIED_BY", "Specification",
                     "A need, once somebody has said how it behaves"),
    RelationshipSpec("Specification", "HAS_AC", "AcceptanceCriterion",
                     "The atomic conditions this specified behaviour breaks into"),
    RelationshipSpec("Specification", "SPECIFIES", "Requirement",
                     "The requirement this behaviour belongs to — kept so §7.8's "
                     "chain still reaches a Requirement (A-24)"),
    RelationshipSpec("Specification", "REALISED_BY", "Feature",
                     "The capability this behaviour is part of. `feature.derive` "
                     "groups SPECIFICATIONS -- on the business noun they name, or "
                     "the component that implements them -- so this is the edge "
                     "the grouping actually establishes. Without it the derivation "
                     "planned AcceptanceCriterion edges using specification ids, "
                     "and every one matched nothing"),
    RelationshipSpec("AcceptanceCriterion", "REALISED_BY", "Feature",
                     "The capability this condition is part of"),
    RelationshipSpec("Requirement", "REALISED_BY", "Feature",
                     "The capability this requirement is part of"),
    RelationshipSpec("Feature", "HAS_SCENARIO", "Scenario",
                     "The walks that demonstrate this capability"),
    # A specialisation inherits its parent's *properties* but not its catalogue
    # entries, so each needs its own. Without these two lines both labels are
    # orphans -- declared, writable, and reachable by no traversal, which is
    # exactly what D-1's "named reader" half exists to prevent.
    RelationshipSpec("RestServer", "EXPOSES", "Endpoint", "The entry points it serves"),
    RelationshipSpec("RestServer", "CONTAINS", "Transition", "Its behaviour at one commit"),
    RelationshipSpec("WebServer", "HAS_PAGE", "Page", "The screens it serves"),
    RelationshipSpec("WebServer", "CONTAINS", "Transition", "Its behaviour at one commit"),
    # ---- the code side reaching the SAME Specification, by its own edge ----
    #
    # A different verb from `Intent`'s on purpose. The node is shared so the two
    # can be compared; the edge is what says which side arrived, and
    # `Specification.provenance` says it again on the node itself. Collapsing
    # both onto one verb would make "somebody asked for this" and "the code does
    # this" the same statement, which is the one thing §4.1 forbids.
    RelationshipSpec("Endpoint", "IMPLEMENTS", "Specification",
                     "This entry point is one implementation of that behaviour"),
    RelationshipSpec("Action", "IMPLEMENTS", "Specification",
                     "This affordance is one implementation of that behaviour"),
    RelationshipSpec("Requirement", "HAS_AC", "AcceptanceCriterion", "Its atomic conditions"),
    RelationshipSpec("AcceptanceCriterion", "VALIDATES", "Transition",
                     "Confirmed match (spec X-18)"),
    RelationshipSpec("State", "WHEN", "Transition", "Source state — the implicit Given"),
    RelationshipSpec("Transition", "THEN", "State", "Resulting target state"),
    # **Two edges, because they are two different claims (M-5a).**
    #
    # `TRIGGERS` is one-to-many and says *this interaction starts that flow* —
    # the Web flow then continues on its own, and nothing yet knows which outcome
    # will occur. `INVOKES` is one-to-one and says *this UI outcome rendered that
    # API outcome*.
    #
    # They were one edge, and conflating them made the graph read as though the
    # two flows merged. It also broke a loader that stored them in a `{ui: api}`
    # dict: a page opening three calls kept one and silently dropped two.
    RelationshipSpec("UiAction", "TRIGGERS", "ApiCall",
                     "This interaction starts that API flow; the UI continues (M-5a)"),
    RelationshipSpec("UiAction", "INVOKES", "ApiCall",
                     "This UI outcome rendered that API outcome (M-5a, M-5b)"),
    RelationshipSpec("Component", "HAS_PAGE", "Page",
                     "A screen this web component presents"),
    RelationshipSpec("Page", "SHOWS", "State",
                     "A condition this page can be observed in (M-2, M-3)"),

    # ---- the Web structure tree ---------------------------------------------
    #
    # `HAS_ELEMENT` throughout, so "every control on this page, at any depth" is
    # one variable-length query rather than a union over container types. The
    # triples are explicit rather than `UiElement -> UiElement`: the containment
    # rules are real (a Row belongs to a Table, not to a Menu), and cataloguing
    # them is what makes a modelling error a refused write instead of a silent
    # shape nobody notices.
    *[RelationshipSpec(container, "HAS_ELEMENT", element,
                       "A control this surface presents")
      for container, elements in (
          # `UiElement` is the generic, and it is here so an element whose type
          # nothing established is discoverable. All ten of its specialisations
          # carried this edge and the parent carried none -- so `Transition`
          # stays reachable through `COVERS` while an unclassified UI element
          # could not be found and resolved, which is the entire reason a
          # generic label is kept.
          ("Page", ("UiElement", "Menu", "UiTable", "Form", "Dialog", "Action",
                    "Event", "Navigation")),
          ("Menu", ("Action", "Event", "Navigation", "Dialog")),
          ("UiTable", ("Action", "Event", "Navigation", "Dialog",
                       "Row", "Pagination", "Sort")),
          ("Form", ("Action", "Event", "Navigation", "Dialog")),
          # A dialog with no controls cannot be dismissed, and a row with none is
          # inert. Neither was in the original list; both are what makes the
          # other rules usable, and they are named here rather than assumed.
          ("Dialog", ("Action", "Event", "Navigation")),
          ("Row", ("Action", "Event", "Navigation", "Dialog")),
          ("Pagination", ("Action", "Event")),
          ("Sort", ("Action", "Event")),
      ) for element in elements],
    # ---- the data tree ------------------------------------------------------
    RelationshipSpec("Datasource", "CONNECTS_TO", "Database",
                     "Which database this connection addresses"),
    RelationshipSpec("Database", "HAS_SCHEMA", "Schema", "A grouping it contains"),
    *[RelationshipSpec(container, "HAS_OBJECT", kind, "An object it contains")
      for container in ("Schema", "Database")
      for kind in ("Table", "View", "Function", "DbObject")],
    *[RelationshipSpec(relation, "HAS_COLUMN", "Column", "A column it declares")
      for relation in ("Table", "View")],
    # What a criterion's data actually lives in. The same shape as
    # `AcceptanceCriterion-[:REFERENCES]->BusinessEntity`, one layer down: an
    # entity is what the business calls it, a table is where it is kept.
    RelationshipSpec("BusinessEntity", "STORED_IN", "Table",
                     "Where this business noun is persisted"),

    # `ON_EVENT` and `RENDERS` below are the UI surface's own joins, and nothing
    # writes either: `engine.extract` runs the two JVM packs whatever a profile's
    # surface says, so react-ui and js-ui have never produced a fact. Both packs
    # now declare `status: unwired` in their manifests. Wiring pack selection by
    # surface is what gives these writers.
    RelationshipSpec("Action", "ON_EVENT", "Event",
                     "The interaction that invokes this action"),
    RelationshipSpec("Navigation", "NAVIGATES_TO", "Page",
                     "Where this control goes"),
    # The join to behaviour, mirroring `Transition-[:DERIVED_FROM]->Endpoint`.
    RelationshipSpec("Transition", "DERIVED_FROM", "Action",
                     "The control this interaction was recovered from"),
    # The only edge a Passage has. It is reached from its document and never
    # searched for on its own, which is what keeps a node with no independent
    # meaning from becoming one the reader has to know about.
    RelationshipSpec("Lesson", "CONTAINS", "Passage",
                     "Its sections, each carrying its own vector"),
    RelationshipSpec("Component", "CONTAINS", "State", "Membership of this component version"),
    RelationshipSpec("Component", "CONTAINS", "Transition", "Membership of this component version"),
    RelationshipSpec("Scenario", "GENERATED_FROM", "Component",
                     "The exact version this path covers"),
    RelationshipSpec("Scenario", "COVERS", "Transition",
                     "Ordered traversal — makes coverage computable",
                     properties=("sequence", "is_validated")),
    RelationshipSpec("Scenario", "PRODUCES", "TestCase", "The rendered artefact"),
    RelationshipSpec("BusinessEntity", "BELONGS_TO", "BusinessArea",
                     "Which domain this noun lives in"),
    RelationshipSpec("Requirement", "BELONGS_TO", "BusinessArea",
                     "Which domain this requirement governs"),
    # The edge that makes "what is the impact" answerable. Without it a business
    # noun is a word inside prose, and nothing can be asked about it.
    RelationshipSpec("AcceptanceCriterion", "REFERENCES", "BusinessEntity",
                     "A business noun this criterion acts on or constrains"),
    RelationshipSpec("Finding", "ABOUT", ANY_LABEL, "What the finding concerns"),

    # ---- inside the evidence layer -----------------------------------------
    RelationshipSpec("Component", "EXPOSES", "Endpoint",
                     "The entry points this deployable presents"),
    RelationshipSpec("Endpoint", "ACCEPTS", "Parameter", "What a caller must send"),
    RelationshipSpec("Parameter", "OF_TYPE", "Class",
                     "The payload schema — the same node as the declared type"),
    RelationshipSpec("Endpoint", "RETURNS", "Class", "The declared response body type"),
    # **The nested payload.** Without this a DTO field whose type is another DTO
    # was a dead end: `MfaServiceRequest.answers` named `AnswerDto` in a string
    # property and reached it through nothing, so the payload a test case has to
    # construct was only ever one level deep. Followed as far as the declared
    # types go, stopping on a type already on the path and on any type this
    # repository does not declare (REQ-CGA-010 — no stub for a JDK type).
    RelationshipSpec("Class", "OF_TYPE", "Class",
                     "A field of this type is itself a declared type — the "
                     "nested payload. Which field is on `f_<name>_type`"),
    RelationshipSpec("Class", "DECLARES_METHOD", "Method", "Its methods"),
    RelationshipSpec("Endpoint", "HANDLED_BY", "Method", "The handler behind the route"),
    RelationshipSpec("Method", "CALLS", "Method", "A resolved call edge (Layer 1)"),
    # X-19a. `ISSUES` is the path a transition reaches a table by:
    # ApiCall -> Endpoint -> HANDLED_BY -> Method -> CALLS* -> Method -> ISSUES.
    RelationshipSpec("Method", "ISSUES", "Query",
                     "A query this method sends to a database"),
    # Every table a query touches, so a join names both rather than one.
    RelationshipSpec("Query", "QUERIES", "Table",
                     "A table this query reads or writes"),
    RelationshipSpec("Query", "QUERIES", "View", "A view this query reads"),
    RelationshipSpec("Query", "USES", "Column",
                     "A column this query names — a test-design input, because "
                     "it is what a fixture has to populate"),
    RelationshipSpec("Endpoint", "DECLARES", "DeclaredOutcome",
                     "A result this entry point can produce"),
    RelationshipSpec("DeclaredOutcome", "GUARDED_BY", "Check",
                     "The condition selecting this outcome"),
    RelationshipSpec("ExceptionMapping", "HANDLED_BY", "Method",
                     "The @ExceptionHandler that maps it"),
    RelationshipSpec("Route", "RENDERS", "Page", "The page this frontend route shows"),
    RelationshipSpec("Page", "CALLS", "Endpoint", "An API call this page makes"),

    # ---- evidence -> control flow, the join between the two layers ---------
    #
    # **This is what the second layer is FOR.** Before these, a Transition's only
    # provenance was a `source_episode_id` property pointing at an Episode that
    # recorded "the code source ran" — which endpoint, which outcome and which
    # field were answerable only by re-reading a file in /tmp.
    RelationshipSpec("Transition", "DERIVED_FROM", "Endpoint",
                     "The entry point this behaviour was recovered from"),
    RelationshipSpec("Transition", "DERIVED_FROM", "DeclaredOutcome",
                     "The recovered outcome this transition represents"),
    RelationshipSpec("Transition", "DERIVED_FROM", "ExceptionMapping",
                     "The exception→status mapping behind a derived rejection"),
    RelationshipSpec("Transition", "EXERCISES", "Parameter",
                     "An input this transition sends (replaces inputs_json)"),
    # Was `-> Field` until X-6d flattened a field onto its type. The claim is
    # weaker and honest: the TYPE whose constraints a case must satisfy or
    # violate, with which field carrying which constraint on `f_<name>_*`.
    RelationshipSpec("Transition", "REQUIRES", "Class",
                     "A payload type whose field constraints a case must "
                     "satisfy or violate (GD-3)"),
    RelationshipSpec("Transition", "EXPECTS", "Class",
                     "The response body a case should assert"),
    # **The weaker form of the same claim, and it is labelled as one.** A guard
    # whose outcome could not be recovered is referenced by no DeclaredOutcome and
    # no Transition, so it landed connected to nothing — both checks recovered
    # from a real service were of that shape. Attached to the endpoint whose
    # handler it was found in, this says "a condition was recovered here", never
    # "this condition selects that outcome".
    RelationshipSpec("Endpoint", "CONSTRAINED_BY", "Check",
                     "A condition recovered in this endpoint's handler that no "
                     "outcome references"),
    RelationshipSpec("Transition", "CONSTRAINED_BY", "Check",
                     "The recovered condition behind this transition's guard"),
)

RELATIONSHIP_TYPES = tuple(dict.fromkeys(r.rel_type for r in ALLOWED_RELATIONSHIPS))

# Spec §8.7 — excluded, each with the trigger that would bring it back. Kept in
# code so the staging plan is checkable, not just prose.
STAGED_OUT: dict[str, str] = {
    # A field was its own node until X-6d: 68 of them on a real twelve-endpoint
    # service, saying what four properties say, and never queried individually.
    # What a test-designer asks is "what values does this type accept", which is
    # one question about one node — so a scalar field is now `f_<name>_*` on its
    # type and a complex one is a `Class-[:OF_TYPE]->Class` edge.
    "Field": "a field needs an identity of its own — a per-field review state, "
             "or an edge that must point at one field rather than at its type",
    # Declared with neither a writer nor a reader -- `test_ontology` already
    # named it "the standing example of what this test exists to prevent", and
    # it stayed declared anyway. Property-level history needs a temporal design
    # nothing here has; the integer `revision` property on Requirement and
    # AcceptanceCriterion carries what the graph actually uses today.
    "Revision": "property-level history is designed AND something writes it — "
                "an integer `revision` property is what is used now",
    # Written by `plan_persist` and `finding_writer`, matched by no query --
    # D-1 asks for a named writer AND a named reader, and this had only the
    # first. F-3's reproducibility half is already carried elsewhere:
    # `Component` holds the version and commit, and `.metis/runs/*.json` holds
    # the scope and criterion that `workflow status` actually reads.
    "Run": "two generation runs need comparing IN THE GRAPH — F-3's "
           "comparability half, which the run file cannot answer across scopes",
    "Goal": "a backlog hierarchy is actually queried",
    "Capability": "a backlog hierarchy is actually queried",
    "Epic": "a backlog hierarchy is actually queried",
    "Release": "execution results are ingested and release reporting is required",
    "TestCycle": "execution results are ingested",
    "TestExecution": "execution results are ingested (spec C-10's trigger)",
    "Defect": "operational data enters scope",
    "Incident": "operational data enters scope",
    "Alert": "operational data enters scope",
    "Metrics": "operational data enters scope",
    "Logs": "operational data enters scope",
    "Constitution": "formal governance is adopted",
    "Constraint": "formal governance is adopted",
    # `Class`, `Method` and `Endpoint` were here, on the trigger "impact analysis
    # needs code structure in the graph, not just anchors". **The trigger fired**
    # — for a related reason rather than the one predicted: the control-flow
    # layer needed to say what it was derived FROM, and every one of these facts
    # was sitting in a JSON file under /tmp. D-11 calls this list a staging plan,
    # and a staged label that has been admitted must leave it, or the ontology
    # claims to exclude something it ships.
    #
    # `Repository` stays out. Nothing writes or reads it: one repository is the
    # unit of extraction and it is already named on every anchor.
    "Repository": "impact analysis needs code structure in the graph, not just anchors",
    "TestDesign": "a concrete need appears",
    "TestSuite": "a concrete need appears",
    "MicroRequirement": "a concrete need appears",
}


def relationships_from(label: str) -> tuple[RelationshipSpec, ...]:
    return tuple(r for r in ALLOWED_RELATIONSHIPS
                 if r.from_label == label or r.from_label == ANY_LABEL)


def _with_parents(label: str) -> tuple[str, ...]:
    """`ApiCall` -> `("ApiCall", "Transition")`. Walks the chain."""
    out, current = [label], LABELS.get(label)
    while current is not None and current.specialises:
        out.append(current.specialises)
        current = LABELS.get(current.specialises)
    return tuple(out)


def is_allowed(from_label: str, rel_type: str, to_label: str) -> bool:
    """Whether the triple is catalogued, **following the specialisation chain**.

    A specialisation is written instead of its parent, so an `ApiCall` is a
    `Transition` that has been classified. Without the walk, every catalogued
    `-> Transition` triple -- `WHEN`, `THEN`, `VALIDATES`, `COVERS`, `CONTAINS` --
    would reject the very nodes the classification produces.
    """
    from_labels = _with_parents(from_label)
    to_labels = _with_parents(to_label)
    for r in ALLOWED_RELATIONSHIPS:
        if r.rel_type != rel_type:
            continue
        if r.from_label != ANY_LABEL and r.from_label not in from_labels:
            continue
        if r.to_label != ANY_LABEL and r.to_label not in to_labels:
            continue
        return True
    return False
