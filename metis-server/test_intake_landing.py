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
        # Schema-valid: a lowercase enum member, and the two timestamps the
        # schema requires. It carried `"Story"` and neither timestamp, which is
        # what `test_intakes` pinned as a divergence -- the landing path treating
        # as valid a document the published contract rejects.
        "scope": {"primary_id": "PROJ-14", "primary_type": "story",
                  "created_at": "2026-07-14T09:12:00Z",
                  "last_updated_at": "2026-08-02T16:40:00Z",
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
    assert anchor.properties["issue_type"] == "story"


@pytest.mark.parametrize("system,label,prop", [
    ("jira", "JiraItem", "jira_key"),
    ("confluence", "ConfluenceItem", "page_id"),
    ("swagger", "OpenApiItem", "document_id"),
    ("scale", "ZephyrItem", "zephyr_key"),
    ("code_repository", "CodeItem", "repo_id"),
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


# --------------------------------------------------------------------------
# The MCP write tool (W3), which must refuse exactly what the CLI refuses.
#
# `land_intake` exists because intake landing was the one write the agent
# surface had no tool for — `land_model`, `land_knowledge` and `land_findings`
# were all there. The risk in adding it is that it becomes a second, laxer
# writer, so these assert the S-13 behaviour through the tool rather than
# through the planner it calls.
# --------------------------------------------------------------------------

def _land_via_tool(tmp_path, monkeypatch, document):
    """Run `write.land_intake` against a session that records the plan."""
    import hashlib
    import json as _json

    from metis_mcp import policy, write

    uif = tmp_path / "doc.json"
    uif.write_text(_json.dumps(document))

    token, store = "tok", tmp_path / "p.tsv"
    store.write_text(
        f"{hashlib.sha256(token.encode()).hexdigest()}\tdana\tcontributor\n")
    monkeypatch.setenv("METIS_API_TOKENS", str(store))
    monkeypatch.setenv(policy.TOKEN_ENV, token)
    monkeypatch.setenv(policy.WRITE_ENV, policy.AUTHOR)
    monkeypatch.setenv("METIS_AUDIT_DIR", str(tmp_path / "audit"))

    landed = {}

    class _Result:
        ok, nodes_written, edges_written, unmatched, refused = True, 0, 0, [], ""
        episode_id = "ep-test"

    def _fake_land(_session, plan):
        landed["plan"] = plan
        return _Result()

    monkeypatch.setattr("metis_mcp.model_sources.landing.land", _fake_land)
    monkeypatch.setattr("metis_mcp.mbt.graph_session.session",
                        lambda *a, **k: __import__("contextlib").nullcontext(None))
    out = write.land_intake(str(uif), actor="dana", role="contributor")
    return out, landed.get("plan")


def test_the_tool_lands_free_prose_as_a_finding_not_a_requirement(tmp_path,
                                                                  monkeypatch):
    """**The regression that would be worst to ship.** Promoting prose to a
    Requirement files somebody's tracker title as a stated requirement, with an
    author who never wrote it (S-13)."""
    prose = _uif(metadata={"title": "Archive a record",
                           "description": "Archiving should be easier."})
    _out, plan = _land_via_tool(tmp_path, monkeypatch, prose)
    labels = _labels(plan)
    assert "Requirement" not in labels, "free prose became a Requirement"
    assert "Finding" in labels


def test_the_tool_still_lands_ears_text_as_a_requirement(tmp_path, monkeypatch):
    """The guard must not become a refusal machine: conformant text still lands."""
    _out, plan = _land_via_tool(tmp_path, monkeypatch, _uif())
    assert "Requirement" in _labels(plan)


def test_the_tool_reports_the_finding_outcome_rather_than_leaving_it_to_be_counted(
        tmp_path, monkeypatch):
    """Landing as a Finding is the most surprising thing this intake does, so it
    is said in the response, not discovered by counting nodes afterwards."""
    prose = _uif(metadata={"title": "Archive a record",
                           "description": "Archiving should be easier."})
    out, _plan = _land_via_tool(tmp_path, monkeypatch, prose)
    assert out["advisories"] != "none"
    assert any("knowledge-capture" in a or "Finding" in a
               for a in out["advisories"]), out["advisories"]


def test_the_tool_says_everything_landed_at_quarantine(tmp_path, monkeypatch):
    """S-4: intake is not agreement."""
    out, _plan = _land_via_tool(tmp_path, monkeypatch, _uif())
    assert "Quarantine" in out["lifecycle"]


# --------------------------------------------------------------------------
# The S-13 advisory has to fire for the document the SCHEMA defines.
#
# It checked `acceptance_criteria` at the top level and under `metadata`. The
# UIF schema puts them under `specifications` and sets
# `additionalProperties: false`, so both checked locations are shapes a valid
# document cannot have: the advisory fired only for documents the schema
# forbids. The protection held — `plan_intake` never made an
# `AcceptanceCriterion` — but the warning that says so never appeared, so a
# person met the behaviour by counting nodes instead of being told at the door.
# --------------------------------------------------------------------------

def _claim_advisories(doc):
    return [a for a in I.conformance(doc).advisories if "NOT be trusted" in a]


def test_the_advisory_fires_for_criteria_where_the_schema_puts_them():
    """`specifications.acceptance_criteria` — the location a valid UIF uses,
    the one this module's own docstring names, and the one it did not check."""
    doc = _uif(specifications={"acceptance_criteria": [{"text": "a"},
                                                       {"text": "b"}]})
    advisories = _claim_advisories(doc)
    assert advisories, "a schema-valid document's claimed criteria went unreported"
    assert "2 claimed acceptance criteria" in advisories[0]


def test_the_advisory_still_fires_for_the_malformed_placements():
    """`land_intake` accepts a document nothing validated, so a criterion in the
    wrong place must still be reported rather than pass in silence."""
    assert _claim_advisories(_uif(acceptance_criteria=[{"text": "a"}]))
    assert _claim_advisories(
        _uif(metadata={"title": "Archive a record",
                       "acceptance_criteria": [{"text": "a"}]}))


def test_criteria_in_two_places_are_counted_together():
    """First-match would understate what is being declined."""
    doc = _uif(specifications={"acceptance_criteria": [{"text": "a"}]},
               acceptance_criteria=[{"text": "b"}])
    assert "2 claimed acceptance criteria" in _claim_advisories(doc)[0]


def test_a_document_claiming_nothing_gets_no_advisory():
    """Without this the tests above pass for a function that always fires."""
    assert not _claim_advisories(_uif())
    assert not _claim_advisories(_uif(specifications={}))
    assert not _claim_advisories(_uif(specifications={"acceptance_criteria": []}))


def test_the_two_disclosure_paths_report_the_same_count():
    """**The invariant the bug broke, not just the symptom.**

    `conformance` warns before landing; `describe` reports after planning. They
    read the document independently, and they disagreed — `describe` looked
    under `specifications` and `conformance` did not, so the same document was
    reported as claiming two criteria by one and none by the other. Whichever
    location a future document uses, both must see it.
    """
    for doc in (_uif(specifications={"acceptance_criteria": [{"text": "a"},
                                                             {"text": "b"}]}),
                _uif(acceptance_criteria=[{"text": "a"}]),
                _uif()):
        advisories = _claim_advisories(doc)
        described = I.describe(I.plan_intake(doc), doc)
        claims_in_describe = "acceptance criteria are claimed" in described
        assert bool(advisories) == claims_in_describe, (
            f"the two disclosure paths disagree about {doc.get('specifications')}: "
            f"advisory={bool(advisories)} describe={claims_in_describe}")


def test_the_protection_itself_still_holds_wherever_the_claim_sits():
    """The advisory is the warning; this is the thing being warned about."""
    for doc in (_uif(specifications={"acceptance_criteria": [{"text": "a"}]}),
                _uif(acceptance_criteria=[{"text": "a"}]),
                _uif(metadata={"title": "t", "acceptance_criteria": [{"text": "a"}]})):
        assert "AcceptanceCriterion" not in _labels(I.plan_intake(doc))


# ---------------------------------------------------------------------------
# Requirement hierarchy — the epic and the stories under it
# ---------------------------------------------------------------------------
#
# `JiraItem-[:LINKS_TO]->JiraItem` was catalogued with no writer and no reader,
# which D-1 exists to prevent: a query for "what does this link to" returned
# nothing and could not tell that from "it links to nothing".
#
# What blocked the writer was not effort. The UIF had nowhere to put a link —
# `additionalProperties: false` with no `links` key, `source_references` meaning
# *where this fact came from* (a linked epic is not a source of this
# requirement's text), and `secondary_id` being one string where a set is
# needed. Adding `links` to the schema was a contract decision, and once made
# the writer is small.

def _linked(**overrides):
    doc = _uif()
    doc["links"] = [{"relation": "parent", "target_id": "PROJ-100",
                     "target_system": "jira"}]
    doc.update(overrides)
    return doc


def test_a_declared_link_becomes_an_edge_between_anchors():
    plan = I.plan_intake(_linked())
    assert plan.is_legal, plan.errors[:3]
    links = [e for e in plan.edges if e.rel_type == "LINKS_TO"]
    assert len(links) == 1
    assert links[0].from_id == "jira:PROJ-14"
    assert links[0].to_id == "jira:PROJ-100"
    assert links[0].from_label == links[0].to_label == "JiraItem"


def test_the_target_anchor_is_planned_even_though_it_was_not_fetched():
    """An epic linked from a story may never have been fetched itself.

    An edge whose endpoint is absent merges nothing and reports as `unmatched`
    — so the hierarchy would silently not exist for exactly the case it is most
    useful in. Planning a bare anchor means it survives a partial fetch, and the
    epic's own text arrives whenever somebody lands it.
    """
    plan = I.plan_intake(_linked())
    anchors = {n.properties["id"]: n for n in plan.nodes if n.label == "JiraItem"}
    assert set(anchors) == {"jira:PROJ-14", "jira:PROJ-100"}
    # `unknown` rather than a guess: nobody has read PROJ-100 yet.
    assert anchors["jira:PROJ-100"].properties["issue_type"] == "unknown"


def test_a_link_to_another_tracker_is_skipped_and_counted():
    """Not pointed at something plausible.

    A Confluence page linked from a Jira issue has no `JiraItem` to be, and
    inventing one would put a page's id in the issue namespace.
    """
    plan = I.plan_intake(_linked(links=[
        {"relation": "documented by", "target_id": "12345",
         "target_system": "confluence"}]))
    assert not [e for e in plan.edges if e.rel_type == "LINKS_TO"]
    assert plan.skipped, "a skipped link must be counted, not silently dropped"
    assert "cross-tracker" in " ".join(reason for _, reason in plan.skipped)


def test_an_item_that_links_to_itself_plans_no_edge():
    plan = I.plan_intake(_linked(links=[
        {"relation": "relates to", "target_id": "PROJ-14",
         "target_system": "jira"}]))
    assert not [e for e in plan.edges if e.rel_type == "LINKS_TO"]


def test_a_document_with_no_links_plans_none():
    """An absent `links` and an empty one both mean none declared."""
    assert not [e for e in I.plan_intake(_uif()).edges if e.rel_type == "LINKS_TO"]
    assert not [e for e in I.plan_intake(_uif(links=[])).edges
                if e.rel_type == "LINKS_TO"]


def test_the_demo_corpus_carries_a_real_hierarchy():
    """Exercised by the corpus, not only by a fixture built for the test.

    `demo_project/trackers/` holds an epic, a story beneath it, and a defect
    linked to the story — so the path a real backlog takes is the path the
    suite runs.
    """
    from pathlib import Path as _Path

    from code_analysis import tracker

    read = tracker.from_fixture(
        _Path(__file__).parent / "demo_project" / "trackers" / "jira.tracker.json")
    edges = []
    for item in read.items:
        plan = I.plan_intake(tracker.to_uif(item))
        assert plan.is_legal, plan.errors[:2]
        edges += [(e.from_id, e.to_id) for e in plan.edges
                  if e.rel_type == "LINKS_TO"]

    assert ("jira:DEMO-1", "jira:DEMO-100") in edges, (
        "the story does not reach its epic; decomposition is unanswerable")
    assert ("jira:DEMO-2", "jira:DEMO-1") in edges


# ---------------------------------------------------------------------------
# Link kind
# ---------------------------------------------------------------------------


def test_a_tracker_link_records_which_kind_it_is():
    """**`LINKS_TO` landed every link indistinguishable from every other.**

    `PlannedEdge` had no properties field at all, so the intake read a link's
    `relation` — `parent`, `blocks`, `causes` — planned the edge, and had
    nowhere to put the kind. `read.requirement_hierarchy` honestly reported
    `"type": "unknown"` for all of them, which makes "what are this epic's
    children" indistinguishable from "what blocks this" and leaves a backlog
    hierarchy unanswerable.
    """
    plan = I.plan_intake(_uif(links=[
        {"relation": "parent", "target_id": "DEMO-100", "target_system": "jira"},
        {"relation": "blocks", "target_id": "DEMO-7", "target_system": "jira"},
    ]))
    links = [e for e in plan.edges if e.rel_type == "LINKS_TO"]
    assert len(links) == 2
    assert {e.properties.get("relation") for e in links} == {"parent", "blocks"}


def test_a_link_with_no_stated_relation_is_recorded_as_unknown():
    """`unknown` rather than absent: "the tracker did not say" and "nobody
    recorded it" are different, and only the first is a fact about the link."""
    plan = I.plan_intake(_uif(
        links=[{"target_id": "DEMO-100", "target_system": "jira"}]))
    link = [e for e in plan.edges if e.rel_type == "LINKS_TO"][0]
    assert link.properties["relation"] == "unknown"


def test_an_ordinary_edge_carries_no_properties():
    """Empty is correct for almost every edge: a `HAS_AC` says everything by
    existing. Only a relationship whose KIND varies needs the field, and a
    default that invented one would put noise on every edge in the graph."""
    plan = I.plan_intake(_uif())
    others = [e for e in plan.edges if e.rel_type != "LINKS_TO"]
    assert others, "expected at least one ordinary edge"
    assert all(e.properties == {} for e in others)
