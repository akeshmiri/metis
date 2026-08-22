"""
Model manipulation tests (application spec §17; A-52..A-58).

Free to run: overrides are pure and file-based.
"""
import sys
import tempfile
from pathlib import Path

from metis_mcp.mbt.model import APPROVED, IMPLEMENTED, PLANNED, QUARANTINE, Transition
from metis_mcp.overrides import (
    ADD,
    EXTRACTION_ERROR,
    INTENDED_DIVERGENCE,
    MODIFY,
    REMOVE,
    STATE,
    TARGET_METIS,
    TARGET_PRODUCT,
    TRANSITION,
    OverrideLog,
    OverrideRefused,
    apply_overrides,
    check_staleness,
    default_log_path,
    density,
    findings,
    format_overrides,
    plan_override,
)
from mbt_fixtures import login_model


def _log(model, *edits) -> OverrideLog:
    log = OverrideLog(model_id=model.id)
    for kwargs in edits:
        log.append(plan_override(model, **kwargs))
    return log


def _guard_edit(**over):
    base = dict(kind=TRANSITION, element_id="t06", operation=MODIFY, author="bob",
                rationale="AC says 5", classification=INTENDED_DIVERGENCE,
                prop="guard", new_value="NOT credentials_valid AND attempts >= 5")
    base.update(over)
    return base


# --------------------------------------------------------------------------
# A-52 : every override records the full E-2 record
# --------------------------------------------------------------------------

def test_a52_an_override_records_every_required_fact():
    model = login_model()
    o = plan_override(model, **_guard_edit())
    assert o.element_id == "t06" and o.prop == "guard"
    assert o.previous_value == "NOT credentials_valid"        # read from the model
    assert o.new_value == "NOT credentials_valid AND attempts >= 5"
    assert o.author == "bob" and o.rationale == "AC says 5"
    assert o.classification == INTENDED_DIVERGENCE
    assert o.recorded_at, "an override records when it was made"


def test_rationale_is_required_not_optional():
    model = login_model()
    for bad in ("", "   "):
        try:
            plan_override(model, **_guard_edit(rationale=bad))
        except OverrideRefused as e:
            assert "rationale" in str(e)
            continue
        raise AssertionError("an unexplained edit must be refused (E-2)")


def test_an_unclassified_edit_is_refused():
    """E-5: without the class, 'extraction is unreliable' and 'we found a defect'
    become the same record and neither can be measured."""
    model = login_model()
    try:
        plan_override(model, **_guard_edit(classification="because"))
    except OverrideRefused as e:
        assert "extraction_error" in str(e) and "intended_divergence" in str(e)
        return
    raise AssertionError("classification must be required")


def test_previous_value_comes_from_the_model_not_the_caller():
    """An override must not be able to claim evidence that was never on screen."""
    model = login_model()
    o = plan_override(model, **_guard_edit())
    assert o.previous_value == model.transitions["t06"].guard


def test_an_edit_that_changes_nothing_is_refused():
    model = login_model()
    try:
        plan_override(model, **_guard_edit(new_value=model.transitions["t06"].guard))
    except OverrideRefused as e:
        assert "already" in str(e)
        return
    raise AssertionError("a no-change edit would quarantine an element for nothing")


def test_a_property_that_does_not_exist_is_refused():
    model = login_model()
    try:
        plan_override(model, **_guard_edit(prop="colour"))
    except OverrideRefused as e:
        assert "editable property" in str(e)
        return
    raise AssertionError("silently accepting it would write an override that can never apply")


# --------------------------------------------------------------------------
# A-53 : the two classes produce findings against different targets
# --------------------------------------------------------------------------

def test_a53_the_two_classes_point_at_different_targets():
    model = login_model()
    log = _log(model,
               _guard_edit(),                                            # product
               _guard_edit(element_id="t12", prop="guard", new_value="email_verified",
                           classification=EXTRACTION_ERROR,
                           rationale="the extractor read the wrong branch"))
    by_target = {f.element_id: f.target for f in findings(log)}
    assert by_target["t06"] == TARGET_PRODUCT
    assert by_target["t12"] == TARGET_METIS


def test_removal_as_intended_divergence_is_a_defect_finding():
    """E-6's most valuable case: the system does this and it should not."""
    model = login_model()
    log = _log(model, dict(kind=TRANSITION, element_id="t10", operation=REMOVE,
                           author="bob", rationale="valid login must not succeed from Failed4",
                           classification=INTENDED_DIVERGENCE))
    finding = findings(log)[0]
    assert finding.target == TARGET_PRODUCT
    assert finding.meaning == "the code does something it should not — a defect"


