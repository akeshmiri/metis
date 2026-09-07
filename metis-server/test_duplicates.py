"""The four-verdict duplicate guard, and the one verdict that matters.

`unknown` blocking is the whole reason this exists. Métis had exactly the defect
it prevents — an empty `published` map read as "nothing is published" — and the
failure was invisible under `DryRunTransport`, because nothing is sent either
way. Every test that asserts `unknown` here is asserting that the system says
"cannot tell" where it used to say "no".
"""
from metis_mcp.publishing.drift import (
    PublicationLedger, PublishedCase, content_hash,
)
from metis_mcp.publishing.duplicates import (
    EXACT_MATCH, NO_MATCH, SIMILAR_MATCH, UNKNOWN, body_hash, check, summarise,
)
from metis_mcp.rendering.test_case import Step, TestCase


def case(case_id: str, name: str = "Reject an empty name",
         expected: str = "400") -> TestCase:
    return TestCase(
        id=case_id, name=name, objective="o", model_id="records-api",
        criterion="all-transitions", target_key="t",
        precondition_steps=(),
        act_step=Step(transition_id="t1", description="POST /records",
                      wording_tier="verbatim", expected_result=expected,
                      is_assertion=True))


def verdicts_of(cases, ledger):
    return {v.case_id: v.verdict for v in check(cases, ledger)}


def live(**published) -> PublicationLedger:
    return PublicationLedger(
        model_id="records-api", live_publications=len(published) or 1,
        published={k: PublishedCase(k, v, "hash-" + k)
                   for k, v in published.items()})


# --------------------------------------------------------------------------
# The regression. This is the test the module exists for.
# --------------------------------------------------------------------------

def test_a_ledger_that_has_never_published_reports_unknown_not_no_match():
    """**The exact defect, asserted.**

    `compare` read an empty `published` map and reported "no published case for
    this path" — a confident claim of absence built on no information. A blind
    ledger must say it is blind.
    """
    blind = PublicationLedger(model_id="records-api")
    assert blind.live_publications == 0
    assert not blind.can_see_published_content

    result = check([case("TC-1"), case("TC-2")], blind)
    assert {v.verdict for v in result} == {UNKNOWN}
    assert all(not v.proceeds for v in result), "unknown must block"
    assert all("not evidence of absence" in v.detail for v in result)


def test_unknown_blocks_the_whole_batch():
    summary = summarise(check([case("TC-1")], PublicationLedger()))
    assert summary["may_proceed"] is False
    assert summary["blocked"] == 1


def test_an_empty_published_map_on_a_SEEING_ledger_is_a_real_no_match():
    """The other half: once the ledger has recorded a send, absence means absence.

    Without this the guard would block forever and be switched off.
    """
    seeing = PublicationLedger(model_id="records-api", live_publications=4)
    assert seeing.can_see_published_content
    assert verdicts_of([case("TC-1")], seeing) == {"TC-1": NO_MATCH}


# --------------------------------------------------------------------------
# The other three verdicts.
# --------------------------------------------------------------------------

def test_a_published_case_is_an_exact_match_and_carries_its_published_id():
    result = check([case("TC-1")], live(**{"TC-1": "ZEP-9"}))
    assert result[0].verdict == EXACT_MATCH
    assert result[0].published_id == "ZEP-9"
    assert not result[0].proceeds


def test_two_cases_rendering_identically_are_a_similar_match():
    """**This branch was dead when it was written, and running it is what found that.**

    It first used `drift.content_hash`, which includes `case.id` — so two cases
    with different ids could never share a hash and `similar_match` was
    unreachable. It looked exactly like a working check.
    """
    twins = [case("TC-1"), case("TC-2")]
    assert body_hash(twins[0]) == body_hash(twins[1])
    assert content_hash(twins[0]) != content_hash(twins[1]), (
        "content_hash must still include the id — drift depends on it")

    result = verdicts_of(twins, PublicationLedger(model_id="records-api",
                                                  live_publications=2))
    assert result == {"TC-1": SIMILAR_MATCH, "TC-2": SIMILAR_MATCH}


def test_a_genuinely_different_case_is_no_match():
    cases = [case("TC-1"), case("TC-2", name="Reject a name over 40 chars",
                                expected="422")]
    result = verdicts_of(cases, PublicationLedger(model_id="records-api",
                                                  live_publications=2))
    assert result == {"TC-1": NO_MATCH, "TC-2": NO_MATCH}


def test_all_four_verdicts_are_reachable():
    """A vocabulary with an unreachable member is a vocabulary that lies."""
    reached = set()
    reached |= {v.verdict for v in check([case("TC-1")], PublicationLedger())}
    seeing = live(**{"TC-1": "ZEP-9"})
    reached |= {v.verdict for v in check(
        [case("TC-1"), case("TC-2"), case("TC-3"),
         case("TC-4", name="Something else")], seeing)}
    assert reached == {UNKNOWN, EXACT_MATCH, SIMILAR_MATCH, NO_MATCH}


# --------------------------------------------------------------------------
# The rollup.
# --------------------------------------------------------------------------

def test_a_batch_is_not_partially_safe_to_publish():
    """One blocked case blocks the batch: the decision is about the batch."""
    cases = [case("TC-1"), case("TC-2", name="Reject a long name")]
    summary = summarise(check(cases, live(**{"TC-1": "ZEP-9"})))
    assert summary["counts"] == {EXACT_MATCH: 1, NO_MATCH: 1}
    assert summary["may_proceed"] is False


def test_all_clear_proceeds():
    cases = [case("TC-1"), case("TC-2", name="Reject a long name")]
    summary = summarise(check(cases, PublicationLedger(model_id="records-api",
                                                       live_publications=2)))
    assert summary["may_proceed"] is True
    assert summary["blocked"] == 0


def test_an_empty_batch_does_not_proceed():
    """Nothing to publish is not permission to publish."""
    assert summarise([])["may_proceed"] is False
