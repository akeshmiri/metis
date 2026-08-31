"""
What test generation consumes from the model — declared, and checkable.

**Why this exists.** Nothing stated what generation takes from the model, and the
absence cost twice over at once. `Transition` grew fields nothing on the path
reads — `outcome_source`, `guard_claim`, `name_tier` — while facts the model
holds died before the artefact: `media_types` is loaded and read nowhere, so no
generated test ever sets a content type. The two symptoms look opposite and have
one cause. Properties accrete when nothing says which are owed, and gaps persist
when nothing says which are missing.

**The shape is `labels.LABELS` + `STAGED_OUT`, applied to fields.** A field is
either consumed — and a test proves how far it travels — or deliberately not,
carrying the trigger that would change that. The set is closed against
`dataclasses.fields`, so adding a field to `mbt/model.py` without deciding its
status fails a test rather than passing unnoticed.

**`reaches` is measured, not asserted.** Every claim here was established by
putting a sentinel in one field and following it through `render`, which is also
what `test_generation_contract.py` does on every run.

**Two destinations now, and they fail independently.** A fact can be rendered
into the human-readable case, or consumed as a precondition and never rendered.
There were four: `payload` (`metis.automation-payload/1`) and `artefact` (the
emitted `.java` / `.spec.ts`) went with the generators, because Métis states what
must be verified and does not produce the implementation.

**Five facts reached ONLY those two** and are no longer consumed by anything:
`Transition.id`, `security`, `media_types`, `guard_anchor` and `State.page`.
They are recorded in `GENERATOR_ONLY` rather than deleted — a property the model
still carries and nothing now reads is worth being able to see, and it is the
list to revisit if an executor is ever handed a machine-readable form again.

Not a JSON manifest: `intakes.py:_root()` walks to the repo root and does not
survive a wheel install, and here the check *is* the artefact. Not in
`mbt/model.py`: that declares what the model *holds*; this declares what
generation *takes*, and `rendering` imports `mbt`, never the reverse.

(Unrelated to `code_analysis/contract.py`, which is the normalised pack contract.
Different package, no import clash.)
"""
from __future__ import annotations

from dataclasses import dataclass

CONTRACT_VERSION = "metis.generation-contract/1"

# Where a fact can arrive. Ordered by how far along the chain it is.
PROSE = "prose"          # the human-readable TestCase — R8's actual product
GATE = "gate"            # consumed as a precondition, never rendered (D-10)

DESTINATIONS = (PROSE, GATE)

# Retired with the generators. Kept as names rather than as `reaches` entries so
# that `test_generation_contract` measures against destinations that still exist,
# while the fact that these properties are now read by nothing stays visible.
PAYLOAD = "payload"      # metis.automation-payload/1 — removed
ARTEFACT = "artefact"    # the emitted .java / .spec.ts — removed
RETIRED_DESTINATIONS = ()

#: Properties the model carries that no destination reads any more.
GENERATOR_ONLY = (
    ("Transition", "id"),
    ("Transition", "security"),
    ("Transition", "media_types"),
    ("Transition", "guard_anchor"),
    ("State", "page"),
)

# --------------------------------------------------------------------------
# What a property is FOR
# --------------------------------------------------------------------------
#
# **The question this answers: opening an `ApiCall` in Neo4j Browser shows 25
# properties in one flat table, and nothing says which describe the CALL and
# which describe the BEHAVIOUR.** `trigger` and `inputs_json` and `guard_tier`
# and `source_episode_id` sit side by side looking equally important, and a QA
# engineer has to know the codebase to tell a fact about the state machine from
# a fact about how the request is issued.
#
# A property may serve two concerns and several genuinely do — `trigger` names
# the interaction AND is where the curl's method and path are split from. Saying
# so is more useful than forcing a single bucket, because the straddle is exactly
# what a reader needs to know.

