"""
Pure model types for the MBT engine (application spec §2, §6).

Deliberately database-free. The engine operates on these dataclasses, never on a
Neo4j session, for the same reason `requirement_landing.py` splits its planner
from its writer: the interesting logic becomes provable without a container.

A `Model` here is one `<journey>-<surface>` machine (spec M-1) -- a
user-perspective state machine, not a data-lifecycle one (M-3). Nothing in this
module knows which source produced the model; that is spec F-29, and it is why
the same engine serves hand-authored, AC-mined and code-extracted models alike.
"""
from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, field, fields

# Transition.implementation_status values. `planned` behaviour is excluded from
# coverage because it is not a gap -- it does not exist yet (spec P-11).
IMPLEMENTED = "implemented"
PLANNED = "planned"

# lifecycle_state values (spec §8.6). Generation reads ONLY `Approved` elements
# (spec D-10); everything else is excluded with its own distinct reason, because
# "not yet reviewed" and "sources disagree" are different facts.
#
# The default is QUARANTINE, not APPROVED: every model source produces candidates
# (spec S-4), and a default of "approved" would mean a carelessly-constructed
# element silently earns authority it was never granted.
QUARANTINE = "Quarantine"
APPROVED = "Approved"
DISPUTED = "Disputed"
REJECTED = "Rejected"
DEPRECATED = "Deprecated"

# Transition.outcome_source values. Whether the response this transition produces
# was seen being BUILT, or only DECLARED on an annotation.
#
# The distinction has to survive into the graph, because a `@ApiResponse` can
# simply be wrong -- a copy-pasted annotation declares a status the endpoint
# cannot produce, and the resulting path is one nobody can walk. That is a real
# finding about the codebase and the model is right to hold it (a model is every
# possible user path, not a transcript of what the code happens to do), but a
# reviewer must be able to see which kind of claim they are approving.
CONSTRUCTED = "constructed"
DECLARED = "declared"


@dataclass(frozen=True)
class State:
    """One observable situation on one surface (spec M-3).

    `is_initial` marks a state a tester can establish from nothing. Paths start
    only at initial states (spec P-8) -- a test whose precondition cannot be
    established is not executable.
    """

    id: str
    name: str
    surface: str = "api"
    is_initial: bool = False
    lifecycle_state: str = QUARANTINE
    # Web-surface detail. A `ui` state is a screen, mode or message shown (M-2),
    # so it belongs to a page and names the condition that page is in --
    # `MetricWorkspacePage` / `summary=error`. Empty on the API surface, where a
    # state is a response condition and there is no page to belong to.
    page: str = ""
    condition: str = ""
    # X-8, as above. A state named `MetricGetActionByIdNoContent204` and one a
    # reviewer renamed to "the metric is not found" are different kinds of claim.
    name_tier: str = ""


@dataclass(frozen=True)
class GuardCheck:
    """One condition that selected an outcome, as recovered.

    Ordered, anchored, and classified. A bare guard string is none of those.
    """

    expression: str
    order: int = 0
    dimension_class: str = ""
    # `file:line@commit` — T-9a: a condition a reviewer cannot trace is a claim
    # they must take on trust.
    anchor: str = ""


