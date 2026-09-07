"""
Human decisions survive re-ingest (application spec I-14..I-18, S-4).

**The cost this addresses is the only one that compounds.** `landing.py`
hardcoded `lifecycle_state: Quarantine` on every element it wrote, so approving
206 transitions and re-running the packs meant approving 206 transitions again.
Extraction is a script; re-reviewing an estate by hand on every run is not.

`identity.carry_human_facts` was written for exactly this and had zero production
callers — and could not have been wired as it stood, because it rebuilt each
element from a positional subset of its fields. Complete when a `Transition` had
seven; silently lossy by the time it had twenty-one.

**The first test below is the one that matters**, and it is deliberately written
against `dataclasses.fields` rather than a hand-listed set: a field added next
month must not be able to start disappearing without something failing.

The direction of failure is chosen. Losing an approval costs a re-review; keeping
one that should have been revoked means a generated test claims authority a human
never gave for that behaviour. Everything here fails toward revocation.
"""
from __future__ import annotations

import dataclasses
import sys

from metis_mcp.identity import carry_human_facts, diff
from metis_mcp.mbt.model import (
    APPROVED,
    QUARANTINE,
    Model,
    State,
    Transition,
)

HUMAN_FIELDS = {"lifecycle_state", "name", "name_tier"}


def _model(guard_ok: str = "payload_valid", guard_bad: str = "NOT (payload_valid)",
           extra: dict | None = None) -> Model:
    """One endpoint with two guarded siblings on a single (state, trigger).

    The two guards are varied **independently**. Deriving `bad` from `ok` as
    `NOT (guard_ok)` was the first version, and it made the I-18 test worthless:
    changing `ok` changed `bad` too, so both were revoked for having changed
    themselves and the group mechanism was never exercised at all.
    """
    states = {
        "Metric": State(id="Metric", name="Metric", surface="api", is_initial=True,
                        condition="no metric exists", name_tier="code_convention"),
        "Created": State(id="Created", name="Created", surface="api"),
        "Rejected": State(id="Rejected", name="Rejected", surface="api"),
    }
    transitions = {
        "ok": Transition(
            id="ok", source="Metric", trigger="POST /metric", target="Created",
            guard=guard_ok, outcome_status=201, response_body="RecordDto",
            guard_anchor="RecordController.java:64@sha", guard_wording="the payload is valid",
            guard_tier="code_convention", data_requirements=("@NotNull",),
            inputs=({"name": "metricDto", "location": "body"},),
            evidence=(("Endpoint", "ep:abc"), ("Parameter", "prm:def")),
            **(extra or {})),
        "bad": Transition(
            id="bad", source="Metric", trigger="POST /metric", target="Rejected",
            guard=guard_bad, outcome_status=400,
            guard_wording="the payload is invalid", guard_tier="code_convention"),
    }
    m = Model(id="records-api", states=states, transitions=transitions)
    m.reindex()
    return m


def _approved(model: Model) -> Model:
    approved = Model(
        id=model.id,
        states={k: dataclasses.replace(v, lifecycle_state=APPROVED)
                for k, v in model.states.items()},
        transitions={k: dataclasses.replace(v, lifecycle_state=APPROVED)
                     for k, v in model.transitions.items()})
    approved.reindex()
    return approved


def _carry(previous: Model, candidate: Model):
    return carry_human_facts(previous, candidate, diff(previous, candidate))


# --------------------------------------------------------------------------
# The test that would have caught the bug.
# --------------------------------------------------------------------------

