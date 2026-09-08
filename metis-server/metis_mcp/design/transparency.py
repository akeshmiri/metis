"""How much of the inside was known when a guard was recovered.

**White, grey and black box are a property of the evidence, not a choice.** A
test design usually treats box transparency as a decision somebody makes — "we
will do white-box testing here". Métis cannot make that decision, and it does not
have to: it recovered every guard from something, and *what* it recovered it from
already says how much of the inside was visible. A guard the call graph resolved
is internal knowledge. A guard that is one `@ResponseStatus` annotation is the
interface and nothing behind it. Those are not the same claim and never were.

**This reads `guard_claim`, which was written and never read.**
`rendering/contract.py` records it as a deferred read in as many words: *"how the
guard was arrived at (`contract.LINK_*`). Nothing reads it back today. Returns
when a rendered case distinguishes a guard recovered from a branch from one
derived from four annotations."* That is this module, and this is that condition
being met.

**The vocabulary is open in practice, and the mapping refuses to guess.**
`code_analysis/contract.py` declares five `LINK_*` values ordered weakest-claim-
last, and `synthesis.py` emits a sixth — `advice-scope` — that is in no such
list. So an unrecognised claim maps to `unknown` and is **reported as
unrecognised**, never bucketed into the nearest neighbour. A transparency
silently guessed wrong is worse than one missing: it tells a reader the inside
was visible when nobody looked.

**`name-match` is `unknown`, not white.** It is the one mapping worth arguing
about, and X-6 settles it: a disclosed name heuristic produces no knowledge of
the inside at all. Grading it as structural would let a route called
`validateAndSave` claim the branch coverage of a branch nobody found.

**What this does not decide.** Which level a test runs at — `build_levels` does
that from viability and recovered evidence. Transparency *constrains* the level
(you cannot assert a private branch through an HTTP call) and does not choose it,
and `levels_for` returns what the box permits rather than what the design picked.
"""
from __future__ import annotations

from dataclasses import dataclass

from metis_mcp.mbt.test_levels import (API_FUNCTIONAL, E2E, INTEGRATION,
                                       PERFORMANCE, UNIT, WEB_FUNCTIONAL)

WHITE = "white-box"
GREY = "grey-box"
BLACK = "black-box"
UNKNOWN = "unknown"
BOXES = (WHITE, GREY, BLACK, UNKNOWN)


@dataclass(frozen=True)
class Transparency:
    """What was visible when a guard was recovered, and what follows from it."""

    box: str
    #: The `guard_claim` value this came from, quoted so a reader can check it.
    claim: str
    #: Why the claim means this much visibility.
    because: str
    #: Levels that can actually assert a condition known to this depth.
    levels: tuple[str, ...]
    #: What a test at this transparency can establish.
    verifies: str
    #: What it cannot, however well written. Mandatory — a transparency with no
    #: stated limit reads as sufficiency.
    cannot: str


#: Every level, for the two boxes that constrain nothing. Ordered as
#: `test_levels.LEVELS` orders them so a reader meets one sequence.
_ALL = (UNIT, INTEGRATION, API_FUNCTIONAL, WEB_FUNCTIONAL, E2E, PERFORMANCE)

