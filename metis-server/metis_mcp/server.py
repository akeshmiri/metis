"""
The agent / MCP surface (application spec §9.5, N-8).

**Read-only, and structurally so.** N-8 says no decision may be taken through
this surface, because a decision requires the evidence presentation N-3
specifies and an agent session cannot provide it. That is enforced here by
composition rather than by discipline: every tool below calls a *query*
function, none imports `review.decisions`, `publishing.publish` or
`model_sources.landing`, and `test_mcp_server.py` asserts that no write-path
module is reachable from this one.

The distinction matters because the failure it prevents is quiet. A tool that
approves a model from a chat session would produce exactly the artefact the two
human gates exist to prevent, and it would look like helpfulness.

**Why this file was missing.** `plugins/metis-mcp/.mcp.json` has pointed at
`metis_mcp.server` since the plugin was written, and the module went away with
the v1 engine -- so anyone installing the plugin got a server that failed at
startup. Six skills called tools it used to expose. This restores the surface
against the current engine rather than deleting the plugin, because §9.5 is a
specified interface and the query functions it needs all exist.
"""
from __future__ import annotations

import json
import os
import sys

from mcp.server.fastmcp import FastMCP

from metis_mcp.mbt.graph_loader import load_from_graph
from metis_mcp.mbt.graph_session import GraphNotConfigured, session

mcp = FastMCP("metis")

# What a read-only surface says when it cannot reach the graph. Distinct from
# "nothing found", which is a different answer with a different consequence.
def _no_graph(e: Exception) -> dict:
    """The refusal payload for a graph that could not be used.

    Keeps the exception's OWN message when it has one. `GraphNotConfigured` is
    raised for a malformed config file, an unset `password_env` and an
    unreachable database, each with a specific repair — and every call site used
    to discard all three for the constant below, so a stray comma in
    `.metis/config.json` was reported as "set METIS_NEO4J_URI", which is both
    wrong and unactionable.
    """
    reason = str(e)
    return {"ok": False, "reason": reason} if reason else dict(_NOT_CONFIGURED)


_NOT_CONFIGURED = {
    "ok": False,
    "reason": ("no graph is configured — set METIS_NEO4J_URI / METIS_NEO4J_USER "
               "and provide METIS_NEO4J_PASSWORD in the environment (PLT-005: "
               "never as an argument)"),
}


# `ok` is the one field a refusal cannot afford to lose, and `ok: false` is
# exactly what pruning False removes. Every error response was going out without
# it -- a caller reading `payload["ok"]` got a KeyError, and the test that was
# meant to catch this asserted on the dict rather than on the serialised bytes.
#
# `may_author` and `may_decide` join it for the same reason one step further on:
# they are answers to "can I write here", and `false` is the answer that matters.
# Pruned, `describe_policy` reported `may_decide: null` on a surface that
# definitely could not decide -- a reader cannot tell "no" from "not mentioned",
# and this is the one tool whose entire job is to be unambiguous about that.
# `may_observe` and `may_run` join them for the identical reason one surface
# further out: they answer "can this deployment touch the system under test",
# and `false` is the answer that matters. This was found the way the first pair
# was -- by calling `describe_execution` on an `observe` deployment and getting
# a payload with no `may_run` key at all, which reads as "unspecified" for the
# one question the tool exists to settle.
_ALWAYS_KEPT = frozenset({"ok", "may_author", "may_decide",
                          "may_observe", "may_run",
                          # The question each new tool exists to settle, and
                          # `_prune` deletes False.
                          "conforms", "atomic", "valid",
                          # A ledger row that does NOT count as covered is the
                          # actionable half of a coverage report, and pruning
                          # deleted the field on exactly those rows: a covering
                          # row carried `counts_as_covered: true` and a
                          # non-covering one carried nothing at all. C-11's
                          # whole point is that this figure is read precisely.
                          "counts_as_covered",
                          # `false` here means NOBODY LOOKED at coverage depth,
                          # so the finding list is short for a reason that has
                          # nothing to do with the change being safe. Pruning it
                          # turned "not evaluated" into "nothing found".
                          "depth_consulted",
                          # `null` is the ANSWER on a model-derived risk: Métis
                          # observed a gap and did not forecast a failure.
                          # Pruning it makes an explicitly-absent probability
                          # look like a field the schema never had, which is the
                          # one reading the whole design exists to prevent.
                          "probability",
                          # `false` means the DESIGN ASPECT WAS NOT GATHERED --
                          # no journey named a scope, so "could anything test
                          # this" was answered from the ledger alone. Pruned, an
                          # ungathered aspect reads exactly like a gathered one.
                          "journey_consulted",
                          # An EMPTY list here is the good answer: this design
                          # section rests on every input it needed. Pruned, a
                          # complete section and a section the field was never
                          # computed for read identically -- and the whole
                          # document turns on telling "nothing missing" from
                          # "nobody looked".
                          "unstatable_because",
                          # `false` distinguishes an OPTIONAL missing input from
                          # a required one, and that distinction is the whole of
                          # `inputs.completeness`. Pruned, every gap looked
                          # equally blocking.
                          "required",
                          # "did I see everything" is the question the observe
                          # tier exists to answer honestly, so it may not be
                          # answered by the absence of a key.
                          "truncated"})


def _prune(value):
    """Drop what carries no information, recursively.

    Measured on the largest demo model (11 states, 46 transitions): `security`
    was an empty list on 46 transitions out of 46, and `source_state_unresolved`
    false on 43. Serialising those cost about a fifth of the response and told a
    reader nothing that its absence does not.

    Absent therefore means null, empty, or false -- except for the status field
    `ok`, which is always carried. Every tool below says so in its own
    description, because a convention a caller has to infer is a convention that
    will be inferred wrongly.
    """
    if isinstance(value, dict):
        return {k: _prune(v) for k, v in value.items()
                if k in _ALWAYS_KEPT
                or (v is not None and v != "" and v != [] and v is not False)}
    if isinstance(value, list):
        return [_prune(v) for v in value]
    return value


def _json(payload) -> str:
    """Compact, pruned JSON.

    `indent=2` was 27% of every response — about 2,900 tokens on one
    `get_model` call — spent on whitespace for a reader that does not need it.
    """
    return json.dumps(_prune(payload), separators=(",", ":"))


def _load(journey: str, surface: str):
    with session() as s:
        return load_from_graph(s, journey, surface)


def _no_such_model(s, journey: str, surface: str) -> dict:
    """The refusal for a `<journey>-<surface>` the graph does not hold.

    Necessary because an empty `Model` is what a typo produces, and every tool
    downstream of it reports cheerfully on nothing: `get_model` returned
    `ok: true` with zero states, and `coverage` returned a structurally complete
    ledger with `uncovered: 0` — which reads as "nothing is uncovered". The
    available pairs are listed because the mistake is nearly always a near-miss.
    """
    from metis_mcp.mbt.graph_loader import available_models

    pairs = available_models(s)
    return {
        "ok": False,
        "reason": (f"no model '{journey}-{surface}' — the graph holds no state "
                   f"or transition for journey {journey!r} on surface "
                   f"{surface!r}"),
        "available": [{"journey": j, "surface": sf} for j, sf in pairs],
        "note": ("`journey` is the journey, not the model id: pass 'mfa', not "
                 "'mfa-api'" if journey.endswith(f"-{surface}") else ""),
    }


@mcp.tool()
def list_workflows() -> str:
    """Every defined workflow, its ordered stages, and where it stops for a human."""
    from metis_mcp.workflow.stages import WORKFLOWS

    return _json({
        "workflows": [
            {
                "code": code,
                "summary": w.summary,
                "stages": [
                    {"ordinal": s.ordinal, "name": s.name, "gate": s.is_gate,
                     "blocking": s.blocking}
                    for s in w.ordered
                ],
                "preconditions": list(w.preconditions),
                "entry_patterns": list(w.entry_patterns),
            }
            for code, w in sorted(WORKFLOWS.items())
        ]
    })


@mcp.tool()
def route_request(request: str) -> str:
    """Which workflow a request maps to. Returns null when it does not match one.

    A null is an answer, not a failure: guessing which workflow was meant is how
    a run lands in the wrong place and produces a confident artefact about the
    wrong thing.
    """
    from metis_mcp.workflow.routing import route

    code, why = route(request)
    return _json({"workflow": code, "why": why})


@mcp.tool()
def get_model(journey: str, surface: str = "api", detail: bool = False) -> str:
    """One model's states and transitions, as they stand in the graph.

    Returns a summary — counts, state names, transition ids — unless `detail` is
    true, which adds each transition's trigger, guard, outcome and inputs.
    Ask for detail when you need to reason about specific behaviour; the summary
    answers "what is in this model" for a tenth of the size.

    Fields that are null, empty or false are omitted.
    """
    try:
        with session() as s:
            report = load_from_graph(s, journey, surface)
            if not report.found:
                return _json(_no_such_model(s, journey, surface))
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    model = report.model
    payload = {
        "ok": True,
        "model_id": model.id,
        "states": [
            {"id": s.id, "name": s.name, "is_initial": s.is_initial,
             "lifecycle_state": s.lifecycle_state}
            for s in model.states.values()
        ],
        # F-10: what was left out is named rather than quietly absent. Kept in
        # both shapes -- a summary that hides its own omissions is worse than no
        # summary.
        "skipped": [{"id": i, "reason": r} for i, r in report.skipped],
    }

    if not detail:
        # Deliberately NOT the transition ids. On a recovered model an id is a
        # fully-qualified method signature -- 46 of them were 7,397 of this
        # summary's 8,405 characters, which is the detail payload wearing a
        # summary's name. What orients a reader is how many transitions there
        # are and how their outcomes distribute; addressing a specific one
        # needs detail=true anyway.
        outcomes: dict[str, int] = {}
        for t in model.transitions.values():
            outcomes[t.outcome_status or "unclassified"] = (
                outcomes.get(t.outcome_status or "unclassified", 0) + 1)
        payload["counts"] = {"states": len(model.states),
                             "transitions": len(model.transitions)}
        payload["transitions_by_outcome"] = dict(sorted(outcomes.items()))
        payload["detail_available"] = (
            "call again with detail=true for each transition's id, trigger, "
            "guard, outcome and inputs")
        return _json(payload)

    payload["transitions"] = [
        {"id": t.id, "source": t.source, "trigger": t.trigger,
         "target": t.target, "guard": t.guard,
         "outcome_status": t.outcome_status,
         "guard_anchor": t.guard_anchor,
         "source_state_unresolved": t.source_state_unresolved,
         "inputs": list(t.inputs), "security": list(t.security),
         "lifecycle_state": t.lifecycle_state}
        for t in model.transitions.values()
    ]
    return _json(payload)


@mcp.tool()
def validate_model(journey: str, surface: str = "api") -> str:
    """Well-formedness findings, by severity (§2.6, M-17).

    The three severities are not synonyms. `unverifiable` means the property
    could not be *shown*, which is neither a pass nor a defect, and collapsing it
    into either is how an unparseable guard reads as fine.
    """
    from metis_mcp.mbt.validation import validate

    try:
        with session() as s:
            report = load_from_graph(s, journey, surface)
            if not report.found:
                return _json(_no_such_model(s, journey, surface))
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    result = validate(report.model)
    return _json({
        "ok": True,
        "model_id": result.model_id,
        "checked": result.checked,
        "blocking": [f.describe() for f in result.blocking],
        "unverifiable": [f.describe() for f in result.unverifiable],
        "advisory": [f.describe() for f in result.advisory],
        "generation_would_be_blocked": not result.is_valid(),
    })


# Two fields on every row used to be `covered` and `how`, and `LedgerRow` has
# never had either -- so this tool raised `AttributeError` for any model that
# produced a single row, and no test caught it because none called it. Kept here
# rather than in the docstring: the docstring is loaded into every request, and
# this is repo history a caller cannot act on.
# The commit-range form calls `code_analysis.engine.changed_files`, which has
# existed with no caller since it was written and whose own docstring says it
# produces the list this tool takes. `engine` imports only `mbt.graph_session`,
# so it is safe on the read surface.
#
# **It returns `[]` for two different things** -- "nothing changed" and "git
# could not tell me" -- and says so in its own docstring, leaving the caller to
# distinguish them. This is that caller, so the distinction is made here rather
# than passed on: an empty range with no resolvable git answer is reported as
# `range_unresolved`, never as "no impact".
@mcp.tool()
def impact(changed_files: list[str] | None = None, repo: str = "",
           since: str = "", until: str = "HEAD") -> str:
    """Which recovered behaviour a set of changed files touches.

    Pass what `git diff --name-only` prints, or give `repo` and `since` and let
    it resolve the range itself. Returns the transitions recovered from those
    files, the evidence each was reached through, and the criteria that validate
    them — so a reviewer can see what a change puts at risk before merging.

    **Read-only and safe pre-merge.** It queries the graph, and the repository
    only to list changed paths; it is current as of the last extraction, and the
    commits it matched against come back with the answer. A file that matched
    nothing is named rather than counted as "no impact" — different answers. So
    is a range git could not resolve, which is `range_unresolved` and not zero.

    Fields that are null, empty or false are omitted.
    """
    # Matching is on path suffix: an anchor holds the path the CPG recorded and
    # a diff path rarely shares its root. (Here rather than in the description,
    # which is loaded on every request and capped for that reason.)
    from metis_mcp.impact import impact as _impact

    files = list(changed_files or [])
    resolved_from = None
    if not files and repo and since:
        from code_analysis.engine import changed_files as _range
        files = _range(repo, since, until)
        resolved_from = f"{since}..{until}"
        if not files:
            # `_range` cannot distinguish "no diff" from "git failed", so this
            # does not claim either. Reporting `0 transitions` here would be a
            # confident answer built on no information.
            return _json({
                "ok": False,
                "range_unresolved": resolved_from,
                "reason": "git returned no paths for this range. That is either "
                          "an empty diff or a range this checkout cannot "
                          "resolve — a shallow clone, an unknown commit, or not "
                          "a repository. Pass `changed_files` to be certain.",
            })

    if not files:
        return _json({"ok": False,
                      "reason": "pass `changed_files`, or `repo` and `since`"})

    try:
        payload = _impact(files)
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    if resolved_from and isinstance(payload, dict):
        # Echo what was actually compared: the caller asked about a range and is
        # owed the file list the answer was computed from.
        payload["resolved_range"] = resolved_from
        payload["resolved_files"] = files
    return _json(payload)


