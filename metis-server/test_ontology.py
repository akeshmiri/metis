"""
Ontology tests (application spec §8, D-1, D-2, ONT-001, ONT-002).

Includes the **four-place governance check**: the schema, the validator, the
catalogue and the specification document must agree, and CI must fail when they
do not (ONT-001). Two of the four are generated from one source, so this test
covers the two that are prose.

Free to run: no Neo4j needed. Applying the DDL against a live instance is
verified separately by test_ontology_live.py.
"""
import ast
import re
import sys
from pathlib import Path

from metis_mcp.ontology import (
    ALLOWED_RELATIONSHIPS,
    ANY_LABEL,
    KNOWN_LABELS,
    LABELS,
    RELATIONSHIP_TYPES,
    STAGED_OUT,
    validate,
    validate_relationship,
    validate_update,
    wildcard_relationships,
)
from metis_mcp.ontology.labels import PROVENANCE_GRADES, specialisations_of
from metis_mcp.ontology.schema import (
    FILES,
    constraints_cypher,
    relationships_cypher,
    statements,
)

SPEC = Path("../docs/metis-application-spec.md")


# --------------------------------------------------------------------------
# D-1 : every label earns its place
# --------------------------------------------------------------------------

def test_the_label_set_is_closed_and_each_label_is_argued():
    """D-1: a label exists only when something writes it AND something reads it.

    The count is pinned so growth is deliberate. `Page` was the thirteenth, added
    with both halves named: the react-ui synthesiser writes it, and the Web
    pattern query reads it — a question nothing could ask while the screen name
    survived only as a substring inside a transition id.

    The nine that follow are the evidence layer, admitted together because they
    are one claim: the processed intake belongs in the graph, so the control flow
    can say what it was derived from. §8.7 staged four of them for exactly this
    and D-11 calls that list a staging plan.

    The fifty-sixth is `NeedReview`, and it is a different kind of label: a
    marker carried alongside a node's real one rather than a thing in the world.
    It earns its place on the single question `lifecycle_state` cannot answer —
    "everything awaiting a decision, across every label" — and it is kept in
    step with that property by `test_the_marker_cannot_disagree_with_lifecycle`
    below, because a second representation of one fact is only safe while
    something proves they agree.

    **Read this before adding the fifty-seventh.** D-1 opens by saying the previous
    ontology carried ~45 labels where this application needed twelve, and that
    keeping the rest "would advertise capability that does not exist — the precise
    failure this specification corrects". The count is past that again.

    That is not automatically the same mistake. Every label added since carries a
    named writer and a named reader, which the original thirty-three did not, and
    the business, Web and data layers were each asked for by name to answer a
    question the graph genuinely could not. But the number is a warning to heed
    rather than explain away, and the check on any further growth is the one this
    test enforces: name the writer, name the reader, and if either is "a file
    somebody will write one day", stage it in §8.7 instead.
    """
    assert len(KNOWN_LABELS) == 63, (
        f"the ontology is sixty-two labels (spec D-1); found {len(KNOWN_LABELS)}: "
        f"{sorted(KNOWN_LABELS)}. Adding one requires naming its writer and its "
        f"reader, not just its purpose."
    )


# The tens-and-units words the module docstring could plausibly use for a count.
# Written out rather than computed: three lines of table beat a spelling engine
# nobody else needs.
_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty"}
_UNITS = {0: "", 1: "-one", 2: "-two", 3: "-three", 4: "-four", 5: "-five",
          6: "-six", 7: "-seven", 8: "-eight", 9: "-nine"}
_COUNT_WORD = re.compile(
    r"\b(?:twenty|thirty|forty|fifty|sixty)(?:-(?:one|two|three|four|five|six|"
    r"seven|eight|nine))?\b", re.IGNORECASE)


