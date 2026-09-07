"""The risk toolkit: the arithmetic, the register's coherence, and the two
things it must refuse to do.

The refusals carry most of the value here. Every formula on the cheat sheet is
three lines and hard to get wrong; what is easy to get wrong is applying one to
an input it does not fit, and getting a plausible number back.
"""
import json

import pytest

from metis_mcp.risk import candidates as risk_candidates
from metis_mcp.risk import exposure as risk_exposure
from metis_mcp.risk import rbs, register
from metis_mcp.risk.exposure import RiskInputRefused


# --- the arithmetic, against worked examples -------------------------------

@pytest.mark.parametrize("o,m,p,expected,sd", [
    (4, 6, 14, 7.0, 1.6667),      # the cheat sheet's own worked example
    (10, 10, 10, 10.0, 0.0),      # no spread at all
    (1, 2, 3, 2.0, 0.3333),
])
def test_pert_matches_the_worked_examples(o, m, p, expected, sd):
    got = risk_exposure.pert(o, m, p)
    assert got["estimate"] == expected
    assert got["standard_deviation"] == sd


@pytest.mark.parametrize("prob,imp,score,band", [
    (1, 1, 1, "Low"),             # the four corners of the 5x5
    (1, 5, 5, "Low"),
    (5, 1, 5, "Low"),
    (5, 5, 25, "Very High"),
    (3, 4, 12, "High"),           # the first cell of the High band
    (2, 5, 10, "Medium"),         # ...and the last of Medium, so the boundary
])                                # is asserted from both sides
def test_the_five_by_five_bands_at_their_boundaries(prob, imp, score, band):
    got = risk_exposure.exposure(prob, imp)
    assert (got.score, got.band) == (score, band)


def test_every_cell_of_the_grid_has_a_band():
    for p in range(1, 6):
        for i in range(1, 6):
            assert risk_exposure.exposure(p, i).band in {
                "Low", "Medium", "High", "Very High"}


def test_emv_is_probability_times_amount():
    assert risk_exposure.emv(0.3, 50_000)["emv"] == 15_000.0


# --- the refusals, which are the point -------------------------------------

def test_emv_refuses_a_five_point_ordinal():
    """The failure this exists to prevent: `emv(3, 100_000)` is 300_000, looks
    entirely normal, and is five times too large. It ends up in a budget."""
    with pytest.raises(RiskInputRefused) as e:
        risk_exposure.emv(3, 100_000)
    assert "`exposure`" in str(e.value)      # says where the input belongs


def test_exposure_refuses_a_probability_that_is_really_a_fraction():
    with pytest.raises(RiskInputRefused) as e:
        risk_exposure.exposure(0.3, 4)
    assert "`emv`" in str(e.value)


def test_pert_refuses_unordered_estimates_rather_than_sorting_them():
    with pytest.raises(RiskInputRefused) as e:
        risk_exposure.pert(9, 6, 4)
    assert "9" in str(e.value) and "4" in str(e.value)


def test_an_exposure_score_says_it_is_ordinal():
    """A caller who reads the score as a quantity will average it across a
    portfolio. The basis line is the only thing standing in the way."""
    basis = risk_exposure.exposure(3, 3).basis.lower()
    assert "ordinal" in basis and "summed" in basis


# --- the RBS ---------------------------------------------------------------

def test_a_category_is_matched_case_insensitively():
    assert rbs.validate_category("technical") == "Technical"


def test_an_abbreviation_is_refused_with_the_full_name():
    with pytest.raises(rbs.UnknownCategory) as e:
        rbs.validate_category("Tech")
    assert "Technical" in str(e.value)


def test_the_distribution_reports_empty_categories_rather_than_dropping_them():
    """A category with no risks in it is the interesting one — nobody has looked
    at it — and a bar chart built from present keys alone cannot show that."""
    got = rbs.distribution(["Technical", "Technical"])
    assert got["counts"]["Technical"] == 2
    assert "External" in got["empty"]


# --- the register ----------------------------------------------------------

def _risk(**over):
    base = {"id": "R-1", "description": "d", "category": "Technical",
            "probability": 3, "impact": 4, "score": 12, "polarity": "threat",
            "response": "Mitigate", "owner": "a", "status": "open",
            "derived_from": "authored"}
    base.update(over)
    return base