REQUEST = "request"          # what a caller must send — the curl's inputs
RESPONSE = "response"        # what comes back — what a case asserts
BEHAVIOUR = "behaviour"      # the state machine itself
DATA = "data"                # conditions the test data must satisfy
PROVENANCE = "provenance"    # where the fact came from, and how far to trust it
IDENTITY = "identity"        # keys and scope
REVIEW = "review"            # human decisions
PRESENTATION = "presentation"  # display wording and the tier that produced it

CONCERNS = (REQUEST, RESPONSE, BEHAVIOUR, DATA, PROVENANCE, IDENTITY, REVIEW,
            PRESENTATION)

# The two a "how do I call this?" reader wants, and the one a "what does it do?"
# reader wants. Named so a view can ask for them rather than re-deriving.
CURL_CONCERNS = (REQUEST, RESPONSE)
MODEL_CONCERNS = (BEHAVIOUR, DATA)

# --------------------------------------------------------------------------
# Property-name prefixes
# --------------------------------------------------------------------------
#
# A node shows its properties in one alphabetical table, so a prefix is what
# makes the concerns visible at the point somebody is actually reading — the
# grouping this module computes, carried into the name itself.
#
# **`f_` is deliberately absent.** It is taken: `ontology.facts.FIELD_PREFIX` is
# `f_`, and `expand_fields` decodes anything starting with it as a payload field
# of a `Class`. A UI prefix of `f_` would be silently decoded as field data and
# would corrupt `payload_shape` and `call_recipe`. `u_` carries the UI concern
# instead.
#
# Only four concerns take a prefix. The rest — provenance, identity, review,
# presentation — stay bare on purpose: being unprefixed is itself the signal
# that a property is not what either question is about.
CALL_PREFIX = "c_"
BEHAVIOUR_PREFIX = "b_"
PAGE_PREFIX = "p_"
UI_PREFIX = "u_"
# **How we know, as opposed to what we know.** Nine of a transition's
# twenty-five properties were tier, claim, anchor, wording and extraction
# method — more than a third of the node, none of it a fact about the system
# under test, all of it competing for attention with the facts it annotates.
# They are still worth having (a reviewer weighs a `code_convention` guard
# differently from a confirmed one); they are not worth reading first.
EPISTEMIC_PREFIX = "x_"

# Which prefix a concern earns. Order matters: a property serving two concerns
# takes the prefix of the FIRST match, and a name can only say one thing.
#
# **`c_` has priority over `b_`.** A property that is part of issuing or
# asserting the call is named for that, even when it is also part of the state
# machine — `trigger` is the transition's interaction AND is where the curl's
# method and path are split from, and it takes `c_`. The reasoning: somebody
# scanning for "what do I need to make this call?" must not miss a property
# because it was filed under the behaviour, whereas the state machine is legible
# from the graph's shape regardless of what its properties are called.
PREFIX_FOR: tuple[tuple[str, str], ...] = (
    (RESPONSE, CALL_PREFIX),
    (REQUEST, CALL_PREFIX),
    (BEHAVIOUR, BEHAVIOUR_PREFIX),
    # Last, so anything that is also a fact keeps the prefix of the fact.
    (PROVENANCE, EPISTEMIC_PREFIX),
    (PRESENTATION, EPISTEMIC_PREFIX),
)

# The three properties every label carries (`labels.BASELINE_REQUIRED`). They
# stay bare: prefixing `name` would be renaming a field on every node in the
# graph to say something a reader already knows, and `source_episode_id` is
# provenance on an `Episode`, a `Finding` and a `Lesson` alike — not a fact
# about transitions to be sorted away from.
NEVER_PREFIXED = frozenset({"id", "source_episode_id", "name"})

