"""
Durable review state, separate from the model source (application spec I-14).

Three files, three owners:

    login-api.json          MODEL SOURCE   what a source emitted. Machine facts:
                                           structure, triggers, guards. Never
                                           written by review.
    login-api.review.json   REVIEW STATE   human facts: lifecycle decisions,
                                           resolved names, and the audit trail.
                                           Accumulates; append-only audit.
    review.json             DECISION FILE  transient, human-edited, discarded
                                           after apply.

This mirrors I-14's partition exactly: re-extraction replaces the source file and
**must not** touch the review file. Keeping lifecycle inside the source conflated
the two and meant a re-extraction silently discarded every decision.

It also fixes a real defect the earlier design produced: the review fingerprint
covered lifecycle, so applying a decision changed the fingerprint and a second
apply of the same file was refused. The fingerprint now covers **source
substance only**, so decisions bind to the evidence a reviewer actually read.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from metis_mcp.mbt.model import APPROVED, Model, State, Transition

STATE_VERSION = "metis.review-state/1"


def _bare(element_id: str, model_id: str) -> str:
    """Strip the graph's `<model>::` namespace prefix (spec I-2).

    Landing namespaces every element id by its model, because seven synthesised
    API models all call their initial state `Ready` and would otherwise MERGE
    onto one node. That prefix is a **storage** detail: it is a pure function of
    `model.id`, which this hash already covers.

    Leaving it in made the same model hash differently depending on whether it
    was read from its JSON source or from the graph -- so a workflow that
    extracted from a file and then resumed against the graph saw its own earlier
    stages as stale and refused to continue, reporting a change that had not
    happened.
    """
    prefix = f"{model_id}::"
    return element_id[len(prefix):] if element_id.startswith(prefix) else element_id


def source_fingerprint(model: Model) -> str:
    """Hash of the model's **source substance** -- deliberately excluding lifecycle.

    Covers what a reviewer reads and what a re-extraction could change: structure,
    triggers, guards, implementation status, and display names. Lifecycle is a
    human fact and is not part of the evidence a decision was made against.

    Ids are taken bare (see `_bare`), so one model has one fingerprint however it
    was loaded.
    """
    parts = [model.id]
    for sid in model.state_ids():
        s = model.states[sid]
        parts.append(
            f"S|{_bare(s.id, model.id)}|{s.name}|{s.surface}|{s.is_initial}")
    for tid in model.transition_ids():
        t = model.transitions[tid]
        parts.append(
            f"T|{_bare(t.id, model.id)}|{_bare(t.source, model.id)}|{t.trigger}"
            f"|{_bare(t.target, model.id)}|{t.guard}|{t.implementation_status}"
            # **What a generated test asserts is evidence.** These six fields were
            # the whole hash while `outcome_status` already reached `.statusCode()`
            # in an emitted artefact — so a re-extraction changing 201 to 200 moved
            # the fingerprint not at all, and an approval recorded against the old
            # response was applied silently to the new one. E-8/N-14's rule stops
            # holding exactly on the fields generation asserts, so those fields
            # have to be inside the evidence.
            #
            # `rendering.contract` names them: every fact with
            # `affects_artefact=True`, checked by `test_generation_contract`.
            f"|{t.outcome_status}|{t.response_body}|{','.join(t.media_types)}"
            f"|{json.dumps(list(t.inputs), sort_keys=True, default=str)}"
            # The ordered conditions, not the joined guard. If check 1
            # short-circuits, no fixture reaches check 3 without satisfying check
            # 1 first — so a reordering changes what a fixture must satisfy while
            # `guard` reads identically.
            f"|{json.dumps([asdict(c) for c in t.checks], sort_keys=True)}"
        )
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


@dataclass
class ElementState:
    lifecycle_state: str
    name: str | None = None
    decided_by: str = ""
    decided_at: str = ""
    rationale: str = ""


@dataclass
class ReviewState:
    """Human facts for one model. The audit list is append-only (spec N-15)."""

    version: str = STATE_VERSION
    model_id: str = ""
    source_fingerprint: str = ""
    states: dict[str, ElementState] = field(default_factory=dict)
    transitions: dict[str, ElementState] = field(default_factory=dict)
    audit: list[dict] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({
            "version": self.version,
            "model_id": self.model_id,
            "source_fingerprint": self.source_fingerprint,
            "_note": (
                "Human facts. Re-extraction replaces the model source file and "
                "MUST NOT touch this one (spec I-14/I-16)."
            ),
            "states": {k: asdict(v) for k, v in self.states.items()},
            "transitions": {k: asdict(v) for k, v in self.transitions.items()},
            "audit": self.audit,
        }, indent=2)

    @staticmethod
    def from_json(text: str) -> "ReviewState":
        data = json.loads(text)
        return ReviewState(
            version=data.get("version", STATE_VERSION),
            model_id=data.get("model_id", ""),
            source_fingerprint=data.get("source_fingerprint", ""),
            states={k: ElementState(**v) for k, v in data.get("states", {}).items()},
            transitions={k: ElementState(**v) for k, v in data.get("transitions", {}).items()},
            audit=list(data.get("audit", [])),
        )

    @staticmethod
    def load(path: str | Path) -> "ReviewState":
        p = Path(path)
        if not p.exists():
            return ReviewState()
        return ReviewState.from_json(p.read_text())

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())


def default_state_path(model_path: str | Path) -> Path:
    """`login-api.json` -> `login-api.review.json`."""
    p = Path(model_path)
    return p.with_suffix("").with_suffix(".review.json") if p.suffix else Path(f"{p}.review.json")


@dataclass
class OverlayResult:
    model: Model
    stale: bool
    recorded_fingerprint: str
    current_fingerprint: str
    applied: int = 0


def overlay(model: Model, state: ReviewState) -> OverlayResult:
    """Apply human facts onto a freshly-loaded source model.

    When the source has moved since the decisions were made, the overlay is
    reported **stale** and *not applied* -- spec E-8's staleness rule, and the
    same discipline as N-14: a decision made against different evidence is not
    silently carried forward.
    """
    current = source_fingerprint(model)
    recorded = state.source_fingerprint

    if recorded and recorded != current:
        return OverlayResult(model=model, stale=True,
                             recorded_fingerprint=recorded, current_fingerprint=current)

    # `replace`, never a re-construction naming fields one by one. This loop built
    # a fresh `State`/`Transition` from an enumerated list, so every field it did
    # not name fell back to the dataclass default and was lost the moment a
    # decision was applied: `outcome_status=200` came back `None` and `inputs`
    # came back empty.
    #
    # **That was invisible until the approval evidence widened.** The six fields
    # the enumeration happened to name were exactly the six `source_fingerprint`
    # hashed, so the mutilation never moved the hash. Now that the fingerprint
    # covers what a generated test asserts, `review apply` would record a hash
    # taken from a mutilated model and `generate` would compute it from an intact
    # one — they could never match, and every approval would be stale forever.
    #
    # `replace` preserves every field by construction, including ones added
    # later, which an enumeration cannot promise. `rendering/contract.py` names
    # the fields that must survive; `test_generation_contract` asserts they do.
    applied = 0
    for sid, element in state.states.items():
        existing = model.states.get(sid)
        if existing is None:
            continue
        model.states[sid] = replace(
            existing, name=element.name or existing.name,
            lifecycle_state=element.lifecycle_state)
        applied += 1
    for tid, element in state.transitions.items():
        existing = model.transitions.get(tid)
        if existing is None:
            continue
        # A transition's `name` is display data (D-8) and the review file records
        # it as null; only the decision is applied here.
        model.transitions[tid] = replace(
            existing, lifecycle_state=element.lifecycle_state)
        applied += 1

    return OverlayResult(model=model, stale=False, recorded_fingerprint=recorded,
                         current_fingerprint=current, applied=applied)


def record(state: ReviewState, model: Model, records: list) -> None:
    """Fold applied decisions into durable state and append to the audit.

    `records` are `decisions.AuditRecord`s. The audit is **appended, never
    rewritten** (spec N-15) -- a decision may be superseded, never edited away.
    """
    state.version = STATE_VERSION
    state.model_id = model.id
    state.source_fingerprint = source_fingerprint(model)

    for r in records:
        target = state.states if r.kind == "state" else state.transitions
        existing = target.get(r.element_id)
        target[r.element_id] = ElementState(
            lifecycle_state=r.to_state,
            name=(model.states[r.element_id].name
                  if r.kind == "state" and r.element_id in model.states
                  else (existing.name if existing else None)),
            decided_by=r.reviewer,
            decided_at=r.decided_at,
            rationale=r.rationale,
        )
        state.audit.append(asdict(r))


def summarise(state: ReviewState) -> str:
    approved = sum(1 for e in (*state.states.values(), *state.transitions.values())
                   if e.lifecycle_state == APPROVED)
    total = len(state.states) + len(state.transitions)
    return (f"{state.model_id}: {approved}/{total} decided elements approved, "
            f"{len(state.audit)} audit record(s), source {state.source_fingerprint}")