@mcp.tool()
def coverage(journey: str, surface: str = "api",
             criterion: str = "all-transitions",
             detail: bool = False) -> str:
    """The coverage ledger for a model under a criterion (§6.8b).

    Records **coverage, not outcome**: answers "is this behaviour tested?" and
    never "is it working?" (C-11). No execution result is read, because none is
    ingested (§8.7). States the version and commit the figure refers to (P-16).

    `mechanism` is direct / indirect / initiated, and the distinction is
    load-bearing: `initiated` is reported and never counted (C-1).

    Returns totals and the uncovered transitions unless `detail` is true, which
    adds a row per transition. Fields that are null, empty or false are omitted.
    """
    from metis_mcp.mbt.coverage import COVERING_MECHANISMS, build_ledger
    from metis_mcp.mbt.graph_loader import (
        load_component, load_extracted_commit, load_validating_criteria,
    )
    from metis_mcp.mbt.path_generation import generate

    # One session for all three reads. Two would be two chances for the graph to
    # change underneath a single reported figure.
    try:
        with session() as s:
            report = load_from_graph(s, journey, surface)
            if not report.found:
                return _json(_no_such_model(s, journey, surface))
            model = report.model
            component = load_component(s, journey, surface)
            validating = load_validating_criteria(s, journey, surface)
            # P-16's other half. See the payload below for why the extraction
            # commit and a published version are reported as different facts.
            extracted_commit, extracted_at = ("", "")
            if component is None:
                extracted_commit, extracted_at = load_extracted_commit(s, journey)
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    result = generate(model, criterion, 10)
    ledger = build_ledger(model, result, component=component,
                          validating_criteria=validating)
    summary = ledger.summary()
    payload = {
        "ok": True,
        "model_id": model.id,
        "criterion": criterion,
        # P-16 -- null when no Component has been persisted for this model, which
        # is a reported state and not a silent omission. `_prune` would drop a
        # null, so the absence is spelled out instead.
        "component": summary["component"] or "not recorded (P-16)",
        # **Version and commit are different facts and are no longer reported
        # alike.** A `Component` is written by `persist` and means "what was
        # generated and published", so before a generation there is genuinely no
        # version — that stays "not recorded". The COMMIT is different: landing
        # knows it, and reporting it as unrecorded was an omission rather than
        # an absence. It is labelled by where it came from, because a commit the
        # model was extracted at is a weaker claim than one a published version
        # was cut from, and merging them would overstate the second.
        "version": summary["version"] or "not recorded (P-16)",
        "commit": (summary["commit"] or extracted_commit
                   or "not recorded (P-16)"),
        **({"commit_source": "the episode this model was last landed by — no "
                             "version has been published, so this is the "
                             "extraction commit rather than a released one",
            "extracted_at": extracted_at} if not summary["commit"]
           and extracted_commit else {}),
        "paths": len(result.paths),
        "paths_with_setup": sum(1 for p in result.paths if p.setup_length),
        "covered": summary["covered"],
        "uncovered": summary["uncovered"],
        "criteria_covered": ledger.criteria_covered(),
        "criteria_uncovered": ledger.criteria_uncovered(),
        # Never summarised away: an uncovered transition is the actionable half
        # of a coverage report, and a total alone is the number C-11 warns about.
        "uncovered_detail": [{"transition_id": t, "reason": why}
                             for t, why in ledger.uncovered],
        "means": "what is TESTED, not what is WORKING (C-11)",
    }

    if detail:
        payload["rows"] = [
            {"transition_id": r.transition_id,
             "mechanism": r.mechanism,
             "counts_as_covered": r.mechanism in COVERING_MECHANISMS,
             "test_case_id": r.test_case_id,
             "criterion_ids": list(r.criterion_ids),
             "note": r.note}
            for r in ledger.rows
        ]
    else:
        payload["rows"] = len(ledger.rows)
        payload["detail_available"] = "call again with detail=true for a row per transition"
    return _json(payload)


# `coverage_report` is the tool the generated agents used to name as absent
# ("report generation -- no quality, release or test-design report exists"). It
# joins what previously took four calls and a human to assemble, and adds the
# part that existed nowhere: an enumeration of what could NOT be measured.
#
# **That enumeration is the reason it is a separate tool from `coverage`.**
# `server._prune` drops null, empty and false, so an unmeasured figure and a zero
# figure leave the same trace -- none. `coverage` already works around this once
# by hand (`"not recorded (P-16)"`); this generalises it, because a report is
# exactly where "I did not measure this" and "this is zero" must not look alike.
#
# What it deliberately does NOT do is reach a verdict. A Go/No-Go computed from a
# coverage figure would be reading coverage as a statement about quality, which
# is what C-11 forbids and what §6.8a names as the trigger for reinstating the
# execution labels. It reports; a person decides.
@mcp.tool()
# **Why `as_of` moves only the criteria, kept here rather than in the docstring
# — which is loaded on every request and is guarded for length.**
#
# Four labels carry a validity window: `AcceptanceCriterion`, `Intent`,
# `Requirement`, `Specification`. `State` and `Transition` do not, and that is
# deliberate: an element that changes is the same node MODIFIED (I-17), not a
# new claim, so there is no history to read a model out of.
#
# An as-of coverage figure is therefore the model as it is NOW against the
# criteria as they stood THEN. That is the only honest combination available,
# and the reply carries `as_of_means` saying it — a figure labelled "as of
# 2026-01-01" with no such note would imply a snapshot nobody kept.
#
# This is also the cheaper alternative `PROPOSAL-release-baseline.md` names
# before adding a `Release` label. If asking for a readiness figure at an
# instant turns out to be enough, that proposal should be REFUSED permanently
# rather than left deferred.
def coverage_report(journey: str, surface: str = "api",
                    criterion: str = "all-transitions",
                    detail: bool = False, as_of: str = "") -> str:
    """One report joining coverage, validation, reconciliation and version.

    **States what it could not measure, and why.** `unmeasured` is the field
    that makes the rest safe to read: an absent figure and a zero figure are
    different answers, and everything else here would report them alike.

    `confidence_capped_by` names the weakest input the report rests on — a
    coverage number computed over a model with blocking validation findings is
    not worth more than those findings.

    **Coverage, not outcome** (C-11). Execution results are ingested (§8.7,
    revised) and none is read here — they never write the coverage ledger
    (C-10), so *is this tested* and *did it pass* stay two figures. No verdict.

    `as_of` reads the CRITERIA as they stood at an ISO instant, against the
    model as it is now; the reply says so. `detail` adds every finding and gap
    in full. Fields that are null, empty or false are omitted.
    """
    from metis_mcp.mbt.coverage import COVERING_MECHANISMS, build_ledger
    from metis_mcp.mbt.graph_loader import (
        load_component, load_confirmed_matches, load_extracted_commit,
        load_validating_criteria,
    )
    from metis_mcp.mbt.path_generation import generate
    from metis_mcp.mbt.validation import validate
    from metis_mcp.reconciliation.gaps import reconcile

    # One session for every read: two would be two chances for the graph to move
    # underneath a single reported figure.
    try:
        with session() as s:
            report = load_from_graph(s, journey, surface)
            if not report.found:
                return _json(_no_such_model(s, journey, surface))
            model = report.model
            component = load_component(s, journey, surface)
            validating = load_validating_criteria(s, journey, surface, at=as_of)
            confirmed = load_confirmed_matches(s, journey, at=as_of)
            # P-16's other half, when no version has been published. See the
            # payload below for why the two are reported as different facts.
            extracted_commit, extracted_at = ("", "")
            if component is None:
                extracted_commit, extracted_at = load_extracted_commit(s, journey)
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    result = generate(model, criterion, 10)
    ledger = build_ledger(model, result, component=component,
                          validating_criteria=validating)
    summary = ledger.summary()
    findings = validate(model)

    # **Every entry says whether the absence is structural or operational**, and
    # collapsing the two is a specific harm rather than untidiness: an outage
    # reported as "unmeasurable" reads as a permanent gap in the data model and
    # hides a fixable environment problem, while a genuine gap reported as an
    # outage sends somebody to restart a service that was never involved.
    STRUCTURAL = "structural"       # the data genuinely does not exist
    OPERATIONAL = "operational"     # something that should have answered did not
    unmeasured: list[dict] = []

    # 1. Transitions the loader dropped. A shrunken model reports a smaller
    #    denominator, which raises the percentage rather than lowering it.
    for tid, why in report.skipped:
        unmeasured.append({"figure": "coverage", "kind": STRUCTURAL,
                           "cause": "transition_skipped",
                           "element": tid, "reason": why})

    # 2. P-16: a figure with no version is a figure about nothing in particular.
    if not summary["version"]:
        unmeasured.append({"figure": "version", "kind": STRUCTURAL,
                           "cause": "not_recorded",
                           "reason": "no Component persisted for this model "
                                     "(P-16); run `metis persist`"})

    # 3. Neither a pass nor a defect, and collapsing it into either is how an
    #    unparseable guard reads as fine (M-17).
    for finding in findings.unverifiable:
        unmeasured.append({"figure": "validation", "kind": STRUCTURAL,
                           "cause": "unverifiable",
                           "reason": finding.describe()})

    # 4. S-3: with no criteria there is nothing to reconcile against, and the
    #    run yields coverage and never correctness.
    reconciliation = reconcile(model, [], confirmed) if confirmed else None
    if reconciliation is None:
        unmeasured.append({"figure": "reconciliation", "kind": STRUCTURAL,
                           "cause": "no_confirmed_matches",
                           "reason": "no confirmed VALIDATES edge for this "
                                     "journey, so intent cannot be compared "
                                     "against behaviour (S-3, F-7)"})

    # 5. C-1: `initiated` is reported and never counted.
    initiated = [r.transition_id for r in ledger.rows
                 if r.mechanism not in COVERING_MECHANISMS]
    if initiated:
        unmeasured.append({"figure": "covered", "kind": STRUCTURAL,
                           "cause": "not_a_covering_mechanism",
                           "reason": f"{len(initiated)} transition(s) are "
                                     f"initiated, which is reported and never "
                                     f"counted (C-1)"})

    # 6. Publication drift is deliberately NOT read here, and the reason is
    #    structural rather than an oversight: `PublicationLedger` lives in
    #    `metis_mcp.publishing`, which is in `test_mcp_server.WRITE_PATHS`, so
    #    importing it would put a write path on the read surface and turn N-8's
    #    "no write path is reachable" proof into a lie. The limitation it would
    #    have reported -- MANUALLY_EDITED and OBSOLETE reading zero because
    #    nothing was ever recorded as sent -- is stated by `metis drift` and by
    #    the metis-coverage-report skill instead.
    #
    #    `OPERATIONAL` therefore has no producer on this surface today. It is
    #    defined anyway, because the vocabulary is the contract: a caller must be
    #    able to tell the two kinds apart without knowing which causes exist.

    # The weakest link, named. A number is worth what its worst input is worth.
    if findings.blocking:
        capped = "blocking validation findings — generation is blocked (M-17)"
    elif not confirmed:
        capped = "no intent-backed criteria — coverage, never correctness (S-3)"
    elif not summary["version"]:
        capped = "no recorded version — the figure names no commit (P-16)"
    elif unmeasured:
        capped = "some figures could not be measured; see `unmeasured`"
    else:
        capped = "none — every input was measurable"

    payload = {
        "ok": True,
        "model_id": model.id,
        "criterion": criterion,
        "component": summary["component"] or "not recorded (P-16)",
        # Version and commit are different facts. A `Component` means "what was
        # generated and published", so before a generation there is genuinely no
        # version. The commit landing knows is a weaker claim than one a
        # published version was cut from, and is labelled by where it came from
        # rather than merged into the same field silently.
        "version": summary["version"] or "not recorded (P-16)",
        "commit": (summary["commit"] or extracted_commit
                   or "not recorded (P-16)"),
        **({"commit_source": "the episode this model was last landed by — no "
                             "version has been published, so this is the "
                             "extraction commit rather than a released one",
            "extracted_at": extracted_at} if not summary["commit"]
           and extracted_commit else {}),
        # **An as-of read must say so, or nothing distinguishes it from now.**
        # And it must say what moved: only the criteria did, because only the
        # four VALIDITY_LABELS carry a window. Reporting "as of 2026-01-01"
        # without that would imply a model snapshot Métis does not keep.
        **({"as_of": as_of,
            "as_of_means": ("the criteria as they stood at this instant, "
                            "against the model as it is NOW. State and "
                            "Transition carry no validity window — an element "
                            "that changes is the same node modified (I-17) — so "
                            "Métis keeps no model history and does not pretend "
                            "to")} if as_of else {}),
        "coverage": {
            "covered": summary["covered"],
            "uncovered": summary["uncovered"],
            "criteria_covered": ledger.criteria_covered(),
            "criteria_uncovered": ledger.criteria_uncovered(),
            # Never summarised away: the uncovered half is the actionable one.
            "uncovered_detail": [{"transition_id": tid, "reason": why}
                                 for tid, why in ledger.uncovered],
        },
        "validation": {
            "checked": findings.checked,
            "blocking": len(findings.blocking),
            "unverifiable": len(findings.unverifiable),
            "advisory": len(findings.advisory),
            # A string, not a bool: `_prune` deletes false, and "generation is
            # not blocked" is the half a reader would wrongly infer from silence.
            "generation": "blocked" if not findings.is_valid() else "not blocked",
        },
        # Always present, even empty -- the whole point is that an unmeasured
        # figure cannot look like a measured one.
        "unmeasured": unmeasured or "nothing — every figure below was measured",
        "absence_kinds": ("structural = the data does not exist; "
                          "operational = something that should have answered "
                          "did not, and is probably fixable"),
        "confidence_capped_by": capped,
        "means": "coverage, not outcome (C-11). No verdict is computed.",
    }

    if reconciliation is not None:
        payload["reconciliation"] = {
            **reconciliation.summary,
            "supports_a_correctness_claim":
                "yes" if reconciliation.supports_a_correctness_claim else
                "no — every match is code_derived (S-19, §4.1)",
        }

    if detail:
        payload["validation"]["blocking_detail"] = [
            f.describe() for f in findings.blocking]
        payload["validation"]["unverifiable_detail"] = [
            f.describe() for f in findings.unverifiable]
        if reconciliation is not None:
            payload["reconciliation"]["unspecified_behaviour"] = [
                {"element": g.element_id, "detail": g.detail}
                for g in reconciliation.unspecified_behaviour]
            payload["reconciliation"]["unimplemented"] = [
                {"element": g.element_id, "detail": g.detail}
                for g in reconciliation.unimplemented]
    else:
        payload["detail_available"] = (
            "call again with detail=true for every finding and gap in full")
    return _json(payload)


