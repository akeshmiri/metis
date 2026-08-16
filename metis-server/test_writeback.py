"""
Specification write-back tests (spec §18.4; T-15, T-18, T-19, T-20, SP-5, SP-8).

Free to run: the plan is pure and writes go to a temporary directory.
"""
import sys
import tempfile
from pathlib import Path

from metis_mcp.publishing import AFFIRMATIVE, confirm
from metis_mcp.specgen import build, dated_export, living_page
from metis_mcp.specgen.writeback import (
    CHANGED,
    MANUALLY_EDITED,
    NEW,
    UNCHANGED,
    apply,
    classify,
    content_hash,
    format_plan,
    plan_writeback,
    recorded_hash,
    spec_path,
    stamp,
)
from mbt_fixtures import login_model

AT = "2026-08-16T09:00:00+00:00"


def _docs(approved=True):
    spec = build(login_model(approved=approved), journey="login", generated_at=AT)
    return {"login": living_page(spec)}, {"login": spec}


# --------------------------------------------------------------------------
# Spec Kit layout
# --------------------------------------------------------------------------

def test_the_path_follows_spec_kits_own_layout():
    assert spec_path("/repo", "login") == Path("/repo/.specify/specs/login/spec.md")


def test_a_new_file_is_classified_new():
    with tempfile.TemporaryDirectory() as d:
        docs, specs = _docs()
        plan = plan_writeback(d, docs, specs=specs)
        assert [t.classification for t in plan.targets] == [NEW]
        assert plan.size == 1


# --------------------------------------------------------------------------
# T-18/T-19 : the confirmation gate, shared with test-case publication
# --------------------------------------------------------------------------

def test_t18_nothing_is_written_without_a_confirmation():
    with tempfile.TemporaryDirectory() as d:
        docs, specs = _docs()
        plan = plan_writeback(d, docs, specs=specs)
        result = apply(plan, confirmation=None)
        assert not result["ok"]
        assert AFFIRMATIVE in result["refused"]
        assert not spec_path(d, "login").exists(), "zero files touched"


def test_t19_a_confirmation_for_a_different_batch_size_is_refused():
    with tempfile.TemporaryDirectory() as d:
        docs, specs = _docs()
        plan = plan_writeback(d, docs, specs=specs)
        result = apply(plan, confirm(AFFIRMATIVE, "alice", plan.size + 3))
        assert not result["ok"] and "Re-confirm" in result["refused"]
        assert not spec_path(d, "login").exists()


def test_a_confirmed_write_lands_the_file():
    with tempfile.TemporaryDirectory() as d:
        docs, specs = _docs()
        plan = plan_writeback(d, docs, specs=specs)
        result = apply(plan, confirm(AFFIRMATIVE, "alice", plan.size))
        assert result["ok"] and result["confirmed_by"] == "alice"
        written = spec_path(d, "login")
        assert written.exists()
        assert "behaviour specification" in written.read_text()


def test_t20_the_gate_is_the_same_one_publication_uses():
    """One gate, one thing to assert against — two that can drift apart is how a
    write path escapes review."""
    from metis_mcp.publishing.publish import Confirmation
    import metis_mcp.specgen.writeback as wb
    import inspect
    assert "publishing.publish" in inspect.getsource(wb.apply)
    assert Confirmation.__module__ == "metis_mcp.publishing.publish"


# --------------------------------------------------------------------------
# T-15 : a file the team edited is never overwritten
# --------------------------------------------------------------------------

def test_t15_a_hand_edited_file_is_never_overwritten():
    with tempfile.TemporaryDirectory() as d:
        docs, specs = _docs()
        plan = plan_writeback(d, docs, specs=specs)
        apply(plan, confirm(AFFIRMATIVE, "alice", plan.size))

        target = spec_path(d, "login")
        target.write_text(target.read_text() + "\n\nA product owner added this.\n")

        plan2 = plan_writeback(d, docs, specs=specs)
        assert plan2.targets[0].classification == MANUALLY_EDITED
        assert plan2.size == 0, "nothing writable"
        apply(plan2, confirm(AFFIRMATIVE, "alice", 0))
        assert "A product owner added this." in target.read_text()


def test_a_file_with_no_metis_marker_is_treated_as_authored_by_the_team():
    with tempfile.TemporaryDirectory() as d:
        docs, specs = _docs()
        target = spec_path(d, "login")
        target.parent.mkdir(parents=True)
        target.write_text("# Spec: login\n\nWritten by a person.\n")
        plan = plan_writeback(d, docs, specs=specs)
        assert plan.targets[0].classification == MANUALLY_EDITED
        assert "authored by the team" in plan.targets[0].detail


def test_an_unchanged_file_is_not_rewritten():
    with tempfile.TemporaryDirectory() as d:
        docs, specs = _docs()
        plan = plan_writeback(d, docs, specs=specs)
        apply(plan, confirm(AFFIRMATIVE, "alice", plan.size))
        again = plan_writeback(d, docs, specs=specs)
        assert again.targets[0].classification == UNCHANGED
        assert again.size == 0


def test_a_model_change_is_classified_changed_and_may_be_written():
    with tempfile.TemporaryDirectory() as d:
        docs, specs = _docs()
        plan = plan_writeback(d, docs, specs=specs)
        apply(plan, confirm(AFFIRMATIVE, "alice", plan.size))

        model = login_model()
        del model.transitions["t11"]
        model.reindex()
        spec = build(model, journey="login", generated_at=AT)
        moved = {"login": living_page(spec)}
        plan2 = plan_writeback(d, moved, specs={"login": spec})
        assert plan2.targets[0].classification == CHANGED
        assert plan2.targets[0].may_write


# --------------------------------------------------------------------------
# SP-5 : an unreviewed extraction does not get the standing of a decision
# --------------------------------------------------------------------------

def test_sp5_an_unapproved_specification_is_withheld_by_default():
    with tempfile.TemporaryDirectory() as d:
        docs, specs = _docs(approved=False)
        plan = plan_writeback(d, docs, specs=specs)
        assert plan.size == 0
        assert plan.withheld and "not approved" in plan.withheld[0][1]
        assert "standing of a decision" in plan.withheld[0][1]


def test_sp5_the_override_exists_and_is_explicit():
    with tempfile.TemporaryDirectory() as d:
        docs, specs = _docs(approved=False)
        plan = plan_writeback(d, docs, specs=specs, allow_unapproved=True)
        assert plan.size == 1


# --------------------------------------------------------------------------
# The marker
# --------------------------------------------------------------------------

def test_the_marker_makes_metis_own_output_recognisable():
    stamped = stamp("# Spec\n\nbody\n")
    assert recorded_hash(stamped) == content_hash("# Spec\n\nbody\n")


def test_the_hash_excludes_the_marker_so_stamping_is_stable():
    body = "# Spec\n\nbody\n"
    assert content_hash(stamp(body)) == content_hash(body)


def test_the_plan_says_nothing_has_been_written():
    with tempfile.TemporaryDirectory() as d:
        docs, specs = _docs()
        text = format_plan(plan_writeback(d, docs, specs=specs))
        assert "Nothing has been written" in text
        assert "never overwritten" in text


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
