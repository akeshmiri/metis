"""
Model manipulation as a first-class operation (application spec §17, A-52..A-58).

The model will sometimes be wrong. Extraction is not sound (§5.8), and intended
behaviour sometimes differs from implemented behaviour. Editing is therefore
**an operation with its own discipline**, not an escape hatch bolted on later.

The shape follows I-14's partition, which the rest of this codebase already
respects: a source file holds machine facts, and human facts live beside it. An
override is a **third** kind of human fact, distinct from the lifecycle decisions
and resolved names `review/state.py` keeps:

    login-api.json            MODEL SOURCE     what a source emitted
    login-api.review.json     REVIEW STATE     lifecycle decisions, resolved names
    login-api.overrides.json  OVERRIDE LOG     structural and property edits

**E-1** is the rule the whole module turns on: an override is a fact *layered on*
an element, never a mutation *of* it. The source file is never edited. That is
what lets re-extraction replace machine facts underneath an override while the
override keeps applying (E-7) -- and what makes staleness detectable at all,
since the override still carries the machine value it was made against.

**E-4/E-5 -- the classification is the point of the module.** Every edit states
what it asserts: `extraction_error` (the extractor got this wrong; the code is
fine) or `intended_divergence` (the code is wrong, or intent differs). Without
that distinction every correction looks alike, and neither "our extraction is
unreliable" nor "we found a defect" can be measured. They produce findings
against **different targets**, and the module refuses an unclassified edit.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from metis_mcp.mbt.model import (
    APPROVED,
    IMPLEMENTED,
    QUARANTINE,
    Model,
    State,
    Transition,
)

LOG_VERSION = "metis.override-log/1"

# Operations (spec E-3). Splitting and merging states are composed from these,
# not primitives -- a split is a remove plus two adds, and recording it that way
# keeps every step individually classified and individually reviewable.
ADD = "add"
REMOVE = "remove"
MODIFY = "modify"
OPERATIONS = (ADD, REMOVE, MODIFY)

# Classifications (spec E-4).
EXTRACTION_ERROR = "extraction_error"
INTENDED_DIVERGENCE = "intended_divergence"
CLASSIFICATIONS = (EXTRACTION_ERROR, INTENDED_DIVERGENCE)

# Finding targets (spec E-5). The two classes point at different people.
TARGET_METIS = "metis"
TARGET_PRODUCT = "product"

# Properties an override may modify (spec E-3).
TRANSITION_PROPERTIES = ("source", "trigger", "target", "guard", "implementation_status")
STATE_PROPERTIES = ("name", "surface", "is_initial")

# Modifying one of these moves the element's natural key (spec I-2), so the edit
# is a rename in identity terms rather than an attribute change. Permitted --
# E-3 names `target` explicitly -- but never silently, see `changes_identity`.
IDENTITY_PROPERTIES = ("source", "trigger", "target")

STATE = "state"
TRANSITION = "transition"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class OverrideRefused(ValueError):
    """Raised when an edit cannot be recorded as stated."""


@dataclass(frozen=True)
class Override:
    """One human edit (spec E-2).

    Every field in E-2's list is required rather than optional, `rationale` and
    `classification` included. An unexplained edit is indistinguishable from a
    mistake six months later, and an unclassified one destroys the only
    measurement §17 exists to produce.

    `previous_value` is the **machine** value at the time of the edit, not the
    prior override. It is what makes E-8's staleness check possible: when
    re-extraction moves the underlying value away from it, the evidence this
    edit was made against no longer holds.
    """

    element_kind: str
    element_id: str
    operation: str
    author: str
    rationale: str
    classification: str
    prop: str = ""
    previous_value: str | None = None
    new_value: str | None = None
    payload: dict = field(default_factory=dict)
    recorded_at: str = ""

    @property
    def changes_identity(self) -> bool:
        """Whether this edit moves the element's natural key (spec I-2)."""
        return (self.operation == MODIFY
                and self.element_kind == TRANSITION
                and self.prop in IDENTITY_PROPERTIES)

    @property
    def finding_target(self) -> str:
        """Which side the finding is against (spec E-5)."""
        return TARGET_METIS if self.classification == EXTRACTION_ERROR else TARGET_PRODUCT

    def describe(self) -> str:
        if self.operation == MODIFY:
            return (f"{self.element_id}.{self.prop}: "
                    f"{self.previous_value!r} -> {self.new_value!r}")
        if self.operation == REMOVE:
            return f"{self.element_id}: removed"
        return f"{self.element_id}: added"


