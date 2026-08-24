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


def test_full_mode_permits_a_gate(monkeypatch):
    monkeypatch.setenv(policy.WRITE_ENV, policy.FULL)
    assert authorise(APPROVE_MODEL, "sam", "reviewer").identity.name == "sam"


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
        authorise(CONFIRM_PUBLICATION, "kim", "contributor")
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
    assert "trusted" in described["identity_is_asserted_not_authenticated"]
    assert "unacceptable" in described["identity_is_asserted_not_authenticated"]
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
