"""The test design's shape and its ledger.

**What this file is guarding.** The design document is the deliverable, and its
whole claim is that two runs over the same model produce the same shape. That
claim rests on three things nothing else checks: the registry is internally
coherent (`sections.py`), the ledger says what it does not know
(`inputs.py`), and regeneration preserves what a person wrote (`document.py`).

The vocabulary tests are the ones worth reading twice. Every closed list in the
registry is imported from the module that already owns it, and a test asserting
that is the only thing standing between the design and a level, band or verdict
that the coverage ledger has never heard of.
"""
from __future__ import annotations

import sys

import pytest

from metis_mcp.design import inputs as design_inputs
from metis_mcp.design import sections as S


# --------------------------------------------------------------------------
# The registry is coherent on its own.
# --------------------------------------------------------------------------

def test_there_are_sections_and_groups_to_check():
    """The guard on the guards below, which pass vacuously over an empty
    registry -- the failure mode `test_skills.py` documents at length."""
    assert S.SECTIONS, "no sections declared"
    assert S.GROUPS, "no groups declared"


def test_ordinals_are_unique_and_start_at_one():
    ordinals = [s.ordinal for s in S.ordered()]
    assert ordinals == sorted(ordinals), "ordinals are not monotonic"
    assert len(set(ordinals)) == len(ordinals), "two sections share an ordinal"
    assert ordinals[0] == 1


def test_every_section_belongs_to_a_declared_group():
    for section in S.ordered():
        assert S.group_for(section.group) is not None, (
            f"{section.key} is in group {section.group!r}, which is not declared")


def test_every_group_holds_at_least_one_section():
    """A group with nothing in it is a heading that renders empty every run."""
    for group in S.GROUPS:
        assert S.sections_in(group.key), f"group {group.key} holds no section"


def test_column_keys_are_unique_within_a_section():
    """Two columns with one key make the merge write into the wrong cell, and
    the document still renders -- which is the silent kind of failure."""
    for section in S.ordered():
        keys = [c.key for c in section.columns]
        assert len(set(keys)) == len(keys), f"{section.key} repeats a column key"


def _tables():
    """Sections rendered as a table. A diagram has no columns at all, so every
    assertion about column shape is meaningless for one — and a blanket skip
    would be a weaker claim than naming why."""
    return [s for s in S.ordered() if s.render == S.TABLE]


def test_there_are_tables_and_at_least_one_diagram():
    """The guard on the split: if every section became a diagram, the column
    checks below would pass over nothing."""
    assert _tables(), "no table-rendered section"
    assert [s for s in S.ordered() if s.render == S.DIAGRAM], (
        "no diagram section — the render mode exists for one and this would "
        "pass vacuously without it")


def test_every_table_section_starts_with_the_id_column():
    """`document_table.parse_rows` reads the id from the first column. A section
    whose first column is something else parses that something else as its id."""
    for section in _tables():
        assert section.columns[0].key == "id", (
            f"{section.key} does not lead with the id column")


def test_every_table_section_has_a_human_column():
    """A table with nothing a person owns has nothing for regeneration to
    preserve, which makes it a report rather than a design."""
    for section in _tables():
        assert section.human_columns, f"{section.key} has no human column"


def test_a_diagram_section_owns_nothing_and_says_so():
    """The complement, and it is the reason the mode exists. A diagram has no
    cells, so a regeneration cannot preserve an annotation somebody adds to it —
    and the section has to tell them that rather than let them find out."""
    import mbt_fixtures
    from metis_mcp.design import document
    from metis_mcp.design.builders import DesignContext

    for section in S.ordered():
        if section.render != S.DIAGRAM:
            continue
        assert section.columns == (), f"{section.key} is a diagram with columns"
        assert section.human_columns == ()

    text = document.render_markdown(document.build(
        "login (api)", DesignContext(model=mbt_fixtures.login_model())))
    assert "nothing in it is yours" in text


def test_no_section_carries_a_probability():
    """**The risk rule, crossing into this domain intact.** A design carries a
    risk BAND, which says how much there is to get wrong. A probability is a
    forecast, Métis makes none, and a column here would invite one to be filled
    in -- `risk/document.py` keeps the probability column precisely because a
    person owns it there, and this document has no such owner."""
    for section in S.ordered():
        for column in section.columns:
            assert "probab" not in column.key.lower(), (
                f"{section.key}.{column.key} would hold a probability. A design "
                f"states a band, never a forecast")


def test_every_section_says_what_absent_and_empty_mean_and_they_differ():
    """*Nothing here* and *nobody looked* are the two readings an empty section
    has, and separating them is most of what this document is for."""
    for section in S.ordered():
        assert section.absent_means.strip(), f"{section.key}: no absent_means"
        assert section.empty_means.strip(), f"{section.key}: no empty_means"
        assert section.absent_means != section.empty_means, (
            f"{section.key} gives the same answer for 'could not be built' and "
            f"'built and found nothing'")


def test_no_absent_means_reads_as_reassurance():
    """The string is printed where the rows should have been. If it ever says
    'fine', a section nobody could build reads as a section with nothing in it."""
    banned = ("no risk", "is fine", "is safe", "nothing to worry", "all good",
              "no issue")
    for section in S.ordered():
        for text in (section.absent_means, section.empty_means):
            lowered = text.lower()
            for phrase in banned:
                assert phrase not in lowered, (
                    f"{section.key} reads as reassurance: {text!r}")


def test_the_uncertainty_section_is_last():
    """It reports on every section above it, so it cannot precede them."""
    assert S.ordered()[-1].key == "uncertainty"


# --------------------------------------------------------------------------
# The vocabularies are borrowed, never restated.
# --------------------------------------------------------------------------

def test_the_level_vocabulary_is_the_coverage_ledger_s_own():
    from metis_mcp.mbt.test_levels import LEVELS

    column = next(c for c in S.SECTIONS["levels"].columns if c.key == "level")
    assert column.allowed == LEVELS


def test_the_existing_coverage_grades_are_the_three_test_levels_declares():
    from metis_mcp.mbt.test_levels import COVERED, OUTCOME_UNPROVEN, UNCOVERED

    column = next(c for c in S.SECTIONS["levels"].columns if c.key == "existing")
    assert set(column.allowed) == {COVERED, OUTCOME_UNPROVEN, UNCOVERED}


def test_the_viability_and_performance_verdicts_are_viability_s_own():
    from metis_mcp import viability

    via = next(c for c in S.SECTIONS["levels"].columns if c.key == "viability")
    assert set(via.allowed) == {viability.AUTOMATE, viability.MANUAL_ONLY,
                                viability.DEFER}
    perf = next(c for c in S.SECTIONS["performance"].columns
                if c.key == "candidacy")
    assert set(perf.allowed) == {viability.PERFORMANCE_CANDIDATE,
                                 viability.FUNCTIONAL_ONLY, viability.NO_BASIS}


