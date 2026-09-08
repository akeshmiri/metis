"""The published-standards registry (`metis_mcp/standards.py`).

**Not to be confused with `test_standards.py` beside it**, which asserts the
*work product* map in `design/standards.py` — which design section answers which
29119-3 or IEEE 829 document. This file asserts the other direction: which
published standard governs which skill, where it is read, and what Métis refuses
to claim about it. Two maps, two subjects, and the reason both exist is that
neither answers the other's question.


**Why this file exists.** Métis named six published standards and carried a
reference document for two of them. ISO/IEC/IEEE 29119-3 was a *tool* with no
reference; 29119-4 and ISO/IEC 25010 were bare mentions inside sentences; 29148
appeared only in engine docstrings, where no skill could reach it; ISO 31000 was
named nowhere at all, in the family that runs a full risk lifecycle.

Nothing failed, because nothing checked. That is the same hand-maintained-index
failure `docs/academy/10-where-a-thing-belongs.md` records twice, so this asserts
the map in both directions — and asserts the one property that keeps it from
becoming a compliance claim.
"""
from __future__ import annotations

import re
from pathlib import Path

from metis_mcp import standards

SKILLS = Path(__file__).resolve().parent.parent / "plugins" / "metis" / "skills"


def test_there_are_standards_to_check():
    """The guard on the guard: every assertion below iterates the registry."""
    assert len(standards.STANDARDS) >= 6, "the registry has been emptied"


# --------------------------------------------------------------------------
# Direction one: every registered standard resolves.
# --------------------------------------------------------------------------

def test_every_standard_names_a_reference_that_exists():
    """A registry entry pointing at nothing is worse than no entry: it reads as
    a document somebody could go and read."""
    for std in standards.STANDARDS:
        path = SKILLS / std.reference
        assert path.exists(), f"{std.code} names a missing reference: {std.reference}"


def test_every_standard_names_skills_that_exist():
    for std in standards.STANDARDS:
        assert std.skills, f"{std.code} governs no skill"
        for name in std.skills:
            # A specialist lives one level down; both spellings are legal.
            direct = SKILLS / name / "SKILL.md"
            nested = list(SKILLS.glob(f"*/specialists/*/SKILL.md"))
            found = direct.exists() or any(
                _skill_name(p) == name for p in nested)
            assert found, f"{std.code} names a skill that does not exist: {name}"


def _skill_name(path: Path) -> str:
    head = path.read_text().split("---")
    match = re.search(r"^name:\s*(\S+)", head[1] if len(head) > 1 else "", re.M)
    return match.group(1) if match else ""


def test_every_standard_states_what_it_does_not_claim():
    """**The load-bearing assertion in this file.**

    `design/standards.py` already forbids a `because` line that reads as a
    compliance claim, and gives the reason at length: Métis can say which
    section answers which work product, and cannot say whether that satisfies
    anybody's obligation. A registry that widened the mapping without carrying
    that prohibition forward would produce exactly the artefact the prohibition
    exists to prevent — a table that looks like a certificate.
    """
    for std in standards.STANDARDS:
        assert std.refuses.strip(), f"{std.code} states no limit on its claim"
        assert len(std.refuses) > 60, (
            f"{std.code}'s limit is too short to say anything: {std.refuses!r}")


def test_every_standard_names_where_the_computing_happens():
    """A reader who disagrees must be able to find the code and argue with it.

    **An empty `computes` is legal and must be declared.** One entry —
    12207/15288 — is a life-cycle alignment a person recorded, and nothing
    computes it. Naming a module there to satisfy the shape of the other entries
    would put a fabricated citation exactly where the honest answer is "nobody
    computes this", so the empty case is allowed and the *declaration* is what
    is asserted instead.
    """
    for std in standards.STANDARDS:
        if not std.computes:
            assert "Nothing computes" in std.refuses, (
                f"{std.code} computes nothing and does not say so in `refuses`")
            continue
        joined = " ".join(std.computes)
        assert ".py" in joined or "`" in joined, (
            f"{std.code} names no module or tool for what it computes")


