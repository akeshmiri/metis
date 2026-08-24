"""
Resource-existence unfolding (application spec M-6, M-7, §5.8, T-9d).

The behaviour under test is what turns a star into a machine. Before it, all 13
extracted models had **zero** paths with a setup step, so `Scenario` -- whose
whole content is the ordered walk -- carried nothing at all.

The fail-closed case matters as much as the success case: where no creator can be
recovered, a guessed precondition would be worse than an admitted gap, because it
looks executable.
"""
from __future__ import annotations

import sys

from code_analysis.unfolding import (
    presence_sense,
    residual_guard,
    resource_of,
    resource_label,
    state_name_for,
    unfold,
)
from metis_mcp.mbt.model import QUARANTINE, State, Transition


def _states(*names, initial="Ready"):
    return {n: State(id=n, name=n, surface="api", is_initial=(n == initial),
                     lifecycle_state=QUARANTINE) for n in names}


def _t(tid, source, trigger, target, guard="", status=None):
    return Transition(id=tid, source=source, trigger=trigger, target=target,
                      guard=guard, lifecycle_state=QUARANTINE, outcome_status=status)


# --------------------------------------------------------------------------
# Keying. The guard variable is useless as a key; the path is the only one.
# --------------------------------------------------------------------------

def test_the_resource_is_the_path_up_to_the_first_parameter():
    assert resource_of("/metric/{id}") == "/metric"
    assert resource_of("/tms/execution/{id}") == "/tms/execution"
    assert resource_of("/metric") == "/metric"
    assert resource_of("") == ""


def test_state_names_come_from_the_resource_not_the_variable():
    """`t.isEmpty()` appears at 42 endpoints meaning 42 different things.

    It is one shared helper in `records-common`, so keying on the variable name
    would fuse every resource in the estate into a single state.
    """
    assert state_name_for("/metric") == "MetricPresent"
    assert state_name_for("/tms/execution") == "TmsExecutionPresent"


def test_the_name_uses_every_segment_because_last_segments_collide():
    """`/project/all`, `/user/all`, `/version/all` and `/environment/all` all
    live in the pilot estate's core service. Keyed on the last segment all four become
    `All`, and fusing four distinct resources into one node claims a call to
    `/user/all` starts from the same situation as a call to `/project/all`.

    Latent from the start and it never bit, because a `*Present` state is only
    created for a resource with both a creator and a presence-guarded reader,
    which none of the `/all` routes have. It bites the moment every resource
    gets its own node.
    """
    labels = {resource_label(r) for r in
              ("/project/all", "/user/all", "/version/all", "/environment/all")}
    assert len(labels) == 4, f"one node per resource, got {sorted(labels)}"
    assert resource_label("/metric") == "Metric"
    assert resource_label("/execution_status") == "ExecutionStatus"


def test_presence_sense_reads_both_idioms_and_their_negations():
    assert presence_sense("t.isEmpty()") == ("t.isEmpty()", False)
    assert presence_sense("NOT (t.isEmpty())") == ("NOT (t.isEmpty())", True)
    assert presence_sense("dbRecord.isPresent()") == ("dbRecord.isPresent()", True)
    assert presence_sense("NOT (dbRecord.isPresent())")[1] is False


def test_a_guard_that_says_nothing_about_existence_is_left_alone():
    assert presence_sense("severity >= 5") is None
    assert presence_sense("") is None


def test_m7_removes_only_the_unfolded_condition():
    """M-7: the unfolded variable goes; every other condition stays verbatim."""
    assert residual_guard("NOT (t.isEmpty()) AND user.isAdmin()",
                          "NOT (t.isEmpty())") == "user.isAdmin()"
    assert residual_guard("NOT (t.isEmpty())", "NOT (t.isEmpty())") == ""


# --------------------------------------------------------------------------
# The unfold itself.
# --------------------------------------------------------------------------

def _crud():
    states = _states("Ready", "Ok200", "NoContent204", "Created201")
    transitions = {
        "read-ok": _t("read-ok", "Ready", "GET /metric/{id}", "Ok200",
                      "NOT (t.isEmpty())", 200),
        "read-none": _t("read-none", "Ready", "GET /metric/{id}", "NoContent204",
                        "t.isEmpty()", 204),
        "create": _t("create", "Ready", "POST /metric", "Created201", "", 201),
    }
    return states, transitions


def test_a_read_that_requires_the_resource_starts_from_the_resource_state():
    result = unfold(*_crud())
    assert result.transitions["read-ok"].source == "MetricPresent"
    assert result.transitions["read-ok"].guard == "", "M-7 removes the condition"
    assert "MetricPresent" in result.states