#: `guard_claim` -> transparency. The keys are the values the extractors
#: actually emit, which is a wider set than `contract.LINK_*` declares.
_BY_CLAIM: dict[str, Transparency] = {
    "resolved": Transparency(
        WHITE, "resolved",
        "the call graph resolved the outcome to this entry point, so the path "
        "through the code is known and not inferred",
        (UNIT, INTEGRATION),
        "that the specific branch is taken, and that its complement is taken "
        "when the condition does not hold",
        "that the branch is the RIGHT one. Structural knowledge says what the "
        "code does; whether it should do that is validation (S-19)"),
    "ast-enclosure": Transparency(
        WHITE, "ast-enclosure",
        "the enclosing control structure guards it — a real branch in the "
        "source, not a declaration about one",
        (UNIT, INTEGRATION),
        "branch and condition coverage over the guard's atomic conditions, "
        "bounded by the short-circuit chain (GD-1..GD-9)",
        "anything about a path the extractor did not reach. Coverage of a "
        "recovered branch is not coverage of the method"),
    "derived-validation": Transparency(
        GREY, "derived-validation",
        "the outcome is declared and its cause was traced — the interface says "
        "what happens and the code says why, so part of the inside is visible",
        (INTEGRATION, API_FUNCTIONAL),
        "that a declared constraint produces the declared outcome, driven "
        "through the interface with knowledge of which constraint to violate",
        "that no OTHER cause produces the same outcome. One traced cause is "
        "not an enumeration of causes"),
    "advice-scope": Transparency(
        GREY, "advice-scope",
        "a single exception cause was traced to the handler that turns it into "
        "a status. The handler is declared; the throw was found",
        (INTEGRATION, API_FUNCTIONAL),
        "that the traced exception reaches the handler and produces the status "
        "the handler declares",
        "which of several causes a given call raises, where more than one was "
        "found — GD-9 refuses that, and the precondition stays generic"),
    "declared": Transparency(
        BLACK, "declared",
        "an annotation says so and nothing was traced. This is the interface's "
        "own statement about itself",
        (API_FUNCTIONAL, WEB_FUNCTIONAL, E2E),
        "that the interface behaves as it declares — which is exactly what a "
        "consumer depends on, and is a real and sufficient claim for one",
        "whether the declaration is implemented at all. A declared 404 nothing "
        "raises passes every black-box test that never provokes it"),
    "name-match": Transparency(
        UNKNOWN, "name-match",
        "a disclosed name heuristic. **X-6: a name is not knowledge of the "
        "inside**, and grading this as structural would let a route called "
        "`validateAndSave` claim the coverage of a branch nobody found",
        (),
        "nothing on its own. The behaviour may be real; the evidence for it is "
        "an identifier",
        "everything. Treat the guard as unconfirmed and say so, rather than "
        "choosing a transparency it does not support"),
    "": Transparency(
        UNKNOWN, "",
        "the extractor recorded no claim. This is the common case on models "
        "extracted before `guard_claim` was populated, and it means NOBODY "
        "LOOKED — never that the guard is shallow",
        (),
        "nothing that depends on knowing the inside",
        "any transparency claim at all. Re-extract if the distinction matters "
        "to this design"),
}


def for_claim(claim: str) -> Transparency:
    """The transparency a `guard_claim` supports, or an honest `unknown`.

    **An unrecognised claim is reported, not bucketed.** `synthesis.py` already
    emits one value (`advice-scope`) that `contract.LINK_*` does not declare, so
    a seventh appearing is likely rather than hypothetical. Mapping it to its
    nearest neighbour would put a transparency claim on evidence nobody has
    classified.
    """
    known = _BY_CLAIM.get(claim or "")
    if known is not None:
        return known
    return Transparency(
        UNKNOWN, claim,
        f"`{claim}` is not a claim this mapping recognises. It was recorded by "
        "an extractor and never classified here, so no transparency is inferred "
        "from it",
        (),
        "nothing, until somebody classifies this claim",
        "any transparency claim. Add it to `design/transparency.py` with the "
        "visibility it actually implies rather than reading it as the nearest "
        "value that already exists")


def for_transition(transition) -> Transparency:
    """The transparency behind one transition's guard."""
    return for_claim(getattr(transition, "guard_claim", "") or "")


def levels_for(box: str) -> tuple[str, ...]:
    """Levels that can assert a condition known to this depth.

    `unknown` returns every level rather than none: not knowing how the guard
    was recovered constrains nothing, and returning an empty tuple would read as
    "no level can test this", which is a much stronger claim than the evidence
    supports.
    """
    if box == UNKNOWN:
        return _ALL
    for entry in _BY_CLAIM.values():
        if entry.box == box:
            return entry.levels
    return ()


def describe() -> dict:
    """The mapping, for a tool and for a test."""
    return {
        "boxes": list(BOXES),
        "claims": {
            claim: {"box": t.box, "because": t.because, "levels": list(t.levels),
                    "verifies": t.verifies, "cannot": t.cannot}
            for claim, t in _BY_CLAIM.items()},
        "means": (
            "how much of the inside was visible when each guard was recovered, "
            "read from `guard_claim` — a property of the evidence, not a "
            "testing strategy somebody chose"),
        "does_not_claim": (
            "that a transparency is sufficient. Every entry states what it "
            "cannot establish, and an unrecognised claim is `unknown` rather "
            "than the nearest value that already exists"),
    }
