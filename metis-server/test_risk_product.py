"""
Product risk — the software-quality half of risk management.

`test_risk.py` covers the project-risk family built from a twelve-section
project-management reference. This file covers what that reference does not
contain and software quality engineering does: detectability, the technical /
business split, and risk-based test prioritisation.

**The assertion this file exists to make** is the C-11 boundary. Coverage may
say a behaviour is untested; it may never say the behaviour is likely to fail.
Every module under test here reads the coverage ledger, so every one of them is
a place that rule could be broken quietly, and the tests below are what make
breaking it loud.
"""
from __future__ import annotations

import pytest

from metis_mcp.mbt.coverage import DIRECT, INDIRECT, INITIATED, LedgerRow
from metis_mcp.risk import detection


def _rows(*specs) -> list[LedgerRow]:
    """`(transition, mechanism, case)` triples as ledger rows."""
    return [LedgerRow(tid, "api", mech, "criterion", test_case_id=case)
            for tid, mech, case in specs]


# --- the scale ---------------------------------------------------------------

@pytest.mark.parametrize("mechanism,case,outcome,expected", [
    (DIRECT, "TC-1", "passed", detection.CAUGHT),
    (DIRECT, "TC-1", None, detection.TESTED_UNOBSERVED),
    (INDIRECT, "TC-1", "passed", detection.INDIRECT_ONLY),
    (INITIATED, None, None, detection.EXERCISED_NO_ORACLE),
])
def test_the_mechanism_and_the_execution_together_decide_detectability(
        mechanism, case, outcome, expected):
    """A test that exists and a test that has run are different assurances, and
    the ledger already separates direct from indirect from merely initiated."""
    rows = _rows(("t", mechanism, case))
    executions = {case: outcome} if case and outcome else {}

    assert detection.detection_for("t", rows, executions).score == expected


def test_a_transition_no_row_mentions_is_unnoticed():
    assert detection.detection_for("t", []).score == detection.UNNOTICED


def test_the_best_available_mechanism_wins():
    """A transition covered indirectly AND directly is directly covered. Taking
    the worst row would report a real oracle as an absent one."""
    rows = _rows(("t", INDIRECT, "TC-1"), ("t", DIRECT, "TC-2"))

    assert detection.detection_for("t", rows).score == detection.TESTED_UNOBSERVED


# --- the inversion that is correct -------------------------------------------

def test_a_failing_test_scores_best_and_is_reported_as_a_defect():
    """Detection asks whether the net would catch it. A red test IS the net
    catching it, so detectability is maximal — and the live defect is a second
    finding reported beside it, never folded into the score.

    Scoring a caught failure as poorly-detected would push effort away from the
    failures nobody can see, which is the opposite of what this axis is for.
    """
    rows = _rows(("t", DIRECT, "TC-1"))

    result = detection.detection_for("t", rows, {"TC-1": "failed"})

    assert result.score == detection.CAUGHT
    assert result.failing is True


def test_a_passing_and_a_failing_run_score_the_same_on_this_axis():
    """The axis measures the net, not the code under it."""
    rows = _rows(("t", DIRECT, "TC-1"))

    passed = detection.detection_for("t", rows, {"TC-1": "passed"})
    failed = detection.detection_for("t", rows, {"TC-1": "failed"})

    assert passed.score == failed.score
    assert (passed.failing, failed.failing) == (False, True), (
        "the difference between them is reported, just not on this axis")


@pytest.mark.parametrize("outcome", ["skipped", "errored", "not_run"])
def test_an_outcome_that_did_not_exercise_the_behaviour_does_not_improve_it(
        outcome):
    """`skipped` is the dangerous one: a skipped test is indistinguishable from
    a passing one in most reports, and asserts nothing at all."""
    rows = _rows(("t", DIRECT, "TC-1"))

    result = detection.detection_for("t", rows, {"TC-1": outcome})

    assert result.score == detection.TESTED_UNOBSERVED