def test_a_clean_register_produces_no_errors():
    assert not [f for f in register.validate([_risk()]) if f.severity == "error"]


def test_a_stale_score_is_an_error():
    """The worst register defect: somebody re-rated and did not recalculate, so
    the risk sorts wrongly in every report and looks completely normal."""
    codes = [f.rule for f in register.validate([_risk(score=15)])]
    assert "RISK-SCORE-STALE" in codes


def test_a_threat_response_on_an_opportunity_is_an_error():
    codes = [f.rule for f in register.validate(
        [_risk(polarity="opportunity", response="Mitigate", score=12)])]
    assert "RISK-RESPONSE-POLARITY" in codes


def test_the_opportunity_strategies_are_accepted_on_an_opportunity():
    codes = [f.rule for f in register.validate(
        [_risk(polarity="opportunity", response="Exploit")])]
    assert "RISK-RESPONSE-POLARITY" not in codes


# --- the provenance guard, and its sabotage check --------------------------

def test_the_summary_reports_authored_and_model_derived_apart():
    """C-11 one domain over. A model-derived risk says something is UNTESTED,
    not that it is LIKELY; averaging the two lets a coverage gap read as a
    forecast."""
    got = register.summarise([_risk(id="R-1"),
                              _risk(id="R-2", derived_from="model")])
    assert got["by_derivation"]["authored"] == 1
    assert got["by_derivation"]["model"] == 1
    assert got["mixed"] is True


def test_removing_the_derivation_split_fails_this_test():
    """The sabotage check the plan asks for: this asserts the guard is load
    bearing, not that a key exists. If `summarise` stopped splitting, the
    equality above would still pass against a single merged count — so pin the
    thing that would actually change."""
    merged = register.summarise([_risk(id=f"R-{n}", derived_from="model")
                                 for n in range(3)] + [_risk(id="R-9")])
    # Four risks, and the split must not be reconstructible from the total alone.
    assert sum(merged["by_derivation"].values()) == 4
    assert merged["by_derivation"]["model"] == 3
    assert merged["mixed"] is True
    # A register of one kind is NOT mixed, which is what makes `mixed` mean
    # something rather than being always-true noise.
    assert register.summarise([_risk()])["mixed"] is False


def test_a_model_derived_risk_carries_no_probability():
    """Métis observed a gap; it did not forecast a failure. A number invented to
    fill this column would read as though it had."""
    found = risk_candidates.from_change_review([
        {"severity": "critical", "what": "nothing validates this",
         "transition_id": "t01"}])
    assert found and all(c["probability"] is None for c in found)
    assert all(c["derived_from"] == register.MODEL for c in found)


def test_an_unmeasured_figure_is_a_risk_about_the_report():
    """Not about the behaviour — which may be perfectly healthy and merely
    unmeasured. The description has to say so or it reads as a defect."""
    found = risk_candidates.from_unmeasured(
        [{"figure": "coverage", "kind": "structural",
          "reason": "transition_skipped"}])
    assert found and "could not be" in found[0]["description"]
    assert found[0]["probability"] is None


# --- the tools -------------------------------------------------------------

def test_every_risk_tool_returns_json_with_an_ok_field():
    from metis_mcp import server

    for call in (lambda: server.risk_exposure(3, 4),
                 lambda: server.risk_emv(0.3, 100),
                 lambda: server.risk_pert(1, 2, 3),
                 lambda: server.risk_categories(),
                 lambda: server.risk_register_check(json.dumps([_risk()]))):
        assert "ok" in json.loads(call())


def test_a_refused_input_comes_back_as_a_reason_not_an_exception():
    """An MCP tool that raises gives the client an opaque error. The refusal is
    the useful half and has to survive as data."""
    from metis_mcp import server

    got = json.loads(server.risk_emv(3, 100))
    assert got["ok"] is False and "exposure" in got["reason"]


def test_the_register_tool_reports_a_parse_error_rather_than_raising():
    from metis_mcp import server

    got = json.loads(server.risk_register_check("{not json"))
    assert got["ok"] is False and "JSON" in got["reason"]