def _spelled(n: int) -> str:
    return _TENS[n // 10] + _UNITS[n % 10]


def test_the_module_docstring_states_the_real_count():
    """`labels.py`'s own docstring says it is checked here. It was not.

    The docstring claimed fifty-two while the module carried fifty-five, and the
    test above did not catch it because it pins the *number*, not the prose that
    describes it. A docstring asserting it is verified, which nothing verifies, is
    the silent success this repo hunts for: the reader trusts it precisely because
    of the claim.

    Every tens-word in the docstring must therefore be the real count. If a future
    edit legitimately mentions a different one -- "the v1 ontology carried
    forty-five" -- that sentence needs rewording or this test needs a narrower
    scope, and either is a decision worth making deliberately.
    """
    from metis_mcp.ontology import labels

    expected = _spelled(len(KNOWN_LABELS))
    found = {m.group(0).lower() for m in _COUNT_WORD.finditer(labels.__doc__ or "")}
    assert found == {expected}, (
        f"the module docstring names {sorted(found) or 'no count'} where the "
        f"ontology has {len(KNOWN_LABELS)} labels ({expected}). The docstring "
        f"says it is checked against the module by this test -- keep that true."
    )


# D-1 demands a named writer AND a named reader. A label with only a writer is
# how an ontology accretes — `Revision` is declared here with neither and is the
# standing example of what this test exists to prevent.
EVIDENCE_LAYER = {
    "Endpoint": ("raw_landing", "Transition-[:DERIVED_FROM]->"),
    "Parameter": ("raw_landing", "Transition-[:EXERCISES]->"),
    "Class": ("raw_landing", "Parameter-[:OF_TYPE]-> and Transition-[:EXPECTS]->"),
    # A specialisation of Class, so it is reached by the same edges — which is
    # exactly why every one of them must be matched with
    # `label_expression("Class")`. Its reader is also `Field-[:OF_TYPE]->`, the
    # nested-payload edge: a field of an enum type is how a test case learns its
    # value space is closed and enumerable rather than needing a boundary
    # analysis.
    "Enum": ("raw_landing", "Field-[:OF_TYPE]-> and Parameter-[:OF_TYPE]->"),
    # X-19a. Written as its dialect (`Postgres`/`Oracle`/`MySql`/`JpaQuery`), so
    # every one of these is reached through `label_expression("Query")`. The
    # reader is what makes a table reachable from a transition at all.
    "Query": ("code_analysis.jpa via raw_landing",
              "Method-[:ISSUES]-> and Query-[:QUERIES]->Table"),
    # `Field` was here until X-6d. A field is a property of its type now, and
    # `Transition-[:REQUIRES]->Class` names the type whose constraints a case
    # must satisfy — see STAGED_OUT for what would bring the label back.
    "Method": ("raw_landing", "Endpoint-[:HANDLED_BY]->"),
    "DeclaredOutcome": ("raw_landing", "Transition-[:DERIVED_FROM]->"),
    "Check": ("raw_landing", "Transition-[:CONSTRAINED_BY]->"),
    "ExceptionMapping": ("raw_landing", "ExceptionMapping-[:HANDLED_BY]->Method"),
    "Route": ("raw_landing", "Route-[:RENDERS]->Page"),
    # The five intake anchors. Writer: `intake_landing`, from a UIF's
    # `scope` block. Reader: the traceability chain §7.8 ends on --
    # TestCase -> Scenario -> Transition -> AcceptanceCriterion -> Requirement
    # -> the anchor -- which is what answers "what artefact in the world is
    # this test ultimately about".
    "ConfluenceItem": ("intake_landing", "ConfluenceItem-[:REPRESENTS]->Requirement"),
    "OpenApiItem": ("intake_landing", "OpenApiItem-[:REPRESENTS]->Requirement"),
    "ZephyrItem": ("intake_landing", "ZephyrItem-[:REPRESENTS]->Requirement"),
    "DatasourceItem": ("intake_landing", "DatasourceItem-[:REPRESENTS]->Requirement"),
    "CodeItem": ("intake_landing", "CodeItem-[:REPRESENTS]->Requirement"),
    # The two document labels. Writer: `specgen`. Reader: the MCP surface's
    # `get_spec` / `get_entity`, which is the whole point of putting the
    # document in the graph rather than in a file.
    "SpecDocument": ("specgen.specification", "SpecDocument-[:DESCRIBES]->Component"),
    "EntityDocument": ("specgen.entity", "EntityDocument-[:DESCRIBES]->BusinessEntity"),
}


def test_every_evidence_label_participates_in_the_catalogue():
    """The half of D-1 that is easy to skip: a writer alone means the graph grows
    and nothing asks it anything.

    Participation, not target-ness. An entry node is legitimately a source only —
    `Route` is where a UI query *starts*, and requiring something to point at it
    would mean inventing an edge to satisfy a test. What must never happen is a
    label that appears in no relationship at all.
    """
    # **Specialisations participate through their parent's edges**, because that
    # is what `is_allowed` does: it walks the specialisation chain. Reading the
    # catalogue literally said `Enum` appears in no relationship at all, while
    # `is_allowed("Field", "OF_TYPE", "Enum")` was True — the test and the
    # function would have disagreed about the same ontology.
    used = set()
    for r in ALLOWED_RELATIONSHIPS:
        used |= set(specialisations_of(r.to_label))
        used |= set(specialisations_of(r.from_label))
    for label in EVIDENCE_LAYER:
        assert label in KNOWN_LABELS, f"{label} is claimed but not declared"
        assert label in used, (
            f"{label} is written and appears in no relationship — D-1 requires a "
            f"reader, not just a purpose")


# What the control flow must be able to reach. `Route` and the call graph are
# reached from their own layer (Route -> Page, Endpoint -> Method), not from a
# transition, so they are deliberately absent.
#
# `Field` was here until X-6d. A field is a property of its type now, so the
# thing a transition must reach is the TYPE — `Transition-[:REQUIRES]->Class` —
# and the field detail travels on it. Dropping the entry without repointing
# REQUIRES would have removed the requirement rather than restated it.
REACHED_FROM_TRANSITION = {
    "Endpoint", "DeclaredOutcome", "ExceptionMapping",
    "Parameter", "Class", "Check",
}


def test_the_control_flow_can_reach_its_own_evidence():
    """D-14: provenance is an edge, not a property.

    `source_episode_id` says which ingest produced an element and cannot say
    which endpoint, outcome or field — so every fact a reviewer or a generator
    needs must be reachable from the transition itself.
    """
    from_transition = {r.to_label for r in ALLOWED_RELATIONSHIPS
                       if r.from_label == "Transition"}
    missing = REACHED_FROM_TRANSITION - from_transition
    assert not missing, f"a transition cannot reach {sorted(missing)}"


def test_acceptance_criterion_can_store_its_s19_grade():
    """Spec D-9b. A grade the graph cannot hold is a grade that does not exist.

    `review/decisions.py:promotion_for` computed the promoted grade correctly
    from the day it was written, and `AcceptanceCriterion` had no property to put
    it in — so every promotion was discarded and "0 intent-backed criteria" was a
    structural fact, not a review backlog.
    """
    spec = LABELS["AcceptanceCriterion"]
    assert "provenance" in spec.enums, "S-19's grade must be a declared enum"
    assert spec.enums["provenance"] == PROVENANCE_GRADES
    assert "provenance" in spec.indexed, (
        "the question this answers is a filter — 'which criteria here are still "
        "code_derived' — not a lookup")


def test_the_grade_enum_has_one_definition_shared_with_the_matcher():
    """D-2: two places that cannot drift beat two kept in step by discipline."""
    from metis_mcp.reconciliation import matching
    assert matching.PROVENANCE_GRADES is PROVENANCE_GRADES


def test_a_partial_update_is_gated_on_enums_without_demanding_required_props():
    """`SET n.provenance = ...` must be checkable (D-10, ONT-012).

    `validate` rightly demands the whole required set for a *candidate node*, so
    running an update through it fails on properties the node already has. That
    mismatch is why every `SET` in this codebase skipped the gate entirely.
    """
    assert validate_update("AcceptanceCriterion",
                           {"provenance": "human_confirmed"}).valid
    bad = validate_update("AcceptanceCriterion", {"provenance": "vouched_for"})
    assert not bad.valid
    assert "vouched_for" in bad.errors[0]
    # The distinction from `validate` is the point of the function existing.
    assert not validate("AcceptanceCriterion", {"provenance": "human_confirmed"}).valid


def test_a_partial_update_still_refuses_an_unknown_label():
    assert not validate_update("Sprint", {"name": "x"}).valid


def test_staged_out_labels_each_name_their_return_trigger():
    """Spec D-11: the exclusion list is a staging plan, not a rejection."""
    assert STAGED_OUT, "the excluded labels must be recorded, not merely absent"
    for label, trigger in STAGED_OUT.items():
        assert label not in KNOWN_LABELS, f"{label} is both staged out and active"
        assert trigger.strip(), f"{label} has no trigger for its return"


def test_every_label_has_a_purpose():
    for label, spec in LABELS.items():
        assert spec.purpose.strip(), f"{label} has no stated purpose"


# --------------------------------------------------------------------------
# ONT-002 : rejection, never auto-creation
# --------------------------------------------------------------------------

def test_unknown_label_is_rejected():
    result = validate("Goal", {"id": "g1", "source_episode_id": "e1", "name": "Goal"})
    assert not result.valid
    assert "closed" in result.errors[0]


def test_missing_required_property_is_rejected():
    result = validate("Transition", {"id": "t1", "source_episode_id": "e1", "name": "t1"})
    assert not result.valid
    missing = " ".join(result.errors)
    for prop in ("trigger", "guard_expression", "implementation_status", "surface"):
        assert prop in missing, f"{prop} should be reported missing"


def test_empty_string_counts_as_missing():
    result = validate("JiraItem", {"id": "j1", "source_episode_id": "e1",
                                   "name": "PROJ-1", "jira_key": "  ", "issue_type": "Story"})
    assert not result.valid
    assert "jira_key" in result.errors[0]


def test_enum_membership_is_enforced_by_the_gate_not_the_schema():
    """Spec ONT-012: the schema guarantees presence, this gate guarantees membership."""
    base = {"id": "t1", "source_episode_id": "e1", "name": "t1", "trigger": "click",
            "guard_expression": "", "implementation_status": "implemented"}
    assert validate("Transition", {**base, "surface": "api"}).valid
    bad = validate("Transition", {**base, "surface": "cli"})
    assert not bad.valid and "surface" in bad.errors[0]


def test_episode_is_exempt_from_source_episode_id():
    """An Episode is the provenance record; it cannot point at one."""
    result = validate("Episode", {"id": "e1", "name": "ep", "t_recorded": "2026-01-01",
                                  "source_connector": "jira", "job_id": "j1"})
    assert result.valid, result.errors
    assert "source_episode_id" not in LABELS["Episode"].all_required


def test_valid_node_passes():
    assert validate("Scenario", {
        "id": "p1", "source_episode_id": "e1", "name": "path",
        "criterion": "all-transitions", "generator_version": "1",
    }).valid


# --------------------------------------------------------------------------
# Relationship catalogue
# --------------------------------------------------------------------------

def test_catalogued_relationship_is_allowed():
    assert validate_relationship("State", "WHEN", "Transition").valid
    assert validate_relationship("Transition", "THEN", "State").valid
    assert validate_relationship("AcceptanceCriterion", "VALIDATES", "Transition").valid


def test_uncatalogued_triple_is_rejected_with_the_permitted_set():
    result = validate_relationship("Transition", "WHEN", "State")
    assert not result.valid
    assert "(State)-[:WHEN]->(Transition)" in result.errors[0], (
        "the error should name what IS permitted, not merely what is not"
    )


def test_testcase_cannot_link_directly_to_a_requirement():
    """Spec D-4: traceability always routes through an AcceptanceCriterion."""
    assert not validate_relationship("TestCase", "VERIFIES", "Requirement").valid


def test_unknown_relationship_type_is_rejected():
    result = validate_relationship("State", "TRACES_TO", "Transition")
    assert not result.valid
    assert "closed" in result.errors[0]


def test_only_one_wildcard_relationship_exists():
    """A documented exception, not an unenforced hole.

    There were two. `HAS_REVISION` went with `Revision` when it was staged out:
    a wildcard edge into a label nothing wrote is the widest possible hole in a
    closed catalogue, and it was there to serve a temporal design that does not
    exist yet.
    """
    assert set(wildcard_relationships()) == {"ABOUT"}


def test_triggering_a_flow_and_observing_it_are_different_edges():
    """Spec M-5a. One edge conflated two claims and the graph read as though the
    two flows merged — a page *starts* an API call and then continues its own
    flow, and a failing call frequently produces no UI transition at all."""
    assert validate_relationship("UiAction", "TRIGGERS", "ApiCall").valid
    assert validate_relationship("UiAction", "INVOKES", "ApiCall").valid
    # Direction is part of the claim: an API call does not start a UI flow.
    assert not validate_relationship("ApiCall", "TRIGGERS", "UiAction").valid
    assert not validate_relationship("ApiCall", "INVOKES", "UiAction").valid


def test_a_specialisation_narrows_its_parent_and_inherits_the_rest():
    """`:ApiCall` rides alongside `:Transition`, never instead of it — which is
    what lets the graph name the two surfaces while the engine keeps one
    traversal and therefore one definition of a flow."""
    base = {"id": "t", "source_episode_id": "e", "name": "n", "trigger": "GET /x",
            "guard_expression": "", "implementation_status": "implemented"}
    assert validate("ApiCall", {**base, "surface": "api"}).valid
    assert validate("UiAction", {**base, "surface": "ui"}).valid
    # The narrowing is real.
    assert not validate("ApiCall", {**base, "surface": "ui"}).valid
    # And the inheritance is real: an unguarded transition is normal, and
    # forgetting to inherit `may_be_empty` would reject every one of them.
    assert LABELS["ApiCall"].specialises == "Transition"
    assert "guard_expression" in LABELS["ApiCall"].all_may_be_empty


# --------------------------------------------------------------------------
# D-2 / ONT-001 : the four places agree
# --------------------------------------------------------------------------

def test_generated_schema_covers_every_label():
    cypher = constraints_cypher()
    for label in KNOWN_LABELS:
        assert f"(n:{label})" in cypher, f"{label} has no constraint in the generated schema"


def test_generated_schema_covers_every_relationship_type():
    cypher = relationships_cypher()
    for rel_type in RELATIONSHIP_TYPES:
        assert f"[x:{rel_type}]" in cypher, f"{rel_type} has no index (spec ONT-011)"


def test_generated_schema_has_no_duplicate_index_names():
    names = re.findall(r"CREATE (?:INDEX|CONSTRAINT) (\w+)",
                       constraints_cypher() + relationships_cypher())
    duplicates = {n for n in names if names.count(n) > 1}
    assert not duplicates, f"duplicate schema object names: {duplicates}"


def test_checked_in_schema_matches_the_generator():
    """A hand-edit to the generated file is exactly the drift generation prevents."""
    for name, generator in FILES.items():
        path = Path("schema") / name
        assert path.exists(), f"{path} missing — run: python3 -m metis_mcp.ontology.schema --write"
        assert path.read_text() == generator(), (
            f"{path} differs from the generator. Do not hand-edit; regenerate."
        )


def test_specification_document_lists_the_same_labels():
    """ONT-001's fourth place: the prose catalogue in §8.2."""
    if not SPEC.exists():
        return  # spec not adjacent in this checkout; the other three still agree
    text = SPEC.read_text()
    section = text[text.index("### 8.2 Labels"):text.index("### 8.3 Relationships")]
    for label in KNOWN_LABELS:
        assert f"`{label}`" in section, (
            f"{label} is in the code but not in §8.2 of the specification (ONT-001)"
        )


def test_specification_document_lists_the_same_relationships():
    if not SPEC.exists():
        return
    text = SPEC.read_text()
    section = text[text.index("### 8.3 Relationships"):text.index("### 8.4 Versioning")]
    for spec in ALLOWED_RELATIONSHIPS:
        assert f"`{spec.rel_type}`" in section, (
            f"{spec.rel_type} is in the code but not in §8.3 (ONT-001)"
        )


def test_statements_split_cleanly():
    stmts = statements(constraints_cypher())
    assert stmts and all(s.endswith(";") for s in stmts)
    assert not any(s.lstrip().startswith("//") for s in stmts)


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


def test_episode_is_reachable_by_property_and_that_is_the_decision():
    """`Episode` is in no relationship, which reads as a D-1 violation until you
    see the property.

    Every node carries `source_episode_id` — a baseline requirement — and it is
    indexed on every non-exempt label, so "everything this ingestion produced"
    is a lookup rather than a scan. An `Episode -[:PRODUCED]-> *` edge would be
    one edge per node restating a fact the node already carries, and two
    representations that can disagree.
    """
    from metis_mcp.ontology.labels import BASELINE_EXEMPT, BASELINE_REQUIRED
    from metis_mcp.ontology.schema import constraints_cypher

    assert "source_episode_id" in BASELINE_REQUIRED
    assert "Episode" in BASELINE_EXEMPT

    cypher = constraints_cypher()
    for label in KNOWN_LABELS:
        if label in BASELINE_EXEMPT:
            continue
        assert f"FOR (n:{label}) ON (n.source_episode_id)" in cypher, (
            f"{label} does not index the provenance property, so reaching its "
            f"Episode is a full scan")


def test_a_semicolon_inside_a_comment_does_not_eat_the_next_statement():
    """The generated schema contains one, and it cost three uniqueness constraints.

    `Episode`'s purpose line is "Immutable record of one ingested unit;
    everything derived points here". Splitting on `;` before stripping `//`
    lines cut inside that comment, orphaned its tail, and glued the prose onto
    the following `CREATE CONSTRAINT` — which Neo4j then refused. The database
    came up missing `episode_id_unique`, `jira_item_id_unique`, `page_id_unique`
    and `rel_c_o_v_e_r_s_sequence`, and nothing said so.
    """
    text = (
        "// Immutable record of one ingested unit; everything derived points here\n"
        "CREATE CONSTRAINT episode_id_unique IF NOT EXISTS "
        "FOR (n:Episode) REQUIRE n.id IS UNIQUE;\n"
        "// another; comment\n"
        "CREATE INDEX page_component IF NOT EXISTS FOR (n:Page) ON (n.component);\n"
    )
    out = statements(text)
    assert len(out) == 2, out
    assert out[0].startswith("CREATE CONSTRAINT episode_id_unique")
    assert out[1].startswith("CREATE INDEX page_component")
    assert not any("derived points here" in s for s in out)


def test_every_generated_statement_is_one_create():
    """The real files, not a fixture: no chunk may carry stray prose.

    A statement that does not begin with CREATE is the signature of the split
    above, whatever produced it.
    """
    for generator in FILES.values():
        for stmt in statements(generator()):
            assert stmt.startswith("CREATE "), stmt[:120]


def test_the_marker_cannot_disagree_with_lifecycle():
    """`NeedReview` is derived from `lifecycle_state`, never independent of it.

    Two representations of one fact is where most of this codebase's real
    defects have come from, so the second one is only safe while something
    proves it agrees with the first. This is that proof for the planning half;
    `test_landing.py` covers the write, and the removal on decision is covered
    where the decision is recorded.
    """
    from metis_mcp.model_sources.landing import PlannedNode, _with_marker
    from metis_mcp.ontology.labels import (
        LIFECYCLE_STATES, NEED_REVIEW, NEEDS_REVIEW_STATES,
    )

    node = PlannedNode(label="State", properties={})
    for state in LIFECYCLE_STATES:
        marked = NEED_REVIEW in _with_marker(node, {"lifecycle_state": state})
        assert marked == (state in NEEDS_REVIEW_STATES), (
            f"{state}: marker={marked}, but NEEDS_REVIEW_STATES says "
            f"{state in NEEDS_REVIEW_STATES}")

    # A node with no lifecycle at all is a FACT, not a candidate. An Endpoint or
    # an Episode is not reviewed, and marking one would put evidence in a queue
    # nobody can clear.
    assert NEED_REVIEW not in _with_marker(node, {})

    # And it never displaces a label the node already carries.
    both = _with_marker(PlannedNode(label="Component", properties={}, also=("Cached",)),
                        {"lifecycle_state": "Quarantine"})
    assert "Cached" in both and NEED_REVIEW in both


def test_the_marker_carries_no_properties_of_its_own():
    """A marker that accreted properties would become a second place to look."""
    from metis_mcp.ontology.labels import LABELS, NEED_REVIEW

    spec = LABELS[NEED_REVIEW]
    assert spec.required == (), "the node's real label carries its properties"
    assert spec.enums == {}
    assert not spec.is_specialisation, (
        "a specialisation REPLACES its parent; this is carried alongside one")


def test_relationships_with_no_writer_are_named_as_such():
    """D-1 wants a named writer AND a named reader for everything catalogued.

    Three relationships have neither: `LINKS_TO` (Jira issue links, which
    `intake_landing` would write), and `ON_EVENT`/`RENDERS` (the UI surface,
    whose packs are declared `status: unwired`). They stay in the catalogue
    because each has a real intended writer — but a gap nobody has written down
    is a gap somebody rediscovers, so this asserts the comment is there.

    When a writer appears, delete its name from here and from the comment.
    """
    source = Path("metis_mcp/ontology/labels.py").read_text()
    for rel, why in (("LINKS_TO", "written by nothing"),
                     ("ON_EVENT", "nothing writes either"),
                     ("RENDERS", "nothing writes either")):
        assert rel in source
    assert "Catalogued, written by nothing" in source
    assert "status: unwired" in source


# ---------------------------------------------------------------------------
# Cypher may not name a label the ontology does not have (D-2, fifth place)
# ---------------------------------------------------------------------------
#
# The bug this exists for: staging out `Field` (X-6d) left
# `(t)-[:REQUIRES]->(f:Field)` in `read.py`. It stayed valid Cypher, matched
# nothing, and returned an empty list -- so `get_transition` reported a payload
# of no fields for every transition that had one. Nothing failed. It was found by
# calling the tool, which is the expensive way.
#
# D-2 already requires four places to agree when the ontology changes. Cypher
# written by hand is the fifth, and it is the one no generator covers.

_NODE_PATTERN = re.compile(r"\(\s*\w*\s*:\s*([A-Za-z_|`\s]+?)\s*[){]")
_IS_CYPHER = re.compile(r"\b(MATCH|MERGE|CREATE|OPTIONAL MATCH)\b")


def _labels_in_cypher(text: str) -> set[str]:
    """Node labels named by a Cypher string.

    Node patterns only: `-[:REQUIRES]->` is a relationship type and lives in a
    different namespace, so anchoring on `(` is what keeps the two apart.
    """
    out: set[str] = set()
    for match in _NODE_PATTERN.finditer(text):
        for token in match.group(1).split("|"):
            token = token.strip().strip("`")
            if token.isidentifier() and token[:1].isupper():
                out.add(token)
    return out


def _cypher_strings():
    """`(path, lineno, text)` for every string literal that looks like Cypher."""
    roots = (Path("metis_mcp"), Path("code_analysis"))
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if path.name == "labels.py":
                continue          # the source of truth, not a consumer of it
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant)
                        and isinstance(node.value, str)
                        and _IS_CYPHER.search(node.value)):
                    yield path, node.lineno, node.value


