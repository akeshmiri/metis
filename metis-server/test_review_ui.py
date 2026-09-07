"""
Review-UI tests (application spec §9.1, §9.3; N-2, N-3, N-4, N-5).

Free to run: evidence assembly and rendering are pure.
"""
import sys

import pytest

from metis_mcp.mbt.coverage import DIRECT, INDIRECT, Ledger, LedgerRow, build_ledger
from metis_mcp.mbt.criteria import ALL_TRANSITIONS, DEFAULT_CRITERION
from metis_mcp.mbt.model import APPROVED, DISPUTED, PLANNED, QUARANTINE, Model, State, Transition
from metis_mcp.mbt.path_generation import generate
from metis_mcp.mbt.validation import validate
from metis_mcp.reconciliation import AcceptanceCriterion, prefilter, reconcile
from metis_mcp.review.roles import (
    APPROVE_MODEL, CONFIRM_PUBLICATION, CONTRIBUTOR, PUBLISHER, REVIEWER, Identity,
)
from metis_mcp.review_ui import (
    COVERED_DIRECT,
    COVERED_INDIRECT,
    EXCLUDED,
    REQUIRED_EVIDENCE,
    UNCOVERED,
    EvidenceMissing,
    approve_model_screen,
    batch,
    build_layout,
    confirm_match_screen,
    confirm_publication_screen,
    decide_drift_screen,
    format_screen,
    layered_layout,
    name_state_screen,
    permitted,
    render_html,
    render_svg,
    resolve_divergence_screen,
)
from mbt_fixtures import login_model


def _ledger(model):
    result = generate(model, DEFAULT_CRITERION, 10)
    return build_ledger(model, result)


# --------------------------------------------------------------------------
# N-4 : a screen that cannot show its evidence BLOCKS the decision
# --------------------------------------------------------------------------

def test_n4_a_screen_without_its_evidence_blocks():
    model = login_model()
    screen = approve_model_screen(model)            # no validation, no reconciliation
    assert not screen.can_decide
    assert "validation_findings" in screen.missing
    assert "reconciliation_gaps" in screen.missing
    assert "blocks the decision" in screen.blocked_reason


def test_n4_a_blocked_screen_refuses_rather_than_degrades():
    screen = approve_model_screen(login_model())
    try:
        screen.require()
    except EvidenceMissing as e:
        assert "approving without evidence is the failure" in str(e)
        return
    raise AssertionError("N-4: it must refuse, not present a partial view")


def test_n4_a_complete_screen_permits_the_decision():
    model = login_model()
    screen = approve_model_screen(
        model, validation=validate(model),
        reconciliation=reconcile(model, [], []),
        element_sources={t: "hand_authored" for t in model.transitions})
    assert screen.can_decide, screen.missing
    screen.require()


def test_present_but_empty_is_not_missing():
    """"No validation findings" and "findings not computed" are different facts;
    conflating them would block a clean model."""
    model = login_model()
    validation = validate(model)
    assert validation.blocking == []
    screen = approve_model_screen(model, validation=validation,
                                  reconciliation=reconcile(model, [], []),
                                  element_sources={})
    assert screen.can_decide
    assert screen.evidence["element_sources"] == {}


def test_every_decision_declares_its_required_evidence():
    from metis_mcp.review_ui import DECISIONS
    assert set(REQUIRED_EVIDENCE) == set(DECISIONS)
    assert all(REQUIRED_EVIDENCE[d] for d in DECISIONS)


# --------------------------------------------------------------------------
# N-3 : per-decision evidence, from the real modules
# --------------------------------------------------------------------------

def test_approve_shows_both_reconciliation_directions_never_one_number():
    model = login_model()
    criteria = [AcceptanceCriterion("ac-1", "unrelated pagination requirement")]
    screen = approve_model_screen(model, validation=validate(model),
                                  reconciliation=reconcile(model, criteria, []),
                                  element_sources={})
    gaps = screen.evidence["reconciliation_gaps"]
    assert "unspecified_behaviour" in gaps and "unimplemented_or_unmodelled" in gaps
    assert "never one number" in gaps["note"]


def test_approve_lists_every_unnamed_state_and_never_blocks_on_it():
    model = login_model()
    model.states["Failed1"] = State(id="Failed1", name="Failed1", surface="api")
    model.reindex()
    screen = approve_model_screen(model, validation=validate(model),
                                  reconciliation=reconcile(model, [], []),
                                  element_sources={})
    assert "Failed1" in screen.evidence["unnamed_states"]
    assert screen.can_decide, "computable from the model, so never a reason to block"


def test_approve_warns_when_the_model_is_not_well_formed():
    model = login_model()
    model.transitions["tX"] = Transition(
        id="tX", source="LoggedOut", trigger="submit_invalid_credentials",
        target="AccountLocked", guard="attempts >= 1", lifecycle_state=APPROVED)
    model.transitions["t02"] = Transition(
        id="t02", source="LoggedOut", trigger="submit_invalid_credentials",
        target="Failed1", guard="attempts >= 0", lifecycle_state=APPROVED)
    model.reindex()
    screen = approve_model_screen(model, validation=validate(model),
                                  reconciliation=reconcile(model, [], []),
                                  element_sources={})
    assert any("M-18" in n for n in screen.notes)
    assert any("will not" in n for n in screen.notes)


def test_naming_a_state_carries_x11s_circularity_warning():
    """X-11: naming from the AC vocabulary is NOT evidence the models agree."""
    screen = name_state_screen(login_model(), "Failed1",
                               ac_candidates=["First failed attempt"],
                               code_candidates=["FAILED_1"])
    assert screen.can_decide
    assert any("NOT evidence" in n for n in screen.notes)
    assert screen.evidence["ac_candidates"] == ["First failed attempt"]
    assert "LoggedOut" in screen.evidence["sibling_names"]


def test_naming_an_unknown_state_blocks():
    screen = name_state_screen(login_model(), "NoSuchState")
    assert not screen.can_decide


def test_divergence_shows_both_sides_and_recommends_neither():
    """S-10: a precedence rule would silently decide which of a defect and a
    stale requirement is right."""
    screen = resolve_divergence_screen(
        "t06",
        code_side={"guard": "attempts >= 3", "anchor": "AuthController.java:88@a3f21c"},
        ac_side={"guard": "attempts >= 5", "source": "PROJ-1421 AC-2"},
        blocked_paths=["path-7", "path-9"])
    assert screen.can_decide
    implications = screen.evidence["implications"]
    assert "accept_code" in implications and "accept_ac" in implications
    assert "neither side wins automatically" in implications["note"]
    assert "recommended" not in str(screen.evidence).lower()


def test_divergence_without_both_sides_blocks():
    screen = resolve_divergence_screen("t06", code_side={"guard": "x"},
                                       ac_side=None, blocked_paths=[])
    assert not screen.can_decide and "ac_side" in screen.missing


def test_confirm_match_shows_why_it_was_proposed():
    """X-17: a reviewer must see that a match rests on a route and a status
    rather than on wording similarity."""
    model = login_model()
    ac = AcceptanceCriterion("ac-1", "submit valid credentials to become logged in")
    proposal = prefilter(ac, model, {})
    top = proposal.candidates[0].transition_id
    screen = confirm_match_screen(model, "ac-1", ac.text, top, proposal=proposal,
                                  code_anchor="AuthController.java:44@a3f21c")
    assert screen.can_decide
    assert screen.evidence["why_proposed"]["evidence"]
    assert screen.evidence["transition_tuple"]["trigger"]


