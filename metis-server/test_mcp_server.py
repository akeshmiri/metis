"""
The agent / MCP surface (application spec §9.5, N-8).

`server.py`'s own docstring has always said "`test_mcp_server.py` asserts that
no write-path module is reachable from this one." No such file existed, and
nothing tested the surface at all — the guarantee the module claims to enforce
structurally was enforced by nobody.

The read-only property is the one that matters. A tool that approves a model
from a chat session produces exactly the artefact the two human gates exist to
prevent, and it looks like helpfulness while doing it.
"""
import ast
import json
import os
import pathlib

import pytest

from metis_mcp import server
from metis_mcp.mbt.cli import read_source

SERVER = pathlib.Path(server.__file__)

# The three modules that can change the world. None may be reachable from the
# agent surface, at import time or inside a function body.
WRITE_PATHS = (
    "metis_mcp.review.decisions",
    "metis_mcp.publishing",
    "metis_mcp.model_sources.landing",
    "metis_mcp.mbt.graph_writer",
    "metis_mcp.mbt.finding_writer",
)


def _imported_modules(path: pathlib.Path) -> set[str]:
    """Every module named by an import anywhere in the file.

    Walks the AST rather than the module's `__dict__`, because the tools import
    lazily inside their own bodies — a check on module-level imports alone would
    pass while a write path sat inside a function.
    """
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


# --------------------------------------------------------------------------
# N-8 : read-only by construction, not by discipline
# --------------------------------------------------------------------------

def test_no_write_path_is_reachable_from_the_agent_surface():
    imported = _imported_modules(SERVER)
    for write_path in WRITE_PATHS:
        assert not any(m == write_path or m.startswith(write_path + ".")
                       for m in imported), (
            f"{write_path} is imported by the MCP surface — N-8 says no decision "
            f"may be taken through it"
        )


def test_no_tool_name_suggests_a_decision():
    """A read-only surface should not offer a verb that sounds like a gate."""
    forbidden = ("approve", "reject", "publish", "land", "persist", "apply",
                 "decide", "write")
    tree = ast.parse(SERVER.read_text())
    names = [n.name for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef)
             and any(getattr(d, "attr", "") == "tool"
                     for d in n.decorator_list if isinstance(d, ast.Attribute))
             or (isinstance(n, ast.FunctionDef)
                 and any(isinstance(d, ast.Call)
                         and getattr(d.func, "attr", "") == "tool"
                         for d in n.decorator_list))]
    assert names, "no tools were discovered — the parser missed the decorator"
    for name in names:
        assert not any(word in name for word in forbidden), (
            f"tool {name!r} names an action the surface must not perform"
        )


def test_why_read_only_states_the_rule_and_where_decisions_go():
    payload = json.loads(server.why_read_only())
    assert payload["rule"] == "N-8"
    assert payload["where_decisions_are_taken"]
    assert set(payload["gates"]) == {"G1", "G2"}


# --------------------------------------------------------------------------
# Serialisation: compact, pruned, and honest about the pruning
# --------------------------------------------------------------------------

def test_responses_carry_no_indentation():
    """`indent=2` was 27% of every response, spent on whitespace for a reader
    that does not need it."""
    assert "\n" not in server.why_read_only()
    assert "  " not in server.list_workflows()


def test_null_empty_and_false_fields_are_dropped():
    pruned = server._prune(
        {"keep": "yes", "n": 0, "null": None, "blank": "", "empty": [],
         "false": False, "nested": {"gone": None, "stays": 1}})
    assert pruned == {"keep": "yes", "n": 0, "nested": {"stays": 1}}


def test_zero_is_not_dropped():
    """A count of zero is a fact. Dropping it would make "none covered" and
    "not measured" the same response."""
    assert server._prune({"covered": 0}) == {"covered": 0}


@pytest.mark.parametrize("tool", [server.get_model, server.coverage])
def test_summarising_tools_declare_that_detail_exists(tool):
    """A summary that does not say it is a summary reads as the whole answer."""
    assert "detail" in tool.__doc__


