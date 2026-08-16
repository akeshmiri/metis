"""
Roles and audit tests (application spec §9.6, §9.7; N-9..N-15, A-26, A-27).

Free to run: pure.
"""
import sys

from metis_mcp.review.roles import (
    ADMIN,
    ADMINISTER,
    APPROVE_MODEL,
    CAPABILITIES,
    CONFIRM_MATCH,
    CONFIRM_PUBLICATION,
    CONTRIBUTOR,
    DECIDE_DRIFT,
    NAME_STATE,
    PROPOSE,
    PUBLISHER,
    READ,
    RESOLVE_DIVERGENCE,
    REVIEWER,
    ROLES,
    VIEWER,
    AuditLog,
    Identity,
    NotPermitted,
    check_self_approval,
    format_audit,
    record_decision,
    require,
)

ALICE = Identity("alice", REVIEWER)
BOB = Identity("bob", CONTRIBUTOR)
PAT = Identity("pat", PUBLISHER)


# --------------------------------------------------------------------------
# N-9 : five roles
# --------------------------------------------------------------------------

def test_n9_every_role_is_defined():
    assert set(ROLES) == {VIEWER, CONTRIBUTOR, REVIEWER, PUBLISHER, ADMIN}
    assert all(r in CAPABILITIES for r in ROLES)


def test_a_viewer_reads_and_nothing_else():
    viewer = Identity("vic", VIEWER)
    assert viewer.can(READ)
    for capability in (PROPOSE, APPROVE_MODEL, CONFIRM_PUBLICATION, ADMINISTER):
        assert not viewer.can(capability)


def test_a_contributor_proposes_but_never_approves():
    assert BOB.can(PROPOSE)
    assert not BOB.can(APPROVE_MODEL)


def test_a_reviewer_holds_all_five_review_decisions():
    for capability in (APPROVE_MODEL, NAME_STATE, RESOLVE_DIVERGENCE,
                       CONFIRM_MATCH, DECIDE_DRIFT):
        assert ALICE.can(capability)


def test_n12_a_reviewer_may_not_publish():
    """Publication writes to a system outside Métis's control and is the least
    reversible action, so it is a separate capability."""
    assert not ALICE.can(CONFIRM_PUBLICATION)
    assert PAT.can(CONFIRM_PUBLICATION)


def test_a_publisher_also_holds_the_review_decisions():
    assert PAT.can(APPROVE_MODEL) and PAT.can(DECIDE_DRIFT)


def test_only_an_admin_administers():
    assert Identity("root", ADMIN).can(ADMINISTER)
    assert not PAT.can(ADMINISTER)


def test_require_names_who_may_do_it_instead_of_only_refusing():
    try:
        require(BOB, CONFIRM_PUBLICATION)
    except NotPermitted as e:
        assert "bob is a contributor" in str(e)
        assert PUBLISHER in str(e) and ADMIN in str(e)
        return
    raise AssertionError("a contributor must not publish")


def test_an_identity_requires_a_name_and_a_known_role():
    for bad in (("", REVIEWER), ("  ", REVIEWER), ("alice", "wizard")):
        try:
            Identity(*bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad} must be refused")


# --------------------------------------------------------------------------
# N-10 / N-11 / A-27 : proposal separated from approval
# --------------------------------------------------------------------------

def test_n10_the_proposer_may_not_approve_their_own_element():
    outcome = check_self_approval(ALICE, proposed_by="alice")
    assert not outcome.permitted
    assert outcome.is_self_approval
    assert "may not approve it" in outcome.reason


def test_n10_a_different_reviewer_may_approve():
    outcome = check_self_approval(ALICE, proposed_by="bob")
    assert outcome.permitted and not outcome.is_self_approval


def test_an_element_with_no_recorded_proposer_is_not_a_self_approval():
    assert not check_self_approval(ALICE, proposed_by=None).is_self_approval
    assert not check_self_approval(ALICE, proposed_by="").is_self_approval


def test_n11_the_override_permits_but_still_flags():
    """The flag must survive the permission — A-27 needs a permitted
    self-approval to still be recorded as one."""
    outcome = check_self_approval(ALICE, proposed_by="alice", allow_self_approval=True)
    assert outcome.permitted
    assert outcome.is_self_approval, "permitting it must not erase the fact"
    assert "visible in the audit view" in outcome.reason