def test_confirm_match_flags_an_ambiguous_proposal():
    model = login_model()
    ac = AcceptanceCriterion("ac-1", "submit valid credentials")
    proposal = prefilter(ac, model, {})
    screen = confirm_match_screen(model, "ac-1", ac.text,
                                  proposal.candidates[0].transition_id,
                                  proposal=proposal, code_anchor="x:1@c")
    if proposal.is_ambiguous:
        assert any("a human decides" in n for n in screen.notes)


def test_drift_screen_says_a_hand_edited_case_is_never_overwritten():
    from metis_mcp.publishing import DriftItem, MANUALLY_EDITED, PROPOSE_NOTHING
    item = DriftItem(case_id="tc-1", drift_class=MANUALLY_EDITED,
                     action=PROPOSE_NOTHING, detail="edited by hand")
    screen = decide_drift_screen(item, published_content="a", last_generated="b",
                                 newly_generated="c")
    assert screen.can_decide
    assert any("never overwrite" in n for n in screen.notes)
    assert set(screen.evidence["three_way_comparison"]) == {
        "last_generated", "currently_published", "newly_generated"}


# --------------------------------------------------------------------------
# N-5 : batch decisions, without batch blindness
# --------------------------------------------------------------------------

def test_n5_a_publication_screen_enumerates_every_operation():
    from metis_mcp.publishing import PublicationLedger, compare, plan_publication
    from metis_mcp.rendering import render
    model = login_model()
    cases = render(model, generate(model, DEFAULT_CRITERION, 10).paths).cases
    b = plan_publication(compare(cases, PublicationLedger(model_id="login-api")), cases)

    screen = confirm_publication_screen(b, dry_run_payload=[{"id": c.id} for c in cases])
    assert screen.can_decide
    assert len(screen.evidence["draft_content"]) == b.size
    assert any("every one is listed above" in n for n in screen.notes)


def test_n5_a_batch_is_enumerable_and_one_blocked_member_blocks_it():
    model = login_model()
    good = approve_model_screen(model, validation=validate(model),
                                reconciliation=reconcile(model, [], []),
                                element_sources={})
    bad = approve_model_screen(model)          # missing evidence
    group = batch(APPROVE_MODEL, [good, bad])
    assert group.enumerated == [model.id, model.id]
    assert not group.can_decide
    assert len(group.blocked) == 1


def test_n5_an_all_good_batch_can_be_decided():
    model = login_model()
    screens = [approve_model_screen(model, validation=validate(model),
                                    reconciliation=reconcile(model, [], []),
                                    element_sources={}) for _ in range(3)]
    assert batch(APPROVE_MODEL, screens).can_decide


def test_an_empty_batch_is_not_decidable():
    assert not batch(APPROVE_MODEL, []).can_decide


def test_withheld_cases_are_named_on_the_publication_screen():
    from metis_mcp.publishing import Batch
    b = Batch(model_id="m", operations=[],
              withheld=[("tc-1", "hand-edited")])
    screen = confirm_publication_screen(b)
    assert any("WITHHELD" in n for n in screen.notes)
    assert any("only what is shown" in n for n in screen.notes)


# --------------------------------------------------------------------------
# N-9 : the surface never grants a capability
# --------------------------------------------------------------------------

def test_the_ui_checks_capability_rather_than_assuming_it():
    assert permitted(Identity("alice", REVIEWER), APPROVE_MODEL)
    assert not permitted(Identity("bob", CONTRIBUTOR), APPROVE_MODEL)
    assert permitted(Identity("pat", PUBLISHER), CONFIRM_PUBLICATION)
    assert not permitted(Identity("alice", REVIEWER), CONFIRM_PUBLICATION)


# --------------------------------------------------------------------------
# N-2 : the model view
# --------------------------------------------------------------------------

def test_n2_layout_places_the_initial_state_first():
    layout = layered_layout(login_model())
    initial = next(n for n in layout.nodes if n.is_initial)
    assert initial.column == 0
    assert initial.id == "LoggedOut"


def test_n2_layout_is_deterministic():
    """A diagram that moves between runs cannot be what an approval was audited
    against (P-7's discipline, N-14)."""
    a = layered_layout(login_model())
    b = layered_layout(login_model())
    assert [(n.id, n.column, n.row) for n in a.nodes] == [
        (n.id, n.column, n.row) for n in b.nodes]
    assert render_svg(a) == render_svg(b)


def test_n2_the_failure_chain_is_laid_out_in_order():
    layout = layered_layout(login_model())
    column = {n.id: n.column for n in layout.nodes}
    assert column["Failed1"] < column["Failed2"] < column["Failed3"] < column["Failed4"]
    assert column["Failed4"] < column["AccountLocked"]


def test_n2_an_unreachable_state_is_shown_not_hidden():
    model = login_model()
    model.states["Orphan"] = State(id="Orphan", name="Orphan", surface="api")
    model.reindex()
    layout = layered_layout(model)
    assert "Orphan" in layout.unplaced
    assert any(n.id == "Orphan" for n in layout.nodes), "shown, never hidden"
    assert "Orphan" in render_html(model, build_layout(model))


def test_n2_the_coverage_overlay_distinguishes_all_four_states():
    model = login_model()
    layout = build_layout(model, _ledger(model))
    by_id = {e.id: e for e in layout.edges}
    assert by_id["t01"].coverage == COVERED_DIRECT
    assert by_id["t17"].coverage == EXCLUDED, "planned"
    assert "not built yet" in by_id["t17"].note


def test_n2_an_indirectly_covered_transition_is_marked_as_such():
    """C-8: never presented as equivalently tested."""
    model = login_model()
    ledger = Ledger(model_id=model.id, criterion=ALL_TRANSITIONS)
    ledger.rows.append(LedgerRow(transition_id="t01", surface="api",
                                 mechanism=INDIRECT, criterion=ALL_TRANSITIONS))
    layout = build_layout(model, ledger)
    edge = next(e for e in layout.edges if e.id == "t01")
    assert edge.coverage == COVERED_INDIRECT
    assert "never exercised" in edge.note


def test_n2_an_uncovered_transition_carries_its_reason():
    model = login_model()
    ledger = Ledger(model_id=model.id, criterion=ALL_TRANSITIONS)
    ledger.uncovered.append(("t01", "budget exhausted"))
    edge = next(e for e in build_layout(model, ledger).edges if e.id == "t01")
    assert edge.coverage == UNCOVERED
    assert edge.note == "budget exhausted"


def test_the_html_is_self_contained():
    """No external stylesheet, script, font or image: a review artefact that
    renders differently depending on a CDN is not evidence of what was seen.

    Two things that look like external references and are not: the SVG XML
    namespace `http://www.w3.org/2000/svg`, which is an identifier and is never
    fetched, and `url(#arrow-d)`, which is an internal fragment reference.
    """
    import re
    model = login_model()
    page = render_html(model, build_layout(model, _ledger(model)))

    for forbidden in ("<script", "<link", "<img", "@import", "<iframe", "srcset"):
        assert forbidden not in page, forbidden

    # Every url(...) must be an internal fragment.
    for reference in re.findall(r"url\(([^)]*)\)", page):
        assert reference.startswith("#"), reference

    # The only absolute URL permitted is the SVG namespace declaration.
    for url in re.findall(r"https?://[^\s\"'<>]+", page):
        assert url == "http://www.w3.org/2000/svg", url

    assert page.startswith("<!doctype html>")