def test_the_risk_bands_are_the_ones_risk_exposure_reports():
    from metis_mcp.risk.exposure import BANDS

    assert S.RISK_BANDS == tuple(name for _lo, _hi, name in BANDS)


def test_the_techniques_are_the_ones_the_engine_can_actually_apply():
    """Four come from `mbt/design.py`, which is what computes them. The fifth is
    declared here because state-transition testing lives in the criteria
    machinery rather than as a named technique -- and saying so is better than
    silently having five constants in two places."""
    from metis_mcp.mbt import design as engine

    for name in (engine.DECISION_TABLE, engine.PAIRWISE, engine.BOUNDARY_VALUE,
                 engine.EQUIVALENCE_PARTITION):
        assert name in S.TECHNIQUES
    assert S.STATE_TRANSITION in S.TECHNIQUES


def test_describe_serves_the_shape_so_no_skill_has_to_restate_it():
    shape = S.describe()
    assert {g["key"] for g in shape["groups"]} == {g.key for g in S.GROUPS}
    assert len(shape["sections"]) == len(S.SECTIONS)
    for rendered in shape["sections"]:
        assert rendered["render"] in (S.TABLE, S.DIAGRAM), (
            f"{rendered['key']} does not say how it renders, so a client "
            f"cannot tell whether to expect a table")
        if rendered["render"] == S.TABLE:
            assert rendered["columns"], f"{rendered['key']} served with no columns"


# --------------------------------------------------------------------------
# The ledger.
# --------------------------------------------------------------------------

def test_input_names_are_unique():
    """A duplicate silently shadows in `BY_NAME`, and the shadowed input then
    never appears as missing."""
    names = [i.name for i in design_inputs.INPUTS]
    assert len(set(names)) == len(names), "two inputs share a name"


def test_every_input_says_what_its_absence_means():
    for item in design_inputs.INPUTS:
        assert item.absent_means.strip(), f"{item.name} has no absent_means"


def test_no_input_absent_means_reads_as_reassurance():
    banned = ("no risk", "is fine", "is safe", "nothing to worry", "all good")
    for item in design_inputs.INPUTS:
        lowered = item.absent_means.lower()
        for phrase in banned:
            assert phrase not in lowered, (
                f"{item.name} reads as reassurance: {item.absent_means!r}")


def test_every_asked_input_carries_a_question_not_a_topic():
    for item in design_inputs.INPUTS:
        if item.source != design_inputs.ASKED:
            continue
        assert "?" in item.question, f"{item.name} has no question"
        assert len(item.question.split()) >= 6, (
            f"{item.name}'s question is a topic: {item.question!r}")


def test_every_gathered_input_names_a_tool_the_server_exposes():
    """The claim a gathered input makes is that somebody can go and check it.
    A tool name that does not exist makes that claim unverifiable, which is the
    defect `test_skills.py` was written for, one layer down."""
    from metis_mcp.agent_generator import exposed_tools

    real = set(exposed_tools())
    assert real, "no tools parsed from server.py"
    for item in design_inputs.INPUTS:
        if item.source != design_inputs.GATHERED:
            continue
        assert item.tool in real, (
            f"{item.name} names `{item.tool}`, which the server does not expose")


def test_architecture_and_the_design_specification_are_asked_not_gathered():
    """**The decision this ledger exists to record.** Métis could describe an
    architecture by summarising what it recovered, and that description would be
    the implementation restated as its own intent -- S-19 in a new place. So
    both are questions, and a design without them says which sections it could
    not state."""
    for name in ("runtime_architecture", "design_specification"):
        item = design_inputs.BY_NAME[name]
        assert item.source == design_inputs.ASKED, (
            f"{name} must be asked. Deriving it from recovered code would make "
            f"the design test the code against itself")
        assert item.required, f"{name} must be required, or its absence is free"


def test_a_missing_required_input_makes_the_design_incomplete():
    result = design_inputs.completeness(gathered={}, answers={})
    assert result["status"] == design_inputs.INCOMPLETE
    assert result["missing_required"]
    assert "unfinished" in result["means"]


def test_a_complete_ledger_says_so():
    gathered = {i.name: "x" for i in design_inputs.INPUTS
                if i.source == design_inputs.GATHERED}
    answers = {i.name: "x" for i in design_inputs.INPUTS
               if i.source == design_inputs.ASKED}
    result = design_inputs.completeness(gathered=gathered, answers=answers)
    assert result["status"] == design_inputs.COMPLETE
    assert result["missing_required"] == []


def test_an_empty_answer_counts_as_supplied():
    """"Nothing is out of scope" is an answer. Treating it as absence asks the
    same question for ever, which teaches people to stop answering."""
    gathered = {i.name: "x" for i in design_inputs.INPUTS
                if i.source == design_inputs.GATHERED}
    answers = {i.name: "" for i in design_inputs.INPUTS
               if i.source == design_inputs.ASKED}
    assert design_inputs.completeness(
        gathered=gathered, answers=answers)["status"] == design_inputs.COMPLETE


def test_the_ledger_reports_no_completeness_percentage():
    """A percentage over incommensurable inputs invents precision, and makes a
    missing architecture look like a small deduction rather than a hole."""
    result = design_inputs.completeness()
    for key, value in result.items():
        assert "percent" not in key and "score" not in key, key
        assert not isinstance(value, float), f"{key} is a scalar score"


def test_unstatable_names_the_sections_a_missing_input_silences():
    missing = design_inputs.completeness()["missing_required"]
    silenced = design_inputs.unstatable(missing)
    assert silenced, "nothing was silenced by an empty ledger"
    for key in silenced:
        assert key in S.SECTIONS, f"{key} is not a section"
    assert "levels" in silenced, (
        "`environments` is missing, so levels can be assigned and not executed")


def test_a_cross_cutting_input_silences_no_single_section():
    """An input with no `decides_sections` belongs to all of them. Filing it
    against one would make that section look uniquely broken."""
    item = design_inputs.BY_NAME["entry_exit_criteria"]
    assert item.decides_sections == ()
    assert "entry_exit_criteria" not in {
        name for names in design_inputs.unstatable(
            ["entry_exit_criteria"]).values() for name in names}


def test_inputs_for_a_section_are_that_section_s_plus_the_cross_cutting_ones():
    for_data = {i.name for i in design_inputs.inputs_for("data")}
    assert "payload_shape" in for_data
    assert "test_data_constraints" in for_data
    assert "risk_band" in for_data, "cross-cutting inputs belong to every section"
    assert "auth_facts" not in for_data, "that is the security section's input"


def test_an_unknown_section_is_refused_by_name():
    with pytest.raises(design_inputs.UnknownSection) as raised:
        design_inputs.inputs_for("nonsense")
    assert "nonsense" in str(raised.value)
    assert "technique" in str(raised.value), "the refusal lists what is known"


