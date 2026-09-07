"""
Repair history into the graph — `Commit`, what it touched, what it fixed.

The landing half of `code_analysis.history`. Pure: a `RepairHistory` and a file
→ class-id resolver in, a `LandingPlan` out, nothing written.

**Three rules travel with it, and they are the reason the proposal was accepted
rather than the feature just built** (`PROPOSAL-commits-and-defect-history.md`):

1. **No `Defect` is ever planned here.** A commit subject is not a fault report.
   Where a subject names a ticket key the edge is `FIXES` to the `JiraItem`,
   because the item is the report and the commit is only evidence about it.
   `test_history.py` asserts the plan contains no `Defect` node whatever the
   input.

2. **`is_fix` carries `fix_basis`.** The classification is a claim about the
   message, and naming the pattern that matched is what lets a reader disagree
   with the claim rather than only with the count drawn from it.

3. **The window is on the `Episode`.** A fix count with no range is not a
   measurement, and the range is a property of the read rather than of any
   commit in it.

Landing at `Quarantine` like every other source (S-4). An observed repair is
still a claim: the classification is a regex against somebody's prose.
"""
from __future__ import annotations

import hashlib

from metis_mcp.mbt.model import QUARANTINE
from metis_mcp.model_sources.landing import LandingPlan

PROVENANCE = "recovered_from_history"


def episode_id_for(repo: str, since: str, until: str) -> str:
    """Content-derived (D-8): re-reading one window is a no-op, not a second run."""
    basis = "|".join(("repair-history", repo, since, until))
    return "ep-fix-" + hashlib.sha256(basis.encode()).hexdigest()[:16]


def commit_id(repo: str, sha: str) -> str:
    """Namespaced like every other id, so two repositories never collide."""
    return f"{repo}::commit::{sha}"


def _anchor_label(system: str) -> str:
    """The anchor label for a tracker. Only Jira has a `FIXES` edge today."""
    return {"jira": "JiraItem", "zephyr": "ZephyrItem",
            "confluence": "ConfluenceItem"}.get(system, "JiraItem")


def anchor_id_for(key: str, system: str = "jira") -> str:
    """The id `intake_landing` gives a tracker anchor: `jira:ABC-1`.

    Derived here rather than assumed, because the first version of this module
    edged to the bare key and would have matched nothing at write time — `land`
    reports that as `unmatched`, which reads as a broken chain rather than as an
    id built two different ways in two modules.
    """
    return f"{system}:{key}"


