"""Pre-import analysis: the four readings, and the gate before landing.

**What this file is guarding.** `intake` used to fetch, validate, land, and only
then assess risk — so the first moment anybody saw what was wrong with a claim
was after it was a node in the graph. Two stages now sit before `land`, and the
property they rest on is narrow and easy to get wrong in either direction:

- refuse too much and Métis only accepts claims that are already finished, which
  is not what intake is for;
- refuse too little and a need nobody has specified becomes a node nothing can
  ever be checked against (D-1).

So most of what follows asserts exactly where the line is.
"""
from __future__ import annotations

import sys

from metis_mcp.analysis import areas, gaps, readiness

INTENT_FILE = {
    "intent_version": "metis.intent/1",
    "area": "records",
    "intents": [
        {"id": "INT-1", "statement": "Users should be able to archive a record."},
        {"id": "INT-2", "statement": "Records should be tidy."},
    ],
    "specifications": [
        {"id": "SPEC-1",
         "statement": "When a user archives a record, the system shall hide it "
                      "from the default list.",
         "intent": "INT-1", "provenance": "independently_authored",
         "entities": ["Record"]},
    ],
}

UIF = {
    "scope": {"source_key": "ABC-1", "source_system": "jira"},
    "summary": "Archive a record",
    "description": "When a user archives a record the system shall hide it.",
}


def _intent_file(raw=None):
    """An `IntentFile` from a dict, without touching the filesystem."""
    import json
    import tempfile
    from pathlib import Path

    from metis_mcp.model_sources.intent import load

    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "intent.json"
        target.write_text(json.dumps(raw if raw is not None else INTENT_FILE))
        return load(target)


# --------------------------------------------------------------------------
# The gap taxonomy.
# --------------------------------------------------------------------------

def test_every_gap_names_the_aspect_that_found_it_and_what_closes_it():
    """A gap with no closer is a complaint. Naming the skill or tool that closes
    it is what makes the ledger a work list rather than a verdict."""
    found = [gaps.no_specification("INT-1"), gaps.no_criteria("REQ-1"),
             gaps.untestable("INT-2", "no observable outcome")]
    found += gaps.from_wording("REQ-1", False, ())
    found += gaps.from_design("scope", [{"name": "environments",
                                         "absent_means": "x", "question": "y?"}])
    found += gaps.from_risk("scope", [{"name": "business_criticality",
                                       "absent_means": "x", "question": "y?"}])
    assert found
    for gap in found:
        assert gap.aspect in gaps.ASPECTS, f"{gap.aspect} is not an aspect"
        assert gap.what.strip(), "a gap that says nothing is missing"
        assert gap.closes_with.strip(), f"{gap.what!r} names nothing that closes it"


def test_no_gap_reads_as_reassurance():
    """The same rule the two ledgers keep: a gap whose text says "fine" turns a
    missing input into a clean bill in the reader's eye."""
    banned = ("no risk", "is fine", "is safe", "nothing to worry", "all good")
    found = [gaps.no_specification("INT-1"), gaps.no_criteria("REQ-1")]
    for gap in found:
        for phrase in banned:
            assert phrase not in gap.what.lower(), gap.what


def test_the_only_blocking_gaps_are_the_ones_that_cannot_be_represented():
    """**The line, asserted from the permissive side.** A claim nobody has
    costed, whose environments are unlisted and which has no criteria yet is a
    normal thing to import. Refusing it would mean Métis only ever accepted
    claims that were already finished."""
    reported = ([gaps.no_criteria("REQ-1")]
                + gaps.from_wording("REQ-1", False, ())
                + gaps.from_design("s", [{"name": "environments",
                                          "absent_means": "x", "question": "y?"}])
                + gaps.from_risk("s", [{"name": "business_criticality",
                                        "absent_means": "x", "question": "y?"}]))
    assert reported, "nothing to check"
    assert not any(g.blocks_import for g in reported), (
        "an unfinished claim must still be importable — only an unrepresentable "
        "one is refused")
    assert gaps.readiness(reported)["status"] == gaps.READY


