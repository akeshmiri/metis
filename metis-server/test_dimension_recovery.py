"""
Pack facts -> a guard-dimension chain (application spec GD-1, GD-2, X-10a..X-10d).

`mbt/dimensions.py` had zero callers: four hundred lines implementing §2.4a's
whole combinatorial answer, and nothing that could build it a `Chain`. These
tests pin the step that was missing, and in particular pin the three ways it is
allowed to REFUSE -- because the refusals are what keep a derived guard honest.

The load-bearing claim is narrow: `@Valid` on the body, plus a constrained DTO,
plus an `@ExceptionHandler` mapping the bean-validation exception to this status.
Miss any one and there is no validation dimension, and the reason says which.
"""
from __future__ import annotations

import sys

from code_analysis.contract import (
    Anchor,
    EndpointFact,
    ExceptionMappingFact,
    ExtractionReport,
    MemberFact,
    ParameterFact,
    exception_anchors,
    exception_status_map,
)
from code_analysis.dimension_recovery import (
    BEAN_VALIDATION_EXCEPTION,
    GENERIC_EXPRESSION,
    VALIDATION_DIMENSION_ID,
    VALIDATION_EXPRESSION,
    VALIDATION_ORDER,
    constrained_members,
    recover_chain,
)
from metis_mcp.mbt.dimensions import BUSINESS, VALIDATION, prefix_guard, variation_scope

A = Anchor("Controller.java", 42, "sha")
DTO_A = Anchor("MetricDto.java", 12, "sha")
ADVICE_A = Anchor("GlobalExceptionHandler.java", 81, "sha")


def _endpoint(validated: bool = True, body: bool = True) -> dict:
    params = []
    if body:
        params.append({"name": "metric", "location": "body",
                       "type_name": "org.catools.athena.model.MetricDto",
                       "required": True, "constraints": []})
    return {"id": "MetricController.save::POST", "http_method": "POST",
            "path": "/metric", "parameters": params, "validated": validated,
            "anchor": {"file": A.file, "line": A.line, "commit": A.commit}}


def _members(constrained: bool = True) -> list[MemberFact]:
    return [
        MemberFact("MetricDto", "duration", "java.lang.Long", DTO_A,
                   constraints=("@NotNull(message = \"required\")",) if constrained else ()),
        MemberFact("MetricDto", "project", "java.lang.String", DTO_A,
                   constraints=("@NotNull",) if constrained else ()),
        # A different DTO's constraints must never be borrowed.
        MemberFact("ProjectDto", "name", "java.lang.String", DTO_A,
                   constraints=("@Size(max=64)",)),
    ]


class _Check:
    """`CheckFact`-shaped, which is all `build_chain` requires."""

    def __init__(self, cid, expression, order):
        self.id, self.expression, self.order = cid, expression, order
        self.anchor = A
        self.dimension_class = None


def _recover(**kw):
    """`kw.get(k, default)`, never `kw.get(k) or default` -- an intentionally
    EMPTY exception map is falsy, and the `or` form silently substituted the
    populated default, so the one test that mattered here passed for no reason."""
    return recover_chain(
        kw.get("endpoint", _endpoint()),
        kw.get("checks", ()),
        kw.get("members", _members()),
        kw.get("exception_status", {BEAN_VALIDATION_EXCEPTION: 400}),
        kw.get("status", 400),
        declared_anchor=kw.get("declared_anchor", str(A)),
        exception_anchors=kw.get("exception_anchors", {BEAN_VALIDATION_EXCEPTION: str(ADVICE_A)}),
    )


# --------------------------------------------------------------------------
# The chain closes.
# --------------------------------------------------------------------------

def test_the_validation_dimension_is_recovered_when_all_three_links_are_present():
    recovery = _recover()
    assert recovery.has_validation, recovery.reason
    assert recovery.reason == ""
    assert recovery.validation.expression == VALIDATION_EXPRESSION
    assert recovery.validation.dimension_class == VALIDATION


def test_validation_runs_before_every_in_body_check():
    """X-10a/X-10d: order is the framework's contract, never source position.

    Spring evaluates bean validation in the argument resolver, so it precedes the
    handler body whatever line the annotation appears on. The check below is
    declared at order 1 and anchored EARLIER in the file than the DTO, and
    validation still comes first.
    """
    recovery = _recover(checks=[_Check("chk-1", "t.isEmpty()", 1)])
    ordered = recovery.chain.ordered()
    assert [d.id for d in ordered] == [VALIDATION_DIMENSION_ID, "chk-1"]
    assert ordered[0].order == VALIDATION_ORDER == 0


def test_the_chain_stays_unambiguous_alongside_the_behaviour_packs_checks():
    """GD-9: two dimensions sharing an order make the chain unresolved.

    The behaviour pack numbers its checks from 1, so validation must be exactly
    0. Any other value collides and this assertion is what catches it.
    """
    recovery = _recover(checks=[_Check("chk-1", "a", 1), _Check("chk-2", "b", 2)])
    assert recovery.chain.is_resolved, recovery.chain.unresolved_reason


def test_the_guard_is_gd2s_prefix_and_names_no_downstream_dimension():
    """GD-2/GD-3: earlier dimensions pass, this one fails, later ones are absent.

    Naming a downstream dimension would imply a constraint the code never
    evaluates -- the request never reaches it.
    """
    recovery = _recover(checks=[_Check("chk-1", "t.isEmpty()", 1)])
    guard = prefix_guard(recovery.chain, VALIDATION_DIMENSION_ID)
    assert guard == f"NOT ({VALIDATION_EXPRESSION})"
    assert "isEmpty" not in guard

    scope = variation_scope(recovery.chain, VALIDATION_DIMENSION_ID)
    assert scope.held_pass == ()
    assert scope.not_varied == ("chk-1",), "the in-body check is unreachable here"


