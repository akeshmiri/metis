"""
Drift and publication tests (application spec §7.6, §7.7; A-20..A-23).

Free to run: the only transport is dry-run, which makes no network call.
"""
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from metis_mcp.mbt.criteria import DEFAULT_CRITERION
from metis_mcp.mbt.path_generation import generate
from metis_mcp.publishing import (
    AFFIRMATIVE,
    CHANGED,
    CREATE,
    DEPRECATE,
    MANUALLY_EDITED,
    NEW,
    NO_ACTION,
    OBSOLETE,
    PROPOSE_NOTHING,
    UNCHANGED,
    UPDATE,
    ConfirmationRefused,
    DryRunTransport,
    PublicationLedger,
    PublishedCase,
    Transport,
    compare,
    confirm,
    content_hash,
    default_ledger_path,
    format_batch,
    format_drift,
    plan_publication,
    publish,
    record_generation,
)
from metis_mcp.rendering import render
from mbt_fixtures import login_model


def _cases():
    model = login_model()
    result = generate(model, DEFAULT_CRITERION, 10)
    return model, render(model, result.paths).cases


class RecordingTransport(Transport):
    """A-22's stub: records **every** attempt, including refused ones."""

    name = "recording"
    is_dry_run = True

    def __init__(self):
        self.attempts = []

    def send(self, operation):
        self.attempts.append(operation)
        return "sent"


def _published_ledger(cases, model_id="login-api", edited=()):
    ledger = PublicationLedger(model_id=model_id)
    record_generation(ledger, model_id, cases)
    for case in cases:
        h = content_hash(case)
        ledger.published[case.id] = PublishedCase(
            case_id=case.id, published_id=f"ZS-{case.id[-4:]}",
            content_hash=("hand-edited" if case.id in edited else h))
    return ledger


# --------------------------------------------------------------------------
# A-20 : three-way comparison distinguishes model change from manual edit
# --------------------------------------------------------------------------

def test_a20_an_unchanged_case_is_unchanged():
    model, cases = _cases()
    report = compare(cases, _published_ledger(cases))
    assert report.summary[UNCHANGED] == len(cases)
    assert report.actionable == []


def test_a20_a_model_change_reads_as_changed():
    model, cases = _cases()
    ledger = _published_ledger(cases)
    moved = [replace(cases[0], name="Something else")] + cases[1:]
    report = compare(moved, ledger)
    assert report.summary[CHANGED] == 1
    assert report.of(CHANGED)[0].case_id == cases[0].id


def test_a20_a_hand_edit_reads_as_manually_edited_not_changed():
    """The two are indistinguishable to a two-way diff — T-13's whole point."""
    model, cases = _cases()
    ledger = _published_ledger(cases, edited={cases[0].id})
    report = compare(cases, ledger)
    assert report.summary[MANUALLY_EDITED] == 1
    assert report.summary[CHANGED] == 0
    assert report.of(MANUALLY_EDITED)[0].case_id == cases[0].id


def test_a20_both_at_once_reads_as_manually_edited():
    """A case that was hand-edited AND model-changed must never be proposed for
    update: overwriting the edit is the irreversible outcome."""
    model, cases = _cases()
    ledger = _published_ledger(cases, edited={cases[0].id})
    moved = [replace(cases[0], name="Something else")] + cases[1:]
    report = compare(moved, ledger)
    assert report.summary[MANUALLY_EDITED] == 1
    assert report.summary[CHANGED] == 0


def test_a_new_path_reads_as_new():
    model, cases = _cases()
    ledger = _published_ledger(cases[1:])
    report = compare(cases, ledger)
    assert report.summary[NEW] == 1
    assert report.of(NEW)[0].case_id == cases[0].id


def test_a_vanished_path_reads_as_obsolete():
    model, cases = _cases()
    ledger = _published_ledger(cases)
    report = compare(cases[1:], ledger)
    assert report.summary[OBSOLETE] == 1
    assert "never deleted" in report.of(OBSOLETE)[0].detail