def test_a_need_with_no_specification_blocks():
    """And from the strict side. Landing it puts a node in the graph that
    nothing can ever be checked against (D-1)."""
    verdict = gaps.readiness([gaps.no_specification("INT-2")])
    assert verdict["status"] == gaps.NOT_READY
    assert verdict["blocking"]
    assert "CANNOT BE IMPORTED" in verdict["means"]


def test_every_validator_problem_blocks_because_landing_refuses_them_all():
    """**One definition rather than two, and this test exists because keeping
    two went wrong.** An earlier version had its own set of "serious" intent
    problems; deduplicating a gap moved a missing specification onto a row the
    set did not name, and a need nobody had specified came back `ready`.

    `cmd_intent_land` refuses the file if `validate` returns anything at all, so
    a validator problem blocks here because it will block there.
    """
    from metis_mcp.model_sources.intent import validate

    problems = validate(_intent_file())
    assert problems, "the fixture must carry at least one problem"
    found = gaps.from_intent(problems)
    assert all(g.blocks_import for g in found), (
        "a validator problem that does not block here would let a run reach "
        "`land`, which then refuses it — a gate that passes what the next step "
        "rejects is worse than no gate")


def test_readiness_computes_no_score():
    """The four aspects are not commensurable: a missing statement and a missing
    environment list are not two thirds and five sixths of ready."""
    verdict = gaps.readiness([gaps.no_criteria("REQ-1")])
    for key, value in verdict.items():
        assert "percent" not in key and "score" not in key, key
        assert not isinstance(value, float), f"{key} is a scalar score"


# --------------------------------------------------------------------------
# The four readings, composed.
# --------------------------------------------------------------------------

def test_both_document_shapes_reduce_to_subjects():
    """An intent file and a UIF are read by structure rather than by a flag: a
    caller that had to say which it had would eventually say wrong."""
    from_intent = readiness.subjects_of(_intent_file())
    assert [s.id for s in from_intent] == ["INT-1", "INT-2"]
    assert from_intent[0].specifications and not from_intent[1].specifications

    from_uif = readiness.subjects_of(UIF)
    assert [s.id for s in from_uif] == ["ABC-1"]
    assert from_uif[0].statement == "Archive a record"


def test_an_unknown_shape_yields_no_subjects_rather_than_raising():
    assert readiness.subjects_of(None) == []
    assert readiness.subjects_of("not a document") == []


def test_a_missing_specification_is_reported_once_and_not_twice():
    """**The defect this test was written after finding.** `intent.validate`
    already reports a need with no specification, and re-deriving it here filed
    every such need twice — once in the validator's words and once in ours. A
    duplicated gap inflates the count a reader judges the claim by, and the
    second row looks like a second problem."""
    from metis_mcp.model_sources.intent import validate

    document = _intent_file()
    result = readiness.analyse(document, intent_problems=validate(document))
    about_int2 = [g for g in result["gaps"]
                  if g["aspect"] == gaps.INTENT and g["subject"] == "INT-2"]
    assert len(about_int2) == 1, (
        f"INT-2's missing specification is reported {len(about_int2)} times")


def test_every_aspect_is_represented_in_a_full_reading():
    """Parametrised over `ASPECTS` rather than a hardcoded four, so a sixth
    reading added without a way to produce a gap fails here instead of shipping
    as a heading that is always empty."""
    document = _intent_file()
    result = readiness.analyse(
        document,
        wording={"INT-1": (False, ()), "INT-2": (False, ())},
        design_missing=[{"name": "environments", "absent_means": "x",
                         "question": "which environments exist?"}],
        risk_missing=[{"name": "business_criticality", "absent_means": "y",
                       "question": "what does the business lose?"}],
        consumers_unknown=3, consumers_total=4)
    for aspect in gaps.ASPECTS:
        assert result["counts"][aspect] > 0, f"the {aspect} reading found nothing"


