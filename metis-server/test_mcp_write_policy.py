"""
The write policy (spec N-1, N-9..N-15, O-4c; and the change to N-8).

`test_mcp_server.py` used to assert that no write path was reachable from the
agent surface. That rule is gone by an explicit product decision. **These tests
are what replaces it** — the invariants N-8 was protecting, each one now
checkable on its own:

    off by default              a surface nobody configured cannot write
    everything at Quarantine    authoring is not approving (S-4)
    a gate costs a literal      no default yes, no truthy value (G1/G2, T-18)
    every write is audited      through the same function every surface uses

Free to run: no Neo4j, no MCP client.
"""
import pytest

from metis_mcp import policy
from metis_mcp.policy import (
    APPROVE_LITERAL,
    ConfirmationRefused,
    WriteDisabled,
    authorise,
    mode,
    record,
    require_confirmation,
    resolve_identity,
)
from metis_mcp.review.roles import (
    APPROVE_MODEL,
    CONFIRM_PUBLICATION,
    NotPermitted,
    PROPOSE,
)
from metis_mcp.review.state import ReviewState


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(policy.WRITE_ENV, raising=False)
    monkeypatch.delenv(policy.IDENTITY_ENV, raising=False)


# --------------------------------------------------------------------------
# Mode
# --------------------------------------------------------------------------

def test_the_default_is_read_only():
    """A surface that starts writable is one nobody chose to make writable."""
    assert mode() == policy.OFF
    assert not policy.may_author() and not policy.may_decide()


def test_an_unknown_mode_halts_rather_than_defaulting_to_off(monkeypatch):
    """`METIS_MCP_WRITE=ful` must not silently refuse every write in silence."""
    monkeypatch.setenv(policy.WRITE_ENV, "ful")
    with pytest.raises(WriteDisabled) as e:
        mode()
    assert "ful" in str(e.value)


def test_author_mode_may_land_but_may_not_decide(monkeypatch):
    monkeypatch.setenv(policy.WRITE_ENV, policy.AUTHOR)
    assert authorise(PROPOSE, "alex", "contributor").mode == policy.AUTHOR
    with pytest.raises(WriteDisabled) as e:
        authorise(APPROVE_MODEL, "sam", "reviewer")
    assert "gate" in str(e.value)


def test_read_only_mode_refuses_even_a_permitted_role(monkeypatch):
    """Configuration is checked before capability: they are different problems."""
    monkeypatch.setenv(policy.WRITE_ENV, policy.OFF)
    with pytest.raises(WriteDisabled) as e:
        authorise(PROPOSE, "sam", "admin")
    assert policy.WRITE_ENV in str(e.value)


def _verified(name: str, role: str):
    """What an authenticated surface hands to `authorise`.

    Since W1, `full` will not accept a name the caller merely asserted: deciding
    costs a verified identity, because an agent that can name itself can name
    somebody else, and every audit record would then say whoever the caller
    claimed to be. The HTTP app checks its bearer header and passes the
    `Identity`; an MCP deployment sets `METIS_MCP_TOKEN`.
    """
    from metis_mcp.review.roles import Identity

    return Identity(name=name, role=role)


def test_full_mode_permits_a_gate(monkeypatch):
    monkeypatch.setenv(policy.WRITE_ENV, policy.FULL)
    grant = authorise(APPROVE_MODEL, "sam", "reviewer",
                      verified=_verified("sam", "reviewer"))
    assert grant.identity.name == "sam"


# --------------------------------------------------------------------------
# Identity (N-13, O-4c)
# --------------------------------------------------------------------------

def test_there_is_no_anonymous_write(monkeypatch):
    monkeypatch.setenv(policy.WRITE_ENV, policy.AUTHOR)
    with pytest.raises(NotPermitted) as e:
        authorise(PROPOSE)
    assert policy.IDENTITY_ENV in str(e.value)


def test_identity_can_come_from_the_environment(monkeypatch):
    monkeypatch.setenv(policy.IDENTITY_ENV, "robin:reviewer")
    identity = resolve_identity()
    assert (identity.name, identity.role) == ("robin", "reviewer")


def test_an_explicit_actor_beats_the_environment(monkeypatch):
    monkeypatch.setenv(policy.IDENTITY_ENV, "robin:reviewer")
    assert resolve_identity("sam", "admin").name == "sam"


def test_a_role_that_lacks_the_capability_is_told_who_may(monkeypatch):
    monkeypatch.setenv(policy.WRITE_ENV, policy.FULL)
    with pytest.raises(NotPermitted) as e:
        authorise(CONFIRM_PUBLICATION, "kim", "contributor",
                  verified=_verified("kim", "contributor"))
    assert "publisher" in str(e.value)


# --------------------------------------------------------------------------
# The gate literal (G1/G2, T-18)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("given", ["", "y", "yes", "YES", "Approve", "true", "1",
                                   "publish"])