def test_every_tool_description_stays_lean():
    """Tool descriptions are loaded into every request. `coverage` carried a
    paragraph of repo history — true, and not actionable by a caller."""
    tree = ast.parse(SERVER.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not any(isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool"
                   for d in node.decorator_list):
            continue
        doc = ast.get_docstring(node) or ""
        assert len(doc) < 900, (
            f"{node.name}'s description is {len(doc)} chars and is loaded on "
            f"every request — move the history to a comment"
        )


# --------------------------------------------------------------------------
# The summary is orientation, not the payload wearing a summary's name
# --------------------------------------------------------------------------

def test_the_summary_does_not_carry_the_transition_ids():
    """On a recovered model an id is a fully-qualified method signature: 46 of
    them were 7,397 of an 8,405-character "summary"."""
    source = SERVER.read_text()
    summary_block = source.split("if not detail:")[1].split("payload[\"transitions\"]")[0]
    assert "transition_ids" not in summary_block


def test_pruning_a_real_model_payload_is_a_large_saving():
    model = read_source("demo_data/models/records-api.json")
    payload = {
        "ok": True, "model_id": model.id,
        "transitions": [
            {"id": t.id, "guard": t.guard, "inputs": list(t.inputs),
             "security": list(t.security),
             "source_state_unresolved": t.source_state_unresolved}
            for t in model.transitions.values()
        ],
    }
    before = json.dumps(payload, indent=2)
    after = server._json(payload)
    assert len(after) < len(before) * 0.75, (
        f"expected a substantial saving, got {100 - 100 * len(after) / len(before):.0f}%"
    )


def test_a_missing_graph_is_reported_as_a_reason_not_an_empty_result():
    """"Nothing found" and "could not look" are different answers with different
    consequences.

    Asserted on the **serialised bytes**, not on the dict. This test used to
    check `_NOT_CONFIGURED["ok"]` and passed while every refusal went out
    without its `ok` field at all: `_prune` drops False, and `ok: false` is what
    a refusal is. Checking the source of a value rather than what a caller
    receives is how a wire-format bug hides behind a green test.
    """
    payload = json.loads(server._json(server._NOT_CONFIGURED))
    assert payload["ok"] is False
    assert "METIS_NEO4J_PASSWORD" in payload["reason"]
    assert "PLT-005" in payload["reason"]


def test_the_status_field_survives_pruning_in_every_refusal():
    """`ok` is the one field a refusal cannot afford to lose."""
    for refusal in ({"ok": False, "reason": "no"},
                    {"ok": False}, server._NOT_CONFIGURED):
        assert json.loads(server._json(refusal))["ok"] is False
    # And a genuinely uninformative False elsewhere is still dropped.
    assert "flag" not in json.loads(server._json({"ok": True, "flag": False}))


# --------------------------------------------------------------------------
# N-8, transitively — the AST check alone is not the guarantee
# --------------------------------------------------------------------------

def test_no_write_path_is_reachable_through_a_lazy_import():
    """`test_no_write_path_is_reachable_from_the_agent_surface` walks this
    module's AST, which catches a direct import and misses a transitive one: a
    tool importing `specgen.entity` would pull in a write path if that module
    ever imported one, and the AST would still be clean.

    **Runs in a subprocess**, deliberately. Checking this in-process means
    clearing `metis_mcp` out of `sys.modules` and reimporting, which rebinds
    every module object the rest of the suite already holds — the first version
    of this test did exactly that and broke an unrelated identity comparison in
    `test_ontology`. A test that has to corrupt the interpreter to run is a test
    that belongs in its own one.
    """
    import subprocess
    import sys

    program = """
import importlib, sys
importlib.import_module("metis_mcp.server")
for lazy in ("metis_mcp.mbt.graph_loader", "metis_mcp.specgen.entity",
             "metis_mcp.workflow.stages", "metis_mcp.workflow.routing",
             "metis_mcp.mbt.validation", "metis_mcp.mbt.coverage",
             "metis_mcp.mbt.path_generation"):
    importlib.import_module(lazy)
write_paths = %r
bad = [w for w in write_paths
       for m in sys.modules if m == w or m.startswith(w + ".")]
print(",".join(sorted(set(bad))))
""" % (WRITE_PATHS + ("metis_mcp.specgen.documents",),)

    result = subprocess.run([sys.executable, "-c", program],
                            capture_output=True, text=True, cwd=str(SERVER.parents[2]))
    assert result.returncode == 0, result.stderr
    reachable = [x for x in result.stdout.strip().split(",") if x]
    assert not reachable, (
        f"reachable from the agent surface through a lazy import: {reachable} — "
        f"N-8 is enforced by composition, and this is the hole the AST check "
        f"cannot see"
    )


def test_the_knowledge_tools_exist_and_summarise_by_default():
    """The five tools that make documents readable. Each returns a summary
    unless asked for detail, because a document body is the largest thing this
    surface can return."""
    for tool in (server.list_entities, server.get_entity, server.get_spec,
                 server.get_requirement, server.search_knowledge):
        assert tool.__doc__, f"{tool.__name__} has no description"

    for tool in (server.get_entity, server.get_spec, server.get_requirement):
        assert "detail" in tool.__doc__, (
            f"{tool.__name__} summarises but does not say so")


def test_an_empty_search_is_refused_rather_than_matching_everything():
    payload = json.loads(server.search_knowledge("   "))
    assert payload["ok"] is False
    assert "term" in payload["reason"]


# ---------------------------------------------------------------------------
# Transport selection.
#
# `main()` was `mcp.run()` and nothing more, while `Dockerfile.mcp-server` set
# `METIS_HTTP_PORT=8090` and `EXPOSE`d it. A detached container therefore
# published a port nothing listened on and waited on an stdin nobody was
# attached to. These tests exist so the Dockerfile's promise stays implemented.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_transport_env(monkeypatch):
    for var in (server.TRANSPORT_ENV, server.HOST_ENV, server.PORT_ENV):
        monkeypatch.delenv(var, raising=False)


def _capture_run(monkeypatch):
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda **kw: calls.append(kw))
    return calls