def test_the_table_carries_the_verbatim_guard():
    """T-5's discipline applies to a review screen at least as much as to a case."""
    model = login_model()
    page = render_html(model, build_layout(model, _ledger(model)))
    assert "credentials_valid AND NOT account_locked" in page
    assert "guard (verbatim)" in page


def test_the_view_carries_the_c11_caveat():
    model = login_model()
    page = render_html(model, build_layout(model, _ledger(model)))
    assert "not what is <strong>working</strong>" in page


def test_every_state_and_transition_appears_in_the_view():
    model = login_model()
    page = render_html(model, build_layout(model, _ledger(model)))
    for sid in model.states:
        assert sid in page
    for tid in model.transitions:
        assert tid in page


def test_the_svg_escapes_content_rather_than_trusting_it():
    model = Model(
        id="x",
        states={"A": State(id="A", name="<script>alert(1)</script>", surface="api",
                           is_initial=True)},
        transitions={})
    model.reindex()
    svg = render_svg(layered_layout(model))
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_format_screen_reports_a_block_rather_than_listing_partial_evidence():
    text = format_screen(approve_model_screen(login_model()))
    assert "BLOCKED" in text


# --------------------------------------------------------------------------
# The HTTP backend (§9.2). Exercised against a real socket on an ephemeral port.
# --------------------------------------------------------------------------

def _serve(commit=True):
    """Start the real server on a free port. Returns (base_url, context, stop).

    A `commit` is supplied by default because a context without one is now
    read-only: the server refuses to take a decision it cannot store (N-1). The
    committed records are collected on `context.committed` so a test can assert
    that an approval actually became durable rather than merely returning 200 --
    which is exactly what this surface used to do.
    """
    import threading
    from http.server import HTTPServer
    from metis_mcp.review.roles import AuditLog
    from metis_mcp.review_ui.server import ReviewContext, make_handler

    from metis_mcp.review.state import ReviewState

    model = login_model(approved=False)
    committed: list = []
    # §9.1's decisions 3, 4 and 5 accumulate in a review-state file rather than
    # in the model, so the context carries one and a `save_state` for the same
    # reason it carries `commit`: a decision this surface cannot keep is one it
    # must refuse rather than acknowledge with 200.
    review_state = ReviewState(model_id=model.id)
    saved: list = []
    context = ReviewContext(
        model=model, audit=AuditLog(), proposers={model.id: "bob"},
        commit=((lambda ctx, applied: committed.extend(applied)) if commit else None),
        review_state=(review_state if commit else None),
        save_state=((lambda s: saved.append(s)) if commit else None))
    context.committed = committed
    context.saved = saved
    server = HTTPServer(("127.0.0.1", 0), make_handler(context))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    def stop():
        server.shutdown()
        server.server_close()

    return f"http://127.0.0.1:{port}", context, stop


def _request(url, method="GET", body=None, headers=None):
    import json as _json
    import urllib.error
    import urllib.request
    data = _json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_the_server_renders_the_model_view():
    import json as _json
    base, context, stop = _serve()
    try:
        status, body = _request(f"{base}/model")
        assert status == 200
        assert "<!doctype html>" in body
        assert "LoggedOut" in body
    finally:
        stop()


def test_the_server_sets_a_content_security_policy_it_can_actually_meet():
    import urllib.request
    base, context, stop = _serve()
    try:
        with urllib.request.urlopen(f"{base}/model") as response:
            csp = response.headers.get("Content-Security-Policy")
        assert "default-src 'none'" in csp
    finally:
        stop()


def test_n13_a_decision_without_a_credential_is_refused():
    import json as _json
    base, context, stop = _serve()
    try:
        status, body = _request(f"{base}/api/decide/approve", "POST", {})
        assert status == 401
        assert "cannot take a decision" in _json.loads(body)["error"]
        assert context.audit.entries == []
    finally:
        stop()


def test_an_asserted_name_no_longer_buys_a_decision():
    """The hole this closed, stated as the test that would have caught it.

    Before `_identity` authenticated, these two headers WERE the identity: any
    caller could approve as anybody, and the audit record would name them. N-10,
    the role table and the evidence fingerprint were all defeated by typing.
    """
    import json as _json
    base, context, stop = _serve()
    try:
        status, body = _request(
            f"{base}/api/decide/approve", "POST", {"rationale": "mine now"},
            {"X-Metis-User": "alice", "X-Metis-Role": "reviewer",
             "Content-Type": "application/json"})
        assert status == 401, body
        assert "cannot take a decision" in _json.loads(body)["error"]
        assert context.audit.entries == [], (
            "a decision was recorded for somebody who presented no credential")
    finally:
        stop()


def test_a_header_that_contradicts_the_credential_is_refused_not_preferred():
    """`policy.authorise` refuses an `actor` that disagrees with the credential.

    The same rule here, and for the same reason: silently using the credential
    would record the decision under a name the caller did not expect to see in
    the audit trail, and silently using the header would be the hole itself.
    """
    import json as _json
    base, context, stop = _serve()
    try:
        headers = dict(_as("alice"))
        headers["X-Metis-User"] = "bob"
        status, body = _request(
            f"{base}/api/decide/approve", "POST", {"rationale": "r"}, headers)
        assert status == 401, body
        assert "credential decides who is acting" in _json.loads(body)["error"]
        assert context.audit.entries == []
    finally:
        stop()


def test_a_role_asserted_above_the_credential_is_refused():
    """Roles come from the store (N-1). A viewer may not promote themselves."""
    import json as _json
    base, context, stop = _serve()
    try:
        headers = dict(_as("dave"))            # a viewer
        headers["X-Metis-Role"] = "reviewer"
        status, body = _request(
            f"{base}/api/decide/approve", "POST", {"rationale": "r"}, headers)
        assert status == 401, body
        assert "Roles come from the" in _json.loads(body)["error"]
        assert context.audit.entries == []
    finally:
        stop()


def test_an_unknown_token_is_refused_and_says_nothing_useful():
    """The same message a malformed credential gets: telling an attacker which
    half of the guess was right is free help."""
    import json as _json
    base, context, stop = _serve()
    try:
        status, body = _request(
            f"{base}/api/decide/approve", "POST", {"rationale": "r"},
            {"Authorization": "Bearer not-a-real-token",
             "Content-Type": "application/json"})
        assert status == 401
        assert "not recognised" in _json.loads(body)["error"]
        assert context.audit.entries == []
    finally:
        stop()


def test_reading_is_unaffected_by_the_absence_of_a_credential(monkeypatch):
    """Reads are not decisions.

    Requiring a bearer token on page navigation would make the UI unusable in a
    browser, and a surface nobody can open is not a safer surface. With no store
    configured at all the model view still renders and only the decision is
    refused -- the same shape as the existing read-only refusal.
    """
    from metis_mcp.api import auth

    monkeypatch.delenv(auth.TOKENS_ENV, raising=False)
    base, context, stop = _serve()
    try:
        status, body = _request(f"{base}/model")
        assert status == 200
        assert "LoggedOut" in body

        status, _ = _request(f"{base}/api/decide/approve", "POST", {})
        assert status == 401
        assert context.audit.entries == []
    finally:
        stop()


def test_n9_a_contributor_may_not_approve_through_the_web_surface():
    import json as _json
    base, context, stop = _serve()
    try:
        status, body = _request(
            f"{base}/api/decide/approve", "POST", {},
            _as("carol"))
        assert status == 403
        assert "may not approve_model" in _json.loads(body)["error"]
        assert context.audit.entries == []
    finally:
        stop()


