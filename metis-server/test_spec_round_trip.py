"""
Code → model → spec → edited spec → model (spec §18, SP-1, SP-1a; §4.3).

**The target journey is spec-driven with the model primary.** Spec and AC are
where intent is authored and reviewed in business language; the model is what
test design and refinement consume. That only works if the document can be
generated, edited, and read back — and it could not be.

Three breaks, all closed here:

  * **Identity.** `specgen` emitted `### get /metric/{id} → MetricGet…204` and
    `spec_kit` needs `### AC-<id>: …`, so a generated spec parsed back to
    **zero** criteria. The loop was open at its first joint.
  * **Language.** The clauses rendered the code's vocabulary — `they are
    MetricGetActionByIdNoContent204`, `the condition NOT (request_accepted)
    holds` — while `guard_wording`, `state.condition` and `response_body` sat on
    the model unused.
  * **The binding.** `specgen` has always stamped the transition id into each
    block and nothing ever read it, while the graph held **0 `VALIDATES`** edges.

The test that matters most is `test_human_wording_survives_regeneration`. If a
regeneration silently reverts a person's editing, the whole "generate once, then
maintain the spec" architecture is unusable — and it fails quietly, in a diff
nobody reads.
"""
from __future__ import annotations

import dataclasses
import sys
import tempfile
from pathlib import Path

from metis_mcp.mbt.model import APPROVED, Model, State, Transition
from metis_mcp.model_sources.spec_kit import parse_spec
from metis_mcp.specgen import specification as sg

HUMAN = "ac_vocabulary"


def _model() -> Model:
    states = {
        "Metric": State(id="Metric", name="Metric", surface="api", is_initial=True,
                        condition="no metric exists", lifecycle_state=APPROVED),
        "MetricPresent": State(id="MetricPresent", name="MetricPresent",
                               surface="api", lifecycle_state=APPROVED),
        "Rejected": State(id="Rejected", name="MetricSaveRejected400",
                          surface="api", lifecycle_state=APPROVED),
    }
    transitions = {
        "create": Transition(
            id="create", source="Metric", trigger="POST /metric",
            target="MetricPresent", guard="payload_valid",
            guard_wording="the payload is valid", guard_tier="code_convention",
            outcome_status=201, lifecycle_state=APPROVED),
        "reject": Transition(
            id="reject", source="Metric", trigger="POST /metric",
            target="Rejected", guard="NOT (payload_valid)",
            guard_wording="the payload is invalid", guard_tier="code_convention",
            outcome_status=400, lifecycle_state=APPROVED),
        "read": Transition(
            id="read", source="MetricPresent", trigger="GET /metric/{id}",
            target="MetricPresent", guard="", guard_wording="always",
            guard_tier="code_convention", outcome_status=200,
            response_body="RecordDto", lifecycle_state=APPROVED),
    }
    m = Model(id="records-api", states=states, transitions=transitions)
    m.reindex()
    return m


def _render(model: Model) -> str:
    return sg.render_markdown(sg.build(model, journey="records"))


def _round_trip(model: Model):
    directory = Path(tempfile.mkdtemp()) / "records"
    directory.mkdir()
    (directory / "spec.md").write_text(_render(model))
    return parse_spec(directory / "spec.md")


# --------------------------------------------------------------------------
# The loop closes.
# --------------------------------------------------------------------------

def test_a_generated_spec_parses_back_into_criteria():
    """This returned **zero** before the heading carried an `AC-` id."""
    model = _model()
    feature = _round_trip(model)
    assert len(feature.criteria) == len(model.transitions)
    assert all(c.is_behavioural for c in feature.criteria)


def test_every_criterion_binds_to_the_transition_it_came_from():
    """No matching heuristic — the id is in the document.

    X-17 forbids name similarity as sufficient evidence for a match. This is not
    similarity: it is the identity `specgen` wrote and `spec_kit` now reads.
    """
    model = _model()
    for criterion in _round_trip(model).criteria:
        assert criterion.transition_id in model.transitions, (
            f"{criterion.id} does not bind to a real transition")


