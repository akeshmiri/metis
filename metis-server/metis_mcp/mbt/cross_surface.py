"""
Cross-surface linking: `INVOKES` (application spec §2.2.1; M-5a..M-5g,
A-12a..A-12c, A-17d).

`coverage.py` already knows how to *credit* an `INVOKES` link, and refuses to
credit one toward guard coverage (C-2). Nothing produced the links. This module
does: it proposes them, validates the rules around them, and turns M-5f's
divergences from a judgement into a query.

**Surfaces stay separate.** `login-ui` and `login-api` each keep their own states,
because the observable situations genuinely differ -- a screen is not a status
code (M-3). The relationship between them is an explicit edge, not a merge.

**M-5c is the rule that makes indirect coverage sound.** A UI transition may
carry a *local* guard -- client-side validation, enablement, a permission check in
the client -- and it may *inherit* the guard of the API transition it invokes. The
inherited one is a **reference**, never a copy. That is not tidiness: C-3 credits
a UI path with the API transition's coverage precisely because the guard is the
same object. Restate it and the two drift, and the credit becomes a guess.

**M-5g -- proposed by extraction, confirmed by a human**, like every other
cross-artefact link (F-7, X-18). Extraction proposes by matching the API call in
a UI handler to an endpoint and response discriminator; that match is evidence,
not a verdict.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from metis_mcp.mbt.model import IMPLEMENTED, Model

# M-5f finding kinds. Each is a *pattern*, so the finding is a query result
# rather than someone's reading of two diagrams side by side.
API_ONLY = "api_only"
DANGLING_INVOKES = "dangling_invokes"
UNHANDLED_OUTCOME = "unhandled_outcome"
RESTATED_GUARD = "restated_guard"

UI = "ui"
API = "api"


class LinkRefused(ValueError):
    """Raised when an `INVOKES` link cannot be recorded as stated."""


@dataclass(frozen=True)
class InvokesLink:
    """`Transition(ui) -[:INVOKES]-> Transition(api)` (spec M-5a).

    Many-to-one (M-5e): the same API transition may be invoked from several
    screens, and that is normal rather than a duplicate.
    """

    ui_transition_id: str
    api_transition_id: str
    proposed_by: str
    evidence: dict = field(default_factory=dict)
    confirmed_by: str = ""

    @property
    def is_confirmed(self) -> bool:
        """M-5g. An unconfirmed link is a proposal and is not acted on."""
        return bool(self.confirmed_by.strip())


@dataclass
class LinkSet:
    """All proposed and confirmed links between one journey's two surfaces."""

    journey: str
    links: list[InvokesLink] = field(default_factory=list)
    # What a UI action **starts** (M-5a's `TRIGGERS`), kept separate from what it
    # **observed** (`INVOKES`). Same record shape, different claim — and a
    # different cardinality: a trigger fans out, an observation is one-to-one.
    triggers: list[InvokesLink] = field(default_factory=list)

    def confirmed(self) -> list[InvokesLink]:
        return [l for l in self.links if l.is_confirmed]

    def confirmed_triggers(self) -> list[InvokesLink]:
        return [l for l in self.triggers if l.is_confirmed]

    def triggered_map(self, confirmed_only: bool = True) -> dict[str, list[str]]:
        """`{ui_transition_id: [api_transition_id, ...]}` — **all** of them.

        A dict of lists rather than a dict, because a page opening three panels
        starts three calls. Storing this in the one-to-one `as_map` shape kept
        one and silently dropped the rest.
        """
        source = self.confirmed_triggers() if confirmed_only else self.triggers
        out: dict[str, list[str]] = {}
        for link in source:
            out.setdefault(link.ui_transition_id, []).append(link.api_transition_id)
        return out

    def triggered_api_ids(self, confirmed_only: bool = True) -> set[str]:
        return {i for ids in self.triggered_map(confirmed_only).values() for i in ids}

    def as_map(self, confirmed_only: bool = True) -> dict[str, str]:
        """The `{ui_transition_id: api_transition_id}` shape `coverage.credit_indirect`
        expects.

        Defaults to confirmed links only. Crediting coverage from an unconfirmed
        proposal would let a matching heuristic silently raise a coverage figure --
        the failure X-17 names for AC matching, in a different costume.
        """
        source = self.confirmed() if confirmed_only else self.links
        return {l.ui_transition_id: l.api_transition_id for l in source}

    def invoked_api_ids(self, confirmed_only: bool = True) -> set[str]:
        return set(self.as_map(confirmed_only).values())