# --- the split may never lose a row -----------------------------------------

def test_the_derivation_split_always_sums_to_the_total():
    """A row whose `derived_from` is neither value used to be counted in neither
    bucket, so it vanished from the split — silently, in the one figure this
    module exists to keep honest. `validate` reports the bad value; the summary
    must not disagree with its own total while it does."""
    got = register.summarise([
        _risk(id="R-1", derived_from="authored"),
        _risk(id="R-2", derived_from="model"),
        _risk(id="R-3", derived_from="guesswork"),
    ])
    assert sum(got["by_derivation"].values()) == got["total"] == 3
    assert got["by_derivation"][register.UNKNOWN] == 1


def test_an_unrecognised_derivation_is_not_counted_as_authored():
    """The tempting fix — defaulting to `authored` — would file an unreadable
    row under the claim a person is accountable for."""
    got = register.summarise([_risk(derived_from="guesswork")])
    assert got["by_derivation"]["authored"] == 0


def test_summarise_folds_status_case_like_validate_does():
    """`validate_risk` accepts `closed`; a summary counting it as open would
    contradict the validation of the very same file."""
    assert register.summarise([_risk(status="closed")])["closed"] == 1


# --- the CLI verb -----------------------------------------------------------

def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    return path


def _run(path, *extra, verb="check"):
    from metis_mcp.mbt.cli import main

    return main(["risk", verb, str(path), *extra])


def test_a_clean_register_exits_zero(tmp_path):
    assert _run(_write(tmp_path, "r.json", [_risk()])) == 0


def test_a_register_with_an_error_exits_one(tmp_path):
    """The reason the verb exists: a pipeline can fail on this."""
    assert _run(_write(tmp_path, "r.json", [_risk(score=15)])) == 1


def test_a_warning_alone_does_not_fail_unless_strict(tmp_path):
    path = _write(tmp_path, "r.json", [
        _risk(id="RM-1", derived_from="model", probability=None, score=None)])
    assert _run(path) == 0
    assert _run(path, "--strict") == 1


def test_a_missing_file_exits_two_not_one(tmp_path):
    """Distinct from a failed check: CI should be able to tell "the register is
    wrong" from "the register is not there"."""
    assert _run(tmp_path / "absent.json") == 2


def test_malformed_json_exits_two(tmp_path):
    path = tmp_path / "r.json"
    path.write_text("{not json")
    assert _run(path) == 2


# --- the consolidated report ------------------------------------------------

def test_the_report_keeps_the_derivations_apart_in_every_band():
    """The whole reason the report exists rather than a total: a band holding
    two authored risks and one model-derived one is not three of a kind."""
    from metis_mcp.risk.report import consolidate

    got = consolidate([_risk(id="R-1", probability=4, impact=5),
                       _risk(id="R-2", probability=4, impact=5,
                             derived_from="model")])
    assert got["by_band"]["Very High"] == {"authored": 1, "model": 1, "unknown": 0}


def test_the_report_computes_no_overall_score():
    """The figure a consolidated report is most often asked for and must not
    produce. Asserted as an absence AND as a stated refusal, because an absence
    alone would pass if the key were simply renamed."""
    from metis_mcp.risk.report import consolidate

    got = consolidate([_risk()])
    for key in got:
        assert "overall" not in key and "average" not in key
    assert "ordinal rank" in got["no_single_score"]


def test_an_unrated_risk_is_counted_not_dropped():
    """A model-derived half with no probabilities set would otherwise make the
    register look empty in a band chart, and the reason — nobody has rated it —
    is the finding."""
    from metis_mcp.risk.report import consolidate

    got = consolidate([_risk(id="RM-1", probability=None, derived_from="model")])
    assert got["unrated"]["model"] == 1
    assert sum(sum(b.values()) for b in got["by_band"].values()) == 0


def test_the_band_is_recomputed_and_never_read_from_a_stale_score():
    """`score: 25` on a 3x4 risk must land in High, not Very High. A report that
    trusted the column would put the row in the wrong band on every review."""
    from metis_mcp.risk.report import consolidate

    got = consolidate([_risk(probability=3, impact=4, score=25)])
    assert sum(got["by_band"]["Very High"].values()) == 0
    assert sum(got["by_band"]["High"].values()) == 1