def test_n10_the_proposer_may_not_approve_through_the_web_surface_either():
    """N-1: no surface has a privileged path."""
    import json as _json
    base, context, stop = _serve()
    try:
        status, body = _request(
            f"{base}/api/decide/approve", "POST", {},
            _as("bob"))
        assert status == 403
        assert "may not approve it" in _json.loads(body)["error"]
        assert context.audit.entries == []
    finally:
        stop()


def test_a_distinct_reviewer_may_approve_and_the_record_carries_the_evidence():
    import json as _json
    base, context, stop = _serve()
    try:
        status, body = _request(
            f"{base}/api/decide/approve", "POST", {"rationale": "reviewed"},
            _as("alice"))
        assert status == 200, body
        assert _json.loads(body)["recorded"] is True

        assert len(context.audit.entries) == 1
        decision = context.audit.entries[0]
        assert decision.actor == "alice" and decision.surface == "web"
        assert decision.evidence["machine"], "N-14: the evidence presented is recorded"
        assert decision.rationale == "reviewed"
    finally:
        stop()


def test_n4_the_server_returns_409_rather_than_a_partial_screen():
    """A name-state screen for a state that is not in the model cannot show its
    evidence, so it blocks."""
    import json as _json
    base, context, stop = _serve()
    try:
        status, body = _request(
            f"{base}/api/decide/name-state", "POST",
            {"state_id": "NoSuchState", "name": "Whatever"},
            _as("alice"))
        assert status == 409
        assert "blocks the decision" in _json.loads(body)["error"]
        assert context.audit.entries == []
    finally:
        stop()


def test_a_placeholder_name_is_refused():
    import json as _json
    base, context, stop = _serve()
    try:
        status, body = _request(
            f"{base}/api/decide/name-state", "POST",
            {"state_id": "Failed1", "name": "   "},
            _as("alice"))
        assert status == 400
        assert "never persists" in _json.loads(body)["error"]
    finally:
        stop()


def test_naming_a_state_records_x11s_warning_with_the_decision():
    import json as _json
    base, context, stop = _serve()
    try:
        status, body = _request(
            f"{base}/api/decide/name-state", "POST",
            {"state_id": "Failed1", "name": "First failed attempt"},
            _as("alice"))
        assert status == 200, body
        assert "not evidence" in _json.loads(body)["note"]
        assert context.audit.entries[0].outcome == "First failed attempt"
    finally:
        stop()


def test_the_screen_endpoint_returns_409_when_evidence_is_missing():
    import json as _json
    base, context, stop = _serve()
    try:
        status, body = _request(f"{base}/api/screen/name-state?state=NoSuchState")
        assert status == 409
        assert _json.loads(body)["can_decide"] is False
    finally:
        stop()


def test_the_audit_endpoint_exposes_every_decision():
    import json as _json
    base, context, stop = _serve()
    try:
        _request(f"{base}/api/decide/approve", "POST", {"rationale": "ok"},
                 _as("alice"))
        status, body = _request(f"{base}/api/audit")
        assert status == 200
        payload = _json.loads(body)
        assert len(payload["entries"]) == 1
        assert payload["entries"][0]["actor"] == "alice"
    finally:
        stop()


def test_the_validation_endpoint_reports_the_verdict():
    import json as _json
    base, context, stop = _serve()
    try:
        status, body = _request(f"{base}/api/validation")
        assert status == 200
        assert _json.loads(body)["verdict"] == "well-formed"
    finally:
        stop()


def test_an_unknown_route_is_404_not_a_silent_200():
    base, context, stop = _serve()
    try:
        assert _request(f"{base}/api/nope")[0] == 404
    finally:
        stop()


# --------------------------------------------------------------------------
# N-1: a decision taken here must become durable, and must go through the same
# `decisions.apply` the CLI uses. Before this, `_approve` recorded to an
# in-memory AuditLog that `cmd_ui` threw away and mutated nothing at all.
# --------------------------------------------------------------------------

def test_a_context_that_cannot_store_a_decision_refuses_to_take_one():
    """N-4 applied to durability: returning 200 and discarding it is the bug."""
    import json as _json
    base, context, stop = _serve(commit=False)
    try:
        status, body = _request(
            f"{base}/api/decide/approve", "POST", {"rationale": "ok"},
            _as("alice"))
        assert status == 409, body
        assert "read-only" in _json.loads(body)["error"]
        assert context.model.unapproved_elements(), "nothing may have changed"
    finally:
        stop()


def test_approving_through_the_web_surface_actually_mutates_and_commits():
    base, context, stop = _serve()
    try:
        outstanding_before = len(context.model.unapproved_elements())
        assert outstanding_before, "fixture must start unapproved"

        status, body = _request(
            f"{base}/api/decide/approve", "POST", {"rationale": "reviewed"},
            _as("alice"))
        assert status == 200, body

        assert context.model.unapproved_elements() == [], (
            "the model must actually be approved — the old path returned 200 "
            "and left every element at Quarantine")
        assert len(context.committed) == outstanding_before, (
            "every applied decision must reach the commit target")
    finally:
        stop()


def test_the_web_surface_cannot_promote_a_criterion_by_merely_approving():
    """S-19 holds on this surface too: a click is not an act of authorship."""
    import json as _json
    base, context, stop = _serve()
    context.drafted = {"AC-1": "Given Ready, when POST /login, then LoggedIn."}
    try:
        status, body = _request(
            f"{base}/api/decide/approve", "POST",
            {"rationale": "ok", "criterion_id": "AC-1",
             "criterion_text": "Given Ready, when POST /login, then LoggedIn."},
            _as("alice"))
        assert status == 200, body
        assert _json.loads(body)["criteria_promoted"] == [], (
            "approving a draft unchanged documents the system; it does not "
            "validate it")
    finally:
        stop()


def test_the_web_surface_promotes_when_the_reviewer_affirms_intent():
    import json as _json
    base, context, stop = _serve()
    context.drafted = {"AC-1": "Given Ready, when POST /login, then LoggedIn."}
    try:
        status, body = _request(
            f"{base}/api/decide/approve", "POST",
            {"rationale": "ok", "criterion_id": "AC-1",
             "criterion_text": "Given Ready, when POST /login, then LoggedIn.",
             "affirmed_as_intent": True},
            _as("alice"))
        assert status == 200, body
        assert _json.loads(body)["criteria_promoted"], (
            "an explicit affirmation is one of the two acts that create intent")
    finally:
        stop()


# ---------------------------------------------------------------------------
# §9.1's decisions 3, 4 and 5 — served at last
# ---------------------------------------------------------------------------
#
# The spec designates this surface "Primary. All six decisions" (§9.2). It served
# two. All six evidence screens existed in `evidence.py` and all six capabilities
# in `roles.py`; what did not exist was anywhere to RECORD an answer for the
# other three, so `metis divergence` reported and nothing accepted a resolution,
# matching proposed and nothing accepted a confirmation, drift classified and
# nothing accepted a decision.

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
#
# This surface used to trust `X-Metis-User` and `X-Metis-Role`, so a test
# "authenticated" by asserting a name. It now resolves the actor through
# `api/auth.py` -- the same store and the same constant-time comparison the HTTP
# API uses -- so a decision test has to present a credential, and a name alone
# gets 401.
#
# One name, one role, which is the point of a store: `bob` was previously the
# proposer at `reviewer` in one test and a `viewer` in another, and a store
# cannot express that. He keeps the role the N-10 test needs him to have and the
# viewer case gets its own principal, because what that test asserts is a
# property of the ROLE and never of the name.

