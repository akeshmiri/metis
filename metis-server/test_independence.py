"""
Métis stands alone (spec X-2, D-2).

**The rule: nothing outside this repository may be needed at runtime**, and a
dependency that cannot be brought in — an engine, a database — is *declared*
rather than discovered. Métis was assembled partly by porting from a sibling
project, and a port that leaves a live wire behind is not a port.

The distinction this file draws, and the reason it is not a naive grep:

  * **Coupling** is importing, executing, or reading a path from another
    project. That is forbidden and is what these tests look for.
  * **Provenance** is a comment saying where something came from. That is
    *required* — `check_design_sync.py` and the intake extractors say plainly
    that they were ported and what changed. Deleting those notes to make a grep
    pass would destroy honest attribution and the record of what was taken.

So "no mention of the word" is the wrong test. "No live wire" is the right one.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP = {".venv", "__pycache__", ".git", "node_modules", "site"}

# Every external thing Métis genuinely needs. It cannot vendor a CPG engine or a
# graph database, so independence here means DECLARED and version-pinned, never
# absent. Adding to this list should be a deliberate act, which is why it is
# asserted rather than described.
DECLARED_EXTERNALS = {
    "joern":        "the CPG engine — a sidecar by design (X-2), version-pinned per pack (X-3)",
    "neo4j":        "the single database (§16.1); reached via bolt or cypher-shell",
    "docker":       "runs the graph container locally",
    "cypher-shell": "schema application and rebuild queries",
    "claude":       "the CLI used for the few real model calls; no API key in this environment",
}

# A live wire: importing, executing, or reading a path from the sibling project.
_COUPLING = (
    re.compile(r"^\s*(?:from|import)\s+atlas", re.M | re.I),
    re.compile(r"~/\.atlas\b"),
    re.compile(r"Projects/atlas\b"),
    re.compile(r"\.agents/(?:skills|scripts)/"),
)


SELF = Path(__file__).name
TRIPLE = '"' * 3
TRIPLE_ALT = "'" * 3


def _sources():
    for path in REPO.rglob("*"):
        if path.is_dir() or any(part in SKIP for part in path.parts):
            continue
        # This file necessarily contains every pattern and binary name it
        # searches for. Both failures on the first run were it matching itself,
        # which is the classic way a guard reports a problem it created.
        if path.name == SELF:
            continue
        if path.suffix in {".py", ".sh", ".json", ".yaml", ".yml"}:
            yield path


def _in_docstring(lines: list[str], index: int) -> bool:
    """Whether this line sits inside a triple-quoted block.

    A module header spanning several lines is attribution, and only its first
    line starts with a quote — checking line-initially reported `lint.py`'s and
    `check_design_sync.py`'s provenance notes as coupling.
    """
    fences = 0
    for line in lines[:index]:
        fences += line.count(TRIPLE) + line.count(TRIPLE_ALT)
    return fences % 2 == 1


def test_nothing_imports_executes_or_reads_from_the_sibling_project():
    """The whole claim, in one assertion.

    A provenance comment naming a source file is allowed *only* inside a comment
    or docstring; a path in live code is not. `lint.py` and `check_design_sync.py`
    both cite `.agents/...` paths in their headers, which is attribution.
    """
    offenders = []
    for path in _sources():
        text = path.read_text(errors="ignore")
        lines = text.splitlines()
        for line_no, line in enumerate(lines, 1):
            stripped = line.strip()
            # Attribution lives in comments and docstrings, not in live code.
            if (stripped.startswith(("#", "//", "*", TRIPLE, TRIPLE_ALT))
                    or '"$comment"' in line
                    or '"description"' in line
                    or _in_docstring(lines, line_no - 1)):
                continue
            for pattern in _COUPLING:
                if pattern.search(line):
                    offenders.append(
                        f"{path.relative_to(REPO)}:{line_no}: {stripped[:70]}")
    assert not offenders, (
        "live dependency on another project:\n  " + "\n  ".join(sorted(offenders)))


def test_no_configuration_key_advertises_a_coupling_that_does_not_exist():
    """`metis.config.example.json` carried an `atlas` block — `endpoint_url`,
    `auth_token`, `timeout_seconds` — that **nothing read**.

    A dead config key is worse than a missing one: it reads as a supported
    integration and invites the next person to wire it.
    """
    import json

    config = json.loads((REPO / "metis-server" / "metis.config.example.json").read_text())
    assert "atlas" not in config, "the dead atlas config block is back"
    for section in config.values():
        if isinstance(section, dict):
            for key, value in section.items():
                if isinstance(value, str):
                    assert "atlas" not in value.lower() or "atlassian" in value.lower(), (
                        f"config value names another project: {key}={value}")


def test_shipped_schemas_claim_metis_own_namespace():
    """A schema whose `$id` points at another project's namespace is that
    project's schema, however local the copy is."""
    import json

    for path in (REPO / "plugins").rglob("*.schema.json"):
        schema_id = json.loads(path.read_text()).get("$id", "")
        assert "atlas" not in schema_id.lower(), (
            f"{path.name} identifies as another project's schema: {schema_id}")


