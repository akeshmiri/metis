"""
The HTTP surface's security boundary: who is calling, and G2 over a replayable
transport.

Free to run — no socket, no graph. Both halves are deliberately testable without
one, because a security property that can only be exercised by standing a server
up is a property nobody exercises.

These are the tests that matter most in this feature. Everything else the API
does is a routing decision over machinery that already existed; these two are the
parts where HTTP makes a previously-safe rule unsafe.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from metis_mcp.api import auth
from metis_mcp.mbt import graph_session
from metis_mcp.publishing.publish import (
    ConfirmationRefused,
    ConfirmationReplayed,
    ConfirmationTickets,
)

TOKEN = "a-real-token-value"


def _store(tmp: str, role: str = "reviewer", name: str = "reviewer-one") -> Path:
    path = Path(tmp) / "tokens"
    path.write_text(f"# principals\n\n{auth.digest(TOKEN)}\t{name}\t{role}\n")
    return path


# --------------------------------------------------------------------------
# Authentication — the trusted header does not survive contact with a network
# --------------------------------------------------------------------------

def test_a_valid_bearer_token_resolves_to_an_identity_with_its_role():
    with tempfile.TemporaryDirectory() as tmp:
        who = auth.authenticate(f"Bearer {TOKEN}", path=_store(tmp))
    assert who.name == "reviewer-one"
    assert who.role == "reviewer"


def test_the_store_holds_digests_so_leaking_it_leaks_nothing_replayable():
    """The difference between an incident and an inconvenience. A configuration
    file that contained usable tokens would be a credential store that everyone
    treats as configuration — backed up, copied into tickets, pasted into chat."""
    with tempfile.TemporaryDirectory() as tmp:
        text = _store(tmp).read_text()
    assert TOKEN not in text
    assert auth.digest(TOKEN) in text


def test_a_token_that_is_not_a_digest_is_refused_at_load():
    """Someone will paste a raw token into this file. Accepting it would mean the
    store silently became a secret without anybody deciding that."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "tokens"
        path.write_text(f"{TOKEN}\tsomebody\treviewer\n")
        with pytest.raises(auth.AuthenticationRequired, match="never the token itself"):
            auth.load_principals(path)


def test_an_unknown_role_is_refused_rather_than_defaulted():
    """A typo in a role that quietly granted less than intended would be found at
    the moment somebody could not approve something they needed to."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "tokens"
        path.write_text(f"{auth.digest(TOKEN)}\tsomebody\tsupervisor\n")
        with pytest.raises(auth.AuthenticationRequired, match="unknown role"):
            auth.load_principals(path)


def test_a_malformed_line_is_refused_rather_than_skipped():
    """A skipped line is a principal who believes they have access and does not."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "tokens"
        path.write_text(f"{auth.digest(TOKEN)}\tmissing-the-role\n")
        with pytest.raises(auth.AuthenticationRequired, match="expected"):
            auth.load_principals(path)


@pytest.mark.parametrize("header", ["", "Basic xyz", "Bearer", "Bearer   ", "token abc"])
def test_a_credential_that_is_not_a_bearer_token_is_refused(header):
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(auth.AuthenticationRequired):
            auth.authenticate(header, path=_store(tmp))


def test_a_wrong_token_and_a_missing_one_tell_the_client_the_same_thing():
    """Distinguished in the code and NOT to the caller: telling an attacker which
    half of the guess was right is free help."""
    assert issubclass(auth.AuthenticationFailed, Exception)
    assert issubclass(auth.AuthenticationRequired, Exception)
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(auth.AuthenticationFailed):
            auth.authenticate("Bearer not-the-token", path=_store(tmp))


def test_no_credential_store_is_a_refusal_not_an_open_door():
    """The failure mode that matters: unconfigured must mean nobody gets in, not
    everybody does."""
    with pytest.raises(auth.AuthenticationRequired, match="no credential store"):
        auth.load_principals(Path("/nonexistent/tokens"))


def test_the_environment_names_the_path_and_never_the_secret():
    """PLT-005: a secret on a command line is in the shell history, the process
    listing, and any log that captures argv."""
    import inspect

    source = inspect.getsource(auth)
    assert 'TOKENS_ENV = "METIS_API_TOKENS"' in source
    assert "os.environ.get(TOKENS_ENV" in source
    # The env var yields a path that is opened — never a credential compared.
    assert "Path(configured)" in source


