"""
`docs/guide/` is generated, and stays generated (spec §5, D-1).

**Why this file exists.** Seven connector manifests sat in `connectors/` and
nothing ever opened them. Four agent files in `plugins/metis/agents/` named
twelve tools that did not exist, each under a "GENERATED — do not hand-edit"
banner that no generator had honoured in a long time. Documentation drifts
silently, and the drift is invisible exactly where it matters.

So the guide is produced from the tree and this diffs it. A stale guide is a
failing build.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from metis_mcp import guide

HERE = pathlib.Path(__file__).parent
GUIDE_DIR = HERE.parent / "docs" / "guide"
ACADEMY_DIR = HERE.parent / "docs" / "academy"


@pytest.fixture(scope="module")
def pages():
    return guide.generate()


# ---------------------------------------------------------------------------
# It is generated, and it is current
# ---------------------------------------------------------------------------

def test_the_committed_guide_matches_what_the_engine_generates(pages):
    """The check that turns drift into a build failure rather than a surprise."""
    stale = []
    for name, content in sorted(pages.items()):
        path = GUIDE_DIR / name
        if not path.exists():
            stale.append(f"{name}: missing")
        elif path.read_text() != content:
            stale.append(f"{name}: differs")
    assert not stale, ("run `metis guide` and commit the result:\n  "
                       + "\n  ".join(stale))


def test_generating_twice_produces_the_same_bytes(pages):
    """Determinism, or the diff check is noise. Nothing here may depend on set
    iteration order, a clock, or a dict that happens to be ordered today."""
    assert guide.generate() == pages


def test_every_page_says_what_it_was_generated_from(pages):
    for name, content in pages.items():
        assert "*Generated from `" in content, name
        assert guide.BANNER in content, name


# ---------------------------------------------------------------------------
# It reports reality, not a number somebody typed
# ---------------------------------------------------------------------------

def test_the_ontology_page_counts_the_labels_that_exist(pages):
    from metis_mcp.ontology import labels

    assert f"{len(labels.LABELS)} labels" in pages["ontology.md"]
    for label in labels.LABELS:
        assert f"- `{label}`" in pages["ontology.md"], label


def test_the_ontology_page_warns_that_a_specialisation_replaces_its_parent(pages):
    """The single most expensive thing to not know: `MATCH (t:Transition)`
    matches nothing on a classified estate."""
    assert "written instead as `ApiCall`, `UiAction`" in pages["ontology.md"]


def test_a_staged_out_label_appears_with_the_trigger_that_would_restore_it(pages):
    from metis_mcp.ontology import labels

    for label in labels.STAGED_OUT:
        assert f"**`{label}`**" in pages["ontology.md"], label


def test_the_tools_page_lists_the_tools_that_are_registered(pages):
    """Counted from the running server, so it cannot claim seventeen when
    eighteen are registered — which CLAUDE.md and the README both did."""
    import asyncio

    from metis_mcp import server

    names = sorted(t.name for t in asyncio.run(server.mcp.list_tools()))
    assert f"{len(names)} tools registered" in pages["mcp-tools.md"]
    for name in names:
        assert f"- `{name}`" in pages["mcp-tools.md"], name


def test_the_intakes_page_names_the_command_that_runs_each_intake(pages):
    """The audit's finding, made visible: an intake with no invoker is a
    capability nobody has, and the table shows an em dash where that is true."""
    from metis_mcp import intakes

    for intake in intakes.all_intakes():
        assert f"| {intake['id']} |" in pages["intakes.md"], intake["id"]
    # At least one intake must actually name its invoker, or the em dash below
    # is the only thing the column ever shows and the table proves nothing.
    # This asserted `metis data catalogue` until the database intake was removed
    # with its layer; the general form is what the test was always about.
    commanded = [i for i in intakes.all_intakes() if i.get("command")]
    assert commanded, "no intake declares a command — the column is vacuous"
    for intake in commanded:
        assert f"`metis {' '.join(intake['command'])}`" in pages["intakes.md"]


def test_the_workflows_page_marks_where_each_one_stops_for_a_person(pages):
    from metis_mcp.workflow.stages import WORKFLOWS

    for code in WORKFLOWS:
        assert f"## `{code}`" in pages["workflows.md"], code
    assert "**yes**" in pages["workflows.md"], "no gate is marked"


# ---------------------------------------------------------------------------
# The CLI command
# ---------------------------------------------------------------------------

def test_the_check_flag_fails_on_a_drifted_page(tmp_path):
    """Perturbation, as a test: `--check` must actually be able to say no."""
    guide.write(tmp_path)
    (tmp_path / "ontology.md").write_text("a sentence nothing generated\n")
    out = subprocess.run(
        [sys.executable, "-m", "metis_mcp.mbt.cli", "guide", "--check",
         "--directory", str(tmp_path)],
        capture_output=True, text=True, cwd=HERE)
    assert out.returncode == 1
    assert "STALE" in out.stdout and "ontology.md" in out.stdout


def test_the_check_flag_passes_on_a_freshly_written_guide(tmp_path):
    guide.write(tmp_path)
    out = subprocess.run(
        [sys.executable, "-m", "metis_mcp.mbt.cli", "guide", "--check",
         "--directory", str(tmp_path)],
        capture_output=True, text=True, cwd=HERE)
    assert out.returncode == 0, out.stdout


# ---------------------------------------------------------------------------
# The academy is authored, and says so
# ---------------------------------------------------------------------------

def test_the_academy_exists_and_declares_itself_authored():
    """The distinction a reader needs: the guide is checkable and this is not.
    Mixing them would leave nobody able to tell which sentences the engine
    stands behind."""
    readme = (ACADEMY_DIR / "README.md").read_text()
    assert "Authored, not generated" in readme
    assert "not built" in readme, "the unlanded state must be stated"


def test_the_deferred_join_lesson_teaches_outcomes_that_exist():
    """The one academy claim that CAN be checked, so it is. A lesson naming a
    mechanism the engine does not have is the drift this whole file is about.

    It checked the four `JoinKind`s until the 2026-08-31 re-baseline staged out
    the labels all four joined. The lesson now teaches the principle through the
    two third-outcomes that are still live, and those are what it must name.
    """
    from metis_mcp.mbt.validation import UNVERIFIABLE

    lesson = (ACADEMY_DIR / "04-deferred-joins.md").read_text()
    assert f"`{UNVERIFIABLE}`" in lesson, "M-17's third outcome is not taught"
    assert "`unmodelled`" in lesson, "recovery's third outcome is not taught"
    assert "JoinKind" in lesson, (
        "the lesson must say what was removed, or a reader meets X-19 in the "
        "spec and finds no trace of it here")


@pytest.mark.parametrize("lesson", sorted(
    p.name for p in ACADEMY_DIR.glob("*.md")))
def test_every_rule_a_lesson_cites_exists_in_the_spec(lesson):
    """A lesson citing a rule id a reader cannot look up is worse than one
    citing none — and rule ids move. `X-8` meant two different things until
    this session: the naming-tier rule in the spec, and the deferred-join rule
    the resolution engine had taken for itself. Every citation of it was
    ambiguous and nothing could tell.
    """
    import re

    text = (ACADEMY_DIR / lesson).read_text()
    spec = (HERE.parent / "docs" / "metis-application-spec.md").read_text()
    cited = set(re.findall(r"\*\*([A-Z]{1,3}-\d+[a-z]?)\*\*", text))
    missing = sorted(rule for rule in cited if f"**{rule}." not in spec
                     and f"**{rule} " not in spec and rule not in spec)
    assert not missing, f"{lesson} cites rules the spec does not have: {missing}"


def test_the_lessons_cite_rules_at_all():
    """Guarding the guard: the parametrised check above passes trivially on a
    lesson that cites nothing."""
    import re

    cited = set()
    for path in ACADEMY_DIR.glob("*.md"):
        cited |= set(re.findall(r"\*\*([A-Z]{1,3}-\d+[a-z]?)\*\*",
                                path.read_text()))
    assert len(cited) >= 8, f"only {len(cited)} rules cited across the academy"
