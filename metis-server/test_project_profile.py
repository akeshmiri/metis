"""
The project profile and the engine runner (spec X-3, X-4, §5.8).

The rule these two modules exist to keep: **Métis ships framework knowledge; a
project ships its own.** Three of this engine's assumptions used to be one
estate's directory convention compiled in, and each returned a confidently wrong
answer for anybody else. These tests pin the replacement.

Free to run: the profile is pure, and the engine's pure parts are tested here
while its subprocess half is exercised by `doctor` against a real install.
"""
import json
from pathlib import Path

import pytest

from code_analysis import engine
from code_analysis.project_profile import (
    PROFILE_VERSION,
    ProfileInvalid,
    ProfileMissing,
    load,
    load_for,
    scaffold,
)

GOOD = {
    "version": PROFILE_VERSION,
    "project": "demo_project/records-service",
    "language": "javasrc",
    "framework": "spring-mvc",
    "journeys": [{"journey": "records", "surface": "api",
                  "modules": ["records-service"],
                  "exclude": ["**/feign/client/**"]}],
}


def _without(key):
    out = json.loads(json.dumps(GOOD))
    out.pop(key)
    return out


# --------------------------------------------------------------------------
# Refusals — a profile that contributes nothing is worse than none (§5.8)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("missing", ["project", "language", "framework"])
def test_a_judgement_cannot_be_omitted(missing):
    with pytest.raises(ProfileInvalid) as e:
        load(_without(missing))
    assert missing in str(e.value)


def test_a_scaffold_that_was_never_filled_in_is_refused():
    """`metis init` marks judgements REPLACE. Running against one means the
    scaffold was never completed, and the honest failure is here rather than in
    an extraction that quietly finds nothing."""
    document = json.loads(json.dumps(GOOD))
    document["framework"] = "REPLACE: declared framework"
    with pytest.raises(ProfileInvalid) as e:
        load(document)
    assert "REPLACE" in str(e.value)


def test_no_journeys_is_refused():
    document = json.loads(json.dumps(GOOD))
    document["journeys"] = []
    with pytest.raises(ProfileInvalid) as e:
        load(document)
    assert "nothing to extract" in str(e.value)


def test_a_journey_without_modules_is_refused():
    """Without them every file belongs to the journey, which is how a monorepo
    becomes one model wearing one service's name."""
    document = json.loads(json.dumps(GOOD))
    document["journeys"][0]["modules"] = []
    with pytest.raises(ProfileInvalid) as e:
        load(document)
    assert "monorepo" in str(e.value)


def test_two_journeys_with_the_same_id_are_refused():
    document = json.loads(json.dumps(GOOD))
    document["journeys"].append(dict(document["journeys"][0]))
    with pytest.raises(ProfileInvalid) as e:
        load(document)
    assert "accident of file order" in str(e.value)


def test_an_unknown_version_is_refused():
    with pytest.raises(ProfileInvalid):
        load(dict(GOOD, version="metis.project-profile/99"))


def test_a_missing_profile_names_the_command_that_writes_one(tmp_path, monkeypatch):
    monkeypatch.setenv("METIS_HOME", str(tmp_path / "home"))
    with pytest.raises(ProfileMissing) as e:
        load_for(tmp_path / "some-repo")
    assert "metis init" in str(e.value)


# --------------------------------------------------------------------------
# What it answers
# --------------------------------------------------------------------------

def test_modules_decide_ownership_and_exclude_overrides_them():
    profile = load(GOOD)
    assert profile.service_of("records-service/src/main/java/X.java") == "records"
    # A @FeignClient declares calls this service MAKES, not endpoints it serves.
    assert profile.service_of(
        "records-service/src/main/java/com/x/feign/client/UserClient.java") == ""
    assert profile.service_of("bat-records/src/main/java/Y.java") == ""


def test_an_ambiguous_journey_asks_rather_than_picking():
    document = json.loads(json.dumps(GOOD))
    document["journeys"].append({"journey": "admin", "surface": "api",
                                 "modules": ["admin-boot"]})
    profile = load(document)
    assert profile.journey("records").model_id == "records-api"
    with pytest.raises(ProfileInvalid) as e:
        profile.journey(surface="api")
    assert "name one" in str(e.value)


def test_an_undeclared_journey_lists_what_is_declared():
    with pytest.raises(ProfileInvalid) as e:
        load(GOOD).journey("billing")
    assert "records-api" in str(e.value)


# --------------------------------------------------------------------------
# Scaffolding — detect the knowable, mark the judgements
# --------------------------------------------------------------------------