def test_the_plan_splits_the_two_halves_and_says_why():
    plan = design_inputs.plan()
    assert plan["gathered"] and plan["asked"]
    assert "unfinished one" in plan["means"]


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


# --------------------------------------------------------------------------
# The builders.
# --------------------------------------------------------------------------

def _login_context(**overrides):
    import mbt_fixtures
    from metis_mcp.design.builders import DesignContext

    return DesignContext(model=mbt_fixtures.login_model(), **overrides)


def test_every_builder_a_section_names_resolves():
    """A section pointing at nothing renders an empty table and looks like a
    section that found nothing -- the silent success this tree keeps finding."""
    from metis_mcp.design import builders

    for section in S.ordered():
        assert builders.builder_for(section.builder) is not None


def test_an_unknown_builder_is_refused_by_name():
    from metis_mcp.design import builders

    with pytest.raises(KeyError) as raised:
        builders.builder_for("build_nothing")
    assert "build_basis" in str(raised.value), "the refusal lists what exists"


def test_every_builder_produces_rows_whose_keys_are_the_section_s_columns():
    """A row with a key no column reads renders nowhere, and a column with no
    key renders as `—` for ever. Both look like an absent value."""
    from metis_mcp.design import builders

    context = _login_context()
    for section in S.ordered():
        # A diagram row carries its rendered block and a note, not cells.
        allowed = ({"id", "diagram", "note"} if section.render == S.DIAGRAM
                   else set(section.fields) | {"id", "carried"})
        for record in builders.builder_for(section.builder)(context):
            unknown = set(record) - allowed
            assert not unknown, f"{section.key} row carries {sorted(unknown)}"
            assert record.get("id"), f"{section.key} produced a row with no id"


def test_the_builders_are_deterministic():
    """P-7's rule, one document up: a design whose rows moved every run would
    undo the byte-identical generation the suite below it depends on."""
    from metis_mcp.design import builders

    first, second = _login_context(), _login_context()
    for section in S.ordered():
        build = builders.builder_for(section.builder)
        assert build(first) == build(second), f"{section.key} is not deterministic"


def test_a_row_id_is_derived_from_what_the_row_is_about():
    """An ordinal id would renumber the moment a transition was added, moving
    every recorded decision one row down. This is the property that stops it."""
    from metis_mcp.design.builders import row_id

    assert row_id("tech", "t01", "a") == row_id("tech", "t01", "a")
    assert row_id("tech", "t01", "a") != row_id("tech", "t02", "a")
    assert row_id("tech", "t01", "a") != row_id("data", "t01", "a")


def test_adding_a_transition_does_not_change_the_other_rows_ids():
    """The claim above, made against a real model rather than against `row_id`
    in isolation -- which is where an ordinal scheme would still pass."""
    import mbt_fixtures
    from metis_mcp.design.builders import DesignContext, build_technique
    from metis_mcp.mbt.model import Transition

    before = build_technique(DesignContext(model=mbt_fixtures.login_model()))
    grown = mbt_fixtures.login_model()
    grown.transitions["t99"] = Transition(
        id="t99", source="LoggedIn", trigger="click_help", target="LoggedIn")
    after = {r["id"] for r in build_technique(DesignContext(model=grown))}
    assert {r["id"] for r in before} <= after, (
        "adding a transition changed the id of a row about a different one")


def test_a_refused_technique_is_a_row_and_not_a_silence():
    """`decision_table` declines a single-transition group, and `analyse_guard`
    declines a predicate with no numeric boundary. Dropping either makes the
    design look like it considered fewer options than it did."""
    from metis_mcp.design.builders import build_technique

    rows = build_technique(_login_context())
    refused = [r for r in rows if r["unavailable"]]
    assert refused, "no refusal was carried through"
    assert any("only one transition" in r["unavailable"] for r in refused)
    assert any("not a numeric threshold" in r["unavailable"] for r in refused)


def test_a_guard_with_an_or_refuses_the_decision_table_verbatim():
    """M-17's fail-closed rule, carried through this document unsoftened. Built
    against a purpose-made group because the login fixture's one OR guard sits
    alone on its `(state, trigger)`, where the table refuses for the other
    reason first -- so asserting it there would assert a fixture accident."""
    import mbt_fixtures
    from metis_mcp.design.builders import DesignContext, build_technique
    from metis_mcp.mbt.model import Transition

    model = mbt_fixtures.login_model()
    model.transitions["t18"] = Transition(
        id="t18", source="AccountLocked", trigger="admin_unlock_or_lockout_elapsed",
        target="AccountLocked", guard="NOT admin_unlocked")

    rows = build_technique(DesignContext(model=model))
    tables = [r for r in rows if r["technique"] == "decision-table"
              and r["behaviour"].startswith("(AccountLocked,")]
    assert tables, "no decision table was attempted for the OR group"
    assert any("OR" in r["unavailable"] for r in tables), (
        "a guard containing OR must refuse the table, and say so: half a table "
        "is worse than none")


def test_no_builder_emits_a_value_where_the_model_states_a_space():
    """M-9 and X-6e together: every data row is a CONDITION. A row naming a
    concrete value would be Métis inventing test data."""
    from metis_mcp.design.builders import build_data

    for record in build_data(_login_context()):
        assert record["condition"], "a data row with no condition states nothing"
        assert "=" not in record["condition"] or any(
            token in record["condition"] for token in ("<", ">", "=")), (
            f"{record['condition']!r} reads as an assignment, not a condition")


def test_the_uncertainty_section_carries_the_exact_question():
    """A topic gets a shrug. The row has to be answerable as written."""
    from metis_mcp.design.builders import build_uncertainty

    rows = build_uncertainty(_login_context())
    asked = [r for r in rows if "?" in (r["question"] or "")]
    assert asked, "no uncertainty row carries a question"
    for record in rows:
        assert record["absent_means"], f"{record['id']} does not say what it means"


def test_the_design_order_is_the_order_the_prioritise_stage_produces():
    """**The wire that ties this document to the batch generated from it.** A
    design and a suite that disagreed about what matters first would be two
    plans. Both sort by `prioritisation.order`, and this asserts they still do
    -- rebuilt here the way `workflow/handlers._prioritise` builds it."""
    import mbt_fixtures
    from metis_mcp.design.builders import DesignContext
    from metis_mcp.risk import detection, prioritisation, product

    model = mbt_fixtures.login_model()
    found = detection.detection_over(model.transition_ids(), [])
    unverifiable = product.unverifiable_ids(model)
    technical = {tid: product.technical_profile(model, tid, unverifiable)
                 for tid in found["scores"]}
    ranked = prioritisation.order(found["scores"], technical)
    ranks = {row["transition_id"]: row["rank"] for row in ranked}

    context = DesignContext(model=model, ranks=ranks)
    unranked = len(ranks) + 1
    expected = sorted(model.transition_ids(),
                      key=lambda tid: (ranks.get(tid, unranked), tid))
    assert context.ordered_transition_ids() == expected
    assert len(set(ranks.values())) > 1, (
        "every transition ranked the same — this would pass under any ordering")


