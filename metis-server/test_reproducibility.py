"""
Same data in, same graph out (TR-6, A-25, D-8).

**Free to run.** Landing plans are pure — no session, no writes — and a plan
fully determines what a run writes, so plan equality is graph equality without
needing a database. That matters: the whole suite runs with no Neo4j, and this
file must not be the one that changes it.

Twelve determinism tests already existed when this was written, and every one of
them covered a pure function in isolation — drafting, mining, rendering, one
writer's statement list. What none of them covered is the property the system
actually claims: TR-6 says *"Re-running is idempotent"* and A-25 says
*"Re-running any operation produces no duplicates"*, and nothing failed if that
stopped being true.

**Why the clock is injected rather than left alone.** Every landing path reads
`t_recorded or datetime.now(timezone.utc).isoformat(timespec="seconds")`. At
one-second resolution two plans built back to back almost always land in the
same second, so a test that just called them twice would pass on timing and fail
on a slow machine — the worst kind of green. Passing an explicit `t_recorded`
makes the question sharp: with the clock held still, is *everything else*
reproducible? And with the clock moved deliberately, does *only* the timestamp
move?
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

from mbt_fixtures import login_model_source
from metis_mcp.model_sources import get, plan_landing

FIXTURES = Path(__file__).parent / "test_fixtures"

# Two instants that are definitely not the same second, so "did the timestamp
# move" is answered by the input rather than by how fast the machine is.
CLOCK_A = "2026-01-01T00:00:00+00:00"
CLOCK_B = "2027-06-15T12:34:56+00:00"


def _authored(tmpdir: str):
    path = Path(tmpdir) / "login-api.json"
    path.write_text(json.dumps(login_model_source(), indent=2))
    return get("authored").produce(path=str(path), author="alice")


def _openapi():
    return get("openapi").produce(path=str(FIXTURES / "records-openapi.json"),
                                  journey="records")


def _canonical(plan) -> dict:
    """A plan as comparable data, ORDER PRESERVED.

    Sets would hide the failure this is looking for. Two runs that plan the same
    nodes in a different order produce the same graph but not the same diff, and
    "what changed since last time" is the question reproducibility exists to
    answer.
    """
    return {
        "episode_id": plan.episode_id,
        "nodes": [(n.label, dict(sorted(n.properties.items()))) for n in plan.nodes],
        "edges": [(e.from_label, e.from_id, e.rel_type, e.to_label, e.to_id)
                  for e in plan.edges],
        "errors": list(plan.errors),
    }


def _plans(build, clock=CLOCK_A):
    """One source, planned twice at the same instant."""
    return _canonical(build(clock)), _canonical(build(clock))


# --------------------------------------------------------------------------
# With the clock held still, everything is reproducible
# --------------------------------------------------------------------------

def test_an_authored_model_plans_identically_twice():
    with tempfile.TemporaryDirectory() as tmp:
        def build(clock):
            return plan_landing(_authored(tmp), journey="login", t_recorded=clock)
        first, second = _plans(build)
    assert first == second


def test_an_openapi_document_plans_identically_twice():
    def build(clock):
        return plan_landing(_openapi(), journey="records", t_recorded=clock)
    first, second = _plans(build)
    assert first == second


def test_the_node_order_is_stable_and_not_merely_the_node_set():
    """Order, explicitly. A plan whose nodes shuffle between runs still writes
    the same graph, and still makes every diff of two runs unreadable."""
    with tempfile.TemporaryDirectory() as tmp:
        def build(clock):
            return plan_landing(_authored(tmp), journey="login", t_recorded=clock)
        first, second = _plans(build)
    assert [label for label, _ in first["nodes"]] == \
           [label for label, _ in second["nodes"]]


# --------------------------------------------------------------------------
# The timestamp must not reach identity
# --------------------------------------------------------------------------

def test_the_episode_id_ignores_the_clock():
    """D-8: identity is content-derived. `intake_landing.episode_id_for` says
    why in as many words — including a timestamp "would mint a new Episode each
    time and make TR-6 unachievable"."""
    with tempfile.TemporaryDirectory() as tmp:
        early = plan_landing(_authored(tmp), journey="login", t_recorded=CLOCK_A)
        late = plan_landing(_authored(tmp), journey="login", t_recorded=CLOCK_B)
    assert early.episode_id == late.episode_id


