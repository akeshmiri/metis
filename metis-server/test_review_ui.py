"""
Review-UI tests (application spec §9.1, §9.3; N-2, N-3, N-4, N-5).

Free to run: evidence assembly and rendering are pure.
"""
import sys

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

    model = login_model(approved=False)
    committed: list = []
    context = ReviewContext(
        model=model, audit=AuditLog(), proposers={model.id: "bob"},
        commit=((lambda ctx, applied: committed.extend(applied)) if commit else None))
    context.committed = committed
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


def test_n13_a_decision_without_an_identity_is_refused():
    import json as _json
    base, context, stop = _serve()
    try:
        status, body = _request(f"{base}/api/decide/approve", "POST", {})
        assert status == 401
        assert "identity required" in _json.loads(body)["error"]
        assert context.audit.entries == []
    finally:
        stop()


def test_n9_a_contributor_may_not_approve_through_the_web_surface():
    import json as _json
    base, context, stop = _serve()
    try:
        status, body = _request(
            f"{base}/api/decide/approve", "POST", {},
            {"X-Metis-User": "carol", "X-Metis-Role": "contributor"})
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
            {"X-Metis-User": "bob", "X-Metis-Role": "reviewer"})
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
            {"X-Metis-User": "alice", "X-Metis-Role": "reviewer"})
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
            {"X-Metis-User": "alice", "X-Metis-Role": "reviewer"})
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
            {"X-Metis-User": "alice", "X-Metis-Role": "reviewer"})
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
            {"X-Metis-User": "alice", "X-Metis-Role": "reviewer"})
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
                 {"X-Metis-User": "alice", "X-Metis-Role": "reviewer"})
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
            {"X-Metis-User": "alice", "X-Metis-Role": "reviewer"})
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
            {"X-Metis-User": "alice", "X-Metis-Role": "reviewer"})
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
            {"X-Metis-User": "alice", "X-Metis-Role": "reviewer"})
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
            {"X-Metis-User": "alice", "X-Metis-Role": "reviewer"})
        assert status == 200, body
        assert _json.loads(body)["criteria_promoted"], (
            "an explicit affirmation is one of the two acts that create intent")
    finally:
        stop()


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