# --------------------------------------------------------------------------
# The document.
# --------------------------------------------------------------------------

def _heading_of(key: str) -> str:
    """The rendered heading for a section, from the registry.

    Written out by hand as `## 3. Test data conditions` until a section was
    inserted ahead of it and three tests failed for a reason that had nothing to
    do with what they assert. The ordinal belongs to the registry; a test that
    copies it is a second place to keep it in step.
    """
    section = S.SECTIONS[key]
    return f"## {section.ordinal}. {section.heading}"


def _rendered(**overrides) -> str:
    from metis_mcp.design import document

    context = _login_context(**overrides)
    return document.render_markdown(document.build("login (api)", context))


def _without_timestamp(text: str) -> str:
    import re

    return re.sub(r"\*Test design generated .*?\.\*", "", text)


def test_the_document_renders_identically_across_runs():
    assert _without_timestamp(_rendered()) == _without_timestamp(_rendered())


def test_the_incomplete_banner_sits_above_the_first_section():
    """Burying it under nine tables is how an unfinished design gets read as a
    finished one."""
    text = _rendered()
    assert "⚠ Incomplete" in text
    assert text.index("⚠ Incomplete") < text.index(_heading_of("basis"))


def test_a_complete_design_says_so_instead():
    from metis_mcp.design import document, inputs as ledger

    context = _login_context(
        gathered={i.name: "x" for i in ledger.INPUTS
                  if i.source == ledger.GATHERED},
        answers={i.name: "x" for i in ledger.INPUTS
                 if i.source == ledger.ASKED})
    text = document.render_markdown(document.build("login (api)", context))
    assert "⚠ Incomplete" not in text
    assert "**Complete**" in text


def test_a_section_with_rows_and_missing_inputs_says_it_is_partial():
    """The dangerous case: a table with content in it, resting on inputs nobody
    supplied. An empty section announces itself; this one has to be told to."""
    text = _rendered()
    technique = text[text.index(_heading_of("technique")):
                     text.index(_heading_of("dimensions"))]
    assert "| tech-" in technique, "the technique table has no rows to qualify"
    assert "> **Partial.**" in technique


def test_an_empty_section_prints_what_its_emptiness_means():
    text = _rendered()
    security = text[text.index(_heading_of("security")):
                    text.index(_heading_of("performance"))]
    assert "AUTHORISATION IS UNEXAMINED" in security
    assert "waiting on: auth_facts" in security


def test_the_rendered_document_names_a_probability_only_to_refuse_one():
    """The word belongs in this document exactly once per place it is ruled out.
    A line mentioning it without a negation would be a column inviting one to be
    filled in -- which is what `test_no_section_carries_a_probability` forbids
    at the registry level, asserted here against what a reader actually sees."""
    for line in _rendered().lower().splitlines():
        if "probab" not in line:
            continue
        assert ("no probability" in line or "never" in line
                or "forecasts nothing" in line), (
            f"this line mentions a probability without ruling one out: {line!r}")


def test_the_document_computes_no_readiness_figure():
    """A percentage over incommensurable inputs makes a missing architecture
    look like a deduction rather than a hole."""
    import re

    text = _rendered()
    assert not re.search(r"\b\d{1,3}\s?%", text), "a percentage was rendered"


def test_regeneration_preserves_an_edited_human_column():
    """The property that silently destroys work when it is wrong."""
    from metis_mcp.design import document

    context = _login_context()
    first = document.render_markdown(document.build("login (api)", context))
    section = S.SECTIONS["technique"]
    target = sorted(document.parse(first, section))[0]

    line = next(l for l in first.splitlines() if l.startswith(f"| {target} "))
    edited_line = line.rsplit("|", 4)[0] + "| accept | alice | our call |"
    edited = first.replace(line, edited_line)

    merged = document.merge(document.build("login (api)", context), edited)
    after = document.parse(document.render_markdown(merged), section)
    assert after[target]["decision"] == "accept"
    assert after[target]["owner"] == "alice"
    assert after[target]["notes"] == "our call"


def test_regeneration_preserves_a_row_somebody_added_by_hand():
    """The architecture is asked, not gathered, so the sections depending on it
    are exactly where a person has most to add. Deleting their row would teach
    them not to edit the file."""
    from metis_mcp.design import document

    context = _login_context()
    first = document.render_markdown(document.build("login (api)", context))
    section = S.SECTIONS["technique"]
    anchor = next(l for l in first.splitlines() if l.startswith("| tech-"))
    # **Built from the section's real width, not hardcoded.** A hand-written row
    # one cell short is correctly REJECTED by `parse_rows` — which is the design
    # — so a fixture that hardcodes the count fails for the wrong reason the
    # moment a column is added, and says nothing about the merge.
    cells = ["tech-HAND01"] + ["—"] * (len(section.columns) - 1)
    cells[1] = "(LoggedOut, submit)"
    cells[-3:] = ["change", "bob", "ours"]
    hand = "| " + " | ".join(cells) + " |"
    edited = first.replace(anchor, anchor + "\n" + hand)

    merged = document.merge(document.build("login (api)", context), edited)
    assert "tech-HAND01" in merged["carried_over"]
    after = document.parse(document.render_markdown(merged), section)
    assert after["tech-HAND01"]["notes"] == "ours"


def test_a_regenerated_document_reports_no_unreadable_rows():
    from metis_mcp.design import document

    assert document.parse_problems(_rendered()) == []


def test_a_row_that_lost_its_shape_is_reported_rather_than_dropped():
    """A discarded edit is the same defect as an overwritten one."""
    from metis_mcp.design import document

    text = _rendered()
    line = next(l for l in text.splitlines() if l.startswith("| tech-"))
    broken = text.replace(line, "| tech-BROKEN | only | two |")
    assert any(p.endswith(":tech-BROKEN")
               for p in document.parse_problems(broken))


def test_one_section_can_be_built_alone():
    """`metis design --section data` exists so a designer working on data
    conditions does not regenerate the journey table to see them."""
    from metis_mcp.design import document

    doc = document.build("login (api)", _login_context(), section="data")
    assert [s["key"] for s in doc["sections"]] == ["data"]
    text = document.render_markdown(doc)
    assert _heading_of("data") in text
    assert _heading_of("technique") not in text


