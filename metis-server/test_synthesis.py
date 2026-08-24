"""
Layer 4 synthesis tests (application spec §2.1, §5.2, M-2, M-3; R4).

Free to run: synthesis is pure.
"""
import sys

from code_analysis.contract import Anchor, CheckFact, ExtractionReport, OutcomeFact
from code_analysis.synthesis import (
    INITIAL_STATE,
    initial_state_for,
    outcome_state_for,
    response_body_for,
    state_name,
    synthesise,
)

COMMIT = "a3f21c"


def _anchor(line=10):
    return Anchor("CommitController.java", line, COMMIT)


def _behaviour(outcomes, checks=None) -> ExtractionReport:
    return ExtractionReport(
        pack="jvm-behaviour", pack_version="0.1.0", engine="joern",
        engine_version="4.0.604", repo="archive-service", commit=COMMIT,
        frontend="javasrc2cpg", layers=(4,),
        checks=checks or [], outcomes=outcomes,
    )


def _outcome(endpoint, status, disc, checks=(), sense=""):
    return OutcomeFact(id=f"{endpoint}::{status}", endpoint_id=endpoint,
                       signature=f"{status}/{disc}", status=status, discriminator=disc,
                       guarding_check_ids=tuple(checks), guard_sense=sense,
                       link="name-match", anchor=_anchor())


# `handler_method_id` is the field name the structural pack actually emits. An
# earlier version of this fixture said `handler`, which no pack has ever
# produced -- so these tests passed against a shape that does not exist. Keep
# this aligned with packs/jvm-structural/query.sc.
ENDPOINTS = [
    {"id": "e1", "http_method": "GET", "path": "/commit",
     "handler_method_id": "h1", "handler_type": "CommitController",
     "handler_name": "getAll", "response_body": "PageDto<CommitDto>", "anchor": "x"},
    {"id": "e2", "http_method": "GET", "path": "/commit/{id}",
     "handler_method_id": "h2", "handler_type": "CommitController",
     "handler_name": "getById", "response_body": "CommitDto", "anchor": "x"},
    {"id": "e3", "http_method": "GET", "path": "/repo",
     "handler_method_id": "h3", "handler_type": "RepoController",
     "handler_name": "search", "response_body": "RepoDto", "anchor": "x"},
]


def test_the_fixture_matches_the_fields_the_real_pack_emits():
    """Guards the mismatch above: if the pack renames a field, these tests must
    fail rather than keep passing against an imaginary shape.

    **This caught a real one.** When outcome states became per-endpoint, the
    fixture still lacked `handler_type`/`handler_name`, so `outcome_state_for`
    silently took its no-endpoint fallback and every test kept asserting the
    OLD converged shape — green, against behaviour the pipeline no longer has.
    Every field synthesis reads is listed here for that reason.
    """
    import pathlib as _p
    pack = _p.Path("code_analysis/packs/jvm-structural/query.sc").read_text()
    for emitted in ("handler_method_id", "handler_type", "handler_name",
                    "response_body", "response_type", "validated"):
        assert f'"{emitted}"' in pack, f"the pack no longer emits {emitted}"
    for required in ("handler_method_id", "handler_type", "handler_name",
                     "response_body"):
        assert all(required in e for e in ENDPOINTS), f"fixture missing {required}"


# --------------------------------------------------------------------------
# M-2 / M-3 : one outcome state per endpoint
# --------------------------------------------------------------------------