# `test_cases` makes the G2 batch reviewable through this surface while the
# decision itself stays on the CLI -- "show them ALL, ask ONE yes/no", split
# across the N-8 boundary at the right place.
#
# **`model_is_approved` is not decoration.** `path_generation.generate` does not
# enforce D-10; the workflow's `model_is_approved` precondition does. So this
# tool will happily render cases from a model nobody has reviewed, and a caller
# who did not check would treat them as publishable. It is reported as a string
# for the usual reason: `_prune` deletes false, and "no" is the answer that
# matters.
@mcp.tool()
def test_cases(journey: str, surface: str = "api",
               criterion: str = "all-transitions", detail: bool = False) -> str:
    """The test cases a model would generate, before anything is published.

    **Says whether the model is approved, every time.** Generation is gated on
    approval (D-10), and this tool is not the gate — cases rendered from an
    unreviewed model are a preview, never a publishable batch.

    `uncoverable` names targets the criterion could not reach and `failures`
    names paths that would not render, each with a reason. Neither is
    summarised away: they are the half a reviewer acts on.

    **Specification, not code** (R8). A case says what must be verified; the
    step definitions that bind it to a running system belong to whatever
    executes the test, and Métis generates none.

    `detail` returns every case in full and the `.feature` text. Fields that are
    null, empty or false are omitted.
    """
    from metis_mcp.mbt.path_generation import generate
    from metis_mcp.rendering import feature_for, format_case, render

    try:
        with session() as s:
            report = load_from_graph(s, journey, surface)
            if not report.found:
                return _json(_no_such_model(s, journey, surface))
            model = report.model
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    outstanding = model.unapproved_elements()
    result = generate(model, criterion, 10)
    rendered = render(model, result.paths)

    payload = {
        "ok": True,
        "model_id": model.id,
        "criterion": criterion,
        # The whole reason a caller can trust or distrust what follows.
        "model_is_approved": "no" if outstanding else "yes",
        "unapproved_elements": len(outstanding),
        "cases": len(rendered.cases),
        "paths": len(result.paths),
        # Never summarised: a target the criterion could not reach is a coverage
        # gap, and a path that would not render is a defect in the model.
        #
        # `uncoverable` holds `Uncoverable` dataclasses and `excluded` holds
        # 2-tuples -- they are not the same shape, and unpacking the first as if
        # it were the second raises only once a model actually has a transition.
        "uncoverable": [{"target": u.target_key,
                         "transition_id": u.validated_transition_id,
                         "reason": u.reason, "detail": u.detail}
                        for u in result.uncoverable],
        "excluded": [{"transition_id": tid, "reason": why}
                     for tid, why in result.excluded],
        "failures": [{"target": tgt, "reason": why}
                     for tgt, why in rendered.failures],
        "means": "specification, not code (R8)",
    }
    if outstanding:
        payload["not_publishable"] = (
            f"{len(outstanding)} element(s) await review; generation reads only "
            f"Approved (D-10). This is a preview of what the model would yield.")

    if detail:
        payload["cases_detail"] = [format_case(c) for c in rendered.cases]
        if rendered.cases:
            payload["feature"] = feature_for(model, rendered.cases,
                                             criterion=criterion)
    else:
        payload["detail_available"] = (
            "call again with detail=true for every case and the .feature text")
    return _json(payload)


# ---------------------------------------------------------------------------
# The knowledge surface (§4.6a, §18; F-12)
#
# Documents live in the graph, not in files, so serving one is a query rather
# than a re-render. That is also why these belong here: a skill that carried
# document text would be a second copy of facts the graph already holds, paid
# for on every invocation.
#
# Every function below reads. None imports `specgen.documents`, which pulls in
# `model_sources.landing` -- `test_mcp_server.py` asserts that, and it is the
# reason `get_entity` reads a stored document instead of rendering one.
# ---------------------------------------------------------------------------

# `trace` walks D-4, the only traceability route into behaviour. It reads
# `graph_loader.TRACE_CASE_CYPHER`, which lived in `graph_writer.py` -- a write
# path -- until this tool needed it; importing it there would have put the writer
# on the read surface and broken N-8's structural proof.
#
# **It reports breaks rather than hiding them.** The graph today holds zero
# `AcceptanceCriterion-[:VALIDATES]->Transition` edges, so almost every walk
# stops at the first hop. Returning `[]` for that would say "this case traces to
# nothing" in the same breath as "no such case", and the generated agents already
# name absent traceability as a thing this build does not have. An enumerated
# break is how that gap becomes visible instead of merely true.
@mcp.tool()
def trace(case_id: str, detail: bool = False) -> str:
    """Where a test case's justification chain reaches, and where it stops.

    Walks D-4: `TestCase -> Scenario -> Transition -> AcceptanceCriterion ->
    Requirement -> JiraItem`. There is deliberately no edge from a test case
    straight to a requirement, so the criterion hop is what makes the chain
    auditable rather than asserted.

    **A break is the answer, not an empty result.** `breaks` names the hop that
    has no edge and what its absence means; a chain that reaches a requirement
    reports `complete`. Zero `VALIDATES` edges in the graph is a real state and
    is reported as one.

    `detail` adds every row of the walk. Fields that are null, empty or false
    are omitted.
    """
    from metis_mcp.mbt.graph_loader import load_trace

    try:
        with session() as s:
            rows = load_trace(s, case_id)
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    if not rows:
        return _json({"ok": False,
                      "reason": f"no test case {case_id!r}, or it covers "
                                f"nothing validated"})

    # Each hop is reported by whether ANY row reached it. One transition tracing
    # home does not make the case traced, so the break list is per-hop and the
    # counts say how many of the rows got that far.
    hops = [
        ("transition", "transition", "the case covers no transition"),
        ("acceptance_criterion", "acceptance_criterion",
         "no AcceptanceCriterion-[:VALIDATES]->Transition edge (D-4)"),
        ("requirement", "requirement",
         "the criterion is not attached to a Requirement (HAS_AC)"),
        ("jira_key", "tracker_item",
         "the requirement is not represented by a tracker item"),
    ]
    reached, breaks = {}, []
    for field, name, meaning in hops:
        got = [r for r in rows if r.get(field)]
        reached[name] = len(got)
        if not got:
            breaks.append({"at": name, "meaning": meaning})

    payload = {
        "ok": True,
        "case_id": case_id,
        "rows": len(rows),
        "reached": reached,
        "breaks": breaks,
        # A string, not a bool. `_prune` drops false, so `complete: False` --
        # the answer that matters most here -- would be deleted on its way out
        # and a caller reading the key would get nothing rather than "no".
        "chain": "complete" if not breaks else "broken",
        "route": "TestCase -> Scenario -> Transition -> AcceptanceCriterion "
                 "-> Requirement -> JiraItem (D-4)",
    }
    if detail:
        payload["walk"] = rows
    else:
        payload["detail_available"] = True
    return _json(payload)


# The handoff to a generator that lives outside Métis. It emits specification --
# an ordered flow, its preconditions, the accepted input space -- and names no
# library, annotation or file layout. R8 is unchanged by it: what must be
# verified is a question about the system, and how to express it is a question
# about a framework, and a module that answered both would be wrong about one
# every time either moved.
@mcp.tool()
def flow_scaffold(journey: str, surface: str = "api",
                  criterion: str = "all-transitions",
                  target: str = "generic", detail: bool = False) -> str:
    """The business flows of a model, ready for an external code generator.

    Emits operations in order, what must hold before each, the **accepted input
    space** for every payload (never a value — X-6e), what a caller must
    present, and which cases share setup so a generator can hoist it.

    **Framework-neutral by construction.** `target` selects which academy lesson
    the reader is pointed at for translation rules; it does not change what is
    emitted. Métis states what must be true; the framework is somebody else's
    decision and lives outside this repository (R8).

    `detail` returns every flow in full rather than the shared-setup summary.
    """
    from metis_mcp.authoring import auth_facts, payload_shape
    from metis_mcp.mbt.path_generation import generate
    from metis_mcp.rendering import render
    from metis_mcp.scaffold import flow_manifests

    try:
        with session() as s:
            report = load_from_graph(s, journey, surface)
            if not report.found:
                return _json(_no_such_model(s, journey, surface))
            model = report.model
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    result = generate(model, criterion, 10)
    rendered = render(model, result.paths)

    # Composed from the authoring surface rather than re-derived: those already
    # state the accepted space and already carry their own caveats about what
    # extraction cannot see.
    try:
        auth = auth_facts(journey)
    except Exception:                                        # noqa: BLE001
        auth = {"unavailable": "auth facts could not be read for this journey"}

    payloads: dict = {}
    for case in rendered.cases:
        for requirement in case.data_requirements:
            name = requirement.condition.split()[0] if requirement.condition else ""
            if name and name not in payloads and name[:1].isupper():
                try:
                    payloads[name] = payload_shape(name)
                except Exception:                            # noqa: BLE001
                    continue

    document = flow_manifests(model, rendered.cases, target=target,
                              payloads=payloads, auth=auth)
    if not detail:
        document["flows"] = len(document["flows"])
        document["detail_available"] = (
            "call again with detail=true for every flow in full")
    return _json(document)


@mcp.tool()
def model_sources() -> str:
    """What can produce a model here, and why the rest cannot (S-17).

    A capability map, and the half that matters is the second: a source listed
    as unavailable says what is missing — an engine, a pack, a configuration —
    rather than being absent from the list and read as "does not exist".
    """
    from metis_mcp.model_sources import availability

    try:
        rows = [{"source": name, "available": ok, "why": why or ""}
                for name, ok, why in availability()]
    except Exception as e:                                       # noqa: BLE001
        return _json({"ok": False, "refused": f"{type(e).__name__}: {e}"})

    return _json({
        "ok": True,
        "sources": rows,
        # Never summarised away: "three available" hides which three, and the
        # unavailable ones are what a caller has to act on.
        "unavailable": [r["source"] for r in rows if not r["available"]],
    })


# The EARS check was already deterministic, already tested, and already the
# function deciding whether intake writes a `Requirement` or a `Finding` — and it
# was reachable from nowhere a caller could stand. So `knowledge-capture`, whose
# whole job is turning prose into criteria, judged conformance by eye and found
# out at landing time. §9's code-vs-LLM table lists "EARS check" as deterministic
# code; this exposes the code rather than asking a model to imitate it.
@mcp.tool()
def check_ears(text: str) -> str:
    """Whether a sentence conforms to EARS, and what it would land as (S-13).

    **Structural conformance only.** A sentence can pass this and still be a bad
    requirement: §2.6 draws the line explicitly, and ISO/IEC/IEEE 29148's
    substantive characteristics — singular, verifiable, unambiguous — are a
    different question. `ac_quality` asks that one.

    `would_land_as` is the fact a caller usually wants: non-conformant text
    becomes a `Finding` pointing at knowledge-capture, never a `Requirement`,
    because `ears_pattern` has no empty form and guessing one is what
    `ac_mining` refuses to do. Nothing here rewrites the sentence to make it
    pass — that is the line S-13 draws.

    `conforms` is always present. Everything else is absent when empty.
    """
    from metis_mcp.ears_checker import check_ears_conformance

    result = check_ears_conformance(text)
    return _json({
        "ok": True,
        "conforms": result.conformant,
        "pattern": result.pattern or "",
        "why": result.reason,
        # Named for the consequence, not the check: "not conformant" leaves a
        # caller to work out what that costs them, and the cost is the whole
        # point of asking before landing rather than after.
        "would_land_as": "Requirement" if result.conformant else "Finding",
        "parts": result.groups,
        "not_checked": ("substantive quality — singular, verifiable, "
                        "unambiguous (ISO/IEC/IEEE 29148). See `ac_quality`."),
    })


@mcp.tool()
def ac_quality(text: str) -> str:
    """Whether one acceptance criterion is precise enough to write a test from.

    **Advisory, and it blocks nothing.** A criterion that fails every rule still
    lands at `Quarantine` (S-4) and a human settles it. Nothing here rewrites a
    criterion to make it pass, which is the line `ac_mining` refuses to cross
    (S-13).

    **Not the EARS check.** `check_ears` asks whether a sentence has one of the
    five EARS shapes; §2.6 says structural conformance is not substantive
    quality. A sentence can pass either one and fail the other.

    Each finding names the offending word and says what to write instead, since
    "is ambiguous" is the kind of report nobody can act on. `atomic` is read from
    whether the multi-assertion rule fired, so it cannot disagree with the
    findings beside it.

    `ok` and `atomic` are always present. Everything else is absent when empty.
    """
    from metis_mcp import ac_quality as checks

    findings = checks.assess(text)
    return _json({
        "ok": True,
        "atomic": checks.is_atomic(findings),
        "findings": [{"rule": f.rule, "severity": f.severity,
                      "detail": f.detail, "suggestion": f.suggestion}
                     for f in findings],
        "errors": sum(1 for f in findings if f.severity == checks.ERROR),
        "warnings": sum(1 for f in findings if f.severity == checks.WARNING),
        "advisory": ("findings do not block landing — everything lands at "
                     "Quarantine and a human decides (S-4)"),
    })


@mcp.tool()
def validate_intake(path: str) -> str:
    """Whether a UIF document matches its declared schema, before landing it.

    The intake skill has always told a reader that a UIF "is validated against
    `unified-intake-format.schema.json`". Nothing in the engine opened that file
    — the only reader in the tree was a test — so the shape was asserted by a
    skill and checked by nobody.

    **This is the mechanical half only.** `land_intake` still asks the questions
    a schema cannot: whether the text is EARS-conformant, whether an anchor
    exists for the source system, and what will therefore land as a `Finding`
    rather than a `Requirement` (S-13). A document can be schema-valid and still
    land almost entirely as findings, which is correct behaviour.

    Refuses rather than reporting a clean document when the schema cannot be
    read: "no errors" and "nothing looked" are different claims.
    """
    import json as _stdlib_json
    from pathlib import Path as _Path

    from metis_mcp import intakes

    available, why = intakes.uif_schema_available()
    if not available:
        return _json({"ok": False, "refused": why})

    target = _Path(path).expanduser()
    if not target.exists():
        return _json({"ok": False, "refused": f"no such document: {target}"})
    try:
        document = _stdlib_json.loads(target.read_text())
    except ValueError as e:
        return _json({"ok": False,
                      "refused": f"not JSON: {type(e).__name__}: {e}"})

    errors = intakes.validate_uif(document)
    return _json({
        "ok": True,
        "valid": not errors,
        "errors": errors,
        "source_system": (document.get("scope") or {}).get("source_system", ""),
        "not_checked": ("EARS conformance and anchor availability — "
                        "`check_ears` and `land_intake` answer those"),
    })


