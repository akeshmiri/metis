"""
`metis generate` — the CLI layer of automation generation.

**Why this file exists.** The emitters were covered by `test_generators.py` and
the join by `test_fixtures_join.py`, and the defect was in neither: `cmd_generate`
named the output files itself, so a run wrote sixteen `tc-<hash>.java` each
declaring `public class LoginApiTest` — source `javac` rejects on its first line.
Both test files stayed green because the bug lived in the seam between them.

So these tests drive `cli.main` exactly as a person would and assert on what
lands on disk, which is the only place that particular class of mistake shows.

Free to run: no Joern, no Neo4j, no network. The model is built here.
"""
from __future__ import annotations

import json
import re

from metis_mcp.mbt import cli
from metis_mcp.review.state import source_fingerprint

MODEL = {
    "id": "records-api",
    "states": [
        {"id": "Anonymous", "name": "Anonymous", "surface": "api", "is_initial": True},
        {"id": "Fetched", "name": "Fetched", "surface": "api"},
        {"id": "Rejected", "name": "Rejected", "surface": "api"},
    ],
    "transitions": [
        {"id": "t01", "source": "Anonymous", "trigger": "GET /record/{id}",
         "target": "Fetched", "guard": "record_exists",
         "implementation_status": "implemented"},
        {"id": "t02", "source": "Anonymous", "trigger": "GET /record/{id}",
         "target": "Rejected", "guard": "NOT record_exists",
         "implementation_status": "implemented"},
    ],
}


def _approved(tmp_path, model: dict = None):
    """A model file and the review overlay that approves every element of it.

    Built here rather than read from `demo_data/` on purpose: the demo model's
    own `.review.json` is not tracked in git, so a test that depended on it
    would pass on this machine and fail on a fresh clone.
    """
    from metis_mcp.mbt.cli import read_source

    data = model or MODEL
    model_path = tmp_path / f"{data['id']}.json"
    model_path.write_text(json.dumps(data))

    decision = {"lifecycle_state": "Approved", "name": None,
                "decided_by": "test", "decided_at": "2026-08-28T00:00:00+00:00",
                "rationale": "fixture: approved to exercise the generation chain"}
    (tmp_path / f"{data['id']}.review.json").write_text(json.dumps({
        "version": "metis.review-state/1",
        "model_id": data["id"],
        "source_fingerprint": source_fingerprint(read_source(str(model_path))),
        "states": {s["id"]: {**decision, "name": s["id"]} for s in data["states"]},
        "transitions": {t["id"]: dict(decision) for t in data["transitions"]},
        "audit": [],
    }))
    return model_path


def _run(*argv) -> int:
    return cli.main([str(a) for a in argv])


# ---------------------------------------------------------------------------
# The refusals, before anything is written
# ---------------------------------------------------------------------------

def test_list_names_what_works_and_what_is_refused(capsys):
    assert _run("generate", "--list") == 0
    out = capsys.readouterr().out
    assert "playwright" in out and "rest-assured" in out and "cypress" in out


def test_an_unverified_runner_is_refused_with_a_nonzero_exit(tmp_path, capsys):
    model = _approved(tmp_path)
    assert _run("generate", model, "--target", "cypress") == 1
    assert "REFUSED" in capsys.readouterr().out


def test_a_missing_fixtures_file_is_an_error_not_an_empty_set(tmp_path, capsys):
    """`--fixtures typo.yaml` meaning 'no fixtures' is how a typo becomes an
    artefact full of TODOs that reads as a modelling gap."""
    model = _approved(tmp_path)
    assert _run("generate", model, "--target", "rest-assured",
                "--fixtures", tmp_path / "nope.yaml") == 1
    assert "REFUSED" in capsys.readouterr().out


def test_a_ui_target_on_an_api_model_is_refused_and_names_the_right_one(tmp_path, capsys):
    """It used to emit a Playwright spec whose every step was a TODO — which
    reads as a modelling gap and is a target mismatch."""
    model = _approved(tmp_path)
    assert _run("generate", model, "--target", "playwright") == 1
    out = capsys.readouterr().out
    assert "REFUSED" in out and "rest-assured" in out


def test_an_unapproved_model_is_refused_before_any_file_is_written(tmp_path):
    """G1. The gate is in front of generation, not beside it."""
    model_path = tmp_path / "records-api.json"
    model_path.write_text(json.dumps(MODEL))          # no review overlay
    out = tmp_path / "out"
    # 2 is the G1 code, distinct from 4 (M-18, not well-formed) and 1 (refused
    # target). A caller scripting this has to be able to tell them apart.
    assert _run("generate", model_path, "--target", "rest-assured", "--out", out) == 2
    assert not out.exists(), "the gate ran after the directory was created"


# ---------------------------------------------------------------------------
# What lands on disk — the seam the emitter tests could not see
# ---------------------------------------------------------------------------

def test_every_java_file_written_is_named_after_the_class_it_declares(tmp_path):
    """The regression. `javac`: `class X is public, should be declared in a file
    named X.java` — sixteen files, sixteen first-line errors, suite green."""
    model = _approved(tmp_path)
    out = tmp_path / "out"
    assert _run("generate", model, "--target", "rest-assured", "--out", out) == 0

    written = sorted(out.glob("*.java"))
    assert written, "nothing was written"
    for path in written:
        declared = re.findall(r"^public class (\w+)", path.read_text(), re.M)
        assert declared == [path.stem], (path.name, declared)


def test_the_cases_of_one_model_land_in_one_file(tmp_path):
    model = _approved(tmp_path)
    out = tmp_path / "out"
    _run("generate", model, "--target", "rest-assured", "--out", out)
    written = list(out.glob("*.java"))
    assert [p.name for p in written] == ["RecordsApiTest.java"]
    assert written[0].read_text().count("@Test") >= 2


def test_fixtures_change_what_is_written(tmp_path):
    """End to end: a person authors a value, and it has to appear. The join
    reported it as `supplied` while both emitters dropped it, so `--fixtures`
    produced a byte-identical artefact."""
    model = _approved(tmp_path)
    fixtures = tmp_path / "f.yaml"
    fixtures.write_text("version: metis.fixtures/1\n"
                        "values:\n  record_exists: \"record 42\"\n")

    bare, joined = tmp_path / "bare", tmp_path / "joined"
    assert _run("generate", model, "--target", "rest-assured", "--out", bare) == 0
    assert _run("generate", model, "--target", "rest-assured",
                "--fixtures", fixtures, "--out", joined) == 0

    without = (bare / "RecordsApiTest.java").read_text()
    with_it = (joined / "RecordsApiTest.java").read_text()
    assert without != with_it, "--fixtures changed nothing in the artefact"
    assert "record 42" in with_it and "record 42" not in without


def test_the_output_says_where_a_value_came_from(tmp_path):
    """A reader must be able to tell an authored value from a recovered fact."""
    model = _approved(tmp_path)
    fixtures = tmp_path / "f.yaml"
    fixtures.write_text("version: metis.fixtures/1\n"
                        "values:\n  record_exists: \"record 42\"\n")
    out = tmp_path / "out"
    _run("generate", model, "--target", "rest-assured",
         "--fixtures", fixtures, "--out", out)
    assert "authored fixture" in (out / "RecordsApiTest.java").read_text()


def test_stdout_carries_the_source_when_no_out_directory_is_given(tmp_path, capsys):
    model = _approved(tmp_path)
    assert _run("generate", model, "--target", "rest-assured") == 0
    assert "public class RecordsApiTest" in capsys.readouterr().out