def test_the_label_scanner_reads_node_labels_and_not_relationship_types():
    """**The guard's own guard.**

    A scan that finds nothing is indistinguishable from a scan that cannot see,
    and this session has already shipped two guards that passed with their fix
    reverted. So the extractor is asserted against the exact shape of the bug it
    was written for before it is trusted to report on the tree.
    """
    sample = ("MATCH (t:Transition|ApiCall)-[:REQUIRES]->(f:Field) "
              "OPTIONAL MATCH (t)-[:GUARDED_BY]->(c:Check {order: 1}) "
              "MERGE (:Episode)")
    assert _labels_in_cypher(sample) == {
        "Transition", "ApiCall", "Field", "Check", "Episode"}, (
        "the extractor must see specialisations, staged-out labels and "
        "map-suffixed patterns")
    assert "REQUIRES" not in _labels_in_cypher(sample), "relationship type"
    assert "GUARDED_BY" not in _labels_in_cypher(sample), "relationship type"


def test_the_scanner_finds_the_cypher_that_is_actually_in_the_tree():
    """And that it is pointed at something. An empty corpus passes anything."""
    seen = list(_cypher_strings())
    assert len(seen) > 20, f"only {len(seen)} Cypher strings found — scan is wrong"
    assert any(_labels_in_cypher(text) for _, _, text in seen)