# Atlas's test-designer stages 04 and 05, which the port had no equivalent for.
# Coverage answers "is this tested?"; these answer "can it be automated at all?"
# and "is it worth driving under load?" -- and a design that skips them either
# automates something it cannot assert or load-tests something nobody sized.
@mcp.tool()
def test_design(journey: str, surface: str = "api", detail: bool = False) -> str:
    """Which behaviour can be automated, and which is worth driving under load.

    **`automate` is never awarded on a name.** It requires recovered evidence
    pointing at a source line (X-6); an unverifiable guard `defer`s because
    there is no oracle to assert against, and an unresolved precondition is
    `manual-only` because it cannot be established from nothing (P-8).

    **Performance candidacy refuses where the model has no volume facts.** It
    reports `no-basis` rather than `functional-only`, because the second reads
    as "measured, and none qualify" — and inventing an SLA threshold is the one
    thing this classification must never do.

    Neither is a coverage figure, and neither says anything is slow: no
    execution result is ingested (§8.7, C-11).
    """
    from metis_mcp.viability import design_report

    try:
        with session() as s:
            report = load_from_graph(s, journey, surface)
            if not report.found:
                return _json(_no_such_model(s, journey, surface))
            model = report.model
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    result = design_report(model)

    # **What the risk band WARRANTS, beside what the model can achieve.**
    # `classify_depth` answers whether a transition CAN be tested deeply;
    # PRISMA's product risk matrix answers whether it SHOULD be. Neither finds
    # the interesting case alone — behaviour that warrants deep testing and
    # cannot receive it, which is what an unverifiable guard or an unreachable
    # partition leaves behind for a person to cover another way.
    from metis_mcp.risk import prioritisation, product

    unverifiable = product.unverifiable_ids(model)
    bands = {tid: product.technical_profile(model, tid, unverifiable)["band"]
             for tid in model.transition_ids()}
    achievable = {row["transition_id"]: row["verdict"]
                  for row in result["depth"]["rows"]}
    result["warranted_depth"] = {
        "by_band": {tid: prioritisation.warranted_depth(band)["approach"]
                    for tid, band in sorted(bands.items())},
        "approaches": dict(prioritisation.DEPTH_FOR_BAND),
        "gaps": prioritisation.depth_gaps(bands, achievable),
        "means": prioritisation.DEPTH_MEANS,
    }

    if not detail:
        # The counts and the basis, not a row per transition -- but the basis is
        # never summarised away: it is the part that says whether the figures
        # mean anything.
        result["viability"] = len(result["viability"])
        result["performance"] = {
            "basis": result["performance"]["basis"],
            "means": result["performance"]["means"],
            "rows": len(result["performance"]["rows"]),
        }
        result["depth"] = {
            "counts": result["depth"]["counts"],
            "means": result["depth"]["means"],
        }
        result["warranted_depth"] = {
            "approaches": result["warranted_depth"]["approaches"],
            "gaps": result["warranted_depth"]["gaps"],
            "means": result["warranted_depth"]["means"],
        }
        result["detail_available"] = (
            "call again with detail=true for a row and a reason per transition")
    return _json(result)


# The design surface. `test_design` above answers two classification questions;
# these three answer the prior one -- what does a design of this behaviour
# consist of, what does it rest on, and what does nobody know. The shape is
# served rather than restated, so a skill never has to list a column.
@mcp.tool()
def design_sections() -> str:
    """The test design's shape: its groups, its sections, and every column.

    **The template is data, and this is how a client gets it.** A design
    "template" written as prose in a skill is a shape a model imitates, and two
    runs imitate it differently. Serving it means the headings, the column
    order and the closed vocabularies are the same every time, and that a skill
    naming them in prose would be a second copy of a generated fact.

    Every closed vocabulary here is borrowed from the module that owns it --
    the six test levels, the three existing-coverage grades, the viability and
    performance verdicts, the four risk bands. None is restated.
    """
    from metis_mcp.design import sections

    return _json({"ok": True, **sections.describe()})


@mcp.tool()
def design_standards() -> str:
    """Which named work product each part of a test design answers.

    ISO/IEC/IEEE 29119-3's six design-time products and IEEE 829's eight
    documents, mapped onto the design's own sections — with `full`, `partial` or
    `out-of-scope` and, wherever it is not `full`, what is missing.

    **Three products are `out-of-scope` and that is a real answer.** A Test Log,
    a Test Incident Report and a Test Summary Report are execution and reporting
    artefacts; claiming them would claim C-10's ledger and C-11's correctness
    figure in one move. Each names where it actually lives.

    **This does not claim the design satisfies a standard.** It says which
    section answers which product. Whether that meets an obligation is a
    judgement about the obligation, not a property Métis computes.
    """
    from metis_mcp.design import standards

    return _json({"ok": True, **standards.describe()})


@mcp.tool()
def design_inputs(section: str = "") -> str:
    """What a test design needs, split into what Métis gathers and what it asks.

    Pass a section key to narrow it; omit it for the whole ledger. Cross-cutting
    inputs -- the model, the risk band, the exit criteria -- belong to every
    section and appear in each.

    **Architecture and the design specification are `asked`, deliberately.**
    Métis could describe an architecture by summarising what it recovered, and
    that description would be the implementation restated as its own intent
    (S-19). So both are questions, and a design without them says which sections
    it therefore could not state.

    Every input says what its absence MEANS, because that string is printed
    where the value should have been -- and a design missing required inputs is
    unfinished, never lean.
    """
    from metis_mcp.design.inputs import UnknownSection, plan

    try:
        return _json({"ok": True, **plan(section)})
    except UnknownSection as e:
        return _json({"ok": False, "reason": str(e)})


# **Ordered the way the generated batch will be.** Rows follow
# `risk.prioritisation.order` -- detectability, then defect-proneness, then id --
# which is exactly what the `prioritise` stage applies to generated paths. A
# design and a suite that disagreed about what matters first would be two plans,
# and `test_design_sections.py` asserts the two orderings stay the same.
#
# **A section built without some of its inputs is marked partial**, rather than
# left looking complete. That is the dangerous case: a table with content in it,
# resting on inputs nobody supplied. An empty section announces itself.
@mcp.tool()
def design_report(journey: str, surface: str = "api", section: str = "",
                  requirement_id: str = "", as_markdown: bool = False) -> str:
    """The test design for a scope: what to test, how, at which level, and what nobody knows.

    Gathers the model, the risk profile, viability and existing coverage, then
    reports what it could not gather as open questions with the words to ask.

    **`status: incomplete` until those are answered.** A short design here means
    nobody has said what the architecture is or which environments exist, not
    that there is little to test.

    `requirement_id` is what lets the basis be gathered; without one the design
    describes what the code does with nothing stating what it should do.
    `as_markdown` returns the document `metis design` would write.
    """
    from metis_mcp.design import builders, document
    from metis_mcp.design import inputs as ledger
    from metis_mcp.design.sections import SECTIONS
    from metis_mcp.risk import prioritisation, product

    if section and section not in SECTIONS:
        return _json({"ok": False,
                      "reason": f"no section named {section!r}. Known: "
                                f"{', '.join(sorted(SECTIONS))}"})

    try:
        loaded, refusal = _product_risk_inputs(journey, surface)
    except GraphNotConfigured as e:
        return _json(_no_graph(e))
    if refusal:
        return _json(refusal)

    model = loaded["model"]
    technical = loaded["technical"]
    bands = {tid: profile["band"] for tid, profile in technical.items()}
    ranks = {row["transition_id"]: row["rank"]
             for row in prioritisation.order(loaded["detection"]["scores"],
                                             technical)}

    # Only what was actually read is recorded. A key absent here renders as
    # "not gathered, therefore not stated" rather than as a passing check.
    gathered: dict = {"model": model.id, "risk_band": bands,
                      "risk_priority": ranks}
    gathered["guards"] = [t.guard for t in model.transitions.values() if t.guard]

    # **Gathered only where a chain can actually be built.** A model whose
    # transitions carry no recovered `Check` has no short-circuit chain, and
    # reporting the input as present would make the `dimensions` section read as
    # complete-and-empty rather than as unavailable — the two readings this
    # document exists to keep apart.
    chained = [t for t in model.transitions.values() if getattr(t, "checks", ())]
    if chained:
        gathered["guard_dimensions"] = len(chained)

    # **Both are gathered from the model itself, so a model with behaviour in it
    # has both.** The condition inventory is decided per transition and the
    # setup chain is walked per transition, so an empty model is the only case
    # where either is genuinely absent — and that case is already reported by
    # `model`.
    if model.transitions:
        gathered["condition_inventory"] = len(model.transitions)
        gathered["setup_cost"] = len(model.transitions)
        gathered["risk_factors"] = len(bands)
        # **Only where an obligation could actually be derived.** An endpoint
        # with no path parameter, no declared security and no body obliges
        # nothing — so a model of those alone leaves this ungathered rather than
        # reporting an empty obligation set as a complete one.
        obliged = [t for t in model.transitions.values()
                   if t.security or any(
                       (p or {}).get("location") in ("path", "body")
                       or ((p or {}).get("location") == "query"
                           and (p or {}).get("required", False))
                       for p in (t.inputs or ()))]
        if obliged:
            gathered["negative_obligations"] = len(obliged)

    viability = json.loads(test_design(journey=journey, surface=surface,
                                       detail=True))
    if viability.get("ok") is not False:
        gathered["viability"] = viability.get("depth", {}).get("counts") or True

    coverage = json.loads(coverage_report(journey=journey, surface=surface))
    if coverage.get("ok"):
        gathered["existing_coverage"] = (coverage.get("coverage") or {}).get(
            "covered")

    requirement: dict | None = None
    if requirement_id:
        raw = json.loads(get_requirement(requirement_id, detail=True))
        if raw.get("ok") is not False and raw.get("id"):
            requirement = raw
            gathered["requirement"] = raw.get("id")
            gathered["acceptance_criteria"] = len(raw.get("criteria") or [])
            gathered["criteria_provenance"] = raw.get("provenance_counts") or {}
            if raw.get("lifecycle_state"):
                gathered["model_is_approved"] = raw["lifecycle_state"]
            text = raw.get("text") or raw.get("statement") or ""
            if text:
                from metis_mcp.ears_checker import check_ears_conformance

                gathered["ears_conformance"] = bool(
                    check_ears_conformance(text).conformant)
            from metis_mcp.ac_quality import assess as assess_quality

            gathered["criterion_quality"] = [
                f.describe() for criterion in (raw.get("criteria") or [])
                for f in assess_quality(criterion.get("text") or "")]

    specifications: tuple = ()
    spec = json.loads(get_spec(journey=journey, surface=surface, detail=True))
    if spec.get("ok") is not False and spec.get("id"):
        specifications = (spec,)
        gathered["specification"] = spec.get("id")

    validation = json.loads(validate_model(journey=journey, surface=surface))
    if validation.get("ok") is not False:
        gathered["validation_findings"] = validation.get("blocking", 0)

    unverifiable = product.unverifiable_ids(model)
    context = builders.DesignContext(
        model=model, requirement=requirement, specifications=specifications,
        coverage=coverage, viability=viability, risk_bands=bands, ranks=ranks,
        gathered=gathered)

    doc = document.build(f"{journey} ({surface})", context, section=section)
    if as_markdown:
        return document.render_markdown(doc)

    completeness = doc["completeness"]
    return _json({
        "ok": True,
        "journey": journey,
        "surface": surface,
        "section": section or "all",
        "status": completeness["status"],
        "gathered": sorted(gathered),
        "sections": [{"key": s["key"], "rows": len(s["rows"]),
                      "unstatable_because": s["unstatable_because"]}
                     for s in doc["sections"]],
        "missing_inputs": completeness["missing_inputs"],
        "means": completeness["means"],
        "unverifiable": len(unverifiable),
        "ordering": ("detectability, then defect-proneness, then id — the same "
                     "keys the `prioritise` stage applies to generated paths"),
        "detail_available": ("call again with as_markdown=true for the document "
                             "`metis design` writes"),
    })


# Pre-import analysis. These three read a DOCUMENT rather than the graph, which
# is what lets them run before anything is landed -- the whole point of a
# pre-processor. `intake` ran fetch, validate, land, THEN assessed risk, so the
# first moment anybody saw what was wrong with a claim was after it was a node.
@mcp.tool()
def check_intent(document_json: str) -> str:
    """Is every need specified, and every specification checkable?

    `model_sources.intent.validate` has always existed and was reachable only
    from `metis intent check` on the CLI, so no workflow and no agent could
    consult it. This is the same reader, exposed.

    **An Intent with no Specification is refused, not landed.** A need nobody
    has said the behaviour of is a wish, and landing it would put a node in the
    graph that nothing can ever be checked against (D-1).
    """
    import json as _json_mod

    from metis_mcp.model_sources.intent import IntentFileRefused, validate

    try:
        raw = _json_mod.loads(document_json)
    except ValueError as e:
        return _json({"ok": False, "refused": f"not JSON: {type(e).__name__}: {e}"})

    try:
        document = _intent_from(raw)
    except (IntentFileRefused, ValueError, KeyError, TypeError) as e:
        return _json({"ok": False, "refused": f"{type(e).__name__}: {e}"})

    problems = validate(document)
    return _json({
        "ok": True,
        "conforms": not problems,
        "intents": len(document.intents),
        "specifications": len(document.specifications),
        "problems": [{"kind": p.kind, "subject": p.entry_id, "detail": p.detail}
                     for p in problems],
        "not_checked": ("whether the need is worth building, and whether "
                        "anybody agrees with it — neither is a question a "
                        "checker can answer"),
    })


def _intent_from(raw: dict):
    """An `IntentFile` from a parsed document, without touching the filesystem.

    `intent.load` takes a path because the CLI has one. A tool does not, and
    writing the document to a temp file so the loader could read it back would
    be a filesystem round trip to reuse a signature.
    """
    import json as _json_mod
    import tempfile
    from pathlib import Path as _Path

    from metis_mcp.model_sources.intent import load

    with tempfile.TemporaryDirectory() as directory:
        target = _Path(directory) / "intent.json"
        target.write_text(_json_mod.dumps(raw))
        return load(target)


@mcp.tool()
def analysis_aspects() -> str:
    """The four readings a stated intent gets, and which skill performs each.

    Two of the four are owned outside the business-analyst family on purpose:
    the requirement reading is `metis-knowledge-capture`'s and the design and
    risk readings belong to the design and risk families. The analyst consults
    them rather than reimplementing what they already do.
    """
    from metis_mcp.analysis import areas

    return _json({"ok": True, **areas.describe()})