def test_removal_as_extraction_error_is_a_metis_finding():
    model = login_model()
    log = _log(model, dict(kind=TRANSITION, element_id="t10", operation=REMOVE,
                           author="bob", rationale="not real; unsound data flow",
                           classification=EXTRACTION_ERROR))
    finding = findings(log)[0]
    assert finding.target == TARGET_METIS
    assert "false positive" in finding.meaning


def test_the_two_finding_lists_are_never_merged():
    model = login_model()
    log = _log(model, _guard_edit(),
               _guard_edit(element_id="t12", prop="guard", new_value="email_verified",
                           classification=EXTRACTION_ERROR, rationale="misread"))
    text = format_overrides(apply_overrides(login_model(), log), log)
    assert "AGAINST MÉTIS" in text and "AGAINST THE PRODUCT" in text
    assert "NOT one number" in text


# --------------------------------------------------------------------------
# A-54 / A-55 : survival and staleness
# --------------------------------------------------------------------------

def test_a54_an_override_survives_re_extraction():
    """E-7: re-extraction replaces machine facts underneath; the override applies."""
    model = login_model()
    log = _log(model, _guard_edit())

    fresh = login_model()                       # a fresh extraction, unedited
    result = apply_overrides(fresh, log)
    assert result.model.transitions["t06"].guard == "NOT credentials_valid AND attempts >= 5"
    assert len(result.applied) == 1


def test_a55_a_moved_underlying_value_flags_stale():
    model = login_model()
    log = _log(model, _guard_edit())

    reextracted = login_model()
    old = reextracted.transitions["t06"]
    reextracted.transitions["t06"] = Transition(
        id=old.id, source=old.source, trigger=old.trigger, target=old.target,
        guard="NOT credentials_valid AND attempts >= 4", lifecycle_state=old.lifecycle_state)
    reextracted.reindex()

    stale = check_staleness(reextracted, log)
    assert len(stale) == 1
    assert stale[0].was_extracted == "NOT credentials_valid"
    assert stale[0].now_extracted == "NOT credentials_valid AND attempts >= 4"
    assert not stale[0].code_now_agrees


def test_a55_a_stale_override_is_still_applied():
    """E-7 and E-8 both hold: it continues to apply AND is flagged."""
    model = login_model()
    log = _log(model, _guard_edit())

    reextracted = login_model()
    old = reextracted.transitions["t06"]
    reextracted.transitions["t06"] = Transition(
        id=old.id, source=old.source, trigger=old.trigger, target=old.target,
        guard="NOT credentials_valid AND attempts >= 4")
    reextracted.reindex()

    result = apply_overrides(reextracted, log)
    assert result.model.transitions["t06"].guard == "NOT credentials_valid AND attempts >= 5"
    assert len(result.stale) == 1
    assert any("flagged stale" in n for n in result.notes)


def test_a55_code_catching_up_is_reported_never_auto_resolved():
    """E-9 is explicit that even agreement does not close the divergence."""
    model = login_model()
    log = _log(model, _guard_edit())

    caught_up = login_model()
    old = caught_up.transitions["t06"]
    caught_up.transitions["t06"] = Transition(
        id=old.id, source=old.source, trigger=old.trigger, target=old.target,
        guard="NOT credentials_valid AND attempts >= 5")
    caught_up.reindex()

    stale = check_staleness(caught_up, log)
    assert len(stale) == 1, "still stale — the evidence moved"
    assert stale[0].code_now_agrees
    assert "code now agrees with you" in stale[0].describe()

    result = apply_overrides(caught_up, log)
    assert len(result.applied) == 1, "not dropped as resolved; a person confirms that"


def test_an_unchanged_underlying_value_is_not_stale():
    model = login_model()
    log = _log(model, _guard_edit())
    assert check_staleness(login_model(), log) == []


# --------------------------------------------------------------------------
# A-56 : an edit is a proposal, and cannot be approved by its own author
# --------------------------------------------------------------------------

def test_a56_an_edit_returns_the_element_to_quarantine():
    model = login_model(approved=True)
    assert model.transitions["t06"].lifecycle_state == APPROVED
    log = _log(model, _guard_edit())
    result = apply_overrides(login_model(approved=True), log)
    assert result.model.transitions["t06"].lifecycle_state == QUARANTINE
    assert "t06" in result.quarantined