# --------------------------------------------------------------------------
# Guard dimensions.
#
# **This section is why `mbt/dimensions.py` exists and why it had no caller.**
# Four hundred lines implementing GD-1..GD-9 sat unreachable behind three
# separate defects: the evidence edges never landed, `GuardCheck` carried no
# `id` for `build_chain` to read, and the loader selected an anchor property
# that does not exist. Each was silent.
# --------------------------------------------------------------------------

def _model_with_a_chain():
    """The login fixture, with a recovered short-circuit chain on one transition."""
    import mbt_fixtures
    from metis_mcp.mbt.model import GuardCheck
    from dataclasses import replace as _replace

    model = mbt_fixtures.login_model()
    model.transitions["t01"] = _replace(
        model.transitions["t01"],
        checks=(GuardCheck(expression="request is authenticated", order=1,
                           anchor="Auth.java:12@abc", id="chk:auth"),
                GuardCheck(expression="caller is authorized", order=2,
                           anchor="Authz.java:40@abc", id="chk:authz"),
                GuardCheck(expression="payload_valid", order=3,
                           anchor="Dto.java:7@abc", id="chk:payload")))
    return model


def test_the_dimension_vocabulary_is_the_engine_s_own():
    from metis_mcp.mbt import dimensions

    column = next(c for c in S.SECTIONS["dimensions"].columns
                  if c.key == "dimension_class")
    assert set(column.allowed) == {
        dimensions.AUTHENTICATION, dimensions.AUTHORIZATION,
        dimensions.VALIDATION, dimensions.BUSINESS, ""}


def test_the_blank_class_is_in_the_vocabulary_on_purpose():
    """X-10c: an unclassified check keeps its position and participates in the
    chain. A blank is a recovered fact, so `--verify` must not reject it."""
    column = next(c for c in S.SECTIONS["dimensions"].columns
                  if c.key == "dimension_class")
    assert "" in column.allowed


def test_the_chain_is_built_and_the_reduction_is_reported():
    from metis_mcp.design.builders import DesignContext, build_dimensions

    rows = build_dimensions(DesignContext(model=_model_with_a_chain()))
    assert len(rows) == 3, "one row per dimension of the chain"
    assert [r["order"] for r in rows] == [1, 2, 3]
    assert [r["dimension_class"] for r in rows] == [
        "authentication", "authorization", "validation"]
    # 3 dimensions, 2 variants each: bounded 1+1+1+1 = 4, product 2*2*2 = 8.
    assert {r["reduction"] for r in rows} == {"4 of 8"}, (
        "the reduction is the point of this section and every row carries it")


def test_a_behaviour_with_no_recovered_check_produces_no_row():
    """Not an empty chain rendered as one dimension of nothing. The section's
    `empty_means` says what an absent chain means; a placeholder row would say
    something else."""
    import mbt_fixtures
    from metis_mcp.design.builders import DesignContext, build_dimensions

    assert build_dimensions(DesignContext(model=mbt_fixtures.login_model())) == []


def test_the_anchor_survives_into_the_row():
    """T-9a: a condition a reviewer cannot trace back to a line is a claim they
    must take on trust. It came back empty for as long as the loader existed."""
    from metis_mcp.design.builders import DesignContext, build_dimensions

    rows = build_dimensions(DesignContext(model=_model_with_a_chain()))
    assert all(r["anchor"] for r in rows), "a dimension with no anchor is untraceable"
    assert rows[0]["anchor"] == "Auth.java:12@abc"


def test_an_unresolvable_chain_reports_the_refusal_rather_than_a_number():
    """GD-9: two checks sharing an evaluation order make the chain ambiguous.
    `cost` falls back to the full product and says so; a tie-break on id would
    be the guess the rule forbids."""
    from dataclasses import replace as _replace

    import mbt_fixtures
    from metis_mcp.design.builders import DesignContext, build_dimensions
    from metis_mcp.mbt.model import GuardCheck

    model = mbt_fixtures.login_model()
    model.transitions["t01"] = _replace(
        model.transitions["t01"],
        checks=(GuardCheck(expression="a", order=1, id="chk:a"),
                GuardCheck(expression="b", order=1, id="chk:b")))
    rows = build_dimensions(DesignContext(model=model))
    assert rows and all(r["unavailable"] for r in rows)
    assert "precedence_unresolved" in rows[0]["unavailable"]
    assert "not generated" in rows[0]["unavailable"], (
        "the explosion is reported rather than generated (P-3b)")


def test_the_loader_assembles_an_anchor_from_the_properties_that_exist():
    """The query selected `c.anchor`, which no `Check` node has — `_anchor_props`
    writes three flat properties because a Neo4j property cannot hold a map."""
    from metis_mcp.mbt.graph_loader import CHECKS_CYPHER, _anchor_of

    assert "c.anchor_file" in CHECKS_CYPHER and "c.anchor_line" in CHECKS_CYPHER
    assert _anchor_of({"anchor_file": "A.java", "anchor_line": 17,
                       "anchor_commit": "abc"}) == "A.java:17@abc"


def test_an_absent_anchor_is_empty_rather_than_a_shape_that_compares_equal():
    """**GD-8 gates equivalence-class credit on an IDENTICAL anchor.** If an
    absent one rendered as `":0@"`, unrelated checks would compare equal and be
    credited as one behaviour — which is the over-crediting the rule exists to
    prevent."""
    from metis_mcp.mbt.graph_loader import _anchor_of

    assert _anchor_of({}) == ""
    assert _anchor_of({"anchor_file": "", "anchor_line": 0,
                       "anchor_commit": ""}) == ""


# --------------------------------------------------------------------------
# Condition completeness.
#
# **The denominator, and the reason a design overstates itself without one.**
# `shared/knowledge/requirement-condition-coverage.md` has stated this rule for
# as long as it has existed and nothing applied it — it was prose a model was
# asked to follow. Six of the eight classes are computable from what Métis
# already recovered; the other two are undrawn and say so.
# --------------------------------------------------------------------------

def _conditions(model=None):
    import mbt_fixtures
    from metis_mcp.design.builders import DesignContext, build_conditions

    return build_conditions(DesignContext(model=model or mbt_fixtures.login_model()))


def test_the_eight_classes_match_the_rule_they_come_from():
    """The tuple is declared in `sections.py` because no module owns the rule —
    which is exactly why it went unapplied. If the two ever disagree, the
    section is deciding classes the rule does not name."""
    from pathlib import Path

    rule = (Path(__file__).resolve().parent.parent / "plugins" / "metis"
            / "skills" / "shared" / "knowledge"
            / "requirement-condition-coverage.md").read_text()
    for name in S.CONDITION_CLASSES:
        assert f"`{name}`" in rule, (
            f"the section decides {name!r} and the rule does not name it")
    assert len(S.CONDITION_CLASSES) == 8


