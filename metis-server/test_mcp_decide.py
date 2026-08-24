"""
The G1 gate through the agent surface (spec §3.4, N-10, N-13, N-14).

The invariant that matters most is structural and is asserted first: **only
`decide.py` may write `Approved`.** Everything in `write.py` lands at Quarantine
and leaves it there, which is what makes an agent that can write tolerable at
all — the worst it can do alone is add a candidate somebody has to review.

The rest are the refusals, one test each, because they fail for different
reasons and a caller needs to know which.

Free to run: the graph is monkeypatched out.
"""
import ast
import pathlib

import pytest

from metis_mcp import decide, policy
from metis_mcp.mbt.model import Model, State, Transition
from metis_mcp.review.roles import NotPermitted

PACKAGE = pathlib.Path(__file__).parent / "metis_mcp"


# --------------------------------------------------------------------------
# The structural invariant
# --------------------------------------------------------------------------

def test_only_decide_may_write_approved():
    """S-4/D-10, as a property of the source rather than of anyone's care.

    `write.py` may not name `Approved`, may not import `APPROVED`, and may not
    reach `review.decisions.apply` — which is the function that promotes. If a
    landing tool ever acquires the ability to approve what it just wrote, the
    two-stage split is gone and nothing else in the suite would notice.
    """
    source = (PACKAGE / "write.py").read_text()
    tree = ast.parse(source)

    imported = {
        alias.name for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
        if node.module.startswith("metis_mcp.review.decisions")
    }
    assert not imported, f"write.py reaches the promotion path: {imported}"

    # `APPROVED` is the constant the model layer promotes with; importing it is
    # the other way a landing tool could acquire the ability.
    names = {alias.name for node in ast.walk(tree)
             if isinstance(node, ast.ImportFrom) for alias in node.names}
    assert "APPROVED" not in names, "write.py imports the APPROVED constant"

    # Docstrings are excluded: this module's own prose says "no source writes
    # Approved", which is the rule being stated, not broken. What is checked is
    # every OTHER string literal — the ones that could reach a Cypher SET or a
    # lifecycle_state assignment.
    docstrings = {
        ast.get_docstring(n, clean=False)
        for n in ast.walk(tree)
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef))
    }
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and node.value not in docstrings):
            assert "Approved" not in node.value, (
                f"write.py names Approved outside a docstring: {node.value[:60]!r}")


def test_decide_is_the_module_that_promotes():
    """The other half: it would be equally wrong for nothing to promote."""
    source = (PACKAGE / "decide.py").read_text()
    assert "review.decisions" in source
    assert "APPROVE_MODEL" in source


# --------------------------------------------------------------------------
# The refusals — different reasons, different messages
# --------------------------------------------------------------------------

def _model() -> Model:
    model = Model(id="records-api")
    model.states["records-api::Ready"] = State(
        id="records-api::Ready", name="Ready", surface="api", is_initial=True)
    model.states["records-api::Done"] = State(
        id="records-api::Done", name="Done", surface="api")
    model.transitions["records-api::go"] = Transition(
        id="records-api::go", source="records-api::Ready", trigger="POST /go",
        target="records-api::Done", guard="")
    return model


@pytest.fixture
def graph(monkeypatch):
    """A model and its proposers, without a database."""
    model = _model()
    monkeypatch.setattr(decide, "_load", lambda j, s: model)
    monkeypatch.setattr(decide, "_proposers",
                        lambda j: {i: "alex" for i in
                                   list(model.states) + list(model.transitions)})
    monkeypatch.setenv(policy.WRITE_ENV, policy.FULL)
    monkeypatch.delenv(policy.IDENTITY_ENV, raising=False)
    return model


def _fingerprint(model) -> str:
    from metis_mcp.review.decisions import model_fingerprint

    return model_fingerprint(model)


def test_approval_without_the_literal_is_refused(graph):
    with pytest.raises(policy.ConfirmationRefused) as e:
        decide.approve_elements(journey="records", element_ids=["records-api::go"],
                                fingerprint=_fingerprint(graph),
                                actor="sam", role="reviewer")
    assert "approve" in str(e.value) and "no default" in str(e.value)


def test_a_stale_fingerprint_refuses_the_whole_batch(graph):
    """N-14. Partial application leaves nobody able to say what was decided."""
    out = decide.approve_elements(journey="records", element_ids=["records-api::go"],
                                  fingerprint="stale", confirm="approve",
                                  actor="sam", role="reviewer")
    assert out["ok"] is False
    assert "changed since" in out["refused"]
    assert out["current_fingerprint"] == _fingerprint(graph)


def test_the_proposer_may_not_approve_their_own_element(graph):
    """N-10, and it must fire on a landed model, not only a hand-edited one."""
    out = decide.approve_elements(journey="records", element_ids=["records-api::go"],
                                  fingerprint=_fingerprint(graph),
                                  confirm="approve", actor="alex", role="reviewer")
    assert out["ok"] is False and out["applied"] == 0
    assert "may not approve" in out["refused"][0]["reason"]
    assert "graph is untouched" in out["means"]


def test_a_role_without_the_capability_is_refused_before_anything_loads(graph):
    with pytest.raises(NotPermitted) as e:
        decide.approve_elements(journey="records", element_ids=["records-api::go"],
                                fingerprint=_fingerprint(graph),
                                confirm="approve", actor="kim", role="contributor")
    assert "reviewer" in str(e.value)


def test_author_mode_cannot_reach_the_gate(graph, monkeypatch):
    monkeypatch.setenv(policy.WRITE_ENV, policy.AUTHOR)
    with pytest.raises(policy.WriteDisabled) as e:
        decide.approve_elements(journey="records", element_ids=["records-api::go"],
                                fingerprint=_fingerprint(graph),
                                confirm="approve", actor="sam", role="reviewer")
    assert "gate" in str(e.value)


def test_no_element_ids_is_an_answer_not_a_crash(graph):
    out = decide.approve_elements(journey="records", element_ids=[],
                                  fingerprint=_fingerprint(graph),
                                  confirm="approve", actor="sam", role="reviewer")
    assert out["ok"] is False and "review_queue" in out["refused"]


def test_a_rejection_needs_a_reason(graph):
    """No literal for reject — a rationale instead. A refusal nobody can read
    is not a review."""
    out = decide.reject_elements(journey="records", element_ids=["records-api::go"],
                                 fingerprint=_fingerprint(graph),
                                 actor="sam", role="reviewer")
    assert out["ok"] is False and "rationale" in out["refused"]


def test_an_unknown_element_is_named(graph):
    out = decide.approve_elements(journey="records", element_ids=["records-api::ghost"],
                                  fingerprint=_fingerprint(graph),
                                  confirm="approve", actor="sam", role="reviewer")
    assert out["ok"] is False and "ghost" in out["refused"]