def test_a56_the_editors_identity_is_carried_for_the_n10_gate():
    """The N-10 machinery already exists in review/decisions.py; the override log
    is what finally populates `proposed_by` in the real flow."""
    model = login_model()
    log = _log(model, _guard_edit())
    result = apply_overrides(login_model(), log)
    assert result.authors["t06"] == "bob"


def test_a56_self_approval_of_an_edit_is_refused_end_to_end():
    from metis_mcp.review.decisions import APPROVE, apply, export

    model = login_model(approved=True)
    log = _log(model, _guard_edit())
    result = apply_overrides(login_model(approved=True), log)

    review = export(result.model, authors=result.authors)
    item = next(i for i in review.items if i.id == "t06")
    assert item.proposed_by == "bob"

    item.decision = APPROVE
    item.rationale = "looks right to me"
    review.reviewer = "bob"
    applied = apply(result.model, review)

    refused = dict(applied.refused)
    assert "t06" in refused and "may not approve" in refused["t06"], applied.refused
    assert result.model.transitions["t06"].lifecycle_state == QUARANTINE
    assert not any(r.element_id == "t06" for r in applied.applied)


# --------------------------------------------------------------------------
# A-57 : group revalidation
# --------------------------------------------------------------------------

def test_a57_editing_a_group_member_revalidates_the_group():
    """t02 and a new sibling share (LoggedOut, submit_invalid_credentials)."""
    model = login_model(approved=True)
    log = _log(model, dict(
        kind=TRANSITION, element_id="t02x", operation=ADD, author="bob",
        rationale="the extractor missed the ip-blocklist branch",
        classification=EXTRACTION_ERROR,
        payload={"source": "LoggedOut", "trigger": "submit_invalid_credentials",
                 "target": "AccountLocked", "guard": "ip_blocklisted"}))

    result = apply_overrides(login_model(approved=True), log)
    assert ("LoggedOut", "submit_invalid_credentials") in result.revalidated_groups
    assert result.model.transitions["t02"].lifecycle_state == QUARANTINE, (
        "an edit can break a sibling's determinism exactly as an extraction can"
    )
    # An unrelated group is untouched.
    assert result.model.transitions["t11"].lifecycle_state == APPROVED


def test_a57_a_guard_edit_revalidates_its_own_group():
    model = login_model(approved=True)
    log = _log(model, _guard_edit())
    result = apply_overrides(login_model(approved=True), log)
    assert ("Failed4", "submit_invalid_credentials") in result.revalidated_groups


# --------------------------------------------------------------------------
# A-58 : density
# --------------------------------------------------------------------------

def test_a58_density_is_counted_over_elements_not_overrides():
    """Five refinements of one guard is one overridden element, not five."""
    model = login_model()
    log = OverrideLog(model_id=model.id)
    working = login_model()
    for value in ("attempts >= 2", "attempts >= 3", "attempts >= 5"):
        o = plan_override(working, **_guard_edit(new_value=value))
        log.append(o)
        working.transitions["t06"] = Transition(
            id="t06", source="Failed4", trigger="submit_invalid_credentials",
            target="AccountLocked", guard=value)
        working.reindex()

    d = density(login_model(), log)
    assert d.overridden == 1, "three edits to one transition is one overridden element"
    assert d.total == 27
    assert d.by_classification[INTENDED_DIVERGENCE] == 1


def test_a58_density_carries_its_caveat():
    model = login_model()
    log = _log(model, _guard_edit())
    d = density(login_model(), log)
    assert "weaker claim about the code" in d.caveat
    assert density(login_model(), OverrideLog()).caveat == ""


# --------------------------------------------------------------------------
# Identity, ordering, persistence
# --------------------------------------------------------------------------

def test_changing_target_is_disclosed_as_an_identity_move():
    model = login_model()
    log = _log(model, dict(kind=TRANSITION, element_id="t06", operation=MODIFY,
                           author="bob", rationale="lockout should land logged out",
                           classification=INTENDED_DIVERGENCE,
                           prop="target", new_value="LoggedOut"))
    result = apply_overrides(login_model(), log)
    assert result.model.transitions["t06"].target == "LoggedOut"
    assert any("natural key" in n for n in result.notes), (
        "moving an identity-bearing property must never be silent (I-2)"
    )


