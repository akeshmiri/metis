"""
Automation viability and performance candidacy (Atlas test-designer 04 and 05).

The two stages the port had no equivalent for. Coverage answers "is this
tested?"; these answer "can it be automated at all?" and "is it worth driving
under load?".

**The refusals are the point.** Atlas's stage 04 forbids marking a scenario
`automate` from its class name alone, and its stage 05 forbids inventing an SLA
threshold. Both become verdicts here, so these tests assert that each branch
fires for its own reason rather than that the happy path works.
"""
from __future__ import annotations

from metis_mcp import viability
from metis_mcp.mbt.model import Model, State, Transition


def _model(*transitions) -> Model:
    states = {"A": State(id="A", name="A", is_initial=True),
              "B": State(id="B", name="B")}
    return Model(id="m-api", states=states,
                 transitions={t.id: t for t in transitions})


def _api(tid, trigger="POST /thing", **kw):
    kw.setdefault("evidence", ({"file": "X.java", "line": 1},))
    kw.setdefault("inputs", ({"name": "id", "location": "path",
                              "type_name": "java.lang.String",
                              "required": True},))
    return Transition(id=tid, source="A", target="B", trigger=trigger, **kw)


def _verdicts(model, unverifiable=None):
    return {r["transition_id"]: r["verdict"]
            for r in viability.classify_viability(model, unverifiable or set())}


# --------------------------------------------------------------------------
# Stage 04 — every branch, each for its own reason
# --------------------------------------------------------------------------

def test_an_anchored_api_call_with_a_contract_is_automatable():
    assert _verdicts(_model(_api("t1")))["t1"] == viability.AUTOMATE


def test_an_unanchored_transition_is_never_automatable():
    """**The ported refusal.** Never mark `automate` from the name alone —
    verify the prerequisite exists, with a concrete reference (X-6)."""
    rows = viability.classify_viability(_model(_api("t1", evidence=())))
    assert rows[0]["verdict"] == viability.MANUAL_ONLY
    assert "X-6" in rows[0]["why"]


def test_an_unverifiable_guard_defers_rather_than_automating():
    """M-17: neither a pass nor a defect. You cannot assert against an oracle
    nobody can evaluate, and pretending otherwise ships a test that means
    nothing."""
    rows = viability.classify_viability(_model(_api("t1")), {"t1"})
    assert rows[0]["verdict"] == viability.DEFER
    assert "oracle" in rows[0]["why"]


def test_an_unresolved_source_state_is_manual_only():
    """P-8: a test whose precondition cannot be established is not executable."""
    rows = viability.classify_viability(
        _model(_api("t1", source_state_unresolved=True)))
    assert rows[0]["verdict"] == viability.MANUAL_ONLY
    assert "P-8" in rows[0]["why"]


def test_a_ui_action_without_an_authored_selector_is_manual_only():
    """Métis never guesses a selector — a guessed one produces a test that
    fails for a reason unrelated to the behaviour under test."""
    rows = viability.classify_viability(
        _model(_api("t1", trigger="click submit")))
    assert rows[0]["verdict"] == viability.MANUAL_ONLY
    assert "selector" in rows[0]["why"]


def test_a_write_with_no_recovered_inputs_defers():
    """A POST whose body is unknown cannot be built from the contract."""
    rows = viability.classify_viability(_model(_api("t1", inputs=())))
    assert rows[0]["verdict"] == viability.DEFER


def test_a_get_with_no_inputs_is_still_automatable():
    """The guard must not become a machine that only refuses: a parameterless
    GET is the most automatable thing there is."""
    rows = viability.classify_viability(
        _model(_api("t1", trigger="GET /things", inputs=())))
    assert rows[0]["verdict"] == viability.AUTOMATE


def test_every_verdict_carries_an_auditable_reason():
    """A verdict a reader cannot audit is one they must take on trust — and this
    one decides whether somebody spends a week automating the unassertable."""
    for row in viability.classify_viability(_model(_api("t1"), _api("t2"))):
        assert len(row["why"]) > 20


# --------------------------------------------------------------------------
# Stage 05 — and the refusal that matters most
# --------------------------------------------------------------------------

def test_a_paging_parameter_makes_a_call_a_performance_candidate():
    model = _model(_api("t1", trigger="GET /things", inputs=(
        {"name": "page", "location": "query", "type_name": "int"},)))
    out = viability.classify_performance(model)
    assert out["rows"][0]["verdict"] == viability.PERFORMANCE_CANDIDATE
    assert out["rows"][0]["signals"]