# --- unmeasured is not a value -----------------------------------------------

def test_an_unmeasured_transition_refuses_rather_than_defaulting():
    """Every default available is a false statement: `UNNOTICED` reports a
    measurement gap as a safety gap, `CAUGHT` reports it as safety."""
    with pytest.raises(detection.Unmeasured):
        detection.detection_for("t", _rows(("t", DIRECT, "TC-1")),
                                unmeasured=["t"])


def test_the_unmeasured_are_kept_out_of_the_scores_entirely():
    """So that no caller can average them in without noticing."""
    rows = _rows(("a", DIRECT, "TC-1"), ("b", DIRECT, "TC-2"))

    out = detection.detection_over(["a", "b"], rows, unmeasured=["b"])

    assert set(out["scores"]) == {"a"}
    assert out["unmeasured"] == ["b"]


def test_unmeasured_is_reported_as_neither_safety_nor_a_blind_spot():
    rows = _rows(("a", DIRECT, "TC-1"))

    out = detection.detection_over(["a", "b"], rows, unmeasured=["b"])

    assert "b" not in out["blind_spots"]
    assert "b" not in out["failing"]


# --- the C-11 boundary, asserted structurally --------------------------------

def test_detection_never_produces_a_probability():
    """The rule the module exists inside. Coverage says *untested*; it does not
    say *likely to fail*, and a detection score must never be mistaken for one
    or reachable as one.
    """
    rows = _rows(("t", DIRECT, "TC-1"))

    result = detection.detection_for("t", rows, {"TC-1": "passed"})

    assert not hasattr(result, "probability")
    assert "probability" not in detection.MEANS.lower().split()
    fields = set(vars(result))
    assert "probability" not in fields and "likelihood" not in fields


def test_the_means_line_says_what_the_number_is_not():
    """Every figure this family produces carries its own basis, because the
    misreading is the failure mode, not the arithmetic."""
    assert "not probability" in detection.MEANS
    assert "C-11" in detection.MEANS


def test_the_scale_is_never_multiplied_into_an_exposure_score():
    """Three ordinals multiplied is an RPN, and an RPN hides which of its three
    axes is the bad one — a 1x5x5 and a 5x5x1 both read as 25."""
    assert "RPN" in detection.MEANS
    assert "never multiplied" in detection.MEANS


# --- the technical / business split (PRISMA) ---------------------------------

def _model():
    from mbt_fixtures import login_model

    return login_model()


def test_the_business_half_is_asked_and_never_gathered():
    """PRISMA's operative rule: impact factors go to business representatives.
    Every one of the six is a statement about what the organisation values, and
    no amount of static analysis produces one."""
    from metis_mcp.risk import inputs, product

    for item in product.business_inputs():
        assert item.source == inputs.ASKED, item.name
        assert item.question, f"{item.name} is asked and carries no question"
        assert item.absent_means, f"{item.name} must say what its absence means"


def test_no_absent_means_reads_as_reassurance():
    """The same assertion `risk/inputs.py` makes about its own declarations."""
    from metis_mcp.risk import product

    for item in product.business_inputs():
        lowered = item.absent_means.lower()
        for reassuring in ("no risk", "low risk", "safe", "fine", "nothing to"):
            assert reassuring not in lowered, (item.name, item.absent_means)


def test_the_technical_half_is_gathered_from_the_model():
    from metis_mcp.risk import product

    model = _model()
    profile = product.technical_profile(model, model.transition_ids()[0])

    declared = {f.name for f in product.TECHNICAL_FACTORS}
    # Scored factors plus unmeasured ones account for every declared factor:
    # nothing is silently dropped, and nothing is scored that was not measured.
    assert set(profile["factors"]) | set(profile["not_measured"]) == declared
    assert set(profile["factors"]).isdisjoint(profile["not_measured"])
    assert profile["band"] in {b for _, _, b in product.BANDS}