def test_only_the_timestamp_moves_when_the_clock_moves():
    """The leak, bounded precisely.

    `t_recorded` is a real property on the Episode and it is expected to differ
    between two runs at two different instants. What must NOT differ is anything
    else — an id, a name, an edge, a count. This states exactly how far the
    clock's influence reaches, so a change that widens it fails here rather than
    being absorbed into "well, timestamps differ".
    """
    with tempfile.TemporaryDirectory() as tmp:
        early = _canonical(plan_landing(_authored(tmp), journey="login",
                                        t_recorded=CLOCK_A))
        late = _canonical(plan_landing(_authored(tmp), journey="login",
                                       t_recorded=CLOCK_B))

    assert early["edges"] == late["edges"]
    assert early["episode_id"] == late["episode_id"]
    assert len(early["nodes"]) == len(late["nodes"])

    differing = []
    for (label_a, props_a), (label_b, props_b) in zip(early["nodes"], late["nodes"]):
        assert label_a == label_b
        for key in sorted(set(props_a) | set(props_b)):
            if props_a.get(key) != props_b.get(key):
                differing.append((label_a, key))

    assert {key for _, key in differing} <= {"t_recorded"}, (
        f"the clock reached further than t_recorded: {sorted(set(differing))}")


# --------------------------------------------------------------------------
# Nothing is minted from entropy
# --------------------------------------------------------------------------

_ENTROPY = re.compile(r"\b(uuid4?|random\.|secrets\.|os\.urandom)\b")


def test_no_landing_path_mints_anything_from_entropy():
    """A random id is unfixable after the fact: it is already in the graph, and
    nothing can tell it from a real one. Cheaper to refuse the import than to
    detect the consequence.

    Scanned rather than asserted on behaviour, because the failure mode is a
    single call site added years from now and reviewed by someone who has never
    read TR-6.
    """
    roots = [Path("metis_mcp/model_sources"), Path("metis_mcp/identity")]
    offences = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            for number, line in enumerate(path.read_text().splitlines(), 1):
                code = line.split("#", 1)[0]
                if _ENTROPY.search(code):
                    offences.append(f"{path}:{number}: {line.strip()}")
    assert not offences, (
        "identity in a landing path must be derived from content (D-8):\n  "
        + "\n  ".join(offences))


# --------------------------------------------------------------------------
# The declaration and the behaviour must agree
# --------------------------------------------------------------------------

# Intakes whose `temporal.t_recorded_source` names a deterministic origin that
# NOTHING currently supplies. Every landing path reads
# `t_recorded or datetime.now(...)`, and no caller anywhere passes the argument —
# so the declared source is documentation of an intention, not of a behaviour.
#
# The consequence is now small. `t_recorded` is a FIRST_SEEN fact, so it is
# written by `ON CREATE SET` and a re-land does not touch it: a second landing of
# unchanged content leaves the graph byte-identical (verified against a
# throwaway Neo4j — 28 nodes, 34 edges, every property equal, with an 18-month
# gap between the two runs).
#
# What is still true is that the FIRST landing stamps the wall clock rather than
# the data's own time, so two SEPARATE estates ingesting the same commit record
# different instants. That is what threading the declared source would fix.
#
# Listed rather than silently tolerated. Removing an entry is the whole fix.
TIMESTAMP_NOT_THREADED = {
    "code": "the commit's own date is available (`git show -s --format=%cI`) "
            "and is not read; `engine.extract` already takes `commit`",
    "openapi": "the document's version field is deterministic; the declared "
               "fallback to file mtime is NOT — git does not preserve mtime, so "
               "a fresh clone would land a different timestamp for identical "
               "content, which is the opposite of what this is for",
    "database": "genuinely has none — a catalogue carries no timestamp of its "
                "own, and the declaration says so. This entry is permanent",
    "confluence": "partial intake; `scope.uif_generated_at` arrives in the UIF",
    "jira": "partial intake; `scope.uif_generated_at` arrives in the UIF",
    "uif": "partial intake; `scope.uif_generated_at` arrives in the UIF",
    "zephyr": "partial intake; `scope.uif_generated_at` arrives in the UIF",
}


