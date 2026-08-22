"""
Pack facts -> a guard-dimension chain (application spec GD-1, GD-2, X-10a..X-10d).

`mbt/dimensions.py` implements the whole of §2.4a's combinatorial answer -- the
short-circuit chain, GD-2's prefix guards, GD-3's variation bound, GD-8's
anchor-gated equivalence -- in four hundred lines with **zero callers**. Nothing
ever built it a `Chain`, because nothing knew how to turn what a pack recovers
into ordered dimensions. This is that missing step.

**Order is a framework fact, not a source-line fact (X-10a, X-10d).** Spring runs
bean validation in the argument resolver, strictly before the handler body is
entered. So a `@Valid` body constraint is evaluated before every in-body check,
whatever line it appears on, and the validation dimension takes `order = 0`. That
is a property of the framework's contract, and it is the only reason this module
may claim an order it did not observe. In-body checks keep the order the
behaviour pack recovered from control flow.

    order 0   validation   @Valid on the body + the DTO's own constraints
    order 1.. business     the CheckFacts the behaviour pack already emits

**Fail-closed, per dimension.** The chain closes only when all three links are
present: the endpoint is `@Valid`-annotated, its body type declares at least one
constraint, and an `@ExceptionHandler` maps the bean-validation exception to the
status in question. Miss any one and this module returns no validation dimension
**and says which link was missing** -- it never falls back to assuming payload
validation, because athena maps four different exceptions onto 400 and only one
of them is validation. Labelling the other three "payload invalid" would be
affirmatively wrong rather than merely unevidenced: a fixture built from it sets
up the wrong precondition and never reaches the path at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from metis_mcp.mbt.dimensions import (
    VALIDATION,
    Chain,
    Dimension,
    build_chain,
)

# The minted propositions. Neither string appears in any source file; both are
# derived from anchored facts, and `link` on the resulting outcome records which
# of the two claims was made (see `contract.LINK_DERIVED_VALIDATION`).
#
# There is precedent for minting a guard token: the behaviour pack already mints
# `"an exception is thrown"` for a CATCH node and ships it in production guards.
# What is new here is saying so in the model rather than only in a comment.
VALIDATION_EXPRESSION = "payload_valid"
GENERIC_EXPRESSION = "request_accepted"

# `order = 0` is the framework contract, and it must be exactly 0: the behaviour
# pack numbers its checks from 1, so any other value would collide and trip
# `build_chain`'s ambiguity guard (GD-9) on endpoints that have both.
VALIDATION_ORDER = 0
VALIDATION_DIMENSION_ID = "dim-validation"

# The exception Spring raises when bean validation fails. Everything else an
# advice maps to 400 is a different behaviour with a different precondition.
BEAN_VALIDATION_EXCEPTION = "MethodArgumentNotValidException"


@dataclass(frozen=True)
class _SyntheticCheck:
    """`CheckFact`-shaped, because `build_chain` is duck-typed on this shape.

    Deliberately not a real `contract.CheckFact`: that type means "a condition the
    engine observed in the code", and this is a condition assembled from four
    separate annotations. Same shape, different claim.
    """

    id: str
    expression: str
    order: int
    anchor: str
    dimension_class: str | None = None


@dataclass
class Recovery:
    """A chain, plus an honest account of what could not be recovered."""

    chain: Chain
    validation: Dimension | None = None
    # Why no validation dimension. Empty when one was recovered.
    reason: str = ""
    # Every anchor behind the validation dimension, in evidence order:
    # the constraint, the @Valid, the @ExceptionHandler, the @ApiResponse.
    anchors: tuple[str, ...] = ()
    # The DTO constraints themselves -- GD-3's variants. These are the data
    # requirements a fixture must violate, and the reason 164 constrained fields
    # stay test data instead of becoming 164 transitions.
    constraints: tuple[str, ...] = field(default_factory=tuple)
    # `(type_name, field_name)` for each constrained field. The constraint
    # STRINGS above say what must be violated; these say which field says it, and
    # without them a transition cannot point at the `Field` node that carries the
    # requirement -- only quote it.
    fields: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def has_validation(self) -> bool:
        return self.validation is not None

    def rejection_expression(self) -> str:
        """The atom this endpoint's rejection is expressed in.

        `payload_valid` where the cause was traced, `request_accepted` where only
        the `@ApiResponse` is known. The second says exactly what the annotation
        says -- this endpoint can reject this request -- and names no cause.
        """
        return VALIDATION_EXPRESSION if self.has_validation else GENERIC_EXPRESSION


def _simple(type_name: str) -> str:
    return (type_name or "").rsplit(".", 1)[-1]


def _anchor_str(anchor) -> str:
    if isinstance(anchor, dict):
        return f"{anchor.get('file', '')}:{anchor.get('line', 0)}@{anchor.get('commit', '')}"
    if anchor is None:
        return ""
    return str(anchor)


def constrained_members(body_type: str, members) -> list:
    """The declared constraints on a body DTO's fields (GD-3's variants).

    Matched on the simple type name because the two packs disagree on form -- a
    parameter carries `org.catools.athena.model.metrics.MetricDto` and a member
    carries `MetricDto`. Comparing them unnormalised silently finds nothing,
    which reads exactly like a DTO with no constraints.
    """
    want = _simple(body_type)
    if not want:
        return []
    return [m for m in members
            if _simple(getattr(m, "type_name", "") or (m.get("type_name", "")
                       if isinstance(m, dict) else ""))== want
            and (getattr(m, "constraints", None)
                 or (m.get("constraints") if isinstance(m, dict) else None))]


def _member_constraints(member) -> tuple[str, ...]:
    if isinstance(member, dict):
        return tuple(member.get("constraints") or ())
    return tuple(getattr(member, "constraints", ()) or ())


def _member_anchor(member):
    if isinstance(member, dict):
        return member.get("anchor")
    return getattr(member, "anchor", None)


def recover_chain(endpoint: dict, checks, members, exception_status: dict,
                  status: int, declared_anchor: str = "",
                  exception_anchors: dict | None = None) -> Recovery:
    """Assemble the chain guarding one entry point.

    `endpoint` is the structural pack's mapped dict; `checks` the behaviour
    pack's `CheckFact`s for this endpoint; `members` the Layer 3 registry;
    `exception_status` the `@ExceptionHandler` map (`contract.exception_status_map`);
    `status` the declared status whose cause is being traced.
    """
    business = list(checks)
    chain = build_chain(endpoint.get("id", ""), business)

    body = next((p for p in endpoint.get("parameters", ())
                 if (p.get("location") if isinstance(p, dict)
                     else getattr(p, "location", "")) == "body"), None)

    if not endpoint.get("validated"):
        return Recovery(chain=chain, reason=(
            "no @Valid/@Validated on the handler, so bean validation does not run "
            "and this status cannot be attributed to payload validation"))
    if body is None:
        return Recovery(chain=chain, reason=(
            "no request body, so there is no payload for bean validation to reject"))

    body_type = (body.get("type_name") if isinstance(body, dict)
                 else getattr(body, "type_name", ""))
    constrained = constrained_members(body_type, members)
    if not constrained:
        return Recovery(chain=chain, reason=(
            f"{_simple(body_type)} declares no field constraints, so @Valid has "
            f"nothing to reject"))

    mapped = exception_status.get(BEAN_VALIDATION_EXCEPTION)
    if mapped is None:
        return Recovery(chain=chain, reason=(
            f"no @ExceptionHandler maps {BEAN_VALIDATION_EXCEPTION} to a status; "
            f"without it, a validation failure's observable result is unknown"))
    if mapped != status:
        return Recovery(chain=chain, reason=(
            f"{BEAN_VALIDATION_EXCEPTION} maps to {mapped}, not {status}; this "
            f"outcome has some other cause"))

    # Four real anchors, in evidence order. Every one of them is a line a
    # reviewer can open -- which is the whole difference between a derived guard
    # and an invented one (§8.5, T-9a).
    #
    # Each is labelled with the fact it establishes, because two of them
    # legitimately resolve to the SAME line: `@Valid` and `@ApiResponse` both sit
    # on the handler, and the pack anchors annotations at the method they
    # decorate. Unlabelled, that reads as a duplicate; labelled, it reads as what
    # it is -- two separate facts recovered from one declaration site.
    anchors = [
        f"constraint={_anchor_str(_member_anchor(constrained[0]))}",
        f"valid={_anchor_str(endpoint.get('anchor'))}",
        f"exception-handler={_anchor_str((exception_anchors or {}).get(BEAN_VALIDATION_EXCEPTION, ''))}",
        f"declared={declared_anchor}",
    ]
    anchors = [a for a in anchors if not a.endswith("=")]

    synthetic = _SyntheticCheck(
        id=VALIDATION_DIMENSION_ID, expression=VALIDATION_EXPRESSION,
        order=VALIDATION_ORDER, anchor=", ".join(anchors),
        dimension_class=VALIDATION)

    full = build_chain(endpoint.get("id", ""), [synthetic, *business])
    dimension = next((d for d in full.dimensions if d.id == VALIDATION_DIMENSION_ID), None)

    constraints: list[str] = []
    for member in constrained:
        constraints.extend(_member_constraints(member))

    identities = tuple(
        (_simple(getattr(m, "type_name", "") or (m.get("type_name", "") if isinstance(m, dict) else "")),
         getattr(m, "name", "") or (m.get("name", "") if isinstance(m, dict) else ""))
        for m in constrained)

    return Recovery(chain=full, validation=dimension, anchors=tuple(anchors),
                    constraints=tuple(dict.fromkeys(constraints)),
                    fields=identities)