def test_external_dependencies_are_declared_not_discovered():
    """Métis cannot vendor Joern or Neo4j, so independence there means the list
    is explicit. A new external binary must be added here deliberately."""
    invoked = set()
    for path in _sources():
        if path.suffix not in {".py", ".sh"}:
            continue
        text = path.read_text(errors="ignore")
        for name in ("joern", "cypher-shell", "docker", "podman", "kubectl", "npm",
                     "mvn", "gradle", "psql", "claude"):
            if re.search(rf"\b{re.escape(name)}\b", text):
                invoked.add(name)
    # `podman` is named in documentation as the preferred local runtime; it is a
    # substitute for docker rather than an addition.
    undeclared = invoked - set(DECLARED_EXTERNALS) - {"podman"}
    assert not undeclared, (
        f"undeclared external dependency: {sorted(undeclared)}. Add it to "
        f"DECLARED_EXTERNALS with the reason it cannot be brought in-repo.")


def test_provenance_notes_are_preserved_not_scrubbed():
    """The counterpart, and it matters as much.

    Making the tests above pass by deleting "Ported from Atlas" would erase the
    record of what was taken and from where. Attribution is required; coupling
    is forbidden. This asserts the notes still exist so a future cleanup cannot
    quietly remove them in the name of independence.
    """
    attributed = [p for p in _sources()
                  if re.search(r"Ported from Atlas|Atlas original", 
                               p.read_text(errors="ignore"))]
    assert attributed, (
        "no provenance notes remain — ported code must say where it came from")


# --------------------------------------------------------------------------
# The port has to be COMPLETE, or independence costs capability.
# --------------------------------------------------------------------------

def test_every_advertised_intake_source_has_a_real_extractor():
    """A partial port is the trap this whole exercise exists to avoid.

    Métis had one of Atlas's six extractors. Deleting Atlas's copy at that point
    would have removed Confluence, Swagger, Zephyr Scale, code and database —
    exactly the sources Requirements must be built from — in the name of
    independence. Independence that costs capability is a regression wearing a
    principle's clothes.

    So the routing table and the registry are checked against each other: a
    source cannot be advertised without something implementing it, and an
    extractor cannot exist unroutable.
    """
    import importlib.util
    import sys

    skill = REPO / "plugins" / "metis" / "skills" / "metis-intake-processor"
    sys.path.insert(0, str(skill))
    try:
        import extractors

        spec = importlib.util.spec_from_file_location(
            "_intake", skill / "intake_processor.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        processor = next(o for o in vars(module).values()
                         if hasattr(o, "EXTRACTORS"))

        routed = set(processor.EXTRACTORS)
        registered = {n for n in extractors.__all__ if n != "BaseExtractor"}
        assert len(routed) == len(registered), (
            f"{len(routed)} routable source(s) but {len(registered)} extractor(s) — "
            f"one of them advertises or hides a source")
        for name, cls in processor.EXTRACTORS.items():
            assert hasattr(cls, "extract"), f"{name} routes to something uncallable"
    finally:
        sys.path.remove(str(skill))