@mcp.tool()
def analysis_report(document_json: str, journey: str = "", surface: str = "api",
                    as_markdown: bool = False) -> str:
    """Read one stated intent from four directions, before it reaches the graph.

    Composes the intent validator, the wording checkers, the design ledger and
    the risk ledger. Each sees a hole the other three cannot, and every gap
    names the aspect that found it and what would close it.

    **`ready` means representable, not agreed.** A ready intent lands at
    `Quarantine` carrying every reported gap, and a person decides at G1 (S-4).
    `not-ready` means the claim cannot be represented honestly — a need with no
    specification, not a need nobody has costed.

    `journey` lets the design half be gathered; without it that aspect reports
    what it could not consult rather than nothing.
    """
    import json as _json_mod

    from metis_mcp.analysis import document as analysis_document
    from metis_mcp.analysis import readiness
    from metis_mcp.design import inputs as design_ledger
    from metis_mcp.risk import inputs as risk_ledger

    try:
        raw = _json_mod.loads(document_json)
    except ValueError as e:
        return _json({"ok": False, "refused": f"not JSON: {type(e).__name__}: {e}"})

    # The intent aspect, where the document is an intent file at all. A UIF is
    # not one, and reporting "no intent problems" for it would be a check that
    # never ran presented as a check that passed.
    intent_problems: list = []
    is_intent_file = isinstance(raw, dict) and "intents" in raw
    document = raw
    if is_intent_file:
        from metis_mcp.model_sources.intent import IntentFileRefused, validate

        try:
            document = _intent_from(raw)
            intent_problems = validate(document)
        except (IntentFileRefused, ValueError, KeyError, TypeError) as e:
            return _json({"ok": False,
                          "refused": f"the intent file could not be read: {e}"})

    subjects = readiness.subjects_of(document)

    # The requirement aspect: EARS conformance and criterion quality, per claim.
    from metis_mcp.ac_quality import assess as assess_quality
    from metis_mcp.ears_checker import check_ears_conformance

    wording = {}
    for subject in subjects:
        text = subject.statement or ""
        conformant = bool(check_ears_conformance(text).conformant) if text else False
        quality = [f for statement in subject.specifications
                   for f in assess_quality(statement)]
        wording[subject.id] = (conformant, quality)

    # The design and risk aspects. Both are about the scope rather than one
    # claim, and both are gathered only when a journey names one — an ungathered
    # aspect reports what it could not consult, which is not the same as clean.
    design_missing: list = []
    risk_missing: list = []
    if journey:
        report = json.loads(design_report(journey=journey, surface=surface))
        if report.get("ok"):
            design_missing = [m for m in report.get("missing_inputs") or []
                              if m.get("required")]
    else:
        design_missing = [
            {"name": item.name, "absent_means": item.absent_means,
             "question": item.question}
            for item in design_ledger.INPUTS
            if item.source == design_ledger.ASKED and item.required]

    risk_missing = [
        {"name": item.name, "absent_means": item.absent_means,
         "question": item.question}
        for item in risk_ledger.inputs_for(risk_ledger.REQUIREMENT)
        if item.source == risk_ledger.ASKED and item.required]

    # The fifth reading. Like the design half it needs a model, so it is
    # gathered only behind a named journey — and `journey_consulted` already
    # tells a reader which of the two states this run was in.
    consumers_unknown = consumers_total = 0
    if journey:
        from metis_mcp.analysis import consumers as consumer_analysis

        try:
            with session() as s:
                loaded = load_from_graph(s, journey, surface)
            if loaded.found:
                counted = consumer_analysis.describe(loaded.model)
                consumers_unknown = counted["unknown"]
                consumers_total = len(counted["by_transition"])
        except GraphNotConfigured:
            # A run without a graph is a normal way to use this. The aspect
            # reports nothing rather than reporting zero unknowns, which would
            # read as "every consumer is named".
            pass

    analysis = readiness.analyse(
        document, wording=wording, intent_problems=intent_problems,
        design_missing=design_missing, risk_missing=risk_missing,
        consumers_unknown=consumers_unknown, consumers_total=consumers_total)

    subject_name = subjects[0].id if len(subjects) == 1 else (journey or "intent")
    if as_markdown:
        return analysis_document.render_markdown(
            analysis_document.build(subject_name, analysis))
    return _json({"ok": True, "subject": subject_name,
                  "journey_consulted": bool(journey), **analysis})


# Static SQL review needs no database, so it is not behind the execution tier --
# reading a statement is not touching the system that runs it.
@mcp.tool()
def sql_review(statement: str, dialect: str = "postgresql") -> str:
    """Anti-patterns in a SQL statement, and how to check them safely.

    **Findings are candidates, not defects.** This has no schema, no statistics
    and no plan, so it cannot know whether an index exists or a join is
    redundant — a person with the schema settles each in seconds.

    The validation plan separates `EXPLAIN`, which asks the planner and executes
    nothing, from `EXPLAIN ANALYZE`, which **runs the statement** with its
    writes and its locks. They are different acts at different tiers.
    """
    from metis_mcp.sql_analysis import review

    return _json(review(statement, dialect))


@mcp.tool()
def sql_confirm(statement: str, dialect: str = "postgresql",
                target: str = "") -> str:
    """How far a statement can actually be confirmed, and where it stopped.

    **"Confirmed" is a ladder, not a boolean** — `shaped`, `static`, `planned`,
    `executed` — and the answer always says which rung it reached. Running a
    statement is what `METIS_EXECUTE` gates, `off` is the default, and
    `EXPLAIN ANALYZE` executes with its writes and its locks. A statement that
    reads cleanly and a statement that ran are different claims.

    Stopping is not failing: *"METIS_EXECUTE is off, so nothing was run"* is the
    honest answer, and it is the one this returns unless a deployment has asked
    for more and named a target.
    """
    from metis_mcp.sql_analysis import confirm

    return _json(confirm(statement, dialect, target=target))


# Risk arithmetic. Tools rather than prose because the placement rule's question
# — *could a unit test assert its output?* — answers yes for every one of them,
# and a cheat sheet restating `Exposure = P x I` in markdown computes nothing.
#
# Each returns the figure AND what it rests on. A 5x5 score is an ordinal rank
# and EMV is a quantity; a caller that cannot tell them apart will sum the first.
@mcp.tool()
def risk_exposure(probability: int, impact: int) -> str:
    """Risk exposure on the 5x5, with the band and what the number means.

    **An ordinal rank, not a quantity.** Probability and impact are 1..5 labels,
    so the product orders risks and does not measure them — it cannot be summed,
    averaged, or compared across projects. For a figure that can, use `risk_emv`.
    """
    from metis_mcp.risk.exposure import RiskInputRefused, heat_map_cell

    try:
        return _json({"ok": True, **heat_map_cell(probability, impact)})
    except RiskInputRefused as e:
        return _json({"ok": False, "reason": str(e)})


@mcp.tool()
def risk_emv(probability: float, financial_impact: float) -> str:
    """Expected Monetary Value: a real probability times a real amount.

    Unlike a 5x5 score this IS a quantity and may be summed across a portfolio.
    A 1..5 ordinal passed here is **refused**, not computed: it would produce a
    figure up to five times too large and entirely plausible-looking, and EMV is
    the number that ends up in a budget.
    """
    from metis_mcp.risk.exposure import RiskInputRefused, emv

    try:
        return _json({"ok": True, **emv(probability, financial_impact)})
    except RiskInputRefused as e:
        return _json({"ok": False, "reason": str(e)})


@mcp.tool()
def risk_pert(optimistic: float, most_likely: float, pessimistic: float) -> str:
    """PERT `(O + 4M + P) / 6`, with the spread.

    The standard deviation comes back too, because an estimate without one
    invites the mean to be read as a commitment. Estimates out of order are
    refused rather than sorted — a confident answer from an input somebody
    stated wrongly is worse than a refusal.
    """
    from metis_mcp.risk.exposure import RiskInputRefused, pert

    try:
        return _json({"ok": True, **pert(optimistic, most_likely, pessimistic)})
    except RiskInputRefused as e:
        return _json({"ok": False, "reason": str(e)})


@mcp.tool()
def risk_register_check(register_json: str) -> str:
    """What is incoherent in a risk register — never whether a risk is real.

    Judgement is not computable and is not attempted. Self-contradiction is: the
    worst failure here is a `score` column that no longer equals probability x
    impact because somebody re-rated and did not recalculate, which sorts that
    risk wrongly in every report and looks completely normal.

    The summary reports authored and model-derived risks **apart**. A
    model-derived risk says something is untested, not that it is likely, and
    averaging across the two would let a coverage gap read as a forecast.
    """
    import json as _json_mod

    from metis_mcp.risk.register import summarise, validate

    try:
        register = _json_mod.loads(register_json)
    except _json_mod.JSONDecodeError as e:
        return _json({"ok": False, "reason": f"register is not valid JSON: {e}"})

    findings = validate(register)
    return _json({
        "ok": not [f for f in findings if f.severity == "error"],
        "findings": [f.describe() for f in findings],
        "summary": summarise(register),
    })


# The gather-or-ask half. These three exist because a risk assessment built only
# from what Métis can reach LOOKS thorough — nine gathered facts about a
# requirement, none of them business criticality — and the missing half is the
# one that decides the answer. Every assessment declares both.
@mcp.tool()
def risk_inputs(assessment: str = "requirement") -> str:
    """What a risk assessment needs, split into what Métis gathers and what it must ask.

    `assessment` is `requirement` or `release`. The `asked` half carries the
    exact question to put to a person — not a topic, which gets a shrug.

    Every input says what its absence MEANS, because that string is printed
    where the value should have been and an assessment missing required inputs
    is unfinished, never low-risk.
    """
    from metis_mcp.risk.inputs import UnknownAssessment, plan

    try:
        return _json({"ok": True, **plan(assessment)})
    except UnknownAssessment as e:
        return _json({"ok": False, "reason": str(e)})


@mcp.tool()
def requirement_risk(requirement_id: str, journey: str = "", surface: str = "api",
                     as_markdown: bool = False) -> str:
    """The risk a requirement carries, from what Métis can observe about it.

    Gathers EARS conformance, criterion count and provenance, lifecycle state,
    coverage and the trace — then reports the five things it **cannot** derive
    (criticality, volatility, regulatory exposure, agreement, dependencies) as
    open questions with the words to ask.

    **`status: incomplete` until those are answered.** A short risk list here
    means nobody has answered them, not that the requirement is safe. Every
    candidate carries `probability: null` and `derived_from: model`.

    `journey` is what lets coverage be gathered — a requirement id alone does
    not name a scope, and without one that input reports as not gathered rather
    than as zero coverage. `as_markdown` returns the document
    `metis risk assess` would write.
    """
    from metis_mcp.risk import assessment as risk_assessment
    from metis_mcp.risk import document, inputs

    try:
        with session() as s:
            from metis_mcp.mbt.graph_loader import load_requirement

            row = load_requirement(s, requirement_id)
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    if row is None:
        return _json({"ok": False, "reason": f"no requirement {requirement_id!r}"})

    # Only what was actually read is recorded. A key absent here renders as
    # "not gathered, therefore not assessed" rather than as a passing check.
    gathered: dict = {}
    criteria = row.get("criteria") or []
    gathered["criteria_count"] = len(criteria)
    intent = [c for c in criteria if c.get("provenance") in
              ("human_confirmed", "independently_authored")]
    gathered["criteria_provenance"] = {"intent": len(intent),
                                       "code_derived": len(criteria) - len(intent)}
    if row.get("lifecycle_state"):
        gathered["lifecycle_state"] = row["lifecycle_state"]
    gathered["anchor"] = ", ".join(row.get("anchors") or [])
    gathered["superseded"] = bool(row.get("valid_to"))

    text = row.get("text") or row.get("statement") or ""
    if text:
        from metis_mcp.ears_checker import check_ears_conformance

        gathered["ears_conformance"] = bool(
            check_ears_conformance(text).conformant)

    quality: list[str] = []
    for criterion in criteria:
        body = criterion.get("text") or ""
        if not body:
            continue
        from metis_mcp.ac_quality import assess as assess_quality

        quality += [f.describe() for f in assess_quality(body)]
    gathered["criterion_quality"] = quality

    if journey:
        report = json.loads(coverage_report(journey=journey, surface=surface))
        if report.get("ok"):
            gathered["coverage"] = (report.get("coverage") or {}).get("covered")

    candidates = risk_assessment.for_requirement(gathered)
    completeness = inputs.completeness(inputs.REQUIREMENT, gathered, {})
    doc = document.build(inputs.REQUIREMENT, requirement_id,
                         gathered=gathered, candidates=candidates,
                         completeness=completeness)
    if as_markdown:
        return document.render_markdown(doc)
    return _json({
        "ok": True,
        "requirement": requirement_id,
        "status": completeness["status"],
        "gathered": {k: v for k, v in gathered.items()},
        "candidates": candidates,
        "missing_inputs": completeness["missing_inputs"],
        "means": completeness["means"],
    })


@mcp.tool()
def release_risk(journey: str, surface: str = "api",
                 as_markdown: bool = False,
                 changed_files: list[str] | None = None, repo: str = "",
                 since: str = "", until: str = "HEAD",
                 register_json: str = "") -> str:
    """The risk of releasing a scope, from coverage, validation and what was run.

    **Consumes readiness, never recomputes it.** `coverage_report` owns the
    figures and `metis-release-readiness` owns the evidence ladder; this adds the
    risk framing and nothing else, so the two cannot give different answers to
    one question.

    Reports the five things no tool can supply — appetite, rollback, external
    commitment, support readiness, accepted known issues — as open questions.
    Without them there is no threshold, so there is no verdict here either.

    Name a diff (`changed_files`, or `since`/`until` with `repo`) to gather
    `change_exposure`, and a register (`register_json`) to gather
    `open_model_risks`. Both are optional and absent is honest.
    """
    # **Why those two arguments exist.** `RELEASE_INPUTS` declared
    # `change_exposure` (tool: `change_review`) and `open_model_risks` (tool:
    # `risk_report`) and this function populated neither, because it accepted no
    # argument that could reach either one. A declared input no surface can
    # supply is a contract with one side missing: both reported as "not
    # gathered" permanently, for a reason that was never the caller's, and
    # `required=False` meant nothing ever failed to say so.
    #
    # They stay `required=False`. A release assessed without a diff is a normal
    # thing to want, and each `absent_means` already states what its absence
    # costs.
    from metis_mcp.risk import assessment as risk_assessment
    from metis_mcp.risk import document, inputs

    # `detail=True` because `blocking_detail` is where the findings themselves
    # are; the default payload carries only a count, and a risk that says
    # "3 blocking findings" without naming them cannot be acted on.
    raw = json.loads(coverage_report(journey=journey, surface=surface,
                                     detail=True))
    if not raw.get("ok"):
        return _json(raw)

    gathered: dict = {}
    coverage = raw.get("coverage") or {}
    if "covered" in coverage:
        # The COUNT of uncovered transitions, not a percentage: `for_release`
        # asks whether anything is uncovered, and a percentage would need a
        # denominator this payload does not promise.
        gathered["coverage"] = coverage.get("covered")
    validation = raw.get("validation") or {}
    gathered["validation_findings"] = validation.get("blocking_detail") or []

    # A STRING when everything was measured, a list otherwise. Normalised here
    # rather than passed through, because `for_release` iterating a string would
    # raise one risk per character.
    unmeasured = raw.get("unmeasured")
    gathered["unmeasured"] = unmeasured if isinstance(unmeasured, list) else []

    if raw.get("confidence_capped_by"):
        gathered["confidence_capped_by"] = raw["confidence_capped_by"]

    from metis_mcp.execution import describe as describe_tier

    tier = describe_tier()
    # `coverage_report` reads no execution result by design (C-10), so there is
    # nothing to carry over from it. At tier `off` nothing was observed and the
    # empty list is the honest value; above `off` this is left ABSENT, which
    # renders as "not gathered" rather than as "nothing ran".
    if tier.get("tier") == "off":
        gathered["execution_evidence"] = []

    # The diff, if one was named. `change_review` grades what a change leaves
    # unasserted; `for_release` raises one candidate per graded finding.
    if changed_files or since:
        reviewed = json.loads(change_review(
            changed_files=changed_files, repo=repo, since=since, until=until,
            journey=journey, surface=surface))
        if reviewed.get("ok"):
            gathered["change_exposure"] = reviewed.get("findings") or []

    # The register, if one was given. Read through `risk_report` so the figures
    # here are the same ones the consolidated report shows -- two readers of one
    # file giving two answers is the defect `release_risk` already refuses to
    # commit against `coverage_report`.
    #
    # It raises no candidate, deliberately, and `coverage` is the precedent: an
    # input can inform the assessment without generating a risk. These rows are
    # risks somebody has ALREADY recorded against this scope, so raising a
    # candidate per row would put each one in the register twice -- once as
    # itself and once as Métis noticing it. What the reader needs is that they
    # exist while judging the rest, which is what the gathered table gives.
    if register_json:
        reported = json.loads(risk_report(register_json))
        if reported.get("ok"):
            gathered["open_model_risks"] = reported.get("needs_attention") or []

    candidates = risk_assessment.for_release(gathered)
    completeness = inputs.completeness(inputs.RELEASE, gathered, {})
    doc = document.build(inputs.RELEASE, f"{journey} ({surface})",
                         gathered=gathered, candidates=candidates,
                         completeness=completeness)
    if as_markdown:
        return document.render_markdown(doc)
    return _json({
        "ok": True,
        "journey": journey,
        "surface": surface,
        "status": completeness["status"],
        "gathered": gathered,
        "candidates": candidates,
        "missing_inputs": completeness["missing_inputs"],
        "means": completeness["means"],
        "readiness_owner": ("coverage figures and the evidence ladder come from "
                            "coverage_report and metis-release-readiness; this "
                            "adds risk framing and recomputes neither"),
    })