@dataclass(frozen=True)
class Transition:
    """One interaction: trigger, guard, source and target state.

    `trigger` and `guard` are properties, never separate entities (spec M-11).
    `guard` is preserved verbatim as recovered and is a *test data requirement*,
    not a solved value (spec M-8, M-9) -- this module never attempts to satisfy it.
    """

    id: str
    source: str
    trigger: str
    target: str
    guard: str = ""
    implementation_status: str = IMPLEMENTED
    lifecycle_state: str = QUARANTINE
    # What a caller must supply to fire this transition, and what it must prove
    # about itself (spec §7.4). A `trigger` of "POST /metric" says which door to
    # knock on and nothing about what to bring; without these a rendered case can
    # assert a status but can never construct the request.
    #
    # Requirements, never values (M-9): each entry states a condition on the data.
    inputs: tuple = ()
    security: tuple = ()
    # `file:line@commit` for the guard's own source (spec §8.5, T-9a). A guard a
    # reviewer cannot trace back to a line is a claim they have to take on trust.
    guard_anchor: str = ""
    # The response this transition produces. Held here rather than read out of the
    # target state's name, because the two are different things: 201 is what the
    # caller receives, and "the resource now exists" is the situation the system
    # is left in. Conflating them is what forced every outcome to be its own
    # state and made the machine a star.
    outcome_status: int | None = None
    # Spec §5.8: a transition may have no recoverable source state. Saying so is
    # required; giving it a guessed one is prohibited.
    source_state_unresolved: bool = False
    # Whether the outcome was constructed in code or only declared on an
    # annotation (see CONSTRUCTED/DECLARED above).
    outcome_source: str = CONSTRUCTED
    # How the guard itself was arrived at -- `contract.LINK_*`. A guard recovered
    # from a real branch and a guard derived from four annotations are both
    # legitimate and are not the same claim, and the rendered case says which.
    guard_claim: str = ""
    # GD-3's variants: the declared constraints an input must violate to reach a
    # rejection (`@NotNull`, `@Size(max=64)`), verbatim. These are why 164
    # constrained fields stay TEST DATA rather than becoming 164 transitions --
    # a technique turns each into cases (P-1a) without adding a model element.
    #
    # Requirements, never values (M-9): the model states what the data must
    # violate; a person or a factory decides what to actually send.
    data_requirements: tuple = ()
    # The expected response, alongside `outcome_status`. `response_body` is the
    # declared body type (`PageDto<ProjectDto>`), **empty meaning no body** --
    # `ResponseEntity<Void>` is a real answer, not a recovery failure. Without
    # these a generated case can assert a status and never check what came back,
    # which is most of what an API test is for.
    response_body: str = ""
    media_types: tuple = ()
    # X-8: a name and a guard each record which tier of X-7's cascade produced
    # them. Without this the question "which of these still read as
    # implementation detail" is not answerable by a query, only by eyeballing
    # 206 nodes -- and the whole point of the cascade is that it can be driven.
    name_tier: str = ""
    # The guard said in business language, and the tier that said it. The raw
    # `guard` is never overwritten: it is the auditable fact, and this is a
    # rendering of it (D-8's "name is display data", applied to conditions).
    guard_wording: str = ""
    guard_tier: str = ""
    # **What this transition was derived from** (spec D-14): `(label, node_id)`
    # pairs into the evidence layer, which landing turns into real edges.
    #
    # Provenance used to be a `source_episode_id` property naming the ingest, and
    # an ingest cannot say WHICH endpoint, outcome or field. Carried as ids
    # rather than objects so this module stays database-free and the pure model
    # keeps its meaning.
    evidence: tuple = ()
    # The `Check` nodes reached by `DERIVED_FROM -> DeclaredOutcome -> GUARDED_BY`.
    #
    # **Why this exists when `guard` already does.** `guard` is one string. A
    # `Check` is one condition, at one line, with the position it holds in the
    # evaluation sequence — and that ordering is a test data requirement, not
    # trivia: if check 1 short-circuits, no fixture reaches check 3 without
    # satisfying check 1 first. Splitting the string cannot recover it.
    #
    # `GUARDED_BY` was written by landing for a long time and read by nothing;
    # this field, and `_guard_coverage` below it, are what make it a fact the
    # engine uses rather than a fact the engine stores.
    checks: tuple = ()

    @property
    def is_callable(self) -> bool:
        """Whether enough is known to actually issue this request.

        A transition that writes (POST/PUT/PATCH) and has no recovered inputs is
        **not** callable, and that is a finding rather than a property of the
        endpoint: real write endpoints take a body, so recovering none means the
        extraction did not see it (X-13). Reporting it as callable would let a
        test case claim it exercises a write it cannot actually perform.
        """
        verb = (self.trigger or "").split(None, 1)[0].upper()
        if verb in ("POST", "PUT", "PATCH"):
            return bool(self.inputs)
        return True

    @property
    def is_generatable(self) -> bool:
        """Whether this transition may take part in generation at all.

        Spec D-10: generation reads only `Approved` elements. Everything else is
        excluded, and `exclusion_reason` says which of several distinct reasons
        applies -- "not yet reviewed", "sources disagree" and "not built yet" are
        different facts and must never be collapsed into one number (spec P-12).
        """
        return (
            self.implementation_status == IMPLEMENTED
            and self.lifecycle_state == APPROVED
        )

    @property
    def exclusion_reason(self) -> str | None:
        if self.implementation_status == PLANNED:
            return "excluded_planned"
        if self.lifecycle_state == DISPUTED:
            return "excluded_disputed"
        if self.lifecycle_state == REJECTED:
            return "excluded_rejected"
        if self.lifecycle_state != APPROVED:
            return "excluded_unapproved"
        return None