def test_no_cypher_names_a_label_the_ontology_does_not_have():
    """Staging a label out must break every query that names it, loudly.

    A staged-out label is the interesting failure: `Field` was removed
    deliberately and correctly, and the cost was a query that silently matched
    nothing for weeks. `STAGED_OUT` is therefore *not* accepted here — it is the
    set most likely to be left behind.
    """
    offences = []
    for path, lineno, text in _cypher_strings():
        for label in sorted(_labels_in_cypher(text)):
            if label in LABELS:
                continue
            why = ("staged out — see STAGED_OUT" if label in STAGED_OUT
                   else "not in the ontology")
            offences.append(f"{path}:{lineno} names :{label} ({why})")
    assert not offences, (
        "Cypher names labels the ontology does not have. A query naming a "
        "label that no longer exists is valid Cypher that matches nothing:\n  "
        + "\n  ".join(offences))


def test_evidence_relationships_name_real_labels():
    """Every label in `EVIDENCE_RELATIONSHIPS` must exist and the edge it maps
    to must be legal.

    The test above scans Cypher *strings*; this map is a Python dict, so it went
    unchecked. It carried `"Field": "REQUIRES"` after `Field` was staged out
    (X-6d), and the consequence was not a dead entry. Landing plans an evidence
    edge for any mapped label, and the plan is validated after it is built, so a
    single field on a rejection put "unknown label 'Field'" into `plan.errors`
    and `land`/`land_model` refused the ENTIRE model with "nothing was written".

    Asserted against the ontology rather than against a copy of the map, so
    staging a label out is enough to fail this — no second list to remember.
    """
    from metis_mcp.model_sources.landing import EVIDENCE_RELATIONSHIPS

    offences = []
    for label, rel_type in EVIDENCE_RELATIONSHIPS.items():
        if label not in LABELS:
            why = ("staged out — see STAGED_OUT" if label in STAGED_OUT
                   else "not in the ontology")
            offences.append(f"{label!r} -> {rel_type!r}: {why}")
            continue
        # The edge is planned FROM a transition, and a classified transition
        # carries `:ApiCall`/`:UiAction` instead of `:Transition`, so every
        # concrete surface has to accept it.
        for source in ("ApiCall", "UiAction"):
            outcome = validate_relationship(source, rel_type, label)
            if not outcome.valid:
                offences.append(
                    f"({source})-[:{rel_type}]->({label}) is planned by "
                    f"landing and refused by the catalogue: {outcome.errors}")

    assert not offences, (
        "EVIDENCE_RELATIONSHIPS names something the ontology will refuse. Each "
        "of these makes landing refuse the whole model, not just the edge:\n  "
        + "\n  ".join(offences))