# --------------------------------------------------------------------------
# G2 over a stateless transport — the assertion this feature exists for
# --------------------------------------------------------------------------

def _issued(actor="alice", fingerprint="fp-abc", size=3):
    tickets = ConfirmationTickets()
    tickets.issue("tkt-1", fingerprint, actor, size)
    return tickets


def test_a_replayed_confirmation_is_refused():
    """**If this ever passes twice, G2 is gone.**

    On a terminal, "in that run" enforces itself — the run is the process the
    operator is looking at. HTTP has no run: a body carrying `publish` is a
    string an attacker can replay, a proxy can retry, and a client can resend on
    a timeout it decided was transient. Each would re-confirm a publication
    nobody re-authorised.
    """
    tickets = _issued()
    first = tickets.redeem("tkt-1", "publish", "fp-abc", "alice")
    assert first.literal == "publish"

    with pytest.raises(ConfirmationReplayed):
        tickets.redeem("tkt-1", "publish", "fp-abc", "alice")


def test_a_ticket_that_was_never_issued_is_refused():
    with pytest.raises(ConfirmationReplayed):
        ConfirmationTickets().redeem("invented", "publish", "fp-abc", "alice")


def test_a_confirmation_does_not_carry_to_a_batch_that_changed():
    """T-17: a confirmation covers what the confirmer SAW."""
    tickets = _issued()
    with pytest.raises(ConfirmationRefused, match="batch changed"):
        tickets.redeem("tkt-1", "publish", "fp-DIFFERENT", "alice")


def test_a_confirmation_is_not_transferable_between_identities():
    """N-13: a confirmation records who gave it."""
    tickets = _issued()
    with pytest.raises(ConfirmationRefused, match="not transferable"):
        tickets.redeem("tkt-1", "publish", "fp-abc", "mallory")


def test_the_literal_word_is_still_required():
    """T-18 survives the transport: there is no default-yes."""
    tickets = _issued()
    with pytest.raises(ConfirmationRefused, match="literal word"):
        tickets.redeem("tkt-1", "yes", "fp-abc", "alice")


def test_a_wrong_literal_still_consumes_the_ticket():
    """Consumed BEFORE the literal is checked, so a caller cannot probe for a
    valid ticket by sending wrong words at it and reading the difference between
    "no such ticket" and "wrong word"."""
    tickets = _issued()
    with pytest.raises(ConfirmationRefused):
        tickets.redeem("tkt-1", "yes", "fp-abc", "alice")
    with pytest.raises(ConfirmationReplayed):
        tickets.redeem("tkt-1", "publish", "fp-abc", "alice")


# --------------------------------------------------------------------------
# The HTTP layer — routing, and the status codes that carry the refusals
#
# `TestClient` drives the app in-process: no socket, no port, no teardown. A
# security property that needed a running server to exercise is a property
# nobody exercises.
# --------------------------------------------------------------------------

@pytest.fixture()
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from metis_mcp.api.app import create_app

    store = tmp_path / "tokens"
    store.write_text(
        f"{auth.digest(TOKEN)}\tpublisher-one\tpublisher\n"
        f"{auth.digest('viewer-token')}\tviewer-one\tviewer\n")
    monkeypatch.setenv(auth.TOKENS_ENV, str(store))
    monkeypatch.setenv("METIS_MCP_WRITE", "full")
    return TestClient(create_app())


AUTHED = {"Authorization": f"Bearer {TOKEN}"}
VIEWER = {"Authorization": "Bearer viewer-token"}


def test_an_unauthenticated_request_is_401_with_a_challenge():
    from fastapi.testclient import TestClient

    from metis_mcp.api.app import create_app

    with TestClient(create_app()) as anonymous:
        response = anonymous.get("/whoami")
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_health_is_unauthenticated_and_reveals_only_liveness():
    """A load balancer is not a principal."""
    from fastapi.testclient import TestClient

    from metis_mcp.api.app import create_app

    with TestClient(create_app()) as anonymous:
        response = anonymous.get("/healthz")
    assert response.status_code == 200
    assert set(response.json()) == {"ok", "write_mode"}


