"""Reading a failure, and the words a release recommendation may use.

**Two small things, and the reason both are small.** Filing a defect and opening
a merge request already worked — `publishing/tracker_write.py` was ported from
the same practice and carries the duplicate check and the two-key gate. What was
missing was the step in front of filing (what is this failure evidence *of*) and
the words in front of a release call (what may this evidence support).

Both are pure. Neither files or sends anything, which is what lets the taxonomy
and the ladder be asserted with no network and no tracker.
"""
from __future__ import annotations

import sys

import pytest

from metis_mcp.defects import classify as classifier
from metis_mcp.risk import verdict


# --------------------------------------------------------------------------
# The root-cause taxonomy.
# --------------------------------------------------------------------------

def test_every_class_fires_on_its_own_evidence():
    """A taxonomy with an unreachable member is a promise it does not keep."""
    cases = {
        classifier.STATUS_MISMATCH: "Expected: 200, Actual: 403",
        classifier.URL_CHANGE: "Expected: 200, Actual: 404",
        classifier.SERVICE_EXCEPTION:
            "HTTP 500\n\tat com.example.Service.handle(Service.java:42)",
        classifier.ENVIRONMENT_ISSUE: "java.net.ConnectException: Connection refused",
        classifier.SCHEMA_DRIFT:
            'UnrecognizedPropertyException: Unrecognized field "newField"',
        classifier.TEST_DATA:
            "java.lang.NullPointerException\n\tat Suite.setUp(Suite.java:12)",
        classifier.ASSERTION_DRIFT:
            "AssertionError: expected <PENDING> but was <ACTIVE>",
    }
    assert set(cases) == set(classifier.LABELS), "a class has no worked example"
    for label, evidence in cases.items():
        assert classifier.classify(evidence).label == label, evidence


def test_an_outage_is_read_before_a_service_defect():
    """**Order matters and this is why.** Both produce a 5xx. Reading an outage
    as a service defect sends somebody hunting a bug that is not there; reading a
    service defect as an outage loses a real one. The narrower evidence wins."""
    both = ("HTTP 503 Service Unavailable\n"
            "\tat com.example.Gateway.forward(Gateway.java:88)")
    assert classifier.classify(both).label == classifier.ENVIRONMENT_ISSUE


def test_nothing_matching_is_unclassified_and_never_a_default():
    """A wrong label routes a defect to the wrong team with a confidence nobody
    earned — which is worse than no label."""
    found = classifier.classify("the disk was full")
    assert found.label == classifier.UNCLASSIFIED
    assert found.points_at == classifier.UNDECIDED
    assert "wrong team" in found.because


def test_no_evidence_says_so_rather_than_guessing():
    found = classifier.classify("")
    assert found.label == classifier.UNCLASSIFIED
    assert "nothing to read" in found.because


def test_every_classification_carries_evidence_and_a_next_check():
    for evidence in ("Expected: 200, Actual: 403", "Connection refused",
                     "the disk was full"):
        found = classifier.classify(evidence)
        assert found.because.strip(), evidence
        assert found.next_check.strip(), evidence


def test_what_the_evidence_points_at_is_the_useful_axis():
    """A test-side failure filed as a product defect goes to a team that cannot
    reproduce it. That routing decision is what this classification is for."""
    assert classifier.classify(
        "HTTP 500\n\tat X.y(X.java:1)").points_at == classifier.SYSTEM
    assert classifier.classify(
        "NullPointerException\n\tat S.setUp(S.java:1)",
        phase="setup").points_at == classifier.TEST
    assert classifier.classify(
        "connection refused").points_at == classifier.ENVIRONMENT


def test_an_ambiguous_class_says_undecided_rather_than_choosing():
    """A schema drift may be a legitimate contract change or a service breaking
    one. Picking either would be asserting a conclusion from an absence."""
    found = classifier.classify("Cannot deserialize value of type X")
    assert found.label == classifier.SCHEMA_DRIFT
    assert found.points_at == classifier.UNDECIDED