@mcp.tool()
def risk_report(register_json: str) -> str:
    """The consolidated report: what a register says, in one place.

    Distribution across bands and categories, which risks carry the exposure,
    whether those above the threshold have owners and responses, and which
    categories nobody has looked at. `risk_register_check` asks whether the
    register is self-consistent; this asks what it says.

    **There is no overall risk score and asking for one is refused in the
    output.** A 5x5 exposure is an ordinal rank, the register holds two kinds of
    claim that must not be averaged, and a model-derived risk has no probability
    until a person sets one. Bands are recomputed from probability x impact
    rather than read from a stored `score`, so a stale column cannot move the
    distribution.
    """
    import json as _json_mod

    from metis_mcp.risk.report import consolidate

    try:
        register = _json_mod.loads(register_json)
    except _json_mod.JSONDecodeError as e:
        return _json({"ok": False, "reason": f"register is not valid JSON: {e}"})

    report = consolidate(register)
    return _json({"ok": not report["errors"], **report})


@mcp.tool()
def risk_categories() -> str:
    """The risk breakdown structure, and the boundaries people confuse.

    A taxonomy, not a judgement: which category a risk belongs to is a person's
    call; whether the category exists is not. Free-text categories are how a
    register grows `Tech`, `Technical` and `technical` as three rows in one chart.
    """
    from metis_mcp.risk.rbs import (
        BOUNDARIES, CATEGORIES, PRODUCT_CATEGORIES, PROCESS_CATEGORIES,
    )

    return _json({
        "ok": True,
        "categories": CATEGORIES,
        "boundaries": [{"between": [a, b], "question": q}
                       for a, b, q in BOUNDARIES],
        # The PRODUCT taxonomy, kept separate and never merged into one
        # distribution. `CATEGORIES` classifies risks to the project; a risk to
        # the product ("this endpoint's authorisation is asserted by nothing")
        # has nowhere to go there but `Quality`, which would hold every software
        # risk a team has. These are ISO/IEC 25010's quality characteristics.
        "product_categories": dict(PRODUCT_CATEGORIES),
        # How the WORK of assuring quality fails, as opposed to how the product
        # or the project does. Neither of the other two has anywhere to put "the
        # test environment drifted" or "the suite is too flaky to read", and
        # those are the risks a quality engineer actually carries.
        "process_categories": dict(PROCESS_CATEGORIES),
        "means": "three taxonomies, and they are never merged into one "
                 "distribution. `categories` classifies risks to the PROJECT "
                 "(who funds it), `product_categories` risks to the PRODUCT "
                 "(ISO 25010 — what the software can be wrong about), and "
                 "`process_categories` risks to the QUALITY WORK itself — "
                 "requirements, test design, test data, environments, "
                 "automation, regression, release, observability. Each family "
                 "is owned by different people, which is why a merged chart "
                 "describes no decision anybody makes. Everything Métis derives "
                 "from a model files under `process_categories`. All three are "
                 "a starting point — an RBS is organisational and a deployment "
                 "is expected to narrow it in one place",
    })


def _product_risk_inputs(journey: str, surface: str):
    """Model, ledger, detections and technical profiles, from one session.

    One session for every read, for the reason `coverage` gives: two would be
    two chances for the graph to change underneath a single reported figure.
    """
    from metis_mcp.mbt.coverage import build_ledger
    from metis_mcp.mbt.graph_loader import (
        load_component, load_execution_outcomes, load_validating_criteria,
    )
    from metis_mcp.mbt.path_generation import generate
    from metis_mcp.risk import detection, product

    with session() as s:
        report = load_from_graph(s, journey, surface)
        if not report.found:
            return None, _no_such_model(s, journey, surface)
        model = report.model
        component = load_component(s, journey, surface)
        validating = load_validating_criteria(s, journey, surface)
        outcomes = load_execution_outcomes(s)

    ledger = build_ledger(model, generate(model, "all-transitions", 10),
                          component=component, validating_criteria=validating)
    # **Empty here, and that is the correct value rather than a placeholder.**
    # `build_ledger` measures every transition in the model, so at this level
    # nothing is unmeasurable -- `ledger.uncovered` is measured-and-zero, which
    # is a different fact and is what `detection` already reports as UNNOTICED.
    # `coverage_report`'s `unmeasured` is a wider scope (what it could not reach
    # at all) and reaches these tools through `release_risk`, not through here.
    # Passed explicitly so the parameter is never silently defaulted.
    unmeasured: list[str] = []
    found = detection.detection_over(
        model.transition_ids(), ledger.rows, outcomes, unmeasured)
    unverifiable = product.unverifiable_ids(model)
    technical = {tid: product.technical_profile(model, tid, unverifiable)
                 for tid in found["scores"]}
    return {"model": model, "ledger": ledger, "detection": found,
            "technical": technical}, None


@mcp.tool()
def product_risk(journey: str, surface: str = "api") -> str:
    """Product risk for a model: the technical factors, and the questions.

    Product risk, not project risk. `risk_categories` carries both taxonomies and
    they are never merged.

    The technical half is gathered from the recovered model (PRISMA's likelihood
    factors); the business half is **asked**, because every one of the six is a
    statement about what the organisation values. Reports the raw counts beside
    the ratings, and names the PRISMA factors it cannot yet answer.

    Sets no probability. A defect-proneness band ranks by how much there is to
    get wrong; it does not forecast a failure.
    """
    from metis_mcp.risk import product

    try:
        loaded, refusal = _product_risk_inputs(journey, surface)
    except GraphNotConfigured as e:
        return _json(_no_graph(e))
    if refusal:
        return _json(refusal)

    profiles = loaded["technical"]
    by_band: dict[str, int] = {}
    for profile in profiles.values():
        by_band[profile["band"]] = by_band.get(profile["band"], 0) + 1

    return _json({
        "ok": True,
        "journey": journey,
        "surface": surface,
        "profiles": profiles,
        "by_band": by_band,
        "item_types": product.RISK_ITEM_TYPES,
        "open_questions": [
            {"name": i.name, "question": i.question,
             "required": i.required, "absent_means": i.absent_means}
            for i in product.business_inputs()],
        "means": product.MEANS,
    })


@mcp.tool()
def risk_priority(journey: str, surface: str = "api", limit: int = 0) -> str:
    """What to test first, and what the order is by.

    Sorted by detectability, then defect-proneness, then id. The last key makes
    the order total, so a regenerated suite diffs cleanly (P-7).

    It is a lexicographic sort and **not** a product: three ordinals multiplied
    is an RPN, and 1x5x5 and 5x5x1 both read as 25 — which hides which axis is
    bad and therefore what to do about it.

    Ranks on the two gathered axes only. Until the business half of
    `product_risk` is answered this has ordered the work by effort, not by what
    is at stake.
    """
    from metis_mcp.risk import prioritisation

    try:
        loaded, refusal = _product_risk_inputs(journey, surface)
    except GraphNotConfigured as e:
        return _json(_no_graph(e))
    if refusal:
        return _json(refusal)

    ordered = prioritisation.order(loaded["detection"]["scores"],
                                   loaded["technical"])
    return _json({
        "ok": True,
        "journey": journey,
        "surface": surface,
        "order": ordered[:limit] if limit else ordered,
        "total": len(ordered),
        "unmeasured": loaded["detection"]["unmeasured"],
        "failing": loaded["detection"]["failing"],
        "sorted_by": ["detection desc", "technical_score desc", "id asc"],
        "means": prioritisation.ORDER_MEANS,
    })


@mcp.tool()
def risk_coverage(journey: str, surface: str = "api") -> str:
    """Is the uncovered part the part that matters?

    A pivot, never a weighted percentage: an ordinal band cannot be summed or
    averaged, and "80% covered" is a different fact depending on which 20% is
    missing. Reports, per band, how many behaviours are uncovered.

    `unmeasured` belongs to no band and to no count — reporting it as covered
    claims safety and as uncovered claims a gap, and neither was measured.
    """
    from metis_mcp.risk import prioritisation

    try:
        loaded, refusal = _product_risk_inputs(journey, surface)
    except GraphNotConfigured as e:
        return _json(_no_graph(e))
    if refusal:
        return _json(refusal)

    found = loaded["detection"]
    report = prioritisation.weighted_coverage(
        found["scores"], loaded["technical"], found["unmeasured"])
    return _json({"ok": True, "journey": journey, "surface": surface, **report})


@mcp.tool()
def residual_risk(journey: str, surface: str = "api",
                  max_unnoticed: int = -1, max_failing: int = -1,
                  max_unmeasured: int = -1) -> str:
    """What is left un-mitigated, as evidence against a threshold. Never a verdict.

    Two populations kept apart because they need different work: behaviour
    nothing would notice breaking (a test), and behaviour something noticed IS
    broken (a fix). One total would let a rising failure count be cancelled by
    rising coverage.

    The thresholds are yours and are settled at planning time. Pass none and this
    reports what there is and says plainly that nothing here can judge it.
    """
    from metis_mcp.risk import prioritisation

    try:
        loaded, refusal = _product_risk_inputs(journey, surface)
    except GraphNotConfigured as e:
        return _json(_no_graph(e))
    if refusal:
        return _json(refusal)

    found = loaded["detection"]
    report = prioritisation.residual(found["scores"], loaded["technical"],
                                     unmeasured=found["unmeasured"])
    limits = {name: value for name, value in
              (("unnoticed", max_unnoticed), ("failing", max_failing),
               ("unmeasured", max_unmeasured)) if value >= 0}
    return _json({
        "ok": True, "journey": journey, "surface": surface,
        "residual": report,
        "exit_criteria": prioritisation.exit_criteria(report, limits),
    })


# **The read half of a write tool, which had no read half.**
# `defects/classify.py` was reachable only through `file_defect` -- a write-tier
# tool needing `METIS_MCP_WRITE` *and* `METIS_ALLOW_EXTERNAL_WRITES` -- so the
# question could not be asked without filing a defect. That is the wrong order:
# the classification is what tells you whether a defect is the right artefact at
# all. A schema drift points at the system, an assertion drift at the test, a 503
# at the environment, and none of those wants the same person.
@mcp.tool()
def classify_failure(evidence: str, expected: str = "", actual: str = "",
                     phase: str = "") -> str:
    """What a failure points at: the system, the test, or the environment.

    **No priority is set**, and that is a refusal rather than an omission: how
    urgent a defect is depends on what it blocks and who is waiting, and neither
    is in a stack trace.

    **Métis did not observe this failure** — the evidence is the caller's, and
    `unclassified` means no rule matched it, never that it is benign.
    """
    from metis_mcp.defects import classify

    return _json({"ok": True,
                  **classify.describe(evidence, expected=expected,
                                      actual=actual, phase=phase)})


# `risk/verdict.py` closed the recommendation vocabulary and had no importer
# anywhere in `metis_mcp/` -- a rule whose whole point is being enforced rather
# than remembered, enforced by nothing. The release-readiness specialist
# meanwhile reproduced the whole ladder in prose, so the refusal its own text
# called "checked rather than remembered" was a model copying a table correctly.
@mcp.tool()
def release_verdict(recommendation: str = "", confidence: str = "",
                    execution_records: int = -1, stale: bool = False) -> str:
    """Whether the evidence supports the recommendation somebody wants to give.

    **Refuses `Go` on coverage alone.** Coverage says a behaviour is *tested*
    and nothing about whether it *works*, so covered-and-failing is a real state
    — and it is the state a coverage-derived `Go` would call ready (C-11).

    Pass `recommendation` and `confidence` to check a pairing, or
    `execution_records` (and `stale`) to derive the confidence from the evidence
    that exists. With no recommendation it serves the whole ladder.

    **The verdict is on the pairing, never on the release.** A refusal says the
    words do not match the evidence; whether the release is safe is a different
    question with a different owner.
    """
    from metis_mcp.risk import verdict as ladder

    if not recommendation:
        return _json({"ok": True, "ladder": ladder.describe()})

    if not confidence:
        if execution_records < 0:
            return _json({
                "ok": False,
                "reason": ("give either `confidence`, or `execution_records` so "
                           "it can be derived. Neither was supplied, and "
                           "assuming one would invent the evidence this refuses "
                           "to let a recommendation rest on"),
                "confidence": list(ladder.CONFIDENCE)})
        confidence = ladder.confidence_from(execution_records, stale=stale)

    try:
        checked = ladder.check(recommendation, confidence)
    except ladder.UnknownConfidence as e:
        return _json({"ok": False, "reason": str(e),
                      "confidence": list(ladder.CONFIDENCE)})
    return _json({**checked, "derived_confidence": confidence})


