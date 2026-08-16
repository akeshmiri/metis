"""
Guard dimensions and precedence (application spec §2.4a, §5.4a, §6.2; GD-1..GD-9,
A-44..A-51).

**The problem this solves is combinatorial, and it is not hypothetical.** A single
endpoint varies along several axes -- authentication, authorization, header
validity, payload validity, each field. Treated as independent they multiply:
`3 auth x 2 authz x 10 payload = 60` cases per endpoint, ~1,500 for a 25-endpoint
service. Almost all of it worthless, because most of those combinations are
unreachable.

**They are not independent. They are a short-circuit chain (GD-1).** A request
that fails authentication never reaches authorization, so varying authorization
underneath it produces no observable difference:

    401   !authenticated                                      auth only
    403   authenticated AND !authorized                        authz only
    400   authenticated AND authorized AND !payload_valid      payload only
    200   authenticated AND authorized AND payload_valid       the success path

    1 + 1 + 10 + 1 = 13 tests, not 60.

Two rules carry the whole reduction, and both are about **not** over-claiming:

  * **GD-3** dimensions after the failing one are *unconstrained*, so varying them
    is unobservable -- that is what removes the product.
  * **GD-8** class credit is gated on an **identical code anchor**. Twenty-five
    endpoints whose 401 resolves to the same line are one behaviour reached
    twenty-five ways. One whose 401 resolves elsewhere is a *different* check --
    and a per-endpoint deviation in an auth check is precisely where a real
    vulnerability hides, so it is never credited away.

**GD-9 -- fail-closed on unknown order.** If precedence cannot be recovered,
dimensions are neither assumed independent nor assumed ordered. The transition is
flagged `precedence_unresolved`, guard coverage falls back to the full product,
and the explosion is **reported rather than silently generated**. Guessing an
order would quietly drop real combinations, which is the one outcome worse than
an expensive test run.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Dimension classes. Which checks belong to which class is **configuration**
# (X-10b); only `cross_cutting` is a property of the class itself.
AUTHENTICATION = "authentication"
AUTHORIZATION = "authorization"
VALIDATION = "validation"
BUSINESS = "business"

CROSS_CUTTING = frozenset({AUTHENTICATION, AUTHORIZATION})

PRECEDENCE_UNRESOLVED = "precedence_unresolved"


@dataclass(frozen=True)
class DimensionClass:
    """One declared axis of variation (spec X-10b).

    `matches` are substrings tested against a recovered check expression. Kept
    deliberately dumb: a regex vocabulary here would become a second, undocumented
    configuration language, and classification is meant to be reviewable by
    whoever owns the framework config, not by whoever wrote this module.
    """

    name: str
    cross_cutting: bool = False
    matches: tuple[str, ...] = ()


DEFAULT_CLASSES = (
    DimensionClass(AUTHENTICATION, True,
                   ("authenticated", "isauthenticated", "principal", "securitycontext",
                    "preauthorize", "jwt", "token_valid", "api_key")),
    DimensionClass(AUTHORIZATION, True,
                   ("authorized", "hasrole", "hasauthority", "permission", "granted",
                    "isowner", "canaccess")),
    DimensionClass(VALIDATION, False,
                   ("valid", "notnull", "isempty", "notblank", "length", "matches",
                    "required", "format")),
)


@dataclass(frozen=True)
class Dimension:
    """One recovered check, placed in the chain.

    `order` is the **evaluation** order, from the framework chain and control
    flow -- never source line position (spec X-10d, A-51).
    """

    id: str
    expression: str
    order: int
    dimension_class: str | None = None
    anchor: str = ""

    @property
    def is_cross_cutting(self) -> bool:
        return self.dimension_class in CROSS_CUTTING


def classify(expression: str, classes: tuple[DimensionClass, ...] = DEFAULT_CLASSES
             ) -> str | None:
    """Match a recovered check against declared classes (spec X-10b).

    Returns None rather than a guess. **X-10c**: an unclassified check keeps its
    recovered *position* and still participates in the chain -- GD-3's scope rule
    works on order alone -- it simply cannot be marked cross-cutting.
    """
    lowered = re.sub(r"[^a-z0-9]", "", expression.lower())
    for declared in classes:
        for needle in declared.matches:
            if needle in lowered:
                return declared.name
    return None


@dataclass
class Chain:
    """The ordered dimensions guarding one entry point (spec GD-1)."""

    endpoint_id: str
    dimensions: list[Dimension] = field(default_factory=list)
    unresolved_reason: str = ""

    @property
    def is_resolved(self) -> bool:
        return not self.unresolved_reason

    def ordered(self) -> list[Dimension]:
        return sorted(self.dimensions, key=lambda d: (d.order, d.id))

    def index_of(self, dimension_id: str) -> int | None:
        for i, d in enumerate(self.ordered()):
            if d.id == dimension_id:
                return i
        return None


def build_chain(endpoint_id: str, checks) -> Chain:
    """Assemble a chain, refusing to invent an order it cannot recover (GD-9).

    `checks` are `code_analysis.contract.CheckFact`-shaped: `id`, `expression`,
    `order`, optionally `dimension_class` and `anchor`.

    Two checks sharing an order make the chain ambiguous. That is reported, not
    broken by a tie-break on id -- a tie-break would be exactly the guess GD-9
    forbids, dressed as determinism.
    """
    chain = Chain(endpoint_id=endpoint_id)
    orders: dict[int, list[str]] = {}

    for check in checks:
        anchor = getattr(check, "anchor", "")
        chain.dimensions.append(Dimension(
            id=check.id, expression=check.expression, order=check.order,
            dimension_class=(getattr(check, "dimension_class", None)
                             or classify(check.expression)),
            anchor=(f"{anchor.file}:{anchor.line}@{anchor.commit}"
                    if hasattr(anchor, "file") else str(anchor)),
        ))
        orders.setdefault(check.order, []).append(check.id)

    ambiguous = {o: ids for o, ids in orders.items() if len(ids) > 1}
    if ambiguous:
        chain.unresolved_reason = (
            f"{PRECEDENCE_UNRESOLVED}: checks share an evaluation order "
            f"({ambiguous}). Order is a code fact (X-10a); it is not inferred from "
            f"source line position (X-10d) and is not tie-broken by id, which "
            f"would be a guess wearing determinism's clothes (GD-9)")
    return chain


# --------------------------------------------------------------------------
# GD-2 : a rejection's guard is prefix-determined
# --------------------------------------------------------------------------

def prefix_guard(chain: Chain, failing_dimension_id: str) -> str:
    """`(dimensions 1..k-1 all pass) AND (dimension k fails)` (spec GD-2, A-44).

    Downstream dimensions appear nowhere: they are unconstrained (GD-3), and
    naming them would imply a constraint the code never evaluates.
    """
    k = chain.index_of(failing_dimension_id)
    if k is None:
        raise KeyError(f"{failing_dimension_id} is not in this chain")
    ordered = chain.ordered()
    parts = [d.expression for d in ordered[:k]]
    parts.append(f"NOT ({ordered[k].expression})")
    return " AND ".join(parts)


def success_guard(chain: Chain) -> str:
    """Every dimension passes -- the terminating case (spec GD-4)."""
    return " AND ".join(d.expression for d in chain.ordered())


# --------------------------------------------------------------------------
# GD-3 / P-3a : what guard coverage may vary
# --------------------------------------------------------------------------

@dataclass
class VariationScope:
    """Which dimensions guard coverage varies for one rejection (spec P-3a)."""

    held_pass: tuple[str, ...]
    varied: str
    not_varied: tuple[str, ...]
    reason: str = ""

    @property
    def is_bounded(self) -> bool:
        return not self.reason


def variation_scope(chain: Chain, failing_dimension_id: str,
                    variants_per_dimension: dict[str, int] | None = None
                    ) -> VariationScope:
    """Spec GD-3, P-3a, A-45.

    Dimensions 1..k-1 are **held at pass** -- they are required to reach this
    transition at all. Dimension k is **varied** -- it is the axis under test.
    Dimensions k+1..n are **not varied** -- unreachable, so variation is
    unobservable.

    Where precedence is unresolved (GD-9), the bound does not apply: everything
    is varied and P-3b's explosion is reported by `cost()`.
    """
    if not chain.is_resolved:
        return VariationScope(
            held_pass=(), varied=failing_dimension_id,
            not_varied=(), reason=chain.unresolved_reason)

    k = chain.index_of(failing_dimension_id)
    if k is None:
        raise KeyError(f"{failing_dimension_id} is not in this chain")
    ordered = chain.ordered()
    return VariationScope(
        held_pass=tuple(d.id for d in ordered[:k]),
        varied=failing_dimension_id,
        not_varied=tuple(d.id for d in ordered[k + 1:]),
    )


@dataclass
class Cost:
    """What guard coverage would actually generate."""

    bounded_total: int
    product_total: int
    per_dimension: dict[str, int]
    exploded: bool = False
    reason: str = ""

    @property
    def saved(self) -> int:
        return self.product_total - self.bounded_total


def cost(chain: Chain, variants: dict[str, int] | None = None) -> Cost:
    """Spec GD-3's worked example, computed rather than asserted (A-46).

    `variants[d]` is the number of distinct ways dimension `d` can be exercised,
    **including** the passing case -- so a dimension with 10 payload variants has
    9 failure modes and 1 pass.

        bounded  = sum over d of (variants[d] - 1)  +  1 success path
        product  = product over d of variants[d]

    With the spec's own figures (3 auth, 2 authz, 10 payload):
    `2 + 1 + 9 + 1 = 13` against `3 x 2 x 10 = 60`.

    An earlier version of this summed `variants[d]` rather than the failure modes
    and could report a bounded count *exceeding* the product -- caught by the
    report reading as nonsense, not by a test.
    """
    counts = variants or {}
    ordered = chain.ordered()
    per_dimension = {d.id: max(counts.get(d.id, 2), 2) for d in ordered}

    bounded = sum(n - 1 for n in per_dimension.values()) + 1
    product = 1
    for n in per_dimension.values():
        product *= n

    if not chain.is_resolved:
        # P-3b: no bound applies. The full product is reported as an explosion
        # warning rather than silently generated.
        return Cost(bounded_total=product, product_total=product,
                    per_dimension=per_dimension, exploded=True,
                    reason=(f"{chain.unresolved_reason}. Guard coverage falls back "
                            f"to the full product: {product} cases. This is reported, "
                            f"not generated (P-3b)"))

    return Cost(bounded_total=bounded, product_total=product,
                per_dimension=per_dimension)


# --------------------------------------------------------------------------
# GD-7 / GD-8 : equivalence by code anchor
# --------------------------------------------------------------------------

@dataclass
class EquivalenceClass:
    """Cross-cutting transitions resolving to the identical code anchor (GD-7)."""

    dimension_class: str
    anchor: str
    transition_ids: tuple[str, ...]

    @property
    def credits_once(self) -> bool:
        """GD-8: covering one member credits the class -- but only ever for a
        cross-cutting class with a shared anchor."""
        return self.dimension_class in CROSS_CUTTING and bool(self.anchor)


def equivalence_classes(entries) -> tuple[list[EquivalenceClass], list[tuple[str, str]]]:
    """Group cross-cutting transitions by `(class, anchor)` (spec GD-7, A-48, A-49).

    `entries` are `(transition_id, dimension_class, anchor)` triples.

    Returns `(classes, covered_separately)`. The second list is the important
    one: a cross-cutting transition whose anchor differs from its peers is
    **distinct behaviour** and is covered on its own. Folding it into the class
    would credit away exactly the per-endpoint deviation a real vulnerability
    lives in (GD-8, P-3c).
    """
    grouped: dict[tuple[str, str], list[str]] = {}
    unanchored: list[tuple[str, str]] = []

    for transition_id, dimension_class, anchor in entries:
        if dimension_class not in CROSS_CUTTING:
            unanchored.append((transition_id, f"not cross-cutting ({dimension_class})"))
            continue
        if not anchor:
            unanchored.append((
                transition_id,
                "no code anchor — equivalence is anchor-gated, and an unanchored "
                "transition cannot be shown identical to anything (GD-8)"))
            continue
        grouped.setdefault((dimension_class, anchor), []).append(transition_id)

    classes = [
        EquivalenceClass(dimension_class=cls, anchor=anchor,
                         transition_ids=tuple(sorted(ids)))
        for (cls, anchor), ids in sorted(grouped.items())
    ]
    for group in classes:
        if len(group.transition_ids) == 1:
            unanchored.append((
                group.transition_ids[0],
                f"only member of its ({group.dimension_class}, {group.anchor}) class "
                f"— no peer shares its anchor, so it is distinct behaviour (GD-8)"))

    return classes, sorted(unanchored)


def class_credit(classes: list[EquivalenceClass], covered: set[str]) -> dict[str, str]:
    """Which transitions are credited by covering a peer (spec P-3c).

    Returns `transition_id -> the id whose coverage credits it`. Only ever
    populated for classes of two or more with an identical anchor.
    """
    credited: dict[str, str] = {}
    for group in classes:
        if not group.credits_once or len(group.transition_ids) < 2:
            continue
        member = next((t for t in group.transition_ids if t in covered), None)
        if member is None:
            continue
        for transition_id in group.transition_ids:
            if transition_id != member:
                credited[transition_id] = member
    return credited


def format_dimensions(chain: Chain, variants: dict[str, int] | None = None) -> str:
    c = cost(chain, variants)
    lines = [f"Guard dimensions — {chain.endpoint_id}"]
    if not chain.is_resolved:
        lines += [f"  {PRECEDENCE_UNRESOLVED}", f"  {chain.unresolved_reason}", ""]
    for i, d in enumerate(chain.ordered()):
        cc = " [cross-cutting]" if d.is_cross_cutting else ""
        cls = d.dimension_class or "unclassified"
        lines.append(f"  {i + 1}. {d.expression}   ({cls}{cc})")
    lines += ["",
              f"  bounded:  {c.bounded_total} cases   (GD-3: only the failing "
              f"dimension varies)",
              f"  product:  {c.product_total} cases   (if the axes were independent)"]
    if c.exploded:
        lines.append(f"  EXPLOSION REPORTED: {c.reason}")
    elif c.saved > 0:
        lines.append(f"  saved:    {c.saved} cases that assert nothing observable")
    return "\n".join(lines)