def confirm_link(link: InvokesLink, confirmed_by: str) -> InvokesLink:
    """Record a human decision on a proposed link (spec M-5g)."""
    if not confirmed_by.strip():
        raise LinkRefused("a confirmation records who made it (N-13)")
    return InvokesLink(
        ui_transition_id=link.ui_transition_id,
        api_transition_id=link.api_transition_id,
        proposed_by=link.proposed_by, evidence=dict(link.evidence),
        confirmed_by=confirmed_by,
    )


# --------------------------------------------------------------------------
# M-5b : one UI transition per API outcome
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ProposedUiTransition:
    """One branch of a UI trigger, mirroring one API outcome (spec M-5b)."""

    ui_transition_id: str
    source_state: str
    trigger: str
    target_state: str
    api_transition_id: str
    local_guard: str = ""

    @property
    def has_local_guard(self) -> bool:
        return bool(self.local_guard.strip())


def plan_ui_transitions(api_model: Model, *, source_state: str, trigger: str,
                        api_trigger: str, api_source_state: str,
                        target_for: dict[str, str],
                        local_guard: str = "") -> list[ProposedUiTransition]:
    """One UI transition per API outcome (spec M-5b, A-12b).

    The click itself has **no guard of its own**; its branching is determined by
    the API's guards. `local_guard` is for genuinely client-side conditions and
    is applied identically to every branch -- a client-side check happens before
    any call, so it cannot distinguish between API outcomes.

    `target_for` maps an API transition id to the UI state that renders it. An
    API outcome with no entry is **omitted and reported** by `divergences` as an
    unhandled outcome, never given an invented screen.
    """
    outcomes = [t for t in api_model.transitions.values()
                if t.source == api_source_state and t.trigger == api_trigger
                and t.implementation_status == IMPLEMENTED]
    proposed = []
    for api_transition in sorted(outcomes, key=lambda t: t.id):
        target = target_for.get(api_transition.id)
        if target is None:
            continue
        proposed.append(ProposedUiTransition(
            ui_transition_id=f"{source_state}::{trigger}::{api_transition.id}",
            source_state=source_state, trigger=trigger, target_state=target,
            api_transition_id=api_transition.id, local_guard=local_guard,
        ))
    return proposed


# --------------------------------------------------------------------------
# M-5c : inherited guards are referenced, never restated
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class EffectiveGuard:
    """A UI transition's two guard kinds, kept distinct (spec M-5c)."""

    local: str
    inherited_from: str
    inherited: str

    def render(self) -> str:
        """For display only. The inherited part is resolved at read time, so this
        string is derived rather than stored -- which is what stops the two
        drifting apart."""
        parts = [p for p in (self.local, self.inherited) if p]
        return " AND ".join(parts)


def effective_guard(ui_local_guard: str, link: InvokesLink | None,
                    api_model: Model) -> EffectiveGuard:
    """Resolve an inherited guard **through the link**, never from a copy.

    A UI transition with no `INVOKES` link never reaches the API (M-5d), so it
    has a local guard and no inherited one. The absence is meaningful, not
    missing data.
    """
    if link is None:
        return EffectiveGuard(local=ui_local_guard, inherited_from="", inherited="")
    api_transition = api_model.transitions.get(link.api_transition_id)
    if api_transition is None:
        return EffectiveGuard(local=ui_local_guard,
                              inherited_from=link.api_transition_id, inherited="")
    return EffectiveGuard(local=ui_local_guard,
                          inherited_from=link.api_transition_id,
                          inherited=api_transition.guard)


