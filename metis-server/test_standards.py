"""The test documentation standards map, asserted in both directions.

**The failure this file exists to prevent.** A standards map is exactly the shape
of thing `docs/academy/10-where-a-thing-belongs.md` says rots: a hand-maintained
index that nothing generates and nothing checks. Atlas's own experience is quoted
there — its hand-written skill catalogue drifted to roughly forty-five names
matching no directory, while its generated registry did not drift at all.

So every claim here is checked against the section registry that is its subject:
a work product naming a section that does not exist fails, and a section claimed
by no work product and not recorded as Métis's own fails the other way.
"""
from __future__ import annotations

import sys

import pytest

from metis_mcp.design import sections, standards


# --------------------------------------------------------------------------
# Both directions.
# --------------------------------------------------------------------------

def test_there_are_work_products_to_check():
    """The guard on the guards: every assertion below passes over an empty map."""
    assert standards.WORK_PRODUCTS
    assert standards.METIS_OWN


def test_every_work_product_names_sections_that_exist():
    for product in standards.WORK_PRODUCTS:
        for key in product.sections:
            assert key in sections.SECTIONS, (
                f"{product.code} names section {key!r}, which the registry does "
                f"not have")


def test_every_section_is_claimed_or_recorded_as_metis_own():
    """The other direction. A section absent from every work product and absent
    from `METIS_OWN` is indistinguishable from one somebody forgot to map —
    which is the whole reason `METIS_OWN` is a list with reasons rather than an
    implicit remainder."""
    claimed = {key for product in standards.WORK_PRODUCTS
               for key in product.sections}
    unmapped = sorted(set(sections.SECTIONS) - claimed - set(standards.METIS_OWN))
    assert not unmapped, (
        f"these sections answer no work product and are not recorded as Métis's "
        f"own: {unmapped}")


def test_every_metis_own_entry_names_a_real_section_and_says_why():
    for key, because in standards.METIS_OWN.items():
        assert key in sections.SECTIONS, f"{key!r} is not a section"
        assert because.strip(), f"{key} is claimed as Métis's own with no reason"


def test_a_metis_own_section_is_not_also_claimed_by_a_work_product():
    """Both at once would be two answers to one question, and a reader would
    have no way to tell which the document meant."""
    claimed = {key for product in standards.WORK_PRODUCTS
               for key in product.sections}
    overlap = sorted(claimed & set(standards.METIS_OWN))
    assert not overlap, f"claimed and Métis's own at the same time: {overlap}"


# --------------------------------------------------------------------------
# The coverage claim itself.
# --------------------------------------------------------------------------

def test_every_coverage_value_is_declared():
    for product in standards.WORK_PRODUCTS:
        assert product.coverage in standards.COVERAGE, (
            f"{product.code} has coverage {product.coverage!r}")


def test_anything_not_full_says_what_is_missing():
    """**A gap with no reason cannot be told from one nobody looked at.** This is
    the same rule `absent_means` keeps in the two ledgers, applied to a coverage
    claim."""
    for product in standards.WORK_PRODUCTS:
        if product.coverage == standards.FULL:
            continue
        assert product.because.strip(), (
            f"{product.code} is {product.coverage} and does not say what is "
            f"missing")


def test_out_of_scope_products_name_no_section_and_full_ones_do():
    for product in standards.WORK_PRODUCTS:
        if product.coverage == standards.OUT_OF_SCOPE:
            assert product.sections == (), (
                f"{product.code} is out of scope and claims {product.sections}")
        else:
            assert product.sections, (
                f"{product.code} claims {product.coverage} coverage and names "
                f"no section that provides it")


def test_the_three_execution_artefacts_are_out_of_scope():
    """**The C-10 / C-11 split, in the standards' own vocabulary.** A Test Log
    and a Test Incident Report are observations; a Test Summary Report is a
    result. A design has run nothing, so claiming any of them would be claiming
    the coverage ledger and the correctness figure in one move."""
    for code in ("TL", "TIR", "TSR"):
        product = standards.by_code(code)
        assert product.coverage == standards.OUT_OF_SCOPE
        assert product.because, f"{code} must say where it actually lives"


def test_no_coverage_claim_reads_as_a_compliance_claim():
    """The map says which section answers which product. Whether that satisfies
    an obligation is a judgement about the obligation — and a `because` line
    promising conformance would be Métis certifying something it cannot
    compute."""
    banned = ("satisfies", "compliant", "conforms to", "certifi", "audit-ready")
    for product in standards.WORK_PRODUCTS:
        lowered = product.because.lower()
        for phrase in banned:
            assert phrase not in lowered, (
                f"{product.code} reads as a compliance claim: {product.because!r}")
    assert "does NOT claim" in standards.describe()["means"]


def test_an_unknown_code_is_refused_by_name():
    with pytest.raises(standards.UnknownWorkProduct) as raised:
        standards.by_code("XYZ")
    assert "XYZ" in str(raised.value)
    assert "TDS" in str(raised.value), "the refusal lists what exists"


# --------------------------------------------------------------------------
# The identifier scheme.
# --------------------------------------------------------------------------

def test_a_row_carrying_a_code_gets_it_from_the_map():
    """Stamped in one place (`document.build`) rather than by each builder, so a
    row and the compliance table cannot disagree about which product it belongs
    to — and a builder cannot forget."""
    import mbt_fixtures
    from metis_mcp.design import builders, document

    doc = document.build("login (api)", builders.DesignContext(
        model=mbt_fixtures.login_model()))
    by_key = {s["key"]: s for s in doc["sections"]}
    for key in ("technique", "data", "levels"):
        rows = by_key[key]["rows"]
        assert rows, f"{key} produced no row to classify"
        expected = standards.code_for(key)
        assert expected, f"{key} carries a work_product column and maps to none"
        assert {row["work_product"] for row in rows} == {expected}


def test_a_code_is_a_classification_and_never_an_identity():
    """TD-32: ids stay content-derived. If a code were part of the id, moving a
    section between work products would renumber every decision recorded
    against it."""
    import mbt_fixtures
    from metis_mcp.design import builders

    rows = builders.build_technique(builders.DesignContext(
        model=mbt_fixtures.login_model()))
    for row in rows:
        assert standards.code_for("technique") not in row["id"]


def test_only_sections_that_answer_a_product_carry_a_code():
    """A section recorded as Métis's own has no product to classify its rows
    under, and inventing one would put it inside a standard it is outside of."""
    for key in standards.METIS_OWN:
        section = sections.SECTIONS[key]
        assert not any(c.key == "work_product" for c in section.columns), (
            f"{key} is Métis's own and carries a work-product column")


# --------------------------------------------------------------------------
# The references.
# --------------------------------------------------------------------------

def test_both_side_references_exist_and_are_cited():
    """`references/` is for what would still be true if Métis were deleted, and
    `test_skills.py` already refuses an uncited one. This names them, so a
    deletion fails here with the reason rather than there with a glob."""
    from pathlib import Path

    skills = Path(__file__).resolve().parent.parent / "plugins" / "metis" / "skills"
    family = skills / "metis-test-design"
    citing = (family / "SKILL.md").read_text()
    for name in ("ieee-829-work-products.md", "life-cycle-alignment.md"):
        assert (family / "references" / name).exists(), f"{name} is missing"
        assert name in citing, f"{name} is cited by nothing"


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
