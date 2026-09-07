"""
Drift and publication tests (application spec §7.6, §7.7; A-20..A-23).

Free to run: these tests select the dry-run transport, which makes no network
call. That is a property of what they pass, not of what exists — `zephyr-scale`
is registered too, and reaching it takes a literal in the run AND
`METIS_ALLOW_EXTERNAL_WRITES=yes` on the installation.
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


def test_the_reprint_instruction_is_runnable_from_the_graph():
    """The refusal prints the command to re-run. `args.model` is None when
    publishing from the graph, so it printed `publish None --confirm publish` —
    an instruction that fails if a reader copies it, which is the only reason
    that line exists.

    Asserted against the CLI source rather than by running it, because the
    behaviour needs a graph and the defect is entirely in the string.
    """
    import pathlib
    import re

    from metis_mcp.mbt import cli

    source = pathlib.Path(cli.__file__).read_text()
    start = source.index("def cmd_publish(")
    block = source[start:source.index("\ndef ", start + 1)]
    assert "{args.model}" not in block, (
        "the re-run instruction interpolates args.model, which is None when "
        "publishing from the graph"
    )
    assert "--journey" in block, (
        "the graph case must print the scope it was actually given"
    )
    # And the scope is chosen, not assumed.
    assert re.search(r"if args\.model", block)


# ---------------------------------------------------------------------------
# The gate in front of the gate: an autopilot can type a literal.
# ---------------------------------------------------------------------------

def _real_batch():
    """A batch with real work in it, built the way the A-22 test builds one."""
    model, cases = _cases()
    return plan_publication(
        compare(cases, PublicationLedger(model_id="login-api")), cases)


def _live_transport(recorder):
    from metis_mcp.publishing.publish import Transport

    class Live(Transport):
        name = "live-stub"
        is_dry_run = False

        def send(self, operation):
            recorder.append(operation)
            return "sent"

    return Live()


def test_a_live_transport_is_refused_unless_the_installation_permits_it(monkeypatch):
    """G2's literal is a string an agent can supply as easily as a person.

    T-18 was written against a human forgetting to confirm; it was not written
    against a caller confirming on the human's behalf. A real write therefore
    needs two things from different places: the literal, from whoever is driving
    the run, and this, from the environment the deployment was configured with.
    """
    from metis_mcp.publishing.publish import (
        AFFIRMATIVE, EXTERNAL_WRITES_ENV, confirm, publish,
    )

    monkeypatch.delenv(EXTERNAL_WRITES_ENV, raising=False)
    attempts = []
    batch = _real_batch()
    result = publish(batch, _live_transport(attempts),
                     confirm(AFFIRMATIVE, "sam", batch.size))

    assert not result.ok
    assert attempts == [], "A-22: zero attempts, not an attempt rolled back"
    assert EXTERNAL_WRITES_ENV in result.refused
    assert "Nothing was sent" in result.refused


def test_only_the_exact_word_yes_enables_external_writes(monkeypatch):
    """`true`, `1` and `on` are what a script sets by accident or a config
    template carries by default. The value of this switch is that it cannot be
    arrived at without meaning it."""
    from metis_mcp.publishing.publish import (
        EXTERNAL_WRITES_ENV, external_writes_allowed,
    )

    for value in ("true", "1", "on", "YES please", "", "no"):
        monkeypatch.setenv(EXTERNAL_WRITES_ENV, value)
        assert not external_writes_allowed(), f"{value!r} must not enable writes"
    for value in ("yes", "YES", " yes "):
        monkeypatch.setenv(EXTERNAL_WRITES_ENV, value)
        assert external_writes_allowed(), f"{value!r} should enable writes"


def test_a_dry_run_never_needs_the_switch(monkeypatch):
    """Off means DRY RUN, not an error: the safe failure is "nothing was sent",
    never "something was sent because nobody said not to"."""
    from metis_mcp.publishing.publish import (
        AFFIRMATIVE, EXTERNAL_WRITES_ENV, DryRunTransport, confirm, publish,
    )

    monkeypatch.delenv(EXTERNAL_WRITES_ENV, raising=False)
    batch = _real_batch()
    result = publish(batch, DryRunTransport(), confirm(AFFIRMATIVE, "sam", batch.size))
    assert result.ok and result.dry_run


# --------------------------------------------------------------------------
# The live transport (W4) — the only thing in Métis that writes outside it.
#
# **No test here makes a network call.** `urlopen` is replaced; what is asserted
# is the gate in front of the send and the handling of what comes back, because
# a test that needed a real tracker would either be skipped forever or would
# create records somebody has to clean up.
# --------------------------------------------------------------------------

import io as _io
import json as _json
import urllib.error as _urlerror

import pytest

from metis_mcp.publishing.publish import ExternalWritesDisabled

import metis_mcp.publishing.zephyr as _zephyr
from metis_mcp.publishing.publish import CREATE, DEPRECATE, UPDATE, Operation
from metis_mcp.publishing.zephyr import PublicationFailed, ZephyrScaleTransport


def _configured(monkeypatch, allow=True):
    monkeypatch.setenv(_zephyr.BASE_URL_ENV, "https://tracker.example.com/api")
    monkeypatch.setenv(_zephyr.TOKEN_ENV, "a-token")
    monkeypatch.setenv(_zephyr.PROJECT_ENV, "DEMO")
    if allow:
        monkeypatch.setenv("METIS_ALLOW_EXTERNAL_WRITES", "yes")
    else:
        monkeypatch.delenv("METIS_ALLOW_EXTERNAL_WRITES", raising=False)
    return ZephyrScaleTransport()


def _responds(monkeypatch, body: dict, existing: list | None = None):
    """Answer the duplicate search and the write separately.

    A create now searches first, so a stub that returns the write's body to both
    calls makes the search look like a hit. `existing` is what the search finds;
    empty by default, which is the "searched, found nothing" case.
    """
    def _fake(request, timeout=None):
        searching = "/testcase/search" in request.full_url
        payload = {"values": existing or []} if searching else body

        class _R:
            def read(self):
                return _json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False
        if not searching:
            _fake.seen = request
        return _R()
    monkeypatch.setattr(_zephyr.urllib.request, "urlopen", _fake)
    return _fake


def test_the_live_transport_is_not_a_dry_run():
    """`is_dry_run` is what arms `check_permitted`. If this flips, the
    installation switch stops applying and the gate is one key, not two."""
    assert ZephyrScaleTransport.is_dry_run is False


def test_a_g2_confirmation_alone_does_not_permit_an_external_write(monkeypatch):
    """The argument the second switch exists for: the literal can be supplied by
    whatever is driving the run, including an agent. A deployment switch cannot."""
    transport = _configured(monkeypatch, allow=False)
    with pytest.raises(ExternalWritesDisabled):
        transport.check_permitted()


def test_a_half_configured_installation_fails_before_the_batch_starts(monkeypatch):
    """T-19 makes a batch one decision. Discovering a missing base URL on
    operation four leaves three records created and the rest not."""
    monkeypatch.setenv("METIS_ALLOW_EXTERNAL_WRITES", "yes")
    monkeypatch.delenv(_zephyr.BASE_URL_ENV, raising=False)
    monkeypatch.setenv(_zephyr.TOKEN_ENV, "a-token")
    monkeypatch.setenv(_zephyr.PROJECT_ENV, "DEMO")
    with pytest.raises(PublicationFailed) as e:
        ZephyrScaleTransport().check_permitted()
    assert _zephyr.BASE_URL_ENV in str(e.value) and "Nothing was sent" in str(e.value)


def test_the_token_never_comes_from_an_argument_in_the_public_path(monkeypatch):
    """PLT-005: a secret in argv is in the shell history and the process list.
    The constructor accepts one only so a test need not set an environment
    variable; nothing in the CLI or the workflow passes it."""
    import pathlib as _p

    for path in (_p.Path("metis_mcp/mbt/cli.py"),
                 _p.Path("metis_mcp/workflow/handlers.py")):
        assert "ZephyrScaleTransport(" not in path.read_text() or \
               "token=" not in path.read_text()


def test_a_published_id_comes_back_and_is_what_the_ledger_was_missing(monkeypatch):
    """`DryRunTransport` structurally cannot produce this, which is why
    MANUALLY_EDITED and OBSOLETE always read zero without a live transport."""
    transport = _configured(monkeypatch)
    _responds(monkeypatch, {"key": "DEMO-T42"})
    published = transport.send(Operation(action=CREATE, case_id="c1",
                                         published_id="", payload={"name": "x"}))
    assert published == "DEMO-T42"
    assert transport.sent == [("c1", "DEMO-T42")]


def test_a_response_with_no_id_is_refused_rather_than_invented(monkeypatch):
    """The write may have succeeded. Saying so beats putting a fiction in the
    ledger, which is what a generated id would be."""
    transport = _configured(monkeypatch)
    _responds(monkeypatch, {"ok": True})
    with pytest.raises(PublicationFailed) as e:
        transport.send(Operation(action=CREATE, case_id="c1", published_id="",
                                 payload={"name": "Archive a record"}))
    assert "unknown" in str(e.value)


def test_an_unreachable_tracker_says_the_outcome_is_unknown(monkeypatch):
    """A timeout is not a failure to write — it is not knowing. A caller told
    "failed" retries, and a retry after a write that landed creates a duplicate."""
    transport = _configured(monkeypatch)

    def _boom(request, timeout=None):
        raise _urlerror.URLError("connection refused")
    monkeypatch.setattr(_zephyr.urllib.request, "urlopen", _boom)

    with pytest.raises(PublicationFailed) as e:
        transport.send(Operation(action=CREATE, case_id="c1", published_id="",
                                 payload={"name": "Archive a record"}))
    # The search is what fails first now, and its message is the right one: a
    # lookup that could not run is not evidence of absence.
    assert "not evidence of absence" in str(e.value)


def test_an_update_without_a_published_id_is_refused(monkeypatch):
    """Updating needs the id of an existing case; without it the URL would be
    malformed and the request would create or clobber something else."""
    transport = _configured(monkeypatch)
    with pytest.raises(PublicationFailed):
        transport.send(Operation(action=UPDATE, case_id="c1", published_id="",
                                 payload={}))


def test_deprecation_is_a_status_change_and_never_a_delete(monkeypatch):
    """A published case somebody may have run is evidence of what was verified."""
    transport = _configured(monkeypatch)
    fake = _responds(monkeypatch, {"key": "DEMO-T1"})
    transport.send(Operation(action=DEPRECATE, case_id="c1",
                             published_id="DEMO-T1", payload={}))
    assert fake.seen.method == "PUT"
    assert _json.loads(fake.seen.data)["status"] == "Deprecated"


def test_the_failure_message_does_not_echo_the_request_body(monkeypatch):
    """It ends up in logs, and the body sits next to an Authorization header."""
    transport = _configured(monkeypatch)

    def _http_error(request, timeout=None):
        raise _urlerror.HTTPError("u", 401, "Unauthorized", {}, _io.BytesIO(b""))
    monkeypatch.setattr(_zephyr.urllib.request, "urlopen", _http_error)

    with pytest.raises(PublicationFailed) as e:
        transport.send(Operation(action=CREATE, case_id="c1", published_id="",
                                 payload={"name": "N", "secret": "sensitive-value"}))
    assert "sensitive-value" not in str(e.value)
    assert "a-token" not in str(e.value)


# --------------------------------------------------------------------------
# Check-before-create, and the ledger that could not see.
#
# Ported from Atlas's duplicate-guard discipline, whose central rule is that a
# lookup which could not run is **not** evidence of absence. Métis had the
# matching defect in two places at once: nothing ever wrote
# `PublicationLedger.published` — only deserialisation and these tests did — and
# `compare` read the resulting empty map as "no published case for this path".
# Under dry-run that is invisible; the moment a live transport runs against such
# a ledger, every case reads as new and is created a second time.
# --------------------------------------------------------------------------

def test_an_existing_case_is_not_created_a_second_time(monkeypatch):
    transport = _configured(monkeypatch)
    _responds(monkeypatch, {"key": "NEW"},
              existing=[{"name": "Archive a record", "key": "DEMO-T7"}])
    with pytest.raises(PublicationFailed) as e:
        transport.send(Operation(action=CREATE, case_id="c1", published_id="",
                                 payload={"name": "Archive a record"}))
    assert "DEMO-T7" in str(e.value)
    assert transport.sent == [], "it created despite finding a duplicate"


def test_a_failed_duplicate_search_blocks_rather_than_assuming_absence(monkeypatch):
    """**The rule this port is built on.** Reading a timed-out lookup as
    "nothing there" is how a duplicate gets created."""
    transport = _configured(monkeypatch)

    def _boom(request, timeout=None):
        raise _urlerror.URLError("search unavailable")
    monkeypatch.setattr(_zephyr.urllib.request, "urlopen", _boom)

    with pytest.raises(PublicationFailed) as e:
        transport.send(Operation(action=CREATE, case_id="c1", published_id="",
                                 payload={"name": "Archive a record"}))
    assert "not evidence of absence" in str(e.value)
    assert transport.sent == []


def test_a_clean_search_lets_the_create_through(monkeypatch):
    """The guard must not become a machine that only refuses."""
    transport = _configured(monkeypatch)
    _responds(monkeypatch, {"key": "DEMO-T9"}, existing=[])
    assert transport.send(Operation(action=CREATE, case_id="c1",
                                    published_id="",
                                    payload={"name": "Archive"})) == "DEMO-T9"


def test_update_and_deprecate_are_not_duplicate_checked(monkeypatch):
    """Only a create can duplicate; the others address a record by id."""
    transport = _configured(monkeypatch)
    _responds(monkeypatch, {"key": "DEMO-T1"},
              existing=[{"name": "anything", "key": "DEMO-T1"}])
    assert transport.send(Operation(action=UPDATE, case_id="c1",
                                    published_id="DEMO-T1",
                                    payload={"name": "anything"})) == "DEMO-T1"


def test_a_ledger_that_never_published_says_unknown_not_no():
    """`NEW` is still the class — there is nothing else it could be — but the
    detail must not claim knowledge the ledger does not have."""
    from metis_mcp.publishing.drift import PublicationLedger, compare

    _model, cases = _cases()
    blind = PublicationLedger(model_id="records-api")
    report = compare(cases, blind)
    detail = report.items[0].detail
    assert "UNKNOWN, not no" in detail, detail


def test_a_ledger_that_has_published_says_no_plainly():
    from metis_mcp.publishing.drift import PublicationLedger, compare

    _model, cases = _cases()
    seen = PublicationLedger(model_id="records-api", live_publications=3)
    detail = compare(cases, seen).items[0].detail
    assert "no published case for this path" in detail


def test_a_dry_run_records_no_published_id():
    """It learns none. Writing a fabricated one would put a fiction where the
    next comparison reads its evidence."""
    from metis_mcp.publishing.drift import PublicationLedger, record_publication

    ledger = PublicationLedger(model_id="records-api")
    ops = [Operation(action=CREATE, case_id="c1", published_id="", payload={})]
    assert record_publication(ledger, ops, ["ignored"], _cases()[1],
                              dry_run=True) == 0
    assert ledger.published == {} and ledger.live_publications == 0


def test_a_live_publication_is_recorded_so_the_next_run_can_see_it():
    """The half that was missing entirely: `published` had no writer at all, so
    MANUALLY_EDITED and OBSOLETE could never fire for any deployment."""
    from metis_mcp.publishing.drift import PublicationLedger, record_publication

    _model, cases = _cases()
    ledger = PublicationLedger(model_id="records-api")
    ops = [Operation(action=CREATE, case_id=cases[0].id, published_id="",
                     payload={})]
    assert record_publication(ledger, ops, ["DEMO-T5"], cases,
                              dry_run=False) == 1
    assert ledger.published[cases[0].id].published_id == "DEMO-T5"
    assert ledger.can_see_published_content is True


def test_the_recorded_ledger_survives_a_round_trip():
    """`live_publications` is optional on load, so older ledgers report zero
    honestly rather than failing to parse."""
    from metis_mcp.publishing.drift import PublicationLedger

    ledger = PublicationLedger(model_id="m", live_publications=2)
    assert PublicationLedger.from_json(ledger.to_json()).live_publications == 2
    assert PublicationLedger.from_json('{"model_id": "m"}').live_publications == 0