# Rule ids cited in code that the specification does not define.
#
# `PLT-*` is an entire rule family with no section in the spec: the code
# implements and documents it (`mbt/graph_session.py` is the fullest statement --
# resolution order for a graph connection, no default password, and a secret that
# must never reach a process listing or shell history), and cites it eleven
# times, but §-anything never introduces it. CLAUDE.md quotes PLT-005 as though
# it were settled.
#
# Listed rather than silently tolerated, and listed rather than invented: writing
# normative text into the authoritative spec is an authoring decision, not a
# test's to make. Deleting an entry here once the section exists is the whole
# fix. Nothing may be ADDED to this list without the same conversation.
# Empty. `PLT-002`, `PLT-003` and `PLT-005` are defined in §11.0 of the
# specification now — they were cited eleven times in code and written nowhere,
# which is a dangling reference that reads as authority.
#
# Kept as a named set rather than deleted: the guard below needs somewhere to
# record "known, and here is why" if a citation ever legitimately precedes its
# definition. An empty exemption list is a stronger statement than no list.
UNDEFINED_RULE_IDS: dict[str, str] = {}

_RULE_ID = re.compile(r"\b(?:M|S|P|D|GD|N|X|T|C|PLT|R|A|G)-[0-9]+[a-z]?\b")


def test_every_rule_id_cited_in_code_is_defined_in_the_spec():
    """The code cites spec rule ids inline; a citation of a rule nobody wrote is
    a dangling reference that reads as authority.

    This is the traceability direction that was never checked. The spec defines
    285 ids and the code cites 178; all but the `PLT-*` family resolve, and that
    family resolves nowhere at all.
    """
    spec_ids = set(_RULE_ID.findall(SPEC.read_text()))

    cited: dict[str, list[str]] = {}
    for path in sorted(Path(".").glob("metis_mcp/**/*.py")) + \
            sorted(Path(".").glob("code_analysis/**/*.py")):
        for rule_id in _RULE_ID.findall(path.read_text()):
            cited.setdefault(rule_id, []).append(str(path))

    dangling = {r: sorted(set(p))[:3] for r, p in cited.items()
                if r not in spec_ids and r not in UNDEFINED_RULE_IDS}
    assert not dangling, (
        "code cites rule ids the specification does not define:\n  "
        + "\n  ".join(f"{r} — cited in {', '.join(p)}"
                      for r, p in sorted(dangling.items())))

    # The exemption list may not outlive the gap it records.
    stale = {r for r in UNDEFINED_RULE_IDS if r in spec_ids}
    assert not stale, (
        f"{sorted(stale)} are defined in the spec now — delete them from "
        f"UNDEFINED_RULE_IDS")