def test_stdio_is_the_default(monkeypatch):
    calls = _capture_run(monkeypatch)
    server.main()
    assert calls == [{}]          # mcp.run() with no transport argument


def test_an_http_transport_binds_the_configured_host_and_port(monkeypatch):
    calls = _capture_run(monkeypatch)
    monkeypatch.setenv(server.TRANSPORT_ENV, "streamable-http")
    monkeypatch.setenv(server.PORT_ENV, "8430")
    server.main()
    assert calls == [{"transport": "streamable-http"}]
    assert (server.mcp.settings.host, server.mcp.settings.port) == ("127.0.0.1", 8430)


def test_a_wider_bind_is_warned_about_on_stderr(monkeypatch, capsys):
    """Read-only is not the same as safe to expose."""
    _capture_run(monkeypatch)
    monkeypatch.setenv(server.TRANSPORT_ENV, "streamable-http")
    monkeypatch.setenv(server.HOST_ENV, "0.0.0.0")
    server.main()
    err = capsys.readouterr().err
    assert "does not authenticate" in err
    # stdout is the JSON-RPC channel for the stdio transport; nothing may go there
    assert capsys.readouterr().out == ""


def test_an_unknown_transport_halts_rather_than_falling_back(monkeypatch):
    """Falling back to stdio is how a container 'starts fine' and is unreachable."""
    _capture_run(monkeypatch)
    monkeypatch.setenv(server.TRANSPORT_ENV, "websocket")
    with pytest.raises(SystemExit) as e:
        server.main()
    assert "websocket" in str(e.value)


def test_the_dockerfile_port_is_the_default_http_port():
    """The image sets one; this must be the same number, or the EXPOSE is a lie."""
    dockerfile = pathlib.Path("Dockerfile.mcp-server").read_text()
    assert "ENV METIS_HTTP_PORT=8090" in dockerfile
    assert "EXPOSE 8090" in dockerfile
    assert server.PORT_ENV == "METIS_HTTP_PORT"


def test_the_read_only_default_is_still_structural():
    """N-8 is now conditional on configuration — and `off` must still be a proof.

    The write half is registered by `_register_write_tools`, which imports
    `metis_mcp.write` **inside** the branch. If that import ever moves to the
    top of the module, an unconfigured server would reach a write path while
    remaining unable to use it: the prohibition would survive as a policy check
    and die as a construction, and nothing else would notice.
    """
    import subprocess
    import sys

    program = """
import importlib, os, sys
assert os.environ.get("METIS_MCP_WRITE", "off") == "off"
importlib.import_module("metis_mcp.server")
print(",".join(sorted(m for m in sys.modules if m.startswith("metis_mcp.write"))))
"""
    env = {k: v for k, v in os.environ.items() if k != "METIS_MCP_WRITE"}
    result = subprocess.run([sys.executable, "-c", program], capture_output=True,
                            text=True, cwd=str(SERVER.parents[2]), env=env)
    assert result.returncode == 0, result.stderr
    assert not result.stdout.strip(), (
        f"the write module is imported with writes off: {result.stdout!r}")