def test_every_behaviour_gets_a_row_for_every_class():
    """The whole mechanism. A requirement with no numeric limit still needs a
    `boundary` row marked `not-applicable` with a reason; what it must not do is
    silently disappear.

    Grouped by `subject` rather than by transition id: the id is a digest of
    what the row is about, so a filter written as `tid in row["id"]` matches
    nothing — and the first version of this test papered over that with an
    `or True`, which made the filter vacuous and the assertion meaningless.
    """
    import collections

    import mbt_fixtures

    model = mbt_fixtures.login_model()
    rows = _conditions(model)
    assert len(rows) == len(model.transitions) * len(S.CONDITION_CLASSES)

    by_subject = collections.defaultdict(set)
    for row in rows:
        by_subject[row["subject"]].add(row["condition_class"])
    assert len(by_subject) == len(model.transitions), (
        "two behaviours collapsed onto one subject, so one of them is undecided")
    for subject, classes in by_subject.items():
        assert classes == set(S.CONDITION_CLASSES), (
            f"{subject} is missing {sorted(set(S.CONDITION_CLASSES) - classes)}")


def test_every_row_carries_a_reason_including_the_ones_that_do_not_apply():
    """A `not-applicable` with no reason is the row this section refuses to
    write: it is indistinguishable from a class nobody considered."""
    for row in _conditions():
        assert row["reason"].strip(), (
            f"{row['condition_class']} on {row['subject']} has no reason")


def test_the_two_undrawn_classes_come_back_clarify_and_say_why():
    """Métis recovers the branches in this code. What happens when something
    outside it stops answering, and what was deliberately excluded, are not in
    the source it read."""
    for name in ("dependency-failure", "non-goal"):
        rows = [r for r in _conditions() if r["condition_class"] == name]
        assert rows and all(r["proposed"] == "clarify" for r in rows)
        assert all(r["found"] == "" for r in rows), (
            f"{name} is undrawn — claiming a finding for it would be an invention")


def test_an_absent_authorisation_check_is_clarify_and_never_not_applicable():
    """Declarative security is all extraction sees. `not-applicable` would say
    the class does not apply here; the truth is that nobody looked."""
    rows = [r for r in _conditions() if r["condition_class"] == "authorization"]
    assert rows and all(r["proposed"] == "clarify" for r in rows)
    assert any("nobody looked" in r["reason"] for r in rows)


def test_a_guard_with_no_numeric_threshold_is_not_applicable_with_the_reason():
    """The login guards are predicates. `t.isEmpty()` has no boundary, and
    inventing one is what M-9 forbids — so the class is closed with a reason
    rather than left open."""
    rows = [r for r in _conditions() if r["condition_class"] == "boundary"]
    assert rows and all(r["proposed"] == "not-applicable" for r in rows)
    assert all(r["reason"] for r in rows)


def test_a_rejecting_sibling_is_what_makes_prohibited_answerable():
    """The complement of a guard has a case only where the model carries the
    other branch. Without one the class is `clarify`, not covered."""
    from dataclasses import replace as _replace

    import mbt_fixtures

    model = mbt_fixtures.login_model()
    before = [r for r in _conditions(model)
              if r["condition_class"] == "prohibited"]
    assert all(r["proposed"] == "clarify" for r in before)

    # Give one (state, trigger) a real rejecting branch.
    model.transitions["t02"] = _replace(model.transitions["t02"],
                                        outcome_status=401)
    after = [r for r in _conditions(model)
             if r["condition_class"] == "prohibited"
             and r["subject"].startswith("(LoggedOut, submit_invalid")]
    assert after and all(r["proposed"] == "test" for r in after)


def test_metis_proposes_and_never_decides():
    """`proposed` is its reading; `decision` is a person's. They are separate
    columns because a class Métis could not reach reads `clarify`, which is
    neither yes nor no."""
    section = S.SECTIONS["conditions"]
    proposed = next(c for c in section.columns if c.key == "proposed")
    decision = next(c for c in section.columns if c.key == "decision")
    assert proposed.filled_by == S.COMPUTED
    assert decision.filled_by == S.HUMAN
    assert set(proposed.allowed) == set(decision.allowed) == set(S.CONDITION_DECISIONS)


def test_a_condition_row_never_claims_intent_from_recovered_code():
    """S-19: a condition read out of the implementation can only report that the
    code agrees with itself. `independently_authored` is what intent is, and
    nothing here may claim it."""
    for row in _conditions():
        assert row["provenance"] in ("code_derived", ""), row


# --------------------------------------------------------------------------
# Setup cost.
# --------------------------------------------------------------------------

def _setup(model=None):
    import mbt_fixtures
    from metis_mcp.design.builders import DesignContext, build_setup

    return build_setup(DesignContext(model=model or mbt_fixtures.login_model()))


def test_setup_depth_comes_from_the_path_not_from_a_verb():
    """The practice this comes from classifies a slice by its business verb.
    Métis walks the machine instead, and `Path.setup_transition_ids` IS the
    chain a test must establish."""
    rows = _setup()
    assert rows, "no path was generated for any behaviour"
    assert any(r["setup_depth"] > 0 for r in rows), (
        "every behaviour reachable with no setup — this would pass under a "
        "builder that never read the path at all")
    for row in rows:
        assert row["preconditions"], "a row with no precondition column states nothing"


def test_a_trigger_with_no_http_verb_reports_an_unknown_effect():
    """**The silent wrong answer this refuses.** A UI action's trigger is
    `submit_valid_credentials`. A rule falling through to `read-only` would call
    a credential submission a read and hand it the cheapest cost band."""
    rows = _setup()
    assert all(r["effect"] == "unknown" for r in rows), (
        "the login fixture's triggers are not HTTP verbs")
    assert all("UNKNOWN" in r["basis"] for r in rows), (
        "the band must say the effect is missing, not quietly absorb it")


def test_an_http_verb_is_classified_and_a_write_costs_more():
    from dataclasses import replace as _replace

    import mbt_fixtures

    model = mbt_fixtures.login_model()
    model.transitions["t11"] = _replace(model.transitions["t11"],
                                        trigger="GET /reset")
    model.transitions["t16"] = _replace(model.transitions["t16"],
                                        trigger="POST /logout")
    rows = {r["behaviour"]: r for r in _setup(model)}
    read = next(r for b, r in rows.items() if "GET /reset" in b)
    write = next(r for b, r in rows.items() if "POST /logout" in b)
    assert read["effect"] == "read-only" and read["complexity"] == "minimal"
    assert write["effect"] == "state-changing"
    assert "cleanup is owed" in write["basis"] or write["complexity"] == "escalate"


def test_the_setup_pattern_is_a_human_column():
    """Whether reuse is safe depends on stable data and cleanup ownership, and
    Métis can see neither. It computes the cost; a person picks the pattern."""
    pattern = next(c for c in S.SECTIONS["setup"].columns if c.key == "pattern")
    assert pattern.filled_by == S.HUMAN
    assert set(pattern.allowed) == set(S.SETUP_PATTERNS)