def inherited_guards(api_model: Model, links: LinkSet,
                     confirmed_only: bool = True) -> dict[str, str]:
    """`{ui_transition_id: the API guard it inherits}` (spec M-5c).

    Feed this to `validation.validate(..., inherited=...)`. Without it a UI model
    reads as ambiguous precisely where the API side determines it: two
    transitions on one trigger, both locally unguarded, whose real guards are
    `t.isEmpty()` and its negation on the other surface. That is not a modelling
    defect -- it is M-5c working, and the validator simply could not see across
    the link.

    Confirmed links only by default, for the same reason `as_map` defaults that
    way: an unconfirmed proposal must not quietly make a model look well-formed.
    """
    out: dict[str, str] = {}
    for ui_id, api_id in links.as_map(confirmed_only).items():
        api_transition = api_model.transitions.get(api_id)
        if api_transition is not None and api_transition.guard.strip():
            out[ui_id] = api_transition.guard.strip()
    return out


def check_restatement(ui_model: Model, api_model: Model, links: LinkSet
                      ) -> list["Divergence"]:
    """Catch a UI guard that *copies* the API guard instead of referencing it
    (spec M-5c, A-12c).

    A stored copy is indistinguishable from a reference until the API guard
    changes, at which point the UI silently asserts the old condition and every
    indirect coverage credit built on it becomes false. Detected by literal
    containment: no interpretation, and none needed.
    """
    findings = []
    for link in links.links:
        ui = ui_model.transitions.get(link.ui_transition_id)
        api = api_model.transitions.get(link.api_transition_id)
        if ui is None or api is None or not api.guard.strip():
            continue
        if api.guard.strip() and api.guard.strip() in ui.guard:
            findings.append(Divergence(
                kind=RESTATED_GUARD, element_id=link.ui_transition_id,
                counterpart_id=link.api_transition_id,
                detail=(f"the UI guard restates the API guard {api.guard!r} instead "
                        f"of referencing it. A copy cannot be kept in step, and "
                        f"C-3's indirect credit assumes they are the same "
                        f"condition (M-5c)"),
                remedy="carry only the local guard on the UI transition; the "
                       "inherited one resolves through INVOKES",
            ))
    return findings


# --------------------------------------------------------------------------
# M-5f : divergence becomes computable
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Divergence:
    kind: str
    element_id: str
    counterpart_id: str
    detail: str
    remedy: str = ""

    def describe(self) -> str:
        return f"[{self.kind}] {self.element_id}: {self.detail}"


