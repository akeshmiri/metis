"""
UIF → the graph (application spec §3.2 stage 2; D-8, S-4, TR-6).

Free to run: the planner is pure and fully validated offline, so what a UIF
lands as is provable without a database.

The properties that matter are the ones that would let intake quietly invent
things: whether a claimed acceptance criterion becomes one, whether free prose
becomes a requirement, and whether re-extracting the same ticket mints a second
Episode.
"""
import json

import pytest

from metis_mcp.model_sources import intake_landing as I

BASE = {
    "uif_version": "1.0.0",
    "facts": {}, "comments": [], "api_contracts": [], "error_handling": {},
    "links": [], "specifications": {}, "data_model": [], "open_questions": {},
}


def _uif(**overrides):
    doc = {
        **BASE,
        "scope": {"primary_id": "PROJ-14", "primary_type": "Story",
                  "source_system": "jira", "uif_generated_at": "2026-08-21T10:00:00Z"},
        "metadata": {"title": "Archive a record",
                     "description": "When a user archives a record, the system "
                                    "shall hide it from search."},
    }
    doc.update(overrides)
    return doc


def _labels(plan):
    return {n.label for n in plan.nodes}


# --------------------------------------------------------------------------
# The two provenance records answer different questions
# --------------------------------------------------------------------------

def test_one_uif_lands_one_episode_and_one_anchor():
    plan = I.plan_intake(_uif())
    assert plan.is_legal, plan.errors[:3]
    assert len([n for n in plan.nodes if n.label == "Episode"]) == 1
    assert len([n for n in plan.nodes if n.label == "JiraItem"]) == 1


def test_the_anchor_carries_the_identifier_its_own_system_uses():
    plan = I.plan_intake(_uif())
    anchor = next(n for n in plan.nodes if n.label == "JiraItem")
    assert anchor.properties["jira_key"] == "PROJ-14"
    assert anchor.properties["issue_type"] == "Story"


@pytest.mark.parametrize("system,label,prop", [
    ("jira", "JiraItem", "jira_key"),
    ("confluence", "ConfluenceItem", "page_id"),
    ("swagger", "OpenApiItem", "document_id"),
    ("scale", "ZephyrItem", "zephyr_key"),
    ("code_repository", "CodeItem", "repo_id"),
    ("database", "DatasourceItem", "datasource_id"),
])
def test_every_extractor_has_an_anchor(system, label, prop):
    """Taken from what a producer actually emits, not what the source is
    called: an OpenAPI document's `source_system` is `swagger` and Zephyr
    Scale's is `scale`."""
    doc = _uif(scope={"primary_id": "X-1", "primary_type": "t",
                      "source_system": system})
    plan = I.plan_intake(doc)
    assert plan.is_legal, plan.errors[:3]
    anchor = next(n for n in plan.nodes if n.label == label)
    assert anchor.properties[prop] == "X-1"


def test_an_unknown_source_system_is_refused_rather_than_guessed():
    """Adding an anchor is an ontology change under D-2, not an edit here."""
    doc = _uif(scope={"primary_id": "X", "primary_type": "t",
                      "source_system": "servicenow"})
    with pytest.raises(I.IntakeRefused) as e:
        I.plan_intake(doc)
    assert "servicenow" in str(e.value)


def test_the_episode_carries_the_raw_document():
    """F-12: a consumer never re-derives. Without the body they would have to
    re-extract to see what was actually received."""
    plan = I.plan_intake(_uif())
    episode = next(n for n in plan.nodes if n.label == "Episode")
    assert json.loads(episode.properties["raw_content"])["scope"]["primary_id"] == "PROJ-14"


def test_the_episode_records_who_proposed_it():
    """N-10 reads this back: the identity that proposed an element may not
    approve it."""
    plan = I.plan_intake(_uif(), proposed_by="alice")
    episode = next(n for n in plan.nodes if n.label == "Episode")
    assert episode.properties["proposed_by"] == "alice"


# --------------------------------------------------------------------------
# D-8 / TR-6 : re-extracting unchanged content is a no-op
# --------------------------------------------------------------------------

def test_the_episode_id_ignores_the_extraction_timestamp():
    """`scope.uif_generated_at` changes on every run. Hashing it would mint a
    new Episode each time and make idempotence unachievable."""
    a = _uif()
    b = _uif(scope={**a["scope"], "uif_generated_at": "2026-12-31T23:59:59Z"})
    assert I.episode_id_for(a) == I.episode_id_for(b)


def test_the_episode_id_changes_when_the_content_does():
    a = _uif()
    b = _uif(metadata={**a["metadata"], "description": "something else entirely."})
    assert I.episode_id_for(a) != I.episode_id_for(b)


# --------------------------------------------------------------------------
# What intake must NOT invent
# --------------------------------------------------------------------------