def test_only_the_exact_word_confirms(given):
    """`publish` is refused for G1 on purpose: one gate's word is not the other's."""
    with pytest.raises(ConfirmationRefused):
        require_confirmation(given, APPROVE_LITERAL, "approval")


def test_a_truthy_value_is_not_a_confirmation():
    with pytest.raises(ConfirmationRefused):
        require_confirmation(True, APPROVE_LITERAL, "approval")


def test_the_exact_word_passes():
    require_confirmation(APPROVE_LITERAL, APPROVE_LITERAL, "approval")


# --------------------------------------------------------------------------
# Audit (N-1, N-15)
# --------------------------------------------------------------------------

def test_a_write_is_recorded_with_the_mcp_surface(monkeypatch):
    monkeypatch.setenv(policy.WRITE_ENV, policy.AUTHOR)
    grant = authorise(PROPOSE, "alex", "contributor")
    state = ReviewState(model_id="records-api")

    entry = record(grant, state, "records-api::t1", "landed",
                   evidence={"states": 3}, fingerprint="abc123",
                   rationale="from the jvm-behaviour pack")

    assert state.audit == [entry]
    assert entry["surface"] == "mcp"
    assert entry["actor"] == "alex" and entry["capability"] == PROPOSE
    assert entry["evidence_fingerprint"] == "abc123"


def test_the_audit_is_append_only(monkeypatch):
    monkeypatch.setenv(policy.WRITE_ENV, policy.AUTHOR)
    grant = authorise(PROPOSE, "alex", "contributor")
    state = ReviewState(model_id="records-api")
    for i in range(3):
        record(grant, state, f"records-api::t{i}", "landed", evidence={})
    assert len(state.audit) == 3
    assert [e["element_id"] for e in state.audit] == [
        "records-api::t0", "records-api::t1", "records-api::t2"]


def test_the_audit_survives_a_round_trip_to_disk(tmp_path, monkeypatch):
    """An in-memory log nothing saves is what `cli ui` shipped with once."""
    monkeypatch.setenv(policy.WRITE_ENV, policy.AUTHOR)
    grant = authorise(PROPOSE, "alex", "contributor")
    state = ReviewState(model_id="records-api")
    record(grant, state, "records-api::t1", "landed", evidence={"n": 1})

    path = tmp_path / "records-api.review.json"
    state.save(path)
    assert ReviewState.load(path).audit[0]["surface"] == "mcp"


def test_describe_names_the_trust_it_places_in_the_caller(monkeypatch):
    monkeypatch.setenv(policy.WRITE_ENV, policy.FULL)
    described = policy.describe()
    assert described["mode"] == policy.FULL
    assert "Quarantine" in described["everything_lands_at"]
    # The key reports what IS. With no credential configured the surface still
    # trusts the caller, and says so; W1 added the other branch rather than
    # replacing this one, because most localhost deployments never set a token.
    assert "asserted" in described["identity"]
    assert "trusted" in described["identity"]
    assert "unacceptable" in described["identity"]
    assert set(described["gates"]) == {"G1", "G2"}


# --------------------------------------------------------------------------
# Autopilot containment: what an agent must not be able to do at all
# --------------------------------------------------------------------------

def test_the_agent_surface_exposes_no_way_to_publish():
    """**Nothing outside Métis may be written from an agent session.**

    G2's literal is a string, and an agent can supply `publish` as easily as a
    person can — T-18 was written against a human forgetting to confirm, not
    against a caller confirming on the human's behalf. So publication is not
    reachable here at all: the containment is the absence of the tool, not a
    check inside one.

    Asserted over the registered names rather than by reading intent, and over
    `full` mode, which is the most permissive this surface has.
    """
    import os
    import subprocess
    import sys

    program = ("import importlib;"
               "print(','.join(sorted(importlib.import_module"
               "('metis_mcp.server')._WRITE_TOOLS)))")
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True,
        env={**os.environ, "METIS_MCP_WRITE": "full"})
    assert result.returncode == 0, result.stderr
    registered = [t for t in result.stdout.strip().split(",") if t]

    forbidden = [t for t in registered
                 if any(word in t for word in ("publish", "export_to", "send",
                                               "upload", "sync"))]
    assert not forbidden, (
        f"the agent surface can reach an external write: {forbidden}. "
        f"Publication goes through the CLI, where a person is driving.")


def test_no_agent_tool_accepts_a_gate_literal():
    """`resume_workflow` used to take `confirm`, so an agent could have handed
    G2 its own `publish`.

    Checked on the SIGNATURES, because that is where the hole was: the tool did
    not publish, it forwarded a literal to a workflow stage that did.
    """
    import inspect

    from metis_mcp import decide, flow, write

    for module, allowed in ((flow, set()), (write, set()),
                            (decide, {"approve_elements"})):
        for name, fn in vars(module).items():
            if name.startswith("_") or not inspect.isfunction(fn):
                continue
            if name in allowed:
                continue  # G1 is a Métis-internal decision, not an external write
            params = inspect.signature(fn).parameters
            assert "confirm" not in params, (
                f"{module.__name__}.{name} accepts a gate literal; an agent "
                f"could supply it")