def test_the_criterion_is_not_part_of_the_content_hash():
    """T-10: regenerating under a deeper criterion must not make every case look
    edited."""
    model, cases = _cases()
    assert content_hash(cases[0]) == content_hash(replace(cases[0], criterion="guard-coverage"))


def test_a_changed_case_carries_a_real_diff():
    model, cases = _cases()
    ledger = _published_ledger(cases)
    moved = [replace(cases[0], name="Something else")] + cases[1:]
    report = compare(moved, ledger, previous_cases={c.id: c for c in cases})
    assert any("name:" in d for d in report.of(CHANGED)[0].diff)


# --------------------------------------------------------------------------
# A-21 : a manually edited case is never overwritten
# --------------------------------------------------------------------------

def test_a21_a_manually_edited_case_proposes_nothing():
    model, cases = _cases()
    report = compare(cases, _published_ledger(cases, edited={cases[0].id}))
    assert report.of(MANUALLY_EDITED)[0].action == PROPOSE_NOTHING


def test_a21_it_is_withheld_from_the_batch_with_its_reason():
    """Silently omitting it would mean the batch approved is not the batch
    the operator thinks they approved."""
    model, cases = _cases()
    report = compare(cases, _published_ledger(cases, edited={cases[0].id}))
    batch = plan_publication(report, cases)
    assert cases[0].id not in {op.case_id for op in batch.operations}
    assert any(cid == cases[0].id for cid, _ in batch.withheld)
    assert "a human decides" in format_drift(report)


def test_a21_no_operation_ever_targets_a_manually_edited_case():
    model, cases = _cases()
    ledger = _published_ledger(cases, edited={c.id for c in cases[:3]})
    batch = plan_publication(compare(cases, ledger), cases)
    assert batch.operations == []
    assert len(batch.withheld) == 3


# --------------------------------------------------------------------------
# A-22 : withholding confirmation produces ZERO external calls
# --------------------------------------------------------------------------

def test_a22_no_confirmation_means_zero_attempts():
    model, cases = _cases()
    batch = plan_publication(compare(cases, PublicationLedger(model_id="login-api")), cases)
    assert batch.size == len(cases), "there is real work to send"

    transport = RecordingTransport()
    result = publish(batch, transport, confirmation=None)

    assert not result.ok
    assert transport.attempts == [], "T-18: zero external calls were attempted"
    assert AFFIRMATIVE in result.refused


def test_a22_a_wrong_literal_is_refused_before_the_transport_is_touched():
    for bad in ("", "y", "yes", "Publish", "PUBLISH", "ok", "true"):
        try:
            confirm(bad, "alice", 1)
        except ConfirmationRefused as e:
            assert "literal word" in str(e) or "records who" in str(e)
            continue
        raise AssertionError(f"{bad!r} must not confirm publication")


def test_a22_there_is_no_default_yes_and_no_truthy_shortcut():
    """`Confirmation(True)` must be impossible — the type refuses, not a rule
    someone has to remember at each call site."""
    from metis_mcp.publishing.publish import Confirmation
    try:
        Confirmation(confirmed_by="alice", literal=True, at="now", batch_size=1)
    except ConfirmationRefused:
        return
    raise AssertionError("a truthy value must not stand in for the literal")


def test_a22_a_confirmation_records_who_gave_it():
    try:
        confirm(AFFIRMATIVE, "   ", 1)
    except ConfirmationRefused as e:
        assert "records who" in str(e)
        return
    raise AssertionError("an anonymous confirmation must be refused")


def test_a_confirmation_does_not_carry_over_to_a_different_batch():
    """T-19 gives one decision per batch, not one per session."""
    model, cases = _cases()
    small = plan_publication(compare(cases[:3], PublicationLedger(model_id="m")), cases)
    big = plan_publication(compare(cases, PublicationLedger(model_id="m")), cases)

    transport = RecordingTransport()
    result = publish(big, transport, confirm(AFFIRMATIVE, "alice", small.size))
    assert not result.ok
    assert transport.attempts == []
    assert "Re-confirm" in result.refused