def test_an_unmeasured_factor_is_named_rather_than_scored():
    """This fixture is a hand-built model with no code behind it, so the two
    measured factors have no value. Scoring them as their best would rank the
    least-known behaviour in a service as its safest."""
    from metis_mcp.risk import product

    model = _model()
    profile = product.technical_profile(model, model.transition_ids()[0])

    assert profile["not_measured"] == ["code_complexity", "code_size", "repairs"]
    assert "code_complexity" not in profile["factors"]


def test_a_repair_count_is_never_read_without_its_window():
    """Zero repairs is a real answer; no window is not. `repairs_window` is what
    separates "counted, and it was never fixed" from "nobody counted", and a
    count without it is a number rather than a measurement."""
    from metis_mcp.risk import product

    model = _model()
    profile = product.technical_profile(model, model.transition_ids()[0])

    assert profile["repairs_window"] == ""
    assert "repairs" in profile["not_measured"]


def test_a_counted_zero_scores_where_an_uncounted_one_does_not():
    """The distinction the window exists for, asserted on both sides."""
    import dataclasses

    from metis_mcp.risk import product

    model = _model()
    tid = model.transition_ids()[0]
    model.transitions[tid] = dataclasses.replace(
        model.transitions[tid], repairs=0, repairs_window="v1..HEAD")

    profile = product.technical_profile(model, tid)

    assert profile["factors"]["repairs"] == 1, "never repaired is the best score"
    assert "repairs" not in profile["not_measured"]


def test_the_band_is_a_mean_so_a_better_known_behaviour_is_not_ranked_worse():
    """The number of factors varies — four without a JVM handler, six with one.
    A sum would make the measured behaviour score higher for being better known,
    which inverts what the band is for."""
    from metis_mcp.risk import product

    model = _model()
    profile = product.technical_profile(model, model.transition_ids()[0])

    assert 1.0 <= profile["score"] <= 5.0, (
        "a mean over 1..5 factors stays in 1..5 however many were measured")


def test_the_profile_reports_the_raw_counts_beside_the_ratings():
    """Reporting only the rating hides the measurement a reader disagrees with."""
    from metis_mcp.risk import product

    model = _model()
    profile = product.technical_profile(model, model.transition_ids()[0])

    assert set(profile["observed"]) == set(profile["factors"])


def test_each_factor_is_rated_before_anything_is_added():
    """Summing raw counts lets the factor with the largest natural range decide
    the band alone. Measured: `fan_in` rated an ordinary transition Very High
    because six things pointed at its target."""
    from metis_mcp.risk import product

    assert product._rate("fan_in", 100) == 5
    assert product._rate("fan_in", 0) == 1
    assert all(1 <= product._rate(name, n) <= 5
               for name in product.THRESHOLDS for n in range(0, 40))


def test_the_profile_names_the_prisma_factors_it_cannot_yet_answer():
    """Four of PRISMA's six technical factors need facts the packs compute and
    do not land. Saying so is the difference between a partial profile and one
    that reads as complete."""
    from metis_mcp.risk import product

    model = _model()
    profile = product.technical_profile(model, model.transition_ids()[0])

    assert profile["not_covered"], "a partial profile must say what it omits"
    # `size` and `complexity` left this list when the packs began measuring
    # them. What remains are the three PRISMA factors nothing here can answer:
    # they are facts about the team and the technology, not about the code.
    assert set(profile["not_covered"]) == {
        "degree of re-use", "technology", "team experience"}


def test_unverifiable_guards_come_from_the_validator_and_not_a_second_notion():
    """`mbt/validation.py` already decides M-17 and is already tested. A second
    notion here would drift, and the two would disagree about one guard."""
    from metis_mcp.mbt.validation import validate
    from metis_mcp.risk import product

    model = _model()
    expected = set()
    for finding in validate(model).unverifiable:
        expected.update(finding.element_ids)

    assert set(product.unverifiable_ids(model)) == expected