# Properties whose concern is right but whose prefix is not derivable from it.
# A UI state's `page` and `condition` are both RESPONSE — what a tester observes
# — but they describe the PAGE, and a reader looking for the page should not have
# to know that "response" is where it was filed.
PREFIX_OVERRIDE: dict[tuple[str, str], str] = {
    # `page` and `condition` are both RESPONSE — what a tester observes — so the
    # precedence rule would give them `c_`. They are overridden because they
    # describe the PAGE specifically, and a reader looking for the page should
    # not have to know it was filed under the call.
    ("State", "page"): PAGE_PREFIX,
    ("State", "condition"): PAGE_PREFIX,
    # **These three lost their derivation with the generators.** A prefix comes
    # from a fact's `concerns`, and the facts that declared theirs left `CONSUMED`
    # when `payload` and `artefact` did. The properties are still landed and must
    # still be spelled the way landing writes them, so the name is stated here
    # rather than inferred from a fact that no longer exists.
    ("Transition", "security"): CALL_PREFIX,
    ("Transition", "media_types"): CALL_PREFIX,
    ("Transition", "guard_anchor"): EPISTEMIC_PREFIX,
}

# `u_` is declared and carries nothing today. Forms are an interaction
# (`fill_form` in the vocabulary a runner uses), not node data, so no property
# has earned it yet — recorded rather than invented, so the prefix is ready and
# is not quietly doing nothing while looking as though it does.
UNUSED_PREFIXES = {UI_PREFIX: "forms are an interaction, not node data — no "
                             "property carries this yet"}


def prefix_for(element: str, prop: str) -> str:
    """The prefix a property's name should carry, or `""` for none."""
    bare = unprefixed(prop)
    if bare in NEVER_PREFIXED:
        return ""
    override = PREFIX_OVERRIDE.get((element, bare))
    if override is not None:
        return override
    concerns = concerns_of(element, bare)
    for concern, prefix in PREFIX_FOR:
        if concern in concerns:
            return prefix
    return ""


def graph_name(element: str, prop: str) -> str:
    """What a property is called ON THE NODE, prefix included. Idempotent."""
    bare = unprefixed(prop)
    return prefix_for(element, bare) + bare


@dataclass(frozen=True)
class ModelFact:
    """One model field, and how far it actually travels.

    `owed` is the whole point of the frozen pair: a field can be genuinely read
    and still not reach where it is needed. An empty `owed` means the fact
    arrives everywhere it should — and that is an assertion the test suite
    checks, not a comment.
    """

    element: str                    # "Transition" | "State"
    field: str
    reaches: tuple[str, ...]        # verified by sentinel on every run
    consumers: tuple[str, ...]      # who reads it, as module.function
    why: str                        # what a generated case loses without it
    owed: str = ""                  # what it should ALSO reach, and does not
    # The destinations `owed` is about, when it is about destinations at all.
    # `inputs` reaches the artefact and is still incomplete — it arrives as a
    # data-requirement comment rather than a request body — so a gap is not
    # always expressible as somewhere the fact fails to arrive.
    owed_reaches: tuple[str, ...] = ()
    # What this property is FOR. Several serve two; see the note by `CONCERNS`.
    concerns: tuple[str, ...] = ()
    graph_property: str = ""        # what landing writes; "" if same as `field`
    affects_artefact: bool = False  # a change here changes an emitted assertion

    @property
    def is_complete(self) -> bool:
        return not self.owed

    @property
    def landed_as(self) -> str:
        """The property's name ON THE NODE, prefix included.

        Reads `self.concerns` directly rather than going through `concerns_of`,
        which searches `CONSUMED` by `landed_as` and would recurse.
        """
        base = self.graph_property or self.field
        override = PREFIX_OVERRIDE.get((self.element, base))
        if override is not None:
            return override + base
        for concern, prefix in PREFIX_FOR:
            if concern in self.concerns:
                return prefix + base
        return base


# ---------------------------------------------------------------------------
# Consumed — generation reads it. `reaches` says how far.
# ---------------------------------------------------------------------------