def test_four_real_anchors_ride_with_the_dimension():
    """§8.5/T-9a. The guard token is minted; every fact behind it is a line a
    reviewer can open, and each is labelled with what it establishes."""
    recovery = _recover()
    assert len(recovery.anchors) == 4
    labels = [a.split("=", 1)[0] for a in recovery.anchors]
    assert labels == ["constraint", "valid", "exception-handler", "declared"]
    assert "MetricDto.java:12" in recovery.anchors[0]
    assert "GlobalExceptionHandler.java:81" in recovery.anchors[2]


def test_the_dtos_constraints_ride_along_as_data_requirements():
    """GD-3: these are variants of one rejection, not transitions of their own."""
    recovery = _recover()
    assert recovery.constraints == ('@NotNull(message = "required")', "@NotNull")
    assert "@Size(max=64)" not in recovery.constraints, "that belongs to ProjectDto"


# --------------------------------------------------------------------------
# The three refusals. Each is a case where guessing would be wrong, not vague.
# --------------------------------------------------------------------------

def test_no_valid_annotation_means_no_validation_claim():
    recovery = _recover(endpoint=_endpoint(validated=False))
    assert not recovery.has_validation
    assert "@Valid" in recovery.reason
    assert recovery.rejection_expression() == GENERIC_EXPRESSION


def test_no_body_means_no_payload_to_reject():
    """`getActionById(@PathVariable Long id)` declares a 400 and has no DTO.

    Its 400 is a `RecordNotFoundException`. Labelling it "payload invalid" would
    be affirmatively wrong: a fixture built from it sends a malformed body to an
    endpoint that reads none, and never reaches the path.
    """
    recovery = _recover(endpoint=_endpoint(body=False))
    assert not recovery.has_validation
    assert "no request body" in recovery.reason


def test_an_unconstrained_dto_gives_valid_nothing_to_reject():
    recovery = _recover(members=_members(constrained=False))
    assert not recovery.has_validation
    assert "no field constraints" in recovery.reason


def test_an_exception_mapped_to_a_different_status_is_not_this_outcomes_cause():
    """The endpoint declares 422; bean validation produces 400. Different path."""
    recovery = _recover(status=422)
    assert not recovery.has_validation
    assert "maps to 400, not 422" in recovery.reason


def test_no_exception_handler_at_all_leaves_the_result_unknown():
    recovery = _recover(exception_status={})
    assert not recovery.has_validation
    assert BEAN_VALIDATION_EXCEPTION in recovery.reason


# --------------------------------------------------------------------------
# The join the two packs have to agree on.
# --------------------------------------------------------------------------

def test_members_are_matched_on_the_simple_type_name():
    """A parameter carries the FQN and a member the simple name. Comparing them
    unnormalised finds nothing, which reads exactly like a DTO with no
    constraints -- silent, and wrong in the safe-looking direction."""
    found = constrained_members("org.catools.athena.model.MetricDto", _members())
    assert [m.name for m in found] == ["duration", "project"]


# --------------------------------------------------------------------------
# The exception map itself.
# --------------------------------------------------------------------------

def _report(*mappings) -> ExtractionReport:
    return ExtractionReport(exception_mappings=list(mappings))


def test_the_exception_map_resolves_agreeing_advices():
    """Two beans, same exception, same status: certain, and not a conflict.

    athena's `ControllerErrorHandler` overrides Spring's base-class method while
    `GlobalExceptionHandler` annotates one. They disagree about the response
    BODY and agree about the status, so the status is usable.
    """
    resolved, contested = exception_status_map(_report(
        ExceptionMappingFact(BEAN_VALIDATION_EXCEPTION, 400, "GlobalExceptionHandler", ADVICE_A),
        ExceptionMappingFact(BEAN_VALIDATION_EXCEPTION, 400, "ControllerErrorHandler", ADVICE_A),
    ))
    assert resolved == {BEAN_VALIDATION_EXCEPTION: 400}
    assert contested == []


def test_a_genuinely_contested_exception_is_excluded_not_picked():
    """GD-9. Spring's choice is undecidable without an @Order, so no rejection is
    attributed to it -- a guess here puts a precondition on a transition the
    runtime may never satisfy."""
    resolved, contested = exception_status_map(_report(
        ExceptionMappingFact("BoomException", 400, "AdviceA", ADVICE_A),
        ExceptionMappingFact("BoomException", 422, "AdviceB", ADVICE_A),
    ))
    assert resolved == {}
    assert contested == ["BoomException"]


def test_every_mapping_carries_a_line_to_open():
    assert exception_anchors(_report(
        ExceptionMappingFact(BEAN_VALIDATION_EXCEPTION, 400, "GlobalExceptionHandler", ADVICE_A),
    )) == {BEAN_VALIDATION_EXCEPTION: str(ADVICE_A)}


def test_the_endpoint_fact_carries_validated_and_the_member_fact_carries_constraints():
    """Both fields are new to the contract; a pack emitting them must round-trip."""
    endpoint = EndpointFact(
        id="e", http_method="POST", path="/metric", handler_method_id="h",
        anchor=A, parameters=(ParameterFact("m", "body", "MetricDto"),), validated=True)
    assert endpoint.validated is True
    assert MemberFact("MetricDto", "duration", "Long", DTO_A).constraints == ()


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
        except Exception as e:                                    # noqa: BLE001
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
