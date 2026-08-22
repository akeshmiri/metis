"""
The knowledge-centre file (application spec §4.5, §4.6; S-13, S-19, I-5).

Free to run: no Neo4j, no model calls, no config. Everything here is either pure
or goes through the registered `ac-mined` source, which makes no model call by
design.
"""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from metis_mcp.identity.matching import ADDED, MODIFIED, REMOVED, UNCHANGED, diff
from metis_mcp.model_sources import get as get_source
from metis_mcp.model_sources.knowledge import (
    BAD_VALUE,
    DUPLICATE_ID,
    MISSING_REQUIREMENT,
    NOT_EARS,
    ORPHANED_CRITERION,
    FILE_VERSION,
    INFERRED_COMPLEMENT,
    MISSING_SOURCE,
    NEGATIVE,
    NOT_ATOMIC,
    POSITIVE,
    STATED,
    UNGROUNDED_COMPLEMENT,
    UNPARSEABLE,
    KnowledgeEntry,
    KnowledgeFile,
    KnowledgeFileRefused,
    KnowledgeRequirement,
    check_atomic,
    load,
    plan_documentation,
    provenance_for,
    to_criteria,
)
from metis_mcp.model_sources.knowledge import validate as validate_knowledge
from metis_mcp.ontology.labels import CODE_DERIVED, HUMAN_CONFIRMED

STATEMENT = "if user has admin permission then it should be able to do 1, 2 and 3"
REQUIREMENT = KnowledgeRequirement(
    id="REQ-ADMIN-01",
    text="When a user has admin permission, the system shall permit the action.")


def _entry(eid, text, **kwargs):
    kwargs.setdefault("source_statement", STATEMENT)
    return KnowledgeEntry(id=eid, text=text, requirement_id="REQ-ADMIN-01", **kwargs)


def _admin_file() -> KnowledgeFile:
    """The user's own example: three permitted actions, and their complements."""
    entries = []
    for n in (1, 2, 3):
        entries.append(_entry(
            f"AC-00{n}",
            f"Given the user has admin permission, when they do {n}, "
            f"then the request succeeds."))
    for n in (1, 2, 3):
        entries.append(_entry(
            f"AC-00{n + 3}",
            f"Given the user does not have admin permission, when they do {n}, "
            f"then the request is rejected.",
            polarity=NEGATIVE, derived=INFERRED_COMPLEMENT,
            complement_of=f"AC-00{n}"))
    return KnowledgeFile(model_id="admin-api", requirement=REQUIREMENT, surface="api",
                         statement=STATEMENT, initial_state="Authenticated",
                         entries=entries)


def _mine(knowledge: KnowledgeFile):
    return get_source("ac-mined").produce(
        criteria=to_criteria(knowledge), model_id=knowledge.model_id,
        surface=knowledge.surface,
        initial_state=knowledge.initial_state or None).model


# --------------------------------------------------------------------------
# Atomicity — one condition, one action, one validation
# --------------------------------------------------------------------------

def test_a_criterion_with_one_of_each_is_atomic():
    assert check_atomic(
        "Given the user has admin permission, when they do 1, "
        "then the request succeeds.") is None


def test_two_validations_are_not_one_criterion():
    detail = check_atomic(
        "Given the user has admin permission, when they archive a record, "
        "then the record is archived and an audit entry is written.")
    assert detail and "validation (Then)" in detail


def test_two_conditions_are_not_one_criterion():
    detail = check_atomic(
        "Given the user is logged in, when they archive a record, and they have "
        "admin permission and write access, then the record is archived.")
    assert detail and "condition (And)" in detail


def test_two_actions_are_caught_even_though_the_parser_reads_one():
    """The hole a per-clause check alone leaves open.

    `_GWT`'s optional `and` clause swallows "delete a record" as though it were a
    condition, so every clause looks single and two actions go through as one
    criterion. English does not separate the readings; the comma does, and `, and`
    is exactly what `ac_drafting` and §18 already write.
    """
    detail = check_atomic(
        "Given the user has admin permission, when they archive a record and "
        "delete a record, then the record is archived.")
    assert detail and "action (When)" in detail


def test_a_comma_delimited_condition_is_still_atomic():
    """The other side of the same rule — it must not reject a real condition."""
    assert check_atomic(
        "Given the user is logged in, when they archive a record, and they have "
        "admin permission, then the record is archived.") is None


def test_an_unguarded_criterion_is_atomic():
    """Three of the login model's seventeen transitions are unguarded. Demanding
    a condition where none exists would reject real behaviour."""
    assert check_atomic(
        "Given the user is logged out, when they open the page, "
        "then the login form is shown.") is None