_PRINCIPALS = {
    "alice": ("reviewer", "alice-token"),      # the distinct reviewer
    "bob": ("reviewer", "bob-token"),          # the PROPOSER — see N-10 below
    "carol": ("contributor", "carol-token"),
    "dave": ("viewer", "dave-token"),
}


@pytest.fixture(autouse=True)
def _credential_store(tmp_path, monkeypatch):
    """A real digest store for every test in this module.

    Autouse because the alternative is remembering it in twenty decision tests,
    and the one that forgot would fail with 401 and read as a broken assertion
    rather than as missing setup.
    """
    from metis_mcp.api import auth

    store = tmp_path / "tokens.tsv"
    store.write_text("".join(
        f"{auth.digest(token)}\t{name}\t{role}\n"
        for name, (role, token) in _PRINCIPALS.items()))
    monkeypatch.setenv(auth.TOKENS_ENV, str(store))
    return store


def _as(name: str) -> dict:
    """Bearer headers for one principal."""
    return {"Authorization": f"Bearer {_PRINCIPALS[name][1]}",
            "Content-Type": "application/json"}


AS_REVIEWER = {"Authorization": "Bearer alice-token",
               "Content-Type": "application/json"}
AS_VIEWER = {"Authorization": "Bearer dave-token",
             "Content-Type": "application/json"}

_DIVERGENCE = {
    "element_id": "t_lock", "choice": "accept_ac",
    "rationale": "the code locks after 3 attempts; AC-7 says 5",
    "code_side": {"anchor": "Auth.java:88@abc123", "guard": "attempts >= 3"},
    "ac_side": {"text": "after 5 failed attempts", "ticket": "PROJ-14"},
    "blocked_paths": ["p1", "p2"],
}
_DRIFT = {
    "case_id": "TC-9", "drift_class": "obsolete", "action": "propose_deprecate",
    "detail": "the transition it covered was removed",
    "resolution": "propose_deprecate", "published": "old text",
    "last_generated": "old text", "newly_generated": "",
}


def _match_body(**overrides):
    base, context, _ = None, None, None
    # X-17: `why_proposed` is required evidence, not decoration. A reviewer must
    # be able to see that a match rests on a route and a status rather than on
    # wording similarity, which is never sufficient on its own.
    body = {"ac_id": "AC-7", "transition_id": "", "ac_text": "after 5 attempts",
            "code_anchor": "Auth.java:88@abc123", "confirmed": True,
            "rationale": "route and status both match",
            "why_proposed": {"evidence": {"route": "POST /login", "status": 423},
                             "strength": 2, "ambiguous": False, "note": ""}}
    body.update(overrides)
    return body


def test_a_divergence_screen_without_both_sides_blocks_the_decision():
    """N-4, on the screen that most needs it.

    S-10 says neither side wins automatically. A screen showing one side and
    calling itself decidable would BE the precedence rule S-10 forbids.
    """
    base, context, stop = _serve()
    try:
        status, _ = _request(f"{base}/api/screen/divergence?element=t_lock")
        assert status == 409, "a one-sided divergence screen must refuse"
    finally:
        stop()


def test_resolving_a_divergence_records_it_durably():
    import json as _json

    base, context, stop = _serve()
    try:
        status, body = _request(f"{base}/api/decide/divergence", "POST",
                                _DIVERGENCE, AS_REVIEWER)
        assert status == 200, body
        assert _json.loads(body)["outcome"] == "accept_ac"

        recorded = context.review_state.divergences["t_lock"]
        assert recorded.choice == "accept_ac"
        assert recorded.decided_by == "alice"
        assert recorded.rationale, "S-11: the reason is part of the record"
        assert recorded.evidence_fingerprint, (
            "N-13: a decision records what evidence was PRESENTED, not only the "
            "outcome")
        assert context.saved, "a decision that is not persisted was not taken"
    finally:
        stop()


def test_a_divergence_with_no_reason_is_refused():
    """S-11 again, and not as politeness.

    Recording only the outcome makes the choice indistinguishable from a
    precedence rule, attributed to a person who never gave one.
    """
    base, context, stop = _serve()
    try:
        status, body = _request(f"{base}/api/decide/divergence", "POST",
                                {**_DIVERGENCE, "rationale": "  "}, AS_REVIEWER)
        assert status == 409, body
        assert "S-11" in body
        assert not context.review_state.divergences
    finally:
        stop()


def test_a_viewer_may_not_decide_any_of_the_three():
    """N-9, per decision, because each carries its own capability."""
    base, context, stop = _serve()
    try:
        for path, body in (("divergence", _DIVERGENCE), ("drift", _DRIFT)):
            status, _ = _request(f"{base}/api/decide/{path}", "POST", body, AS_VIEWER)
            assert status == 403, f"{path} accepted a viewer"
        assert not context.review_state.divergences and not context.review_state.drift
    finally:
        stop()


def test_a_rejected_match_is_stored_rather_than_dropped():
    """X-18. An unconsidered proposal and a refused one are different states.

    Collapsing them means the same rejected candidate returns looking new on
    every subsequent run, which trains a reviewer to stop reading them.
    """
    base, context, stop = _serve()
    try:
        transition_id = next(iter(context.model.transitions))
        status, body = _request(
            f"{base}/api/decide/match", "POST",
            _match_body(transition_id=transition_id, confirmed=False,
                        rationale="wording similarity only; no route evidence"),
            AS_REVIEWER)
        assert status == 200, body
        stored = context.review_state.matches[f"AC-7->{transition_id}"]
        assert stored.confirmed is False
        assert stored.rationale
    finally:
        stop()


def test_a_match_without_why_it_was_proposed_still_blocks():
    """X-17 survives the route that made the decision reachable.

    `confirm_match_screen` gained a `why_proposed` parameter so a web caller --
    which holds the matcher's report as data and not as a `Proposal` object --
    could satisfy N-3 at all. The risk in that change is that it becomes a way
    to skip the requirement: pass nothing, get a screen anyway.

    It is not. Omitting it blocks exactly as before, which is the whole point of
    the evidence being required rather than displayed.
    """
    base, context, stop = _serve()
    try:
        transition_id = next(iter(context.model.transitions))
        body = _match_body(transition_id=transition_id)
        body.pop("why_proposed")
        status, out = _request(f"{base}/api/decide/match", "POST", body,
                               AS_REVIEWER)
        assert status == 409, out
        assert "why_proposed" in out
        assert not context.review_state.matches
    finally:
        stop()


def test_a_real_proposal_outranks_a_supplied_one():
    """The fallback may not let a caller pass prettier evidence than the matcher
    produced."""
    from metis_mcp.review_ui.evidence import confirm_match_screen
    from mbt_fixtures import login_model

    model = login_model()
    transition_id = next(iter(model.transitions))

    class _Candidate:
        transition_id = None
        evidence = {"route": "real"}
        strength = 9

    class _Proposal:
        candidates = ()
        is_ambiguous = False
        note = "from the matcher"

    candidate = _Candidate()
    candidate.transition_id = transition_id
    proposal = _Proposal()
    proposal.candidates = (candidate,)

    screen = confirm_match_screen(
        model, "AC-1", "text", transition_id, proposal=proposal,
        why_proposed={"evidence": {"route": "supplied"}, "strength": 99})
    assert screen.evidence["why_proposed"]["evidence"] == {"route": "real"}


