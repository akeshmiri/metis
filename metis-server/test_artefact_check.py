"""
The confirmation ladder for generated artefacts (`artefact_confirm`).

**What it defends.** "We generated it" and "we know it works" are different
claims. A curl that carries invented test data looks runnable and is wrong,
which is worse than a visible gap because nobody can tell by looking (X-6e).
"""
from __future__ import annotations

import json

import pytest

from metis_mcp import artefact_check as ac


def _tier(name):
    return type("E", (), {"tier": staticmethod(lambda: name)})


# ---------------------------------------------------------------------------
# shaped
# ---------------------------------------------------------------------------


def test_a_real_generated_curl_is_well_shaped():
    """Against what `recipe.as_curl` actually emits, not a hand-written sample —
    a check that only passes on invented input proves nothing."""
    from metis_mcp.rendering import recipe

    built = recipe.build(
        {"http_method": "POST", "path": "/record", "id": "ep:1",
         "content_type": "application/json"},
        base_url="",
        payload_types=({"type": "R", "fields": {
            "name": {"type": "java.lang.String", "expected_min_length": 3,
                     "expected_max_length": 40, "required": "true"}}},))
    assert ac.shape_of_curl(recipe.as_curl(built))["ok"]


def test_a_malformed_payload_is_caught_and_nothing_further_is_attempted():
    out = ac.confirm_curl("curl -X POST '{base}/r' -d '{not json}'")
    assert out["ok"] is False
    assert out["confirmed_to"] is None
    assert "not valid JSON" in out["stopped_because"]


def test_comment_lines_do_not_unbalance_the_quote_count():
    """`as_curl` appends `# ...` notes carrying the reasons, and those contain
    apostrophes. Counting them would refuse every real recipe."""
    command = ("curl -X GET '{base}/r'\n"
               "# base_url: a base URL lives in deployment config, not in a "
               "controller — it isn't recoverable")
    assert ac.shape_of_curl(command)["ok"], ac.shape_of_curl(command)


def test_the_shape_check_does_not_claim_the_target_accepts_it():
    assert "not that the target accepts it" in ac.shape_of_curl("curl -X GET 'x'")["means"]


# ---------------------------------------------------------------------------
# static — X-6e as a check
# ---------------------------------------------------------------------------


def test_invented_test_data_is_reported():
    violations = ac.x6e_violations(
        'curl -X POST \'{base}/r\' -d \'{"name": "test123"}\'')
    assert any(v["value"] == "test123" for v in violations)


def test_a_concrete_host_where_base_belongs_is_reported():
    """Métis does not know a hostname and must not invent one. A real host here
    came from somewhere it should not have."""
    violations = ac.x6e_violations("curl -X GET 'https://api.acme.internal/r'")
    assert any("acme.internal" in v["value"] for v in violations)


def test_a_documented_placeholder_host_is_not_a_violation():
    """`example.com` and `localhost` are conventional stand-ins. Flagging them
    would make the check fire on the very documents that teach the rule."""
    assert not [v for v in ac.x6e_violations("curl -X GET 'http://localhost:8080/r'")
                if "localhost" in v["value"]]


def test_a_properly_generated_artefact_is_clean():
    """The rule stated positively: placeholders describing the space pass."""
    command = ('curl -X POST \'{base}/record\' '
               '-d \'{"name": "<string, length 3..40, required>", '
               '"kind": "<draft|final>"}\'')
    assert ac.x6e_violations(command) == []


def test_an_enum_rendering_its_real_members_is_not_flagged():
    """`<draft|final>` are the actual allowed values. A heuristic broad enough
    to call those invented would fire on every correct enum, and a check people
    learn to ignore is worse than no check."""
    assert ac.x6e_violations('{"kind": "<draft|final>"}') == []


# ---------------------------------------------------------------------------
# executed — the tier is decided by the verb
# ---------------------------------------------------------------------------


def test_with_execution_off_the_call_is_checked_not_confirmed():
    out = ac.confirm_curl("curl -X GET '{base}/r'", execute=_tier("off"))
    assert out["confirmed_to"] == ac.STATIC
    assert "CHECKED, not confirmed" in out["stopped_because"]


def test_a_read_is_confirmable_at_observe_and_a_write_is_not():
    """`execution.py` separates `observe` from `run` because reading a replica
    is recoverable and making something happen is not. A GET is a read; a POST
    changes somebody else's system."""
    get = ac.confirm_curl("curl -X GET '{base}/r'", execute=_tier("observe"),
                          target="staging")
    post = ac.confirm_curl("curl -X POST '{base}/r' -d '{}'",
                           execute=_tier("observe"), target="staging")

    assert get["needs_tier"] == "observe"
    assert "permit sending this" in get["stopped_because"]
    assert post["needs_tier"] == "run"
    assert "needs `run`" in post["stopped_because"]


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_every_mutating_verb_needs_the_run_tier(method):
    out = ac.confirm_curl(f"curl -X {method} '{{base}}/r'", execute=_tier("off"))
    assert out["needs_tier"] == "run", method


def test_an_unrecoverable_verb_gets_the_stricter_tier():
    """**Not guessed into POST.** `recipe.build` writes `__unrecoverable__` when
    extraction could not recover the method, and inferring one from the presence
    of a body would turn "Métis does not know" into a confident answer that
    decides which tier the call needs."""
    out = ac.confirm_curl(
        "curl -X __unrecoverable__ '{base}/r' -d '{}'", execute=_tier("off"))
    assert out["method"] == "__unrecoverable__"
    assert out["needs_tier"] == "run"


def test_the_rung_never_exceeds_static_because_nothing_here_sends():
    """This module opens no HTTP connection and acquires none, however
    permissive the tier — and must not say it did."""
    for tier in ("observe", "run"):
        out = ac.confirm_curl("curl -X GET '{base}/r'", execute=_tier(tier),
                              target="staging")
        assert out["confirmed_to"] == ac.STATIC
        assert out["confirmed_to"] != ac.EXECUTED


def test_stopping_is_an_answer_rather_than_a_failure():
    out = ac.confirm_curl("curl -X GET '{base}/r'", execute=_tier("off"))
    assert out["ok"] is True


def test_there_is_no_planned_rung_and_the_answer_says_why():
    """SQL has EXPLAIN. There is no way to ask a server what a POST would do
    except by sending it, so naming a rung nothing climbs would be worse than
    having three."""
    assert "planned" not in ac.RUNGS
    out = ac.confirm_curl("curl -X GET '{base}/r'", execute=_tier("off"))
    assert "no `planned` rung" in out["means"]


# ---------------------------------------------------------------------------
# scaffold
# ---------------------------------------------------------------------------


def test_a_scaffold_has_no_rung_above_static_and_says_why():
    """It is consumed by a generator outside Métis. There is nothing here to
    execute — a fact about the artefact, not a limitation."""
    out = ac.confirm_scaffold(json.dumps({"operations": [{"id": "a"}]}))
    assert out["confirmed_to"] == ac.STATIC
    assert "nothing here to execute" in out["stopped_because"]
    assert out["rungs"]["shaped"]["operations"] == 1


def test_a_scaffold_that_is_not_json_stops_at_the_first_rung():
    out = ac.confirm_scaffold("{not json")
    assert out["ok"] is False
    assert out["confirmed_to"] is None


def test_a_scaffold_is_checked_for_x6e_too():
    out = ac.confirm_scaffold(json.dumps({"operations": [{"body": "test123"}]}))
    assert out["rungs"]["static"]["ok"] is False