@mcp.tool()
def risk_candidates(changed_files: list[str] | None = None, repo: str = "",
                    since: str = "", until: str = "HEAD",
                    journey: str = "", surface: str = "api") -> str:
    """Risks Métis can OBSERVE: behaviour a change leaves unasserted.

    The one risk tool that needs a graph. Every candidate is `derived_from:
    model` and carries **no probability** — Métis observed a gap, it did not
    forecast a failure, and a number invented to fill that column would read as
    though it had. A person rates it, and the rating becomes theirs.

    These are observations, not an assessment. `coverage_report`'s `unmeasured`
    entries are candidates too; pass them to `risk.candidates.from_unmeasured`
    rather than having this recompute coverage.
    """
    from metis_mcp.change_review import findings_for
    from metis_mcp.risk.candidates import from_change_review

    raw = json.loads(impact(changed_files=changed_files, repo=repo,
                            since=since, until=until))
    if not raw.get("ok"):
        return _json(raw)

    depth = None
    if journey:
        try:
            from metis_mcp.viability import classify_depth

            with session() as s:
                report = load_from_graph(s, journey, surface)
            if report.found:
                depth = classify_depth(report.model)
        except (GraphNotConfigured, Exception):              # noqa: BLE001
            depth = None                                     # reported as absent

    candidates = from_change_review(findings_for(raw, depth))
    result = {
        "ok": True,
        "candidates": candidates,
        "count": len(candidates),
        "depth_consulted": bool(depth),
        "means": ("observations, not assessments — each needs a person to rate "
                  "the probability and take ownership before it is a risk"),
    }
    if not depth:
        # Same reason change_review names it: a missing input REMOVES candidates
        # rather than downgrading them. A short list here may mean nobody looked.
        result["note"] = ("no coverage-depth data, so positive-path-only "
                          "behaviour produced no candidate — pass `journey` "
                          "to include it")
    return _json(result)


@mcp.tool()
def artefact_confirm(artefact: str, kind: str = "curl",
                     target: str = "") -> str:
    """How far a generated call or scaffold can be confirmed, and where it stopped.

    **The ladder is `shaped` → `static` → `executed`, with no `planned`.** SQL
    has `EXPLAIN` — a way to ask a target what it would do without doing it.
    HTTP has no equivalent, so naming a rung nothing climbs would be worse than
    having three.

    `static` is X-6e as a check: a generated artefact states the accepted space
    and never a value. A curl carrying `"name": "test123"` has invented test
    data, which is worse than a visible gap because it looks runnable.

    Which tier `executed` needs is decided by the **verb**: a `GET` reads and is
    confirmable at `observe`; a `POST` makes something happen in a system that
    is not Métis's and needs `run`. A verb extraction could not recover gets the
    stricter of the two.
    """
    from metis_mcp import artefact_check

    if kind == "scaffold":
        return _json(artefact_check.confirm_scaffold(artefact))
    return _json(artefact_check.confirm_curl(artefact, target=target))


# What the behaviour model can establish about a diff. Deliberately NOT a code
# review: style and maintainability belong to the linters a repo already runs.
@mcp.tool()
def change_review(changed_files: list[str] | None = None, repo: str = "",
                  since: str = "", until: str = "HEAD",
                  journey: str = "", surface: str = "api") -> str:
    """Which behaviour a change leaves unasserted, graded by severity.

    `critical` — touched behaviour nothing validates. `major` — covered on the
    positive path only, so the complement has no oracle. `minor` — validated
    only by criteria written from the code, which is coverage and never
    correctness. `question` — a changed file matched nothing, which is **never**
    reported as "no impact".

    Produces the blocking list `open_merge_request` refuses over. It reviews
    behaviour, not code: a clean result is not a statement that the change is
    good.
    """
    from metis_mcp.change_review import findings_for, summarise

    raw = json.loads(impact(changed_files=changed_files, repo=repo,
                            since=since, until=until))
    if not raw.get("ok"):
        return _json(raw)

    depth = None
    if journey:
        try:
            from metis_mcp.viability import classify_depth

            with session() as s:
                report = load_from_graph(s, journey, surface)
            if report.found:
                depth = classify_depth(report.model)
        except (GraphNotConfigured, Exception):              # noqa: BLE001
            depth = None                                     # reported as absent

    result = summarise(findings_for(raw, depth))
    result["depth_consulted"] = bool(depth)
    if not depth:
        # Named, because a missing input removes findings rather than
        # downgrading them: no `major` here means nobody looked, not that the
        # complement is covered.
        result["note"] = ("no coverage-depth data, so `major` findings were not "
                          "evaluated — pass `journey` to include them")
    return _json(result)


@mcp.tool()
def list_entities(area: str = "") -> str:
    """Every business noun Métis knows, optionally within one area.

    A business entity is what a criterion is *about* — `record`, `user`,
    `session` — carrying what it is, what changes when you act on it, and the
    properties it has. Narrow with `area` when a domain is known.

    Fields that are null, empty or false are omitted.
    """
    from metis_mcp.mbt.graph_loader import load_entities

    try:
        with session() as s:
            rows = load_entities(s, area=area)
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    return _json({
        "ok": True,
        "count": len(rows),
        "area": area,
        "entities": [
            {"id": r.get("id"), "name": r.get("name"),
             "area": r.get("area_name") or r.get("area"),
             "description": r.get("description")}
            for r in rows
        ],
        "detail_available": "call get_entity(name) for one entity's full specification",
    })


@mcp.tool()
def get_entity(name: str, detail: bool = False) -> str:
    """One business entity: what it is, its properties, and what acting on it changes.

    By id or by name. Returns the definition by default; `detail` adds the
    rendered specification document, including every acceptance criterion that
    references this entity and the provenance grade of each.

    A criterion graded `code_derived` was written from the code, so its agreeing
    with the code is evidence of coverage and never of correctness (§4.1).

    Fields that are null, empty or false are omitted.
    """
    from metis_mcp.mbt.graph_loader import (
        load_entity, load_entity_criteria, load_entity_document,
    )

    try:
        with session() as s:
            entity = load_entity(s, name)
            if entity is None:
                return _json({"ok": False,
                              "reason": f"no business entity {name!r}"})
            criteria = load_entity_criteria(s, entity["id"])
            document = load_entity_document(s, name) if detail else None
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    from metis_mcp.specgen.entity import build

    spec = build(entity, criteria, area_name=entity.get("area_name") or "")
    payload = {
        "ok": True,
        "id": spec.entity_id,
        "name": spec.name,
        "area": spec.area_name,
        "description": spec.description,
        "impact": list(spec.impact),
        "properties": [
            {"name": p.name, "meaning": p.meaning, "values": list(p.values)}
            for p in spec.properties
        ],
        "criteria_count": len(spec.rules),
        # The distinction that separates a coverage claim from a correctness one.
        "criteria_by_provenance": {
            "intent": len(spec.intent_rules),
            "code_derived": len(spec.code_derived_rules),
        },
        "means": "code_derived criteria give coverage, never correctness (§4.1)",
    }

    if not detail:
        payload["detail_available"] = (
            "call again with detail=true for the criteria and the rendered document")
        return _json(payload)

    payload["criteria"] = [
        {"id": r.criterion_id, "text": r.text, "provenance": r.provenance,
         "is_intent": r.is_intent, "lifecycle_state": r.lifecycle_state,
         "requirement_id": r.requirement_id,
         "validates": list(r.transition_ids)}
        for r in spec.rules
    ]
    if document is not None:
        payload["document"] = {
            "id": document.get("id"),
            "rendered_at": document.get("rendered_at"),
            "content_hash": document.get("content_hash"),
            "lifecycle_state": document.get("lifecycle_state"),
            "body_markdown": document.get("body_markdown"),
        }
    else:
        # F-10: named rather than quietly absent. "Not rendered yet" and "has no
        # content" are different answers with different next steps.
        payload["document"] = None
        payload["document_note"] = (
            "no entity document has been rendered — run `entity render`")
    return _json(payload)


@mcp.tool()
def get_spec(journey: str, surface: str = "api", detail: bool = False) -> str:
    """The stored specification for one journey, as a stakeholder reads it.

    Generated from the model and landed in the graph, so this is a lookup rather
    than a re-render. Returns the document's identity and the component version
    it describes; `detail` adds the markdown body.

    Fields that are null, empty or false are omitted.
    """
    from metis_mcp.mbt.graph_loader import load_spec_document

    try:
        with session() as s:
            document = load_spec_document(s, journey, surface)
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    if document is None:
        return _json({
            "ok": False,
            "reason": (f"no specification has been rendered for "
                       f"{journey}-{surface} — run `spec <model> --land`"),
        })

    payload = {
        "ok": True,
        "id": document.get("id"),
        "name": document.get("name"),
        "component_id": document.get("component_id"),
        "version": str(document.get("version") or "") or None,
        "commit": document.get("commit_sha"),
        "rendered_at": document.get("rendered_at"),
        "content_hash": document.get("content_hash"),
        "lifecycle_state": document.get("lifecycle_state"),
    }
    if detail:
        payload["body_markdown"] = document.get("body_markdown")
    else:
        payload["detail_available"] = "call again with detail=true for the document body"
    return _json(payload)


@mcp.tool()
def get_requirement(requirement_id: str, detail: bool = False) -> str:
    """One requirement, its acceptance criteria, and where it came from.

    Returns the requirement and its provenance counts by default; `detail` adds
    every acceptance criterion in full.

    `anchors` names the artefact in the world the requirement was derived from —
    a Jira issue, a Confluence page, an OpenAPI document. That is a different
    fact from the Episode that ingested it: an anchor survives its Requirement
    being rejected.

    Fields that are null, empty or false are omitted.
    """
    from metis_mcp.mbt.graph_loader import load_requirement

    try:
        with session() as s:
            row = load_requirement(s, requirement_id)
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    if row is None:
        return _json({"ok": False, "reason": f"no requirement {requirement_id!r}"})

    criteria = row.get("criteria") or []
    intent = [c for c in criteria
              if c.get("provenance") in ("human_confirmed", "independently_authored")]
    payload = {
        "ok": True,
        "id": row.get("id"),
        "text": row.get("text"),
        "statement": row.get("statement"),
        "ears_pattern": row.get("ears_pattern"),
        "area": row.get("area"),
        "lifecycle_state": row.get("lifecycle_state"),
        "criteria_count": len(criteria),
        "criteria_by_provenance": {
            "intent": len(intent),
            "code_derived": len(criteria) - len(intent),
        },
        "anchors": [{"kind": a.get("label"), "id": a.get("id")}
                    for a in (row.get("anchors") or [])],
    }
    if detail:
        payload["criteria"] = criteria
    else:
        payload["detail_available"] = "call again with detail=true for the criteria"
    return _json(payload)


@mcp.tool()
def search_knowledge(query: str, limit: int = 20) -> str:
    """Find business entities, requirements and acceptance criteria by term.

    Which of the three matched is part of the answer: an entity tells you what a
    noun means, a requirement what was asked for, a criterion what must be true.
    Results are grouped rather than merged, because the next step differs.

    Fields that are null, empty or false are omitted.
    """
    from metis_mcp.mbt.graph_loader import search_knowledge as _search

    if not query.strip():
        return _json({"ok": False, "reason": "an empty query matches everything; "
                                             "give a term"})
    try:
        with session() as s:
            rows = _search(s, query, limit=limit)
    except GraphNotConfigured as e:
        return _json(_no_graph(e))

    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row["label"], []).append({
            "id": row.get("id"),
            "name": row.get("name"),
            "body": (row.get("body") or "")[:200],
            "lifecycle_state": row.get("lifecycle_state"),
            "provenance": row.get("provenance"),
        })

    return _json({
        "ok": True,
        "query": query,
        "count": len(rows),
        "truncated": len(rows) >= limit,
        "results": grouped,
    })


@mcp.tool()
def run_status(run_id: str) -> str:
    """Where a workflow run got to, and what it is waiting for."""
    from metis_mcp.workflow.run import RunRecord, run_path

    record = RunRecord.load(run_path(run_id))
    if record is None:
        return _json({"ok": False, "reason": f"no run {run_id!r}"})
    blocked = record.outcome_for(record.blocked_on) if record.is_blocked else None
    return _json({
        "ok": True,
        "run_id": record.run_id,
        "workflow": record.workflow,
        "scope": record.scope,
        "blocked_on": record.blocked_on,
        "failed_reason": record.failed_reason,
        "complete": record.is_complete,
        "stages": [
            {"ordinal": o.ordinal, "stage": o.stage, "outcome": o.outcome,
             "detail": o.detail}
            for o in record.outcomes
        ],
        "outstanding": list(blocked.outstanding) if blocked else [],
        "next_command": blocked.next_command if blocked else "",
    })


@mcp.tool()
def decision_queue(workflow: str = "", limit: int = 50) -> str:
    """What is waiting on a person, across every run on this machine.

    `run_status` answers "where did THIS run get to" and needs an id you only
    have if you started it. This answers the question a reviewer actually
    arrives with, and the one that decides whether a gate is attended to or
    quietly forgotten.

    Blocked runs only. A failed run needs fixing and a complete one needs
    nothing; mixing either in turns a queue of decisions into a list of things
    that are merely unfinished.

    Every entry carries the gate's own `outstanding` and `next_command` — the
    engine authored both, and a caller neither composes the command nor
    re-derives what is blocking.
    """
    from metis_mcp.workflow.run import pending

    entries = []
    for record in pending():
        if workflow and record.workflow != workflow:
            continue
        blocked = record.outcome_for(record.blocked_on)
        entries.append({
            "run_id": record.run_id,
            "workflow": record.workflow,
            "scope": record.scope,
            "blocked_on": record.blocked_on,
            "waiting_since": record.started_at,
            "outstanding": list(blocked.outstanding) if blocked else [],
            # **No count here, deliberately.** `outstanding` is the gate's own
            # display lines, and G1's include a "NOT RECOVERED" section listing
            # what extraction could not model — so `len()` is a line count, not
            # a decision count. Reporting it as one inflated 31 elements awaiting
            # review into "40 items outstanding", which overstates what somebody
            # owes and is the `len(rows)` figure this codebase keeps finding.
            #
            # `detail` is the gate's own sentence and already carries the real
            # number. One authoritative count beats two that disagree.
            "detail": blocked.detail if blocked else "",
            "next_command": blocked.next_command if blocked else "",
        })

    by_workflow: dict[str, int] = {}
    for entry in entries:
        by_workflow[entry["workflow"]] = by_workflow.get(entry["workflow"], 0) + 1

    return _json({
        "ok": True,
        "waiting": entries[:limit],
        "total": len(entries),
        "by_workflow": by_workflow,
        "means": ("runs stopped at a gate, waiting for a person. Nothing here "
                  "has failed and nothing is in progress — each one is a "
                  "decision somebody owes. `next_command` is the engine's own "
                  "resolution for each, not a command this tool composed"),
    })