def test_each_endpoints_outcome_is_its_own_state():
    """**These used to converge on one `Ok200` per model, and that was wrong.**

    The old reasoning was that a response is indistinguishable to a caller
    whichever endpoint produced it. It is not: `GET /commit/{id}` returns a
    `CommitDto` and `GET /commit` a `PageDto<CommitDto>` — 48 distinct body
    types across the pilot estate's 91 endpoints — so merging them erased a difference the
    surface really does expose, and a generated case could assert the status and
    never the payload.

    It holds even where two responses are byte-identical. A state is the
    situation the system is left in, not the bytes on the wire: after
    `POST /environment` an environment exists and after `POST /project` a project
    does, both answering `ResponseEntity<Void>`, and a later GET tells them
    apart.
    """
    check = CheckFact("c1", "t.isEmpty()", 1, _anchor())
    outcomes = []
    for handler in ("h1", "h2", "h3"):
        outcomes.append(_outcome(f"{handler}::GET", 204, "noContent", ("c1",)))
        outcomes.append(_outcome(f"{handler}::GET", 200, "ok", ("c1",), sense="!"))

    result = synthesise(_behaviour(outcomes, [check]), ENDPOINTS, journey="archive-service")
    assert result.ok, result.errors

    model = result.model
    outcome_states = {sid for sid, st in model.states.items() if not st.is_initial}
    # Named from the route since I-2 — see `test_the_route_is_what_keeps_two_
    # endpoints_apart`. The property under test is unchanged: one outcome state
    # per endpoint, and three endpoints keep three distinct 204s.
    assert outcome_states == {
        "GetCommit200", "GetCommit204",
        "GetCommitId200", "GetCommitId204",
        "GetRepo200", "GetRepo204",
    }, f"one outcome per endpoint, got {sorted(outcome_states)}"

    to_204 = [t for t in model.transitions.values() if t.outcome_status == 204]
    assert len({t.target for t in to_204}) == 3, "three endpoints, three 204 states"


def test_the_route_is_what_keeps_two_endpoints_apart():
    """`save`, `getById` and `getAll` recur in every controller in a service, so
    the method name alone would fuse two outcomes — and the ROUTE separates them
    at least as well, while being the thing two intakes agree on (I-2).

    Named from the handler, the same endpoint reached the graph twice: the code
    intake produced `RecordPageOk200` and the OpenAPI intake
    `DefaultPageRecordsAPageOfRecords200`, so one behaviour became two nodes.
    """
    assert outcome_state_for(
        {"handler_type": "RepoController", "handler_name": "search",
         "http_method": "GET", "path": "/repo/search"}, 200, "ok"
    ) == "GetRepoSearch200"
    assert outcome_state_for(
        {"handler_type": "CommitController", "handler_name": "search",
         "http_method": "GET", "path": "/commit/search"}, 200, "ok"
    ) == "GetCommitSearch200"


def test_the_verb_is_part_of_the_outcome_state():
    """A state is the situation the system is left in, not the bytes on the wire:
    after `PUT /record/{id}` the record is changed and after `GET /record/{id}`
    it is not, and both answer 200."""
    put = outcome_state_for({"http_method": "PUT", "path": "/record/{id}"}, 200, "ok")
    get = outcome_state_for({"http_method": "GET", "path": "/record/{id}"}, 200, "ok")
    assert put != get


def test_an_unrecovered_handler_falls_back_to_the_status_alone():
    """Fail-closed: no handler facts means no endpoint-specific name to give it,
    and inventing one would name a state after a guess."""
    assert outcome_state_for(None, 200, "ok") == "Ok200"
    assert outcome_state_for({}, 204, "noContent") == "NoContent204"


def test_the_status_label_still_comes_from_the_code_convention():
    """X-7 tier 2 — the response helper's own name, never the route."""
    assert state_name(204, "noContent") == "NoContent204"
    assert state_name(200, "ok") == "Ok200"
    assert state_name(201, "created") == "Created201"


# --------------------------------------------------------------------------
# The expected response — what a test asserts once it has the status
# --------------------------------------------------------------------------

def test_the_declared_response_body_rides_on_the_transition():
    outcomes = [_outcome("h2::GET", 200, "ok")]
    model = synthesise(_behaviour(outcomes), ENDPOINTS, journey="g").model
    assert [t.response_body for t in model.transitions.values()] == ["CommitDto"]


def test_a_bodyless_status_carries_no_body_whatever_the_signature_declares():
    """`getById` declares `ResponseEntity<CommitDto>`; its 204 branch sends
    nothing. Copying the declared type onto the 204 would tell a generated test
    to assert a `CommitDto` the caller never receives — wrong, not vague."""
    outcomes = [_outcome("h2::GET", 204, "noContent")]
    model = synthesise(_behaviour(outcomes), ENDPOINTS, journey="g").model
    assert [t.response_body for t in model.transitions.values()] == [""]
    assert response_body_for(204, "CommitDto") == ""
    assert response_body_for(200, "CommitDto") == "CommitDto"