CONSUMED: tuple[ModelFact, ...] = (
    ModelFact(
        "Transition", "source", (PROSE,),
        ("mbt.path_generation.generate", "rendering.test_case.render"),
        "no path can be walked and no precondition stated",
        concerns=(BEHAVIOUR,)),
    ModelFact(
        "Transition", "target", (PROSE,),
        ("mbt.path_generation.generate", "rendering.payload._step_payload"),
        "nothing says where the case lands",
        concerns=(BEHAVIOUR,)),
    ModelFact(
        "Transition", "trigger", (PROSE,),
        ("rendering.test_case._describe", "rendering.payload._act_detail",
         "rendering.generators.rest_assured._step"),
        "the method and path are split from it — with no trigger there is no call",
        affects_artefact=True,
        concerns=(BEHAVIOUR, REQUEST)),
    ModelFact(
        "Transition", "guard", (PROSE,),
        ("rendering.test_case.render", "rendering.payload._step_payload",
         "rendering.generators._data.lines"),
        "the precondition a case must establish, and the data requirement it "
        "states (M-9: a requirement, never a solved value)",
        graph_property="guard_expression", affects_artefact=True,
        concerns=(BEHAVIOUR, DATA)),
    ModelFact(
        "Transition", "implementation_status", (GATE,),
        ("mbt.model.Transition.is_generatable", "mbt.model.Transition.exclusion_reason"),
        "a planned transition would be generated as though it were built",
        concerns=(BEHAVIOUR,)),
    ModelFact(
        "Transition", "lifecycle_state", (GATE,),
        ("mbt.model.Transition.is_generatable", "mbt.cli._require_approved"),
        "D-10: generation reads only Approved. Without this the G1 gate is not "
        "enforced at the point of generation",
        concerns=(REVIEW,)),
    ModelFact(
        "Transition", "inputs", (PROSE,),
        ("rendering.test_case.input_condition", "rendering.payload._act_detail",
         "rendering.generators._data.lines"),
        "what a caller must send. A POST with a recovered body used to be emitted "
        "with no body at all. It now carries the CONDITION — `body.record is a "
        "required RecordDto` — and a real `.body(...)` appears only where the "
        "fixtures join supplied a value, labelled as authored. That a body is "
        "absent without a fixture is the designed behaviour, not a gap: which "
        "document satisfies the condition is a decision a person makes (T-9c)",
        # `_json` is dropped from the name. It is a STORAGE detail — structure
        # cannot be a Neo4j property, so a list of records rides as JSON text —
        # and the `c_` prefix is a PURPOSE. Stacking them made one name say two
        # orthogonal things, and the value is visibly a JSON string anyway.
        # `graph_loader._json_rows` still decodes it.
        graph_property="inputs", affects_artefact=True,
        concerns=(REQUEST, DATA)),
    ModelFact(
        "Transition", "outcome_status", (PROSE,),
        ("rendering.test_case.observable_result", "rendering.payload._act_detail",
         "rendering.generators.rest_assured._step"),
        "the status a case asserts. Absent, the emitter states that asserting one "
        "would invent it rather than defaulting to 200",
        affects_artefact=True,
        concerns=(RESPONSE, BEHAVIOUR)),
    ModelFact(
        "Transition", "response_body", (PROSE,),
        ("rendering.test_case.observable_result", "rendering.payload._assert_detail",
         "rendering.generators.rest_assured._expectations"),
        "the declared body type. Empty means NO body — `ResponseEntity<Void>` is "
        "an answer, not a recovery failure, and the emitter asserts an empty body "
        "rather than skipping the check",
        affects_artefact=True,
        concerns=(RESPONSE,)),
    ModelFact(
        "Transition", "guard_wording", (PROSE,),
        ("rendering.test_case.render", "rendering.payload._step_payload",
         "rendering.generators._data.guard_lines"),
        "the guard in business language. The raw guard is never overwritten — "
        "this is a rendering of it (D-8) — and both are put in front of a reader, "
        "because the wording is what a reviewer approved and the expression is "
        "what the code evaluates",
        # Display data, not evidence: the raw `guard` is the auditable fact and
        # is already hashed. Rewording a condition must not revoke approval.
        affects_artefact=False,
        concerns=(PRESENTATION,)),
    ModelFact(
        "Transition", "data_requirements", (PROSE,),
        ("mbt.techniques.analyse_constraints", "mbt.criteria._boundary_coverage",
         "rendering.payload.build_payload", "rendering.generators._data.lines"),
        "GD-3's declared constraints an input must violate to reach a rejection. "
        "These are why 164 constrained fields stay TEST DATA rather than becoming "
        "164 transitions: `analyse_constraints` turns each into boundary and "
        "partition cases without adding a model element (P-1a). A constraint "
        "arrives as bare annotation text, so it names no field — `length = 65` is "
        "stated and which field's length is not, which is a recovery limit and "
        "not something to guess (M-9)",
        # Not evidence: these ride on a rejection whose guard is already hashed,
        # and a constraint changing without the guard changing is a re-extraction
        # detail rather than a behaviour change.
        affects_artefact=False,
        concerns=(DATA,)),
    ModelFact(
        "Transition", "checks", (PROSE,),
        ("mbt.criteria.guard_conditions", "rendering.payload._step_payload",
         "rendering.generators._data.guard_lines"),
        "one condition, at one line, in its evaluation order — a test data "
        "requirement, not documentation: if check 1 short-circuits, no fixture "
        "reaches check 3 without satisfying check 1 first. The expressions used "
        "to reach the payload only inside `target_key`, which is an identity",
        # **Evidence, and now safely hashable.** A change to the ordering changes
        # what a fixture must satisfy. This was held out of the approval evidence
        # while `checks` arrived only from `graph_loader.CHECKS_CYPHER` — hashing
        # it then would have given one logical model two fingerprints depending on
        # which loader saw it. `mbt.model`'s shared codec carries it through a
        # model file too, so the condition that held it back is gone.
        affects_artefact=True,
        concerns=(BEHAVIOUR, DATA)),

    # -- State ------------------------------------------------------------
    ModelFact(
        "State", "id", (GATE,),
        ("mbt.model.Model.reindex", "mbt.path_generation.generate"),
        "the machine cannot be indexed or walked",
        concerns=(IDENTITY,)),
    ModelFact(
        "State", "name", (PROSE,),
        ("rendering.test_case.observable_result", "rendering.payload._step_payload",
         "rendering.generators.playwright._step"),
        "what the case says it reached. A case is a transition AND the state it "
        "lands in — without the target the artefact says what to do and never "
        "what makes it right, and a reader could not tell one 200 from another",
        concerns=(IDENTITY, PRESENTATION)),
    ModelFact(
        "State", "surface", (GATE,),
        ("rendering.payload._act_detail", "rendering.generators.select_for"),
        "which emitter a case routes to, and which branch of the act detail applies",
        concerns=(BEHAVIOUR,)),
    ModelFact(
        "State", "is_initial", (GATE,),
        ("mbt.path_generation.generate",),
        "P-8: paths start only at states a tester can establish from nothing",
        concerns=(BEHAVIOUR,)),
    ModelFact(
        "State", "lifecycle_state", (GATE,),
        ("mbt.cli._require_approved",),
        "the G1 gate's outstanding list",
        concerns=(REVIEW,)),
    ModelFact(
        "State", "condition", (PROSE,),
        ("rendering.test_case.precondition_of", "rendering.payload._act_detail",
         "rendering.generators.playwright._step"),
        "what the page presents, which is what a UI tester actually asserts",
        concerns=(RESPONSE,)),
)


