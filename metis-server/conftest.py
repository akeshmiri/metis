"""
Shared fixtures. The demo corpus is built here, once per session.

**Why a CPG is built during an ordinary test run.** Before this file, the five
`query.sc` packs had no behavioural test at all: the only assertions on them were
greps for a string inside the Scala, and every correctness claim lived as prose in
`pack.yaml` naming a private repository nobody else can check out. So a pack edit
could change what Métis recovers and nothing would fail.

Joern and a JDK are prerequisites, not optional extras, and a missing one **fails**
rather than skipping — a skip here quietly restores the situation above. What is
deliberately *not* required is a database: extraction is database-free, so the
graph preflight check is ignored and no external service is needed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

DEMO = Path(__file__).parent / "demo_project"
SERVICE = DEMO / "records-service"
UI = DEMO / "records-ui"
PAGE = DEMO / "records-page"
PROFILE = DEMO / "profile.json"


def tree_hash(*roots: Path) -> str:
    """A commit-like identity for the demo tree.

    `engine.extract` defaults to `head_commit(repo)`, which for a demo living
    inside Métis is *Métis's* HEAD — so every unrelated commit would invalidate
    the cache and rebuild the CPG. Hashing the tree instead means it rebuilds when
    the demo changes and not otherwise. `cache_key` already folds in the pack
    hashes, so editing a `query.sc` still busts it, which is what makes these
    tests bite.
    """
    digest = hashlib.sha256()
    for root in roots:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


@pytest.fixture(scope="session")
def demo_profile() -> dict:
    return json.loads(PROFILE.read_text())


@pytest.fixture(scope="session")
def demo_api(demo_profile):
    """The real packs, run by the real engine, over the demo service.

    Cached across sessions by `engine.cache_key`, so this is a one-off cost on a
    cold cache and near-free afterwards.
    """
    from code_analysis import engine

    # Checked here so the failure names `metis doctor` rather than surfacing from
    # inside a CPG build, then skipped in `extract` — each preflight starts a JVM
    # to read `joern --version`, and running it twice doubled a ~7s cache hit.
    engine.preflight().require(ignore=("graph",))
    return engine.extract(
        SERVICE, language="javasrc", project="demo-records",
        framework="spring-mvc", project_annotations=demo_profile["annotations"],
        commit=tree_hash(SERVICE, PROFILE), skip_preflight=True)


@pytest.fixture(scope="session")
def demo_structural(demo_api) -> dict:
    return json.loads(demo_api.structural.read_text())


@pytest.fixture(scope="session")
def demo_behaviour(demo_api) -> dict:
    return json.loads(demo_api.behaviour.read_text())


@pytest.fixture(scope="session")
def demo_inventory(demo_api) -> dict:
    assert demo_api.inventory is not None, (
        "no test inventory was produced; the demo carries test sources and the "
        "engine is supposed to parse them from a test-rooted CPG")
    return json.loads(demo_api.inventory.read_text())


@pytest.fixture(scope="session")
def demo_ui() -> dict:
    """The React surface: `react-ui` over `demo_project/records-ui`.

    A second frontend (jssrc2cpg) and therefore a second CPG. This is the corpus
    that let `react` be declared a supported framework at all — `WebExtractedSource`
    requires `ui_states`, and no React application available before it had a
    recoverable status-setter convention.
    """
    from code_analysis import engine

    extraction = engine.extract(
        UI, language="jssrc", project="demo-records-ui", framework="react",
        commit=tree_hash(UI), skip_preflight=True)
    report = next(iter(extraction.reports.values()))
    return json.loads(report.read_text())


@pytest.fixture(scope="session")
def demo_page() -> dict:
    """The plain-DOM surface: `js-ui` over `demo_project/records-page`.

    Separate from `demo_ui` because the two packs exist for genuinely different
    shapes — a React app has no `addEventListener` at all.
    """
    from code_analysis import engine

    extraction = engine.extract(
        PAGE, language="jssrc", project="demo-records-page",
        framework="dom-events", commit=tree_hash(PAGE), skip_preflight=True)
    report = next(iter(extraction.reports.values()))
    return json.loads(report.read_text())