def divergences(ui_model: Model, api_model: Model, links: LinkSet,
                confirmed_only: bool = True) -> list[Divergence]:
    """M-5f's three patterns, as queries rather than judgements.

    **A-17d is enforced by omission and stated here so it stays that way**: a
    UI-only transition -- client-side validation, navigation, a display toggle --
    has no `INVOKES` by design (M-5d) and is *never* reported as a gap against the
    API model. Only the API side is checked for missing links.
    """
    findings: list[Divergence] = []
    invoked = links.invoked_api_ids(confirmed_only)

    # API-only: reachable by a client but never exposed through the UI.
    for tid in api_model.transition_ids():
        transition = api_model.transitions[tid]
        if (transition.implementation_status != IMPLEMENTED
                or tid in invoked
                or tid in links.triggered_api_ids(confirmed_only)):
            # A triggered-but-unobserved call is not API-only — the UI does reach
            # it. That is the unhandled-outcome finding below, and reporting both
            # would double-count one problem as two.
            continue
        findings.append(Divergence(
            kind=API_ONLY, element_id=tid, counterpart_id="",
            detail=(f"{transition.source} --[{transition.trigger}]--> "
                    f"{transition.target}: no UI transition invokes it. Reachable "
                    f"by a client, never exposed through the UI — frequently a real "
                    f"security or completeness gap (M-5f)"),
            remedy="confirm it is intentionally API-only; it needs DIRECT coverage "
                   "either way, since no UI path can ever credit it (C-4)",
        ))

    # Dangling: the UI drives an endpoint the API model no longer has.
    for link in links.links:
        if link.api_transition_id not in api_model.transitions:
            findings.append(Divergence(
                kind=DANGLING_INVOKES, element_id=link.ui_transition_id,
                counterpart_id=link.api_transition_id,
                detail=(f"invokes {link.api_transition_id}, which is not in the API "
                        f"model any more"),
                remedy="re-extract the API surface, or retire the UI transition"))

    # Unhandled outcome: the UI *starts* this call and can never render this
    # result. **This is a direct query, and only a direct query.** It used to be
    # inferred from a same-trigger heuristic over the invokes map, because one
    # edge type could not distinguish "the UI starts this flow" from "the UI
    # rendered this outcome". With `TRIGGERS` separate, the question is exactly:
    #
    #     triggered by some UiAction, and observed by none.
    #
    # That heuristic was kept for a while as a fallback for journeys whose links
    # predated the split, and it is gone: it reported a finding derived from the
    # very conflation `TRIGGERS` exists to remove, without saying that was where
    # the finding came from. A journey with no `TRIGGERS` recorded now reports
    # nothing here, which is what re-extraction fixes.
    triggered = links.triggered_api_ids(confirmed_only)
    reverse: dict[str, list[str]] = {}
    for ui_id, api_id in links.as_map(confirmed_only).items():
        reverse.setdefault(api_id, []).append(ui_id)

    for tid in api_model.transition_ids():
        api_transition = api_model.transitions[tid]
        if api_transition.implementation_status != IMPLEMENTED or tid in reverse:
            continue
        if tid in triggered:
            findings.append(Divergence(
                kind=UNHANDLED_OUTCOME, element_id=tid, counterpart_id="",
                detail=(f"the UI starts {api_transition.trigger!r} but has no "
                        f"transition for the {api_transition.target} outcome — the "
                        f"call is made and this result can never be rendered (M-5f)"),
                remedy="add the UI transition that renders this outcome (M-5b), or "
                       "confirm the outcome is genuinely unreachable from the UI"))

    findings.extend(check_restatement(ui_model, api_model, links))
    return findings


# Triage outcomes for an API-only finding (M-5f, C-4).
CONSUMED_ELSEWHERE = "consumed_elsewhere"
NO_KNOWN_CONSUMER = "no_known_consumer"


@dataclass(frozen=True)
class Triage:
    finding: "Divergence"
    outcome: str
    consumer: str = ""

    @property
    def needs_attention(self) -> bool:
        return self.outcome == NO_KNOWN_CONSUMER


def triage_api_only(findings: list["Divergence"], model: Model,
                    consumers: dict[str, str]) -> list[Triage]:
    """Separate "no UI calls it" from "nothing calls it" (spec M-5f, C-4).

    **These are different findings and merging them buries the real one.** An
    endpoint with no inbound `INVOKES` is API-only by definition, but an estate
    that ships feign clients and CLIs consumes many endpoints machine-to-machine
    on purpose. On the the pilot estate estate 83 of 86 API-only endpoints turned out to be
    declared by a feign client -- so the three that are not are the finding, and
    reporting all 86 with equal weight would have hidden them.

    `consumers` maps a path to the module that declares it. C-4 still holds for
    every one of them: no UI path can ever credit an API-only transition, so they
    all need DIRECT coverage. What changes is who acts on it, and why.
    """
    out = []
    for finding in findings:
        if finding.kind != API_ONLY:
            continue
        transition = model.transitions.get(finding.element_id)
        if transition is None:
            continue
        parts = transition.trigger.split(None, 1)
        path = parts[1] if len(parts) > 1 else ""
        # The gateway strips the service prefix, and controllers are dual-mounted
        # on both `""` and `/<service>` -- so a consumer may declare EITHER form,
        # and the model may carry either. Both directions must be tried.
        #
        # Trying only the stripping direction reported `RecordController.getById`
        # and `.save` as having no consumer at all, when `MetricFeignClient`
        # declares `GET /metric/{id}` and `POST /metric` outright. Three false
        # findings, caught by checking the feign interface rather than trusting
        # the lookup.
        # `<journey>-<surface>` (M-1). Only the surface comes off — the old
        # form also stripped a company prefix, which silently renamed the journey of
        # every model belonging to anyone else.
        service = re.sub(r"-api$", "", model.id)
        candidates = [path,
                      re.sub(r"^/[a-z]+", "", path, count=1) or "/",
                      f"/{service}{path}".rstrip("/") or f"/{service}",
                      f"/{service}"]
        consumer = next((consumers[c] for c in candidates if c in consumers), "")
        out.append(Triage(
            finding=finding,
            outcome=CONSUMED_ELSEWHERE if consumer else NO_KNOWN_CONSUMER,
            consumer=consumer))
    return out