def test_the_technical_profile_sets_no_probability():
    """Defect-proneness ranks; it does not forecast."""
    from metis_mcp.risk import product

    model = _model()
    profile = product.technical_profile(model, model.transition_ids()[0])

    assert "probability" not in profile
    assert "not a failure rate" in product.MEANS


def test_an_unknown_transition_raises_rather_than_scoring_zero():
    from metis_mcp.risk import product

    with pytest.raises(KeyError):
        product.technical_profile(_model(), "no-such-transition")


@pytest.mark.parametrize("label,kind", [
    ("Requirement", "functional"), ("Endpoint", "architectural"),
    ("ApiCall", "behavioural"), ("TestCase", "test"), ("Nonsense", None),
])
def test_risk_items_are_typed_by_the_rbt_taxonomy(label, kind):
    from metis_mcp.risk import product

    assert product.item_type_for(label) == kind


# --- prioritisation ----------------------------------------------------------

def _detections(**by_id):
    from metis_mcp.risk.detection import LABELS, Detection

    return {tid: Detection(tid, score, LABELS[score], failing)
            for tid, (score, failing) in by_id.items()}


def test_the_least_detectable_is_ordered_first():
    """The premise of risk-based testing: a new test buys most where nothing
    would notice a break."""
    from metis_mcp.risk import prioritisation

    found = _detections(a=(1, False), b=(5, False), c=(3, False))

    assert [r["transition_id"] for r in prioritisation.order(found)] == ["b", "c", "a"]


def test_defect_proneness_breaks_a_detectability_tie():
    from metis_mcp.risk import prioritisation

    found = _detections(a=(5, False), b=(5, False))
    technical = {"a": {"score": 6, "band": "Low"}, "b": {"score": 14, "band": "High"}}

    assert [r["transition_id"] for r in
            prioritisation.order(found, technical)] == ["b", "a"]


def test_the_order_is_total_so_it_cannot_change_between_runs():
    """P-7. `path_generation` is deterministic BFS in id order precisely so a
    regenerated suite diffs cleanly; an unstable risk order would make every
    run's output look changed."""
    from metis_mcp.risk import prioritisation

    found = _detections(z=(5, False), a=(5, False), m=(5, False))

    once = prioritisation.order(found)
    twice = prioritisation.order(dict(reversed(list(found.items()))))

    assert [r["transition_id"] for r in once] == ["a", "m", "z"]
    assert once == twice, "the same input in a different dict order must sort alike"


def test_an_unprofiled_item_is_ordered_not_dropped():
    """An item nobody profiled is not an item at low risk."""
    from metis_mcp.risk import prioritisation

    found = _detections(a=(5, False), b=(5, False))

    ordered = prioritisation.order(found, {"a": {"score": 9, "band": "Medium"}})

    assert {r["transition_id"] for r in ordered} == {"a", "b"}
    assert ordered[0]["transition_id"] == "a", "profiled and worse sorts first"


def test_weighted_coverage_is_a_pivot_and_never_a_percentage():
    """An ordinal band cannot be averaged (exposure.ORDINAL_BASIS), and a
    'risk-weighted coverage percentage' would sum, average and compare at once."""
    from metis_mcp.risk import prioritisation

    found = _detections(a=(5, False), b=(1, False))
    technical = {"a": {"band": "High"}, "b": {"band": "High"}}

    report = prioritisation.weighted_coverage(found, technical)

    assert report["by_band"]["High"] == {
        "total": 2, "uncovered": 1, "failing": 0, "transitions": ["a"]}
    # Asserted against the data, not the prose: every figure is a count, and a
    # fraction anywhere would be the averaged ordinal this refuses to produce.
    counts = [v for cell in report["by_band"].values()
              for k, v in cell.items() if k != "transitions"]
    assert all(isinstance(v, int) and not isinstance(v, bool) for v in counts)


def test_the_unmeasured_are_in_no_band_and_in_no_count():
    from metis_mcp.risk import prioritisation

    found = _detections(a=(5, False))

    report = prioritisation.weighted_coverage(found, {}, unmeasured=["z"])

    assert report["unmeasured"] == ["z"]
    assert all("z" not in cell["transitions"] for cell in report["by_band"].values())