def test_a_hand_written_criterion_has_no_binding_and_says_so():
    """the pilot estate's 66 criteria carry none. An absent binding is a fact about the
    source, not a gap to fill by guessing — those keep going through
    `reconciliation.prefilter`."""
    directory = Path(tempfile.mkdtemp()) / "hand-written"
    directory.mkdir()
    (directory / "spec.md").write_text(
        "# Feature Spec: x\n\n"
        "### AC-1: A metric can be recorded\n\n"
        "**Given** a project exists\n**When** a metric is submitted\n"
        "**Then** it is stored\n")
    criterion = parse_spec(directory / "spec.md").criteria[0]
    assert criterion.transition_id == ""
    assert criterion.is_behavioural


# --------------------------------------------------------------------------
# It reads as business flow.
# --------------------------------------------------------------------------

def test_the_clauses_carry_no_code_vocabulary():
    md = _render(_model())
    clauses = [l for l in md.splitlines()
               if l.startswith(("**Given**", "**When**", "**And**", "**Then**"))]
    joined = "\n".join(clauses)
    assert "MetricSaveRejected400" not in joined, "the target's node name leaked"
    assert "NOT (payload_valid)" not in joined, "the raw guard is not the sentence"
    assert "no metric exists" in joined
    assert "the payload is invalid" in joined


def test_the_observable_result_is_status_and_body_not_a_node_name():
    md = _render(_model())
    assert "RecordDto is returned (200)" in md
    assert "nothing is returned (400, no body)" in md, (
        "an empty body is a fact — `ResponseEntity<Void>` returns nothing — not "
        "missing information")


def test_the_recovered_condition_stays_visible_as_evidence():
    """T-5: prose changes which of the two is the *sentence*, never which is
    authoritative. A reviewer must still be able to see what the code evaluates."""
    md = _render(_model())
    assert "condition as recovered: `NOT (payload_valid)`" in md


# --------------------------------------------------------------------------
# The test the architecture rests on.
# --------------------------------------------------------------------------

def test_human_wording_survives_regeneration():
    """**Without this, run 2 destroys run 1's editing.**

    `guard_tier` is `ac_vocabulary` only where a confirmed criterion supplied the
    words, so the tier is the machine/human split — the same one
    `carry_human_facts` applies to the graph, with no prose diffing.
    """
    model = _model()
    model.transitions["reject"] = dataclasses.replace(
        model.transitions["reject"],
        guard_wording="the caller omitted a field the metric requires",
        guard_tier=HUMAN)

    md = _render(model)
    assert "the caller omitted a field the metric requires" in md
    assert "the payload is invalid" not in md, "regenerated over a person's words"


def test_a_machine_wording_is_regenerated_not_frozen():
    """The other half. A `code_convention` wording must track the code, or the
    document goes stale exactly where nobody has taken responsibility for it."""
    model = _model()
    model.transitions["reject"] = dataclasses.replace(
        model.transitions["reject"], guard_wording="the payload is invalid",
        guard_tier="code_convention")
    assert "the payload is invalid" in _render(model)


# --------------------------------------------------------------------------
# Identity is stable, because an ordinal is not.
# --------------------------------------------------------------------------

def test_ids_do_not_shift_when_a_rule_is_inserted():
    """the pilot estate has 16 positional `AC-4.1` sub-ids. Insert a rule above one and
    every id after it changes, orphaning its approval. The natural key moves
    only when the behaviour does."""
    model = _model()
    before = {r.transition_id: r.criterion_id
              for r in sg.build(model, journey="records").rules}

    model.transitions["extra"] = Transition(
        id="extra", source="Metric", trigger="DELETE /metric/{id}",
        target="Rejected", outcome_status=204, lifecycle_state=APPROVED)
    model.reindex()

    after = {r.transition_id: r.criterion_id
             for r in sg.build(model, journey="records").rules}
    for tid, criterion_id in before.items():
        assert after[tid] == criterion_id, f"{tid}'s id shifted on an insertion"


def test_the_id_is_stable_across_a_guard_edit():
    """A guard changing is the commonest edit there is. If it moved identity,
    nothing would survive a code tweak (I-6)."""
    model = _model()
    before = sg.build(model, journey="records").rules[0]
    model.transitions[before.transition_id] = dataclasses.replace(
        model.transitions[before.transition_id], guard="payload_valid AND fresh")
    after = next(r for r in sg.build(model, journey="records").rules
                 if r.transition_id == before.transition_id)
    assert after.criterion_id == before.criterion_id