@dataclass
class OverrideLog:
    """Append-only (spec N-15). An override may be superseded, never edited away."""

    version: str = LOG_VERSION
    model_id: str = ""
    entries: list[Override] = field(default_factory=list)

    def append(self, override: Override) -> None:
        self.entries.append(override)

    def for_element(self, element_id: str) -> list[Override]:
        return [o for o in self.entries if o.element_id == element_id]

    def overridden_ids(self) -> set[str]:
        return {o.element_id for o in self.entries}

    def to_json(self) -> str:
        return json.dumps({
            "version": self.version,
            "model_id": self.model_id,
            "_note": (
                "Human edits, layered on the model source (spec E-1). "
                "Re-extraction replaces the source file and MUST NOT touch this "
                "one (E-7). Append-only: supersede an entry, never edit it (N-15)."
            ),
            "entries": [asdict(o) for o in self.entries],
        }, indent=2)

    @staticmethod
    def from_json(text: str) -> "OverrideLog":
        data = json.loads(text)
        return OverrideLog(
            version=data.get("version", LOG_VERSION),
            model_id=data.get("model_id", ""),
            entries=[Override(**e) for e in data.get("entries", [])],
        )

    @staticmethod
    def load(path: str | Path) -> "OverrideLog":
        p = Path(path)
        return OverrideLog.from_json(p.read_text()) if p.exists() else OverrideLog()

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())


def default_log_path(model_path: str | Path) -> Path:
    """`login-api.json` -> `login-api.overrides.json`."""
    p = Path(model_path)
    return (p.with_suffix("").with_suffix(".overrides.json") if p.suffix
            else Path(f"{p}.overrides.json"))


# --------------------------------------------------------------------------
# Reading the current machine value
# --------------------------------------------------------------------------

def current_value(model: Model, kind: str, element_id: str, prop: str) -> str | None:
    """The model's present value for a property, as a string, or None if absent."""
    holder = model.states if kind == STATE else model.transitions
    element = holder.get(element_id)
    if element is None:
        return None
    if not hasattr(element, prop):
        return None
    return str(getattr(element, prop))


# --------------------------------------------------------------------------
# Planning an edit -- pure, refuses rather than repairs
# --------------------------------------------------------------------------

def plan_override(model: Model, *, kind: str, element_id: str, operation: str,
                  author: str, rationale: str, classification: str,
                  prop: str = "", new_value: str | None = None,
                  payload: dict | None = None,
                  machine: Model | None = None) -> Override:
    """Validate an edit against the model and return it **unapplied** (spec E-11).

    Refuses rather than repairs, per F-9. In particular it refuses an edit whose
    stated property does not exist on that element kind: silently accepting one
    would write an override that can never apply and never be seen to fail.

    `previous_value` is read here rather than accepted from the caller, so an
    override cannot claim it was made against evidence that was never on screen.

    `machine` is the model **as a source emitted it**, and is where
    `previous_value` is read from when it differs from `model` -- which it does
    whenever earlier overrides are already layered on. This distinction is
    load-bearing for E-8: if a second edit to the same property recorded the
    first edit's value as "previously extracted", every staleness check would
    compare an override against itself and report stale forever. Supersession is
    log order (N-15), never a chain of previous values.

    An element that exists only because an override added it has no machine value
    at all; `previous_value` is then None, which is the honest answer.
    """
    if kind not in (STATE, TRANSITION):
        raise OverrideRefused(f"unknown element kind {kind!r}")
    if operation not in OPERATIONS:
        raise OverrideRefused(f"unknown operation {operation!r}; expected one of {OPERATIONS}")
    if not author.strip():
        raise OverrideRefused("an override records who made it (spec E-2)")
    if not rationale.strip():
        raise OverrideRefused(
            "an override requires a rationale; it is required, not optional (spec E-2)")
    if classification not in CLASSIFICATIONS:
        raise OverrideRefused(
            f"classify the edit as one of {CLASSIFICATIONS} (spec E-4). "
            f"Without it, 'our extraction is unreliable' and 'we found a defect' "
            f"become the same record and neither can be measured (E-5)")

    holder = model.states if kind == STATE else model.transitions
    exists = element_id in holder

    if operation == ADD:
        if exists:
            raise OverrideRefused(
                f"{element_id} already exists; use {MODIFY!r}, or remove it first")
        if not payload:
            raise OverrideRefused(f"an {ADD} override must carry the element's properties")
        return Override(element_kind=kind, element_id=element_id, operation=ADD,
                        author=author, rationale=rationale, classification=classification,
                        payload=dict(payload), recorded_at=_now())

    if not exists:
        raise OverrideRefused(f"{element_id} is not in this model")

    if operation == REMOVE:
        return Override(element_kind=kind, element_id=element_id, operation=REMOVE,
                        author=author, rationale=rationale, classification=classification,
                        recorded_at=_now())

    allowed = STATE_PROPERTIES if kind == STATE else TRANSITION_PROPERTIES
    if prop not in allowed:
        raise OverrideRefused(f"{prop!r} is not an editable property of a {kind}; "
                              f"expected one of {allowed}")
    if new_value is None:
        raise OverrideRefused(f"a {MODIFY} override needs a new value")

    # `previous_value` is the machine value; `effective` is what the reviewer is
    # actually looking at once earlier edits are layered on. The no-change check
    # uses the latter -- refusing an edit that changes nothing *visible* -- while
    # the record keeps the former, so E-8 stays meaningful.
    source = machine if machine is not None else model
    previous = current_value(source, kind, element_id, prop)
    effective = current_value(model, kind, element_id, prop)
    if str(new_value) == str(effective):
        raise OverrideRefused(
            f"{element_id}.{prop} is already {effective!r}; an override that changes "
            f"nothing would still quarantine the element (E-11) for no reason")

    return Override(element_kind=kind, element_id=element_id, operation=MODIFY,
                    author=author, rationale=rationale, classification=classification,
                    prop=prop, previous_value=previous, new_value=str(new_value),
                    recorded_at=_now())