def test_carrying_preserves_every_machine_field_it_does_not_own():
    """**Enumerated from `dataclasses.fields`, never hand-listed.**

    `carry_human_facts` rebuilt a `Transition` from 7 of its 21 fields, throwing
    away `inputs`, `outcome_status`, `response_body`, `guard_wording`,
    `data_requirements` and `evidence` — in the function whose job is to preserve
    things. Listing the survivors by hand here would reproduce exactly the defect
    that let it drift.
    """
    previous = _approved(_model())
    candidate = _model()
    carried = _carry(previous, candidate).model

    before, after = candidate.transitions["ok"], carried.transitions["ok"]
    for f in dataclasses.fields(Transition):
        if f.name in HUMAN_FIELDS:
            continue
        assert getattr(after, f.name) == getattr(before, f.name), (
            f"Transition.{f.name} was dropped by the carry")

    s_before, s_after = candidate.states["Metric"], carried.states["Metric"]
    for f in dataclasses.fields(State):
        if f.name in HUMAN_FIELDS:
            continue
        assert getattr(s_after, f.name) == getattr(s_before, f.name), (
            f"State.{f.name} was dropped by the carry")


def test_the_evidence_links_specifically_survive():
    """Called out because they are the newest and were the most exposed: a carry
    that lost them would sever the control flow from its evidence layer and the
    rebuild would still report success."""
    carried = _carry(_approved(_model()), _model()).model
    assert carried.transitions["ok"].evidence == (
        ("Endpoint", "ep:abc"), ("Parameter", "prm:def"))


# --------------------------------------------------------------------------
# I-14/I-16: decisions survive an unchanged re-extraction.
# --------------------------------------------------------------------------

def test_an_approval_survives_an_unchanged_rebuild():
    """The whole point. This is what re-approving 206 transitions cost."""
    carried = _carry(_approved(_model()), _model())
    assert carried.model.transitions["ok"].lifecycle_state == APPROVED
    assert carried.model.states["Metric"].lifecycle_state == APPROVED
    assert carried.revoked == []


def test_a_human_resolved_name_is_not_overwritten_by_extraction():
    """I-15: extraction may propose a name, never overwrite one. A tier-1 name
    from a confirmed criterion outranks the code convention that would otherwise
    be regenerated on every run."""
    previous = _approved(_model())
    previous.states["Created"] = dataclasses.replace(
        previous.states["Created"], name="the metric is recorded",
        name_tier="ac_vocabulary")

    carried = _carry(previous, _model()).model
    assert carried.states["Created"].name == "the metric is recorded"
    assert carried.states["Created"].name_tier == "ac_vocabulary", (
        "carrying the name and dropping its tier would claim a reviewer's "
        "wording came from a code convention")


# --------------------------------------------------------------------------
# I-17/I-18: revocation, and how far it reaches.
# --------------------------------------------------------------------------

def test_a_changed_guard_revokes_its_own_approval():
    """I-17. The dangerous direction is keeping an approval that no longer
    applies, so a real behaviour change must cost it."""
    carried = _carry(_approved(_model()), _model(guard_ok="payload_valid AND fresh"))
    assert carried.model.transitions["ok"].lifecycle_state == QUARANTINE
    assert any("ok" in r for r in carried.revoked)


def test_revocation_propagates_across_the_whole_group():
    """I-18. Determinism and guard completeness are properties of the
    `(state, trigger)` group, so a modified sibling can break a transition that
    did not itself change.

    `bad` keeps its exact guard here — it is genuinely untouched — and still
    loses its approval, which is the whole claim.
    """
    changed = _model(guard_ok="payload_valid AND fresh")   # `bad` is identical
    carried = _carry(_approved(_model()), changed)

    assert carried.model.transitions["bad"].lifecycle_state == QUARANTINE
    reasons = {r.split(":")[0]: r for r in carried.revoked}
    assert "behaviour changed" in reasons["ok"]
    assert "group" in reasons["bad"] and "I-18" in reasons["bad"], (
        f"`bad` must be revoked BY THE GROUP, not for itself: {reasons.get('bad')}")