def test_a_drift_decision_cannot_name_an_action_the_publisher_lacks():
    """T-16: obsolete DEPRECATES, and there is no delete to choose.

    A decision nothing can carry out is worse than no decision, because it reads
    as settled.
    """
    base, context, stop = _serve()
    try:
        status, body = _request(f"{base}/api/decide/drift", "POST",
                                {**_DRIFT, "resolution": "delete"}, AS_REVIEWER)
        assert status == 409, body
        assert "unknown drift resolution" in body
        assert not context.review_state.drift
    finally:
        stop()


def test_a_read_only_session_refuses_rather_than_pretending():
    """The failure `commit` was added to fix, applied to the new three.

    Returning 200 for a decision that is then dropped is the privileged,
    unlogged path N-1 prohibits.
    """
    base, context, stop = _serve(commit=False)
    try:
        status, body = _request(f"{base}/api/decide/divergence", "POST",
                                _DIVERGENCE, AS_REVIEWER)
        assert status == 409, body
        assert "read-only" in body
    finally:
        stop()


def test_every_surface_produces_the_same_record(tmp_path):
    """N-1: no surface has a privileged or unlogged path.

    The CLI and this server call the same function in `review.decisions`, so the
    stored decision must be identical apart from who and when. Asserting it here
    is what stops a second implementation appearing behind the web handler --
    which is exactly how two surfaces drift into disagreeing about what a
    decision means.
    """
    from metis_mcp.review.decisions import resolve_divergence
    from metis_mcp.review.state import ReviewState

    base, context, stop = _serve()
    try:
        _request(f"{base}/api/decide/divergence", "POST", _DIVERGENCE, AS_REVIEWER)
        over_http = context.review_state.divergences["t_lock"]
    finally:
        stop()

    via_cli = ReviewState(model_id="login-api")
    resolve_divergence(via_cli, "t_lock", _DIVERGENCE["choice"],
                       _DIVERGENCE["rationale"], actor="alice")
    stored = via_cli.divergences["t_lock"]

    assert stored.choice == over_http.choice
    assert stored.rationale == over_http.rationale
    assert stored.decided_by == over_http.decided_by


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


# ---------------------------------------------------------------------------
# The rendered decision surface
# ---------------------------------------------------------------------------
#
# §9.2 called this surface "Primary. All six decisions" and that was true of the
# JSON API and false of the page: `/model` carried no <button>, <form> or
# <script>, so a reviewer could look at the model and decide nothing in it.
# Academy lesson 16 walked a business analyst through screens that did not
# exist.
#
# Forms rather than scripting, so the CSP keeps `script-src` absent and the
# credential never enters anything a page can read -- which is what `sessions.py`
# is for.


def _login(base, token: str):
    """Sign in and return the session cookie header."""
    import urllib.error
    import urllib.parse
    import urllib.request

    data = urllib.parse.urlencode({"token": token}).encode()
    req = urllib.request.Request(f"{base}/login", data=data, method="POST")

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        response = opener.open(req)
        headers = response.headers
    except urllib.error.HTTPError as e:
        headers = e.headers
    cookie = headers.get("Set-Cookie", "")
    return {"Cookie": cookie.split(";")[0]} if cookie else {}


def _form_post(url, fields, headers=None):
    import urllib.error
    import urllib.parse
    import urllib.request

    # `doseq` so a checkbox list posts as the repeated field a browser sends.
    # Without it a list value is urlencoded as its repr and the server sees one
    # field containing "['a', 'b']".
    data = urllib.parse.urlencode(fields, doseq=True).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers=headers or {})

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        response = opener.open(req)
        return response.status, response.read().decode(), response.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), e.headers


def test_a_decision_page_sends_an_anonymous_visitor_to_sign_in():
    base, _, stop = _serve()
    try:
        status, body = _request(f"{base}/decide/approve")
        # urllib follows the 303, so the login form is what comes back.
        assert status == 200
        assert 'name="token"' in body
    finally:
        stop()


def test_signing_in_with_a_real_token_opens_a_session():
    base, context, stop = _serve()
    try:
        assert len(context.sessions) == 0
        headers = _login(base, "alice-token")
        assert headers, "no Set-Cookie came back"
        assert len(context.sessions) == 1
    finally:
        stop()


def test_a_wrong_token_opens_no_session_and_says_nothing_useful():
    base, context, stop = _serve()
    try:
        status, body, _ = _form_post(f"{base}/login", {"token": "nope"})
        assert status == 401
        assert "not recognised" in body
        assert len(context.sessions) == 0
    finally:
        stop()


def test_the_session_cookie_is_httponly_and_samesite_strict():
    """Both flags are load-bearing: SameSite is the CSRF defence on a
    state-changing POST, HttpOnly keeps the id away from any script."""
    base, _, stop = _serve()
    try:
        _, _, headers = _form_post(f"{base}/login", {"token": "alice-token"})
        cookie = headers.get("Set-Cookie", "")
        assert "HttpOnly" in cookie
        assert "SameSite=Strict" in cookie
    finally:
        stop()


def test_the_login_form_will_not_redirect_off_this_server():
    """A caller-supplied `next` would otherwise make the login page an open
    redirect — the classic way a sign-in form becomes a phishing step."""
    base, _, stop = _serve()
    try:
        _, _, headers = _form_post(
            f"{base}/login",
            {"token": "alice-token", "next": "https://evil.example/steal"})
        assert headers.get("Location") == "/model"

        _, _, headers = _form_post(
            f"{base}/login", {"token": "alice-token", "next": "//evil.example"})
        assert headers.get("Location") == "/model"
    finally:
        stop()


def test_a_signed_in_reviewer_gets_a_form_with_every_outstanding_element():
    base, context, stop = _serve()
    try:
        headers = _login(base, "alice-token")
        status, body = _request(f"{base}/decide/approve", headers=headers)
        assert status == 200
        assert 'action="/decide/approve"' in body
        assert "<button" in body
        # N-5: a batch decision must show its contents, so every element the
        # gate is waiting on is nameable rather than only "approve all".
        for _, element_id, _ in context.model.unapproved_elements():
            assert f'value="{element_id}"' in body, element_id
    finally:
        stop()


def test_a_form_approval_records_the_same_decision_the_json_route_would():
    """N-1: no surface has a privileged or differently-shaped path.

    It reuses `_approve` rather than reimplementing it, and this is what says so
    — a second application path here would be a second definition of the gate.
    """
    base, context, stop = _serve()
    try:
        headers = _login(base, "alice-token")
        status, _, response_headers = _form_post(
            f"{base}/decide/approve",
            {"element_id": "LoggedIn", "rationale": "checked against AC-3"},
            headers)
        assert status == 303, "a decision should redirect, so a refresh cannot resubmit"
        assert "done=" in response_headers.get("Location", "")

        assert len(context.audit.entries) == 1
        decision = context.audit.entries[0]
        assert decision.actor == "alice"
        assert decision.surface == "web"
        assert decision.rationale == "checked against AC-3"
    finally:
        stop()


def test_every_recorded_decision_carries_the_evidence_fingerprint():
    """N-13/N-14, and the field three of four surfaces silently left empty.

    `Screen.fingerprint()` was written for exactly this and had no caller
    outside `policy.py`, so a web or REST decision recorded a digest of nothing
    while its own docstring explained that the field is what makes a record
    answerable later. A record that cannot be checked against what the decider
    SAW is indistinguishable from one made on information they never had.
    """
    base, context, stop = _serve()
    try:
        headers = _login(base, "alice-token")
        _form_post(f"{base}/decide/approve",
                   {"element_id": "LoggedIn", "rationale": "r"}, headers)
        decision = context.audit.entries[0]
        assert decision.evidence_fingerprint, (
            "the decision recorded an empty evidence fingerprint")
        assert len(decision.evidence_fingerprint) >= 16
    finally:
        stop()