def test_empty_categories_are_named_rather_than_omitted():
    from metis_mcp.risk.report import consolidate

    got = consolidate([_risk(category="Technical")])
    assert "External" in got["empty_categories"]
    assert "Technical" not in got["empty_categories"]


def test_a_high_risk_with_no_owner_or_response_is_listed():
    from metis_mcp.risk.report import consolidate

    got = consolidate([_risk(id="R-9", probability=4, impact=5,
                             owner="", response="")])
    assert "R-9" in got["without_owner"] and "R-9" in got["without_response"]


def test_a_closed_risk_does_not_need_attention():
    from metis_mcp.risk.report import consolidate

    got = consolidate([_risk(probability=5, impact=5, status="Closed")])
    assert got["needs_attention"] == []


def test_the_report_verb_prints_and_exits_zero_despite_errors(tmp_path):
    """`report` is for reading, `check` is for gating. Refusing to print the
    report because one row is malformed would withhold the thing asked for."""
    path = _write(tmp_path, "r.json", [_risk(score=15)])
    assert _run(path, verb="report") == 0
    assert _run(path, "--strict", verb="report") == 1
    assert _run(path, verb="check") == 1


# --- the cheat sheet is covered, and that is checkable ----------------------

def _risk_skills() -> dict:
    """Every skill in the risk family, by name."""
    from metis_mcp.agent_generator import read_skills

    return {s.name: s for s in read_skills() if "risk-manager" in s.name}


def test_every_area_of_the_reference_names_a_skill_that_exists():
    """"The cheat sheet is fully implemented" as a check rather than a claim.

    Four of the twelve areas had a skill and eight did not, and nothing in the
    tree recorded which was which — a reader could not tell whether `response`
    covered opportunities without opening it, and neither could a test.
    """
    from metis_mcp.risk.areas import AREAS

    skills = _risk_skills()
    assert len(AREAS) == 12, "the reference has twelve areas"
    for area in AREAS:
        assert area.skill in skills, (
            f"area {area.section} ({area.name}) names {area.skill!r}, which is "
            f"not a skill. Known: {sorted(skills)}")


def test_every_risk_skill_claims_an_area_or_is_named_as_beyond_it():
    """The other direction, so a new specialist cannot appear unaccounted for."""
    from metis_mcp.risk.areas import (
        AREAS, BEYOND_THE_REFERENCE, TESTING_AREAS,
    )

    owned = {a.skill for a in AREAS} | set(BEYOND_THE_REFERENCE) | {
        a.skill for a in TESTING_AREAS}
    for name in _risk_skills():
        assert name in owned, (
            f"{name} carries no area and is not listed in "
            f"BEYOND_THE_REFERENCE — say which of the twelve it covers, or "
            f"record that it is something Métis adds")


def _all_skills() -> dict:
    """Every skill on disk, not only the risk family."""
    from metis_mcp.agent_generator import read_skills

    return {s.name: s for s in read_skills()}


def test_every_testing_area_names_a_skill_that_exists():
    """The second reference. Risk-based testing (ISO/IEC/IEEE 29119-2) is its
    own body of practice and none of its sections exist in the project one.

    Checked against ALL skills rather than the risk family, because these
    deliberately cross the boundary: prioritisation runs in `metis-test-generate`
    and coverage measurement in `metis-coverage-report`, since that is where the
    procedure actually is. Recording it here is what makes the wiring checkable.
    """
    from metis_mcp.risk.areas import TESTING_AREAS

    skills = _all_skills()
    for area in TESTING_AREAS:
        assert area.skill in skills, (
            f"testing area {area.section} ({area.name}) names {area.skill!r}, "
            f"which is not a skill")


def test_a_skill_outside_the_risk_family_owns_a_testing_area():
    """The claim above is only meaningful if the crossing is real — if every
    testing area resolved back into the risk family this would be a second name
    for the same map."""
    from metis_mcp.risk.areas import TESTING_AREAS

    crossing = [a for a in TESTING_AREAS if "risk-manager" not in a.skill]

    assert crossing, "no testing area is owned outside the risk family"