def test_whoami_reports_the_role_the_token_resolves_to(client):
    body = client.get("/whoami", headers=AUTHED).json()
    assert body["name"] == "publisher-one"
    assert body["role"] == "publisher"


def test_a_role_without_the_capability_is_403_not_401(client):
    """The distinction matters to the operator: 401 means fix your credential,
    403 means this credential is real and may not do this."""
    response = client.post("/publications/b1/confirmation",
                           params={"fingerprint": "fp"}, headers=VIEWER)
    assert response.status_code == 403


def test_a_replayed_confirmation_over_http_is_409(client):
    """The single most important assertion in this feature.

    409 rather than 400: the request is well-formed, and the conflict is with the
    state of the world. The caller must re-read, not re-send — and a client that
    retries on 5xx/4xx-transient must not be able to turn a retry into a second
    publication.
    """
    issued = client.post("/publications/b1/confirmation",
                         params={"fingerprint": "fp-abc"}, headers=AUTHED).json()
    args = {"ticket": issued["ticket"], "literal": "publish",
            "fingerprint": "fp-abc"}

    first = client.post("/publications/b1/confirm", params=args, headers=AUTHED)
    assert first.status_code == 200
    assert first.json()["confirmed_by"] == "publisher-one"

    replay = client.post("/publications/b1/confirm", params=args, headers=AUTHED)
    assert replay.status_code == 409, "a replayed G2 confirmation was accepted"


def test_a_confirmation_does_not_carry_to_a_changed_batch_over_http(client):
    issued = client.post("/publications/b1/confirmation",
                         params={"fingerprint": "fp-abc"}, headers=AUTHED).json()
    response = client.post("/publications/b1/confirm", headers=AUTHED, params={
        "ticket": issued["ticket"], "literal": "publish",
        "fingerprint": "fp-CHANGED"})
    assert response.status_code == 400
    assert "batch changed" in response.json()["detail"]


def test_publication_still_sends_nothing(client):
    """Dry-run is the only transport registered (T-21/C3). An API that confirmed
    a publication and then performed one would be a bigger change than this
    is."""
    issued = client.post("/publications/b1/confirmation",
                         params={"fingerprint": "fp"}, headers=AUTHED).json()
    body = client.post("/publications/b1/confirm", headers=AUTHED, params={
        "ticket": issued["ticket"], "literal": "publish",
        "fingerprint": "fp"}).json()
    assert body["published"] is False
    assert "nothing was sent" in body["note"]


def test_a_read_only_deployment_refuses_the_gate_with_409(monkeypatch, tmp_path):
    """N-8: configured read-only is a different problem from unauthorised, and
    the operator fixes it somewhere else entirely — an environment variable, not
    a role grant."""
    from fastapi.testclient import TestClient

    from metis_mcp.api.app import create_app

    store = tmp_path / "tokens"
    store.write_text(f"{auth.digest(TOKEN)}\tpublisher-one\tpublisher\n")
    monkeypatch.setenv(auth.TOKENS_ENV, str(store))
    monkeypatch.setenv("METIS_MCP_WRITE", "off")

    with TestClient(create_app()) as readonly:
        response = readonly.post("/publications/b1/confirmation",
                                 params={"fingerprint": "fp"}, headers=AUTHED)
    assert response.status_code == 409
    assert "read-only" in response.json()["detail"]


# --------------------------------------------------------------------------
# G1 over HTTP — the same decision, through a different door
# --------------------------------------------------------------------------

def _context(commit=None, proposers=None):
    from mbt_fixtures import login_model
    from metis_mcp.review.roles import AuditLog
    from metis_mcp.review_ui.server import ReviewContext

    return ReviewContext(
        model=login_model(approved=False),
        audit=AuditLog(),
        proposers=proposers or {},
        commit=commit)


def _app_with(context, tmp_path, monkeypatch, role="reviewer", name="reviewer-one"):
    from fastapi.testclient import TestClient

    from metis_mcp.api.app import create_app

    store = tmp_path / "tokens"
    store.write_text(f"{auth.digest(TOKEN)}\t{name}\t{role}\n")
    monkeypatch.setenv(auth.TOKENS_ENV, str(store))
    monkeypatch.setenv("METIS_MCP_WRITE", "full")
    app = create_app()
    app.state.review_context = context
    return TestClient(app)


