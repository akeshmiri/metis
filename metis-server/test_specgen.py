"""
Stakeholder specification tests (application spec §18; A-59..A-62).

Free to run: generation is pure and takes an injectable timestamp.
"""
import sys

from metis_mcp.mbt.model import APPROVED, DISPUTED, PLANNED, QUARANTINE, Model, State, Transition
from metis_mcp.mbt.validation import validate
from metis_mcp.specgen import EXPORT, LIVING, build, dated_export, living_page, render_markdown
from mbt_fixtures import login_model

AT = "2026-08-15T09:00:00+00:00"


def _spec(model, **kw):
    kw.setdefault("generated_at", AT)
    return build(model, **kw)


# --------------------------------------------------------------------------
# SP-3 : the model is already Given/When/Then
# --------------------------------------------------------------------------

def test_a_transition_renders_as_given_when_then():
    spec = _spec(login_model())
    rule = next(r for r in spec.rules if r.transition_id == "t01")
    assert rule.given == "the user is LoggedOut"
    assert rule.when == "they submit valid credentials"
    assert rule.then == "they are LoggedIn"
    assert rule.and_guard == "credentials_valid AND NOT account_locked"


def test_state_names_appear_exactly_as_the_model_names_them():
    """`LoggedOut` is not softened to "Logged out". Rewriting it would make the
    document and the model use different words for one state, which is precisely
    what stops a reader tracing a sentence back to an element (SP-2)."""
    spec = _spec(login_model())
    model_names = {s.name for s in login_model().states.values()}
    assert {s.name for s in spec.situations} <= model_names


def test_the_verbatim_guard_is_always_shown():
    """T-5's discipline applied to documents: prose is a convenience, the
    recovered condition is the authoritative statement."""
    text = render_markdown(_spec(login_model()))
    assert "`credentials_valid AND NOT account_locked`" in text


def test_every_transition_becomes_exactly_one_rule():
    model = login_model()
    spec = _spec(model)
    assert len(spec.rules) == len(model.transitions) == 17
    assert {r.transition_id for r in spec.rules} == set(model.transitions)


def test_every_state_becomes_exactly_one_situation():
    spec = _spec(login_model())
    assert len(spec.situations) == 10
    assert sum(1 for s in spec.situations if s.is_initial) == 1


# --------------------------------------------------------------------------
# A-59 : non-approved rules are visibly marked, never presented as agreed
# --------------------------------------------------------------------------

def test_a59_a_quarantined_rule_is_marked_in_the_body():
    model = login_model(approved=False)
    text = render_markdown(_spec(model))
    assert "PROPOSED" in text
    assert "not yet approved" in text


def test_a59_a_disputed_rule_is_marked_distinctly_from_quarantine():
    model = login_model(approved=True)
    old = model.transitions["t06"]
    model.transitions["t06"] = Transition(
        id=old.id, source=old.source, trigger=old.trigger, target=old.target,
        guard=old.guard, lifecycle_state=DISPUTED)
    model.reindex()
    rule = next(r for r in _spec(model).rules if r.transition_id == "t06")
    assert "DISPUTED" in rule.mark
    assert "sources disagree" in rule.mark


def test_a59_a_planned_rule_says_it_is_not_built():
    rule = next(r for r in _spec(login_model()).rules if r.transition_id == "t17")
    assert "PLANNED" in rule.mark
    assert "not a coverage gap" in rule.mark


def test_a59_an_approved_rule_carries_no_mark():
    """Marking everything would train readers to skip the marks — the exact
    failure SP-5 exists to prevent."""
    rule = next(r for r in _spec(login_model()).rules if r.transition_id == "t01")
    assert rule.mark == ""
    assert rule.is_settled


def test_a59_the_document_leads_with_how_much_is_unsettled():
    model = login_model(approved=False)
    text = render_markdown(_spec(model))
    assert "are not approved" in text
    assert "not the same as what has been" in text


def test_a_fully_approved_model_carries_no_banner():
    model = login_model(approved=True)
    spec = _spec(model)
    assert spec.is_fully_settled
    assert "rules are not approved" not in render_markdown(spec)


def test_a_planned_rule_does_not_count_as_unreviewed():
    """`review export` skips planned transitions (P-11), so counting one as
    unapproved would make a fully-reviewed model report an outstanding decision
    that can never be made."""
    model = login_model(approved=True)
    planned = model.transitions["t17"]
    assert planned.implementation_status == PLANNED
    model.transitions["t17"] = Transition(
        id=planned.id, source=planned.source, trigger=planned.trigger,
        target=planned.target, guard=planned.guard,
        implementation_status=PLANNED, lifecycle_state=QUARANTINE)
    model.reindex()

    spec = _spec(model)
    assert spec.unsettled == 0, "planned is not unreviewed"
    assert "rules are not approved" not in render_markdown(spec)
    # It is still marked in the body — as planned, which is a different fact.
    rule = next(r for r in spec.rules if r.transition_id == "t17")
    assert "PLANNED" in rule.mark


# --------------------------------------------------------------------------
# A-60 : every statement traces to a model element
# --------------------------------------------------------------------------

def test_a60_open_questions_come_from_real_findings_only():
    model = login_model()
    spec = _spec(model, validation=validate(model))
    assert spec.open_questions == [], "the real model has no blocking findings"

    broken = login_model()
    broken.transitions["tX"] = Transition(
        id="tX", source="LoggedOut", trigger="submit_invalid_credentials",
        target="AccountLocked", guard="attempts >= 1", lifecycle_state=APPROVED)
    broken.transitions["t02"] = Transition(
        id="t02", source="LoggedOut", trigger="submit_invalid_credentials",
        target="Failed1", guard="attempts >= 0", lifecycle_state=APPROVED)
    broken.reindex()
    spec = _spec(broken, validation=validate(broken))
    assert any("blocking" in q and "determinism" in q for q in spec.open_questions)