def format_triage(triaged: list[Triage]) -> str:
    unattended = [t for t in triaged if t.needs_attention]
    consumed = [t for t in triaged if not t.needs_attention]
    lines = [f"API-only triage — {len(triaged)} finding(s)",
             f"  consumed elsewhere (feign/CLI/client): {len(consumed)}",
             f"  NO KNOWN CONSUMER:                     {len(unattended)}"]
    if unattended:
        lines += ["", "  Nothing in this estate is known to call these:"]
        for t in unattended:
            lines.append(f"    {t.finding.element_id[:80]}")
    lines += ["",
              "  Every one of them still needs DIRECT coverage: no UI path can ever",
              "  credit an API-only transition (C-4). Triage changes who acts, not",
              "  whether it is covered."]
    return "\n".join(lines)


def format_divergences(findings: list[Divergence]) -> str:
    if not findings:
        return "No cross-surface divergences."
    lines = [f"Cross-surface divergences — {len(findings)}"]
    for kind, title in ((API_ONLY, "API-ONLY BEHAVIOUR"),
                        (DANGLING_INVOKES, "DANGLING INVOKES"),
                        (UNHANDLED_OUTCOME, "UNHANDLED OUTCOME"),
                        (RESTATED_GUARD, "RESTATED GUARD")):
        group = [f for f in findings if f.kind == kind]
        if not group:
            continue
        lines += ["", f"  {title}  ({len(group)})"]
        for finding in group[:8]:
            lines.append(f"    {finding.element_id}: {finding.detail}")
            if finding.remedy:
                lines.append(f"        -> {finding.remedy}")
    lines += ["",
              "  A UI-only transition is NOT listed here: client-side validation, "
              "navigation",
              "  and display toggles have no INVOKES by design (M-5d, A-17d)."]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------

# `confirmed_by` is a HUMAN fact: **an empty value never clears a real one.**
#
# It was in the unconditional SET, so re-running the proposal step — which passes
# an empty `confirmed_by`, because a fresh proposal has no confirmation —
# **wiped every confirmation that existed**. Silently, and on a step whose whole
# purpose is to be re-runnable.
#
# `ON CREATE SET` is the wrong fix here, because confirming travels through this
# same statement (`persist_invokes(..., confirmed_only=True)`) and would then
# never write. The condition below serves both callers: a proposal leaves an
# existing confirmation alone, and a confirmation always lands.
INVOKES_CYPHER = """
MATCH (ui:Transition|ApiCall|UiAction {id: $ui_id})
MATCH (api:Transition|ApiCall|UiAction {id: $api_id})
MERGE (ui)-[r:INVOKES]->(api)
SET r.proposed_by = $proposed_by,
    r.evidence = $evidence,
    r.confirmed_by = CASE WHEN $confirmed_by <> ''
                          THEN $confirmed_by
                          ELSE coalesce(r.confirmed_by, '') END
"""

