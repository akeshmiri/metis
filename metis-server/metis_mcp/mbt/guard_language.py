"""
Saying a guard in the language of the business (spec X-7, X-8, T-6, M-9).

A guard is the *given* half of `State -[:WHEN]-> Transition -[:THEN]-> State`, and
it was the half nothing ever translated. `naming.py` gives states and transitions
a three-tier cascade and `rendering.test_case._describe` gives step wording
another; between them the guard stayed raw, and the field a rendered case exposes
is still called `guard_verbatim`. So a stakeholder read

    Given the caller is Metric, When GET /metric/{id}, Then MetricGetActionById-
    NoContent204 -- when request_accepted AND t.isEmpty()

which is the implementation's vocabulary in all three positions but the middle.

**This module reverses a decision `naming.py` states explicitly**, and the reason
matters more than the reversal. That module says paraphrasing `t.isEmpty()` into
"no metric exists" would be "Métis inventing meaning, which T-6 forbids however
reasonable the guess looks". That was right about a *paraphrase*. It is not what
happens here, because the reading is not new:

    `unfolding.presence_sense()` ALREADY decides `t.isEmpty()` means the resource
    is absent, and the whole M-6 unfolding pass ALREADY acts on that decision --
    creating `MetricPresent`, re-parenting readers onto it, retargeting creators
    into it. That claim is load-bearing in the graph today.

Refusing to *say* a thing the model has already *acted on* is not caution, it is
an inconsistency that leaves the acted-on claim unreviewable. What T-6 forbids is
inventing meaning; restating a commitment already made, from the same decoder
that made it, invents nothing.

Two rules keep that from sliding:

  * **The decoder is closed and the tier is recorded (X-8).** Only idioms this
    module can name are translated; everything else is passed through verbatim
    and `verbatim_atoms` says which. A guard is never partly translated without
    saying so.
  * **This is tier 2, never tier 1.** It decodes a *convention in code*. It is
    not the business's own words, and it must never be presented as though a
    person wrote it -- that is what a confirmed acceptance criterion is for
    (`naming.propose_from_criteria`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from metis_mcp.behavior_model import _conjuncts
from metis_mcp.mbt.naming import (
    TIER_AC_VOCABULARY,
    TIER_CODE_CONVENTION,
    TIER_HUMAN,
)

# The guard could not be decoded at all and is shown exactly as recovered. A
# distinct value from the three naming tiers: "nobody has improved this yet" and
# "a convention was decoded" are different facts about the same field.
TIER_VERBATIM = "verbatim"

__all__ = ["TIER_AC_VOCABULARY", "TIER_CODE_CONVENTION", "TIER_HUMAN",
           "TIER_VERBATIM", "Wording", "describe_guard", "decode_atom"]

# The presence idiom, decoded by the same shape `unfolding.presence_sense` uses.
# Kept as its own pattern rather than imported so this module states which forms
# it claims to understand.
_PRESENCE = re.compile(r"^([A-Za-z_][\w.]*)\.(isEmpty|isPresent)\(\)$")

# Propositions Métis itself mints (`dimension_recovery`) or the behaviour pack
# mints for a CATCH node. Decoding our own vocabulary is the least speculative
# case there is: these strings appear in no source file, so their meaning is
# whatever we defined it to be.
_MINTED = {
    "payload_valid": ("the payload is valid", "the payload is invalid"),
    "request_accepted": ("the request is accepted", "the request is rejected"),
    "an exception is thrown": ("an error occurs", "no error occurs"),
    "credentials_valid": ("the credentials are valid", "the credentials are invalid"),
    "account_locked": ("the account is locked", "the account is not locked"),
    "request_succeeded": ("the request succeeds", "the request fails"),
}


@dataclass(frozen=True)
class Wording:
    """A guard said in business language, with what it could not translate."""

    text: str
    tier: str
    # The atoms this module recognised, and the ones it passed through. Both are
    # carried so a partly-decoded guard is visibly partly decoded rather than
    # reading as though the whole condition were understood.
    decoded: tuple[str, ...] = ()
    verbatim_atoms: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        """Nothing in this guard is still implementation language.

        An unconditional guard qualifies: "always" is a complete statement of the
        condition, and it has no atoms to leave untranslated.
        """
        return not self.verbatim_atoms


def decode_atom(atom: str, resource: str = "") -> str:
    """One conjunct in business language, or "" if this module cannot say it.

    `resource` is the noun the presence idiom is about, established from the
    endpoint's path -- never from the guard's own variable, which is `t` at 42
    different endpoints because it comes from one shared helper in
    `athena-common`. Keying on the variable would call every resource in the
    estate the same thing, which is the mistake `unfolding.resource_of` exists
    to avoid.
    """
    literals = _conjuncts(atom)
    if not literals or len(literals) != 1:
        return ""
    inner, negated = next(iter(literals))

    if inner in _MINTED:
        positive, negative = _MINTED[inner]
        return negative if negated else positive

    m = _PRESENCE.match(inner.strip())
    if m:
        noun = (resource or "record").strip()
        # `isEmpty` reads as absent, `isPresent` as present; a NOT flips it.
        # Identical to `presence_sense`'s table, which the unfolding pass has
        # already acted on -- this only puts it into words.
        present = (m.group(2) == "isPresent") != negated
        return f"the {noun} exists" if present else f"no {noun} exists"

    return ""


def describe_guard(guard: str, resource: str = "") -> Wording:
    """The whole guard in business language, per X-7's cascade at tier 2.

    An empty guard is unconditional and says so, rather than rendering as a
    blank: "always" is a real statement about the behaviour and a reviewer needs
    to see it to disagree with it.
    """
    text = (guard or "").strip()
    if not text:
        return Wording(text="always", tier=TIER_CODE_CONVENTION)  # unconditional

    literals = _conjuncts(text)
    if literals is None:
        # An OR. `_conjuncts` refuses these and so does this: deciding what a
        # disjunction says needs real boolean reasoning, and a half-understood
        # rendering of a condition is worse than the condition itself.
        return Wording(text=text, tier=TIER_VERBATIM, verbatim_atoms=(text,))

    # Split on the same top-level AND `_conjuncts` uses, but keep the atoms in
    # their written order: a guard reads as the order a tester meets it, and a
    # set does not preserve that.
    atoms = [a.strip() for a in re.split(r"\s+AND\s+", text, flags=re.I) if a.strip()]

    parts, decoded, verbatim = [], [], []
    for atom in atoms:
        said = decode_atom(atom, resource)
        if said:
            parts.append(said)
            decoded.append(atom)
        else:
            parts.append(atom)
            verbatim.append(atom)

    if not decoded:
        return Wording(text=text, tier=TIER_VERBATIM, verbatim_atoms=tuple(verbatim))

    return Wording(text=" and ".join(parts), tier=TIER_CODE_CONVENTION,
                   decoded=tuple(decoded), verbatim_atoms=tuple(verbatim))