def test_the_heading_keeps_the_behaviour_not_just_the_id():
    """SP-1: a stakeholder reads this. An element id printed as a section title
    tells them nothing, so the id is a prefix rather than a replacement."""
    rule = sg.build(_model(), journey="records").rules[0]
    assert rule.heading.startswith(f"{rule.criterion_id}: ")
    assert rule.title in rule.heading


# --------------------------------------------------------------------------
# S-19's ladder: an edit is what turns documentation into intent.
# --------------------------------------------------------------------------

def test_an_untouched_generated_criterion_is_not_an_edit():
    """The bootstrap must not promote itself. A generated spec agreeing with the
    model it came from is circular (§4.1), and a run that reported it as intent
    would manufacture the correctness claim S-19 exists to withhold."""
    feature = _round_trip(_model())
    assert not any(c.edited_by_hand for c in feature.criteria)


def test_rewriting_a_clause_is_detected_as_an_edit():
    """S-19: documentation "until a person edits or affirms one"."""
    directory = Path(tempfile.mkdtemp()) / "records"
    directory.mkdir()
    path = directory / "spec.md"
    path.write_text(_render(_model()))

    path.write_text(path.read_text().replace(
        "**And** the payload is invalid",
        "**And** the caller omitted a field the metric requires", 1))

    edited = [c for c in parse_spec(path).criteria if c.edited_by_hand]
    assert len(edited) == 1, "exactly the rewritten rule, and only it"


def test_a_criterion_with_no_fingerprint_is_never_called_edited():
    """Hand-written criteria carry no stamp. Treating "no fingerprint" as
    evidence of editing would promote the pilot estate's 66 retro-documentation criteria
    to intent on the strength of an absence — the opposite of evidence."""
    directory = Path(tempfile.mkdtemp()) / "hand-written"
    directory.mkdir()
    (directory / "spec.md").write_text(
        "# Feature Spec: x\n\n### AC-1: A metric can be recorded\n\n"
        "**Given** a project exists\n**When** a metric is submitted\n"
        "**Then** it is stored\n")
    criterion = parse_spec(directory / "spec.md").criteria[0]
    assert criterion.edited_by_hand is False
    assert criterion.transition_id == ""


def test_a_regenerated_lifecycle_mark_is_not_mistaken_for_an_edit():
    """The fingerprint covers the four clauses ALONE.

    A lifecycle mark and a `Validated by:` line change as the graph changes, and
    neither is a person rewriting behaviour — including them would report an
    edit on every single regeneration and promote the whole estate to intent.
    """
    model = _model()
    plain = _round_trip(model)

    marked = sg.build(model, journey="records",
                      acceptance_criteria={"reject": ["AC-9 of PROJ-1"]})
    directory = Path(tempfile.mkdtemp()) / "records"
    directory.mkdir()
    (directory / "spec.md").write_text(sg.render_markdown(marked))

    assert not any(c.edited_by_hand for c in parse_spec(directory / "spec.md").criteria)
    assert len(plain.criteria) == len(model.transitions)


# --------------------------------------------------------------------------
# One direction: spec informs test design, never the reverse.
# --------------------------------------------------------------------------

def test_nothing_downstream_of_the_model_writes_back_to_a_specification():
    """**Authority flows one way from spec to test design.**

    Spec and AC are where intent is authored; the model is what test design and
    refinement consume. A path from a test artefact back into a specification
    would let generated output rewrite the intent it was generated from — the
    same circularity §4.1 rejects, arriving by a longer route.

    The only writer to `.specify/specs/` is `specgen.writeback`, which renders
    the MODEL and is gated (T-18). Path generation, rendering and publishing
    must not reach it.
    """
    import importlib
    import pkgutil

    root = Path(__file__).resolve().parent / "metis_mcp"
    downstream = ("mbt.path_generation", "mbt.criteria", "rendering.test_case",
                  "rendering.payload", "publishing.publish")
    offenders = []
    for name in downstream:
        module = root / Path(name.replace(".", "/") + ".py")
        if not module.exists():
            continue
        text = module.read_text()
        for needle in ("specify/specs", "specgen", "writeback"):
            if needle in text:
                offenders.append(f"{name}: {needle}")
    assert not offenders, (
        "test-design/generation reaches a specification writer: "
        + ", ".join(offenders))


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