def test_a_transition_the_criterion_cannot_reach_gets_no_row():
    """Rather than a row claiming zero setup. Inventing a cost for behaviour
    nothing can reach would put a cheap-looking number on the worst case."""
    import mbt_fixtures
    from metis_mcp.mbt.model import Transition

    model = mbt_fixtures.login_model()
    model.transitions["orphan"] = Transition(
        id="orphan", source="Unreachable", trigger="GET /x", target="LoggedIn")
    assert not any(r["id"].endswith("orphan") for r in _setup(model))


def test_setup_is_costed_for_an_unapproved_model():
    """**The reason this walks the machine rather than calling `generate`.**

    `generate` honours D-10 and excludes everything at `Quarantine` — correct for
    generation, wrong here. The `test-design` workflow has no approval
    precondition precisely because designing before approval is when it changes
    a decision, and going through `generate` produced an empty section for every
    real model while its `empty_means` blamed reachability.
    """
    import mbt_fixtures
    from metis_mcp.design.builders import DesignContext, build_setup
    from metis_mcp.mbt.path_generation import generate

    unapproved = mbt_fixtures.login_model(approved=False)
    assert not generate(unapproved, "all-transitions").paths, (
        "generation must still refuse an unapproved model, or D-10 has moved")
    assert build_setup(DesignContext(model=unapproved)), (
        "the design must cost an unapproved model — that is when it is useful")


def test_the_walk_still_refuses_unapproved_steps_for_generation():
    """The parameter is the caller's question and generation keeps the default.
    If this ever passed, D-10 would have been widened by a design concern."""
    import mbt_fixtures
    from metis_mcp.mbt.path_generation import shortest_setup

    unapproved = mbt_fixtures.login_model(approved=False)
    assert shortest_setup(unapproved, "Failed1") is None
    assert shortest_setup(unapproved, "Failed1", generatable_only=False) is not None


# --------------------------------------------------------------------------
# Negative obligations.
#
# The endpoint-shaped half of the completeness question. The practice this comes
# from writes the negative scenario outright with the status hardcoded — 400,
# 401/403, 404. Métis knows what the endpoint was actually seen to produce, so
# it reports the recovered set and asks.
# --------------------------------------------------------------------------

def _api_model():
    """A model whose triggers are real endpoints, with the shapes that oblige."""
    from metis_mcp.mbt.model import Model, State, Transition

    states = {n: State(id=n, name=n, surface="api", is_initial=(n == "Start"))
              for n in ("Start", "Ok", "Bad", "Denied")}
    return Model(id="obl-api", states=states, transitions={
        "get_ok": Transition(
            id="get_ok", source="Start", trigger="GET /thing/{id}", target="Ok",
            outcome_status=200,
            inputs=({"location": "path", "name": "id", "required": True},)),
        "get_bad": Transition(
            id="get_bad", source="Start", trigger="GET /thing/{id}", target="Bad",
            outcome_status=400,
            inputs=({"location": "path", "name": "id", "required": True},)),
        "post_ok": Transition(
            id="post_ok", source="Start", trigger="POST /thing", target="Ok",
            outcome_status=201,
            inputs=({"location": "body", "name": "dto", "required": True},),
            security=({"scheme": "bearer", "role": "admin"},)),
        "post_denied": Transition(
            id="post_denied", source="Start", trigger="POST /thing",
            target="Denied", outcome_status=403,
            inputs=({"location": "body", "name": "dto", "required": True},),
            security=({"scheme": "bearer", "role": "admin"},)),
    })


def _obligations(model=None):
    from metis_mcp.design.builders import DesignContext, build_obligations

    return build_obligations(DesignContext(model=model or _api_model()))


def test_every_obligation_names_the_recovered_fact_that_raised_it():
    """A route that merely looks like it should have one obliges nothing (X-6),
    so each row has to say which fact it came from."""
    rows = _obligations()
    assert rows
    for row in rows:
        assert row["obligation"] in S.OBLIGATIONS
        assert row["because"].strip(), f"{row['obligation']} names no fact"


def test_a_path_parameter_obliges_a_not_found_and_it_is_unmet_here():
    rows = [r for r in _obligations() if r["obligation"] == "not-found"]
    assert len(rows) == 1, "one obligation per endpoint, not per outcome"
    assert rows[0]["status"] == "unmet"
    assert "path parameter" in rows[0]["because"]


def test_an_unmet_obligation_reports_what_was_recovered_beside_it():
    """"`GET /x/{id}` produces 200 and 400, and no 404" is a question somebody
    can answer; "missing 404" is one they cannot."""
    row = next(r for r in _obligations() if r["obligation"] == "not-found")
    assert row["recovered"] == "200, 400"
    assert row["satisfied_by"] == ""


def test_a_recovered_refusal_satisfies_the_authorisation_obligation():
    rows = [r for r in _obligations() if r["obligation"] == "authorization-denied"]
    assert len(rows) == 1
    assert rows[0]["status"] == "satisfied"
    assert rows[0]["satisfied_by"] == "post_denied", (
        "the transition that carries it must be named, not just counted")


def test_either_status_of_a_pair_satisfies_its_obligation():
    """401 and 403 are both a refusal; 400 and 422 are both a rejection.
    Insisting on one of each pair would report an endpoint unmet for choosing
    the other."""
    from dataclasses import replace as _replace

    model = _api_model()
    model.transitions["post_denied"] = _replace(model.transitions["post_denied"],
                                                outcome_status=401)
    rows = [r for r in _obligations(model)
            if r["obligation"] == "authorization-denied"]
    assert rows[0]["status"] == "satisfied"


def test_an_endpoint_with_no_obliging_shape_raises_nothing():
    """No path parameter, no declared security, no body: nothing is obliged, and
    inventing one from the route name is what X-6 forbids."""
    from metis_mcp.mbt.model import Model, State, Transition

    model = Model(
        id="bare-api",
        states={"Start": State(id="Start", name="Start", surface="api",
                               is_initial=True),
                "Ok": State(id="Ok", name="Ok", surface="api")},
        transitions={"t": Transition(id="t", source="Start",
                                     trigger="GET /health", target="Ok",
                                     outcome_status=200)})
    assert _obligations(model) == []


def test_the_status_column_says_unmet_is_a_question_not_a_defect():
    """The whole difference from the practice this came from, which asserts the
    negative scenario outright. `unmet` says no such outcome was RECOVERED, and
    the column has to carry that distinction — a reader who takes it as a defect
    will file bugs against extraction gaps."""
    status = next(c for c in S.SECTIONS["obligations"].columns
                  if c.key == "status")
    assert set(status.allowed) == set(S.OBLIGATION_STATUS)
    assert "RECOVERED" in status.means, (
        "the column must say what `unmet` is about")
    assert "not a defect Métis declared" in status.means