def test_the_document_renders_every_aspect_it_declares():
    """A heading with no explanation beside it is what a `KeyError` here used to
    be — the fifth reading arrived before the table that describes them did."""
    from metis_mcp.analysis import document as analysis_document

    result = readiness.analyse(_intent_file())
    text = analysis_document.render_markdown(
        analysis_document.build("ABC-1", result))
    for aspect in gaps.ASPECTS:
        assert f"| {aspect} |" in text, f"{aspect} has no row in the document"


def test_a_well_formed_intent_is_ready_and_still_carries_gaps():
    """`ready` is not `good`, and this is the shape that proves it: a claim with
    nothing blocking it and a dozen open questions travelling with it."""
    document = _intent_file({
        "intent_version": "metis.intent/1", "area": "records",
        "intents": [{"id": "INT-1",
                     "statement": "Users should be able to archive a record."}],
        "specifications": [
            {"id": "SPEC-1",
             "statement": "When a user archives a record, the system shall hide "
                          "it from the default list.",
             "intent": "INT-1", "provenance": "independently_authored"}]})
    result = readiness.analyse(
        document,
        risk_missing=[{"name": "business_criticality", "absent_means": "y",
                       "question": "what does the business lose?"}])
    assert result["status"] == gaps.READY
    assert result["gaps"], "a ready claim with no reported gap proves nothing"
    assert "never" not in result["means"]
    assert "not that anybody has agreed" in result["means"]


def test_untestability_is_supplied_and_never_inferred():
    """That verdict blocks an import. A heuristic that got it wrong would refuse
    a real requirement at the door, so it is a person's judgement."""
    document = _intent_file()
    without = readiness.analyse(document)
    assert not any(g["aspect"] == gaps.DESIGN and g["blocks_import"]
                   for g in without["gaps"])

    with_reason = readiness.analyse(
        document, untestable_reasons={"INT-1": "no observable outcome"})
    assert any(g["blocks_import"] and g["aspect"] == gaps.DESIGN
               for g in with_reason["gaps"])


# --------------------------------------------------------------------------
# The aspect map, in both directions.
# --------------------------------------------------------------------------

def _all_skills() -> dict:
    from metis_mcp.agent_generator import read_skills

    return {s.name: s for s in read_skills()}


def test_every_aspect_names_a_skill_that_exists():
    known = _all_skills()
    for aspect in areas.ASPECT_OWNERS:
        assert aspect.skill in known, (
            f"aspect {aspect.key} names {aspect.skill!r}, which is not a skill")
    assert areas.CONSOLIDATION in known
    assert areas.SCOPE_SKILL in known


def test_every_business_analyst_skill_is_accounted_for():
    """The other direction, so a new specialist cannot appear unmapped."""
    owned = ({a.skill for a in areas.ASPECT_OWNERS}
             | {areas.CONSOLIDATION, areas.SCOPE_SKILL})
    family = [name for name in _all_skills()
              if name.startswith("metis-business-analyst")]
    assert len(family) == 3, f"expected a parent and two specialists: {family}"
    for name in family:
        assert name in owned, f"{name} carries no aspect and is not consolidation"


def test_three_of_the_four_readings_are_owned_outside_this_family():
    """**The hand-off, and it has to be real.** "Pass it to the test designer
    and the risk manager for a more detailed review" is a sentence in a prompt
    unless something records it. Two of the four aspects plus the requirement
    reading resolve to skills in other families, and each already runs the
    procedure it owns — a second copy here would drift from the one that runs.
    """
    consulted = areas.consulted()
    assert set(consulted) == {"metis-knowledge-capture", "metis-test-design",
                              "metis-risk-manager-requirement-risk"}
    for name in consulted:
        assert not name.startswith("metis-business-analyst"), (
            f"{name} is claimed as consulted and is in this family")


