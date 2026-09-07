"""
Ingesting what a running system did (the change to §8.7).

**Six labels were staged out with the condition that would bring them back**, and
this is that condition arriving: `TestExecution` and `TestCycle` were held
against "execution results are ingested (spec C-10's trigger)", `Defect`,
`Metrics`, `Logs` and `Alert` against "operational data enters scope".

**C-10 and C-11 both survive, and the design is what makes that true.**

  * C-10 constrains the coverage LEDGER: a row says a case *covers* a
    transition, never that it passed. Nothing here writes to that ledger, and
    `test_execution_intake.py` asserts it structurally rather than trusting it.
  * C-11 constrains a coverage FIGURE: it answers "is this behaviour tested?".
    That is unchanged. What is added is a SECOND figure answering "did it
    pass?", which is a different question about the same transition.

A transition may be fully covered and currently failing. Before this Métis could
not see the second half; it still does not report it as the first.

**Everything landed here carries `provenance: observed_from_running_system`**,
and it attaches to a `TestCase` rather than to a `Transition`. That routing is
the load-bearing decision: an execution is evidence about an artefact somebody
ran, and edging it to the transition would make "this behaviour passed"
expressible in one hop — which is exactly the conflation §6.8a names as the
reason the labels were staged out.

**Landing at `Quarantine` like everything else** (S-4). An observed result is
still a claim: it says a run happened and reported an outcome, not that the
outcome was correctly attributed.
"""
from __future__ import annotations

from datetime import datetime, timezone

PROVENANCE = "observed_from_running_system"

OUTCOMES = ("passed", "failed", "skipped", "errored", "not_run")


class IntakeRefused(Exception):
    """The result cannot be landed as stated. Nothing was written."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalise(result: dict) -> dict:
    """One execution record, checked before anything is planned.

    Refuses rather than defaults. An outcome this does not recognise is not
    silently `not_run`: a runner emitting `flaky` or `passed-on-retry` is saying
    something, and flattening it loses the only interesting part.
    """
    case_id = str(result.get("case_id", "")).strip()
    if not case_id:
        raise IntakeRefused(
            "an execution belongs to a case; without `case_id` there is nothing "
            "to attach it to (and attaching it to a transition is exactly what "
            "this must not do)")

    outcome = str(result.get("outcome", "")).strip().lower()
    if outcome not in OUTCOMES:
        raise IntakeRefused(
            f"outcome {outcome or '(none)'!r} is not one of "
            f"{', '.join(OUTCOMES)}. Map it deliberately rather than letting it "
            f"default — a runner that says `flaky` is telling you something")

    return {
        "case_id": case_id,
        "outcome": outcome,
        "observed_at": str(result.get("observed_at") or _now()),
        "duration_ms": int(result.get("duration_ms") or 0),
        # Kept verbatim and never parsed into a claim: a failure message is the
        # runner's words, and rewriting it into a cause is analysis nobody did.
        "detail": str(result.get("detail", ""))[:2000],
        "provenance": PROVENANCE,
    }


def summarise(results: list[dict]) -> dict:
    """The outcome figure — deliberately NOT a coverage figure.

    Reported beside coverage and never merged into it. The two answer different
    questions, and a reader given one number cannot tell which they were
    handed.
    """
    counts: dict[str, int] = {}
    for r in results:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    ran = sum(counts.get(o, 0) for o in ("passed", "failed", "errored"))

    return {
        "executions": len(results),
        "by_outcome": counts,
        # Absent rather than zero when nothing ran: a pass rate over no runs is
        # a division nobody should see the result of.
        "passed_of_ran": (f"{counts.get('passed', 0)}/{ran}" if ran
                          else "nothing ran"),
        "provenance": PROVENANCE,
        "means": ("what happened when these cases were run — NOT coverage. "
                  "A transition may be fully covered and currently failing, "
                  "and these are the two halves of that sentence (C-10, C-11)"),
    }


def plan_execution_landing(results: list[dict], *, cycle: str = "",
                           job_id: str = "execution") -> dict:
    """The nodes and edges an ingest would write. Pure — nothing is written.

    Returns a plan in the shape `model_sources.landing` consumes, so the same
    legality gate that governs every other write governs this one too.
    """
    normalised = [normalise(r) for r in results]
    nodes, edges = [], []

    cycle_id = f"cycle::{cycle}" if cycle else ""
    if cycle_id:
        nodes.append({"label": "TestCycle", "id": cycle_id,
                      "properties": {"id": cycle_id, "name": cycle,
                                     "started_at": _now(),
                                     "provenance": PROVENANCE,
                                     "lifecycle_state": "Quarantine"}})

    for item in normalised:
        # Content-derived, so re-landing the same observed run is a no-op rather
        # than a second execution somebody has to reconcile.
        exec_id = (f"exec::{item['case_id']}::{item['observed_at']}"
                   f"::{item['outcome']}")
        nodes.append({"label": "TestExecution", "id": exec_id,
                      "properties": {"id": exec_id, **item,
                                     "lifecycle_state": "Quarantine"}})
        # To the CASE, never to the transition.
        edges.append({"from_label": "TestExecution", "from_id": exec_id,
                      "rel_type": "OF_CASE",
                      "to_label": "TestCase", "to_id": item["case_id"]})
        if cycle_id:
            edges.append({"from_label": "TestCycle", "from_id": cycle_id,
                          "rel_type": "CONTAINS",
                          "to_label": "TestExecution", "to_id": exec_id})

    return {
        "job_id": job_id,
        "nodes": nodes,
        "edges": edges,
        "summary": summarise(normalised),
        "lifecycle": "Quarantine — an observed result is still a claim (S-4)",
        "attaches_to": ("TestCase, never Transition — an execution is evidence "
                        "about an artefact somebody ran, and edging it to the "
                        "transition would make 'this behaviour passed' "
                        "expressible in one hop"),
    }