@mcp.tool()
def why_read_only() -> str:
    """Why this surface cannot approve, publish or land anything (N-8)."""
    return _json({
        "rule": "N-8",
        "statement": ("Read-only. No decision may be taken through the agent "
                      "surface — decisions require the evidence presentation of "
                      "N-3, which a chat session cannot provide."),
        "where_decisions_are_taken": [
            "the web review UI (§9.3), which blocks a decision it cannot evidence",
            "review export / review apply, as a diffable file (N-7)",
        ],
        "gates": {
            "G1": "model approval, between reconcile and generation",
            "G2": "publication, requiring a literal affirmative in the same run",
        },
    })


@mcp.tool()
def describe_library() -> str:
    """What documents this deployment serves as prompts and resources.

    The counterpart to `describe_policy` and `describe_execution`: it says what
    exists here rather than what is permitted. A deployment installed without
    the repository beside it has the tools and none of the skills, and it must
    say so — an empty library presented as a complete one is how a caller
    concludes a procedure does not exist.
    """
    from metis_mcp import library

    return _json(library.describe())


# ---------------------------------------------------------------------------
# Prompts and resources — the document half of the surface.
#
# ### There is no `@mcp.prompt` or `@mcp.resource` in this file, and that is
# ### deliberate. If you grepped for one and landed here, this is the answer.
#
# Tools are declared one per `def`, so `grep '@mcp.tool'` enumerates them and
# the inventory is readable in the file. Prompts and resources are **not**
# declared: they are discovered at import from `plugins/metis/skills/` and
# `docs/` by `library.py`, and registered in the loop below.
#
# Writing thirteen `@mcp.prompt` decorators would restate the skill list in
# Python — a second copy of `plugins/metis/skills/`, going stale the first time
# somebody adds a skill. That is precisely the duplication `agent_generator`
# exists to prevent, and the disease the sibling project caught: eight of its
# eleven hand-maintained agents carry unresolved merge-conflict markers.
#
# So the inventory moved rather than vanishing. **`docs/guide/mcp-tools.md` is
# the enumeration now** — generated from this module and the library, with
# `metis guide --check` failing on a diff, and `describe_library` answers the
# same question at runtime. `test_documentation_sync.py` asserts the guide names
# every prompt, so the list cannot drift the way a hand-written one would.
#
# A skill becomes a PROMPT because that is what it is: the procedure, its order,
# its gates, its refusals. Its steps, knowledge and references become RESOURCES,
# so progressive disclosure survives the move — `SKILL.md` is paid for when the
# prompt is invoked, and a step costs nothing until a reader fetches it.
#
# Nothing here computes anything. The placement rule is about layers, not
# transports (`docs/academy/10-where-a-thing-belongs.md`).
# ---------------------------------------------------------------------------

def _register_library() -> dict:
    """Register a prompt per skill and a resource per document.

    Returns what was registered, so a caller can see it rather than infer it.
    Silent on absence by design at the protocol level — a client simply lists no
    prompts — but `describe_library` says why, which is the part a person needs.
    """
    from metis_mcp import library

    ok, _ = library.available()
    if not ok:
        return {"prompts": 0, "resources": 0}

    from mcp.server.fastmcp.prompts import Prompt
    from mcp.server.fastmcp.resources import FileResource

    documents = library.documents()
    prompts = 0

    for doc in documents:
        mcp.add_resource(FileResource(
            uri=doc.uri, name=doc.name, description=doc.description,
            path=doc.path, mime_type="text/markdown"))

        if doc.kind != library.SKILL:
            continue

        # The body is read when the prompt is invoked, not now: a skill edited
        # while the server runs should not serve yesterday's procedure.
        def _skill_prompt(path=doc.path) -> str:
            return path.read_text()

        mcp.add_prompt(Prompt.from_function(
            _skill_prompt, name=doc.name, description=doc.description))
        prompts += 1

    return {"prompts": prompts, "resources": len(documents)}


_LIBRARY = _register_library()


# Transports FastMCP offers. `stdio` stays the default: it is what a local MCP
# client launches, and it is the only one that needs no network at all.
TRANSPORTS = ("stdio", "sse", "streamable-http")
TRANSPORT_ENV = "METIS_MCP_TRANSPORT"
HOST_ENV = "METIS_HTTP_HOST"
PORT_ENV = "METIS_HTTP_PORT"


# ---------------------------------------------------------------------------
# Authoring: how to call it, and how it works (X-6e).
#
# Read-only, so these belong here rather than in the write half — the surface at
# `METIS_MCP_WRITE=off` is read-only **by construction**, and a query that writes
# nothing has no business behind a write switch. (`read.get_transition` is behind
# one for historical reasons its own comment admits to.)
# ---------------------------------------------------------------------------
from metis_mcp import authoring as _authoring


def _wrap_read(fn):
    """Turn an unconfigured graph into an answer, the way every read tool does.

    **These five were registered bare and were the only tools on the surface
    that were not.** Every tool defined in this module catches
    `GraphNotConfigured` and returns `_NOT_CONFIGURED`; `_wrap_write` and
    `_wrap_execution` do the same for their groups. `call_recipe`, `auth_facts`,
    `payload_shape` and `journey_walkthrough` propagated a traceback instead, so
    a caller with no `METIS_NEO4J_*` configured got a stack trace where the rest
    of the surface tells them what to configure. `ask` worked around it for its
    own academy route (`authoring.py`) and documented the inconsistency as
    pre-existing; this removes the thing it was working around.

    They already return JSON strings, so there is nothing to serialise here —
    which is the one way this differs from `_wrap_write`.
    """
    import functools

    @functools.wraps(fn)
    def tool(*args, **kwargs) -> str:
        try:
            return fn(*args, **kwargs)
        except GraphNotConfigured as e:
            return _json(_no_graph(e))

    return tool


for _fn in (_authoring.call_recipe, _authoring.auth_facts,
            _authoring.payload_shape, _authoring.journey_walkthrough,
            _authoring.ask):
    mcp.tool()(_wrap_read(_fn))


# ---------------------------------------------------------------------------
# The write half (the change to N-8).
#
# Registered only when `METIS_MCP_WRITE` says so, and `off` is the default — so
# an unconfigured server is exactly the read-only surface it has always been,
# and the forty-four read-only tools are unchanged. Enabling writes is a deployment
# decision somebody makes, never a consequence of upgrading.
#
# The tools are registered here rather than in the modules so that this file
# stays the whole inventory of the TOOLS: `grep '@mcp.tool'` has to keep
# answering "what can an agent call", which is the question N-8 used to answer by
# construction and now answers by enumeration.
#
# It is no longer the whole inventory of the SURFACE. Prompts and resources are
# discovered rather than declared (see `_register_library`), so the enumeration
# of those lives in `docs/guide/mcp-tools.md`, which is generated and checked.
# ---------------------------------------------------------------------------

def _register_write_tools() -> list[str]:
    """Register the author group, and return what was registered."""
    from metis_mcp import policy

    if not policy.may_author():
        # **The import stays inside the branch, and that is the point.** With
        # writes off, `metis_mcp.write` is never imported, so no write path
        # is reachable from this module at all -- N-8 still holds *by
        # construction* for the default deployment, and `test_mcp_server.py`'s
        # subprocess check still proves it. Importing at the top and branching
        # here would have quietly turned that proof into a policy check.
        return []

    from metis_mcp import write

    registered = []
    for fn in (write.land_model, write.land_knowledge, write.land_findings,
               write.land_intake, write.persist_version,
               write.publication_drift, write.duplicate_check,
               write.land_executions, write.fetch_repository):
        mcp.tool()(_wrap_write(fn))
        registered.append(fn.__name__)

    # A read query, registered with the write group only because it did not
    # exist before this package did. It writes nothing.
    from metis_mcp import read

    mcp.tool()(_wrap_write(read.get_transition))
    registered.append(read.get_transition.__name__)

    from metis_mcp import flow

    for fn in (flow.run_workflow, flow.resume_workflow):
        mcp.tool()(_wrap_write(fn))
        registered.append(fn.__name__)

    if policy.may_decide():
        # `review_queue` rides with the gate group rather than with the read
        # tools on purpose: its whole output is the evidence for a decision, and
        # a surface that cannot decide would be handing out a fingerprint no
        # tool it exposes can spend.
        from metis_mcp import decide

        for fn in (decide.review_queue, decide.approve_elements,
                   decide.reject_elements, decide.defer_elements):
            mcp.tool()(_wrap_write(fn))
            registered.append(fn.__name__)
    return registered


def _wrap_write(fn):
    """Serialise like every read tool, and turn a refusal into an answer.

    A refused write is a *result* — "you are a contributor and may not approve"
    is information the caller can act on. Letting it propagate as an exception
    gives an agent a stack trace and no next step.
    """
    import functools

    from metis_mcp.policy import ConfirmationRefused, WriteDisabled
    from metis_mcp.review.roles import NotPermitted

    @functools.wraps(fn)
    def tool(*args, **kwargs) -> str:
        try:
            return _json(fn(*args, **kwargs))
        except (WriteDisabled, NotPermitted, ConfirmationRefused) as e:
            return _json({"ok": False, "refused": str(e),
                          "rule": type(e).__name__})
        except GraphNotConfigured as e:
            return _json(_no_graph(e))

    return tool


@mcp.tool()
def describe_policy() -> str:
    """What this surface may write, what it may not, and which gates apply.

    Replaces `why_read_only` when writes are enabled. Read it before assuming a
    write will work: the answer depends on deployment configuration, on the
    role you pass, and — for the two gates — on a literal word.
    """
    from metis_mcp import policy

    described = policy.describe()
    described["registered_write_tools"] = _WRITE_TOOLS
    return _json(described)


# ---------------------------------------------------------------------------
# Contact with the system under test (the change to X-7a).
#
# Registered only when `METIS_EXECUTE` says so, and `off` is the default — so an
# unconfigured server cannot reach the system it models, exactly as before. The
# import stays inside the branch for the same reason the write import does: at
# `off` the observer and runner modules are never loaded, which is what makes
# `test_execution.py`'s subprocess proof true rather than aspirational.
#
# `describe_execution` is registered unconditionally and is a READ. A caller has
# to be able to ask what this deployment may touch without the answer depending
# on whether it may touch anything — "nothing, and here is how to change that"
# is the most useful answer the tool can give.
# ---------------------------------------------------------------------------

@mcp.tool()
def describe_execution() -> str:
    """What this deployment may do to the system under test, and what it may not.

    X-7a used to say Métis never touches the system it models. It is now a tier
    — `off` (the default), `observe` (read a live system), `run` (also make
    something happen) — and this reports which is in force, which optional
    clients are installed, and what a run costs.

    A fact observed from a running system is never merged with one recovered
    from source: they are different claims (§8.7, C-11).
    """
    from metis_mcp import execution

    try:
        return _json(execution.describe())
    except execution.ExecutionDisabled as e:
        return _json({"ok": False, "refused": str(e)})


def _wrap_execution(fn):
    """Turn an execution refusal into an answer, the way `_wrap_write` does."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> str:
        from metis_mcp import execution

        try:
            return _json(fn(*args, **kwargs))
        except execution.ExecutionDisabled as e:
            return _json({"ok": False, "refused": str(e), "rule": "X-7a (tiered)"})
        except execution.CapabilityUnavailable as e:
            return _json({"ok": False, "refused": str(e), "rule": "optional extra"})
        except execution.ExecutionRefused as e:
            return _json({"ok": False, "refused": str(e), "rule": "run literal"})
        except Exception as e:                                   # noqa: BLE001
            return _json({"ok": False, "refused": f"{type(e).__name__}: {e}"})
    return wrapper


def _register_execution_tools() -> list[str]:
    """Register the observe group, then the run group. Returns what was added."""
    from metis_mcp import execution

    try:
        tier = execution.tier()
    except execution.ExecutionDisabled:
        return []
    if tier == execution.OFF:
        return []

    registered: list[str] = []

    from metis_mcp.observers import kube, sql

    for fn in (sql.query, kube.collect):
        mcp.tool()(_wrap_execution(fn))
        registered.append(fn.__name__)

    if execution.may_run():
        from metis_mcp.runners import load

        mcp.tool()(_wrap_execution(load.run_scenario))
        registered.append(load.run_scenario.__name__)
    return registered


# ---------------------------------------------------------------------------
# Writes that leave Métis (T-20).
#
# Behind the WRITE switch, not the execution one: filing a defect is not contact
# with the system under test, it is contact with the tracker that describes it.
# Each still needs `METIS_ALLOW_EXTERNAL_WRITES=yes` on the installation, checked
# inside the connector — so this registration makes them reachable, never
# permitted.
# ---------------------------------------------------------------------------

def _register_outward_tools() -> list[str]:
    from metis_mcp import policy

    if not policy.may_author():
        return []

    from metis_mcp import outward_tools

    registered = []
    for fn in (outward_tools.file_defect, outward_tools.open_merge_request,
               outward_tools.tracker_folder, outward_tools.tracker_cycle_add):
        mcp.tool()(_wrap_write(fn))
        registered.append(fn.__name__)
    return registered


_WRITE_TOOLS = _register_write_tools()
_EXECUTION_TOOLS = _register_execution_tools()
_OUTWARD_TOOLS = _register_outward_tools()


def main() -> None:
    """Serve the tools above, over stdio unless the environment says otherwise.

    **This used to be `mcp.run()` and nothing else, which made the container
    image undeliverable.** `Dockerfile.mcp-server` sets `ENV METIS_HTTP_PORT=8090`
    and `EXPOSE 8090`, and its `CMD` is this function — so a detached container
    published a port that nothing ever listened on, while the process sat waiting
    on a stdin no one was attached to. The Dockerfile was not wrong; it was
    describing an intent this function had never implemented.

    Read-only is unaffected (N-8). A transport changes who can reach the tools,
    not what they can do, and none of them writes.
    """
    transport = os.environ.get(TRANSPORT_ENV, "stdio").strip() or "stdio"
    if transport not in TRANSPORTS:
        # A halt, not a fallback to stdio: silently serving a transport the
        # operator did not ask for is how a container "starts fine" and is
        # unreachable, which is the failure this function just had.
        raise SystemExit(
            f"{TRANSPORT_ENV}={transport!r} is not one of {', '.join(TRANSPORTS)}."
        )

    if transport == "stdio":
        mcp.run()
        return

    host = os.environ.get(HOST_ENV, "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.environ.get(PORT_ENV, "8090"))
    if host not in ("127.0.0.1", "localhost", "::1"):
        # The same warning `review_ui.serve` prints, for the same reason and with
        # a different consequence: there is no authentication here either, and
        # while these tools cannot decide anything, they will read out every
        # requirement, criterion and specification in the graph to whoever asks.
        print(f"WARNING: binding {host}. This surface does not authenticate. It "
              f"cannot approve or publish (N-8), but it will read out the whole "
              f"knowledge graph to anyone who reaches it.", file=sys.stderr)
    mcp.settings.host = host
    mcp.settings.port = port
    print(f"metis MCP ({transport}) on {host}:{port}", file=sys.stderr)
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