def test_an_element_with_no_previous_match_keeps_its_own_state():
    """S-4: a genuinely new element starts at Quarantine. Nothing here may
    promote anything by accident."""
    previous = _approved(_model())
    candidate = _model()
    candidate.transitions["fresh"] = Transition(
        id="fresh", source="Metric", trigger="DELETE /metric/{id}", target="Rejected")
    candidate.reindex()

    carried = _carry(previous, candidate).model
    assert carried.transitions["fresh"].lifecycle_state == QUARANTINE


def test_a_rename_is_reported_rather_than_silently_resetting_identity():
    """I-22. `transition_key` includes the state names, so a rename reads as
    REMOVED + ADDED and the approval would vanish with no explanation. The delta
    proposes the rename and deliberately does not apply it — the run must say so
    rather than let identity quietly reset."""
    previous = _approved(_model())
    candidate = _model()
    candidate.states["CreatedOk201"] = dataclasses.replace(
        candidate.states.pop("Created"), id="CreatedOk201", name="CreatedOk201")
    candidate.transitions["ok"] = dataclasses.replace(
        candidate.transitions["ok"], target="CreatedOk201")
    candidate.reindex()

    carried = _carry(previous, candidate)
    assert carried.model.transitions["ok"].lifecycle_state == QUARANTINE, (
        "identity changed, so the approval does not carry — fail toward revocation")
    if carried.notes:
        assert any("rename" in n for n in carried.notes)


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
        except Exception as e:                                    # noqa: BLE001
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)


# ---------------------------------------------------------------------------
# A revocation a reviewer cannot see
# ---------------------------------------------------------------------------
#
# `carry_human_facts` builds `revoked` as a list of "<id>: <reason>" strings on
# purpose, and its own comment says why: *"Named, not counted. A revocation a
# reviewer cannot see is a decision taken on their behalf."*
#
# The caller printed `len(carry.revoked)`. The comment stating the intent sat
# three lines above the code doing the opposite, so the one thing the mechanism
# exists to make visible was the only part nobody could see — a reviewer
# re-approving after a code change was told "3 revoked" and could not find out
# which three.

def test_the_extract_stage_names_every_revoked_approval():
    """Findings carry the ids and reasons, not a count.

    **Calls the real function.** The first version of this test rebuilt the
    tuple expression inside itself, asserted on its own copy, imported
    `handlers` without calling anything, and would have passed with the
    production code deleted — a test that cannot fail for the reason it claims,
    written to prevent a failure that could not be seen. `carry_findings` was
    extracted so there is one implementation and this reaches it.
    """
    import types

    from metis_mcp.workflow.handlers import carry_findings

    findings = carry_findings(types.SimpleNamespace(
        carry_revocations=[
            "login-api::t_lock: behaviour changed",
            "login-api::t_retry: group (Ready, POST /login) was disturbed — "
            "determinism and guard completeness are group properties (I-18)"],
        carry_renames=["state s_401 -> s_403 (82% similar)"]))

    assert len(findings) == 3
    joined = " ".join(findings)
    # The ids, because a reviewer acts on those.
    assert "login-api::t_lock" in joined
    assert "login-api::t_retry" in joined
    # And the reason each was taken away, because "revoked" without a cause is
    # a decision presented as an event.
    assert "behaviour changed" in joined
    assert "I-18" in joined, "group propagation must say it was the group"
    assert "NOT applied" in joined, "a rename is proposed, never assumed (I-22)"


def test_a_run_that_revoked_nothing_reports_nothing():
    """The guard against the opposite failure: findings invented from an empty
    carry would put "approval revoked —" in front of every clean re-extraction."""
    import types

    from metis_mcp.workflow.handlers import carry_findings

    assert carry_findings(types.SimpleNamespace()) == ()
    assert carry_findings(types.SimpleNamespace(
        carry_revocations=[], carry_renames=[])) == ()