# --------------------------------------------------------------------------
# The file's own rules
# --------------------------------------------------------------------------

def test_the_users_own_example_validates_clean():
    assert validate_knowledge(_admin_file()) == []


def test_an_inferred_complement_must_name_what_it_complements():
    """S-13. Nobody stated the complement; without its origin it is
    indistinguishable from something a person wrote."""
    knowledge = _admin_file()
    knowledge.entries[3] = _entry(
        "AC-004", knowledge.entries[3].text,
        polarity=NEGATIVE, derived=INFERRED_COMPLEMENT)
    kinds = [p.kind for p in validate_knowledge(knowledge)]
    assert UNGROUNDED_COMPLEMENT in kinds


def test_complement_of_must_name_an_entry_that_exists():
    knowledge = _admin_file()
    knowledge.entries[3] = _entry(
        "AC-004", knowledge.entries[3].text, polarity=NEGATIVE,
        derived=INFERRED_COMPLEMENT, complement_of="AC-999")
    problems = validate_knowledge(knowledge)
    assert any(p.kind == UNGROUNDED_COMPLEMENT and "AC-999" in p.detail
               for p in problems)


def test_a_stated_entry_may_not_claim_to_be_derived():
    knowledge = _admin_file()
    knowledge.entries[0] = _entry("AC-001", knowledge.entries[0].text,
                                  derived=STATED, complement_of="AC-002")
    assert any(p.kind == BAD_VALUE for p in validate_knowledge(knowledge))


def test_every_entry_records_what_it_was_formalised_from():
    knowledge = _admin_file()
    knowledge.entries[0] = KnowledgeEntry(id="AC-001", text=knowledge.entries[0].text)
    assert any(p.kind == MISSING_SOURCE for p in validate_knowledge(knowledge))


def test_free_prose_is_reported_not_guessed_at():
    knowledge = _admin_file()
    knowledge.entries[0] = _entry("AC-001", "if the user is an admin they can do 1")
    assert any(p.kind == UNPARSEABLE for p in validate_knowledge(knowledge))


def test_duplicate_ids_are_caught_before_they_merge_onto_one_node():
    knowledge = _admin_file()
    knowledge.entries.append(_entry("AC-001", knowledge.entries[0].text))
    assert any(p.kind == DUPLICATE_ID for p in validate_knowledge(knowledge))


def test_every_problem_is_reported_not_just_the_first():
    """A person fixing a file wants the whole list; one at a time turns a single
    edit into six rounds."""
    knowledge = _admin_file()
    knowledge.entries[0] = _entry("AC-001", "not a criterion at all")
    knowledge.entries[1] = KnowledgeEntry(
        id="AC-002", text="Given a, when b, then c and d.")
    kinds = {p.kind for p in validate_knowledge(knowledge)}
    assert {UNPARSEABLE, NOT_ATOMIC, MISSING_SOURCE} <= kinds


def test_an_inferred_criterion_never_arrives_as_intent():
    """S-19: only a human edit or affirmation promotes a criterion. A function
    that anticipated that decision would manufacture the thing S-19 protects."""
    for entry in _admin_file().entries:
        assert provenance_for(entry) == CODE_DERIVED
        assert provenance_for(entry) != HUMAN_CONFIRMED


# --------------------------------------------------------------------------
# Reading the file
# --------------------------------------------------------------------------

def test_an_unknown_file_version_is_refused_rather_than_read_optimistically():
    with TemporaryDirectory() as d:
        path = Path(d) / "k.json"
        path.write_text(json.dumps({"knowledge_version": "metis.knowledge/99",
                                    "model_id": "admin-api", "entries": []}))
        try:
            load(path)
        except KnowledgeFileRefused as e:
            assert "metis.knowledge/99" in str(e)
        else:
            raise AssertionError("an unknown version must be refused")


def test_a_file_with_no_model_id_is_refused():
    with TemporaryDirectory() as d:
        path = Path(d) / "k.json"
        path.write_text(json.dumps({"knowledge_version": FILE_VERSION, "entries": []}))
        try:
            load(path)
        except KnowledgeFileRefused as e:
            assert "model_id" in str(e)
        else:
            raise AssertionError("a criterion with no model compares against nothing")


def test_the_file_round_trips():
    original = _admin_file()
    with TemporaryDirectory() as d:
        path = Path(d) / "k.json"
        path.write_text(original.to_json())
        reloaded = load(path)
    assert reloaded.model_id == original.model_id
    assert reloaded.statement == STATEMENT
    assert [e.id for e in reloaded.entries] == [e.id for e in original.entries]
    assert reloaded.entries[3].complement_of == "AC-001"