# --------------------------------------------------------------------------
# Staleness (spec E-8, E-9)
# --------------------------------------------------------------------------

@dataclass
class Staleness:
    override: Override
    was_extracted: str | None
    now_extracted: str | None

    @property
    def code_now_agrees(self) -> bool:
        """The underlying value moved to match the override.

        Reported, never acted on. E-9 is explicit that a stale override is not
        auto-resolved *even here*: someone confirms the divergence is closed.
        Auto-resolving would quietly delete the record that a defect existed.
        """
        return self.now_extracted == self.override.new_value

    def describe(self) -> str:
        agree = "  <- code now agrees with you" if self.code_now_agrees else ""
        return (f"STALE OVERRIDE  {self.override.element_id} / {self.override.prop}\n"
                f"  your value      {self.override.new_value}"
                f"   ({self.override.author}, {self.override.recorded_at[:10]}, "
                f"{self.override.rationale!r})\n"
                f"  was extracted   {self.was_extracted}\n"
                f"  now extracted   {self.now_extracted}{agree}\n"
                f"  -> resolve: keep override | drop as resolved | re-classify")


def check_staleness(model: Model, log: OverrideLog) -> list[Staleness]:
    """Which overrides were made against evidence that has since moved (spec E-8).

    Only `modify` overrides can go stale: they are the only ones carrying a prior
    machine value to compare against. An `add` whose element now exists in the
    source, or a `remove` whose element has gone, is handled in `apply` as a
    no-op with a note rather than as staleness -- the edit's intent was reached,
    which is a different fact from its evidence changing underneath it.
    """
    stale: list[Staleness] = []
    for override in log.entries:
        if override.operation != MODIFY:
            continue
        now = current_value(model, override.element_kind, override.element_id,
                            override.prop)
        if now != override.previous_value:
            stale.append(Staleness(override=override, was_extracted=override.previous_value,
                                   now_extracted=now))
    return stale


# --------------------------------------------------------------------------
# Applying -- layering, never mutating the source
# --------------------------------------------------------------------------

@dataclass
class ApplyResult:
    model: Model
    applied: list[Override] = field(default_factory=list)
    no_ops: list[str] = field(default_factory=list)
    stale: list[Staleness] = field(default_factory=list)
    quarantined: list[str] = field(default_factory=list)
    revalidated_groups: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    authors: dict[str, str] = field(default_factory=dict)


def _with_state(state: State, **changes) -> State:
    fields = {"id": state.id, "name": state.name, "surface": state.surface,
              "is_initial": state.is_initial, "lifecycle_state": state.lifecycle_state}
    fields.update(changes)
    return State(**fields)


def _with_transition(t: Transition, **changes) -> Transition:
    fields = {"id": t.id, "source": t.source, "trigger": t.trigger, "target": t.target,
              "guard": t.guard, "implementation_status": t.implementation_status,
              "lifecycle_state": t.lifecycle_state}
    fields.update(changes)
    return Transition(**fields)


def _coerce(prop: str, value: str):
    if prop == "is_initial":
        return str(value).lower() in ("true", "1", "yes")
    return value