def test_a_viewer_is_refused_at_the_form_and_nothing_is_recorded():
    base, context, stop = _serve()
    try:
        headers = _login(base, "dave-token")            # a viewer
        status, body, _ = _form_post(
            f"{base}/decide/approve",
            {"element_id": "LoggedIn", "rationale": "let me in"}, headers)
        assert status == 403
        assert "may not approve_model" in body
        assert context.audit.entries == []
    finally:
        stop()


def test_a_blocked_screen_renders_the_refusal_and_no_submit_control():
    """N-4 through the rendered surface.

    A disabled button invites somebody to look for the enabling trick, so there
    is no button at all — the page is the refusal, and it names what is absent.
    """
    from metis_mcp.review_ui import pages
    from metis_mcp.review_ui.evidence import Screen

    model = login_model(approved=False)
    screen = Screen(decision="approve_model", element_id=model.id,
                    evidence={"model": model.id},
                    missing=["validation", "reconciliation"])
    body = pages.approve_page(model, screen, Identity("alice", "reviewer"),
                              model.unapproved_elements())
    assert "<button" not in body
    assert 'action="/decide/approve"' not in body
    assert "validation" in body and "reconciliation" in body


def test_the_pages_add_no_script_and_the_policy_still_forbids_one():
    """The decision surface is forms, deliberately.

    If a page ever needs scripting, this test is where that decision gets made
    rather than discovered — relaxing the CSP is how the credential ends up
    somewhere a page can read it.
    """
    base, _, stop = _serve()
    try:
        headers = _login(base, "alice-token")
        for path in ("/model", "/decide/approve", "/decide/name-state", "/audit"):
            status, body = _request(f"{base}{path}", headers=headers)
            assert status == 200, path
            assert "<script" not in body.lower(), path
    finally:
        stop()


def test_signing_out_closes_the_session():
    base, context, stop = _serve()
    try:
        headers = _login(base, "alice-token")
        assert len(context.sessions) == 1
        _request(f"{base}/logout", headers=headers)
        assert len(context.sessions) == 0

        status, body, _ = _form_post(
            f"{base}/decide/approve",
            {"element_id": "LoggedIn", "rationale": "r"}, headers)
        assert status in (303, 401)
        assert context.audit.entries == []
    finally:
        stop()


# --- approving a considered subset -------------------------------------------
#
# The approve form offered one element or the whole model. A reviewer content
# with thirty of forty therefore submitted thirty times with thirty rationales,
# while approving all forty took one click — the blanket decision was the
# cheapest action on the page and the considered one the most expensive, which
# is backwards for a gate.


def test_the_approve_page_lists_every_outstanding_element_selectably():
    """Hidden behind a dropdown, an id cannot be read while deciding."""
    base, context, stop = _serve()
    try:
        headers = _login(base, "alice-token")
        status, body = _request(f"{base}/decide/approve", headers=headers)

        assert status == 200
        outstanding = context.model.unapproved_elements()
        assert outstanding, "nothing outstanding, so this asserts nothing"
        for _, element_id, _ in outstanding:
            assert f'value="{element_id}"' in body, element_id
        assert body.count('name="element_ids"') == len(outstanding)
    finally:
        stop()


def test_every_element_is_ticked_by_default_so_approving_all_stays_one_click():
    """Nothing got harder: the default is still the whole model."""
    base, context, stop = _serve()
    try:
        headers = _login(base, "alice-token")
        _, body = _request(f"{base}/decide/approve", headers=headers)

        assert body.count('name="element_ids"') == body.count("checked")
    finally:
        stop()


def test_a_chosen_subset_is_approved_and_the_rest_stays_outstanding():
    """The decision the old form could not express."""
    base, context, stop = _serve()
    try:
        headers = _login(base, "alice-token")
        outstanding = [eid for _, eid, _ in context.model.unapproved_elements()]
        assert len(outstanding) >= 2, "need two to approve one and leave one"
        picked, left = outstanding[0], outstanding[1]

        status, body, _ = _form_post(
            f"{base}/decide/approve",
            {"element_ids": [picked], "decision": "approve",
             "rationale": "reviewed this one"},
            headers)

        assert status in (200, 303), body[:300]
        remaining = [eid for _, eid, _ in context.model.unapproved_elements()]
        assert picked not in remaining, "the chosen element was not approved"
        assert left in remaining, "an unticked element must stay outstanding"
    finally:
        stop()


def test_deferring_the_uncertain_ones_is_available_on_the_same_form():
    """Defer is what makes approving the rest safe — otherwise a reviewer either
    blesses everything or grinds through it one at a time."""
    base, context, stop = _serve()
    try:
        headers = _login(base, "alice-token")
        _, body = _request(f"{base}/decide/approve", headers=headers)

        assert 'name="decision"' in body
        for choice in ("approve", "defer", "reject"):
            assert f'value="{choice}"' in body, choice
    finally:
        stop()


def test_an_unknown_decision_is_refused_rather_than_defaulting_to_approve():
    """Defaulting here would turn a typo into an approval."""
    base, context, stop = _serve()
    try:
        headers = _login(base, "alice-token")
        outstanding = [eid for _, eid, _ in context.model.unapproved_elements()]

        status, body, _ = _form_post(
            f"{base}/decide/approve",
            {"element_ids": [outstanding[0]], "decision": "looks-fine",
             "rationale": "why not"},
            headers)

        assert status == 400
        assert "looks-fine" in body
        assert outstanding[0] in [
            eid for _, eid, _ in context.model.unapproved_elements()]
    finally:
        stop()


def test_a_subset_naming_an_element_that_does_not_exist_is_refused():
    """A typo'd id must not silently approve the elements beside it."""
    base, context, stop = _serve()
    try:
        headers = _login(base, "alice-token")
        outstanding = [eid for _, eid, _ in context.model.unapproved_elements()]

        status, _, _ = _form_post(
            f"{base}/decide/approve",
            {"element_ids": [outstanding[0], "no-such-element"],
             "decision": "approve", "rationale": "batch"},
            headers)

        assert status == 404
        assert outstanding[0] in [
            eid for _, eid, _ in context.model.unapproved_elements()], (
            "nothing may be applied when part of the batch is unknown")
    finally:
        stop()


def test_the_decision_surface_still_carries_no_script():
    """A tick-all button would need inline script, and the CSP exception is
    worth more than the convenience. Asserted here too so the reason travels
    with the page that wanted one."""
    base, _, stop = _serve()
    try:
        headers = _login(base, "alice-token")
        _, body = _request(f"{base}/decide/approve", headers=headers)

        assert "<script" not in body.lower()
        assert "onclick" not in body.lower()
    finally:
        stop()


# --- the queue: what is waiting on a person ----------------------------------
#
# `run_status` answers "where did THIS run get to" and needs an id you only have
# if you started the run. Nobody could ask what was waiting on them, so a gate
# reached on Tuesday got attended to when somebody happened to remember it.


def test_the_queue_lists_a_run_that_stopped_at_a_gate():
    from metis_mcp.review_ui import pages

    html = pages.queue_page(
        [{"workflow": "model-build", "scope": "records-api",
          "blocked_on": "model-approval", "waiting_since": "2026-09-05T10:00:00",
          "outstanding_count": 40, "detail": "40 element(s) awaiting review",
          "outstanding": ["state Contract Quarantine"],
          "next_command": "metis review apply --journey records"}],
        None, {"model-build": 1})

    assert "records-api" in html
    assert "model-approval" in html
    assert "40 element(s) awaiting review" in html