def test_the_parent_routes_to_every_specialist_and_names_who_it_consults():
    from pathlib import Path

    skills = Path(__file__).resolve().parent.parent / "plugins" / "metis" / "skills"
    text = (skills / "metis-business-analyst" / "SKILL.md").read_text()
    for name in ("metis-business-analyst-intent", "metis-business-analyst-scope"):
        assert name in text, f"the parent does not route to {name}"
    for name in areas.consulted():
        assert name in text, f"the parent does not say it consults {name}"


# --------------------------------------------------------------------------
# The document.
# --------------------------------------------------------------------------

def _rendered(document=None):
    from metis_mcp.analysis import document as analysis_document

    result = readiness.analyse(document if document is not None else _intent_file())
    return analysis_document.render_markdown(
        analysis_document.build("ABC-1", result))


def test_the_verdict_sits_above_the_gaps():
    text = _rendered()
    assert "Not ready to import" in text
    assert text.index("Not ready to import") < text.index("## Gaps")


def test_a_ready_document_says_ready_is_not_agreed():
    text = _rendered(UIF)
    assert "Ready to import" in text
    assert "not the same as ready to build" in text
    assert "Nobody has agreed with it" in text


def test_regeneration_preserves_an_analyst_s_answer_and_their_own_gap():
    """A gap an analyst adds is a gap none of the four readers can see, which is
    the case this file is editable for."""
    from metis_mcp.analysis import document as analysis_document

    result = readiness.analyse(_intent_file())
    first = analysis_document.render_markdown(
        analysis_document.build("ABC-1", result))

    target = sorted(analysis_document.parse(first))[0]
    line = next(l for l in first.splitlines() if l.startswith(f"| {target} "))
    edited = line.rsplit("|", 3)[0] + "| carol | answered in ABC-9 |"
    hand = ("| gap-MINE01 | analyst | INT-1 | the archive is reversible and "
            "nobody said for how long | ask product | — | — | carol | ours |")
    text = first.replace(line, edited + "\n" + hand)

    merged = analysis_document.merge(
        analysis_document.build("ABC-1", result), text)
    assert "gap-MINE01" in merged["carried_over"]
    after = analysis_document.parse(analysis_document.render_markdown(merged))
    assert after[target]["owner"] == "carol"
    assert after["gap-MINE01"]["notes"] == "ours"


def test_a_row_that_lost_its_shape_is_reported_rather_than_dropped():
    from metis_mcp.analysis import document as analysis_document

    text = _rendered()
    line = next(l for l in text.splitlines() if l.startswith("| gap-"))
    broken = text.replace(line, "| gap-BROKEN | only | two |")
    assert "gap-BROKEN" in analysis_document.parse_problems(broken)


def test_the_document_computes_no_readiness_figure():
    import re

    assert not re.search(r"\b\d{1,3}\s?%", _rendered())


# --------------------------------------------------------------------------
# The workflow wiring.
# --------------------------------------------------------------------------

def test_the_reading_runs_before_land_in_intake():
    from metis_mcp.workflow.stages import WORKFLOWS

    order = [s.name for s in WORKFLOWS["intake"].stages]
    assert order.index("analysis") < order.index("land")
    assert order.index("readiness") < order.index("land")


def test_the_readiness_check_refuses_a_run_that_never_read_anything():
    """**A check that could not run says so rather than passing quietly** (F-10).
    "No blocking gaps found" and "nothing looked" are different claims, and the
    second must not reach `land`."""
    from metis_mcp.workflow.checks import get

    class _Context:
        analysis = None

    result = get("intent_is_reviewed")(_Context())
    assert not result.ok
    assert "no intent review ran" in result.reason


def test_the_readiness_check_passes_a_ready_claim_and_refuses_an_unready_one():
    from metis_mcp.workflow.checks import get

    class _Ready:
        analysis = {"status": "ready", "blocking": []}

    class _NotReady:
        analysis = {"status": "not-ready",
                    "blocking": ["INT-2: no specification"]}

    check = get("intent_is_reviewed")
    assert check(_Ready()).ok
    refusal = check(_NotReady())
    assert not refusal.ok and "INT-2" in refusal.reason


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