def test_every_intake_declaring_a_deterministic_time_either_uses_it_or_says_why():
    """`connectors/intakes.json` declares a `t_recorded_source` per intake. That
    declaration is checked for shape by `test_intakes.py` and, until this test,
    against nothing at all — so it could describe a behaviour that had never
    been implemented, and did.

    Asserted against the declaration rather than a copy of it, so adding a
    temporal block to a new intake fails here until someone decides whether it
    is threaded or exempt.
    """
    from metis_mcp import intakes

    declared = {i["id"] for i in intakes.load()["intakes"] if i.get("temporal")}
    unexplained = declared - set(TIMESTAMP_NOT_THREADED)
    assert not unexplained, (
        f"{sorted(unexplained)} declare a deterministic t_recorded source. "
        f"Either thread it through to the landing plan, or record here why not.")

    stale = set(TIMESTAMP_NOT_THREADED) - declared
    assert not stale, (
        f"{sorted(stale)} are listed as not-threaded and declare no temporal "
        f"source at all — delete them from TIMESTAMP_NOT_THREADED")


def test_the_wall_clock_fallback_is_the_only_source_of_run_to_run_drift():
    """Stated as a bound, so widening it is a failure rather than a detail.

    Every landing module reaches for the clock the same way. If a second kind of
    run-to-run variation appears — a counter, a set iteration order, a PID — it
    will not look like this pattern and will not be counted here, which is the
    point: the assertion is that the clock is the ONLY thing to fix.
    """
    import re as _re
    from pathlib import Path as _Path

    pattern = _re.compile(r"t_recorded or datetime\.now")
    found = set()
    for path in sorted(_Path("metis_mcp/model_sources").rglob("*.py")):
        if pattern.search(path.read_text()):
            found.add(path.name)

    # Six modules, seven call sites (`data_landing.py` has two). `glossary.py`
    # is in this list because this assertion put it there: it was missed when the
    # set was first written by hand from a truncated grep, and the test failed on
    # its first run rather than enshrining the omission.
    # `knowledge.py` joined this set when bi-temporal validity landed: it had no
    # timestamp at all, and `valid_from` needs one. That is a step in the WRONG
    # direction — `valid_from` is a claim about when something became true, so it
    # wants the data's own time (a commit date), not the clock. Recorded here
    # rather than waved through; see TIMESTAMP_NOT_THREADED.
    assert found == {"landing.py", "raw_landing.py", "intake_landing.py",
                     "data_landing.py", "intent.py", "glossary.py",
                     "knowledge.py", "lessons.py"}, (
        f"the set of modules defaulting to the clock changed: {sorted(found)}. "
        f"If one was fixed, remove it here; if one was added, it needs a "
        f"deterministic source or an entry in TIMESTAMP_NOT_THREADED.")


# --------------------------------------------------------------------------
# What re-landing does to the graph, stated exactly
# --------------------------------------------------------------------------

def test_the_timestamp_is_written_once_and_never_re_asserted():
    """Re-landing unchanged content must not rewrite `t_recorded`.

    The write is::

        MERGE (n:Label {id: row.id})
        ON CREATE SET n += row.on_create
        SET n += row.machine

    `t_recorded` used to be a machine fact, so the second clause rewrote it on
    every run: identity was stable (no duplicate node, TR-6 satisfied) and the
    bytes never were, which is the half anyone diffing two runs needs.

    It is now a FIRST_SEEN fact. Deliberately NOT folded into `HUMAN_FACTS` --
    no reviewer decided it, and that tuple's contract is that a write path may
    never assert its members. Two reasons, one `ON CREATE SET` clause, two names
    so the next person adding a field has to say which reason applies.
    """
    from metis_mcp.model_sources.landing import (
        FIRST_SEEN_FACTS,
        HUMAN_FACTS,
        ON_CREATE_FACTS,
        VALIDITY_FACTS,
        split_row,
    )

    assert HUMAN_FACTS == ("lifecycle_state", "name", "name_tier", "provenance")
    assert "t_recorded" not in HUMAN_FACTS, "a timestamp is not a reviewer's decision"
    assert FIRST_SEEN_FACTS == ("t_recorded",)
    # Validity joins the same clause for a third reason: `valid_to` is SET by
    # invalidation, so a re-land that re-asserted it would reset a superseded
    # fact to valid and undo the invalidation silently.
    assert VALIDITY_FACTS == ("valid_from", "valid_to")
    assert set(ON_CREATE_FACTS) == (
        set(HUMAN_FACTS) | set(FIRST_SEEN_FACTS) | set(VALIDITY_FACTS))

    row = {"id": "ep-1", "t_recorded": CLOCK_A, "lifecycle_state": "Quarantine",
           "name": "Given", "trigger": "GET /record", "guard": "x > 1"}
    split = split_row(row)

    # On the ON CREATE side: written once, kept afterwards.
    assert split["on_create"]["t_recorded"] == CLOCK_A
    assert split["on_create"]["lifecycle_state"] == "Quarantine"
    # On the re-asserted side: machine facts are re-derived every run by design.
    # `id` rides along in the machine bucket, as it did before this split
    # existed: `SET n += row.machine` re-setting the MERGE key to the value it
    # was matched on is a no-op, and excluding it would be unrelated churn.
    assert split["machine"] == {"id": "ep-1", "trigger": "GET /record",
                                "guard": "x > 1"}
    assert "t_recorded" not in split["machine"], (
        "a re-asserted timestamp makes every re-run a different graph")

    # Nothing is lost by the split -- a property in neither bucket is a property
    # that silently stops being written.
    assert set(split["on_create"]) | set(split["machine"]) == set(row)