def test_one_decision_covers_the_whole_batch():
    """T-19: a per-case gate produces reflexive approval."""
    model, cases = _cases()
    batch = plan_publication(compare(cases, PublicationLedger(model_id="m")), cases)
    transport = RecordingTransport()
    result = publish(batch, transport, confirm(AFFIRMATIVE, "alice", batch.size))
    assert result.ok
    assert len(transport.attempts) == batch.size == len(cases)
    assert result.confirmed_by == "alice"


# --------------------------------------------------------------------------
# A-23 : dry-run produces a valid payload and makes no network call
# --------------------------------------------------------------------------

def test_a23_dry_run_builds_a_valid_payload_and_sends_nothing():
    model, cases = _cases()
    batch = plan_publication(compare(cases, PublicationLedger(model_id="m")), cases)
    transport = DryRunTransport()
    result = publish(batch, transport, confirm(AFFIRMATIVE, "alice", batch.size))

    assert result.ok and result.dry_run
    assert len(result.sent) == len(cases)
    assert all(s.startswith("dry-run:") for s in result.sent)
    assert len(transport.attempts) == len(cases)


def test_a23_the_payload_is_validated_not_merely_assembled():
    from metis_mcp.publishing.publish import Operation
    transport = DryRunTransport()
    try:
        transport.send(Operation(action=UPDATE, case_id="tc-1",
                                 published_id="", payload={"id": "tc-1"}))
    except ValueError as e:
        assert "published id" in str(e)
        return
    raise AssertionError("an update with no published id is not a valid payload")


def test_a23_a_payload_with_no_id_is_refused():
    from metis_mcp.publishing.publish import Operation
    try:
        DryRunTransport().send(Operation(action=CREATE, case_id="tc-1",
                                         published_id="", payload={}))
    except ValueError as e:
        assert "no id" in str(e)
        return
    raise AssertionError("an id-less payload must not be sent")


def test_the_batch_is_shown_in_full_before_anything_is_sent():
    """T-17: drafts are shown in full, so a batch decision is an informed one."""
    model, cases = _cases()
    batch = plan_publication(compare(cases, PublicationLedger(model_id="m")), cases)
    text = format_batch(batch)
    assert "Nothing has been sent" in text
    assert AFFIRMATIVE in text
    for case in cases[:3]:
        assert case.id in text
    assert text.count("act:") == len(cases), "every act step is shown"


# --------------------------------------------------------------------------
# Ledger discipline
# --------------------------------------------------------------------------

def test_the_baseline_moves_only_on_a_successful_publication():
    """Recording at render time would make an abandoned run the new baseline,
    and the next comparison would read a real manual edit as unchanged."""
    model, cases = _cases()
    ledger = PublicationLedger(model_id="login-api")
    compare(cases, ledger)
    assert ledger.last_generated == {}, "comparing must not move the baseline"

    record_generation(ledger, "login-api", cases)
    assert len(ledger.last_generated) == len(cases)


def test_the_ledger_round_trips_through_a_file():
    model, cases = _cases()
    ledger = _published_ledger(cases)
    with tempfile.TemporaryDirectory() as d:
        path = default_ledger_path(Path(d) / "login-api.json")
        assert path.name == "login-api.published.json"
        ledger.save(path)
        again = PublicationLedger.load(path)
    assert again.last_generated == ledger.last_generated
    assert again.published[cases[0].id].published_id == ledger.published[cases[0].id].published_id


def test_an_already_deprecated_case_is_not_re_reported():
    model, cases = _cases()
    ledger = _published_ledger(cases)
    ledger.published[cases[0].id].published_status = "deprecated"
    report = compare(cases[1:], ledger)
    assert report.summary[OBSOLETE] == 0


def test_deprecate_operations_carry_the_published_id():
    model, cases = _cases()
    ledger = _published_ledger(cases)
    batch = plan_publication(compare(cases[1:], ledger), cases[1:])
    deprecations = [op for op in batch.operations if op.action == DEPRECATE]
    assert len(deprecations) == 1 and deprecations[0].published_id


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
        except Exception as e:
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