def test_transitions_stay_distinct_even_when_they_share_a_target():
    check = CheckFact("c1", "t.isEmpty()", 1, _anchor())
    outcomes = [_outcome("h1::GET", 204, "noContent", ("c1",)),
                _outcome("h2::GET", 204, "noContent", ("c1",))]
    model = synthesise(_behaviour(outcomes, [check]), ENDPOINTS, journey="g").model
    assert len(model.transitions) == 2, "shared target must not collapse two transitions"
    assert {t.trigger for t in model.transitions.values()} == {"GET /commit", "GET /commit/{id}"}
    assert len({t.target for t in model.transitions.values()}) == 2, (
        "and each lands in its own outcome state")


# --------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------

def test_guard_sense_produces_the_negation():
    check = CheckFact("c1", "t.isEmpty()", 1, _anchor())
    outcomes = [_outcome("h1::GET", 204, "noContent", ("c1",), sense=""),
                _outcome("h1::GET", 200, "ok", ("c1",), sense="!")]
    model = synthesise(_behaviour(outcomes, [check]), ENDPOINTS, journey="g").model
    guards = {t.outcome_status: t.guard for t in model.transitions.values()}
    assert guards[204] == "t.isEmpty()"
    assert guards[200] == "NOT (t.isEmpty())"


def test_an_unguarded_outcome_is_reported_not_invented():
    outcomes = [_outcome("h1::GET", 201, "created")]
    result = synthesise(_behaviour(outcomes), ENDPOINTS, journey="g")
    assert result.model.transitions
    assert result.unguarded, "an outcome with no recovered guard must be reported"
    assert all(t.guard == "" for t in result.model.transitions.values())


# --------------------------------------------------------------------------
# §5.8 : absence is reported as a cause, never as 'no behaviour'
# --------------------------------------------------------------------------

def test_no_outcomes_names_the_likely_cause():
    result = synthesise(_behaviour([]), ENDPOINTS, journey="g")
    assert not result.ok
    assert any("analysis unit" in e or "framework config" in e for e in result.errors)
    assert any("not evidence that the service has no behaviour" in e for e in result.errors)


def test_declared_versus_constructed_is_triage_not_a_defect_claim():
    """A status declared but not constructed in the handler is most often a
    framework exception handler elsewhere — claiming a defect would manufacture
    one out of a recovery limitation.

    The 204 below is the case: a declared 2xx nothing built is a recovery gap
    (the response helper is outside the analysis unit), not a user path. The 400
    in the same declaration IS a user path and is modelled — see
    `test_negative_outcomes.py` — so it is deliberately absent from this
    finding's "not recovered" list, which would otherwise contradict the
    transition standing beside it.
    """
    check = CheckFact("c1", "t.isEmpty()", 1, _anchor())
    outcomes = [
        _outcome("h1::POST", 201, "created", ("c1",)),
        OutcomeFact("d1", "h1::POST", "400/declared", 400, "declared",
                    (), "", "declared", _anchor()),
        OutcomeFact("d2", "h1::POST", "204/declared", 204, "declared",
                    (), "", "declared", _anchor()),
        OutcomeFact("d3", "h1::POST", "201/declared", 201, "declared",
                    (), "", "declared", _anchor()),
    ]
    result = synthesise(_behaviour(outcomes, [check]), ENDPOINTS, journey="g")
    triage = [f for f in result.findings if "Needs triage" in f]
    assert len(triage) == 1
    assert "exception handler" in triage[0]
    assert "Not recovered: [204]" in triage[0], "the 400 was recovered, as a path"
    assert "disagree" not in triage[0], "must not assert a contradiction it cannot establish"


