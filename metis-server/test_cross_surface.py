"""
Cross-surface / INVOKES tests (application spec §2.2.1; M-5a..M-5g,
A-12a..A-12c, A-17a..A-17e).

Free to run: everything is pure; persistence is asserted through its plan.
"""
import sys

from metis_mcp.mbt.coverage import DIRECT, INDIRECT, Ledger, LedgerRow, credit_indirect
from metis_mcp.mbt.criteria import ALL_TRANSITIONS, GUARD_COVERAGE
from metis_mcp.mbt.cross_surface import (
    API_ONLY,
    inherited_guards,
    triage_api_only,
    format_triage,
    NO_KNOWN_CONSUMER,
    CONSUMED_ELSEWHERE,
    DANGLING_INVOKES,
    RESTATED_GUARD,
    UNHANDLED_OUTCOME,
    InvokesLink,
    LinkRefused,
    LinkSet,
    confirm_link,
    divergences,
    effective_guard,
    format_divergences,
    plan_invokes_writes,
    plan_ui_transitions,
)
from metis_mcp.mbt.model import IMPLEMENTED, Model, State, Transition


def _api_model() -> Model:
    """Three outcomes of one endpoint, plus an unrelated one nothing exposes."""
    m = Model(
        id="login-api",
        states={s: State(id=s, name=s, surface="api", is_initial=(s == "LoggedOut"))
                for s in ("LoggedOut", "LoggedIn", "LoginFailed", "AccountLocked",
                          "RateLimited")},
        transitions={
            "a-ok": Transition(id="a-ok", source="LoggedOut", trigger="POST /auth/login",
                               target="LoggedIn", guard="credentials_valid"),
            "a-bad": Transition(id="a-bad", source="LoggedOut", trigger="POST /auth/login",
                                target="LoginFailed", guard="NOT credentials_valid"),
            "a-locked": Transition(id="a-locked", source="LoggedOut",
                                   trigger="POST /auth/login", target="AccountLocked",
                                   guard="account_locked"),
            "a-ratelimit": Transition(id="a-ratelimit", source="LoggedOut",
                                      trigger="POST /auth/login", target="RateLimited",
                                      guard="too_many_requests"),
        })
    m.reindex()
    return m


def _ui_model(include_locked=True, restated_guard=False) -> Model:
    transitions = {
        "u-ok": Transition(id="u-ok", source="LoginForm", trigger="click_sign_in",
                           target="Dashboard"),
        "u-bad": Transition(id="u-bad", source="LoginForm", trigger="click_sign_in",
                            target="ErrorShown",
                            guard=("NOT credentials_valid" if restated_guard else "")),
        "u-validation": Transition(id="u-validation", source="LoginForm",
                                   trigger="click_sign_in", target="ValidationError",
                                   guard="email_field_blank"),
        "u-nav": Transition(id="u-nav", source="LoginForm", trigger="click_help",
                            target="HelpPage"),
    }
    if include_locked:
        transitions["u-locked"] = Transition(
            id="u-locked", source="LoginForm", trigger="click_sign_in",
            target="LockoutScreen")
    states = {s: State(id=s, name=s, surface="ui", is_initial=(s == "LoginForm"))
              for s in ("LoginForm", "Dashboard", "ErrorShown", "ValidationError",
                        "HelpPage", "LockoutScreen")}
    m = Model(id="login-ui", states=states, transitions=transitions)
    m.reindex()
    return m


def _links(confirmed=True, include_locked=True) -> LinkSet:
    pairs = [("u-ok", "a-ok"), ("u-bad", "a-bad")]
    if include_locked:
        pairs.append(("u-locked", "a-locked"))
    links = LinkSet(journey="login")
    for ui, api in pairs:
        link = InvokesLink(ui_transition_id=ui, api_transition_id=api,
                           proposed_by="jvm-behaviour", evidence={"endpoint": "/auth/login"})
        links.links.append(confirm_link(link, "alice") if confirmed else link)
    return links


# --------------------------------------------------------------------------
# M-5a / M-5e : the link, and many-to-one
# --------------------------------------------------------------------------