@dataclass
class Model:
    """One `<journey>-<surface>` state machine.

    Indexes are built once at construction. Every accessor returns results in a
    deterministic order -- spec P-7 requires byte-identical generation across
    runs, and unordered iteration is the usual way that guarantee is lost.
    """

    id: str
    states: dict[str, State] = field(default_factory=dict)
    transitions: dict[str, Transition] = field(default_factory=dict)

    _outgoing: dict[str, list[str]] = field(default_factory=dict, repr=False)
    _incoming: dict[str, list[str]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.reindex()

    def reindex(self) -> None:
        self._outgoing = {sid: [] for sid in self.states}
        self._incoming = {sid: [] for sid in self.states}
        for tid in sorted(self.transitions):
            t = self.transitions[tid]
            # A transition referencing an unknown state is a model defect, not
            # something to silently tolerate: it would silently shrink coverage.
            if t.source not in self.states:
                raise ValueError(f"{t.id}: source state {t.source!r} not in model {self.id}")
            if t.target not in self.states:
                raise ValueError(f"{t.id}: target state {t.target!r} not in model {self.id}")
            self._outgoing[t.source].append(tid)
            self._incoming[t.target].append(tid)

    # -- ordered accessors ------------------------------------------------

    def state_ids(self) -> list[str]:
        return sorted(self.states)

    def transition_ids(self) -> list[str]:
        return sorted(self.transitions)

    def outgoing(self, state_id: str, generatable_only: bool = True) -> list[Transition]:
        out = [self.transitions[tid] for tid in self._outgoing.get(state_id, [])]
        if generatable_only:
            out = [t for t in out if t.is_generatable]
        return out

    def incoming(self, state_id: str, generatable_only: bool = True) -> list[Transition]:
        inc = [self.transitions[tid] for tid in self._incoming.get(state_id, [])]
        if generatable_only:
            inc = [t for t in inc if t.is_generatable]
        return inc

    def initial_state_ids(self) -> list[str]:
        return sorted(sid for sid, s in self.states.items() if s.is_initial)

    def generatable_transitions(self) -> list[Transition]:
        return [self.transitions[tid] for tid in self.transition_ids()
                if self.transitions[tid].is_generatable]

    def excluded_transitions(self) -> list[Transition]:
        return [self.transitions[tid] for tid in self.transition_ids()
                if not self.transitions[tid].is_generatable]

    # -- approval (spec G1, D-10) ----------------------------------------

    def unapproved_elements(self) -> list[tuple[str, str, str]]:
        """Every element still awaiting a decision, as (kind, id, lifecycle_state).

        Reported rather than counted: G1 blocks generation on an unapproved
        model, and a reviewer needs to know *which* elements to look at.

        **Awaiting a decision, not merely un-approved.** A `Rejected`
        transition has been decided -- rejecting an extraction artefact is the
        correct action for it -- and `exclusion_reason` already keeps it out of
        generation as `excluded_rejected`. Counting it here left no decision
        that could clear the gate: approving contradicts the review, deferring
        leaves it, so a single rejection blocked a journey until re-extraction.

        **States are deliberately not treated the same way.** `exclusion_reason`
        and `is_generatable` are properties of `Transition`; `State` has
        neither, and `is_generatable` never checks a transition's endpoints. An
        approved transition into a rejected state would generate a path running
        through it, and G1 is the only thing standing there.
        """
        out = []
        for sid in self.state_ids():
            state = self.states[sid]
            if state.lifecycle_state != APPROVED:
                out.append(("state", sid, state.lifecycle_state))
        for tid in self.transition_ids():
            transition = self.transitions[tid]
            if transition.implementation_status == PLANNED:
                continue  # not a gap; it does not exist yet (spec P-11)
            if transition.lifecycle_state == REJECTED:
                continue  # decided, not pending -- `exclusion_reason` excludes it
            if transition.lifecycle_state != APPROVED:
                out.append(("transition", tid, transition.lifecycle_state))
        return out

    @property
    def is_approved(self) -> bool:
        return not self.unapproved_elements()


# --------------------------------------------------------------------------
# The model-file codec
# --------------------------------------------------------------------------
#
# **Why this exists.** Reading a model file was three independently
# hand-maintained field lists — `mbt.cli.read_source`, `model_sources.sources`
# and `mbt.cli.cmd_ac_mine`'s writer — each naming a subset and each dropping
# whatever it forgot. Four separate defects came out of that in one sitting:
# `response_body` dropped turned "no body" into a false assertion; `guard_wording`
# dropped showed a reader the code's expression where the model held the sentence
# a reviewer approved; `page` and `condition` dropped left a UI case with nothing
# to check; `data_requirements` dropped silently shrank what a boundary-coverage
# run covered. Each was patched field by field, which fixes the instance and
# leaves the mechanism.
#
# Driven by `dataclasses.fields`, so a field added to `Transition` is carried
# without anybody remembering to add it in three places — the discipline
# `test_human_facts_survive` already applies to human facts, applied to the file
# boundary.
#
# **`lifecycle_state` is deliberately NOT carried.** Everything a source emits
# lands at Quarantine (S-4); lifecycle is a human fact and lives in the
# review-state file (I-14). It is a keyword argument here so the rule stays
# visible rather than being swallowed by "carry everything".

# Fields whose JSON form is not their Python form.
_PAIR_TUPLES = frozenset({"evidence"})      # [["Endpoint", "ep:..."]] -> ((..),)
_CHECK_TUPLES = frozenset({"checks"})       # [{...}] -> (GuardCheck(...),)


def _decode(name: str, declared: str, value):
    """One field, from its JSON form to its dataclass form."""
    if name in _PAIR_TUPLES:
        return tuple(tuple(pair) for pair in value or ())
    if name in _CHECK_TUPLES:
        return tuple(v if isinstance(v, GuardCheck) else GuardCheck(**v)
                     for v in value or ())
    if declared == "tuple":
        return tuple(value or ())
    if declared == "bool":
        return bool(value)
    if declared == "int | None":
        return None if value is None else int(value)
    return value if value is not None else ""


def _encode(name: str, value):
    """One field, from its dataclass form to something `json.dumps` accepts."""
    if name in _CHECK_TUPLES:
        return [asdict(c) for c in value or ()]
    if isinstance(value, tuple):
        return [list(v) if isinstance(v, tuple) else v for v in value]
    return value


def _from_dict(cls, data: dict, *, lifecycle_state: str):
    kwargs = {}
    for f in fields(cls):
        if f.name == "lifecycle_state":
            kwargs[f.name] = lifecycle_state
            continue
        if f.name in data:
            kwargs[f.name] = _decode(f.name, str(f.type), data[f.name])
    return cls(**kwargs)


def _to_dict(instance) -> dict:
    """Every field that is not at its default, so a written file stays readable.

    `lifecycle_state` is omitted: a model file holds machine facts, and writing a
    lifecycle into one would invite a source to assert a decision (S-4).
    """
    out = {}
    for f in fields(instance):
        if f.name == "lifecycle_state":
            continue
        value = getattr(instance, f.name)
        default = f.default if f.default is not MISSING else None
        if f.default is MISSING or value != default:
            out[f.name] = _encode(f.name, value)
    return out


def state_from_dict(data: dict, *, lifecycle_state: str = QUARANTINE) -> State:
    """One `State` from its file form. `name` falls back to `id` (X-10)."""
    return _from_dict(State, {"name": data.get("id", ""), **data},
                      lifecycle_state=lifecycle_state)


def transition_from_dict(data: dict, *, lifecycle_state: str = QUARANTINE) -> Transition:
    """One `Transition` from its file form, carrying every declared field."""
    return _from_dict(Transition, data, lifecycle_state=lifecycle_state)


def state_to_dict(state: State) -> dict:
    return _to_dict(state)


def transition_to_dict(transition: Transition) -> dict:
    return _to_dict(transition)