def test_carry_forward_puts_the_revocations_where_the_stage_reads_them():
    """The join between the producer and the consumer, exercised rather than grepped.

    `carry_human_facts` revokes and names; `_carry_forward` stashes; `_land`
    calls `carry_findings`. The defect was that middle link — the reasons were
    produced and then reduced to `len(...)` — so what has to be asserted is that
    a real revocation survives all three hops.

    An earlier version checked this with `inspect.getsource` string matching,
    which is a proxy for behaviour and passes on a function that contains the
    right words and does the wrong thing.
    """
    import types

    from metis_mcp.workflow.handlers import _carry_forward, carry_findings

    approved = _approved(_model())

    # The same model with one guard changed: I-17 revokes exactly there.
    candidate = _model(guard_ok="payload_valid AND quota_available")
    changed = next(t for t in candidate.transitions.values()
                   if "quota_available" in (t.guard or ""))

    context = types.SimpleNamespace(
        args=types.SimpleNamespace(uri=None, user=None, journey="login",
                                   surface="api"))
    result = types.SimpleNamespace(model=candidate)

    # `_carry_forward` loads the previous model from the graph. Substituting the
    # loader is what keeps this database-free, and it is the only thing
    # substituted — the diff, the carry and the finding construction are real.
    import metis_mcp.mbt.graph_loader as loader
    import metis_mcp.mbt.graph_session as gs
    from contextlib import contextmanager

    @contextmanager
    def _session(*a, **k):
        yield object()

    real_session, real_load = gs.session, loader.load_from_graph
    gs.session, loader.load_from_graph = _session, (
        lambda s, **k: types.SimpleNamespace(model=approved))
    try:
        note = _carry_forward(context, result)
    finally:
        gs.session, loader.load_from_graph = real_session, real_load

    assert "revoked" in note
    findings = carry_findings(context)
    assert findings, "the reasons were produced and then dropped — the defect"
    assert any(changed.id in f for f in findings), (
        f"the revoked transition {changed.id} is not named in {findings}")


def test_the_landing_stage_actually_returns_those_findings(monkeypatch):
    """**The join, which is the part that broke and the part the tests missed.**

    The three tests above exercise `carry_findings`, and every one of them
    passes with `_land`'s `findings = carry_findings(context)` replaced by
    `findings = ()` — which is the original defect, restored, undetected. A test
    of a producer proves nothing about a consumer that stopped reading it, and
    that is the shape of every failure in this file's subject.

    So this asserts the wiring: whatever `carry_findings` returns must come back
    out of the stage. `carry_findings` is substituted with a sentinel rather
    than reimplemented, so the assertion is about the CALL and not about the
    formatting, which the other tests own.
    """
    import types
    from contextlib import contextmanager

    from metis_mcp.workflow import handlers
    from metis_mcp.workflow.run import PASSED

    sentinel = ("SENTINEL — approval revoked",)

    @contextmanager
    def _session(*a, **k):
        yield object()

    monkeypatch.setattr(handlers, "carry_findings", lambda ctx: sentinel)
    monkeypatch.setattr(handlers, "_carry_forward", lambda ctx, res: "")
    monkeypatch.setattr(handlers, "_land_evidence",
                        lambda ctx, episode_id, model_plan=None: "")
    monkeypatch.setattr(handlers, "_land_stamped",
                        lambda s, plan, ctx: types.SimpleNamespace(
                            ok=True, refused=None, nodes_written=3,
                            edges_written=2, episode_id="ep-1"))
    monkeypatch.setattr("metis_mcp.mbt.graph_session.session", _session)
    monkeypatch.setattr("metis_mcp.model_sources.plan_landing",
                        lambda result, journey=None, job_id=None:
                        types.SimpleNamespace(is_legal=True, errors=[]))

    context = types.SimpleNamespace(
        source_result=types.SimpleNamespace(model=_model()),
        args=types.SimpleNamespace(journey="login", surface="api",
                                   job_id="j", uri=None, user=None))

    status, detail, findings, _ = handlers._land(context)
    assert status == PASSED, detail
    assert findings == sentinel, (
        "the landing stage dropped what the carry reported — which is the "
        "defect: the reasons were produced and reduced to a count")