def test_a60_prose_only_re_spaces_and_capitalises():
    """`humanise` is reused from rendering so a specification and a test case
    cannot describe the same trigger differently."""
    from metis_mcp.rendering.test_case import humanise
    rule = next(r for r in _spec(login_model()).rules if r.transition_id == "t11")
    assert rule.when == f"they {humanise('click_forgot_password').lower()}"


def test_a60_nothing_is_added_for_readability():
    """Every rule traces to a real element, and every element has a rule.

    The heading is the BEHAVIOUR ("submit valid credentials → LoggedIn"), not the
    element id — a stakeholder document that used
    `org.catools...MetricController.getActionById:...::GET->NoContent204` as a
    section heading is not serving stakeholders (SP-1). The id stays in the body,
    so traceability is unchanged (SP-2).
    """
    model = login_model()
    text = render_markdown(_spec(model))
    for tid in model.transitions:
        assert f"`{tid}`" in text, f"{tid} must remain traceable"
    assert text.count("\n### ") == len(model.transitions)


def test_a60_the_heading_is_the_behaviour_not_the_identifier():
    spec = _spec(login_model())
    rule = next(r for r in spec.rules if r.transition_id == "t01")
    assert rule.heading == "submit valid credentials → LoggedIn"
    assert "t01" not in rule.heading


def test_acceptance_criteria_are_shown_only_where_confirmed():
    model = login_model()
    spec = _spec(model, acceptance_criteria={"t01": ["AC-2 of PROJ-1421"]})
    with_ac = next(r for r in spec.rules if r.transition_id == "t01")
    without = next(r for r in spec.rules if r.transition_id == "t02")
    assert with_ac.acceptance_criteria == ("AC-2 of PROJ-1421",)
    assert without.acceptance_criteria == ()
    assert "AC-2 of PROJ-1421" in render_markdown(spec)


def test_unspecified_behaviour_is_listed_once_criteria_exist():
    model = login_model()
    spec = _spec(model, acceptance_criteria={"t01": ["AC-1"]},
                 validated_transition_ids={"t01"})
    unspecified = [q for q in spec.open_questions if "unspecified behaviour" in q]
    assert len(unspecified) == 15, "16 implemented, 1 validated"
    assert not any("t01" in q for q in unspecified)


# --------------------------------------------------------------------------
# C-11 : coverage means tested, not working
# --------------------------------------------------------------------------

def test_the_coverage_section_carries_the_c11_caveat():
    text = render_markdown(_spec(login_model()), coverage_summary="16/16 transitions")
    assert "16/16 transitions" in text
    assert "not what is **working**" in text


# --------------------------------------------------------------------------
# A-61 / A-62 : living page vs dated export
# --------------------------------------------------------------------------

def test_a61_a_dated_export_records_its_version_and_commit():
    spec = _spec(login_model(), model_version="v3", commit="a3f21c")
    doc = dated_export(spec)
    assert doc.kind == EXPORT
    assert "v3" in doc.body and "a3f21c" in doc.body
    assert "never updated in" in doc.body


def test_a61_generation_is_reproducible():
    """SP-7: same model, same timestamp, identical bytes."""
    a = dated_export(_spec(login_model(), model_version="v3")).body
    b = dated_export(_spec(login_model(), model_version="v3")).body
    assert a == b


def test_a61_there_is_no_way_to_update_an_export_in_place():
    """SP-8: the absence of the function is the enforcement."""
    doc = dated_export(_spec(login_model()))
    assert not hasattr(doc, "update")
    assert not hasattr(doc, "refresh")


def test_a62_a_superseded_export_can_report_that_it_is_stale():
    doc = dated_export(_spec(login_model(), model_version="v3"))
    assert doc.staleness_against("v7") == "generated from v3; the model is now v7"
    assert doc.staleness_against("v3") == ""


def test_a62_an_unrecorded_version_says_so_rather_than_guessing():
    doc = dated_export(_spec(login_model()))
    assert "cannot be determined" in doc.staleness_against("v7")


def test_the_living_page_is_never_reported_stale():
    """It is regenerated on every model change, so staleness is not a property
    it can have (SP-6)."""
    page = living_page(_spec(login_model(), model_version="v3"))
    assert page.kind == LIVING
    assert page.staleness_against("v7") == ""


def test_the_living_page_and_the_export_share_one_content_assembly():
    """SP-6: two outputs, one assembly — so they cannot describe different
    behaviour."""
    spec = _spec(login_model(), model_version="v3")
    page, export = living_page(spec), dated_export(spec)
    assert page.body in export.body


# --------------------------------------------------------------------------
# E-10 : override density is carried into the document
# --------------------------------------------------------------------------

def test_a58_override_density_appears_in_the_specification():
    from metis_mcp.overrides import (
        INTENDED_DIVERGENCE, MODIFY, TRANSITION, OverrideLog, density, plan_override,
    )
    model = login_model()
    log = OverrideLog(model_id=model.id)
    log.append(plan_override(model, kind=TRANSITION, element_id="t06",
                             operation=MODIFY, author="bob", rationale="AC says 5",
                             classification=INTENDED_DIVERGENCE, prop="guard",
                             new_value="NOT credentials_valid AND attempts >= 5"))
    spec = _spec(model, override_density=density(model, log))
    assert "weaker claim about the code" in spec.override_note
    assert "Override density" in render_markdown(spec)


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