# --------------------------------------------------------------------------
# Mining, and the three answers (I-5, I-8)
# --------------------------------------------------------------------------

def test_the_users_example_mines_six_transitions_at_quarantine():
    """Three permitted actions and three refusals — six behaviours, six
    criteria, six transitions. Not one criterion for "an admin has access"."""
    model = _mine(_admin_file())
    assert len(model.transitions) == 6
    assert all(t.lifecycle_state == "Quarantine" for t in model.transitions.values()), (
        "S-4: every source produces candidates; authoring is not approving"
    )
    triggers = sorted(t.trigger for t in model.transitions.values())
    assert triggers == ["do 1", "do 1", "do 2", "do 2", "do 3", "do 3"]


def test_an_unchanged_file_reports_nothing_new():
    """The load-bearing one. A compare that reports ADDED for behaviour already
    in the model looks like success and is not."""
    knowledge = _admin_file()
    delta = diff(_mine(knowledge), _mine(knowledge))
    assert delta.summary[ADDED] == 0
    assert delta.summary[MODIFIED] == 0
    assert delta.summary[UNCHANGED] > 0


def test_a_differing_condition_on_the_same_behaviour_is_a_contradiction():
    """I-8: same natural key, different guard. Both sides are quoted, because
    neither wins automatically (S-10)."""
    before = _mine(_admin_file())
    after = _mine(KnowledgeFile(
        model_id="admin-api", requirement=REQUIREMENT, surface="api",
        statement=STATEMENT,
        entries=[_entry("AC-001",
                        "Given the user has admin permission, when they do 1, and "
                        "the account is not suspended, then the request succeeds.")]))
    modified = diff(before, after).of(MODIFIED)
    assert len(modified) == 1
    assert "guard changed" in modified[0].detail
    assert "the account is not suspended" in modified[0].detail


def test_a_genuinely_new_behaviour_is_added():
    before = _mine(_admin_file())
    knowledge = _admin_file()
    knowledge.entries.append(_entry(
        "AC-007",
        "Given the user has admin permission, when they do 4, "
        "then the request succeeds."))
    added = diff(before, _mine(knowledge)).of(ADDED)
    assert [c.element_id for c in added if c.kind == "transition"] == [
        "ac::UserHasAdminPermission::Do4::TheRequestSucceeds"]


def test_a_partial_statement_does_not_propose_deleting_the_rest():
    """§4.5: an AC-mined model is partial by nature.

    `diff` compares two models that each claim to describe the whole machine, so
    it reports everything the candidate omits as REMOVED. A knowledge file is not
    that claim — one sentence about admin permissions must never read as a
    proposal to delete the rest of the model, which is why the compare handler
    reports these as untouched and never as removals.
    """
    before = _mine(_admin_file())
    after = _mine(KnowledgeFile(
        model_id="admin-api", requirement=REQUIREMENT, surface="api",
        statement=STATEMENT, entries=[_admin_file().entries[0]]))
    delta = diff(before, after)
    assert delta.summary[REMOVED] > 0, "diff itself does report them"
    assert delta.summary[ADDED] == 0, "and none of them is a new proposal"


# --------------------------------------------------------------------------
# Stage 1 is a Requirement AND its criteria
# --------------------------------------------------------------------------

def test_a_file_of_bare_criteria_has_nothing_above_them():
    """The state the live graph was actually in: 255 criteria, 0 requirements.

    A criterion is atomic (S-20), so none of them carries the whole statement.
    Without a Requirement they land as a scatter of conditions with nothing
    saying what they are conditions of.
    """
    knowledge = _admin_file()
    knowledge.requirement = None
    assert any(p.kind == MISSING_REQUIREMENT for p in validate_knowledge(knowledge))


def test_a_requirement_that_is_not_ears_is_refused_not_force_tagged():
    knowledge = _admin_file()
    knowledge.requirement = KnowledgeRequirement(
        id="REQ-ADMIN-01", text="admins can do stuff")
    problems = validate_knowledge(knowledge)
    assert any(p.kind == NOT_EARS for p in problems)


def test_a_criterion_may_not_name_another_file_s_requirement():
    knowledge = _admin_file()
    knowledge.entries[0] = KnowledgeEntry(
        id="AC-001", text=knowledge.entries[0].text,
        requirement_id="REQ-SOMETHING-ELSE", source_statement=STATEMENT)
    assert any(p.kind == ORPHANED_CRITERION for p in validate_knowledge(knowledge))


# --------------------------------------------------------------------------
# Stage 2 — the documentation reaching the graph
# --------------------------------------------------------------------------