def test_a_declared_success_does_not_become_a_transition():
    """A declared 2xx that nothing constructed is a *recovery* gap (O-2c).

    Modelling it would claim the pack found a success it did not find. A declared
    **rejection** is the opposite case — a real user path the handler delegates to
    an exception handler — and `test_negative_outcomes.py` pins that it IS
    modelled.
    """
    outcomes = [OutcomeFact("d1", "h1::GET", "200/declared", 200, "declared",
                            (), "", "declared", _anchor())]
    result = synthesise(_behaviour(outcomes), ENDPOINTS, journey="g")
    assert result.model.transitions == {}


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------

def test_every_transition_starts_at_its_own_resource_state():
    """The endpoint is the cluster: the HTTP calls on a resource leave its node.

    One `Ready` carrying every transition in the model was not a cluster, it was
    a hairball — 43 edges on a single node in the tms service. Keyed on the
    resource rather than the exact path, so `/commit` and `/commit/{id}` share a
    node: they are one resource reached two ways, and splitting them would put a
    reader in a different cluster from its own creator.
    """
    check = CheckFact("c1", "t.isEmpty()", 1, _anchor())
    outcomes = [_outcome("h1::GET", 204, "noContent", ("c1",)),
                _outcome("h2::GET", 200, "ok", ("c1",), sense="!")]
    model = synthesise(_behaviour(outcomes, [check]), ENDPOINTS, journey="g").model

    for t in model.transitions.values():
        assert model.states[t.source].is_initial, "paths start here (P-8)"
        assert t.source == initial_state_for(t.trigger)
    assert INITIAL_STATE not in model.states, (
        "the synthetic fallback is for an UNRESOLVED path only; these resolve")


def test_an_unresolved_path_falls_back_rather_than_naming_a_state_after_nothing():
    """T-9d. `__unresolved__` is a recovery failure, not a resource — deriving a
    state name from it would mint a node named after a marker."""
    outcomes = [_outcome("hx::GET", 200, "ok")]
    model = synthesise(_behaviour(outcomes), [
        {"id": "hx::GET", "http_method": "GET", "path": "__unresolved__",
         "handler_method_id": "hx", "parameters": [], "security": [],
         "anchor": {"file": "X.java", "line": 1, "commit": "sha"}},
    ], journey="g").model
    assert [t.source for t in model.transitions.values()] == [INITIAL_STATE]


def test_elements_land_at_quarantine():
    check = CheckFact("c1", "t.isEmpty()", 1, _anchor())
    outcomes = [_outcome("h1::GET", 204, "noContent", ("c1",))]
    model = synthesise(_behaviour(outcomes, [check]), ENDPOINTS, journey="g").model
    assert all(s.lifecycle_state == "Quarantine" for s in model.states.values())
    assert all(t.lifecycle_state == "Quarantine" for t in model.transitions.values())


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)


def test_a_rejection_carries_the_exception_handlers_body_not_an_empty_one():
    """An empty `response_body` is a CLAIM, not a gap.

    `landing` documents it as meaning NO body — a 204, or `ResponseEntity<Void>`
    — which "is a fact a test can assert". So a 400 left empty told twelve
    generated cases to assert an empty payload against a populated
    `ErrorDto`. The handler's own return type is the error shape,
    and it is now used.
    """
    from code_analysis.synthesis import Rejection

    rejection = Rejection(
        endpoint_id="Ctrl.get::GET", trigger="GET /x", status=400,
        expression="request_accepted", claim="advice-scope",
        response_body="ErrorDto")
    assert rejection.response_body == "ErrorDto"

    # And "" still means "no handler stated it" rather than "no body".
    assert Rejection(endpoint_id="a", trigger="t", status=400,
                     expression="e", claim="c").response_body == ""


def test_the_body_is_dropped_when_handlers_disagree():
    """Two handlers on one controller returning different error shapes cannot
    both be the answer, and picking one would be a guess (GD-9)."""
    import code_analysis.synthesis as syn
    import inspect

    source = inspect.getsource(syn._plan_rejections)
    assert "len(scoped_bodies) == 1" in source, (
        "the single-answer guard is what keeps this from picking one of two")
