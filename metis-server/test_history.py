"""
Repair history — reading it, and the line it must not cross.

`code_analysis/history.py` classifies commits and
`model_sources/repair_landing.py` lands them. The assertion this file exists to
make is the one `PROPOSAL-commits-and-defect-history.md` accepted the feature on:

    Métis never creates a `Defect` from a commit message.

A `Defect` node means somebody observed a fault. A commit message means somebody
typed a word. The gap between those is where a graph full of faults nobody
reported would come from, and it is one regex away at all times.
"""
from __future__ import annotations

import pytest

from code_analysis import history
from metis_mcp.model_sources import repair_landing


def _repair(sha="abc1234", subject="fix: a real one", files=("src/A.java",),
            tickets=(), basis="conventional-commit"):
    return history.Repair(sha=sha, subject=subject,
                          committed_at="2026-09-01T10:00:00Z", is_fix=True,
                          fix_basis=basis, files=files, tickets=tickets)


def _history(*repairs, since="v1", until="HEAD", read=40):
    return history.RepairHistory(since=since, until=until, repairs=repairs,
                                 commits_read=read)


def _java(path):
    return "demo::Records" if path.endswith(".java") else ""


# --- classification ----------------------------------------------------------

@pytest.mark.parametrize("subject,expected", [
    ("fix: null check on owner", "conventional-commit"),
    ("fix(records)!: reject empty title", "conventional-commit"),
    ("Fixed the retention bug", "subject-verb"),
    ("hotfix for the lock timeout", "subject-verb"),
    ('revert "the bad change"', "revert"),
])
def test_a_repair_is_classified_and_names_the_pattern_that_decided(subject, expected):
    """`fix_basis` is what lets a reader disagree with the classification rather
    than only with the count drawn from it."""
    is_fix, basis = history.classify(subject)

    assert is_fix is True
    assert basis == expected


@pytest.mark.parametrize("subject", [
    "add a new endpoint", "refactor the service", "bump the joern pin", "",
])
def test_an_ordinary_commit_is_not_a_repair(subject):
    assert history.classify(subject) == (False, "")


@pytest.mark.parametrize("subject", [
    "fix typo in README", "fix lint", "fixed formatting",
    "fix spelling in a comment", "fix imports",
])
def test_a_fix_that_is_not_about_the_product_is_excluded(subject):
    """Real logs are full of these, and counting them would make the noisiest
    file in a repository look like the most defect-prone one."""
    assert history.classify(subject)[0] is False


# --- ticket keys -------------------------------------------------------------

def test_a_ticket_key_is_read_out_of_the_subject():
    assert history.tickets_in("ABC-123 fix the thing") == ("ABC-123",)


def test_two_keys_are_kept_in_order_without_duplicates():
    assert history.tickets_in("fix ABC-1 and DEF-2, closes ABC-1") == ("ABC-1", "DEF-2")


@pytest.mark.parametrize("subject", ["upgrade to UTF-8", "support HTTP-2", "fix A-1"])
def test_a_loose_identifier_is_not_read_as_a_ticket(subject):
    """Matching anything looser turns every encoding and protocol into a ticket."""
    assert history.tickets_in(subject) == ()


# --- the read refuses rather than guessing -----------------------------------

def test_no_range_is_refused_because_a_count_needs_a_window():
    """"Eleven fixes" means nothing without "since when"."""
    result = history.read(".", since="")

    assert result.repairs == ()
    assert "window" in result.unavailable


def test_a_directory_that_is_not_a_repository_says_so_rather_than_raising(tmp_path):
    """The same shape `changed_files` uses: "I cannot tell you what changed" is
    a different answer from "nothing changed"."""
    result = history.read(tmp_path, since="HEAD~1")

    assert result.repairs == ()
    assert result.unavailable


def test_the_window_survives_into_the_result():
    result = history.read(".", since="HEAD~3", until="HEAD")

    assert (result.since, result.until) == ("HEAD~3", "HEAD")


# --- the rule the proposal accepted this on ----------------------------------

def test_no_defect_is_ever_planned_from_a_commit():
    """**The assertion this file exists for.** A commit subject is not a fault
    report, and a `Defect` node created from one would be a fault nobody
    observed, carrying a provenance that says somebody did.
    """
    plan = repair_landing.plan_repairs(
        _history(_repair(subject="fix: a crash BUG-1", tickets=("BUG-1",)),
                 _repair(sha="d2", subject="hotfix the defect", tickets=())),
        repo="demo", class_for_file=_java, known_tickets={"BUG-1"})

    assert plan.by_label("Defect") == []
    assert not [e for e in plan.edges if "Defect" in (e.from_label, e.to_label)]


