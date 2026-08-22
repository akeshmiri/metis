"""
Declared rejections as user paths (application spec §2.1, O-2e, GD-2, GD-3, X-13).

**A Métis model is every possible user path and use case, not how the application
happens to be built** (§2.1: a model describes a feature "as the interacting party
experiences it"). "I send a request that is rejected" is a use case whether the
rejection comes from bean validation or from a `RecordNotFoundException` -- which
exception produced it is an implementation fact, belonging in the evidence and in
the test data, not in whether the path exists.

`synthesis.py` used to discard every declared outcome on one line:

    if outcome.discriminator == "declared":
        continue  # declared outcomes are evidence, not transitions

O-2e disagrees, in writing, having probed this very estate: `@ApiResponse` yields
"200, 204, 201 and 400 on the real controllers, **which become target states**".
So the models were happy-path only, and the 44 rejections the packs had already
recovered were thrown away every run.

What these tests pin is that modelling them did not cost determinism. Adding a
guarded 400 beside an UNGUARDED 201 is a real conflict and a blocking one -- so
the endpoint's existing transitions gain the matching prefix, and the two guards
are complementary rather than merely different.
"""
from __future__ import annotations

import sys

from code_analysis.contract import (
    LINK_DECLARED,
    LINK_DERIVED_VALIDATION,
    Anchor,
    CheckFact,
    ExceptionMappingFact,
    ExtractionReport,
    MemberFact,
    OutcomeFact,
)
from code_analysis.dimension_recovery import (
    BEAN_VALIDATION_EXCEPTION,
    GENERIC_EXPRESSION,
    VALIDATION_EXPRESSION,
)
from code_analysis.synthesis import synthesise
from metis_mcp.mbt.model import CONSTRUCTED, DECLARED
from metis_mcp.mbt.validation import BLOCKING, validate

A = Anchor("Controller.java", 42, "sha")
DTO_A = Anchor("MetricDto.java", 12, "sha")
ADVICE_A = Anchor("GlobalExceptionHandler.java", 81, "sha")

SAVE = "MetricController.save::POST"
READ = "MetricController.getActionById::GET"


def _behaviour(*outcomes, checks=()) -> ExtractionReport:
    return ExtractionReport(outcomes=list(outcomes), checks=list(checks))


def _structural(constrained: bool = True, mapped: bool = True) -> ExtractionReport:
    return ExtractionReport(
        members=[MemberFact("MetricDto", "duration", "java.lang.Long", DTO_A,
                            constraints=("@NotNull",) if constrained else ()),
                 MemberFact("MetricDto", "project", "java.lang.String", DTO_A,
                            constraints=("@Size(max=64)",) if constrained else ())],
        exception_mappings=([ExceptionMappingFact(
            BEAN_VALIDATION_EXCEPTION, 400, "GlobalExceptionHandler", ADVICE_A)]
            if mapped else []))


def _endpoints(validated: bool = True, body: bool = True) -> list[dict]:
    anchor = {"file": A.file, "line": A.line, "commit": A.commit}
    return [
        {"id": SAVE, "http_method": "POST", "path": "/metric",
         "handler_method_id": "MetricController.save", "validated": validated,
         "parameters": ([{"name": "metric", "location": "body",
                          "type_name": "org.catools.athena.model.MetricDto",
                          "required": True, "constraints": []}] if body else []),
         "security": [], "anchor": anchor},
        {"id": READ, "http_method": "GET", "path": "/metric/{id}",
         "handler_method_id": "MetricController.getActionById", "validated": False,
         "parameters": [{"name": "id", "location": "path",
                         "type_name": "java.lang.Long", "required": True,
                         "constraints": []}],
         "security": [], "anchor": anchor},
    ]


def _declared(endpoint_id: str, status: int) -> OutcomeFact:
    return OutcomeFact(id=f"{endpoint_id}::declared-{status}", endpoint_id=endpoint_id,
                       signature=f"{status}/declared", status=status,
                       discriminator="declared", link=LINK_DECLARED, anchor=A)


def _built(endpoint_id: str, status: int, discriminator: str,
           guards=(), sense="") -> OutcomeFact:
    return OutcomeFact(id=f"{endpoint_id}::{status}", endpoint_id=endpoint_id,
                       signature=f"{status}/{discriminator}", status=status,
                       discriminator=discriminator, guarding_check_ids=tuple(guards),
                       guard_sense=sense, link="name-match", anchor=A)