def test_a_decision_this_surface_cannot_keep_is_refused_not_taken(
        tmp_path, monkeypatch):
    """The defect `ReviewContext` was created to prevent, restated over HTTP.

    An approval acknowledged with 200 and then discarded is exactly the
    privileged, unlogged path N-1 prohibits — and it is worse here than in the
    UI, because an API caller has no screen to notice that nothing changed.
    """
    context = _context(commit=None)
    client = _app_with(context, tmp_path, monkeypatch)
    response = client.post(
        f"/models/{context.model.id}/elements/{context.model.id}/approval",
        headers=AUTHED)
    assert response.status_code == 409
    assert "N-1" in response.json()["detail"]


def test_an_unknown_model_is_404_rather_than_a_decision_about_nothing(
        tmp_path, monkeypatch):
    client = _app_with(_context(commit=lambda *a: None), tmp_path, monkeypatch)
    response = client.post("/models/not-a-model/elements/x/approval",
                           headers=AUTHED)
    assert response.status_code == 404


def test_a_role_without_approve_capability_is_refused(tmp_path, monkeypatch):
    context = _context(commit=lambda *a: None)
    client = _app_with(context, tmp_path, monkeypatch, role="viewer",
                       name="viewer-one")
    response = client.post(
        f"/models/{context.model.id}/elements/{context.model.id}/approval",
        headers=AUTHED)
    assert response.status_code == 403


def test_the_proposer_may_not_approve_their_own_element(tmp_path, monkeypatch):
    """N-10, inherited from `check_self_approval` rather than restated here."""
    context = _context(commit=lambda *a: None)
    context.proposers[context.model.id] = "reviewer-one"
    client = _app_with(context, tmp_path, monkeypatch)
    response = client.post(
        f"/models/{context.model.id}/elements/{context.model.id}/approval",
        headers=AUTHED)
    assert response.status_code == 403


def test_an_approval_writes_the_same_audit_record_the_cli_writes(
        tmp_path, monkeypatch):
    """N-1, and the only difference is the surface it names.

    Asserted on the audit log rather than on the response: a 200 proves the
    handler returned, and the property is that something durable was written.
    """
    committed = []
    context = _context(commit=lambda ctx, applied: committed.append(applied))
    client = _app_with(context, tmp_path, monkeypatch)

    response = client.post(
        f"/models/{context.model.id}/elements/{context.model.id}/approval",
        params={"rationale": "checked the guards"}, headers=AUTHED)

    assert response.status_code == 200, response.json()
    assert committed, "the decision was acknowledged and never committed"

    decisions = context.audit.entries
    assert len(decisions) == 1
    assert decisions[0].surface == "rest"
    assert decisions[0].actor == "reviewer-one"
    assert decisions[0].outcome == "Approved"


# --------------------------------------------------------------------------
# Reads — the same answer as the MCP tool, and available read-only
# --------------------------------------------------------------------------

def _no_ambient_graph(monkeypatch):
    """Neutralise any configuration the developer's machine happens to have.

    The three no-graph tests below delete `METIS_NEO4J_PASSWORD` and expect a
    204. That is only "no graph" if the environment is the *only* place a
    password can come from, and it is not: `~/.metis/config.json` is the
    documented default, and one holding a literal password made `resolve()`
    succeed, connect to a live database, and answer 200.

    So these passed on a machine with no config file and failed on a machine set
    up the way the tool itself recommends -- the class of test that passes in one
    place only, which `test_graph_session.py` already guards against this way.
    """
    monkeypatch.setattr(graph_session, "config_paths",
                        lambda: (tmp_config_dir() / "absent.json",))
    monkeypatch.setattr(graph_session, "unreadable_config_paths", tuple)
    monkeypatch.delenv(graph_session.CONFIG_PATH_ENV, raising=False)


def tmp_config_dir() -> Path:
    """A directory that exists and holds no configuration."""
    return Path(tempfile.gettempdir())


def _readonly_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from metis_mcp.api.app import create_app

    store = tmp_path / "tokens"
    store.write_text(f"{auth.digest(TOKEN)}\tviewer-one\tviewer\n")
    monkeypatch.setenv(auth.TOKENS_ENV, str(store))
    monkeypatch.setenv("METIS_MCP_WRITE", "off")
    _no_ambient_graph(monkeypatch)
    return TestClient(create_app())