def test_each_testing_area_is_owned_by_exactly_one_skill():
    from metis_mcp.risk.areas import TESTING_AREAS

    owners = [a.skill for a in TESTING_AREAS]

    assert len(owners) == len(set(owners)), f"an owner claims two areas: {owners}"


def test_the_two_references_are_not_merged():
    """A project risk and a product risk are rated by different people against
    different objectives. One map holding both would say the project reference
    contains sections it does not."""
    from metis_mcp.risk.areas import AREAS, TESTING_AREAS, describe

    described = describe()

    assert "areas" in described and "testing_areas" in described
    assert len(described["areas"]) == len(AREAS) == 12
    assert len(described["testing_areas"]) == len(TESTING_AREAS)
    assert {a.name for a in AREAS}.isdisjoint({a.name for a in TESTING_AREAS})


def test_each_area_is_owned_by_exactly_one_skill():
    """Two skills claiming one area is two procedures for one job."""
    from metis_mcp.risk.areas import AREAS

    seen: dict = {}
    for area in AREAS:
        # The parent owns the lifecycle and nothing else; every other area is
        # one specialist's.
        assert area.skill not in seen, (
            f"{area.skill} claims areas {seen[area.skill]} and {area.section}")
        seen[area.skill] = area.section


# --- the gather-or-ask ledger ----------------------------------------------

def test_every_input_says_what_its_absence_means():
    from metis_mcp.risk.inputs import ASSESSMENTS

    for name, declared in ASSESSMENTS.items():
        for item in declared:
            assert item.absent_means.strip(), (
                f"{name}/{item.name} does not say what its absence means")


def test_no_absent_means_reads_as_reassurance():
    """That string is printed where the value should have been. If it ever says
    'no risk', a missing input becomes a clean bill in the reader's eye."""
    from metis_mcp.risk.inputs import ASSESSMENTS

    for name, declared in ASSESSMENTS.items():
        for item in declared:
            lowered = item.absent_means.lower()
            for banned in ("no risk", "is fine", "is safe", "nothing to worry"):
                assert banned not in lowered, (
                    f"{name}/{item.name} absent_means reads as reassurance: "
                    f"{item.absent_means!r}")


def test_every_asked_input_carries_a_question_not_a_topic():
    """A topic gets a shrug. The question has to be answerable as written."""
    from metis_mcp.risk.inputs import ASKED, ASSESSMENTS

    for name, declared in ASSESSMENTS.items():
        for item in declared:
            if item.source != ASKED:
                continue
            # A "?" anywhere, not at the end: the best of these ask the
            # question and then say how to answer it ("...what does the
            # business lose? Name the consequence, not a severity word.").
            assert "?" in item.question, f"{name}/{item.name} has no question"
            assert len(item.question.split()) >= 6, (
                f"{name}/{item.name}'s question is a topic, not a question: "
                f"{item.question!r}")


def test_every_gathered_input_names_the_tool_that_supplies_it():
    from metis_mcp.risk.inputs import ASSESSMENTS, GATHERED

    for name, declared in ASSESSMENTS.items():
        for item in declared:
            if item.source == GATHERED:
                assert item.tool, f"{name}/{item.name} names no tool"


def test_a_missing_required_input_makes_the_assessment_incomplete():
    """The rule the whole design exists for."""
    from metis_mcp.risk.inputs import INCOMPLETE, completeness

    got = completeness("requirement", gathered={}, answers={})
    assert got["status"] == INCOMPLETE
    assert "business_criticality" in got["missing_required"]


def test_incomplete_never_reads_as_low_risk():
    """The sabotage check. Asserting the STATUS alone would pass if the message
    were replaced with 'no issues found' — which is exactly the failure this
    guards, so pin the wording that stops a reader concluding it."""
    from metis_mcp.risk.inputs import completeness

    got = completeness("release", gathered={}, answers={})
    means = got["means"].lower()
    assert "not a low-risk" in means or "unfinished" in means, (
        "the incomplete message must say it is unfinished rather than clean")
    for banned in ("no risk", "looks good", "nothing found"):
        assert banned not in means