# ---------------------------------------------------------------------------
# Owed — generation does NOT read it, and that is a gap
# ---------------------------------------------------------------------------
#
# Not folded into NOT_CONSUMED, because that would record a lie: spec §7.4a
# already promises these. Not folded into CONSUMED, because they are not read at
# all and the suite would be red on day one. `STAGED_OUT` is the codebase's own
# answer to a known gap — name it in code with its trigger, and assert the
# naming — and this is that, applied to fields.

OWED: dict[tuple[str, str], str] = {}


# ---------------------------------------------------------------------------
# Not consumed — unread by generation on purpose, with the trigger
# ---------------------------------------------------------------------------

NOT_CONSUMED: dict[tuple[str, str], str] = {
    # **The five that went with the generators.** Each reached `payload` and
    # `artefact` and nothing else, so removing those destinations left them read
    # by nobody. Recorded rather than deleted: the model still carries them, and
    # "carried but unread" is the state this table exists to make visible.
    # `GENERATOR_ONLY` above is the same list, addressable in one place.
    ("Transition", "id"):
        "the stable identity a generated method was named from. Still the key "
        "everything joins on; nothing RENDERS it. Returns if a case must print "
        "the transition it came from.",
    ("Transition", "security"):
        "the declared scheme, which became an auth comment in the emitted "
        "source. `auth_facts` reads SecurityScheme from the graph instead. "
        "Returns when a rendered case states what the caller must present.",
    ("Transition", "media_types"):
        "the content types a runner set as headers. Returns when a case must "
        "distinguish two outcomes differing only by representation.",
    ("Transition", "guard_anchor"):
        "`file:line@commit` for the guard, written into the emitted test as a "
        "comment. Still landed as evidence (T-9a) and shown by the review UI; it "
        "no longer reaches a case. Returns when prose cites its source line.",
    ("State", "page"):
        "which page a ui state belongs to, used to pick a Playwright locator. "
        "Still carried for identity and display. Returns when a ui case names "
        "the screen it acts on.",
    ("Transition", "source_state_unresolved"):
        "§5.8's honesty flag, for review and reporting rather than generation. "
        "Read by `server.get_model` and `landing`. Returns when a case must say "
        "its starting point was not recovered.",
    ("Transition", "outcome_source"):
        "whether the outcome was constructed in code or only declared on an "
        "annotation. Read by `read.py`. Returns when a case should be graded by "
        "how its expectation was arrived at.",
    ("Transition", "guard_claim"):
        "how the guard was arrived at (`contract.LINK_*`). Nothing reads it back "
        "today. Returns when a rendered case distinguishes a guard recovered from "
        "a branch from one derived from four annotations.",
    ("Transition", "name_tier"):
        "which tier of X-7's cascade produced the name. Read by "
        "`identity.matching` and `synthesis`, which is where naming is decided. "
        "Returns when generation varies by naming confidence.",
    ("Transition", "guard_tier"):
        "as `name_tier`, for the guard. Read by `specgen.specification` and "
        "`read.py`. Returns when a case is graded by its guard's provenance.",
    ("Transition", "evidence"):
        "`(label, node_id)` pairs that `landing` turns into edges (D-14). "
        "Write-only on this path by design — provenance belongs in the graph, not "
        "in a test. Returns when an artefact must cite the endpoint it came from.",
    ("State", "name_tier"):
        "as `Transition.name_tier`. Read by `identity.matching`.",
}