def test_no_extractor_silently_truncates_the_evidence_it_extracts():
    """The defect the Jira port found, checked across all six.

    Atlas capped `description` at 200 characters. In this pipeline that field IS
    the evidence mined into Requirements, so the cap destroyed requirement text
    mid-word — silently, and only on the long descriptions that matter most.
    `confluence_extractor` carried the identical cap on the identical field.
    """
    extractors = REPO / "plugins" / "metis" / "skills" / "metis-intake-processor" / "extractors"
    offenders = []
    for path in extractors.glob("*_extractor.py"):
        for line_no, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r'"description":.*\[:\d+\]', line):
                offenders.append(f"{path.name}:{line_no}")
    assert not offenders, (
        "these truncate the field that becomes requirement evidence: "
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


def test_no_config_key_names_a_deleted_module_or_tool():
    """The same rule as above, applied to the v1 engine rather than to Atlas.

    `.metis/config.yaml` carried a `token_optimization` block configuring
    `metis_mcp/token_optimization.py` for three MCP tools. The module and all
    three tools went with the v1 engine, and nothing has read that file since --
    so the block read as a supported control that could be switched on.

    A comment *naming* a deleted thing as deleted is fine and is how the rest of
    this tree records history. A live key is not.
    """
    import re

    text = (REPO / "metis-server" / ".metis" / "config.yaml").read_text()
    live = "\n".join(l for l in text.split("\n") if not l.lstrip().startswith("#"))

    dead_tools = ("metis_get_context", "metis_get_traceability",
                  "metis_check_coverage", "metis_impact_analysis",
                  "metis_submit_episode", "metis_list_skills")
    dead_modules = ("token_optimization", "neo4j_graph_store", "dq_metrics",
                    "structural_validation", "confidence_tiering",
                    "layer8_heuristics", "uif_intake")

    for name in dead_tools + dead_modules:
        assert name not in live, (
            f"a live config key names {name!r}, which the v1 engine took with it — "
            f"a dead key reads as a supported control"
        )


def test_no_module_writes_transitions_except_landing():
    """A second writer for an element type is how two halves of one graph come
    to disagree about what is in it.

    `behavior_model.load_transition` MERGE-d `(:Transition {id: $id})` with a
    bare id while `landing` writes `:ApiCall`/`:UiAction` with
    `{model_id}::{id}` — so calling it against a landed model would have created
    a second node per transition rather than updating the first. It had no
    caller, which is the only reason it never did.

    Transitions reach the graph through `landing.plan_landing`, and the two
    document writers reach it through the same `land()`. Nothing else may MERGE
    a transition label.
    """
    import re

    allowed = {"landing.py"}
    offenders = []
    for path in (REPO / "metis-server" / "metis_mcp").rglob("*.py"):
        if "__pycache__" in path.parts or path.name in allowed:
            continue
        text = path.read_text()
        for match in re.finditer(
                r"MERGE \(\s*\w*\s*:(Transition|ApiCall|UiAction)\b", text):
            offenders.append(f"{path.name}: MERGE (:{match.group(1)})")
    assert not offenders, (
        "a module other than landing.py creates transition nodes: "
        + ", ".join(offenders))


def test_no_module_mints_a_business_entity_id_of_its_own():
    """I-2: one natural key per noun. The glossary carried an author-chosen id
    and intake derived its own, so `api spec` landed twice with nothing marking
    either canonical. Both now go through `identity.business_entity_key`.
    """
    import re

    offenders = []
    for path in (REPO / "metis-server" / "metis_mcp").rglob("*.py"):
        if "__pycache__" in path.parts or path.name == "keys.py":
            continue
        text = path.read_text()
        # An f-string minting an entity id by hand, e.g. f"entity-{name...}".
        if re.search(r'f"entity-\{', text):
            offenders.append(path.name)
    assert not offenders, (
        f"these mint a business-entity id instead of using the natural key: "
        f"{offenders}")