def _model(behaviour, structural=None, endpoints=None, unfold=False):
    result = synthesise(behaviour, endpoints if endpoints is not None else _endpoints(),
                        journey="athena-metric", surface="api",
                        unfold_resources=unfold, structural=structural)
    assert result.ok, result.errors
    return result


def _rejections(model):
    return [t for t in model.transitions.values() if t.outcome_source == DECLARED]


# --------------------------------------------------------------------------
# The path exists. That is the point.
# --------------------------------------------------------------------------

def test_a_declared_rejection_becomes_a_transition():
    """O-2e, met at last. Every run before this discarded it."""
    result = _model(_behaviour(_built(SAVE, 201, "created"), _declared(SAVE, 400)),
                    _structural())
    rejected = _rejections(result.model)
    assert len(rejected) == 1
    assert rejected[0].outcome_status == 400
    assert rejected[0].trigger == "POST /metric"


def test_both_precision_levels_produce_a_path_and_they_differ_only_in_setup():
    """The central claim. `save` has a traceable cause and `getActionById` does
    not -- and BOTH are modelled, because both are things a user can do."""
    result = _model(
        _behaviour(_built(SAVE, 201, "created"), _declared(SAVE, 400),
                   _built(READ, 200, "ok"), _declared(READ, 400)),
        _structural())
    by_trigger = {t.trigger: t for t in _rejections(result.model)}
    assert set(by_trigger) == {"POST /metric", "GET /metric/{id}"}

    save = by_trigger["POST /metric"]
    assert save.guard == f"NOT ({VALIDATION_EXPRESSION})"
    assert save.guard_claim == LINK_DERIVED_VALIDATION

    read = by_trigger["GET /metric/{id}"]
    assert read.guard == f"NOT ({GENERIC_EXPRESSION})"
    assert read.guard_claim == LINK_DECLARED
    assert VALIDATION_EXPRESSION not in read.guard, (
        "its 400 is a RecordNotFoundException; claiming payload validation would "
        "be affirmatively wrong, not merely unevidenced")


def test_the_weaker_path_is_reported_as_sharpenable_not_dismissed():
    """§4.3: an AC or a person can supply the precision code could not. The
    finding says so, rather than reading as a defect to be closed."""
    result = _model(_behaviour(_built(READ, 200, "ok"), _declared(READ, 400)),
                    _structural())
    said = " ".join(result.findings)
    assert "The path is real" in said
    assert "acceptance criterion can sharpen it" in said


def test_the_derived_rejection_carries_its_evidence_and_its_data_requirements():
    result = _model(_behaviour(_built(SAVE, 201, "created"), _declared(SAVE, 400)),
                    _structural())
    rejection = _rejections(result.model)[0]
    assert rejection.guard_anchor.count("=") == 4, "four labelled anchors"
    assert "GlobalExceptionHandler.java:81" in rejection.guard_anchor
    # GD-3: variants of one rejection, carried as data.
    assert rejection.data_requirements == ("@NotNull", "@Size(max=64)")


# --------------------------------------------------------------------------
# Determinism. The check that says the scheme is sound rather than bigger.
# --------------------------------------------------------------------------

def test_the_existing_success_gains_the_matching_prefix():
    """GD-4: reaching a constructed outcome means every earlier dimension passed.

    Without this the 201 stays unguarded, and an unguarded transition beside a
    guarded one on the same (state, trigger) is a determinism CONFLICT.
    """
    result = _model(_behaviour(_built(SAVE, 201, "created"), _declared(SAVE, 400)),
                    _structural())
    created = next(t for t in result.model.transitions.values()
                   if t.outcome_status == 201)
    assert created.guard == VALIDATION_EXPRESSION
    assert created.outcome_source == CONSTRUCTED


def test_the_pair_is_complementary_and_nothing_blocks():
    result = _model(_behaviour(_built(SAVE, 201, "created"), _declared(SAVE, 400)),
                    _structural())
    findings = validate(result.model).findings
    assert [f for f in findings if f.severity == BLOCKING] == []