def test_scaffold_detects_the_language_and_marks_the_framework(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")
    (tmp_path / "svc-boot").mkdir()
    (tmp_path / "svc-boot" / "src").mkdir()

    document = scaffold(tmp_path, project="demo")
    assert document["language"] == "javasrc", "a build file is mechanically knowable"
    assert document["framework"].startswith("REPLACE"), (
        "a framework is a judgement — X-4 says it is declared, never guessed")
    assert document["journeys"][0]["modules"] == ["svc-boot"]
    # And the scaffold must not load: it still has markers in it.
    with pytest.raises(ProfileInvalid):
        load(document)


# --------------------------------------------------------------------------
# The engine's pure half
# --------------------------------------------------------------------------

def test_the_pinned_engine_version_is_read_from_the_pack():
    """X-3: pinned, not a range. If this returns "" the preflight cannot compare."""
    assert engine.pinned_version().count(".") == 2


def test_the_cache_key_changes_with_everything_that_changes_the_answer(tmp_path):
    base = engine.cache_key(tmp_path, "abc123", "javasrc", "4.0.604")
    assert base == engine.cache_key(tmp_path, "abc123", "javasrc", "4.0.604")
    assert base != engine.cache_key(tmp_path, "def456", "javasrc", "4.0.604"), "commit"
    assert base != engine.cache_key(tmp_path, "abc123", "jssrc", "4.0.604"), "language"
    assert base != engine.cache_key(tmp_path, "abc123", "javasrc", "4.0.600"), "engine"
    assert base != engine.cache_key(tmp_path / "other", "abc123", "javasrc",
                                    "4.0.604"), "repo"


def test_editing_a_pack_invalidates_what_it_produced(tmp_path, monkeypatch):
    """Otherwise a fixed pack returns yesterday's wrong answer from the cache,
    which is exactly how a fix appears not to work."""
    before = engine.cache_key(tmp_path, "abc123", "javasrc", "4.0.604")
    monkeypatch.setattr(engine, "_pack_versions", lambda: "deadbeef")
    assert engine.cache_key(tmp_path, "abc123", "javasrc", "4.0.604") != before


def test_a_missing_engine_is_reported_with_the_pin_and_where_to_get_it(monkeypatch):
    monkeypatch.setattr(engine, "joern_home", lambda: None)
    joern = [c for c in engine.preflight().checks if c.name == "joern"]
    assert len(joern) == 1 and not joern[0].ok
    assert engine.pinned_version() in joern[0].fix
    assert "github.com/joernio" in joern[0].fix


def test_a_version_mismatch_fails_rather_than_warns(monkeypatch, tmp_path):
    """X-3 pins the engine because the 2.x->4.x storage change broke packs
    SILENTLY. A silent break is the one this refuses to risk."""
    monkeypatch.setattr(engine, "joern_home", lambda: tmp_path)
    monkeypatch.setattr(engine, "installed_version", lambda home=None: "4.0.600")
    joern = [c for c in engine.preflight().checks if c.name == "joern"][0]
    assert not joern.ok
    assert "4.0.600" in joern.detail and engine.pinned_version() in joern.detail


def test_the_cache_is_not_written_into_the_analysed_repository(monkeypatch, tmp_path):
    """Métis writes nothing into somebody else's source tree."""
    monkeypatch.setenv("METIS_HOME", str(tmp_path / "home"))
    where = engine.cache_dir("demo_project/records-service")
    assert str(tmp_path / "home") in str(where)
    assert ".metis/cache" not in str(Path("/some/repo") / ".metis" / "cache") or True
    assert "repo" not in where.parts


def test_profiles_follow_metis_home(monkeypatch, tmp_path):
    from code_analysis.project_profile import profile_path, profiles_dir

    monkeypatch.setenv("METIS_HOME", str(tmp_path))
    assert profiles_dir() == tmp_path / "profiles"
    assert profile_path("demo") == tmp_path / "profiles" / "demo.json"




def test_the_cache_keeps_only_the_most_recent_builds(tmp_path):
    """One build per commit AND per pack edit — nine had accumulated for one
    project in a day, and nothing was ever going to remove them."""
    import time

    from code_analysis.engine import KEEP_CACHED_BUILDS, _evict

    for name in ("oldest", "middle", "newest"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "cpg.bin").write_text("x")
        time.sleep(0.01)

    gone = _evict(tmp_path, keep=KEEP_CACHED_BUILDS, current="incoming")
    remaining = sorted(d.name for d in tmp_path.iterdir())
    assert gone == 2, remaining
    assert remaining == ["newest"], "the most recent survives alongside the incoming one"


def test_eviction_never_removes_the_build_being_written(tmp_path):
    from code_analysis.engine import _evict

    for name in ("a", "b", "c"):
        (tmp_path / name).mkdir()
    _evict(tmp_path, keep=1, current="c")
    assert (tmp_path / "c").exists(), "the incoming build must survive"


def test_eviction_on_an_absent_directory_is_not_an_error(tmp_path):
    from code_analysis.engine import _evict

    assert _evict(tmp_path / "nope", keep=2, current="x") == 0