def test_a_fully_supplied_assessment_is_complete():
    """The complement — otherwise `incomplete` could be hardcoded and pass."""
    from metis_mcp.risk.inputs import (
        ASKED, COMPLETE, GATHERED, RELEASE_INPUTS, completeness,
    )

    got = completeness(
        "release",
        gathered={i.name: "x" for i in RELEASE_INPUTS if i.source == GATHERED},
        answers={i.name: "x" for i in RELEASE_INPUTS if i.source == ASKED})
    assert got["status"] == COMPLETE
    assert got["missing_required"] == []


# --- the derivation ---------------------------------------------------------

def test_a_missing_fact_produces_no_risk_at_all():
    """Absence never invents a finding. "We did not check" and "we checked and
    it was fine" are different answers and a risk list holds neither."""
    from metis_mcp.risk.assessment import for_release, for_requirement

    assert for_requirement({}) == []
    # `for_release` fires on execution evidence being absent, which IS the
    # finding — so assert the shape rather than emptiness.
    assert all(c["probability"] is None for c in for_release({}))


def test_every_derived_candidate_names_the_tool_behind_it():
    from metis_mcp.risk.assessment import for_requirement

    found = for_requirement({"criteria_count": 0, "ears_conformance": False})
    assert found
    for candidate in found:
        assert candidate["derived_by"], f"{candidate['id']} names no tool"
        assert candidate["probability"] is None
        assert candidate["derived_from"] == register.MODEL


# --- the document survives being edited ------------------------------------

def _doc_with(**over):
    from metis_mcp.risk import document
    from metis_mcp.risk.assessment import for_requirement

    facts = {"criteria_count": 0, "ears_conformance": False}
    return document.build("requirement", "REQ-1", gathered=facts,
                          candidates=for_requirement(facts),
                          completeness={"status": "incomplete",
                                        "missing_required": ["business_criticality"]},
                          **over)


def test_a_hand_set_probability_survives_regeneration():
    """The claim `document.merge` exists to make. Without it the second run
    silently deletes every rating anybody set, and looks successful doing it."""
    from metis_mcp.risk import document

    first = document.render_markdown(_doc_with())
    edited = first.replace("| RM-RQ-001 |", "| RM-RQ-001 |", 1)
    rows = document.parse(first)
    assert "RM-RQ-001" in rows, "the row to edit was not found"

    # The category is read back rather than hardcoded: this test is about the
    # five human columns surviving, and pinning the generated half here made it
    # fail when model-derived risks were refiled from the project taxonomy into
    # the process one — a change it has no opinion about.
    row = rows["RM-RQ-001"]
    edited = first.replace(
        f"| RM-RQ-001 | {row['description']} | {row['category']} | — | 5 | — | — | Open | — |",
        f"| RM-RQ-001 | {row['description']} | {row['category']} | 4 | 5 | "
        f"ana | Mitigate | Open | mine |")
    assert edited != first, "the edit did not apply"

    merged = document.merge(_doc_with(), edited)
    kept = {r["id"]: r for r in merged["candidates"]}["RM-RQ-001"]
    assert kept["probability"] == "4"
    assert kept["owner"] == "ana"
    assert kept["response"] == "Mitigate"
    assert kept["notes"] == "mine"
    # And the generated half is still regenerated.
    assert kept["impact"] == 5


def test_a_hand_added_row_survives_regeneration():
    """The eleven categories Métis cannot see are most of the register. A
    regeneration that deleted them would teach people not to edit the file."""
    from metis_mcp.risk import document

    first = document.render_markdown(_doc_with())
    edited = first.replace(
        "\n\n## How to read this",
        "\n| R-SUP-1 | supplier may slip | External | 3 | 4 | sam | Transfer "
        "| Open | — | hand-added |\n\n## How to read this")
    merged = document.merge(_doc_with(), edited)
    rows = {r["id"]: r for r in merged["candidates"]}
    assert "R-SUP-1" in rows
    assert rows["R-SUP-1"]["derived_from"] == "authored"
    assert merged["carried_over"] == ["R-SUP-1"]


def test_the_gathered_facts_table_is_not_read_as_broken_risk_rows():
    """It was. Parsing every pipe row flagged the three-column facts table as
    six malformed risks, so a correct run printed a warning naming things that
    were never risks — and a warning that cries wolf gets ignored."""
    from metis_mcp.risk import document

    assert document.parse_problems(document.render_markdown(_doc_with())) == []