# Properties, not dataclass fields — enumerated so the closure check does not
# silently miss `is_callable`, which `validation.check_callability` depends on.
DERIVED: frozenset[str] = frozenset({
    "is_callable", "is_generatable", "exclusion_reason",
})

# Written by landing but not model facts: identity, provenance and routing.
INFRASTRUCTURE: frozenset[str] = frozenset({
    "id", "source_episode_id", "name", "model_id", "functional_areas",
    "surface", "extraction_method", "lifecycle_state",
})


# Graph properties `landing` writes that correspond to no model field and that
# nothing reads. Named rather than tolerated: an unclassified property is how a
# node grows to 26 columns without anyone deciding it should.
#
# Removal is the irreversible direction — stop writing one and the next
# `rebuild_graph.sh` produces a graph without it — so these are recorded here and
# removed deliberately, after the reader set is settled. `test_generation_contract`
# asserts they are still unread, so a reader appearing is a failing test telling
# you to reclassify rather than a silent contradiction.
UNREAD_GRAPH_PROPERTIES: dict[str, str] = {}


# Graph properties with no dataclass field behind them. They are on the node a
# reader opens, so leaving them unclassified would answer the question for two
# thirds of what Browser shows.
GRAPH_CONCERNS: dict[str, tuple[str, ...]] = {
    "id": (IDENTITY,),
    "model_id": (IDENTITY,),
    "name": (IDENTITY, PRESENTATION),
    "functional_areas": (IDENTITY,),
    "surface": (BEHAVIOUR,),
    "lifecycle_state": (REVIEW,),
    "source_episode_id": (PROVENANCE,),
    "extraction_method": (PROVENANCE,),
    # **Classified here since the generators left.** Their concerns used to come
    # from their `ModelFact`; the facts moved to `NOT_CONSUMED` when `payload`
    # and `artefact` were removed, and a property on the node still has to say
    # what it is for — "generation does not consume it" is no excuse, because it
    # is landed either way.
    "security": (REQUEST,),
    "media_types": (RESPONSE,),
    "guard_anchor": (PROVENANCE,),
    # A `ui` State's page. It picked a Playwright locator and now picks nothing,
    # but it is still how a reader tells two states on different screens apart.
    "page": (IDENTITY, PRESENTATION),
    # `landing` writes these under names that differ from the dataclass field.
    "guard_expression": (BEHAVIOUR, DATA),
    "inputs_json": (REQUEST, DATA),
    "security_json": (REQUEST,),
    # Not consumed by generation, but on the node a reader opens — and a reader
    # asking "which of these is the call?" is owed an answer for all 25, not for
    # the subset generation happens to use.
    "source_state_unresolved": (PROVENANCE,),
    "outcome_source": (PROVENANCE,),
    "guard_claim": (PROVENANCE,),
    "evidence": (PROVENANCE,),
    "name_tier": (PRESENTATION,),
    "guard_tier": (PRESENTATION,),
}

