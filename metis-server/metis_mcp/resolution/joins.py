"""
The pending-join record and the pass that resolves it (spec X-19).

Pure: it takes proposals and a set of things that exist, and returns what
resolved, what did not, and why. No session, no writes — the same shape as the
landing planners, and for the same reason: an invariant asserted without a
database is an invariant a suite can hold.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# What a proposal has become.
PROPOSED = "proposed"      # the confirming side has not arrived
CONFIRMED = "confirmed"    # it arrived and contains the target
REFUTED = "refuted"        # it arrived and does NOT contain the target


@dataclass(frozen=True)
class JoinKind:
    """One kind of deferred join, declared once.

    `proposed_by` and `confirmed_by` are intake ids. They are what makes the
    engine generic: an intake says which joins it can offer and which it can
    settle, and a new intake adds rows here rather than code.
    """

    name: str
    relationship: str
    from_label: str
    to_label: str
    proposed_by: tuple[str, ...]
    confirmed_by: tuple[str, ...]
    meaning: str
    # Set where the confirming side supplies a VALUE rather than a target node.
    # A selector is not a thing on the graph — it is how to find one — so
    # `Element.selector` is a property and `relationship` is empty.
    property_name: str = ""


# The three that exist as hand-work today. Each names the intake that can settle
# it, which is also the answer to "why is this unresolved" — that intake has not
# run.
KINDS: dict[str, JoinKind] = {k.name: k for k in (
    JoinKind(
        name="entity_storage",
        relationship="STORED_IN", from_label="BusinessEntity", to_label="Table",
        proposed_by=("knowledge", "structure"), confirmed_by=("database",),
        meaning="which table a business noun is persisted in"),
    JoinKind(
        name="query_target",
        relationship="QUERIES", from_label="Query", to_label="Table",
        proposed_by=("code",), confirmed_by=("database",),
        meaning="which table a query reads or writes"),
    JoinKind(
        name="route_page",
        relationship="RENDERS", from_label="Route", to_label="Page",
        proposed_by=("web",), confirmed_by=("structure",),
        meaning="which page a frontend route shows"),
    JoinKind(
        name="element_selector",
        relationship="", from_label="UiElement", to_label="",
        proposed_by=("structure",), confirmed_by=("web",),
        meaning="how to find an authored element on the page",
        property_name="selector"),
)}


@dataclass(frozen=True)
class PendingJoin:
    """One proposal, and how it was arrived at.

    `to_ref` is what the proposing side *believes* the target is called. It is
    deliberately a name rather than an id: the target may not exist yet, and
    minting an id for a thing that does not exist is how an edge comes to point
    at nothing.
    """

    kind: str
    from_id: str
    to_ref: str
    basis: str
    detail: str = ""

    @property
    def spec(self) -> JoinKind:
        return KINDS[self.kind]


@dataclass
class Resolution:
    """What a pass concluded. Every proposal appears in exactly one list."""

    confirmed: list[tuple[PendingJoin, str]] = field(default_factory=list)
    refuted: list[tuple[PendingJoin, str]] = field(default_factory=list)
    proposed: list[tuple[PendingJoin, str]] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {CONFIRMED: len(self.confirmed), REFUTED: len(self.refuted),
                PROPOSED: len(self.proposed)}

    def describe(self) -> str:
        bits = [f"{n} {k}" for k, n in self.counts.items() if n]
        return ", ".join(bits) or "no pending joins"


def resolve(pending, available: dict[str, set[str]]) -> Resolution:
    """Settle what can be settled.

    `available` maps an intake id to the names it has landed —
    `{"database": {"record", "record_tag"}}`. An intake absent from the mapping
    has **not run**, which is a different answer from having run and not
    contained the name:

        absent  -> still `proposed`. The join may yet resolve.
        present -> `confirmed` if the name is there, `refuted` if it is not.

    Collapsing those two is the whole failure this distinction exists to
    prevent: a retry loop treats "no" as "not yet" and never stops asking, and a
    reviewer never learns the proposal was wrong.
    """
    out = Resolution()
    for join in pending:
        spec = join.spec
        settled = False
        for intake in spec.confirmed_by:
            names = available.get(intake)
            if names is None:
                continue
            settled = True
            if join.to_ref in names:
                out.confirmed.append((join, intake))
            else:
                out.refuted.append((
                    join,
                    f"{intake} has run and declares no {spec.to_label.lower()} "
                    f"named {join.to_ref!r}; it was proposed on {join.basis}"))
            break
        if not settled:
            out.proposed.append((
                join,
                f"nothing has confirmed it — {' or '.join(spec.confirmed_by)} "
                f"has not run. Proposed on {join.basis}"))
    return out


def findings_for(resolution: Resolution) -> list[tuple[str, str, str]]:
    """`(about_id, severity, detail)` for everything that did not confirm.

    An unresolved join is reported rather than retried silently, because the
    reason differs and the reader needs it: `proposed` is a missing intake and
    `refuted` is a wrong belief, and only one of them is fixed by running
    something.
    """
    out: list[tuple[str, str, str]] = []
    for join, why in resolution.refuted:
        out.append((join.from_id, "advisory",
                    f"{join.spec.meaning}: proposed {join.to_ref!r} and it was "
                    f"refuted — {why}"))
    for join, why in resolution.proposed:
        out.append((join.from_id, "advisory",
                    f"{join.spec.meaning}: {join.to_ref!r} is unconfirmed — {why}"))
    return out


def properties_for(resolution: Resolution, value_for
                   ) -> list[tuple[str, str, str, str]]:
    """`(from_label, from_id, property, value)` for confirmed property-valued joins.

    The counterpart to `edges_for`, and the reason `edges_for` has always had a
    branch that skips these. A selector is not a node — writing `#archive` as an
    entity would put a CSS string in the label space and give a reviewer a thing
    to approve that is not a fact about the system. It is how to reach an
    element, so it belongs on the element.

    `value_for` turns the confirmed name into whatever the confirming intake
    recorded against it, because only that intake knows.
    """
    out = []
    for join, _ in resolution.confirmed:
        spec = join.spec
        if not spec.property_name:
            continue
        value = value_for(join.to_ref)
        if value:
            out.append((spec.from_label, join.from_id, spec.property_name, value))
    return out


def edges_for(resolution: Resolution, target_id) -> list[tuple[str, str, str, str, str]]:
    """`(from_label, from_id, rel_type, to_label, to_id)` for confirmed joins only.

    `target_id` turns a confirmed name into the id the confirming intake wrote,
    because only that intake knows how it keys its nodes.
    """
    out = []
    for join, _ in resolution.confirmed:
        spec = join.spec
        if not spec.relationship:
            continue          # a property-valued join, not an edge
        out.append((spec.from_label, join.from_id, spec.relationship,
                    spec.to_label, target_id(join.to_ref)))
    return out