def test_an_existing_guard_is_conjoined_not_replaced():
    """M-7's discipline in a different place: the recovered condition survives
    verbatim and the dimension is prepended."""
    result = _model(_behaviour(
        _built(SAVE, 200, "ok", guards=["chk-1"]),
        _built(SAVE, 204, "noContent", guards=["chk-1"], sense="!"),
        _declared(SAVE, 400),
        checks=[CheckFact("chk-1", "t.isEmpty()", 1, A)]), _structural())
    guards = {t.outcome_status: t.guard for t in result.model.transitions.values()}
    assert guards[200] == "payload_valid AND t.isEmpty()"
    assert guards[204] == "payload_valid AND NOT (t.isEmpty())"
    assert guards[400] == "NOT (payload_valid)"
    assert [f for f in validate(result.model).findings if f.severity == BLOCKING] == []


def test_an_endpoint_without_a_rejection_is_left_completely_alone():
    """N-14: a changed guard stales every prior review decision. Prefixing an
    endpoint that gains no negative path would do that for nothing."""
    result = _model(_behaviour(_built(READ, 200, "ok")), _structural())
    assert [t.guard for t in result.model.transitions.values()] == [""]


# --------------------------------------------------------------------------
# What is deliberately NOT modelled.
# --------------------------------------------------------------------------

def test_a_declared_status_the_endpoint_also_constructs_is_not_duplicated():
    """Three athena controllers declare a 409 AND build it, with a real
    `ast-enclosure` guard. Taking both would give one behaviour two transitions,
    one of them guarded on a minted atom."""
    result = _model(_behaviour(
        _built(SAVE, 201, "created"),
        _built(SAVE, 409, "conflict", guards=["chk-1"]),
        _declared(SAVE, 409),
        checks=[CheckFact("chk-1", "existing != null", 1, A)]), _structural())
    assert _rejections(result.model) == []
    assert any(t.outcome_status == 409 for t in result.model.transitions.values())


def test_a_declared_2xx_that_was_never_constructed_is_a_recovery_gap_not_a_path():
    """O-2c. The response helper is outside the analysis unit. Turning it into a
    guarded transition would model a success the pack FAILED TO FIND as a
    conditional behaviour -- a different claim, and a false one."""
    result = _model(_behaviour(_built(SAVE, 201, "created"), _declared(SAVE, 204)),
                    _structural())
    assert _rejections(result.model) == []
    assert any("declares" in f for f in result.findings)


def test_a_constrained_field_never_becomes_its_own_transition():
    """GD-3/P-1a: two constraints, one rejection. A technique turns each into
    CASES; neither adds a model element. This is the bound that makes modelling
    the negatives affordable at all."""
    result = _model(_behaviour(_built(SAVE, 201, "created"), _declared(SAVE, 400)),
                    _structural())
    assert len(result.model.transitions) == 2
    assert len(_rejections(result.model)[0].data_requirements) == 2


# --------------------------------------------------------------------------
# Fail-closed, end to end.
# --------------------------------------------------------------------------

def test_without_the_structural_report_the_path_is_still_modelled_just_generically():
    """The rejection is a user path regardless of how much was recovered about
    it. Losing the evidence must weaken the precondition, never delete the path."""
    result = _model(_behaviour(_built(SAVE, 201, "created"), _declared(SAVE, 400)))
    rejection = _rejections(result.model)[0]
    assert rejection.guard == f"NOT ({GENERIC_EXPRESSION})"
    assert rejection.guard_claim == LINK_DECLARED


def test_a_missing_exception_mapping_downgrades_the_claim_rather_than_guessing():
    result = _model(_behaviour(_built(SAVE, 201, "created"), _declared(SAVE, 400)),
                    _structural(mapped=False))
    assert _rejections(result.model)[0].guard_claim == LINK_DECLARED


def test_two_advices_disagreeing_is_reported_and_never_resolved_by_picking_one():
    structural = _structural()
    structural.exception_mappings.append(
        ExceptionMappingFact(BEAN_VALIDATION_EXCEPTION, 422, "OtherAdvice", ADVICE_A))
    result = _model(_behaviour(_built(SAVE, 201, "created"), _declared(SAVE, 400)),
                    structural)
    assert any("not statically decidable" in f for f in result.findings)
    assert _rejections(result.model)[0].guard_claim == LINK_DECLARED


def test_a_rejection_whose_endpoint_was_never_recovered_is_reported_not_invented():
    """No endpoint means no trigger, and a transition with a guessed trigger is
    worse than an admitted gap (§5.8, T-9d)."""
    result = _model(_behaviour(_built(SAVE, 201, "created"),
                               _declared("GhostController.x::POST", 400)),
                    _structural())
    assert _rejections(result.model) == []
    assert any("the trigger is unknown" in f for f in result.findings)


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