def plan_repairs(history, *, repo: str, class_for_file=None,
                 known_tickets=(), fetch_missing=None, system: str = "jira",
                 job_id: str = "history", t_recorded: str = "") -> LandingPlan:
    """`Episode` + one `Commit` per repair, with its edges.

    `class_for_file` maps a repo-relative path to a `Class` node id, or returns
    "" where the file is not one Métis landed — a build script and a README are
    real changes and reach no type, and inventing a node for them would put code
    structure in the graph that no requirement question needs (X-6d).

    `known_tickets` is the set of tracker KEYS the graph already holds.

    **A ticket the graph does not hold is reported, never dropped.** The first
    version of this silently skipped the edge, which is the exact failure this
    codebase hunts for: a commit saying it fixed `ABC-123` when Métis has never
    heard of `ABC-123` is *information* — either the backlog was never intaken,
    or the team references a project nobody told Métis about — and a plan that
    quietly omits the edge reports a clean landing over a broken chain. Every
    unresolved key lands in `plan.skipped` with the reason.

    **`fetch_missing` closes the loop rather than reporting it.** Given a
    callable taking a list of keys and returning a `tracker.TrackerRead`, the
    missing items are read from the tracker FIRST, landed as anchors, and the
    commit is then linked to a node that exists. It is injected for the same
    reason `tracker.read` injects `get`: no HTTP library is a dependency of
    Métis, the credential never passes through here (PLT-005), and a test can
    supply a stub. Absent, the keys are simply reported — fetching is a network
    call and this never makes one on its own.

    A fetched item lands at `Quarantine` like every other anchor. Reading a
    ticket is not approving what it says.
    """
    from datetime import datetime, timezone

    recorded = t_recorded or datetime.now(timezone.utc).isoformat(timespec="seconds")
    episode_id = episode_id_for(repo, history.since, history.until)
    plan = LandingPlan(episode_id=episode_id, project=repo)

    plan.add_node("Episode", {
        "id": episode_id,
        "name": f"repair history: {history.since}..{history.until}",
        "t_recorded": recorded,
        "source_connector": "repair-history",
        "job_id": job_id,
        # The window, on the record of the read rather than on any commit in it.
        "evidence": (f"repo={repo}, since={history.since}, until={history.until}, "
                     f"commits_read={history.commits_read}"),
        "commit": history.until,
        "proposed_by": "code_analysis.history",
    })

    resolve = class_for_file or (lambda path: "")
    tickets = {str(k) for k in (known_tickets or ())}

    # **Resolve the tickets before any commit is planned**, so a commit is only
    # ever linked to a node that exists by the time the plan is written.
    named = {key for repair in history.repairs if repair.is_fix
             for key in repair.tickets}
    missing = sorted(named - tickets)
    fetched: list[str] = []

    if missing and fetch_missing is not None:
        try:
            read = fetch_missing(missing)
        except Exception as e:                      # transport, auth, refusal
            # Reported, not raised: the repairs are still worth landing, and a
            # tracker that is down is a fact about this run rather than a reason
            # to lose the history.
            plan.skipped.append(
                (", ".join(missing),
                 f"the tracker could not be read ({type(e).__name__}: {e}), so "
                 f"these items were neither fetched nor linked"))
            read = None
        for item in getattr(read, "items", ()) or ():
            anchor = anchor_id_for(item.key, system)
            if plan.add_node(_anchor_label(system), {
                "id": anchor,
                "source_episode_id": episode_id,
                "name": item.title or item.key,
                f"{system}_key": item.key,
                # Its second required property. `unknown` where the tracker
                # states none -- never defaulted to `Bug`, which would assert a
                # defect nobody typed.
                "issue_type": item.item_type or "unknown",
                "lifecycle_state": QUARANTINE,
            }):
                tickets.add(item.key)
                fetched.append(item.key)

    for key in sorted(named - tickets):
        plan.skipped.append((
            key,
            "named by a fix commit and not in the graph — the item was never "
            "intaken, or it belongs to a project Métis has not been told about. "
            "No FIXES edge was planned; pass `fetch_missing` to read it from "
            "the tracker instead of reporting it"))

    for repair in history.repairs:
        if not repair.is_fix:
            continue
        cid = commit_id(repo, repair.sha)
        # Branch on the outcome: `add_node` returns whether the node was
        # accepted, and planning edges from a refused node produces a plan whose
        # edges match nothing at write time — reported as `unmatched`, which
        # reads as a broken chain rather than as a node that was never legal.
        accepted = plan.add_node("Commit", {
            "id": cid,
            "name": f"{repair.sha[:8]} {repair.subject}"[:120],
            "source_episode_id": episode_id,
            "sha": repair.sha,
            "subject": repair.subject,
            "committed_at": repair.committed_at,
            "provenance": PROVENANCE,
            "is_fix": True,
            # Which pattern decided. Empty is illegal for a fix and the label
            # contract allows it empty only because a non-fix carries none.
            "fix_basis": repair.fix_basis,
            "lifecycle_state": QUARANTINE,
        })

        if not accepted:
            continue

        for path in repair.files:
            class_id = resolve(path)
            if class_id:
                plan.add_edge("Commit", cid, "TOUCHES", "Class", class_id)

        for key in repair.tickets:
            if key in tickets:
                plan.add_edge("Commit", cid, "FIXES", _anchor_label(system),
                              anchor_id_for(key, system))

    return plan


def fixes_by_class(history, class_for_file) -> dict[str, int]:
    """`{class id: repairs}` — the figure `risk/product.py` bands.

    Counted per class rather than per file because that is the node the risk
    model reaches. A commit touching three files of one class counts once for
    it: the repair is one event, and counting it three times would rank a
    type by how it happens to be split across files.
    """
    counts: dict[str, int] = {}
    for repair in history.repairs:
        if not repair.is_fix:
            continue
        touched = {class_for_file(path) for path in repair.files}
        for class_id in touched:
            if class_id:
                counts[class_id] = counts.get(class_id, 0) + 1
    return counts