def test_a_second_land_of_unchanged_content_changes_nothing():
    """The property stated end to end, at the level the plan can prove it.

    Two plans built at two different instants over identical input: the node
    written on the second run must carry no `machine` property that differs from
    the first, and its `on_create` payload is irrelevant because MERGE will not
    apply it to an existing node.
    """
    from metis_mcp.model_sources.landing import split_row

    with tempfile.TemporaryDirectory() as tmp:
        early = plan_landing(_authored(tmp), journey="login", t_recorded=CLOCK_A)
        late = plan_landing(_authored(tmp), journey="login", t_recorded=CLOCK_B)

    assert early.episode_id == late.episode_id
    for first, second in zip(early.nodes, late.nodes):
        a, b = split_row(first.properties), split_row(second.properties)
        assert a["id"] == b["id"]
        moved = sorted(k for k in set(a["machine"]) | set(b["machine"])
                       if a["machine"].get(k) != b["machine"].get(k))
        assert not moved, (
            f"{first.label} re-asserts {moved}, which moved with the clock — "
            f"every re-run would write a different graph")


# --------------------------------------------------------------------------
# The OpenAPI declaration is a Fact, and reaches the same node the code does
#
# §4.1's comparison is a report-level set difference (`test_extraction.py::
# test_the_three_deviations_and_no_others`), computed BEFORE anything is landed.
# Sharing identity in the graph therefore does not weaken it: the two sources
# still disagree in exactly the same places, and now the agreement is expressible
# as one node carrying evidence from both rather than two nodes nobody can join.
# --------------------------------------------------------------------------

def test_both_intakes_mint_the_same_endpoint_id_for_one_route():
    """The natural key already does the work: `raw_landing.endpoint_id` is keyed
    on `(repo, service, method, path)`, not on the source's own id.

    Neither source's own id space reaches the graph — the code's is a handler
    signature, the contract's an operationId, and they will never agree.
    """
    from metis_mcp.model_sources.raw_landing import endpoint_id

    assert endpoint_id("records", "GET", "/record/{id}", "") == \
           endpoint_id("records", "GET", "/record/{id}", "")

    # The scope is part of the key on purpose: a path is not unique across a
    # monorepo, and two services declaring `GET /summary` must not fuse.
    assert endpoint_id("records", "GET", "/record/{id}", "") != \
           endpoint_id("other", "GET", "/record/{id}", "")


def test_the_openapi_source_carries_its_evidence_layer():
    """`connectors/intakes.json` declares the openapi intake lands `Endpoint`,
    `DeclaredOutcome`, `Parameter` and `Class`. It did not.

    `workflow/handlers.py` plans the evidence layer from `SourceResult.reports`,
    and this source never populated it — so `reports.get("structural")` was None,
    the handler took the "not every source has an evidence layer" branch meant
    for hand-authored models, and every declared fact in the document was dropped
    in silence. The same declaration-vs-behaviour split as the `t_recorded`
    sources above.
    """
    from metis_mcp.model_sources import get

    result = get("openapi").produce(path=str(FIXTURES / "records-openapi.json"),
                                    journey="records")
    assert result.reports, (
        "the openapi source produced no reports, so its Endpoint / "
        "DeclaredOutcome / Parameter / Class facts are never planned")
    assert "structural" in result.reports
    assert result.reports["structural"].endpoints, "no endpoints carried"

    # `behaviour` is absent on purpose: a document DECLARES outcomes, it does not
    # implement them, and `plan_raw_landing` treats absent as absent rather than
    # as an empty behaviour layer.
    assert "behaviour" not in result.reports