def test_residual_keeps_the_two_populations_apart():
    """A test and a fix are different work, and one total would let a rising
    failure count be cancelled by rising coverage."""
    from metis_mcp.risk import prioritisation

    found = _detections(blind=(5, False), broken=(1, True))
    technical = {"blind": {"band": "High"}, "broken": {"band": "High"}}

    report = prioritisation.residual(found, technical)

    assert [r["transition_id"] for r in report["unnoticed"]] == ["blind"]
    assert [r["transition_id"] for r in report["failing"]] == ["broken"]
    assert "total" not in report


def test_exit_criteria_refuses_to_decide_without_a_threshold():
    """The threshold is a person's, settled at planning time."""
    from metis_mcp.risk import prioritisation

    report = prioritisation.exit_criteria({"unnoticed": [1], "failing": []})

    assert report["decidable"] is False
    assert "NO THRESHOLD" in report["means"]


def test_exit_criteria_reports_a_breach_and_still_gives_no_verdict():
    from metis_mcp.risk import prioritisation

    report = prioritisation.exit_criteria(
        {"unnoticed": [1, 2, 3], "failing": []}, {"unnoticed": 1})

    assert report["within_threshold"] is False
    assert report["breaches"] == ["unnoticed: 3 exceeds the agreed 1"]
    for word in ("ship", "release", "go", "approve"):
        assert f" {word} " not in report["means"].replace("to ship.", "")


def test_no_module_here_multiplies_the_three_axes_into_one_number():
    """An RPN hides which axis is the bad one: 1x5x5 and 5x5x1 both read 25."""
    from metis_mcp.risk import prioritisation

    assert "NOT a product" in prioritisation.ORDER_MEANS
    assert "RPN" in prioritisation.ORDER_MEANS


# --- the wiring: risk reaches the workflows that need it ---------------------
#
# Before this, the dependency ran strictly one way. Risk consumed
# `coverage_report`, `change_review`, `validate_model` and `describe_execution`;
# nothing called back, so Métis could say a requirement was risky and could not
# use that to decide what to test first — which is the entire point of risk in
# software quality engineering.


def _paths_context(model, ledger=None):
    import types

    from metis_mcp.mbt.path_generation import generate

    return types.SimpleNamespace(
        model=model, paths=generate(model, "all-transitions", 10), ledger=ledger)


def test_test_generate_has_a_prioritise_stage_before_render():
    """Ordering after rendering would order a batch nobody re-rendered."""
    from metis_mcp.workflow.stages import WORKFLOWS

    stages = {s.name: s for s in WORKFLOWS["test-generate"].ordered}

    assert "prioritise" in stages
    assert stages["prioritise"].ordinal < stages["render"].ordinal
    assert "prioritise" in stages["render"].requires


def test_prioritising_reorders_the_paths_and_drops_none():
    """Risk decides what is tested FIRST. Dropping the tail would turn a
    priority into a scope cut nobody approved."""
    from metis_mcp.workflow.handlers import _prioritise
    from mbt_fixtures import login_model

    model = login_model()
    context = _paths_context(model)
    before = [p.validated_transition_id for p in context.paths.paths]

    outcome, _, _, _ = _prioritise(context)
    after = [p.validated_transition_id for p in context.paths.paths]

    assert outcome == "passed"
    assert after != before, "the ordering did nothing, so this proves nothing"
    assert sorted(after) == sorted(before), "a path was dropped"


def test_the_risk_order_is_byte_identical_between_runs():
    """P-7. `path_generation` is deterministic BFS in id order so a regenerated
    suite diffs cleanly; an unstable risk order would make every run look
    changed."""
    from metis_mcp.workflow.handlers import _prioritise
    from mbt_fixtures import login_model

    model = login_model()
    first, second = _paths_context(model), _paths_context(model)

    _prioritise(first)
    _prioritise(second)

    assert ([p.validated_transition_id for p in first.paths.paths]
            == [p.validated_transition_id for p in second.paths.paths])