def test_a_fix_links_to_the_item_because_the_item_is_the_report():
    plan = repair_landing.plan_repairs(
        _history(_repair(subject="fix ABC-1", tickets=("ABC-1",))),
        repo="demo", class_for_file=_java, known_tickets={"ABC-1"})

    fixes = [e for e in plan.edges if e.rel_type == "FIXES"]

    assert [(e.to_label, e.to_id) for e in fixes] == [("JiraItem", "jira:ABC-1")]


def test_a_ticket_the_graph_does_not_hold_is_reported_and_not_dropped():
    """**A missing item is information, not noise.**

    This originally skipped the edge in silence, which is the exact failure this
    codebase hunts for: a commit saying it fixed `ZZZ-9` when Métis has never
    heard of `ZZZ-9` means either the backlog was never intaken or the team
    references a project nobody mentioned. A plan that quietly omits the edge
    reports a clean landing over a broken chain.
    """
    plan = repair_landing.plan_repairs(
        _history(_repair(subject="fix ABC-1 and ZZZ-9", tickets=("ABC-1", "ZZZ-9"))),
        repo="demo", class_for_file=_java, known_tickets={"ABC-1"})

    assert [key for key, _ in plan.skipped] == ["ZZZ-9"]
    assert "not in the graph" in dict(plan.skipped)["ZZZ-9"]
    # The one it does hold is still linked: a missing sibling is not a reason to
    # lose the edge that is real.
    assert [e.to_id for e in plan.edges
            if e.rel_type == "FIXES"] == ["jira:ABC-1"]


def test_the_edge_targets_the_id_intake_landing_actually_writes():
    """`jira:ABC-1`, not the bare key. Built two different ways in two modules,
    the edge matches nothing at write time and `land` reports `unmatched` —
    which reads as a broken chain rather than as an id convention nobody shared.
    """
    plan = repair_landing.plan_repairs(
        _history(_repair(subject="fix ABC-1", tickets=("ABC-1",))),
        repo="demo", class_for_file=_java, known_tickets={"ABC-1"})

    assert repair_landing.anchor_id_for("ABC-1") == "jira:ABC-1"
    assert [e.to_id for e in plan.edges if e.rel_type == "FIXES"] == ["jira:ABC-1"]


# --- reading the missing item rather than only reporting it ------------------

def _tracker_read(keys, item_type="Bug"):
    from code_analysis.tracker import TrackerItem, TrackerRead

    return TrackerRead(system="jira", base_url="https://example.invalid",
                       items=tuple(TrackerItem(system="jira", key=k,
                                               title=f"Issue {k}",
                                               item_type=item_type)
                                   for k in keys))


def test_a_missing_item_is_read_from_the_tracker_then_linked():
    """The loop closed rather than reported: fetch first, land the anchor, and
    link the commit to a node that exists by the time the plan is written."""
    plan = repair_landing.plan_repairs(
        _history(_repair(subject="fix ZZZ-9", tickets=("ZZZ-9",))),
        repo="demo", class_for_file=_java, known_tickets=set(),
        fetch_missing=lambda keys: _tracker_read(keys))

    assert plan.skipped == []
    assert [n.properties["id"] for n in plan.by_label("JiraItem")] == ["jira:ZZZ-9"]
    assert [e.to_id for e in plan.edges if e.rel_type == "FIXES"] == ["jira:ZZZ-9"]


def test_a_fetched_item_lands_at_quarantine():
    """Reading a ticket is not approving what it says (S-4)."""
    plan = repair_landing.plan_repairs(
        _history(_repair(subject="fix ZZZ-9", tickets=("ZZZ-9",))),
        repo="demo", fetch_missing=lambda keys: _tracker_read(keys))

    assert all(n.properties["lifecycle_state"] == "Quarantine"
               for n in plan.by_label("JiraItem"))


def test_a_fetched_item_with_no_type_is_unknown_and_not_a_bug():
    """Defaulting to `Bug` would assert a defect nobody typed — the same line
    the whole module is drawn on, one field over."""
    plan = repair_landing.plan_repairs(
        _history(_repair(subject="fix ZZZ-9", tickets=("ZZZ-9",))),
        repo="demo", fetch_missing=lambda keys: _tracker_read(keys, item_type=""))

    assert plan.by_label("JiraItem")[0].properties["issue_type"] == "unknown"