def test_the_card_states_no_count_of_its_own():
    """**The `len(rows)` bug, caught in the queue's first render.**

    G1's `outstanding` is display lines, and it deliberately appends a
    "NOT RECOVERED" section listing what extraction could not model — so its
    length is a line count, not a decision count. Reporting it as one turned 31
    elements awaiting review into "40 items outstanding", overstating what a
    reviewer owed. The gate's own `detail` already carries the real number, and
    one authoritative count beats two that disagree.
    """
    from metis_mcp.review_ui import pages

    html = pages.queue_page(
        [{"workflow": "model-build", "scope": "s", "blocked_on": "model-approval",
          "waiting_since": "2026-09-05",
          "detail": "s is not approved — 31 element(s) awaiting review",
          "outstanding": ["state A", "state B", "",
                          "NOT RECOVERED — 9 element(s) extraction could not model:"],
          "next_command": "c"}],
        None, {})

    assert "31 element(s) awaiting review" in html
    assert "4 item" not in html, "a line count must not be shown as a decision count"


def test_the_queue_tool_invents_no_count():
    import json as _json_mod

    from metis_mcp import server as tools

    payload = _json_mod.loads(tools.decision_queue())

    for entry in payload["waiting"]:
        assert "outstanding_count" not in entry


def test_the_queue_renders_the_engines_own_next_command():
    """Not one this page composed. A surface that rewrote the resolution would
    be giving the reviewer its own account of what unblocks the gate."""
    from metis_mcp.review_ui import pages

    command = "metis workflow resume risk-review --scope x --accept accept-risk"
    html = pages.queue_page(
        [{"workflow": "risk-review", "scope": "x", "blocked_on": "risk-acceptance",
          "waiting_since": "2026-09-05", "outstanding_count": 1,
          "outstanding": ["one question"], "next_command": command}],
        None, {})

    assert command in html


def test_an_empty_queue_says_what_it_does_not_cover():
    """"Nothing waiting" must not read as "nothing wrong": a failed run needs
    fixing and deliberately does not appear here."""
    from metis_mcp.review_ui import pages

    html = pages.queue_page([], None, {})

    assert "Nothing is waiting" in html
    assert "failed run" in html


def test_a_gate_with_no_screen_says_so_rather_than_linking_into_a_refusal():
    """Four of the six decisions are JSON-only because the review context does
    not hold what they are about. A link into a 409 teaches people the queue is
    unreliable."""
    from metis_mcp.review_ui import pages

    html = pages.queue_page(
        [{"workflow": "test-generate", "scope": "x",
          "blocked_on": "publication-confirmation", "waiting_since": "2026-09-05",
          "outstanding_count": 2, "outstanding": [], "next_command": "metis publish"}],
        None, {})

    assert "no rendered screen yet" in html
    # Scoped to the card: `/decide/approve` is in the shared nav on every page,
    # which is correct. What must not appear is a link from THIS card.
    card = html.split('<div class="card">')[-1]
    assert "Open the approval screen" not in card


def test_the_queue_takes_no_decision_of_its_own():
    """A queue that could also approve is one somebody works through without
    reading — and the evidence gate lives on the decision page, not here."""
    from metis_mcp.review_ui import pages

    html = pages.queue_page(
        [{"workflow": "model-build", "scope": "s", "blocked_on": "model-approval",
          "waiting_since": "2026-09-05", "outstanding_count": 1,
          "outstanding": ["state X"], "next_command": "c"}],
        None, {})

    assert "<form" not in html.lower()
    assert "<script" not in html.lower()


def test_the_queue_is_served_and_reachable_from_the_decision_pages():
    """The model view carries no nav at all and never has — it is a rendered
    table rather than part of the decision surface, so this asserts the pages
    that do share one."""
    base, _, stop = _serve()
    try:
        headers = _login(base, "alice-token")
        status, _ = _request(f"{base}/queue", headers=headers)
        assert status == 200

        for path in ("/decide/approve", "/audit"):
            _, body = _request(f"{base}{path}", headers=headers)
            assert "/queue" in body, path
    finally:
        stop()


def test_the_queue_answers_without_a_graph():
    """Run records are files. A gate somebody owes a decision on does not stop
    mattering because Neo4j is down, and every model read returning 204 is
    exactly when a reviewer most needs to see what is outstanding."""
    from metis_mcp import server as tools

    import json as _json_mod

    payload = _json_mod.loads(tools.decision_queue())

    assert payload["ok"] is True
    assert "waiting" in payload and "by_workflow" in payload


# --- the first of the four unrenderable decisions gets a page ----------------
#
# `confirm-match` is fillable from a review session — the model is loaded and
# the pre-filter is pure — which is why it is the one rendered first. The other
# three need a live read (a tracker, a generation run) and say so.


def test_confirm_match_renders_when_the_session_can_fill_it():
    from metis_mcp.reconciliation.matching import AcceptanceCriterion

    base, context, stop = _serve()
    try:
        context.criteria = [AcceptanceCriterion(
            id="AC-1",
            text="When the password is wrong, the system shall reject with 401")]
        tid = context.model.transition_ids()[0]
        headers = _login(base, "alice-token")

        status, body = _request(
            f"{base}/decide/confirm-match?ac=AC-1&transition={tid}",
            headers=headers)

        assert status == 200, body[:300]
        assert "AC-1" in body and tid in body
        assert "Why this was proposed" in body
    finally:
        stop()


def test_confirm_match_refuses_and_names_what_is_missing():
    """N-4's discipline, finally actionable. `Screen.require()` could block a
    decision with incomplete evidence but could not say which input was absent
    or who held it — by then the caller had already failed to supply it."""
    base, context, stop = _serve()
    try:
        context.criteria = []          # nothing to fill `ac_text` from
        tid = context.model.transition_ids()[0]
        headers = _login(base, "alice-token")

        status, body = _request(
            f"{base}/decide/confirm-match?ac=AC-1&transition={tid}",
            headers=headers)

        assert status == 409
        assert "cannot be drawn yet" in body
        assert "ac_text" in body
        assert "AcceptanceCriterion node in the graph" in body
    finally:
        stop()


def test_the_refusal_records_nothing():
    """A refusal is a screen, not a decision that half happened."""
    base, context, stop = _serve()
    try:
        context.criteria = []
        headers = _login(base, "alice-token")
        before = len(context.audit.entries)

        _request(f"{base}/decide/confirm-match?ac=AC-1&transition=t01",
                 headers=headers)

        assert len(context.audit.entries) == before
    finally:
        stop()


def test_the_match_page_shows_the_matchers_own_evidence_not_a_summary():
    """X-17: a reviewer has to see that a match rests on a route and a status
    rather than on wording similarity, which is never sufficient alone."""
    from metis_mcp.reconciliation.matching import AcceptanceCriterion

    base, context, stop = _serve()
    try:
        context.criteria = [AcceptanceCriterion(id="AC-1", text="unrelated words")]
        tid = context.model.transition_ids()[-1]
        headers = _login(base, "alice-token")

        _, body = _request(
            f"{base}/decide/confirm-match?ac=AC-1&transition={tid}",
            headers=headers)

        assert "narrows candidates" in body
        assert "override" in body, (
            "confirming a pairing the matcher never proposed must say so")
    finally:
        stop()