def test_prioritising_without_paths_fails_rather_than_passing_empty():
    import types

    from metis_mcp.workflow.handlers import _prioritise

    outcome, detail, _, _ = _prioritise(
        types.SimpleNamespace(model=None, paths=None, ledger=None))

    assert outcome == "failed"
    assert "generate-paths" in detail


def test_coverage_report_reports_risk_weighted_coverage():
    from metis_mcp.workflow.stages import WORKFLOWS

    stages = {s.name: s for s in WORKFLOWS["coverage-report"].ordered}

    assert "risk-weighted" in stages
    assert stages["risk-weighted"].blocking is False, (
        "a concentration of uncovered high-band behaviour is something to act "
        "on, not a failed run — the gates here are deliberately two")


def test_the_risk_weighted_stage_needs_the_ledger_and_says_so():
    import types

    from metis_mcp.workflow.handlers import _risk_weighted
    from mbt_fixtures import login_model

    outcome, detail, _, _ = _risk_weighted(
        types.SimpleNamespace(model=login_model(), ledger=None))

    assert outcome == "failed"
    assert "ledger" in detail


def test_change_review_turns_its_findings_into_risk_candidates():
    """`candidates.from_change_review` was written for exactly this shape and
    was reachable only from the `risk_candidates` tool — the workflow that
    produces the findings and the function that consumes them ran in separate
    worlds."""
    import types

    from metis_mcp.workflow.handlers import _change_review

    findings = [{"severity": "critical", "what": "nothing validates this",
                 "transition_id": "t01"}]
    context = types.SimpleNamespace(
        carry_revocations=(), carry_renames=(), change_findings=findings,
        risk_candidates=[])

    _change_review(context)

    assert len(context.risk_candidates) == 1
    assert context.risk_candidates[0]["derived_from"] == "model"


def test_a_candidate_from_a_change_review_still_carries_no_probability():
    """Métis observed that a change left behaviour unasserted. That is not a
    forecast, and a number invented to fill the column would read as one."""
    import types

    from metis_mcp.workflow.handlers import _change_review

    context = types.SimpleNamespace(
        carry_revocations=(), carry_renames=(),
        change_findings=[{"severity": "major", "what": "positive path only",
                          "transition_id": "t02"}],
        risk_candidates=[])

    _change_review(context)

    assert context.risk_candidates[0]["probability"] is None


def test_warranted_depth_and_achievable_depth_are_different_questions():
    """`classify_depth` says whether a transition CAN be tested deeply; the band
    says whether it SHOULD be. The join is the interesting case."""
    from metis_mcp.risk import prioritisation

    gaps = prioritisation.depth_gaps(
        {"deep-wanted": "Very High", "shallow-fine": "Low"},
        {"deep-wanted": "partial", "shallow-fine": "partial"})

    assert [g["transition_id"] for g in gaps] == ["deep-wanted"]


def test_a_fully_reachable_transition_is_no_depth_gap():
    from metis_mcp.risk import prioritisation

    assert prioritisation.depth_gaps({"t": "Very High"}, {"t": "full"}) == []


def test_every_wired_surface_is_recorded_as_a_testing_area():
    """The map is what makes the wiring checkable: a renamed or deleted owner
    fails a test rather than quietly leaving an area unowned."""
    from metis_mcp.risk.areas import TESTING_AREAS

    owners = {a.skill for a in TESTING_AREAS}

    assert {"metis-test-generate", "metis-coverage-report"} <= owners


# --- the risks are software quality engineering risks ------------------------
#
# The family was built from a project-management reference whose ten categories
# are Strategic, Financial, Technical, Operational, Schedule, Cost, Quality,
# Resource, Procurement and External. Every software observation Métis can make
# landed in `Quality` or `Technical` — two buckets in a taxonomy about funding
# and vendors, neither addressable by anybody in particular.