def test_the_creator_lands_in_the_resource_state_and_keeps_its_status():
    """201 is what the caller receives; "it now exists" is the situation left
    behind. The status is not lost — it moves to the transition."""
    result = unfold(*_crud())
    create = result.transitions["create"]
    assert create.target == "MetricPresent"
    assert create.outcome_status == 201


def test_the_absent_atom_is_dropped_once_its_own_state_says_the_same_thing():
    """M-7 on the other side of the fold.

    The present case already loses its atom — the reader starts from
    `MetricPresent`, so `NOT (t.isEmpty())` would restate the node it leaves.
    The absent case restates its node just as much once synthesis gives the
    resource its own starting state, so it goes too: the same condition said
    twice, once as a node and once in the implementation's words.
    """
    states, transitions = _crud()
    # As synthesis now builds it: the resource's own state, not a shared `Ready`.
    states["Metric"] = State(id="Metric", name="Metric", surface="api",
                             is_initial=True, lifecycle_state=QUARANTINE)
    transitions["read-none"] = _t("read-none", "Metric", "GET /metric/{id}",
                                  "NoContent204", "t.isEmpty()", 204)
    transitions["create"] = _t("create", "Metric", "POST /metric", "Created201", "", 201)

    result = unfold(states, transitions)
    assert result.transitions["read-none"].guard == "", (
        "`Metric` already means the metric is absent")
    assert result.transitions["read-none"].source == "Metric"


def test_the_atom_survives_where_the_source_state_does_not_say_it():
    """The strip is tied to leaving the resource's OWN state, not to a global
    assumption. A transition leaving a shared `Ready` keeps its atom, because
    `Ready` means only "nothing has been called yet" and the atom is then the
    one thing saying the record is missing."""
    result = unfold(*_crud())
    assert result.transitions["read-none"].source == "Ready"
    assert result.transitions["read-none"].guard == "t.isEmpty()"


def test_the_absent_read_keeps_ready_as_its_source():
    """"Nothing exists yet" IS the initial state. Inventing an `Absent` state
    beside `Ready` would add a node meaning the same thing."""
    result = unfold(*_crud())
    assert result.transitions["read-none"].source == "Ready"
    assert result.transitions["read-none"].guard == "t.isEmpty()"


def test_the_orphaned_status_state_is_dropped():
    result = unfold(*_crud())
    assert "Created201" not in result.states, (
        "retargeting the creator leaves it unreachable; keeping it would report "
        "an unreachable-state finding about this pass rather than about the code")


def test_unfolding_makes_setup_reachable():
    """The whole point: BFS can now walk to the read's precondition."""
    from dataclasses import replace
    from metis_mcp.mbt.model import APPROVED, Model
    from metis_mcp.mbt.path_generation import generate

    result = unfold(*_crud())
    model = Model(
        id="m-api",
        states={k: replace(v, lifecycle_state=APPROVED) for k, v in result.states.items()},
        transitions={k: replace(v, lifecycle_state=APPROVED)
                     for k, v in result.transitions.items()})
    paths = generate(model, "all-transitions", 10).paths
    with_setup = [p for p in paths if p.setup_length]
    assert with_setup, "the read must now cost a setup step"
    setup_triggers = [model.transitions[t].trigger
                      for p in with_setup for t in p.setup_transition_ids]
    assert "POST /metric" in setup_triggers


# --------------------------------------------------------------------------
# Fail-closed (§5.8, T-9d). The half that stops this becoming a guess.
# --------------------------------------------------------------------------

def test_no_creator_means_no_unfold_and_an_explicit_flag():
    states = _states("Ready", "Ok200")
    transitions = {
        "read-ok": _t("read-ok", "Ready", "GET /orphan/{id}", "Ok200",
                      "NOT (t.isEmpty())", 200),
    }
    result = unfold(states, transitions)
    kept = result.transitions["read-ok"]
    assert kept.source == "Ready", "no invented source state"
    assert kept.guard == "NOT (t.isEmpty())", "the condition is not silently dropped"
    assert kept.source_state_unresolved is True
    assert result.unresolved and "no creating transition" in result.unresolved[0][1]
    assert not any(s.startswith("Orphan") for s in result.states)


def test_a_non_2xx_creator_does_not_count():
    """A POST that only ever fails creates nothing."""
    states = _states("Ready", "Ok200", "BadRequest400")
    transitions = {
        "read-ok": _t("read-ok", "Ready", "GET /thing/{id}", "Ok200",
                      "NOT (t.isEmpty())", 200),
        "create-fails": _t("create-fails", "Ready", "POST /thing", "BadRequest400",
                           "", 400),
    }
    result = unfold(states, transitions)
    assert result.transitions["read-ok"].source_state_unresolved is True


def test_the_creator_inference_is_reported_as_one():
    """It is a REST convention, not a proof — so it says so."""
    result = unfold(*_crud())
    assert result.findings
    assert "convention" in " ".join(result.findings)


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