def test_a_link_points_from_ui_to_api():
    link = _links().links[0]
    assert link.ui_transition_id == "u-ok"
    assert link.api_transition_id == "a-ok"
    assert link.evidence["endpoint"] == "/auth/login"


def test_m5e_the_same_api_transition_may_be_invoked_from_several_screens():
    links = LinkSet(journey="login")
    for screen in ("login-page", "checkout-modal", "session-expiry-prompt"):
        links.links.append(confirm_link(
            InvokesLink(ui_transition_id=f"{screen}::sign_in",
                        api_transition_id="a-ok", proposed_by="pack"), "alice"))
    assert len(links.as_map()) == 3
    assert links.invoked_api_ids() == {"a-ok"}


# --------------------------------------------------------------------------
# M-5g : proposed by extraction, confirmed by a human
# --------------------------------------------------------------------------

def test_m5g_an_unconfirmed_link_is_a_proposal():
    links = _links(confirmed=False)
    assert links.confirmed() == []
    assert links.as_map() == {}, "unconfirmed links do not participate"
    assert len(links.as_map(confirmed_only=False)) == 3


def test_m5g_an_unconfirmed_link_cannot_credit_coverage():
    """Otherwise a matching heuristic silently raises a coverage figure — X-17's
    failure in a different costume."""
    api = _api_model()
    ledger = Ledger(model_id="login-api", criterion=ALL_TRANSITIONS)
    credited = credit_indirect(ledger, api, _links(confirmed=False).as_map(),
                               covered_elsewhere={"u-ok", "u-bad"})
    assert credited == []


def test_a_confirmation_records_who_made_it():
    link = InvokesLink(ui_transition_id="u", api_transition_id="a", proposed_by="pack")
    try:
        confirm_link(link, "   ")
    except LinkRefused as e:
        assert "records who" in str(e)
        return
    raise AssertionError("an anonymous confirmation must be refused")


# --------------------------------------------------------------------------
# A-12b : one UI transition per API outcome
# --------------------------------------------------------------------------

def test_a12b_one_ui_transition_per_api_outcome():
    api = _api_model()
    proposed = plan_ui_transitions(
        api, source_state="LoginForm", trigger="click_sign_in",
        api_trigger="POST /auth/login", api_source_state="LoggedOut",
        target_for={"a-ok": "Dashboard", "a-bad": "ErrorShown",
                    "a-locked": "LockoutScreen", "a-ratelimit": "RateLimitScreen"})
    assert len(proposed) == 4
    assert {p.api_transition_id for p in proposed} == {"a-ok", "a-bad", "a-locked",
                                                       "a-ratelimit"}
    assert {p.trigger for p in proposed} == {"click_sign_in"}, "one trigger, four branches"


def test_a12b_the_click_carries_no_guard_of_its_own():
    """M-5b: branching is determined by the API's guards, not the click's."""
    api = _api_model()
    proposed = plan_ui_transitions(
        api, source_state="LoginForm", trigger="click_sign_in",
        api_trigger="POST /auth/login", api_source_state="LoggedOut",
        target_for={"a-ok": "Dashboard", "a-bad": "ErrorShown"})
    assert all(not p.has_local_guard for p in proposed)


def test_a_local_guard_applies_identically_to_every_branch():
    """A client-side check happens before any call, so it cannot distinguish
    between API outcomes."""
    api = _api_model()
    proposed = plan_ui_transitions(
        api, source_state="LoginForm", trigger="click_sign_in",
        api_trigger="POST /auth/login", api_source_state="LoggedOut",
        target_for={"a-ok": "Dashboard", "a-bad": "ErrorShown"},
        local_guard="form_complete")
    assert {p.local_guard for p in proposed} == {"form_complete"}


def test_an_outcome_with_no_screen_is_omitted_not_invented():
    api = _api_model()
    proposed = plan_ui_transitions(
        api, source_state="LoginForm", trigger="click_sign_in",
        api_trigger="POST /auth/login", api_source_state="LoggedOut",
        target_for={"a-ok": "Dashboard"})
    assert len(proposed) == 1, "no screen is invented for the other outcomes"


# --------------------------------------------------------------------------
# A-12c : inherited guards are referenced, never restated
# --------------------------------------------------------------------------