def test_enabling_writes_registers_the_author_group_and_nothing_more():
    """`author` may land; it may not decide. The gate group is a separate mode."""
    import subprocess
    import sys

    program = """
import importlib
server = importlib.import_module("metis_mcp.server")
print(",".join(sorted(server._WRITE_TOOLS)))
"""
    result = subprocess.run([sys.executable, "-c", program], capture_output=True,
                            text=True, cwd=str(SERVER.parents[2]),
                            env={**os.environ, "METIS_MCP_WRITE": "author"})
    assert result.returncode == 0, result.stderr
    registered = sorted(x for x in result.stdout.strip().split(",") if x)
    # The rule, not a frozen list: authoring may grow (it did — get_transition
    # and the workflow tools joined it), and a test pinned to today's names
    # would have to be edited every time, which is how it stops being read.
    assert {"land_model", "land_knowledge", "land_findings"} <= set(registered)
    gates = [t for t in registered
             if any(word in t for word in ("approve", "reject", "defer",
                                           "publish", "review_queue"))]
    assert not gates, f"a gate tool registered in author mode: {gates}"


def test_full_mode_adds_the_gate_group_and_the_queue_that_feeds_it():
    """`review_queue` belongs with the gates, not the read tools.

    Its whole output is the evidence for a decision, including the fingerprint
    `approve_elements` demands back. A surface that could hand out that
    fingerprint but not spend it would be inviting a call it cannot serve.
    """
    import subprocess
    import sys

    program = ("import importlib;"
               "print(','.join(sorted(importlib.import_module"
               "('metis_mcp.server')._WRITE_TOOLS)))")
    result = subprocess.run([sys.executable, "-c", program], capture_output=True,
                            text=True, cwd=str(SERVER.parents[2]),
                            env={**os.environ, "METIS_MCP_WRITE": "full"})
    assert result.returncode == 0, result.stderr
    registered = set(result.stdout.strip().split(","))
    assert {"review_queue", "approve_elements", "reject_elements",
            "defer_elements"} <= registered


# ---------------------------------------------------------------------------
# A model that does not exist is refused, not reported on
# ---------------------------------------------------------------------------

class _FakeSession:
    """A graph holding exactly one model, `mfa-api`."""

    def __init__(self, rows_for):
        self._rows_for = rows_for

    def run(self, cypher, **params):
        return self._rows_for(cypher, params)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def one_model(monkeypatch):
    def rows_for(cypher, params):
        if "UNWIND s.functional_areas" in cypher:
            return [{"journey": "mfa", "surface": "api"}]
        if params.get("journey") != "mfa" or params.get("surface", "api") != "api":
            return []
        if "MATCH (s:State)" in cypher:
            return [{"id": "s1", "name": "Ready", "surface": "api",
                     "is_initial": True}]
        return []
    monkeypatch.setattr(server, "session", lambda: _FakeSession(rows_for))


@pytest.mark.parametrize("tool", ["get_model", "validate_model", "coverage"])
def test_a_model_the_graph_does_not_hold_is_refused(one_model, tool):
    """**The third instance of this bug class, and the one that reads worst.**

    An empty `Model` is what a typo produces, and every tool downstream reported
    on it cheerfully: `get_model` returned `ok: true` with zero states, and
    `coverage` returned a structurally complete ledger with `uncovered: 0` —
    which a reader, or an agent, takes for "nothing is uncovered". `ok: true` on
    a question about a thing that does not exist is the failure mode this
    codebase hunts, not a tolerable edge case.
    """
    out = json.loads(getattr(server, tool)("does-not-exist"))
    assert out["ok"] is False, f"{tool} reported success for a missing model"
    assert "does-not-exist" in out["reason"]


def test_the_refusal_names_the_models_that_do_exist(one_model):
    """A wrong journey is nearly always a near-miss, so a dead end is a waste."""
    out = json.loads(server.get_model("does-not-exist"))
    assert out["available"] == [{"journey": "mfa", "surface": "api"}]


def test_passing_the_model_id_instead_of_the_journey_is_named_as_such(one_model):
    """The mistake that found this: `get_model("mfa-api")` builds `mfa-api-api`.
    It is common enough — the model id is what every other tool prints — that
    guessing at it is worth doing explicitly."""
    out = json.loads(server.get_model("mfa-api"))
    assert out["ok"] is False
    assert "pass 'mfa', not 'mfa-api'" in out["note"]


def test_a_model_that_does_exist_is_still_answered(one_model):
    """The guard must not become a refusal machine."""
    out = json.loads(server.get_model("mfa"))
    assert out["ok"] is True and len(out["states"]) == 1