# Same shape, different claim: this interaction *starts* that flow.
TRIGGERS_CYPHER = INVOKES_CYPHER.replace("[r:INVOKES]", "[r:TRIGGERS]")


def plan_invokes_writes(links: LinkSet, confirmed_only: bool = True) -> list[dict]:
    """Parameters for the `INVOKES` MERGE, one per link. **Pure.**

    `MERGE` rather than `CREATE`, for the reason this codebase already
    standardised on: a bare `CREATE` on a pre-computed identity is not safe
    against a driver-level transaction retry.
    """
    source = links.confirmed() if confirmed_only else links.links
    return [{
        "ui_id": link.ui_transition_id,
        "api_id": link.api_transition_id,
        "proposed_by": link.proposed_by,
        "confirmed_by": link.confirmed_by,
        "evidence": sorted(f"{k}={v}" for k, v in link.evidence.items()),
    } for link in sorted(source, key=lambda l: (l.ui_transition_id, l.api_transition_id))]


def persist_triggers(session, links: LinkSet,
                     confirmed_only: bool = True) -> tuple[int, list[tuple[str, str]]]:
    """Write the `TRIGGERS` edges. Same honesty about what actually landed."""
    return _persist(session, TRIGGERS_CYPHER,
                    links.confirmed_triggers() if confirmed_only else links.triggers,
                    "TRIGGERS")


def persist_invokes(session, links: LinkSet,
                    confirmed_only: bool = True) -> tuple[int, list[tuple[str, str]]]:
    """Write the links. Confirmed only by default (M-5g).

    Returns `(written, unmatched)` — and the second half is the point.

    **It used to count rows it planned, not writes it made.** `INVOKES_CYPHER`
    opens with two `MATCH`es; if either transition id is absent the statement
    matches nothing and merges nothing, and the old counter incremented anyway.
    That is how a rebuild reported "91 INVOKES proposal(s)" into a graph holding
    zero of them: the UI transition ids had changed under a new synthesiser, and
    every single link silently referred to a transition that no longer existed.

    A write path that cannot tell success from silence will always eventually
    report the wrong number, so this asks the database what it did.
    """
    return _persist(session, INVOKES_CYPHER,
                    links.confirmed() if confirmed_only else links.links, "INVOKES")


def _persist(session, cypher: str, source, rel_type: str
             ) -> tuple[int, list[tuple[str, str]]]:
    written = 0
    unmatched: list[tuple[str, str]] = []
    for params in [{"ui_id": l.ui_transition_id, "api_id": l.api_transition_id,
                    "proposed_by": l.proposed_by, "confirmed_by": l.confirmed_by,
                    "evidence": ", ".join(f"{k}={v}" for k, v in sorted(l.evidence.items()))}
                   for l in source]:
        result = session.run(cypher, **params)
        summary = getattr(result, "consume", lambda: None)()
        counters = getattr(summary, "counters", None)
        created = getattr(counters, "relationships_created", None)
        if created is None:
            # A stub session with no counters: fall back to the planned count
            # rather than reporting zero, and do not claim to have verified it.
            written += 1
            continue
        if created or _edge_exists(session, params, rel_type):
            written += 1
        else:
            unmatched.append((params["ui_id"], params["api_id"]))
    return written, unmatched


def _edge_exists(session, params: dict, rel_type: str = "INVOKES") -> bool:
    """Whether the MERGE landed on an edge that was already there.

    `relationships_created` is 0 both when nothing matched and when the edge
    already existed. Only the second is a success, so the two are told apart
    rather than guessed at.
    """
    rows = list(session.run(
        f"MATCH (:Transition|ApiCall|UiAction {{id:$ui_id}})-[r:{rel_type}]->(:Transition|ApiCall|UiAction {{id:$api_id}}) "
        f"RETURN count(r) AS n", ui_id=params["ui_id"], api_id=params["api_id"]))
    return bool(rows and rows[0]["n"])