def test_a_tracker_that_cannot_be_read_is_reported_and_the_history_still_lands():
    """A tracker being down is a fact about this run, not a reason to lose the
    repairs. The keys are reported with the transport failure named."""
    def refuse(keys):
        raise RuntimeError("401 Unauthorized")

    plan = repair_landing.plan_repairs(
        _history(_repair(subject="fix ZZZ-9", tickets=("ZZZ-9",))),
        repo="demo", class_for_file=_java, fetch_missing=refuse)

    assert plan.by_label("Commit"), "the repairs still landed"
    assert any("401 Unauthorized" in why for _, why in plan.skipped)


def test_nothing_is_fetched_when_every_ticket_is_already_held():
    """No network call on the ordinary path."""
    calls = []

    repair_landing.plan_repairs(
        _history(_repair(subject="fix ABC-1", tickets=("ABC-1",))),
        repo="demo", known_tickets={"ABC-1"},
        fetch_missing=lambda keys: calls.append(keys) or _tracker_read(keys))

    assert calls == []


def test_fetching_still_creates_no_defect():
    """The rule survives the new path: an item read from the tracker is an
    ITEM. Whether it is a defect is what its `issue_type` says, and that is the
    tracker's claim rather than Métis's."""
    plan = repair_landing.plan_repairs(
        _history(_repair(subject="fix ZZZ-9", tickets=("ZZZ-9",))),
        repo="demo", fetch_missing=lambda keys: _tracker_read(keys))

    assert plan.by_label("Defect") == []


def test_no_author_is_read_or_landed():
    """A defect count per person is a management use of a quality signal, and
    this system does not supply the column."""
    plan = repair_landing.plan_repairs(
        _history(_repair()), repo="demo", class_for_file=_java)

    for node in plan.nodes:
        assert not any(k in node.properties
                       for k in ("author", "author_email", "committer"))
    assert "%an" not in (history.read.__doc__ or "")


# --- the plan is legal, and says what it read --------------------------------

def test_the_plan_passes_the_same_gate_every_other_write_does():
    plan = repair_landing.plan_repairs(
        _history(_repair()), repo="demo", class_for_file=_java)

    assert plan.is_legal, plan.errors


def test_every_commit_lands_at_quarantine():
    """An observed repair is still a claim: the classification is a regex
    against somebody's prose (S-4)."""
    plan = repair_landing.plan_repairs(
        _history(_repair()), repo="demo", class_for_file=_java)

    assert all(n.properties["lifecycle_state"] == "Quarantine"
               for n in plan.by_label("Commit"))


def test_the_window_is_recorded_on_the_episode():
    plan = repair_landing.plan_repairs(
        _history(_repair(), since="v2.1", until="v2.2"), repo="demo",
        class_for_file=_java)

    evidence = plan.by_label("Episode")[0].properties["evidence"]

    assert "since=v2.1" in evidence and "until=v2.2" in evidence
    assert "commits_read=40" in evidence, "a fix rate needs a denominator"


def test_re_reading_one_window_is_a_no_op():
    """D-8: content-derived ids, so a second read is not a second run."""
    first = repair_landing.plan_repairs(_history(_repair()), repo="demo")
    second = repair_landing.plan_repairs(_history(_repair()), repo="demo")

    assert first.episode_id == second.episode_id


def test_a_file_that_reaches_no_class_gets_no_edge():
    """A build script and a README are real changes that reach no type, and
    inventing a node for them would put code structure in the graph that no
    requirement question needs (X-6d)."""
    plan = repair_landing.plan_repairs(
        _history(_repair(files=("src/A.java", "README.md", "build.gradle"))),
        repo="demo", class_for_file=_java)

    assert len([e for e in plan.edges if e.rel_type == "TOUCHES"]) == 1


# --- the figure the risk model bands -----------------------------------------

def test_one_repair_touching_three_files_of_a_class_counts_once():
    """Counting per file would rank a type by how it happens to be split across
    files rather than by how often it has needed repairing."""
    counts = repair_landing.fixes_by_class(
        _history(_repair(files=("src/A.java", "src/B.java"))),
        lambda path: "demo::Records")

    assert counts == {"demo::Records": 1}


def test_repairs_accumulate_across_commits():
    counts = repair_landing.fixes_by_class(
        _history(_repair(sha="a"), _repair(sha="b"), _repair(sha="c")), _java)

    assert counts == {"demo::Records": 3}