def test_a27_a_permitted_self_approval_appears_in_the_audit_view():
    log = AuditLog()
    outcome = check_self_approval(ALICE, proposed_by="alice", allow_self_approval=True)
    record_decision(log, ALICE, APPROVE_MODEL, "t06", "Approved",
                    evidence={"guard": "x >= 5"}, self_approval=outcome.is_self_approval)
    record_decision(log, ALICE, APPROVE_MODEL, "t07", "Approved", evidence={})

    assert len(log.self_approvals()) == 1
    assert log.self_approvals()[0].element_id == "t06"
    text = format_audit(log)
    assert "[SELF-APPROVED]" in text
    assert "visible, not silent" in text


# --------------------------------------------------------------------------
# N-13 / N-14 / A-26 : the record carries the evidence presented
# --------------------------------------------------------------------------

def test_a26_a_decision_records_who_when_what_and_the_evidence():
    log = AuditLog()
    decision = record_decision(
        log, ALICE, APPROVE_MODEL, "t06", "Approved",
        evidence={"guard": "NOT credentials_valid", "from": "Failed4"},
        evidence_fingerprint="5e1a08680516c496", rationale="matches AC-2")

    assert decision.actor == "alice" and decision.role == REVIEWER
    assert decision.capability == APPROVE_MODEL
    assert decision.element_id == "t06" and decision.outcome == "Approved"
    assert decision.at, "when"
    assert decision.evidence["guard"] == "NOT credentials_valid"
    assert decision.evidence_fingerprint == "5e1a08680516c496"
    assert decision.rationale == "matches AC-2"


def test_n14_the_evidence_is_stored_not_referenced():
    """A reference would resolve to current state and quietly rewrite history."""
    log = AuditLog()
    evidence = {"guard": "x >= 3"}
    record_decision(log, ALICE, APPROVE_MODEL, "t06", "Approved", evidence=evidence)
    evidence["guard"] = "x >= 5"          # the model moves afterwards
    assert log.entries[0].evidence["guard"] == "x >= 3", (
        "the record must show what the reviewer actually saw"
    )


def test_n15_the_audit_is_append_only():
    log = AuditLog()
    record_decision(log, ALICE, APPROVE_MODEL, "t06", "Approved", evidence={})
    record_decision(log, ALICE, APPROVE_MODEL, "t06", "Rejected", evidence={},
                    rationale="superseded on review")
    history = log.for_element("t06")
    assert len(history) == 2, "a decision is superseded, never edited away"
    assert [d.outcome for d in history] == ["Approved", "Rejected"]


def test_n1_every_surface_produces_the_same_record():
    """The surface is recorded, but it grants nothing and changes nothing."""
    log = AuditLog()
    cli = record_decision(log, ALICE, APPROVE_MODEL, "t06", "Approved",
                          evidence={"g": "x"}, surface="cli")
    web = record_decision(log, ALICE, APPROVE_MODEL, "t07", "Approved",
                          evidence={"g": "x"}, surface="web")
    assert cli.surface == "cli" and web.surface == "web"
    for field in ("actor", "role", "capability", "outcome", "evidence"):
        assert getattr(cli, field) == getattr(web, field)


def test_decisions_are_retrievable_by_actor_and_by_element():
    log = AuditLog()
    record_decision(log, ALICE, APPROVE_MODEL, "t06", "Approved", evidence={})
    record_decision(log, PAT, CONFIRM_PUBLICATION, "batch-1", "Sent", evidence={})
    assert len(log.by("alice")) == 1
    assert len(log.by("pat")) == 1
    assert log.for_element("batch-1")[0].capability == CONFIRM_PUBLICATION


def test_n12_approval_and_publication_are_separately_logged():
    """Even where one person holds both roles, the actions stay distinguishable."""
    log = AuditLog()
    both = Identity("sam", ADMIN)
    record_decision(log, both, APPROVE_MODEL, "t06", "Approved", evidence={})
    record_decision(log, both, CONFIRM_PUBLICATION, "batch-1", "Sent", evidence={})
    capabilities = [d.capability for d in log.by("sam")]
    assert capabilities == [APPROVE_MODEL, CONFIRM_PUBLICATION]


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