# Read queries that touch a validity-carrying label and do NOT filter on it.
#
# Harmless TODAY and dangerous the moment it is not: nothing sets `valid_to` yet,
# so every node is currently valid and an unfiltered read cannot return a
# superseded fact. The instant an invalidation path exists, each of these starts
# returning history as though it were current — and that failure looks exactly
# like success, which is why it is listed rather than left to be noticed.
#
# Emptying this list is the rest of the bi-temporal work.
# Empty. Every read over a validity-carrying label now filters on it.
#
# Kept as a named, asserted-against set rather than deleted: the guard below
# fails when a NEW query reads one of these labels without filtering, and it
# needs somewhere to say "known, and here is why" if that is ever the right
# answer. An empty exemption list is a stronger statement than no list.
UNFILTERED_VALIDITY_READS: dict[str, str] = {}


def test_every_read_over_a_validity_label_filters_on_validity_or_is_listed():
    """A query that ignores `valid_to` answers "what did we ever believe", not
    "what do we believe now" — and returns the first while looking like the
    second.

    **Inspects the module's actual constants, not its source text.** The first
    version regexed the file, and reported a false gap the moment a query was
    built by concatenation rather than as one literal, because the pattern
    captured only the fragment before the first `+`. What matters is the string
    Neo4j actually receives.

    `lifecycle_state` filtering is NOT a substitute — review state and validity
    are independent axes, and an Approved fact can be superseded.
    """
    import re as _re

    from metis_mcp.mbt import graph_loader
    from metis_mcp.ontology.labels import VALIDITY_LABELS

    label_alt = "|".join(VALIDITY_LABELS)
    offences = []
    for name in sorted(n for n in vars(graph_loader) if n.endswith("_CYPHER")):
        body = getattr(graph_loader, name)
        if not isinstance(body, str) or not _re.search(rf":({label_alt})\b", body):
            continue
        filters = "valid_to" in body
        if filters and name in UNFILTERED_VALIDITY_READS:
            offences.append(f"{name} now filters on validity — delete it from "
                            f"UNFILTERED_VALIDITY_READS")
        elif not filters and name not in UNFILTERED_VALIDITY_READS:
            offences.append(f"{name} reads a validity-carrying label and does not "
                            f"filter on `valid_to`, and is not listed as a known gap")
    assert not offences, "\n  ".join([""] + offences)