def test_a_collection_input_makes_a_call_a_performance_candidate():
    model = _model(_api("t1", inputs=(
        {"name": "items", "location": "body",
         "type_name": "java.util.List<Item>"},)))
    assert viability.classify_performance(model)["rows"][0]["verdict"] == \
        viability.PERFORMANCE_CANDIDATE


def test_a_model_with_no_volume_facts_reports_no_basis_not_functional_only():
    """**The refusal this stage exists for.** Classifying everything
    `functional-only` would read as "measured, and none qualify" — a claim
    nobody made. Inventing an SLA threshold is what Atlas's stage 05 forbids."""
    out = viability.classify_performance(_model(_api("t1"), _api("t2")))
    assert {r["verdict"] for r in out["rows"]} == {viability.NO_BASIS}
    assert "invented SLA" in out["basis"]


def test_performance_only_considers_what_can_be_automated():
    """Driving load at something that cannot be automated is not a plan."""
    model = _model(_api("t1", evidence=()), _api("t2", trigger="GET /x", inputs=(
        {"name": "limit", "location": "query", "type_name": "int"},)))
    viab = viability.classify_viability(model)
    rows = viability.classify_performance(model, viab)["rows"]
    assert {r["transition_id"] for r in rows} == {"t2"}


def test_the_report_never_reads_as_a_statement_about_speed():
    """C-11 / §8.7: a candidate is a call whose cost plausibly scales, not one
    observed to be slow.

    This said "no execution result is ingested", which stopped being true when
    `execution_intake` landed six labels (§8.7, revised). The claim that
    survives is the one the test is about: **this analysis reads none** — an
    execution result attaches to the `TestCase` that ran and never writes the
    coverage ledger (C-10), so a viability candidate is still a structural
    judgement and not a measurement.
    """
    out = viability.classify_performance(_model(_api("t1")))
    assert "§8.7" in out["means"]


# --------------------------------------------------------------------------
# Coverage depth — Atlas test-designer stage 03's third status.
#
# `coverage` is binary per transition, so a case that walks the happy path makes
# it "covered". Atlas says plainly that a positive scenario is NOT coverage for a
# prohibited or boundary condition unless a test with that condition's own oracle
# exists. Métis had the criteria to tell the difference and nothing that asked.
# --------------------------------------------------------------------------

APPROVED = "Approved"


def _approved(*transitions, states=("A", "B", "C")) -> Model:
    built = {s: State(id=s, name=s, is_initial=(s == "A"),
                      lifecycle_state=APPROVED) for s in states}
    return Model(id="d-api", states=built,
                 transitions={t.id: t for t in transitions})


def _t(tid, source, target, guard="", trigger="POST /r"):
    return Transition(id=tid, source=source, target=target, trigger=trigger,
                      guard=guard, lifecycle_state=APPROVED)


def test_a_guarded_transition_with_one_branch_is_positive_only():
    """**The rule this exists for.** One case walking the positive path leaves
    the complement with no oracle of its own, and `coverage` calls that
    covered."""
    out = viability.classify_depth(_approved(_t("ok", "A", "B", "len(n) >= 3")))
    assert out["rows"][0]["verdict"] == viability.POSITIVE_ONLY
    assert "complement" in out["rows"][0]["why"]


def test_both_branches_present_reads_as_full():
    """The guard must not become a machine that only complains."""
    out = viability.classify_depth(_approved(
        _t("ok", "A", "B", "len(n) >= 3"),
        _t("bad", "A", "C", "NOT (len(n) >= 3)")))
    assert set(out["counts"]) == {viability.FULL}, out["counts"]


def test_an_unguarded_transition_is_full_not_partial():
    """One path really is the whole of it — flagging it would be noise that
    teaches people to ignore the report."""
    out = viability.classify_depth(_approved(_t("plain", "A", "B")))
    assert out["rows"][0]["verdict"] == viability.FULL


def test_depth_does_not_claim_to_be_coverage():
    """C-11 / C-1: this is a second question about the same model, not a
    redefinition of the ledger."""
    out = viability.classify_depth(_approved(_t("plain", "A", "B")))
    assert "not the ledger" in out["means"]


def test_a_transition_the_ledger_never_reached_is_left_to_coverage():
    """Depth is about the conditions of behaviour that IS generated. Something
    excluded entirely is `coverage`'s finding, and reporting it twice in
    different words is how two figures come to disagree."""
    out = viability.classify_depth(_approved(
        _t("unreachable", "C", "B", "x > 1")))     # C is not initial
    assert out["rows"] == []


def test_the_design_report_carries_all_three_classifications():
    model = _approved(_t("ok", "A", "B", "len(n) >= 3"))
    report = viability.design_report(model)
    for key in ("viability", "performance", "depth"):
        assert key in report, key
