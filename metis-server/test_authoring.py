"""
The authoring surface (spec §7.4b, X-6e).

Free to run: the graph is stubbed at `_rows`, which is the one function that
opens a session. What is asserted is the routing and the composition rule — the
two parts where a wrong answer would be fluent and confident.
"""
from __future__ import annotations

import pytest

from metis_mcp import authoring as A


@pytest.fixture
def graph(monkeypatch):
    """A minimal service: one endpoint, two headers, no declared security."""
    def rows(cypher: str, **params):
        if "security_schemes IS NOT NULL" in cypher:
            return []
        if "location:'header'" in cypher:
            return [{"name": "userId", "endpoints": 6, "required": True},
                    {"name": "mfaSessionId", "endpoints": 5, "required": True}]
        if "count(e) AS n" in cypher:
            return [{"n": 12}]
        if "is_initial" in cypher:
            return [{"name": "Ready"}]
        if "THEN]->(tgt" in cypher:
            return [{"trigger": "POST /challenge", "status": "200",
                     "guard": "", "from_state": "Ready", "to_state": "Ok200",
                     "causes": []},
                    {"trigger": "POST /challenge", "status": "400",
                     "guard": "NOT (accepted)", "from_state": "Ready",
                     "to_state": "Rejected400", "causes": ["BadThing"]}]
        return []
    monkeypatch.setattr(A, "_rows", rows)


# --------------------------------------------------------------------------
# Routing — and refusing to route
# --------------------------------------------------------------------------

@pytest.mark.parametrize("question,tool", [
    ("how should I pass MFA Auth", "auth_facts"),
    ("what token do I need", "auth_facts"),
    ("give me a curl for the challenge endpoint", "call_recipe"),
    ("what body does this endpoint want", "call_recipe"),
    ("how does MFA work", "journey_walkthrough"),
    ("explain the flow", "journey_walkthrough"),
])
def test_a_question_routes_to_the_tool_that_can_answer_it(graph, question, tool):
    assert A.ask(question, journey="mfa")["answered_by"] == tool


def test_a_question_no_tool_answers_is_refused_not_guessed(graph):
    """**The whole difference between this and guessing.** Métis can say how to
    call an endpoint and how a journey moves; it cannot say why a decision was
    taken, and answering from general knowledge is the failure this surface
    exists to avoid."""
    out = A.ask("why was this designed the way it is")
    assert out["ok"] is False
    assert "cannot answer from anything but the graph" in out["reason"]
    assert "answer" not in out, "nothing was produced"


@pytest.mark.parametrize("question,kind", [
    ("what happens when the token expires", "expiry and lifetime"),
    ("how long does a challenge last", "duration"),
    ("is this endpoint slow", "latency"),
    ("who owns this service and when was it last deployed", "deployment"),
])
def test_a_kind_of_fact_metis_does_not_hold_is_named(graph, question, kind):
    """**Checked before routing, and that ordering is the fix.**

    "What happens when the token expires" matches *token*, routes to
    `auth_facts`, and comes back with a confident list of headers — a different
    question, fluently answered wrong. The model is a state machine recovered
    from source: expiry, timing, retry, latency and ownership are categories it
    holds no facts about at all, so no amount of better routing helps and saying
    so IS the answer.
    """
    out = A.ask(question, journey="mfa")
    assert out["ok"] is False
    assert out["out_of_scope"] == kind
    assert "answer" not in out, "no tool was consulted"
    assert "behaves over time" in out["reason"] or kind in out["reason"]


def test_an_in_scope_question_is_not_swallowed_by_the_scope_check(graph):
    """The check must not become a refusal machine: everything Métis genuinely
    answers still routes."""
    for question in ("how should I pass MFA Auth", "how does MFA work",
                     "give me a curl for the challenge endpoint"):
        assert A.ask(question, journey="mfa").get("answered_by"), question


def test_the_refusal_names_what_can_be_answered(graph):
    out = A.ask("what is the meaning of this")
    assert set(out["tools"]) == {"call_recipe", "auth_facts", "payload_shape",
                                 "journey_walkthrough"}


# --------------------------------------------------------------------------
# `ask` composes; it does not narrate
# --------------------------------------------------------------------------

def test_ask_states_nothing_the_tool_did_not(graph, monkeypatch):
    """T-6, applied to the answering surface. Every string `ask` returns is
    either the tool's own output or a fixed frame — never a sentence about the
    system that the tool did not produce."""
    sentinel = {"ok": True, "declared_security": [], "required_headers": [],
                "endpoints": 0, "caveat": "CAVEAT-TEXT",
                "how_to_read_this": "READ-TEXT"}
    monkeypatch.setattr(A, "auth_facts", lambda journey: sentinel)

    out = A.ask("how do I authenticate", journey="mfa")
    assert out["answer"] is sentinel, "the tool's output, unmodified"

    frame = {out["question"], out["answered_by"], out["rule"]}
    strings = {v for v in out.values() if isinstance(v, str)}
    assert strings <= frame, f"ask added prose of its own: {strings - frame}"


def test_ask_says_where_every_claim_came_from(graph):
    out = A.ask("how should I pass MFA Auth", journey="mfa")
    assert out["answered_by"] == "auth_facts"
    assert "came from the graph" in out["rule"]


# --------------------------------------------------------------------------
# The auth answer, which is the one most likely to be read as a guarantee
# --------------------------------------------------------------------------

def test_no_declared_security_is_never_reported_as_open(graph):
    """A filter chain or a gateway enforces authentication invisibly to
    extraction. "Nothing declared" is the only claim available, and the answer
    has to carry that or a reader takes silence for a finding."""
    out = A.auth_facts("mfa")
    assert out["declared_security"] == []
    assert "not the same as open" in out["caveat"]


def test_the_headers_are_offered_as_a_likelihood_not_a_fact(graph):
    """On a real service the auth travels as ordinary header parameters, and
    saying so is useful — but extraction cannot confirm anything checks them."""
    out = A.auth_facts("mfa")
    assert [h["name"] for h in out["required_headers"]] == ["userId", "mfaSessionId"]
    assert "cannot confirm" in out["how_to_read_this"]


# --------------------------------------------------------------------------
# The walkthrough
# --------------------------------------------------------------------------

def test_a_walkthrough_separates_the_rejections(graph):
    out = A.journey_walkthrough("mfa")
    assert len(out["transitions"]) == 2
    assert [t["status"] for t in out["rejections"]] == ["400"]


def test_a_walkthrough_states_that_none_of_it_is_approved(graph):
    """Everything recovered lands at Quarantine (S-4), so a walkthrough that read
    as settled fact would misrepresent it."""
    assert "none of it is approved" in A.journey_walkthrough("mfa")["means"]


def test_an_unknown_journey_is_reported(graph, monkeypatch):
    monkeypatch.setattr(A, "_rows", lambda *a, **k: [])
    out = A.journey_walkthrough("nope")
    assert out["ok"] is False and "nope" in out["reason"]
