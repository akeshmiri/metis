"""
Jira and Zephyr Scale as intakes (spec §5.2b, X-7a).

Free to run: the fixture path is what is exercised, and the live path takes a
transport the caller opens — so a stub is the whole of the network here. That is
the same split `db_catalogue` uses, and it is why the suite needs no HTTP
library installed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_analysis import tracker as T

DEMO = Path(__file__).parent / "demo_project" / "trackers"
JIRA_FIXTURE = DEMO / "jira.tracker.json"
ZEPHYR_FIXTURE = DEMO / "zephyr.tracker.json"


@pytest.fixture(scope="module")
def jira():
    return T.from_fixture(JIRA_FIXTURE)


@pytest.fixture(scope="module")
def zephyr():
    return T.from_fixture(ZEPHYR_FIXTURE)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def test_a_jira_issue_is_normalised(jira):
    item = next(i for i in jira.items if i.key == "DEMO-1")
    assert item.item_type == "Story" and item.status == "In Progress"
    assert item.labels == ("records", "archive")
    assert item.source_url.endswith("/browse/DEMO-1")


def test_an_adf_description_is_flattened_to_its_text_and_nothing_else(jira):
    """**No structure is reconstructed.** Atlassian Document Format is a nested
    node tree; only the text nodes are taken. A rendering that resembled the
    ticket without being it is worse than plain text, because a reviewer would
    compare it against the ticket and trust the resemblance."""
    item = next(i for i in jira.items if i.key == "DEMO-1")
    assert item.description == ("Archiving is terminal. A later PUT must not "
                                "revive the record.")
    assert "type" not in item.description and "{" not in item.description


def test_zephyr_is_read_from_a_flat_shape_not_jiras_nested_one(zephyr):
    """Jira nests everything under `fields`; Zephyr Scale does not. One reader,
    two shapes, declared in `FIELDS` rather than branched on inline."""
    item = zephyr.items[0]
    assert item.key == "DEMO-T1" and item.item_type == "TestCase"
    assert item.title == "Archived record rejects an update"
    assert item.description.startswith("While a record is archived")


def test_the_zephyr_source_system_stays_scale(zephyr):
    """`intake_landing.ANCHORS` keys `ZephyrItem` on `scale`. Renaming it to
    the friendlier `zephyr` would detach every item from its anchor — the
    landing would report success and the chain would be broken."""
    from metis_mcp.model_sources.intake_landing import ANCHORS

    assert zephyr.system == "scale"
    assert ANCHORS["scale"][0] == "ZephyrItem"


def test_an_unknown_tracker_is_refused_rather_than_read_optimistically():
    with pytest.raises(T.TrackerRefused) as e:
        T.item_from_payload("notion", "N-1", {})
    assert "D-2" in str(e.value), "the fix is named"


def test_an_unknown_fixture_version_is_refused(tmp_path):
    bad = tmp_path / "x.json"
    bad.write_text(json.dumps({"tracker_version": "metis.tracker-item/99"}))
    with pytest.raises(T.TrackerRefused):
        T.from_fixture(bad)


# ---------------------------------------------------------------------------
# Read-only by construction (X-7a)
# ---------------------------------------------------------------------------

def test_the_live_read_only_issues_allowlisted_get_paths():
    seen = []

    def get(url):
        seen.append(url)
        return {"key": "DEMO-9", "fields": {"summary": "x",
                                            "issuetype": {"name": "Story"}}}

    T.read(T.JIRA, "https://tracker.example.com", ["DEMO-9"], get)
    assert seen == ["https://tracker.example.com/rest/api/3/issue/DEMO-9"]


def test_a_path_outside_the_allowlist_is_refused_before_any_request():
    """The analogue of `assert_no_row_reads`: the discipline that matters is the
    one a test can fail, not the one a docstring asserts."""
    # `/issue/X/transitions` is the endpoint that MOVES a ticket, and the read
    # path is a prefix of it — so a substring test accepts it. This is the exact
    # URL that made the first version of the check useless.
    with pytest.raises(T.TrackerRefused) as e:
        T.assert_read_only(["https://tracker.example.com/rest/api/3/issue/X/"
                            "transitions"])
    assert "not an allowlisted read path" in str(e.value)
    assert "X-7a" in str(e.value)

    # And it must still accept the real one, or it is just a refusal machine.
    T.assert_read_only(["https://tracker.example.com/rest/api/3/issue/DEMO-1"])


def test_no_endpoint_in_the_allowlist_is_a_write():
    """A closed list is only worth having if nothing in it writes."""
    for system, template in T.ENDPOINTS.items():
        assert "delete" not in template.lower(), system
        assert "transition" not in template.lower(), system


def test_the_reader_does_not_crawl():
    """It reads the keys it is given. A project-wide crawl or a JQL search is a
    different capability with a different blast radius, and it would need
    arguing for rather than appearing."""
    with pytest.raises(T.TrackerRefused) as e:
        T.read(T.JIRA, "https://tracker.example.com", [], lambda url: {})
    assert "does not crawl" in str(e.value)


def test_a_non_object_response_is_refused_rather_than_shrugged_at():
    with pytest.raises(T.TrackerRefused):
        T.read(T.JIRA, "https://tracker.example.com", ["A-1"],
               lambda url: ["not", "an", "object"])


# ---------------------------------------------------------------------------
# UIF, and what it deliberately does not claim
# ---------------------------------------------------------------------------

def test_a_uif_from_a_tracker_item_lands(jira):
    from metis_mcp.model_sources.intake_landing import conformance

    item = next(i for i in jira.items if i.key == "DEMO-1")
    outcome = conformance(T.to_uif(item))
    assert outcome.conformant and outcome.advisories == ()


def test_free_prose_is_carried_verbatim_and_flagged_not_reshaped(jira):
    """DEMO-2's summary is "Archive is broken again" — a real Jira title and not
    a requirement. It lands as a `Finding` pointing at knowledge-capture, and
    the connector does not massage it into something that would pass (S-13)."""
    from metis_mcp.model_sources.intake_landing import conformance

    item = next(i for i in jira.items if i.key == "DEMO-2")
    document = T.to_uif(item)
    assert document["metadata"]["title"] == "Archive is broken again"
    assert any("Finding" in a for a in conformance(document).advisories)


def test_no_acceptance_criteria_are_claimed(jira):
    """A criterion asserted by the ticket that raised the requirement is not
    independent evidence of it. Emitting the key at all would invite a reader to
    trust it, and landing refuses to."""
    for item in jira.items:
        assert "acceptance_criteria" not in T.to_uif(item)
        assert "acceptance_criteria" not in T.to_uif(item)["metadata"]


def test_the_uif_is_stable_when_the_timestamp_is_supplied(jira):
    """`uif_generated_at` is excluded from `episode_id_for` precisely because it
    changes every run; pinning it here proves the rest of the document does
    not, so re-fetching an unchanged ticket is a no-op."""
    item = jira.items[0]
    first = T.to_uif(item, generated_at="2026-01-01T00:00:00Z")
    second = T.to_uif(item, generated_at="2026-01-01T00:00:00Z")
    assert first == second


# ---------------------------------------------------------------------------
# The selection rule this connector exposed
# ---------------------------------------------------------------------------

def test_the_ears_conformant_field_wins_over_field_order():
    """**Found by this connector.** A Jira story's *summary* is where the
    requirement-shaped sentence lives and its description is context prose;
    `_requirement_text` preferred description unconditionally and threw the
    conforming sentence away, landing the ticket as a `Finding`.

    This selects between two verbatim fields. It never rewrites either, which
    is the line `ac_mining` will not cross.
    """
    from metis_mcp.model_sources.intake_landing import _requirement_text

    document = {"metadata": {
        "title": "When a record has been archived, the system shall reject an "
                 "update with 409.",
        "description": "Archiving is terminal."}}
    assert _requirement_text(document).startswith("When a record")


def test_a_conformant_description_still_wins_when_both_conform():
    from metis_mcp.model_sources.intake_landing import _requirement_text

    document = {"metadata": {
        "title": "When A, the system shall B.",
        "description": "When C, the system shall D."}}
    assert _requirement_text(document).startswith("When C")


def test_neither_conforming_keeps_the_original_precedence():
    """The change must be monotone: it can turn a Finding into a Requirement
    where the text already conformed, and never the reverse."""
    from metis_mcp.model_sources.intake_landing import _requirement_text

    document = {"metadata": {"title": "t", "description": "d"}}
    assert _requirement_text(document) == "d"


# --------------------------------------------------------------------------
# Confluence — the one source ported into this reader rather than superseded
# --------------------------------------------------------------------------

CONFLUENCE_PAGE = {
    "id": "88021", "title": "Record locking", "status": "current",
    "body": {"storage": {"value":
        "<p>When a record is locked the service <strong>shall</strong> return "
        "409.</p><ac:structured-macro ac:name='code'>"
        "<ac:parameter ac:name='language'>json</ac:parameter>"
        "<ac:plain-text-body><![CDATA[{\"status\": 409}]]></ac:plain-text-body>"
        "</ac:structured-macro>"}},
    "metadata": {"labels": {"results": [{"name": "records"}, {"name": "api"}]}},
}
BASE = "https://wiki.example.org"


@pytest.fixture
def page():
    return T.item_from_payload("confluence", "88021", CONFLUENCE_PAGE, BASE)


def test_a_confluence_page_is_normalised(page):
    assert page.key == "88021"
    assert page.title == "Record locking"
    assert page.item_type == "Page"
    # The real `current`/`draft`, not a static: a page still in draft is exactly
    # what a reviewer needs flagged.
    assert page.status == "current"


def test_labels_come_from_nested_objects_not_their_repr(page):
    """Jira's labels are plain strings and Confluence's are `{"name": ...}`.
    Stringifying one of those lands the repr of a dict as a label."""
    assert page.labels == ("records", "api")


def test_storage_markup_is_flattened_to_text_and_nothing_is_reconstructed(page):
    assert "<p>" not in page.description and "<strong>" not in page.description
    assert "When a record is locked the service shall return 409." in page.description
    # A code macro's CDATA body is content and is kept.
    assert '{"status": 409}' in page.description
    # Its `language` parameter is configuration, and letting it through drops
    # the word `json` into the middle of a requirement.
    assert "json" not in page.description


def test_the_page_url_carries_the_page_id(page):
    """**The bug this pins.** Confluence payloads carry `id` where Jira carries
    `key`. The resolved key was used for identity and the raw parameter for the
    URL, so every page fetched from a fixture got `...?pageId=` with nothing
    after it — a link that silently resolves to a search page."""
    assert page.source_url == f"{BASE}/pages/viewpage.action?pageId=88021"
    assert page.source_url.endswith("88021")


def test_a_page_that_claims_acceptance_criteria_does_not_emit_any():
    """The extractor this replaces parsed an `Acceptance Criteria` heading into
    `specifications.acceptance_criteria` — manufacturing precisely the
    self-asserted criterion S-13 refuses to trust."""
    payload = dict(CONFLUENCE_PAGE)
    payload["body"] = {"storage": {"value":
        "<p>The service shall lock a record.</p>"
        "<h2>Acceptance Criteria</h2><ul><li>409 is returned</li></ul>"}}
    uif = T.to_uif(T.item_from_payload("confluence", "88021", payload, BASE))
    assert "acceptance_criteria" not in json.dumps(uif)
    # Nor an invented priority, which the extractor hardcoded to "high".
    assert "priority" not in json.dumps(uif)


def test_a_confluence_read_is_get_only_and_cannot_traverse(page):
    good = T.ENDPOINTS["confluence"].format(base=BASE, key="88021")
    T.assert_read_only([good])
    for bad in (f"{BASE}/rest/api/content/88021/child/page",
                f"{BASE}/rest/api/content/88021?expand=body.storage&status=draft"):
        with pytest.raises(T.TrackerRefused):
            T.assert_read_only([bad])


def test_a_page_with_no_body_is_empty_rather_than_a_traceback():
    """A read whose `expand` was dropped by a proxy has no `body`. The honest
    result is an empty description that `conformance` flags, not a traceback
    three layers from the cause."""
    item = T.item_from_payload("confluence", "1", {"id": "1", "title": "T"}, BASE)
    assert item.description == ""
    assert item.title == "T"


# ---------------------------------------------------------------------------
# Links, read from the response already being fetched
# ---------------------------------------------------------------------------
#
# No endpoint was added for this. `fields.parent` and `fields.issuelinks` are in
# the issue payload the reader already GETs, so `ENDPOINTS` stays the closed
# allowlist `assert_read_only` checks (X-7a) and no new read surface exists.

def test_a_jira_parent_becomes_a_parent_link():
    item = T.item_from_payload("jira", "PROJ-1", {
        "key": "PROJ-1",
        "fields": {"summary": "x", "issuetype": {"name": "Story"},
                   "parent": {"key": "PROJ-100"}}},
        base_url="https://tracker.example.com")
    (link,) = item.links
    assert link.relation == "parent"
    assert link.target_id == "PROJ-100"
    assert link.target_url.endswith("/browse/PROJ-100")


def test_a_classic_epic_link_is_normalised_to_parent():
    """Three spellings, one relation.

    `parent` (next-gen), an `Epic Link` and an inward `is subtask of` all mean
    the same thing to a reader. Normalising is what makes "which stories are
    under this epic" one question rather than three.
    """
    item = T.item_from_payload("jira", "PROJ-1", {
        "key": "PROJ-1",
        "fields": {"summary": "x", "issuetype": {"name": "Story"},
                   "issuelinks": [{"type": {"inward": "is subtask of",
                                            "outward": "has subtask"},
                                   "inwardIssue": {"key": "PROJ-100"}}]}})
    assert [(l.relation, l.target_id) for l in item.links] == [
        ("parent", "PROJ-100")]


def test_an_ordinary_link_keeps_the_trackers_own_relation_name():
    """Carried, and interpreted by nobody.

    A `relates to` means whatever the team that clicked it meant. Métis records
    that the tracker asserted it and reads nothing into it.
    """
    item = T.item_from_payload("jira", "PROJ-2", {
        "key": "PROJ-2",
        "fields": {"summary": "x", "issuetype": {"name": "Bug"},
                   "issuelinks": [{"type": {"inward": "is caused by",
                                            "outward": "causes"},
                                   "outwardIssue": {"key": "PROJ-1"}}]}})
    assert [(l.relation, l.target_id) for l in item.links] == [
        ("causes", "PROJ-1")]


def test_the_direction_the_payload_states_is_the_one_recorded():
    """`blocks` and `is blocked by` are not flattened into one claim."""
    inward = T.item_from_payload("jira", "A", {
        "key": "A", "fields": {"summary": "x", "issuetype": {"name": "Bug"},
                               "issuelinks": [{"type": {"inward": "is blocked by",
                                                        "outward": "blocks"},
                                               "inwardIssue": {"key": "B"}}]}})
    outward = T.item_from_payload("jira", "A", {
        "key": "A", "fields": {"summary": "x", "issuetype": {"name": "Bug"},
                               "issuelinks": [{"type": {"inward": "is blocked by",
                                                        "outward": "blocks"},
                                               "outwardIssue": {"key": "B"}}]}})
    assert inward.links[0].relation == "is blocked by"
    assert outward.links[0].relation == "blocks"


def test_a_tracker_with_no_link_concept_reports_none():
    """Zephyr Scale has no issue links. An empty tuple is a fact about the
    tracker, not a gap in the reader."""
    item = T.item_from_payload("scale", "T-1", {"key": "T-1", "name": "x"})
    assert item.links == ()


def test_reading_links_adds_no_endpoint():
    """The whole point of taking them from the existing payload.

    A search or a link-expansion endpoint would be an allowlist change, and the
    allowlist is what makes this intake read-only by construction rather than by
    intention.
    """
    assert set(T.ENDPOINTS) == {T.JIRA, T.ZEPHYR, T.CONFLUENCE}
    assert "issuelink" not in " ".join(T.ENDPOINTS.values())
    assert "search" not in " ".join(T.ENDPOINTS.values())
