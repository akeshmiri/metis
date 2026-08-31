"""
The generation contract (`rendering/contract.py`) — enforced, not documented.

**What these defend.** `Transition` grew fields nothing on the generation path
reads, while facts the model holds died before the artefact. Both symptoms have
one cause: nothing stated what generation takes. A contract that is only prose
would drift the same way, so every claim in it is checked here by putting a
sentinel in one field and following it through `render`. It followed it through
`build_payload` and `emit` too, until those were removed: Métis states what must
be verified and no longer emits an implementation.

**Value-travel, not source scanning.** "Read by nobody" is a fact about runtime.
A grep for `inputs` finds `payload.py:73` and concludes the field is consumed;
following a sentinel shows it arrives as a data-requirement condition and never
as a request body. Three entries were classified wrongly by reading the code and
corrected by measurement before this file existed.

Free to run: no Joern, no Neo4j, no network.
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from metis_mcp.mbt import graph_loader
from metis_mcp.mbt.model import APPROVED, GuardCheck, Model, State, Transition
from metis_mcp.mbt.path_generation import generate
from metis_mcp.rendering import contract
from metis_mcp.rendering.contract import (
    CONSUMED, DERIVED, GATE, GENERATOR_ONLY, INFRASTRUCTURE, NOT_CONSUMED, OWED,
    PROSE, UNREAD_GRAPH_PROPERTIES)
from metis_mcp.rendering.test_case import render

SENTINEL = "ZQXSENTINEL"
ELEMENTS = {"Transition": Transition, "State": State}

# Fields a sentinel cannot be put in: they are identity, or an enum the engine
# branches on, so a sentinel value produces a broken model rather than a
# measurement. Their consumption is structural — nothing generates without them —
# and is asserted by every other test in the suite.
STRUCTURAL = {
    ("Transition", "id"), ("Transition", "source"), ("Transition", "target"),
    ("Transition", "implementation_status"), ("Transition", "lifecycle_state"),
    ("State", "id"), ("State", "surface"), ("State", "is_initial"),
    ("State", "lifecycle_state"),
}


# ---------------------------------------------------------------------------
# The sentinel harness
# ---------------------------------------------------------------------------

def _tuple_valued(field: str, sentinel: str):
    """A sentinel shaped like the field's real contents.

    A bare string in `inputs` would be read as a parameter record and produce
    nothing; the sentinel has to travel the way a real value does or the
    measurement is meaningless.
    """
    return {
        "inputs": ({"name": sentinel, "location": "body",
                    "type_name": "com.example." + sentinel, "required": True},),
        "security": ({"scheme": sentinel},),
        "evidence": (("Endpoint", sentinel),),
        "checks": (GuardCheck(expression=sentinel, order=1),),
    }.get(field, (sentinel,))


# A fact that only travels under a particular criterion. `checks` is read by
# `criteria.guard_conditions`, which only runs for guard coverage.
CRITERION = {
    ("Transition", "checks"): "guard-coverage",
    # GD-3's constraints become cases only under boundary analysis — that IS the
    # technique that consumes them.
    ("Transition", "data_requirements"): "boundary-coverage",
}


def _model_with(element: str, field: str, sentinel: str, *, surface: str) -> Model:
    """An approved two-state model carrying `sentinel` in exactly one field."""
    trigger = "POST /thing" if surface == "api" else "click thing"
    tkw = dict(id="t1", source="A", target="B", trigger=trigger, guard="g_ok",
               lifecycle_state=APPROVED)
    a = dict(id="A", name="A", surface=surface, is_initial=True, lifecycle_state=APPROVED)
    b = dict(id="B", name="B", surface=surface, lifecycle_state=APPROVED)

    # `observable_result` returns the target's NAME when no status was recovered
    # (test_case.py:181), so a probe for the body half must supply one or it
    # measures the fallback instead of the field.
    if field == "response_body":
        tkw["outcome_status"] = 200
    # `precondition_of` reads the SOURCE state's condition and `_act_detail` the
    # TARGET's, so a probe on one state alone sees half the readers.
    if element == "State" and field == "condition":
        a["condition"] = sentinel

    if element == "Transition":
        declared = {f.name: f for f in dataclasses.fields(Transition)}
        if field == "outcome_status":
            tkw[field] = 599
        elif isinstance(declared[field].default, tuple):
            tkw[field] = _tuple_valued(field, sentinel)
        else:
            tkw[field] = sentinel
    else:
        b[field] = sentinel
        if field == "page":
            # `_act_detail` carries `page` only alongside a condition
            # (payload.py:106), so a probe without one measures the wrong thing.
            b.setdefault("condition", "some condition")

    return Model(id="probe", states={"A": State(**a), "B": State(**b)},
                 transitions={"t1": Transition(**tkw)})


def _travel(element: str, field: str, *, surface: str, criterion: str = ""):
    """Where a sentinel in `field` actually arrives. Returns a set of destinations."""
    model = _model_with(element, field, SENTINEL, surface=surface)
    criterion = criterion or CRITERION.get((element, field), "all-transitions")
    result = generate(model, criterion, 3)
    if not result.paths:
        return set()

    rendered = render(model, result.paths)
    needle = "599" if field == "outcome_status" else SENTINEL

    arrived = set()
    if needle in json.dumps([dataclasses.asdict(c) for c in rendered.cases], default=str):
        arrived.add(PROSE)

    return arrived


def _surface_for(fact) -> str:
    """Which surface exercises this fact. A UI-only reader is not measurable on
    an API model, and vice versa."""
    if fact.element == "State" and fact.field in ("condition", "page"):
        return "ui"
    if "playwright" in " ".join(fact.consumers) and "rest_assured" not in " ".join(fact.consumers):
        return "ui"
    return "api"


# ---------------------------------------------------------------------------
# T1 — closure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("element", sorted(ELEMENTS))
def test_every_field_is_classified(element):
    """Adding a field to `mbt/model.py` without deciding whether generation
    consumes it fails here rather than passing unnoticed. Enumerated from
    `dataclasses.fields`, never hand-listed — the idiom
    `test_human_facts_survive.py:92` already uses."""
    declared = {f.name for f in dataclasses.fields(ELEMENTS[element])}
    classified = (
        {f.field for f in CONSUMED if f.element == element}
        | {field for (el, field) in OWED if el == element}
        | {field for (el, field) in NOT_CONSUMED if el == element})
    assert declared == classified, (
        f"unclassified: {declared - classified}; "
        f"named but not a field: {classified - declared}")


@pytest.mark.parametrize("element", sorted(ELEMENTS))
def test_no_field_is_in_two_buckets(element):
    consumed = {f.field for f in CONSUMED if f.element == element}
    owed = {field for (el, field) in OWED if el == element}
    unread = {field for (el, field) in NOT_CONSUMED if el == element}
    assert not (consumed & owed) and not (consumed & unread) and not (owed & unread)


def test_derived_names_only_real_properties():
    """`is_callable` is not a dataclass field, so T1 cannot see it — and
    `validation.check_callability` depends on it."""
    for name in DERIVED:
        attr = getattr(Transition, name, None)
        assert isinstance(attr, property), f"{name} is not a property of Transition"


def test_every_fact_says_what_a_case_loses_without_it():
    for fact in CONSUMED:
        assert fact.why.strip(), f"{fact.element}.{fact.field}"
    for why in list(OWED.values()) + list(NOT_CONSUMED.values()):
        assert why.strip()


def test_every_destination_is_a_known_one():
    for fact in CONSUMED:
        assert fact.reaches, f"{fact.element}.{fact.field} reaches nothing"
        assert set(fact.reaches) <= set(contract.DESTINATIONS), fact.field


# ---------------------------------------------------------------------------
# T2 — the declared reach is the real reach
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fact", [f for f in CONSUMED
             if set(f.reaches) - {GATE} and (f.element, f.field) not in STRUCTURAL],
    ids=lambda f: f"{f.element}.{f.field}")
def test_a_fact_reaches_exactly_what_it_claims(fact):
    """The measurement, on every run. A claim here that stops being true — an
    emitter dropping a field, a payload key renamed — fails rather than quietly
    becoming documentation."""
    claimed = set(fact.reaches) - {GATE}
    arrived = _travel(fact.element, fact.field, surface=_surface_for(fact))
    assert claimed <= arrived, (
        f"{fact.element}.{fact.field} claims {sorted(claimed)} and reaches "
        f"{sorted(arrived) or 'nothing'}")


@pytest.mark.parametrize(
    "fact", [f for f in CONSUMED if f.owed_reaches],
    ids=lambda f: f"{f.element}.{f.field}")
def test_a_destination_a_fact_is_owed_is_still_missing(fact):
    """The mirror, so `owed` cannot go stale. When somebody closes a gap this
    fails and tells them to clear the sentence — without it the contract slowly
    starts describing a system that no longer exists.

    Only facts whose gap IS a destination are checkable this way. `inputs`
    reaches the artefact and is still incomplete, because it arrives as a
    data-requirement comment rather than a request body; that gap is recorded in
    prose and closed by reading the emitted text, not by counting destinations.
    """
    arrived = _travel(fact.element, fact.field, surface=_surface_for(fact))
    still_missing = set(fact.owed_reaches) - arrived
    assert still_missing == set(fact.owed_reaches), (
        f"{fact.element}.{fact.field} now reaches "
        f"{sorted(set(fact.owed_reaches) & arrived)} — update its `owed`")


@pytest.mark.parametrize("key", sorted(OWED), ids=lambda k: f"{k[0]}.{k[1]}")
def test_an_owed_fact_is_genuinely_unread(key):
    """`OWED` claims generation does not read these at all. If one starts
    travelling, it belongs in CONSUMED."""
    element, field = key
    surface = "ui" if element == "State" else "api"
    assert not _travel(element, field, surface=surface), (
        f"{element}.{field} now travels — move it to CONSUMED")


# ---------------------------------------------------------------------------
# T3 — the graph loader carries what the contract names
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fact", [f for f in CONSUMED if f.element == "Transition"],
    ids=lambda f: f.field)
def test_the_transition_query_selects_every_consumed_property(fact):
    """A contract naming a property the loader does not select would describe a
    fact that never arrives from the graph."""
    if fact.field == "checks":
        assert "GUARDED_BY" in graph_loader.CHECKS_CYPHER   # its own query
        return
    if fact.field in ("source", "target"):
        return                                              # traversed, not selected
    assert f"t.{fact.landed_as}" in graph_loader.TRANSITIONS_CYPHER, fact.landed_as


@pytest.mark.parametrize(
    "fact", [f for f in CONSUMED if f.element == "State"], ids=lambda f: f.field)
def test_the_state_query_selects_every_consumed_property(fact):
    assert f"s.{fact.landed_as}" in graph_loader.STATES_CYPHER, fact.landed_as


# ---------------------------------------------------------------------------
# T5 — nothing lands unclassified
# ---------------------------------------------------------------------------

def _landed_properties(label: str) -> set[str]:
    from metis_mcp.model_sources.landing import plan_landing
    from metis_mcp.model_sources.base import SourceResult

    # The id's suffix decides the transition label — `landing.py:323` reads the
    # surface off `model.id`, not off the states.
    model = Model(
        id="probe-api",
        states={"A": State(id="A", name="A", surface="api", is_initial=True),
                "B": State(id="B", name="B", surface="api")},
        transitions={"t1": Transition(id="t1", source="A", target="B",
                                      trigger="POST /thing", guard="g")})
    plan = plan_landing(SourceResult(model=model, extraction_method="hand_authored",
                                     source_connector="test"), journey="probe")
    # A plan that failed validation writes nothing, and an empty property set
    # would then read as "no unclassified properties" — a pass for the wrong
    # reason. `extraction_method="test"` did exactly that here once.
    assert not plan.errors, plan.errors
    return {key for node in plan.nodes if node.label == label
            for key in node.properties}


def test_every_landed_transition_property_is_classified():
    """The anti-accretion half. A property written to the graph that no model
    field, no infrastructure entry and no unread-property entry accounts for is
    how a node reaches 26 columns without anybody deciding it should."""
    landed = _landed_properties("ApiCall")
    assert landed, "measured nothing"
    # Compared in the spelling landing writes — prefixed. `graph_name` is
    # idempotent, so a bare entry and an already-prefixed one both normalise.
    known = {contract.graph_name("Transition", p) for p in (
        INFRASTRUCTURE
        | set(UNREAD_GRAPH_PROPERTIES)
        | {f.landed_as for f in CONSUMED if f.element == "Transition"}
        | {field for (el, field) in OWED if el == "Transition"}
        | {field for (el, field) in NOT_CONSUMED if el == "Transition"})}
    assert landed <= known, f"unclassified graph properties: {sorted(landed - known)}"


def test_every_landed_state_property_is_classified():
    landed = _landed_properties("State")
    assert landed, "measured nothing"
    known = {contract.graph_name("State", p) for p in (
        INFRASTRUCTURE
        | {f.landed_as for f in CONSUMED if f.element == "State"}
        | {field for (el, field) in OWED if el == "State"}
        | {field for (el, field) in NOT_CONSUMED if el == "State"})}
    assert landed <= known, f"unclassified graph properties: {sorted(landed - known)}"


def test_the_unread_properties_are_still_unread():
    """If somebody gives one a reader, this fails and asks for it to be
    reclassified — rather than the contract quietly contradicting the code."""
    import subprocess
    for name in UNREAD_GRAPH_PROPERTIES:
        found = subprocess.run(
            ["grep", "-rn", name, "--include=*.py", "metis_mcp", "code_analysis"],
            capture_output=True, text=True).stdout.splitlines()
        readers = [line for line in found
                   if "landing.py" not in line and "labels.py" not in line
                   and "contract.py" not in line]
        assert not readers, f"{name} now has a reader: {readers}"


# ---------------------------------------------------------------------------
# T6 — the guards examined something
# ---------------------------------------------------------------------------

def test_the_contract_is_not_silently_empty():
    """An empty loop passes anything. This repo has shipped guards that stayed
    green with their fix reverted."""
    assert len(CONSUMED) > 10
    assert {f.element for f in CONSUMED} == {"Transition", "State"}
    assert any(PROSE in f.reaches for f in CONSUMED)
    # Something must still be recorded as not carried. This deliberately does NOT
    # assert that a CONSUMED fact is incomplete — every one of those gaps is now
    # closed, and a guard that required a gap to exist would have to be weakened
    # the moment the work succeeded, which is how a guard becomes a ritual.
    assert OWED or NOT_CONSUMED, "nothing recorded as unread — is that true?"


def test_the_incomplete_helper_would_report_a_gap_if_there_were_one():
    """`incomplete()` is empty today. That is a fact about the code, not about
    the helper — so this checks the helper still detects a gap, rather than
    leaving `test_a_destination_a_fact_is_owed_is_still_missing` to sit on an
    empty parametrize forever and pass by having nothing to do."""
    from metis_mcp.rendering.contract import ModelFact

    complete = ModelFact("Transition", "x", (PROSE,), ("c",), "why")
    gapped = ModelFact("Transition", "y", (PROSE,), ("c",), "why",
                       owed="the gate", owed_reaches=(GATE,))
    assert complete.is_complete and not gapped.is_complete


def test_describe_names_the_gaps_not_just_the_facts():
    text = contract.describe()
    assert "OWED" in text and "NOT CONSUMED" in text
    # The marker appears exactly when there is something to mark.
    assert ("INCOMPLETE" in text) == bool(contract.incomplete())


# ---------------------------------------------------------------------------
# T7 — a fact a test asserts is inside the approval evidence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fact", [f for f in CONSUMED if f.affects_artefact],
    ids=lambda f: f"{f.element}.{f.field}")
def test_a_fact_that_changes_an_assertion_invalidates_approval(fact):
    """E-8/N-14: a decision made against different evidence must not be applied.

    `source_fingerprint` hashes six of `Transition`'s twenty-two fields, so a
    re-extraction changing `outcome_status` 201->200 moves it not at all and an
    approval recorded against the old evidence is applied silently. Harmless only
    while nothing asserts that fact — and these all do.
    """
    from metis_mcp.review.state import source_fingerprint

    before = _model_with(fact.element, fact.field, "AAA", surface=_surface_for(fact))
    after = _model_with(fact.element, fact.field, "BBB", surface=_surface_for(fact))
    if fact.field == "outcome_status":
        after.transitions["t1"] = dataclasses.replace(
            after.transitions["t1"], outcome_status=598)

    assert source_fingerprint(before) != source_fingerprint(after), (
        f"{fact.element}.{fact.field} reaches an emitted assertion and is not in "
        f"the approval evidence — an approval survives a change to it")


@pytest.mark.parametrize(
    "field", [f for f in contract.asserted_fields("Transition")
              if f not in ("trigger",)],   # a changed trigger is a changed identity
    ids=lambda f: f)
def test_changing_an_asserted_fact_revokes_that_transitions_approval(field):
    """The per-element half of the same rule. `source_fingerprint` is model-wide
    and stales every decision at once; `identity.matching` revokes precisely the
    transitions whose evidence actually moved. Both must see the same facts, or
    the two mechanisms disagree about what counts as evidence."""
    from metis_mcp.identity.matching import diff

    before = _model_with("Transition", field, "AAA", surface="api")
    after = _model_with("Transition", field, "BBB", surface="api")
    if field == "outcome_status":
        after.transitions["t1"] = dataclasses.replace(
            after.transitions["t1"], outcome_status=598)

    delta = diff(before, after)
    revoked = [c for c in delta.changes
               if getattr(c, "invalidates_approval", False)]
    assert revoked, (
        f"changing {field} — which a generated test asserts — revokes no "
        f"approval, so a decision made against the old value is carried forward")


def test_the_two_evidence_mechanisms_agree():
    """`source_fingerprint` hand-lists its fields for hash stability; this
    asserts the hand-list has not drifted from the contract that drives
    `identity.matching`."""
    import inspect

    from metis_mcp.review.state import source_fingerprint

    source = inspect.getsource(source_fingerprint)
    for field in contract.asserted_fields("Transition"):
        assert f"t.{field}" in source, (
            f"{field} is asserted by a generated test and driven into "
            f"`identity.matching`, but `source_fingerprint` does not hash it")


# ---------------------------------------------------------------------------
# A consumed fact survives the act of approving it
# ---------------------------------------------------------------------------
#
# `review.state.overlay` rebuilt each element from an enumerated list of six
# fields, so everything else fell back to the dataclass default the moment a
# decision was applied. It was invisible for as long as the approval evidence
# hashed exactly those six fields — the mutilation never moved the hash. Widening
# the fingerprint to cover what a generated test asserts made it load-bearing:
# `review apply` records a hash from the mutilated model and `generate` computes
# one from the intact model, so no approval could ever match again.

def _approve_everything(model):
    from metis_mcp.review.state import ElementState, ReviewState, source_fingerprint

    decision = dict(lifecycle_state=APPROVED, decided_by="t",
                    decided_at="2026-08-28T00:00:00+00:00", rationale="t")
    return ReviewState(
        model_id=model.id, source_fingerprint=source_fingerprint(model),
        states={sid: ElementState(name=sid, **decision) for sid in model.states},
        transitions={tid: ElementState(name=None, **decision)
                     for tid in model.transitions})


@pytest.mark.parametrize(
    "fact", [f for f in CONSUMED
             if f.element == "Transition" and (f.element, f.field) not in STRUCTURAL],
    ids=lambda f: f.field)
def test_a_consumed_fact_survives_approval(fact):
    """Applying a decision must change the lifecycle state and nothing else."""
    from metis_mcp.review.state import overlay

    model = _model_with("Transition", fact.field, SENTINEL, surface=_surface_for(fact))
    before = dataclasses.asdict(model.transitions["t1"])

    result = overlay(model, _approve_everything(model))
    after = dataclasses.asdict(result.model.transitions["t1"])

    changed = {k for k in after if after[k] != before[k]}
    # `<=`, not `==`: the probe model is already Approved, so a decision may
    # legitimately change nothing. What must never happen is a field OTHER than
    # the lifecycle moving.
    assert changed <= {"lifecycle_state"}, (
        f"approving also changed {sorted(changed - {'lifecycle_state'})}")


def test_approval_does_not_move_the_evidence_it_was_recorded_against():
    """The circular failure this prevents: `record` fingerprints the model AFTER
    decisions are applied, so a lossy overlay makes the recorded hash one the
    loader can never reproduce — every approval stale, permanently."""
    from metis_mcp.review.state import overlay, source_fingerprint

    model = _model_with("Transition", "outcome_status", SENTINEL, surface="api")
    before = source_fingerprint(model)
    after = source_fingerprint(overlay(model, _approve_everything(model)).model)
    assert before == after


# ---------------------------------------------------------------------------
# The file loader carries what the contract declares
# ---------------------------------------------------------------------------
#
# `reaches` is measured on a Model built in memory, so it says nothing about how
# that model was LOADED. Three times now a fact declared consumed was dropped by
# `cli.read_source` and the contract was true of the engine and false of every
# model read from a file — once turning "no response body" into a false
# assertion, and once leaving a UI case with nothing to check at all.

# Fields the file format genuinely does not express. **Empty, and that is the
# result of the shared codec** — `checks` was here, on the reasoning that
# `graph_loader.CHECKS_CYPHER` walks
# `DERIVED_FROM -> DeclaredOutcome -> GUARDED_BY` and a flat file has no edges to
# walk. True of the traversal, false of the field: `mbt.model`'s codec carries
# every declared field, so a file stating its checks round-trips them. The
# exemption was a claim, and `test_the_graph_only_exemptions_are_real` is what
# turned it into a failing test the moment it stopped being true.
GRAPH_ONLY: set[tuple[str, str]] = set()


def _round_trip(element: str, field: str, value):
    """`value` written into a model file, then read back through `read_source`."""
    import json
    import pathlib
    import tempfile

    from metis_mcp.mbt.cli import read_source

    transition = {"id": "t1", "source": "A", "target": "B",
                  "trigger": "POST /x", "guard": "g",
                  "implementation_status": "implemented"}
    source = {"id": "A", "name": "A", "surface": "api", "is_initial": True}
    target = {"id": "B", "name": "B", "surface": "api"}
    (transition if element == "Transition" else target)[field] = value

    path = pathlib.Path(tempfile.mkdtemp()) / "m.json"
    path.write_text(json.dumps({"id": "m-api", "states": [source, target],
                                "transitions": [transition]}))
    from metis_mcp.mbt.model import state_to_dict, transition_to_dict

    model = read_source(str(path))
    # Compared in FILE form, not dataclass form: `checks` decodes to
    # `GuardCheck` objects, and comparing those to the JSON that produced them
    # would fail for a reason that is not a loss. Re-encoding also exercises the
    # writer, so a codec that reads a field and cannot write it back fails here.
    if element == "Transition":
        return transition_to_dict(model.transitions["t1"]).get(field)
    return state_to_dict(model.states["B"]).get(field)


@pytest.mark.parametrize(
    "fact", [f for f in CONSUMED
             if (f.element, f.field) not in STRUCTURAL
             and (f.element, f.field) not in GRAPH_ONLY],
    ids=lambda f: f"{f.element}.{f.field}")
def test_a_consumed_fact_survives_the_file_loader(fact):
    """A fact the contract declares consumed must arrive from a model file too,
    or the contract describes only half the system."""
    # A value shaped like the field's real contents — a bare string handed to a
    # tuple-typed field round-trips as a tuple of characters and fails for the
    # wrong reason.
    value = {"outcome_status": 201, "inputs": [{"name": "n", "location": "body"}],
             "security": [{"scheme": "bearer"}], "media_types": ["application/json"],
             "data_requirements": ["@Size(max=64)"],
             # The full record: `GuardCheck` has four fields and the encoder
             # writes all of them, so a partial fixture fails on the defaults
             # rather than on a loss.
             "checks": [{"expression": "a", "order": 1,
                         "dimension_class": "", "anchor": ""}],
             "trigger": "POST /x", "guard": "g",
             "implementation_status": "implemented"}.get(fact.field, "CARRIED")
    assert _round_trip(fact.element, fact.field, value) == value, (
        f"{fact.element}.{fact.field} is declared consumed and `cli.read_source` "
        f"drops it — the contract is false for every model read from a file")


def test_the_graph_only_exemptions_are_real():
    """An exemption is a claim, and an unchecked claim is how a gap hides.

    Vacuous today — `GRAPH_ONLY` is empty — which is the honest state and not a
    reason to delete the test: the next field somebody exempts gets checked.
    """
    for element, field in GRAPH_ONLY:
        assert contract.fact(element, field), f"{element}.{field} is not consumed"
        assert _round_trip(element, field, "CARRIED") != "CARRIED", (
            f"{element}.{field} does survive the file loader — drop the exemption")


# ---------------------------------------------------------------------------
# What each property is FOR
# ---------------------------------------------------------------------------
#
# Opening an `ApiCall` in Neo4j Browser shows 25 properties in one flat table.
# `trigger`, `inputs_json`, `guard_tier` and `source_episode_id` sit side by side
# looking equally important, and telling a fact about the state machine from a
# fact about how the request is issued required knowing the codebase.

def test_every_landed_property_says_what_it_is_for():
    """The closure that makes the answer complete. A property nobody classified
    is one a reader still cannot place — and generation not consuming it is no
    excuse, because it is on the node either way."""
    for label, element in (("ApiCall", "Transition"), ("State", "State")):
        landed = _landed_properties(label)
        assert landed, f"measured nothing for {label}"
        unplaced = {p for p in landed if not contract.concerns_of(element, p)}
        assert not unplaced, f"{label}: no concern recorded for {sorted(unplaced)}"


def test_every_concern_named_is_a_declared_one():
    for element in ("Transition", "State"):
        for concern, props in contract.properties_by_concern(element).items():
            assert concern in contract.CONCERNS, concern
            assert props, f"{concern} is declared and empty"


def test_the_curl_and_the_model_are_answerable_separately():
    """The question as asked: which of these describe the CALL, and which the
    BEHAVIOUR."""
    grouped = contract.properties_by_concern("Transition")
    curl = {p for c in contract.CURL_CONCERNS for p in grouped.get(c, ())}
    model = {p for c in contract.MODEL_CONCERNS for p in grouped.get(c, ())}
    assert "c_inputs" in curl and "c_response_body" in curl
    assert "b_guard_expression" in model
    # Provenance and presentation are neither, which is the useful part — they
    # are what a reader can skip when asking either question, and their names
    # stay bare precisely to say so.
    assert "source_episode_id" not in curl | model
    assert "guard_tier" not in curl | model


def test_a_property_serving_two_concerns_appears_under_both():
    """`trigger` names the interaction AND is where the curl's method and path
    are split from. Forcing one bucket to keep the table tidy loses the half a
    reader needs."""
    grouped = contract.properties_by_concern("Transition")
    assert "c_trigger" in grouped[contract.BEHAVIOUR]
    assert "c_trigger" in grouped[contract.REQUEST], (
        "the prefix picks one concern; the grouping must still show both")