def test_documentation_lands_a_requirement_and_its_criteria():
    knowledge = _admin_file()
    plan = plan_documentation(knowledge, "ep-1")
    assert plan.is_legal, plan.errors
    labels = [n.label for n in plan.nodes]
    assert labels.count("Requirement") == 1
    assert labels.count("AcceptanceCriterion") == 6
    has_ac = [e for e in plan.edges if e.rel_type == "HAS_AC"]
    assert len(has_ac) == 6, "every criterion hangs off its requirement"


def test_the_requirement_carries_the_pattern_the_checker_found():
    plan = plan_documentation(_admin_file(), "ep-1")
    requirement = next(n for n in plan.nodes if n.label == "Requirement")
    assert requirement.properties["ears_pattern"] == "EventDriven", (
        "the checker decides the pattern; it is never force-tagged"
    )


def test_everything_lands_at_quarantine():
    """S-4: a source produces candidates. This one is no exception because a
    person wrote it — authoring is not approving (E-11)."""
    plan = plan_documentation(_admin_file(), "ep-1")
    assert all(n.properties["lifecycle_state"] == "Quarantine" for n in plan.nodes)


def test_an_inferred_complement_carries_its_marking_into_the_graph():
    """The label has to survive the file, or the honesty ends at the filesystem."""
    plan = plan_documentation(_admin_file(), "ep-1")
    inferred = next(n for n in plan.nodes
                    if n.label == "AcceptanceCriterion"
                    and n.properties["id"] == "AC-004")
    assert inferred.properties["derived"] == INFERRED_COMPLEMENT
    assert inferred.properties["complement_of"] == "AC-001"
    assert inferred.properties["provenance"] == CODE_DERIVED


def test_validates_is_minted_only_for_the_transition_the_criterion_produced():
    """Not a judgement here, unlike `land_spec_criteria`'s case.

    The transition did not pre-exist to be matched against — it was mined FROM
    this criterion, and S-14 records the span. Withholding the edge would report
    the criterion's own behaviour as unspecified: a false gap, not a cautious one.
    """
    knowledge = _admin_file()
    mapping = {"AC-001": ["ac::UserHasAdminPermission::Do1::TheRequestSucceeds"]}
    plan = plan_documentation(knowledge, "ep-1", criterion_transitions=mapping)
    validates = [e for e in plan.edges if e.rel_type == "VALIDATES"]
    assert len(validates) == 1, "only the criterion that produced it"
    assert validates[0].from_id == "AC-001"


def test_validates_targets_the_label_and_id_landing_actually_writes():
    """The bug this catches was silent in every check that existed.

    A classified transition is written as `:ApiCall` **instead of** `:Transition`,
    and landing namespaces every id by model. An edge planned as
    `(:AcceptanceCriterion)-[:VALIDATES]->(:Transition {id: "ac::..."})` passes
    the ontology catalogue -- `is_allowed` walks the specialisation chain -- and
    then merges nothing, because no node carries that label or that id. `land`
    reports the shortfall as `unmatched`; it does not fail. Both stages landed,
    the counts looked plausible, and the traceability chain was still broken.
    """
    from metis_mcp.model_sources.landing import namespaced_id, transition_label_for

    mined = "ac::UserHasAdminPermission::Do1::TheRequestSucceeds"
    plan = plan_documentation(_admin_file(), "ep-1",
                              criterion_transitions={"AC-001": [mined]})
    edge = next(e for e in plan.edges if e.rel_type == "VALIDATES")
    assert edge.to_label == transition_label_for("api") == "ApiCall"
    assert edge.to_id == namespaced_id("admin-api", mined)
    assert edge.to_id.startswith("admin-api::"), (
        "the bare mined id matches no node in the graph"
    )


def test_no_mapping_means_no_validates_edge():
    plan = plan_documentation(_admin_file(), "ep-1")
    assert [e for e in plan.edges if e.rel_type == "VALIDATES"] == []


def test_mining_reports_which_criterion_produced_which_transition():
    """The mapping `plan_documentation` needs. It was computed and discarded."""
    result = get_source("ac-mined").produce(
        criteria=to_criteria(_admin_file()), model_id="admin-api", surface="api")
    mapping = result.evidence["criterion_transitions"]
    assert mapping["AC-001"] == ["ac::UserHasAdminPermission::Do1::TheRequestSucceeds"]
    assert set(mapping) == {f"AC-00{n}" for n in range(1, 7)}