def test_a_genuinely_malformed_risk_row_is_still_reported():
    """The complement, so the fix above did not make the check vacuous."""
    from metis_mcp.risk import document

    broken = document.render_markdown(_doc_with()).replace(
        "\n\n## How to read this", "\n| R-BAD-1 | half a row | Quality |\n\n## How to read this")
    assert document.parse_problems(broken) == ["R-BAD-1"]


def test_the_document_says_incomplete_before_it_says_anything_else():
    """Burying it below the findings is how an unfinished assessment gets read
    as a clean one."""
    from metis_mcp.risk import document

    text = document.render_markdown(_doc_with())
    assert "Incomplete" in text
    assert text.index("Incomplete") < text.index("## Risks")


# --- an answer survives regeneration, so `incomplete` can end ---------------
#
# `render_markdown` has always written "Answers on record" and nothing read it
# back, so the `ASKED` half of an assessment could not be supplied through any
# surface: the workflow's gate records who accepted, the CLI passed no answers
# at all, and `merge` carried the risk rows but not the answers. Every
# assessment therefore reported `incomplete` for ever.
#
# That is the failure `risk/inputs.py` is written to prevent. A status that
# cannot change is one readers learn to skip, and it is the same word that has
# to carry a genuinely unfinished assessment when one turns up.


def _answers_table(names, value="an answer somebody gave"):
    """The section as `render_markdown` writes it, for a test to edit in."""
    return "\n".join(["", "### Answers on record", "",
                       "| Question | Answer |", "|---|---|"]
                      + [f"| {n} | {value} |" for n in names]
                      + ["", "## Risks", ""])


def test_an_answer_written_into_the_document_is_read_back():
    from metis_mcp.risk import document

    text = document.render_markdown(_doc_with(answers={"volatility": "changes weekly"}))

    assert document.parse_answers(text) == {"volatility": "changes weekly"}


def test_an_answer_survives_regeneration():
    """The same claim `test_a_hand_set_probability_survives_regeneration` makes
    for the risk table, for the half of the document that had no such guard."""
    from metis_mcp.risk import document

    edited = document.render_markdown(_doc_with()) + _answers_table(["business_criticality"])

    merged = document.merge(_doc_with(), edited)

    assert merged["answers"]["business_criticality"] == "an answer somebody gave"


def test_this_run_answer_wins_over_the_one_already_in_the_file():
    """A fresh acceptance is newer than the record of the last one."""
    from metis_mcp.risk import document

    edited = document.render_markdown(_doc_with()) + _answers_table(
        ["accepted_by", "volatility"], value="bob")

    merged = document.merge(_doc_with(answers={"accepted_by": "alice"}), edited)

    assert merged["answers"]["accepted_by"] == "alice"
    assert merged["answers"]["volatility"] == "bob", "the rest is kept"


def test_answering_every_required_question_ends_the_incomplete_status():
    """The transition that was unreachable. Before the round-trip existed,
    `status` was a constant across the whole tool surface."""
    from metis_mcp.risk import document, inputs

    gathered = {i.name: "x" for i in inputs.inputs_for("requirement")
                if i.source == inputs.GATHERED}
    required = [i.name for i in inputs.inputs_for("requirement")
                if i.source == inputs.ASKED and i.required]

    before = inputs.completeness("requirement", gathered, {})
    assert before["status"] == inputs.INCOMPLETE

    edited = document.render_markdown(_doc_with()) + _answers_table(required)
    merged = document.merge(
        document.build("requirement", "REQ-1", gathered=gathered), edited)
    after = inputs.completeness("requirement", gathered, merged["answers"])

    assert after["status"] == inputs.COMPLETE
    assert "\u26a0 Incomplete" not in document.render_markdown(
        {**merged, "completeness": after})


def test_the_gathered_table_is_never_read_as_an_answer():
    """The document holds three pipe tables. `_risk_section` was scoped because
    reading them as one turned gathered facts into malformed risk rows; the
    answers parser is scoped for the same reason, in the other direction."""
    from metis_mcp.risk import document

    text = document.render_markdown(_doc_with())   # carries gathered facts

    assert document.parse_answers(text) == {}, (
        "the gathered-facts table is not a set of answers")