# --------------------------------------------------------------------------
# Defect-proneness factors.
# --------------------------------------------------------------------------

def _profile(model=None):
    import mbt_fixtures
    from metis_mcp.design.builders import DesignContext, build_profile

    return build_profile(DesignContext(model=model or mbt_fixtures.login_model()))


def test_every_factor_carries_the_response_it_asks_for():
    """`technical_profile`'s docstring makes this argument and nothing acted on
    it: high branching wants more cases, high fan-in wants a contract nobody may
    break, and "test it more" is the answer to neither."""
    rows = _profile()
    assert rows
    measured = [r for r in rows if r["observed"] != "not measured"]
    assert measured
    for row in measured:
        assert row["response"].strip(), f"{row['factor']} asks for nothing"


def test_an_unmeasured_factor_is_a_row_and_never_a_blank():
    """A blank in a column of counts reads as zero, and zero here reads as
    *simple* — which is the reading `technical_profile` refuses when it leaves
    an unmeasured factor out of `observed` entirely."""
    rows = [r for r in _profile() if r["observed"] == "not measured"]
    assert rows, "the login fixture measures no complexity, size or repairs"
    assert all(r["rating"] is None for r in rows), (
        "an unmeasured factor must carry no rating, or it contributes to a band")
    assert all(r["response"] for r in rows)


def test_an_unmeasured_repair_count_says_nobody_counted_rather_than_none():
    """A file counted and never repaired is not a file nobody counted, and
    `repairs_window` is the only thing that tells them apart."""
    row = next(r for r in _profile() if r["factor"] == "repairs")
    assert "no window was given" in row["response"]
    assert "not a file with no repairs" in row["response"]


def test_the_profile_reports_the_raw_count_beside_the_rating():
    """The rating is what orders; the raw count is what a reader disagrees
    with. Reporting only the rating hides the measurement."""
    row = next(r for r in _profile()
               if r["factor"] == "fan_out" and r["observed"] != "not measured")
    assert isinstance(row["observed"], int)
    assert isinstance(row["rating"], int)


# --------------------------------------------------------------------------
# The machine diagram.
# --------------------------------------------------------------------------

def _machine(model=None):
    import mbt_fixtures
    from metis_mcp.design.builders import DesignContext, build_machine

    return build_machine(DesignContext(model=model or mbt_fixtures.login_model()))


def test_the_diagram_is_drawn_from_what_was_recovered_and_nothing_else():
    """No actors, no inferred grouping. An actor is an `asked` input, and a
    diagram inventing one would put a person on the page nobody named."""
    import mbt_fixtures

    model = mbt_fixtures.login_model()
    diagram = _machine(model)[0]["diagram"]
    assert diagram.startswith("stateDiagram-v2")
    # Every arrow's endpoints are states the model actually holds.
    names = {(s.name or sid).rsplit("::", 1)[-1] for sid, s in model.states.items()}
    import re

    drawn = set(re.findall(r"^\s*(\w+) -->", diagram, re.M)) - {"[*]"}
    unknown = {d for d in drawn if d not in {n.replace(" ", "_") for n in names}}
    assert not unknown, f"the diagram draws states the model does not have: {unknown}"


def test_the_diagram_is_deterministic():
    """P-7 reaches the picture too: a diagram whose node order moved every run
    would make a regenerated design diff against itself."""
    assert _machine()[0]["diagram"] == _machine()[0]["diagram"]
    import mbt_fixtures
    from metis_mcp.design.builders import DesignContext, build_machine

    a = build_machine(DesignContext(model=mbt_fixtures.login_model()))
    b = build_machine(DesignContext(model=mbt_fixtures.login_model()))
    assert a == b


def test_a_model_too_large_to_draw_is_reported_rather_than_truncated():
    """**P-3b through a picture.** A diagram showing forty of fifty-six
    transitions with no note is worse than none: it looks complete."""
    from dataclasses import replace as _replace

    import mbt_fixtures
    from metis_mcp.mbt.model import Transition

    model = mbt_fixtures.login_model()
    for i in range(S.MAX_DIAGRAM_TRANSITIONS):
        model.transitions[f"x{i:03d}"] = Transition(
            id=f"x{i:03d}", source="LoggedIn", trigger=f"GET /x{i}",
            target="LoggedIn")
    row = _machine(model)[0]
    assert row["diagram"] == "", "a model over the cap must not be part-drawn"
    assert str(len(model.transitions)) in row["note"]
    assert "Not drawn" in row["note"]


def test_a_state_name_becomes_a_usable_mermaid_id():
    """An id mermaid cannot parse breaks the whole block rather than one line,
    so names are substituted rather than quoted and hoped for."""
    from metis_mcp.design.builders import _mermaid_id

    assert _mermaid_id("athena-tms-api::Item") == "athena_tms_api__Item"
    assert _mermaid_id("Logged Out") == "Logged_Out"
    assert _mermaid_id("!!!") == "unnamed"


def test_a_guard_with_mermaid_syntax_in_it_does_not_break_the_block():
    """A colon separates a mermaid transition from its label, and a guard
    containing one would end the label early."""
    from dataclasses import replace as _replace

    import mbt_fixtures
    from metis_mcp.design.builders import DesignContext, build_machine

    model = mbt_fixtures.login_model()
    model.transitions["t01"] = _replace(
        model.transitions["t01"], guard="ratio: 1 < 2 AND x > 3")
    diagram = build_machine(DesignContext(model=model))[0]["diagram"]
    body = diagram.split("\n", 1)[1]
    for line in body.splitlines():
        assert line.count(":") <= 1, f"a label ended early: {line}"
    assert "&lt;" in diagram and "&gt;" in diagram


def test_the_rendered_document_still_verifies_with_a_diagram_in_it():
    from metis_mcp.design import document

    assert document.verify(_rendered()) == []
    assert document.parse_problems(_rendered()) == []


def test_regeneration_still_preserves_a_table_edit_beside_a_diagram():
    """The diagram is rewritten whole; the tables around it are not. This is the
    property the render mode had to not break."""
    from metis_mcp.design import document

    context = _login_context()
    first = document.render_markdown(document.build("login (api)", context))
    section = S.SECTIONS["technique"]
    target = sorted(document.parse(first, section))[0]
    line = next(l for l in first.splitlines() if l.startswith(f"| {target} "))
    edited = line.rsplit("|", 4)[0] + "| accept | erin | ours |"

    merged = document.merge(document.build("login (api)", context),
                            first.replace(line, edited))
    after = document.parse(document.render_markdown(merged), section)
    assert after[target]["owner"] == "erin"
    assert "stateDiagram-v2" in document.render_markdown(merged)