def test_no_entry_claims_conformance():
    """The word that must never appear as a claim.

    Scoped to `computes`, which is where a claim would live. `refuses` says
    things like "makes no conformance claim", which is the opposite and must
    stay sayable.
    """
    banned = ("complies", "compliant", "conformant", "certified", "conforms to")
    for std in standards.STANDARDS:
        for claim in std.computes:
            lowered = claim.lower()
            for word in banned:
                assert word not in lowered, (
                    f"{std.code} claims conformance in `computes`: {claim!r}")


# --------------------------------------------------------------------------
# Direction two: every reference on disk is registered and reachable.
# --------------------------------------------------------------------------

def _standards_references() -> list[Path]:
    """Reference files whose name marks them as being about a standard."""
    return sorted(p for p in SKILLS.rglob("references/*.md")
                  if re.match(r"^(iso|ieee)-", p.name))


def test_the_reference_scan_is_not_vacuous():
    assert _standards_references(), (
        "no standards reference files found — the naming convention the scan "
        "depends on has changed")


def test_every_standards_reference_on_disk_is_registered():
    """An orphan reference is the failure this registry was written to end."""
    registered = {std.reference for std in standards.STANDARDS}
    for path in _standards_references():
        relative = str(path.relative_to(SKILLS))
        assert relative in registered, (
            f"{relative} is a standards reference that no registry entry names")


def test_every_reference_says_what_metis_does_not_claim():
    """The same prohibition, on the prose side.

    A reference that only described a standard would read as an endorsement of
    whatever Métis produces against it.
    """
    for path in _standards_references():
        text = path.read_text()
        assert "does not do" in text or "does not claim" in text, (
            f"{path.name} never states what it does not claim")
        assert "not loaded by default" in text, (
            f"{path.name} does not declare itself a side reference — "
            "`references/` is paid for only on lookup")


def test_every_reference_is_cited_by_the_skills_that_own_it():
    """A reference nothing points at is not a reference.

    `test_skills.py` asserts that *something* cites each shared asset; this
    asserts the specific skills the registry says own it do, which is the claim
    that would otherwise be untrue while the looser one passed.
    """
    for std in standards.STANDARDS:
        filename = Path(std.reference).name
        for name in std.skills:
            path = _skill_path(name)
            assert path is not None, f"{name} has no SKILL.md"
            assert filename in path.read_text(), (
                f"{name} is registered as an owner of {std.code} and never "
                f"cites {filename}")


def _skill_path(name: str) -> Path | None:
    direct = SKILLS / name / "SKILL.md"
    if direct.exists():
        return direct
    for path in SKILLS.glob("*/specialists/*/SKILL.md"):
        if _skill_name(path) == name:
            return path
    return None


# --------------------------------------------------------------------------
# The two registries must agree.
# --------------------------------------------------------------------------

def test_the_work_product_map_and_the_registry_name_the_same_standards():
    """`design/standards.py` maps work products; this maps documents to skills.

    Two modules naming the same two standards differently is how a reader ends
    up trusting whichever they opened first.
    """
    from metis_mcp.design import standards as work_products

    mapped = {work_products.ISO_29119_3, work_products.IEEE_829}
    registered = {std.code for std in standards.STANDARDS}
    missing = mapped - registered
    assert not missing, (
        f"design/standards.py maps {missing} and the registry does not carry it")


def test_describe_serves_the_map_and_says_what_it_omits():
    served = standards.describe()
    assert served["standards"], "describe() serves nothing"
    assert "never a compliance claim" in served["means"]
    # The omission is stated rather than left to be discovered: these are
    # purchased documents and the references do not reproduce them.
    assert "does_not_include" in served
    assert "text of any standard" in served["does_not_include"]


def test_for_skill_finds_a_specialist_as_well_as_a_parent():
    assert standards.for_skill("metis-risk-manager"), "parent lookup failed"
    assert standards.for_skill("metis-test-design-technique"), (
        "a specialist that owns a standard is not reachable by name")
    assert not standards.for_skill("no-such-skill")