def test_g1s_literal_is_not_g2s():
    """The one confirmation an agent may pass is G1's, which promotes inside
    Métis and sends nothing. Sharing a word between the two gates would let a
    confirmation typed for one satisfy the other."""
    from metis_mcp.policy import APPROVE_LITERAL
    from metis_mcp.publishing.publish import AFFIRMATIVE

    assert APPROVE_LITERAL != AFFIRMATIVE


# --------------------------------------------------------------------------
# W1: the identity is verified, not asserted.
#
# `describe_policy` has always admitted that `actor` and `role` were "taken from
# the caller and trusted ... honest for a localhost tool; unacceptable for
# anything reachable by others". `api/auth.py` names the consequence exactly: a
# trusted name "is an impersonation hole leading directly into G1 and G2, and
# every audit record it produces is a record of whoever the caller said they
# were." These assert the hole is closed, not merely documented.
# --------------------------------------------------------------------------

import hashlib as _hashlib


@pytest.fixture
def credential(tmp_path, monkeypatch):
    """A real store with one principal, `dana` the reviewer."""
    token = "s3cret-token-value"
    store = tmp_path / "principals.tsv"
    digest = _hashlib.sha256(token.encode()).hexdigest()
    store.write_text(f"{digest}\tdana\treviewer\n")
    monkeypatch.setenv("METIS_API_TOKENS", str(store))
    monkeypatch.setenv(policy.TOKEN_ENV, token)
    return token


def test_a_credential_decides_who_is_acting(monkeypatch, credential):
    monkeypatch.setenv(policy.WRITE_ENV, policy.FULL)
    assert policy.resolve_identity().name == "dana"


def test_naming_somebody_else_is_refused_not_silently_overridden(monkeypatch,
                                                                credential):
    """**The test W1 exists for.** Preferring the credential quietly would be
    safe and would teach a caller nothing; an impersonation attempt is answered
    as one."""
    monkeypatch.setenv(policy.WRITE_ENV, policy.FULL)
    with pytest.raises(NotPermitted) as e:
        policy.resolve_identity(actor="somebody-else", role="reviewer")
    assert "somebody-else" in str(e.value) and "dana" in str(e.value)


def test_claiming_a_role_the_store_did_not_grant_is_refused(monkeypatch,
                                                            credential):
    """Escalation is the same hole in a different direction: the store says
    reviewer, so `admin` cannot come from the caller (N-1)."""
    monkeypatch.setenv(policy.WRITE_ENV, policy.FULL)
    with pytest.raises(NotPermitted) as e:
        policy.resolve_identity(actor="dana", role="admin")
    assert "reviewer" in str(e.value)


def test_deciding_without_a_credential_is_refused(monkeypatch):
    """At `full` an asserted name is not enough. Authoring lands at Quarantine
    and is reversible; a gate is neither (N-10)."""
    monkeypatch.delenv(policy.TOKEN_ENV, raising=False)
    monkeypatch.setenv(policy.WRITE_ENV, policy.FULL)
    with pytest.raises(NotPermitted) as e:
        policy.resolve_identity(actor="sam", role="reviewer")
    assert policy.TOKEN_ENV in str(e.value)


def test_authoring_without_a_credential_still_works(monkeypatch):
    """W1 must not break the localhost author case it was never about."""
    monkeypatch.delenv(policy.TOKEN_ENV, raising=False)
    monkeypatch.setenv(policy.WRITE_ENV, policy.AUTHOR)
    assert policy.resolve_identity(actor="sam", role="contributor").name == "sam"


def test_a_bad_token_is_refused_rather_than_falling_back_to_assertion(
        monkeypatch, tmp_path):
    """Fail closed. Falling back to the asserted name on a bad credential would
    make the credential optional in the only case it matters."""
    from metis_mcp.api.auth import AuthenticationFailed

    store = tmp_path / "principals.tsv"
    store.write_text(f"{_hashlib.sha256(b'other').hexdigest()}\tdana\treviewer\n")
    monkeypatch.setenv("METIS_API_TOKENS", str(store))
    monkeypatch.setenv(policy.TOKEN_ENV, "not-the-right-token")
    monkeypatch.setenv(policy.WRITE_ENV, policy.AUTHOR)
    with pytest.raises(AuthenticationFailed):
        policy.resolve_identity(actor="sam", role="contributor")