def test_a12c_an_inherited_guard_resolves_through_the_link():
    api = _api_model()
    link = _links().links[1]                                   # u-bad -> a-bad
    guard = effective_guard("", link, api)
    assert guard.inherited == "NOT credentials_valid"
    assert guard.inherited_from == "a-bad"
    assert guard.local == ""


def test_a12c_it_tracks_the_api_guard_when_that_changes():
    """The point of a reference: no copy can drift out of step with it."""
    api = _api_model()
    link = _links().links[1]
    api.transitions["a-bad"] = Transition(
        id="a-bad", source="LoggedOut", trigger="POST /auth/login",
        target="LoginFailed", guard="NOT credentials_valid AND NOT locked")
    api.reindex()
    assert effective_guard("", link, api).inherited == "NOT credentials_valid AND NOT locked"


def test_a12c_a_restated_guard_is_reported():
    findings = divergences(_ui_model(restated_guard=True), _api_model(), _links())
    restated = [f for f in findings if f.kind == RESTATED_GUARD]
    assert len(restated) == 1 and restated[0].element_id == "u-bad"
    assert "cannot be kept in step" in restated[0].detail


def test_local_and_inherited_guards_are_kept_distinct():
    api = _api_model()
    guard = effective_guard("form_complete", _links().links[1], api)
    assert guard.local == "form_complete"
    assert guard.inherited == "NOT credentials_valid"
    assert guard.render() == "form_complete AND NOT credentials_valid"


def test_m5d_a_client_side_transition_has_no_inherited_guard():
    """Its absence is meaningful, not missing data."""
    guard = effective_guard("email_field_blank", None, _api_model())
    assert guard.inherited == "" and guard.inherited_from == ""
    assert guard.render() == "email_field_blank"


# --------------------------------------------------------------------------
# A-12a / M-5f : divergence is a query
# --------------------------------------------------------------------------

def test_a12a_an_api_transition_with_no_inbound_invokes_is_reported():
    findings = divergences(_ui_model(), _api_model(), _links())
    api_only = [f for f in findings if f.kind == API_ONLY]
    assert [f.element_id for f in api_only] == ["a-ratelimit"]
    assert "security or completeness gap" in api_only[0].detail


def test_a12a_it_says_direct_coverage_is_required():
    """C-4: no UI path can ever credit an API-only transition."""
    findings = divergences(_ui_model(), _api_model(), _links())
    api_only = next(f for f in findings if f.kind == API_ONLY)
    assert "DIRECT coverage" in api_only.remedy


def test_a_dangling_invokes_is_reported():
    api = _api_model()
    del api.transitions["a-locked"]
    api.reindex()
    findings = divergences(_ui_model(), api, _links())
    dangling = [f for f in findings if f.kind == DANGLING_INVOKES]
    assert len(dangling) == 1 and dangling[0].counterpart_id == "a-locked"


def test_an_unhandled_outcome_is_reported():
    """The UI handles this trigger but cannot render one of its outcomes."""
    findings = divergences(_ui_model(include_locked=False), _api_model(),
                           _links(include_locked=False))
    unhandled = [f for f in findings if f.kind == UNHANDLED_OUTCOME]
    assert "a-locked" in {f.element_id for f in unhandled}


# --------------------------------------------------------------------------
# A-17d : a UI-only transition is never a gap
# --------------------------------------------------------------------------

def test_a17d_ui_only_transitions_are_not_reported_as_gaps():
    findings = divergences(_ui_model(), _api_model(), _links())
    reported = {f.element_id for f in findings}
    assert "u-validation" not in reported, "client-side validation is not a gap"
    assert "u-nav" not in reported, "navigation is not a gap"


def test_a17d_the_report_says_so_explicitly():
    text = format_divergences(divergences(_ui_model(), _api_model(), _links()))
    assert "UI-only transition is NOT listed here" in text


# --------------------------------------------------------------------------
# A-17a / A-17b / A-17c : crediting, through the real ledger
# --------------------------------------------------------------------------