def test_no_priority_is_set_anywhere():
    """The practice this came from assigns Normal/High. How urgent a defect is
    depends on what it blocks and who is waiting, and neither is in a stack
    trace."""
    described = classifier.describe("Expected: 200, Actual: 403")
    assert not any("priorit" in key.lower() for key in described)
    assert "No priority is set" in described["means"]


def test_an_unclassified_reading_contributes_no_label(monkeypatch):
    """Tagging an issue `unclassified` adds a word and no information, and it
    would become a label somebody filters on."""
    described = classifier.describe("the disk was full")
    assert described["classified"] is False


# --------------------------------------------------------------------------
# The release recommendation.
# --------------------------------------------------------------------------

def test_coverage_alone_can_never_support_go():
    """**The rule C-11 exists for, enforced rather than trusted.** Covered-and-
    failing is a real state, and it is the state a coverage-derived Go would
    call ready. This was prose in a skill; it is a function now."""
    assert verdict.GO not in verdict.permitted_by(verdict.ESTIMATED)
    refusal = verdict.check(verdict.GO, verdict.ESTIMATED)
    assert refusal["ok"] is False
    assert "C-11" in refusal["reason"]


def test_no_evidence_at_all_permits_only_no_go():
    assert verdict.permitted_by(verdict.UNKNOWN) == (verdict.NO_GO,)


def test_an_observed_run_permits_every_recommendation():
    for level in (verdict.CONFIRMED, verdict.INFERRED):
        assert set(verdict.permitted_by(level)) == set(verdict.RECOMMENDATIONS)


def test_caution_is_permitted_on_weak_evidence_and_confidence_is_not():
    """Saying *do not ship* on thin evidence is a cautious call a person may
    make. Saying *ship* on it is a claim the evidence cannot support."""
    weak = verdict.permitted_by(verdict.ESTIMATED)
    assert verdict.NO_GO in weak and verdict.GO_WITH_CONDITIONS in weak
    assert verdict.GO not in weak


def test_zero_runs_is_estimated_and_not_inferred():
    """A coverage figure with no run behind it is an estimate of quality.
    Calling it an inference would let it climb a rung it did not earn."""
    assert verdict.confidence_from(0) == verdict.ESTIMATED
    assert verdict.confidence_from(1) == verdict.INFERRED
    assert verdict.confidence_from(9) == verdict.CONFIRMED


def test_stale_evidence_is_capped_below_confirmed():
    """An outcome observed last month is not a fact about today."""
    assert verdict.confidence_from(9, stale=True) == verdict.INFERRED


def test_an_unmeasurable_scope_is_unknown_however_many_runs_exist():
    assert verdict.confidence_from(9, measurable=False) == verdict.UNKNOWN


def test_an_unrecognised_confidence_is_refused_rather_than_defaulted():
    """A typo silently becoming `confirmed` would widen the ladder at exactly
    the point it exists to narrow it."""
    with pytest.raises(verdict.UnknownConfidence) as raised:
        verdict.permitted_by("high")
    assert "confirmed" in str(raised.value)


def test_the_vocabulary_matches_the_skill_that_uses_it():
    """The words are shared with the sibling project deliberately — a reader who
    moves between the two must not meet a synonym and read a different claim."""
    from pathlib import Path

    skill = (Path(__file__).resolve().parent.parent / "plugins" / "metis"
             / "skills" / "metis-coverage-report" / "specialists"
             / "release-readiness" / "SKILL.md").read_text()
    for word in verdict.RECOMMENDATIONS:
        assert word in skill, f"{word!r} is not in the skill that gives it"
    for level in verdict.CONFIDENCE:
        assert level in skill, f"{level!r} is not in the skill that caps it"


def test_metis_recommends_nothing():
    """`permitted_by` says what the evidence can support. Which one to give is a
    person's call, and `exit_criteria` already refuses to make it."""
    described = verdict.describe()
    assert "does not choose one" in described["means"]


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
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