# --------------------------------------------------------------------------
# The two CLI-only capabilities that were CLI-only by accident.
#
# `persist_version` closes a loop that was broken: `coverage` and
# `coverage_report` report "not recorded (P-16)" and tell the reader to run
# `metis persist`, which was the one instruction the MCP surface could not act
# on — an agent following its own tool's advice hit a wall.
#
# `publication_drift` is behind the write switch although it only reads, because
# `PublicationLedger` lives in a WRITE_PATH. Read-tier would break N-8's proof.
# --------------------------------------------------------------------------

def test_both_new_tools_are_registered_at_the_author_tier(monkeypatch):
    import pathlib
    import subprocess
    import sys

    probe = ("import os; os.environ['METIS_MCP_WRITE']='author'\n"
             "from metis_mcp import server; print(','.join(server._WRITE_TOOLS))\n")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True, cwd=pathlib.Path(__file__).parent)
    assert "persist_version" in out.stdout
    assert "publication_drift" in out.stdout


def test_neither_is_reachable_at_the_default_tier():
    """They are writes (one nominally), and `off` must stay the read-only
    surface it has always been."""
    import pathlib
    import subprocess
    import sys

    probe = ("import os; os.environ.pop('METIS_MCP_WRITE', None)\n"
             "from metis_mcp import server; print(','.join(server._WRITE_TOOLS))\n")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True, cwd=pathlib.Path(__file__).parent)
    assert out.stdout.strip() == ""


def test_drift_says_when_it_cannot_see_published_content(monkeypatch, tmp_path):
    """**The field that stops a zero being misread.** MANUALLY_EDITED and
    OBSOLETE read zero whenever nothing was recorded as sent, and that means
    "cannot tell", not "no drift"."""
    from metis_mcp import write
    from metis_mcp.mbt.model import Model, State, Transition
    from metis_mcp.publishing import PublicationLedger

    model = Model(id="mfa-api",
                  states={"s1": State(id="s1", name="Ready", is_initial=True),
                          "s2": State(id="s2", name="Done")},
                  transitions={"t1": Transition(id="t1", source="s1",
                                                target="s2",
                                                trigger="POST /mfa")})

    class _Report:
        found, skipped, invokes = True, [], {}

        def __init__(self, m):
            self.model = m

    monkeypatch.setattr("metis_mcp.mbt.graph_loader.load_from_graph",
                        lambda s, j, sf: _Report(model))
    monkeypatch.setattr("metis_mcp.mbt.graph_session.session",
                        lambda *a, **k: __import__("contextlib").nullcontext(None))
    monkeypatch.setattr("metis_mcp.publishing.default_ledger_path",
                        lambda mid: str(tmp_path / "ledger.json"))
    monkeypatch.setenv(policy.WRITE_ENV, policy.AUTHOR)
    monkeypatch.delenv(policy.TOKEN_ENV, raising=False)
    monkeypatch.setenv("METIS_AUDIT_DIR", str(tmp_path / "audit"))

    out = write.publication_drift(journey="mfa", actor="dana",
                                  role="contributor")
    assert out["ok"] is True
    assert out["published_content_visible"].startswith("no —"), \
        out["published_content_visible"]
    assert "cannot tell" in out["published_content_visible"]


# --------------------------------------------------------------------------
# `duplicate_check` rides with `publication_drift`, for the same structural
# reason: it reads `PublicationLedger`, which lives in a WRITE_PATH, so a
# read-tier registration would put a write path on the read surface and turn
# N-8's "no write path is reachable" proof into a policy check.
# --------------------------------------------------------------------------

def test_duplicate_check_is_at_the_author_tier_and_not_below():
    import pathlib
    import subprocess
    import sys

    here = pathlib.Path(__file__).parent

    def registered(tier):
        setup = (f"import os; os.environ['METIS_MCP_WRITE']={tier!r}\n"
                 if tier else
                 "import os; os.environ.pop('METIS_MCP_WRITE', None)\n")
        out = subprocess.run(
            [sys.executable, "-c",
             setup + "from metis_mcp import server\n"
                     "print(','.join(server._WRITE_TOOLS))\n"],
            capture_output=True, text=True, cwd=here)
        return out.stdout

    assert "duplicate_check" in registered("author")
    assert "duplicate_check" not in registered(None), (
        "a write path became reachable at the default tier")


def test_the_read_surface_never_imports_the_duplicate_module():
    """The construction, not the policy. `publishing` is a WRITE_PATH and this
    module lives inside it, so `off` must not load it."""
    import pathlib
    import subprocess
    import sys

    probe = ("import os, sys; os.environ.pop('METIS_MCP_WRITE', None)\n"
             "import metis_mcp.server\n"
             "print('metis_mcp.publishing.duplicates' in sys.modules)\n")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True, cwd=pathlib.Path(__file__).parent)
    assert out.stdout.strip() == "False", out.stdout + out.stderr