# --- the workflow -----------------------------------------------------------

def test_every_declared_gathered_input_has_a_surface_that_can_supply_it():
    """A declared input nothing can populate is a contract with one side missing.

    `change_exposure` and `open_model_risks` were declared on `RELEASE_INPUTS`
    with a tool named, and `release_risk` accepted no argument that could reach
    either — so both reported as "not gathered" for a reason that was never the
    caller's, permanently. Asserted by parameter name rather than by calling the
    tool, because the graph this needs is not available to this suite.
    """
    import inspect

    from metis_mcp import server
    from metis_mcp.risk import inputs

    accepted = set(inspect.signature(server.release_risk).parameters)
    # The argument that carries each gathered input into the tool.
    supplies = {"coverage": "journey", "validation_findings": "journey",
                "unmeasured": "journey", "confidence_capped_by": "journey",
                "execution_evidence": "journey", "execution_stale": "journey",
                "change_exposure": "changed_files",
                "open_model_risks": "register_json"}

    for item in inputs.inputs_for(inputs.RELEASE):
        if item.source != inputs.GATHERED:
            continue
        assert item.name in supplies, (
            f"{item.name} is declared gathered and this test does not know "
            f"which argument supplies it")
        assert supplies[item.name] in accepted, (
            f"{item.name} names tool `{item.tool}` and release_risk takes no "
            f"argument that could reach it")


def test_the_acceptance_gate_is_guarded_by_a_check_and_not_only_by_its_handler():
    """Every other gate here is guarded twice — a handler decides what to
    report, a check decides whether the stage may pass. This one declared no
    checks at all, so its whole guarantee rested on nobody editing the handler.
    """
    from metis_mcp.workflow import checks
    from metis_mcp.workflow.stages import WORKFLOWS

    gate = WORKFLOWS["risk-review"].stage("risk-acceptance")

    assert gate.is_gate
    assert "risk_is_accepted" in gate.checks
    assert checks.get("risk_is_accepted") is not None, (
        "a workflow naming a check nothing implements fails the lint")


@pytest.mark.parametrize("answers,accepted", [
    ({}, False),
    ({"accepted_by": ""}, False),
    ({"accepted_by": "   "}, False),
    ({"accepted_by": "alice"}, True),
])
def test_the_acceptance_check_requires_a_named_person(answers, accepted):
    """`risk-governance.md` requires who / when / what / why. Without the first
    there is no audit trail at all, so an unsigned acceptance may not pass."""
    import types

    from metis_mcp.workflow import checks

    result = checks.get("risk_is_accepted")(
        types.SimpleNamespace(risk_answers=answers))

    assert bool(result) is accepted
    if not accepted:
        assert result.reason, "a check that fails must say what failed (F-9)"


def test_the_risk_review_workflow_halts_for_a_person():
    """Without the gate the run computes an assessment from the half Métis can
    see and presents it as whole."""
    from metis_mcp.workflow.stages import WORKFLOWS

    workflow = WORKFLOWS["risk-review"]
    gates = [s for s in workflow.stages if s.is_gate]
    assert len(gates) == 1 and gates[0].name == "risk-acceptance"


def test_the_open_questions_stage_never_blocks():
    """The questions ARE its output (F-4). A run that stopped there would deny
    the reader the list they need in order to answer."""
    from metis_mcp.workflow.stages import WORKFLOWS

    stage = WORKFLOWS["risk-review"].stage("open-questions")
    assert stage is not None and stage.blocking is False


def test_risk_review_requires_no_prior_approval():
    """A risk review of an unapproved model is when it is most useful — "what
    would we be accepting" is a pre-approval question."""
    from metis_mcp.workflow.stages import WORKFLOWS

    assert WORKFLOWS["risk-review"].preconditions == ()


def test_every_risk_review_stage_has_a_registered_handler():
    from metis_mcp.workflow.stages import WORKFLOWS, registered_handlers

    known = registered_handlers()
    for stage in WORKFLOWS["risk-review"].ordered:
        assert stage.handler in known, f"{stage.name} names {stage.handler}"