def test_a17a_a_ui_path_credits_the_api_transition_for_all_transitions():
    api = _api_model()
    ledger = Ledger(model_id="login-api", criterion=ALL_TRANSITIONS)
    credited = credit_indirect(ledger, api, _links().as_map(),
                               covered_elsewhere={"u-ok", "u-bad", "u-locked"})
    assert set(credited) == {"a-ok", "a-bad", "a-locked"}


def test_a17a_it_never_credits_guard_coverage():
    """C-2: a UI path can only submit what the UI is capable of submitting."""
    api = _api_model()
    ledger = Ledger(model_id="login-api", criterion=GUARD_COVERAGE)
    assert credit_indirect(ledger, api, _links().as_map(),
                           covered_elsewhere={"u-ok", "u-bad", "u-locked"}) == []


def test_a17b_an_indirectly_covered_transition_is_reported_as_such():
    api = _api_model()
    ledger = Ledger(model_id="login-api", criterion=ALL_TRANSITIONS)
    ledger.rows.append(LedgerRow(transition_id="a-ok", surface="api",
                                 mechanism=DIRECT, criterion=ALL_TRANSITIONS))
    credit_indirect(ledger, api, _links().as_map(),
                    covered_elsewhere={"u-ok", "u-bad", "u-locked"})
    assert set(ledger.indirect_only()) == {"a-bad", "a-locked"}
    assert "a-ok" not in ledger.indirect_only(), "it has direct coverage too"


def test_a17c_an_api_only_transition_is_never_credited_by_any_ui_path():
    api = _api_model()
    ledger = Ledger(model_id="login-api", criterion=ALL_TRANSITIONS)
    credited = credit_indirect(ledger, api, _links().as_map(),
                               covered_elsewhere={"u-ok", "u-bad", "u-locked",
                                                  "u-validation", "u-nav"})
    assert "a-ratelimit" not in credited


def test_a17e_the_ledger_answers_per_transition():
    api = _api_model()
    ledger = Ledger(model_id="login-api", criterion=ALL_TRANSITIONS)
    ledger.rows.append(LedgerRow(transition_id="a-ok", surface="api", mechanism=DIRECT,
                                 criterion=ALL_TRANSITIONS, test_case_id="TC-101"))
    credit_indirect(ledger, api, _links().as_map(),
                    covered_elsewhere={"u-ok", "u-bad", "u-locked"})
    assert ledger.mechanisms_for("a-ok") == {DIRECT}
    assert ledger.mechanisms_for("a-bad") == {INDIRECT}
    assert ledger.mechanisms_for("a-ratelimit") == set()
    note = next(r.note for r in ledger.rows_for("a-bad"))
    assert "via INVOKES from u-bad" == note


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------

def test_only_confirmed_links_are_written_by_default():
    assert len(plan_invokes_writes(_links(confirmed=True))) == 3
    assert plan_invokes_writes(_links(confirmed=False)) == []


def test_the_write_plan_is_deterministic_and_carries_provenance():
    first = plan_invokes_writes(_links())
    second = plan_invokes_writes(_links())
    assert first == second
    assert first[0]["proposed_by"] == "jvm-behaviour"
    assert first[0]["confirmed_by"] == "alice"
    assert first[0]["evidence"] == ["endpoint=/auth/login"]


def test_the_write_uses_merge_not_create():
    """A bare CREATE on a pre-computed identity is not safe against a
    driver-level transaction retry — a bug this codebase already fixed once."""
    from metis_mcp.mbt.cross_surface import INVOKES_CYPHER
    assert "MERGE" in INVOKES_CYPHER and "CREATE" not in INVOKES_CYPHER


def test_persist_calls_the_session_once_per_link():
    from metis_mcp.mbt.cross_surface import persist_invokes

    class FakeSession:
        def __init__(self):
            self.calls = []

        def run(self, cypher, **params):
            self.calls.append(params)

    session = FakeSession()
    written, unmatched = persist_invokes(session, _links())
    assert written == 3 and not unmatched
    assert len(session.calls) == 3
    assert {c["api_id"] for c in session.calls} == {"a-ok", "a-bad", "a-locked"}


# --------------------------------------------------------------------------
# M-5c : a UI model reads as ambiguous until the inherited guard is resolved
# --------------------------------------------------------------------------

