"""What a test at each level is obliged to do, beyond asserting the behaviour.

**The gap this closes.** `build_levels` assigns a level — unit, integration,
api_functional, web_functional, e2e, performance — and attaches nothing to it. A
level on its own is a location, and two people handed the same location write
tests that differ in every respect that makes a suite maintainable: whether the
dependency is real, whether the selector was authored or guessed, whether the
data is cleaned up, whether a timing assumption is baked in.

The sibling practice carries this as a per-level prose fragment substituted into
the design document. That works and it drifts: the fragment is a template a model
reproduces, which is the failure a served shape exists to remove
(`design/sections.py`). So the obligations are data, keyed on the levels module,
and rendered into a column.

**The levels are imported, never restated.** `mbt/test_levels.LEVELS` is the
source. A second copy here is how a design starts reporting a level the coverage
ledger has never heard of, and `test_design_sections.py` asserts every level has
an entry and that no entry names a level that does not exist.

**Each obligation says who can check it, and most of them are people.** That is
the honest half and the reason this is not a lint rule. `checkable` names the
module or tool that decides; an obligation with no checker is a **person's**, and
saying so is what stops the column reading as a list of things Métis verified.
**Most are not checkable**, and no count is written here — `describe()["counts"]`
serves it, and a hand-written number beside a served one is the copy that goes
stale. Printing an unchecked obligation beside a checked one without the
distinction would be claiming checks that do not exist, which is what the marker
in `summarise` prevents.

**What this does not do.** It does not decide the level — `build_levels` does
that from viability and the recovered evidence. It does not refuse a test that
breaks an obligation; nothing here blocks. It states what the level asks for, so
a reviewer reading the design can see it before the tests exist rather than in
review afterwards.
"""
from __future__ import annotations

from dataclasses import dataclass

from metis_mcp.mbt.test_levels import LEVELS


@dataclass(frozen=True)
class Obligation:
    """One thing a test at a level must do, and who decides whether it did."""

    text: str
    #: The module or tool that can decide this. Empty means **a person decides**,
    #: which is the common case and is stated rather than implied.
    checkable: str = ""

    @property
    def is_checkable(self) -> bool:
        return bool(self.checkable)


#: Level -> the obligations a test at that level carries.
#:
#: Keyed on `LEVELS` and asserted complete in both directions. Order within a
#: level is the order a reviewer would ask them in, not an importance ranking —
#: there is no ranking here, and inventing one would be a judgement this module
#: has no basis for.
REQUIREMENTS: dict[str, tuple[Obligation, ...]] = {
    "unit": (
        Obligation("one assertion per case — a case checking two things cannot "
                   "say which one failed (T-1a)",
                   checkable="rendering/test_case.py"),
        Obligation("no I/O, no clock, no network. A unit test that reaches a "
                   "dependency is an integration test with a misleading name"),
        Obligation("the guard's atomic conditions are what is varied, not the "
                   "public behaviour — that is the level above"),
    ),
    "integration": (
        Obligation("the dependency is real, not a double. A test that mocks the "
                   "boundary it exists to exercise asserts the mock"),
        Obligation("cleanup ownership is stated. Whether reuse is safe depends "
                   "on stable data and on who tears it down, and both are "
                   "`asked` inputs Métis does not hold"),
        Obligation("the setup chain is the cost — `Path.setup_transition_ids`, "
                   "not the business verb in the route name",
                   checkable="design/builders.py:build_setup"),
    ),
    "api_functional": (
        Obligation("the status AND the body shape are asserted. A 200 with an "
                   "empty body passes a status-only test"),
        Obligation("the negative sits beside the positive. An endpoint's own "
                   "shape obliges it — a path parameter obliges a not-found, a "
                   "declared security requirement obliges a denial",
                   checkable="design/builders.py:build_obligations"),
        Obligation("values come from the accepted space, never a literal "
                   "(X-6e). `<string, length 3..40, required>` is the "
                   "assertion; a chosen example is a fixture",
                   checkable="rendering/contract.py"),
    ),
    "web_functional": (
        Obligation("the selector is **authored**. A UI element with no authored "
                   "selector raises rather than guessing one (X-6e) — a guessed "
                   "selector is a test that passes until the markup moves",
                   checkable="rendering/"),
        Obligation("no sleep. A timing assumption is an unverifiable guard "
                   "wearing a test's clothes"),
        Obligation("the guard the action inherits from the call beneath it is "
                   "asserted at one level or the other, and the design says "
                   "which (M-5c)"),
    ),
    "e2e": (
        Obligation("the journey crosses a surface, or it is not e2e. A "
                   "single-surface path at this level is an api_functional or "
                   "web_functional test paying e2e's setup cost"),
        Obligation("the setup chain is stated in full, because at this level it "
                   "is most of the runtime and all of the flakiness"),
        Obligation("what it asserts is the crossing itself. Re-asserting each "
                   "surface's own behaviour here duplicates the two levels "
                   "below and fails for their reasons"),
    ),
    "performance": (
        Obligation("a sized target exists. Without one the verdict is "
                   "`no-basis`, and a load test with no threshold produces a "
                   "number nobody can call a pass or a failure",
                   checkable="design/builders.py:build_performance"),
        Obligation("the load profile is a person's. Métis reports which calls "
                   "are worth driving; how many concurrent users is a fact "
                   "about the business, not about the code"),
        Obligation("it runs against a system, so it is `METIS_EXECUTE=run` and "
                   "the result is `observed_from_running_system` — never merged "
                   "with a fact recovered from source"),
    ),
}


def for_level(level: str) -> tuple[Obligation, ...]:
    """The obligations for one level. Unknown levels get nothing, not a guess."""
    return REQUIREMENTS.get(level, ())


def summarise(level: str) -> str:
    """One cell: the obligations, with the checkable ones marked.

    **The marker is the point of the cell.** A reader scanning the column has to
    be able to tell an obligation Métis decides from one they decide, without
    opening this module. `[checked]` says a tool decides it; everything else is
    theirs.
    """
    obligations = for_level(level)
    if not obligations:
        return ("no obligations recorded for this level — which means the level "
                "is not one Métis assigns, not that a test there is unconstrained")
    return "; ".join(
        f"{o.text}{' [checked]' if o.is_checkable else ''}" for o in obligations)


def describe() -> dict:
    """The map, for a tool and for a test."""
    return {
        "levels": {
            level: [{"text": o.text, "checkable": o.checkable,
                     "decided_by": o.checkable or "a person"}
                    for o in REQUIREMENTS[level]]
            for level in LEVELS},
        "counts": {
            "levels": len(LEVELS),
            "obligations": sum(len(v) for v in REQUIREMENTS.values()),
            "checkable": sum(1 for v in REQUIREMENTS.values()
                             for o in v if o.is_checkable),
        },
        "means": (
            "what a test at each level is obliged to do beyond asserting the "
            "behaviour, and who decides whether it did"),
        "does_not_claim": (
            "that Métis verified any of these. Most are a reviewer's, which the "
            "`decided_by` field states rather than implies; nothing here blocks"),
    }