# Scoped, because a grouping for one element must not list the other's
# properties. `page` and `condition` are State facts and already carry their own
# concerns; `guard_*` and `evidence` land only on a transition.
ELEMENT_ONLY: dict[str, frozenset[str]] = {
    "Transition": frozenset({
        "guard_expression", "guard_anchor", "guard_claim", "guard_tier",
        "guard_wording", "inputs_json", "security_json", "input_count",
        "requires_body", "outcome_source", "source_state_unresolved",
        "evidence", "extraction_method"}),
    "State": frozenset(),
}


ALL_PREFIXES = (CALL_PREFIX, BEHAVIOUR_PREFIX, PAGE_PREFIX, UI_PREFIX,
                EPISTEMIC_PREFIX)


def unprefixed(prop: str) -> str:
    """A property name with its concern prefix removed, if it has one."""
    for prefix in ALL_PREFIXES:
        if prop.startswith(prefix):
            return prop[len(prefix):]
    return prop


def concerns_of(element: str, prop: str) -> tuple[str, ...]:
    """What one property is for, by either its bare or its prefixed name.

    The question this exists for: opening an `ApiCall` shows 25 properties in one
    flat table and nothing says which describe the CALL and which the BEHAVIOUR.
    Accepts both spellings because a caller may hold either — the dataclass field
    is `trigger` and the node property is `c_trigger`.
    """
    found = fact(element, prop)
    if found is not None and found.concerns:
        return found.concerns
    for candidate in CONSUMED:
        if candidate.element == element and candidate.landed_as == prop:
            return candidate.concerns
    return GRAPH_CONCERNS.get(unprefixed(prop), GRAPH_CONCERNS.get(prop, ()))


def properties_by_concern(element: str = "Transition") -> dict[str, list[str]]:
    """Every property of one element, grouped by what it is for.

    A property serving two concerns appears under both — `trigger` names the
    interaction AND is where the curl's method and path are split from, and
    hiding that to keep the buckets tidy would lose the useful half.
    """
    grouped: dict[str, list[str]] = {c: [] for c in CONCERNS}
    seen: dict[str, tuple[str, ...]] = {}
    for f in facts_for(element):
        seen[f.landed_as] = f.concerns
    for prop, concerns in GRAPH_CONCERNS.items():
        owner = next((e for e, props in ELEMENT_ONLY.items() if prop in props), None)
        if owner is not None and owner != element:
            continue
        # Keyed by the name on the NODE, which is what a reader is holding.
        seen.setdefault(graph_name(element, prop), concerns)
    for prop, concerns in seen.items():
        for concern in concerns:
            grouped[concern].append(prop)
    return {c: sorted(props) for c, props in grouped.items() if props}


