"""The design family's map, asserted in both directions.

**Why this file exists.** `risk/areas.py`'s docstring makes the argument and it
applies unchanged here: a family of nine sections and eight skills with nothing
recording which skill covers which activity is a family where a reader cannot
tell whether `technique` covers data conditions without opening it, and neither
can a test. So the mapping is data, and this asserts it holds.

It also guards the property the whole design rests on: **the template is served,
never restated.** A `SKILL.md` that listed a section's columns would be a second
copy of what `design_sections()` generates, and it is the copy nothing checks.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from metis_mcp.design import areas, sections

SKILLS = Path(__file__).resolve().parent.parent / "plugins" / "metis" / "skills"
FAMILY = SKILLS / "metis-test-design"


def _all_skills() -> dict:
    from metis_mcp.agent_generator import read_skills

    return {s.name: s for s in read_skills()}


def _design_skills() -> dict:
    return {name: skill for name, skill in _all_skills().items()
            if name == "metis-test-design" or name.startswith("metis-test-design-")}


# --------------------------------------------------------------------------
# Both directions.
# --------------------------------------------------------------------------

def test_the_family_exists_on_disk():
    """The guard on the guards: every test below passes vacuously over an empty
    family, which is exactly how a deleted skill would go unnoticed."""
    found = _design_skills()
    assert "metis-test-design" in found, "the parent is missing"
    assert len(found) == 8, f"expected a parent and seven specialists, got {sorted(found)}"


def test_every_area_names_a_skill_that_exists():
    known = _all_skills()
    for area in areas.AREAS + areas.ATTRIBUTE_AREAS:
        assert area.skill in known, (
            f"area {area.ordinal} ({area.name}) names {area.skill!r}, which is "
            f"not a skill. Known: {sorted(known)}")


def test_every_design_skill_claims_an_area():
    """The other direction, so a new specialist cannot appear unaccounted for."""
    owned = ({a.skill for a in areas.AREAS}
             | {a.skill for a in areas.ATTRIBUTE_AREAS}
             | {skill for skill, _s, _c in areas.BEYOND_THE_REFERENCE})
    for name in _design_skills():
        assert name in owned, (
            f"{name} carries no area and is not in BEYOND_THE_REFERENCE — say "
            f"which activity it covers, or record that it is something Métis "
            f"adds")


def test_every_section_has_exactly_one_owning_skill():
    for key in sections.SECTIONS:
        owner = areas.owner_of(key)
        assert owner, f"section {key!r} is owned by nobody"
        assert owner in _all_skills(), f"section {key!r} names a skill that is gone"


def test_the_registry_and_the_areas_agree_about_who_owns_what():
    """Two places name the owner -- `sections.py`'s `specialist` field and
    `areas.py`'s map -- and two representations of one fact is this codebase's
    most common defect. They are written apart on purpose (a section knows its
    own skill; the map knows the activity) and they may never disagree."""
    for key, section in sections.SECTIONS.items():
        assert section.specialist == areas.owner_of(key), (
            f"section {key}: sections.py says {section.specialist!r}, "
            f"areas.py says {areas.owner_of(key)!r}")


def test_the_last_three_activities_are_owned_outside_this_family():
    """**The crossing, and it has to be real.** Design derives conditions and
    coverage items; generation derives cases, sets and procedures. If every area
    resolved back into the design family this map would be a second name for the
    same thing, and the hand-off would be implied rather than recorded."""
    crossing = [a for a in areas.AREAS if not a.skill.startswith("metis-test-design")]
    assert crossing, "no activity crosses out of the design family"
    assert {a.skill for a in crossing} == {"metis-test-generate"}
    assert {a.name for a in crossing} == {
        "Test case derivation", "Test set assembly", "Test procedure derivation"}


def test_an_activity_that_crosses_produces_no_design_section():
    """It produces test cases, not a section of this document. A `section` here
    would put a table in the design that generation owns."""
    for area in areas.AREAS:
        if area.skill == "metis-test-generate":
            assert area.section == "", (
                f"{area.name} claims section {area.section!r}, which this "
                f"document does not produce")


def test_the_parent_keeps_the_basis_and_the_uncertainty_ledger():
    """Consolidating what every section could not state IS running the design,
    so a specialist for it would be a skill that only calls its caller — the
    argument `risk/areas.py` makes about its own lifecycle area."""
    assert areas.owner_of("basis") == "metis-test-design"
    assert areas.owner_of("uncertainty") == "metis-test-design"


def test_describe_serves_both_maps_and_says_why_there_are_two():
    described = areas.describe()
    assert len(described["areas"]) == len(areas.AREAS)
    assert len(described["attribute_areas"]) == len(areas.ATTRIBUTE_AREAS)
    assert "two maps" in described["means"]


# --------------------------------------------------------------------------
# The parent routes to every specialist.
# --------------------------------------------------------------------------

def test_the_parent_routes_to_every_specialist_by_name():
    """A specialist nobody routes to is a skill with no way in. `test_skills.py`
    asserts this generically; asserted here too because the routing table is
    keyed by SECTION, and a section added without a routing row would leave the
    section owned and unreachable."""
    routing = (FAMILY / "SKILL.md").read_text()
    for name in _design_skills():
        if name == "metis-test-design":
            continue
        assert name in routing, f"the parent does not route to {name}"


def test_every_specialist_names_the_section_it_owns():
    for name, skill in _design_skills().items():
        if name == "metis-test-design":
            continue
        text = (skill.directory / "SKILL.md").read_text()
        owned = [key for key, s in sections.SECTIONS.items()
                 if s.specialist == name]
        assert owned, f"{name} owns no section"
        for key in owned:
            assert f"`{key}`" in text, (
                f"{name} owns the {key!r} section and does not say so")


# --------------------------------------------------------------------------
# The template is served, never restated.
# --------------------------------------------------------------------------

def _column_headings() -> set[str]:
    """Every column heading, excluding words a skill legitimately uses in prose.

    The exclusion matters: a guard that flagged the word "Risk" or "Notes" would
    fire on ordinary sentences, and a check that cries wolf is one people route
    around -- the same reasoning `document_table`'s scoped reads are built on.
    """
    ordinary = {"ID", "Risk", "Notes", "Owner", "Decision", "Call", "Basis",
                "Condition", "Behaviour", "Level", "Target", "Answer",
                "Question", "Status", "Input", "Claim", "Kind", "Provenance",
                "State", "Technique", "Selector", "Deviation", "Declared",
                "Recovered", "Invokes", "Decides"}
    return {c.heading for s in sections.ordered() for c in s.columns} - ordinary


def test_the_heading_scan_is_not_vacuous():
    """`test_no_skill_hand_lists_a_section_s_columns` cannot fail if it has
    nothing distinctive left to look for, which is how a guard quietly stops
    guarding."""
    assert len(_column_headings()) >= 5, (
        "almost every column heading is an ordinary word — this check would "
        "pass over a skill that listed the whole table")


def test_no_skill_hand_lists_a_section_s_columns():
    """**The rule that keeps the output deterministic.** The shape comes from
    `design_sections()`. A skill that wrote the columns out in prose would be a
    second copy of a generated fact, imitated slightly differently every run --
    which is the failure a served template exists to remove.

    This is `test_no_plugin_readme_hand_lists_the_tools` applied one layer over:
    naming a column or two in a sentence is useful and stays legal; reproducing
    a table's headings is an inventory, and an inventory drifts.
    """
    distinctive = _column_headings()
    offenders: list[str] = []
    for path in SKILLS.rglob("*.md"):
        text = path.read_text()
        for line in text.splitlines():
            stripped = line.lstrip()
            if not stripped.startswith("|"):
                continue
            named = {h for h in distinctive if h in stripped}
            if len(named) >= 3:
                offenders.append(
                    f"{path.relative_to(SKILLS)}: {sorted(named)}")
    assert not offenders, (
        "these reproduce a design section's column headings, which "
        "`design_sections()` generates: " + "; ".join(offenders))


def test_no_design_skill_restates_the_closed_vocabularies():
    """A skill listing every allowed value of a column is the same defect one
    step down: the vocabularies are imported from the modules that own them, and
    a prose copy is what starts reporting a level the coverage ledger has never
    heard of."""
    vocabularies = {c.heading: set(c.allowed)
                    for s in sections.ordered() for c in s.columns
                    if len(c.allowed) >= 3}
    assert vocabularies, "no closed vocabulary to check"

    offenders: list[str] = []
    for name, skill in _design_skills().items():
        text = " ".join(p.read_text() for p in skill.directory.rglob("*.md"))
        for heading, allowed in vocabularies.items():
            present = {value for value in allowed if f"`{value}`" in text}
            if present == allowed and len(allowed) > 3:
                offenders.append(f"{name}: the whole {heading!r} vocabulary")
    assert not offenders, (
        "these restate a closed vocabulary `design_sections()` serves: "
        + "; ".join(offenders))


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


def test_the_column_inventory_scan_recognises_an_inventory():
    """The sabotage check. `test_no_skill_hand_lists_a_section_s_columns` passes
    over a healthy tree, and a guard that has only ever passed is one nobody has
    seen work. This feeds it the line it exists to catch."""
    distinctive = _column_headings()
    inventory = ("| ID | Coverage items | Refused because | Depth achievable | "
                 "Depth warranted |")
    named = {heading for heading in distinctive if heading in inventory}
    assert len(named) >= 3, (
        "the scan would not flag a row reproducing four column headings — "
        "either the headings changed or the exclusion list has swallowed them")