def test_there_are_three_taxonomies_and_they_are_disjoint():
    """One name meaning two things in two families would make `taxonomy_of` a
    coin toss, and a register unroutable."""
    from metis_mcp.risk import rbs

    project = set(rbs.CATEGORIES)
    product = set(rbs.PRODUCT_CATEGORIES)
    process = set(rbs.PROCESS_CATEGORIES)

    assert project.isdisjoint(product)
    assert project.isdisjoint(process)
    assert product.isdisjoint(process)
    assert set(rbs.ALL_CATEGORIES) == project | product | process


def test_the_process_taxonomy_covers_delivery_not_only_testing():
    """"Process" here means the whole quality pipeline. A taxonomy that stops at
    test design cannot hold "we cannot roll this back" or "we would not know in
    production", which are where quality is actually lost."""
    from metis_mcp.risk import rbs

    assert {"Release and deployment", "Observability", "Test environment",
            "Test data", "Automation", "Regression",
            "Technical debt"} <= set(rbs.PROCESS_CATEGORIES)


@pytest.mark.parametrize("name,family", [
    ("Test environment", "process"),
    ("Release and deployment", "process"),
    ("Security", "product"),
    ("Procurement", "project"),
])
def test_a_category_reports_which_family_owns_it(name, family):
    """A process risk is owned by the people who build the pipeline, a product
    risk by the people who build the feature, a project risk by the people who
    fund it."""
    from metis_mcp.risk import rbs

    assert rbs.taxonomy_of(name) == family


def test_every_model_derived_candidate_is_a_process_risk():
    """**The claim this section exists to make.** Métis observes things about
    the quality work — untested behaviour, a self-confirming criterion, a change
    nothing re-checks. None of those is a project risk, and filing them as
    `Quality` said they were."""
    from metis_mcp.risk import rbs
    from metis_mcp.risk.assessment import for_release, for_requirement
    from metis_mcp.risk.candidates import from_change_review, from_unmeasured

    rows = (
        from_change_review([
            {"severity": s, "what": "w", "transition_id": "t"}
            for s in ("critical", "major", "minor", "question")])
        + from_unmeasured([{"scope": "s", "reason": "r", "kind": "structural"}])
        + for_requirement({"criteria_count": 0, "coverage": 0,
                           "ears_conformance": False, "anchor": "",
                           "criterion_quality": ["vague"],
                           "lifecycle_state": "Quarantine"})
        + for_release({"validation_findings": ["v"], "execution_evidence": [],
                       "unmeasured": [{"scope": "s", "reason": "r"}],
                       "change_exposure": [{"severity": "critical", "what": "w"}]})
    )

    assert rows, "no candidates produced, so this asserts nothing"
    families = {rbs.taxonomy_of(r["category"]) for r in rows}
    assert families == {"process"}, (
        f"a model-derived risk landed outside the process taxonomy: "
        f"{sorted({r['category'] for r in rows if rbs.taxonomy_of(r['category']) != 'process'})}")


def test_a_register_may_hold_all_three_families_without_being_refused():
    """Validation asks "is this a real category"; a distribution asks "how are
    risks spread across ONE family". Only the second must not merge."""
    from metis_mcp.risk import register

    for category in ("Procurement", "Security", "Test environment"):
        findings = register.validate_risk({
            "id": "R-1", "description": "cause -> event -> effect",
            "category": category, "owner": "ana", "derived_from": "authored"})
        assert not [f for f in findings if f.rule == "RISK-CATEGORY"], category


def test_a_distribution_is_still_drawn_over_one_family():
    """Merging three taxonomies into one chart describes no decision anybody
    makes — the categories are not comparable and have different owners."""
    from metis_mcp.risk import rbs

    over_process = rbs.distribution(["Test data"], rbs.PROCESS_CATEGORIES)

    assert over_process["counts"]["Test data"] == 1
    assert "Procurement" not in over_process["counts"], (
        "a process distribution must not carry project categories")