def facts_for(element: str) -> tuple[ModelFact, ...]:
    return tuple(f for f in CONSUMED if f.element == element)


def fact(element: str, field: str) -> ModelFact | None:
    return next((f for f in CONSUMED
                 if f.element == element and f.field == field), None)


def asserted_fields(element: str = "Transition") -> tuple[str, ...]:
    """Fields a generated test asserts, so a change to one is evidence.

    **The rule this exists to make executable.** E-8/N-14 say a decision made
    against different evidence must not be applied. What a generated test
    asserts IS evidence — so the moment a fact reaches an emitted assertion, a
    change to it has to revoke the approval that was recorded before it changed.
    Kept here rather than hand-listed in `identity.matching` so the two cannot
    say different things about the same question.

    `source_fingerprint` deliberately does NOT derive from this: a hash whose
    input silently changes when somebody edits a declaration would restale every
    recorded decision with no visible cause. It hand-lists, and
    `test_generation_contract` asserts the two agree.
    """
    return tuple(f.field for f in CONSUMED
                 if f.element == element and f.affects_artefact)


def incomplete() -> tuple[ModelFact, ...]:
    """Consumed facts that do not reach everywhere they should."""
    return tuple(f for f in CONSUMED if not f.is_complete)


def describe_concerns(element: str = "Transition") -> str:
    """Every property of one element, grouped by what it is for.

    Answers the question a node in Neo4j Browser cannot: of these 25 properties,
    which describe the CALL and which describe the BEHAVIOUR.
    """
    grouped = properties_by_concern(element)
    width = max((len(p) for props in grouped.values() for p in props), default=10)
    lines = [f"{element} properties, by what each is for ({CONTRACT_VERSION})", ""]
    for concern in CONCERNS:
        props = grouped.get(concern)
        if not props:
            continue
        tag = ("  <- how to CALL it" if concern in CURL_CONCERNS
               else "  <- what it DOES" if concern in MODEL_CONCERNS else "")
        lines.append(f"  {concern.upper()}{tag}")
        for prop in props:
            also = [c for c in concerns_of(element, prop) if c != concern]
            note = f"   (also {', '.join(also)})" if also else ""
            lines.append(f"    {prop:{width}}{note}")
        lines.append("")
    lines += [
        "  A property under two concerns is doing two jobs — `trigger` names the",
        "  interaction and is where the curl's method and path are split from.",
        "  PROVENANCE and PRESENTATION are neither: they say where a fact came",
        "  from and how it is worded, and are what you skip when asking either",
        "  question.",
    ]
    return "\n".join(lines)


def describe() -> str:
    """The contract, as a reader would want it."""
    lines = [f"Generation contract ({CONTRACT_VERSION})", ""]
    for element in ("Transition", "State"):
        lines.append(f"  {element.upper()}")
        for f in facts_for(element):
            flag = "" if f.is_complete else "  <- INCOMPLETE"
            lines.append(f"    {f.field:24} {'+'.join(f.reaches):24}{flag}")
            if not f.is_complete:
                lines.append(f"        owed: {f.owed}")
        lines.append("")
    lines.append("  OWED — held by the model, not read by generation")
    for (element, field), why in sorted(OWED.items()):
        lines.append(f"    {element}.{field}")
        lines.append(f"        {why}")
    lines.append("")
    lines.append("  NOT CONSUMED — unread on purpose, each with its trigger")
    for (element, field), why in sorted(NOT_CONSUMED.items()):
        lines.append(f"    {element}.{field}")
        lines.append(f"        {why}")
    return "\n".join(lines)
