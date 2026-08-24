"""
Guards in business language (application spec X-7, X-8, T-6, M-9).

The model is `State -[:WHEN]-> Transition -[:THEN]-> State` — given, action,
verification — and the guard is the *given*. It was the one position nothing
translated: `naming.py` has a cascade for names and `rendering.test_case` has one
for step wording, and between them a stakeholder read

    Given Metric, When GET /metric/{id}, Then MetricGetActionByIdNoContent204
    -- when request_accepted AND t.isEmpty()

**These tests pin the line this module refuses to cross**, because that line is
the whole design. It decodes conventions the model has *already committed to*
elsewhere, and passes through anything else untranslated with a record of what it
could not say. `ex.getCause() instanceof ConstraintViolationException` means a
duplicate was submitted; no decoder can know that, and inventing it is what T-6
forbids.
"""
from __future__ import annotations

import sys

from code_analysis.unfolding import presence_sense, resource_noun, resource_of
from metis_mcp.mbt.guard_language import (
    TIER_CODE_CONVENTION,
    TIER_VERBATIM,
    decode_atom,
    describe_guard,
)


# --------------------------------------------------------------------------
# What it says.
# --------------------------------------------------------------------------

def test_the_presence_idiom_becomes_a_sentence_about_the_resource():
    assert decode_atom("t.isEmpty()", "user") == "no user exists"
    assert decode_atom("NOT (t.isEmpty())", "user") == "the user exists"
    assert decode_atom("dbRecord.isPresent()", "project") == "the project exists"
    assert decode_atom("NOT (dbRecord.isPresent())", "project") == "no project exists"


def test_the_noun_comes_from_the_path_never_from_the_guards_variable():
    """`t` is the variable at 42 endpoints — one shared helper in records-common.

    Naming the noun from it would call every resource in the estate `t`, which is
    the same mistake `unfolding.resource_of` exists to prevent for state ids.
    """
    assert resource_noun(resource_of("/user/{id}")) == "user"
    assert resource_noun(resource_of("/tms/execution/{id}")) == "tms execution"
    assert decode_atom("t.isEmpty()", resource_noun(resource_of("/user/{id}"))) == (
        "no user exists")


def test_metis_own_minted_propositions_are_decoded():
    """`payload_valid` and `request_accepted` appear in no source file — Métis
    minted them in `dimension_recovery`, so their meaning is exactly what we
    defined it to be. Decoding our own vocabulary speculates about nothing."""
    assert decode_atom("payload_valid") == "the payload is valid"
    assert decode_atom("NOT (payload_valid)") == "the payload is invalid"
    assert decode_atom("request_accepted") == "the request is accepted"
    assert decode_atom("NOT (request_accepted)") == "the request is rejected"


def test_a_whole_conjunction_reads_as_one_sentence_in_written_order():
    wording = describe_guard("request_accepted AND t.isEmpty()", "user")
    assert wording.text == "the request is accepted and no user exists"
    assert wording.tier == TIER_CODE_CONVENTION
    assert wording.is_complete


def test_an_unconditional_guard_says_so_rather_than_rendering_blank():
    """"Always" is a real claim about the behaviour, and a reviewer needs to see
    it to disagree with it. A blank reads as missing information."""
    wording = describe_guard("", "user")
    assert wording.text == "always"
    assert wording.is_complete


# --------------------------------------------------------------------------
# What it refuses to say. This is the load-bearing half.
# --------------------------------------------------------------------------

def test_domain_meaning_the_code_never_states_is_passed_through_untouched():
    """15 guards in the pilot estate contain this. It means "a duplicate was
    submitted" — and nothing in the source says so, so this module must not."""
    atom = "ex.getCause() instanceof ConstraintViolationException"
    assert decode_atom(atom) == ""
    wording = describe_guard(atom)
    assert wording.text == atom
    assert wording.tier == TIER_VERBATIM
    assert not wording.is_complete


def test_a_partly_decodable_guard_says_which_part_it_could_not_translate():
    """A guard half in business language and half in code must not read as though
    the whole condition were understood."""
    wording = describe_guard(
        "payload_valid AND ex.getCause() instanceof ConstraintViolationException")
    assert wording.text.startswith("the payload is valid and ")
    assert wording.decoded == ("payload_valid",)
    assert wording.verbatim_atoms == (
        "ex.getCause() instanceof ConstraintViolationException",)
    assert not wording.is_complete, "partly translated is not translated"


def test_a_disjunction_is_refused_whole():
    """`_conjuncts` refuses an OR because deciding it needs real boolean
    reasoning; rendering half of one would be worse than the raw condition."""
    wording = describe_guard("a.isEmpty() OR b.isEmpty()", "user")
    assert wording.tier == TIER_VERBATIM
    assert wording.text == "a.isEmpty() OR b.isEmpty()"


def test_an_unrecognised_atom_never_becomes_a_guess():
    assert decode_atom("version.getCode() == null") == ""
    assert decode_atom("severity >= 5") == ""


# --------------------------------------------------------------------------
# The consistency argument this module rests on.
# --------------------------------------------------------------------------

def test_the_wording_agrees_with_the_unfolding_that_already_acted_on_it():
    """**This is why the translation is not an invention.**

    `presence_sense` decides `t.isEmpty()` means the resource is absent, and the
    M-6 pass has already built `MetricPresent` and re-parented readers on the
    strength of that decision. The wording restates a commitment the graph
    already carries; the two must never disagree.
    """
    for atom, resource in (("t.isEmpty()", "metric"),
                           ("NOT (t.isEmpty())", "metric"),
                           ("dbRecord.isPresent()", "metric"),
                           ("NOT (dbRecord.isPresent())", "metric")):
        sense = presence_sense(atom)
        assert sense is not None, f"unfolding does not recognise {atom}"
        _, unfolding_says_present = sense
        wording = decode_atom(atom, resource)
        wording_says_present = wording == f"the {resource} exists"
        assert wording_says_present == unfolding_says_present, (
            f"{atom}: unfolding says present={unfolding_says_present}, "
            f"wording says {wording!r}")


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