def apply_overrides(model: Model, log: OverrideLog) -> ApplyResult:
    """Layer the log onto a freshly-loaded source model (spec E-7).

    Applied in log order, so a later override supersedes an earlier one on the
    same property -- which is what makes the log append-only without needing
    edits (N-15).

    A **stale** override is still applied and *also* flagged. E-7 and E-8 both
    hold: the override continues to apply, and the fact that its evidence moved
    is surfaced for revalidation. Skipping it would silently discard human work
    (I-16); resolving it silently would decide a question E-9 reserves for a
    person.
    """
    result = ApplyResult(model=model)
    result.stale = check_staleness(model, log)
    stale_ids = {(s.override.element_id, s.override.prop) for s in result.stale}
    touched: set[tuple[str, str]] = set()

    for override in log.entries:
        kind, eid = override.element_kind, override.element_id
        holder = model.states if kind == STATE else model.transitions

        if override.operation == ADD:
            if eid in holder:
                result.no_ops.append(
                    f"{eid}: add is a no-op — the source now contains it too")
                continue
            if kind == STATE:
                p = override.payload
                holder[eid] = State(id=eid, name=p.get("name", eid),
                                    surface=p.get("surface", "api"),
                                    is_initial=bool(p.get("is_initial", False)),
                                    lifecycle_state=QUARANTINE)
            else:
                p = override.payload
                holder[eid] = Transition(
                    id=eid, source=p["source"], trigger=p["trigger"], target=p["target"],
                    guard=p.get("guard", ""),
                    implementation_status=p.get("implementation_status", IMPLEMENTED),
                    lifecycle_state=QUARANTINE)
                touched.add((holder[eid].source, holder[eid].trigger))

        elif override.operation == REMOVE:
            if eid not in holder:
                result.no_ops.append(
                    f"{eid}: remove is a no-op — the source no longer contains it")
                continue
            if kind == TRANSITION:
                t = holder[eid]
                touched.add((t.source, t.trigger))
            del holder[eid]

        else:  # MODIFY
            if eid not in holder:
                result.no_ops.append(
                    f"{eid}: modify is a no-op — the element is no longer in the source")
                continue
            value = _coerce(override.prop, override.new_value)
            if kind == STATE:
                holder[eid] = _with_state(holder[eid], **{override.prop: value},
                                          lifecycle_state=QUARANTINE)
            else:
                before = holder[eid]
                touched.add((before.source, before.trigger))
                holder[eid] = _with_transition(before, **{override.prop: value},
                                               lifecycle_state=QUARANTINE)
                touched.add((holder[eid].source, holder[eid].trigger))
                if override.changes_identity:
                    result.notes.append(
                        f"{eid}.{override.prop} changed — this moves the "
                        f"transition's natural key (I-2). It is a rename in identity "
                        f"terms, so the next re-extraction will not match it to the "
                        f"element it came from without a confirmed rename (I-21)")
            if (eid, override.prop) in stale_ids:
                result.notes.append(
                    f"{eid}.{override.prop}: applied, and flagged stale (E-8) — "
                    f"the extracted value moved since this edit was made")

        result.applied.append(override)
        result.authors[eid] = override.author
        # E-11: an edit is a proposal, exactly like any source's output (S-4).
        if eid in holder and holder[eid].lifecycle_state != QUARANTINE:
            holder[eid] = (_with_state(holder[eid], lifecycle_state=QUARANTINE)
                           if kind == STATE
                           else _with_transition(holder[eid], lifecycle_state=QUARANTINE))
        if eid in holder:
            result.quarantined.append(eid)

    # E-13/I-18: determinism and guard completeness are properties of a
    # (state, trigger) group, so editing one member revalidates the whole group.
    # Approval is revoked on *disturbance*, matching identity/matching.py rather
    # than re-deriving a second, subtly different rule here: an edit can break a
    # sibling's determinism exactly as an extraction can.
    model.reindex()
    for source_state, trigger in sorted(touched):
        siblings = [t for t in model.transitions.values()
                    if t.source == source_state and t.trigger == trigger]
        if not siblings:
            continue
        result.revalidated_groups.append((source_state, trigger))
        for sibling in siblings:
            if sibling.lifecycle_state == APPROVED:
                model.transitions[sibling.id] = _with_transition(
                    sibling, lifecycle_state=QUARANTINE)
                result.quarantined.append(sibling.id)
                result.notes.append(
                    f"{sibling.id}: approval revoked — group ({source_state}, {trigger}) "
                    f"was disturbed by an edit; determinism and guard completeness are "
                    f"group properties (I-18, E-13)")

    model.reindex()
    result.quarantined = sorted(set(result.quarantined))
    return result


# --------------------------------------------------------------------------
# Findings (spec E-4, E-5, E-6)
# --------------------------------------------------------------------------