def test_a_claimed_acceptance_criterion_does_not_become_one():
    """A UIF arrives with criteria already labelled as such. Trusting an
    upstream extractor's labelling is the shortcut the intake skill refuses --
    the text goes through mining and review like any other intake."""
    doc = _uif(specifications={"acceptance_criteria": [
        {"text": "claims to be an AC"}, {"text": "so does this"}]})
    plan = I.plan_intake(doc)
    assert "AcceptanceCriterion" not in _labels(plan)


def test_free_prose_does_not_become_a_requirement():
    """A Jira title is free prose, and `ears_pattern` has no empty form.
    Inventing one produces the fluent, well-formed, invented requirement
    `ac_mining` exists to refuse (S-13, TR-4)."""
    doc = _uif(metadata={"title": "Archive button broken",
                         "description": "Clicking archive does nothing on Safari"})
    plan = I.plan_intake(doc)
    assert "Requirement" not in _labels(plan)


def test_non_conformant_text_is_reported_rather_than_dropped():
    """The honest outcome, not a silent skip: a Finding naming what has to
    happen next."""
    doc = _uif(metadata={"title": "x", "description": "Clicking archive does nothing"})
    plan = I.plan_intake(doc)
    finding = next(n for n in plan.nodes if n.label == "Finding")
    assert finding.properties["finding_type"] == I.NOT_EARS
    assert "knowledge-capture" in finding.properties["remedy"]


def test_ears_conformant_text_does_become_a_requirement():
    plan = I.plan_intake(_uif())
    requirement = next(n for n in plan.nodes if n.label == "Requirement")
    assert requirement.properties["ears_pattern"] == "EventDriven"
    assert requirement.properties["lifecycle_state"] == "Quarantine"
    assert ("JiraItem", "REPRESENTS", "Requirement") in {
        (e.from_label, e.rel_type, e.to_label) for e in plan.edges}


def test_an_entity_with_no_description_is_skipped():
    """D-13: a glossary entry whose name is its own only explanation answers
    nothing. Better absent than empty."""
    doc = _uif(data_model=[{"name": "record", "description": "A stored item"},
                           {"name": "mystery"}])
    plan = I.plan_intake(doc)
    entities = [n for n in plan.nodes if n.label == "BusinessEntity"]
    assert [e.properties["name"] for e in entities] == ["record"]


def test_open_questions_become_findings_about_the_artefact():
    doc = _uif(open_questions={"ambiguities": ["what about shared records?"],
                               "conflicts": ["two specs disagree"]})
    plan = I.plan_intake(doc)
    findings = [n for n in plan.nodes if n.label == "Finding"]
    assert len(findings) == 2
    about = {(e.rel_type, e.to_label) for e in plan.edges if e.from_label == "Finding"}
    assert ("ABOUT", "JiraItem") in about


# --------------------------------------------------------------------------
# S-4 : everything lands at Quarantine
# --------------------------------------------------------------------------

def test_nothing_lands_approved():
    doc = _uif(data_model=[{"name": "record", "description": "A stored item"}],
               open_questions={"ambiguities": ["?"]})
    plan = I.plan_intake(doc)
    for node in plan.nodes:
        state = node.properties.get("lifecycle_state")
        if state is not None:
            assert state == "Quarantine", f"{node.label} landed {state}"


# --------------------------------------------------------------------------
# Reading the file: a shape this cannot land is refused, not read optimistically
# --------------------------------------------------------------------------

def test_an_unknown_uif_version_is_refused(tmp_path):
    path = tmp_path / "u.json"
    path.write_text(json.dumps({**BASE, "uif_version": "9.0.0",
                                "scope": {"primary_id": "a", "source_system": "jira"}}))
    with pytest.raises(I.IntakeRefused) as e:
        I.load(path)
    assert "9.0.0" in str(e.value)


def test_a_document_with_no_source_system_is_refused(tmp_path):
    path = tmp_path / "u.json"
    path.write_text(json.dumps({**BASE, "scope": {"primary_id": "a"}}))
    with pytest.raises(I.IntakeRefused) as e:
        I.load(path)
    assert "source_system" in str(e.value)


def test_a_document_with_no_primary_id_is_refused(tmp_path):
    path = tmp_path / "u.json"
    path.write_text(json.dumps({**BASE, "scope": {"source_system": "jira"}}))
    with pytest.raises(I.IntakeRefused) as e:
        I.load(path)
    assert "primary_id" in str(e.value)


def test_the_description_names_what_was_not_trusted():
    """A person running this should see that claimed criteria were skipped, and
    why — a count that quietly excludes them is the silent half."""
    doc = _uif(specifications={"acceptance_criteria": [{"text": "a"}, {"text": "b"}]})
    text = I.describe(I.plan_intake(doc), doc)
    assert "2 acceptance criteria are claimed" in text
    assert "NONE is created" in text