def test_the_requirement_survives_a_file_round_trip():
    with TemporaryDirectory() as d:
        path = Path(d) / "k.json"
        path.write_text(_admin_file().to_json())
        reloaded = load(path)
    assert reloaded.requirement is not None
    assert reloaded.requirement.id == "REQ-ADMIN-01"
    assert reloaded.requirement.ears.conformant


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


# --------------------------------------------------------------------------
# The glossary lands (§4.6a, D-13) — it plans its own Episode, and the
# knowledge file's business-layer edges attach only once it has
# --------------------------------------------------------------------------

def _glossary():
    import json as _json
    from tempfile import TemporaryDirectory
    from metis_mcp.model_sources import glossary as G
    doc = {"glossary_version": G.FILE_VERSION,
           "areas": [{"id": "records", "name": "Records", "description": "Record lifecycle"}],
           "entities": [{"id": "record", "name": "record", "description": "A stored item",
                         "area": "records", "impact": ["archiving hides it from search"],
                         "properties": [{"name": "status", "meaning": "where it is in its life",
                                         "values": ["active", "archived"]}]}]}
    with TemporaryDirectory() as d:
        p = Path(d) / "g.json"
        p.write_text(_json.dumps(doc))
        return G.load(p)


def test_the_glossary_does_not_steal_an_episode_it_was_given():
    """`workflow.handlers._knowledge_land` passes the behaviour plan's episode
    id so a knowledge run lands as one ingestion. That Episode already exists
    and already carries the run's `source_connector` — MERGEing it again here
    would overwrite it with "glossary" and quietly relabel where the run came
    from."""
    from metis_mcp.model_sources.glossary import plan_glossary

    shared = plan_glossary(_glossary(), "ep-from-behaviour")
    assert not [n for n in shared.nodes if n.label == "Episode"], (
        "an explicit episode id means somebody else owns that Episode"
    )
    assert all(n.properties["source_episode_id"] == "ep-from-behaviour"
               for n in shared.nodes)


def test_the_glossary_plans_its_own_episode():
    """Every node carries `source_episode_id` — one of three baseline-required
    properties. This used to plan entities pointing at an Episode nothing
    created, so the provenance every other node resolves through did not exist
    for these."""
    from metis_mcp.model_sources.glossary import plan_glossary

    plan = plan_glossary(_glossary())
    assert plan.is_legal, plan.errors[:3]
    labels = [n.label for n in plan.nodes]
    assert "Episode" in labels, "the glossary must land the Episode it points at"
    episode = next(n for n in plan.nodes if n.label == "Episode")
    for node in plan.nodes:
        if node.label == "Episode":
            continue
        assert node.properties["source_episode_id"] == episode.properties["id"]


def test_the_glossary_episode_id_is_content_derived():
    """D-8/TR-6: re-landing an unchanged glossary is a no-op, and editing one
    definition mints a new Episode rather than mutating the old record."""
    import dataclasses
    from metis_mcp.model_sources.glossary import episode_id_for

    g = _glossary()
    assert episode_id_for(g) == episode_id_for(_glossary())

    changed = dataclasses.replace(
        g, entities=tuple(dataclasses.replace(e, description="something else")
                          for e in g.entities))
    assert episode_id_for(changed) != episode_id_for(g)


def test_knowledge_business_edges_target_what_the_glossary_writes():
    """`knowledge.plan_documentation` plans
    `AcceptanceCriterion-[:REFERENCES]->BusinessEntity` and
    `Requirement-[:BELONGS_TO]->BusinessArea` and creates neither node. Landing
    the glossary first is what makes those edges attach; landing it second is
    reported as `unmatched` rather than passing silently.
    """
    import dataclasses
    from metis_mcp.model_sources.glossary import entities_referenced_by, plan_glossary

    glossary = _glossary()
    k = _admin_file()
    k.area = "records"
    k.entries = [dataclasses.replace(e, text=e.text.replace("do 1", "archive a record"))
                 for e in k.entries]
    assert entities_referenced_by(k.entries[0].text, glossary) == ["record"]

    knowledge_plan = plan_documentation(k, episode_id="ep-k", glossary=glossary)
    targets = {(e.rel_type, e.to_label) for e in knowledge_plan.edges}
    assert ("REFERENCES", "BusinessEntity") in targets
    assert ("BELONGS_TO", "BusinessArea") in targets

    written = {(n.label, n.properties["id"]) for n in plan_glossary(glossary).nodes}
    for edge in knowledge_plan.edges:
        if edge.to_label in ("BusinessEntity", "BusinessArea"):
            assert (edge.to_label, edge.to_id) in written, (
                f"{edge.to_label} {edge.to_id!r} is referenced by knowledge landing "
                f"and written by nothing — land the glossary first"
            )