# Spec E-6, verbatim in meaning. Removal classified `intended_divergence` is the
# one worth calling out: it says *the system does this and it should not*, which
# is among the most valuable findings the platform can produce -- and it arrives
# through the editor rather than through any analysis.
_MEANING = {
    (ADD, EXTRACTION_ERROR): "extraction missed real behaviour",
    (ADD, INTENDED_DIVERGENCE): "behaviour that should exist but does not — a gap",
    (REMOVE, EXTRACTION_ERROR): "a false positive from unsound analysis",
    (REMOVE, INTENDED_DIVERGENCE): "the code does something it should not — a defect",
    (MODIFY, EXTRACTION_ERROR): "extraction misread the condition",
    (MODIFY, INTENDED_DIVERGENCE): "the condition is wrong in the code",
}


@dataclass
class OverrideFinding:
    target: str
    element_id: str
    operation: str
    classification: str
    meaning: str
    author: str
    rationale: str
    detail: str


def findings(log: OverrideLog) -> list[OverrideFinding]:
    """Split the log into findings against Métis and findings against the product.

    Two lists, never one number -- the same discipline F-5 applies to
    reconciliation gaps, and for the same reason: an unreliable extractor and a
    product defect have different causes, different severities, different owners.
    """
    out = []
    for o in log.entries:
        out.append(OverrideFinding(
            target=o.finding_target, element_id=o.element_id, operation=o.operation,
            classification=o.classification,
            meaning=_MEANING.get((o.operation, o.classification), ""),
            author=o.author, rationale=o.rationale, detail=o.describe(),
        ))
    return out


# --------------------------------------------------------------------------
# Density (spec E-10)
# --------------------------------------------------------------------------

@dataclass
class Density:
    overridden: int
    total: int
    by_classification: dict[str, int]

    @property
    def ratio(self) -> float:
        return round(self.overridden / self.total, 3) if self.total else 0.0

    @property
    def caveat(self) -> str:
        """What the number means for the model's standing as a claim about code."""
        if not self.overridden:
            return ""
        return (f"{self.overridden} of {self.total} elements carry a human override "
                f"({self.ratio:.0%}). A heavily overridden code-derived model is a "
                f"weaker claim about the code; do not read it as a faithful mirror "
                f"of the implementation (E-10)")


def density(model: Model, log: OverrideLog) -> Density:
    """Reported on the model view and in the generated specification (spec E-10).

    Counted over elements, not overrides: five edits to one transition is one
    overridden element, not five. Counting overrides would let repeated
    refinement of a single guard look like pervasive distrust of the extractor.
    """
    total = len(model.states) + len(model.transitions)
    present = {eid for eid in log.overridden_ids()
               if eid in model.states or eid in model.transitions}
    by_class: dict[str, int] = {}
    for c in CLASSIFICATIONS:
        by_class[c] = len({o.element_id for o in log.entries
                           if o.classification == c and o.element_id in present})
    return Density(overridden=len(present), total=total, by_classification=by_class)


def format_overrides(result: ApplyResult, log: OverrideLog) -> str:
    """Human-readable summary, keeping the two finding targets separate (E-5)."""
    d = density(result.model, log)
    lines = [f"Overrides — {log.model_id or result.model.id}",
             f"  applied:        {len(result.applied)}",
             f"  quarantined:    {len(result.quarantined)} element(s) (E-11)",
             f"  groups revalidated: {len(result.revalidated_groups)} (E-13)"]

    against_metis = [f for f in findings(log) if f.target == TARGET_METIS]
    against_product = [f for f in findings(log) if f.target == TARGET_PRODUCT]
    lines += ["", f"  AGAINST MÉTIS (extraction quality):   {len(against_metis)}"]
    lines += [f"       {f.element_id}: {f.meaning} — {f.rationale}" for f in against_metis[:8]]
    lines += ["", f"  AGAINST THE PRODUCT (candidate defects): {len(against_product)}"]
    lines += [f"       {f.element_id}: {f.meaning} — {f.rationale}" for f in against_product[:8]]

    if result.stale:
        lines += ["", f"  STALE: {len(result.stale)} (E-8) — applied, and awaiting revalidation"]
        lines += [f"       {s.describe().splitlines()[0]}" for s in result.stale]
    if result.no_ops:
        lines += ["", "  NO-OPS:"] + [f"       {n}" for n in result.no_ops]
    if d.caveat:
        lines += ["", f"  {d.caveat}"]
    lines += ["", "  These two finding lists are NOT one number. An unreliable extractor",
              "  and a product defect have different owners (E-5, cf. F-5)."]
    return "\n".join(lines)