def test_a_later_override_supersedes_an_earlier_one():
    """The log is append-only (N-15), so supersession is order, not editing."""
    source = login_model()
    log = OverrideLog(model_id=source.id)
    log.append(plan_override(source, **_guard_edit(new_value="attempts >= 3")))

    effective = apply_overrides(login_model(), log).model
    log.append(plan_override(effective, machine=source,
                             **_guard_edit(new_value="attempts >= 5")))

    result = apply_overrides(login_model(), log)
    assert result.model.transitions["t06"].guard == "attempts >= 5"
    assert len(log.entries) == 2, "the earlier entry is retained, not rewritten"


def test_a_superseding_edit_records_the_machine_value_not_the_earlier_edit():
    """The bug this guards against is real and was caught by running the CLI, not
    by these tests: if a second edit recorded the first edit's value as "previously
    extracted", every staleness check would compare an override against itself and
    report stale forever."""
    source = login_model()
    log = OverrideLog(model_id=source.id)
    log.append(plan_override(source, **_guard_edit(new_value="attempts >= 3")))
    effective = apply_overrides(login_model(), log).model
    second = plan_override(effective, machine=source, **_guard_edit(new_value="attempts >= 5"))

    assert second.previous_value == "NOT credentials_valid", (
        "previous_value is the machine value, never the prior override's"
    )
    log.append(second)
    assert check_staleness(login_model(), log) == [], (
        "nothing has moved in the source, so nothing is stale"
    )


def test_an_edit_matching_the_visible_value_is_refused_even_if_the_source_differs():
    """The no-change check reads what the reviewer is looking at, not the source."""
    source = login_model()
    log = OverrideLog(model_id=source.id)
    log.append(plan_override(source, **_guard_edit(new_value="attempts >= 3")))
    effective = apply_overrides(login_model(), log).model
    try:
        plan_override(effective, machine=source, **_guard_edit(new_value="attempts >= 3"))
    except OverrideRefused as e:
        assert "already" in str(e)
        return
    raise AssertionError("re-asserting the value already in force changes nothing visible")


def test_removing_an_element_the_source_dropped_is_a_no_op_not_an_error():
    model = login_model()
    log = _log(model, dict(kind=TRANSITION, element_id="t11", operation=REMOVE,
                           author="bob", rationale="not real", classification=EXTRACTION_ERROR))
    shrunk = login_model()
    del shrunk.transitions["t11"]
    shrunk.reindex()

    result = apply_overrides(shrunk, log)
    assert result.applied == []
    assert any("no-op" in n for n in result.no_ops)


def test_an_added_element_lands_at_quarantine():
    model = login_model(approved=True)
    log = _log(model, dict(
        kind=STATE, element_id="RateLimited", operation=ADD, author="bob",
        rationale="the extractor missed the 429 outcome", classification=EXTRACTION_ERROR,
        payload={"name": "RateLimited", "surface": "api"}))
    result = apply_overrides(login_model(approved=True), log)
    assert result.model.states["RateLimited"].lifecycle_state == QUARANTINE


def test_the_log_round_trips_through_a_file():
    model = login_model()
    log = _log(model, _guard_edit())
    with tempfile.TemporaryDirectory() as d:
        path = default_log_path(Path(d) / "login-api.json")
        assert path.name == "login-api.overrides.json"
        log.save(path)
        again = OverrideLog.load(path)
    assert len(again.entries) == 1
    assert again.entries[0].rationale == "AC says 5"
    assert again.entries[0].previous_value == "NOT credentials_valid"


def test_the_source_model_is_never_mutated_by_planning():
    """E-1: an override is layered on an element, never a mutation of it."""
    model = login_model()
    before = model.transitions["t06"].guard
    plan_override(model, **_guard_edit())
    assert model.transitions["t06"].guard == before


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


def test_landing_applies_the_override_log():
    """§17 makes a human edit a layered fact, and `load_model` applies the log
    for every file-based command — but `land` read the raw source and dropped
    them.

    The failure was silent and complete: a guard recorded with `override edit`
    validated clean on the file, `land` reported "Landed 22 nodes", and the
    graph got the transition with an empty guard. M-18 then blocked generation
    for a defect that had already been corrected.
    """
    import pathlib
    import re

    from metis_mcp.mbt import cli

    source = pathlib.Path(cli.__file__).read_text()
    block = source[source.index("def cmd_land("):]
    block = block[:block.index("\ndef ")]
    assert "OverrideLog.load" in block, (
        "cmd_land does not read the override log — human edits will not reach "
        "the graph"
    )
    assert "apply_overrides" in block, (
        "cmd_land reads the log but never applies it"
    )
    # And it says so, rather than applying edits invisibly.
    assert re.search(r"applied .*override", block)