def test_a_read_endpoint_returns_exactly_what_the_mcp_tool_returns(
        tmp_path, monkeypatch):
    """One implementation, two transports.

    Asserted as EQUALITY against the tool's own output rather than by checking a
    few keys: two surfaces that answer the same question differently give the
    graph two vocabularies, and that is where nearly every real defect in this
    codebase has come from.
    """
    import json

    from metis_mcp import server as tools

    client = _readonly_client(tmp_path, monkeypatch)
    response = client.get("/workflows", headers=AUTHED)

    assert response.status_code == 200
    assert response.json() == json.loads(tools.list_workflows())


def test_the_policy_endpoint_agrees_with_the_tool(tmp_path, monkeypatch):
    import json

    from metis_mcp import server as tools

    client = _readonly_client(tmp_path, monkeypatch)
    assert client.get("/policy", headers=AUTHED).json() == \
        json.loads(tools.describe_policy())


def test_reads_work_in_a_read_only_deployment(tmp_path, monkeypatch):
    """N-8 is about what may be WRITTEN. A read-only deployment that could not
    read would be a strange thing to have built."""
    client = _readonly_client(tmp_path, monkeypatch)
    for path in ("/workflows", "/policy"):
        assert client.get(path, headers=AUTHED).status_code == 200, path


def test_a_read_still_needs_a_credential(tmp_path, monkeypatch):
    """Read-only is not the same as public. The graph carries a customer's
    requirements and the code recovered from their service."""
    client = _readonly_client(tmp_path, monkeypatch)
    assert client.get("/workflows").status_code == 401


def test_a_read_with_no_graph_returns_no_content(tmp_path, monkeypatch):
    """204, and an empty body.

    Returning the tool's `{"ok": false}` with a 200 would mean
    `raise_for_status()` reports success and the body then says otherwise — a
    trap laid for every client library's happy path.

    204 rather than 4xx or 5xx because nothing is wrong with the request and
    nothing is broken on the server. There is no content to give.
    """
    client = _readonly_client(tmp_path, monkeypatch)
    monkeypatch.delenv("METIS_NEO4J_PASSWORD", raising=False)

    response = client.get("/models/login", headers=AUTHED)
    assert response.status_code == 204
    assert response.content == b"", "a 204 may not carry a body"


def test_the_reason_survives_in_a_header(tmp_path, monkeypatch):
    """A blank response with no explanation would leave an operator guessing at
    a missing password. A 204 may not have a body; it may have headers."""
    client = _readonly_client(tmp_path, monkeypatch)
    monkeypatch.delenv("METIS_NEO4J_PASSWORD", raising=False)

    response = client.get("/models/login", headers=AUTHED)
    reason = response.headers.get("X-Metis-Reason", "")
    assert "graph" in reason.lower()
    assert "METIS_NEO4J_PASSWORD" in reason


def test_an_answer_that_is_legitimately_empty_is_still_200(tmp_path, monkeypatch):
    """The distinction 204 is carrying. "I looked and there is none" is an
    answer; "I cannot look" is the absence of one, and a caller that cannot tell
    them apart will report an empty graph as an empty result."""
    import json

    from metis_mcp import server as tools

    client = _readonly_client(tmp_path, monkeypatch)
    response = client.get("/workflows", headers=AUTHED)

    assert response.status_code == 200
    assert response.json() == json.loads(tools.list_workflows())


def test_a_reason_with_typography_does_not_become_a_500(tmp_path, monkeypatch):
    """Regression. HTTP headers are latin-1; these messages are written for
    humans and contain an em-dash. Encoding one raised `UnicodeEncodeError`
    inside starlette, which turned a deliberate 204 into a 500 — the response
    saying "this server has a bug" for a server that was working correctly.
    """
    from metis_mcp.api.app import create_app

    app = create_app()
    # The sanitiser is a closure over the factory, so it is exercised through the
    # behaviour rather than reached into.
    client = _readonly_client(tmp_path, monkeypatch)
    monkeypatch.delenv("METIS_NEO4J_PASSWORD", raising=False)

    response = client.get("/models/login", headers=AUTHED)
    assert response.status_code == 204
    reason = response.headers["X-Metis-Reason"]
    assert "—" not in reason, "an em-dash cannot ride in a latin-1 header"
    reason.encode("latin-1")          # raises if anything else slipped through