def test_inherited_guards_are_exposed_for_validation():
    api = _api_model()
    guards = inherited_guards(api, _links())
    assert guards["u-ok"] == "credentials_valid"
    assert guards["u-bad"] == "NOT credentials_valid"


def test_an_unguarded_api_transition_contributes_nothing():
    api = _api_model()
    api.transitions["a-ok"] = Transition(id="a-ok", source="LoggedOut",
                                         trigger="POST /auth/login", target="LoggedIn")
    api.reindex()
    assert "u-ok" not in inherited_guards(api, _links())


def test_unconfirmed_links_do_not_supply_inherited_guards():
    """An unconfirmed proposal must not quietly make a model look well-formed."""
    assert inherited_guards(_api_model(), _links(confirmed=False)) == {}


def test_m5c_resolves_an_apparent_ambiguity_in_the_ui_model():
    """The real case, from records-spec: `GET /spec/{id}` returns 200 or 204, so
    the UI transition lands in Ready or Empty. The UI carries no guard by design
    (M-5c), so read alone it is ambiguous; read with the link it is determined."""
    from metis_mcp.mbt.validation import validate

    api = _api_model()
    ui = Model(
        id="login-ui",
        states={"LoginForm": State(id="LoginForm", name="LoginForm", surface="ui",
                                   is_initial=True),
                "Dashboard": State(id="Dashboard", name="Dashboard", surface="ui"),
                "ErrorShown": State(id="ErrorShown", name="ErrorShown", surface="ui")},
        transitions={
            "u-ok": Transition(id="u-ok", source="LoginForm", trigger="click_sign_in",
                               target="Dashboard"),
            "u-bad": Transition(id="u-bad", source="LoginForm", trigger="click_sign_in",
                                target="ErrorShown")})
    ui.reindex()

    assert len(validate(ui).blocking) == 1, "ambiguous read in isolation"
    guards = inherited_guards(api, _links())
    assert validate(ui, inherited=guards).blocking == [], "determined once resolved"


def test_the_finding_says_when_no_invokes_guards_were_supplied():
    """So a narrow answer is never mistaken for the wider one."""
    from metis_mcp.mbt.validation import validate
    ui = Model(
        id="x-ui",
        states={"A": State(id="A", name="A", surface="ui", is_initial=True),
                "B": State(id="B", name="B", surface="ui")},
        transitions={"t1": Transition(id="t1", source="A", trigger="go", target="B"),
                     "t2": Transition(id="t2", source="A", trigger="go", target="B")})
    ui.reindex()
    assert "M-5c" in validate(ui).blocking[0].detail
    assert "M-5c" not in validate(ui, inherited={}).blocking[0].detail


# --------------------------------------------------------------------------
# M-5f triage: "no UI calls it" is not "nothing calls it"
# --------------------------------------------------------------------------

def test_an_api_only_endpoint_with_a_feign_consumer_is_not_the_finding():
    api = _api_model()
    found = divergences(_ui_model(), api, _links())
    triaged = triage_api_only(found, api, {"/auth/login": "records-client"})
    assert len(triaged) == 1
    assert triaged[0].outcome == CONSUMED_ELSEWHERE
    assert not triaged[0].needs_attention


def test_an_api_only_endpoint_with_no_consumer_at_all_IS_the_finding():
    api = _api_model()
    found = divergences(_ui_model(), api, _links())
    triaged = triage_api_only(found, api, consumers={})
    assert triaged[0].outcome == NO_KNOWN_CONSUMER
    assert triaged[0].needs_attention


def test_triage_never_excuses_a_transition_from_direct_coverage():
    """C-4 holds regardless: no UI path can credit an API-only transition."""
    api = _api_model()
    triaged = triage_api_only(divergences(_ui_model(), api, _links()), api,
                              {"/auth/login": "some-feign"})
    assert "DIRECT coverage" in format_triage(triaged)
    assert "Triage changes who acts, not" in format_triage(triaged)


def test_the_service_prefix_is_tried_both_ways():
    """The gateway strips it, so a consumer may declare either form."""
    api = _api_model()
    found = divergences(_ui_model(), api, _links())
    assert triage_api_only(found, api, {"/login": "feign"})[0].outcome == CONSUMED_ELSEWHERE


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
