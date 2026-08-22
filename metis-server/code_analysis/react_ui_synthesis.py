"""
React UI synthesis: `react-ui` facts -> a Web-surface model (spec §5.2, M-2, M-3).

**Why a second UI synthesiser.** `ui_synthesis.py` reads `triggers` and
`outcomes` -- the `js-ui` pack's keys, recovered from `addEventListener` and DOM
mutations. `react-ui` emits neither; it emits `screen`, `ui_states` and
`api_calls`, because jssrc2cpg keeps JSX as raw text and event bindings are not
structurally recoverable. Feeding one pack's report to the other's synthesiser
returns "no event handlers recovered", which is true and useless.

**What was being thrown away.** The pack recovers 66 `ui_states` across 9 real
pages, each `setStatus`-style variable taking exactly `loading`, `ready` and
`error`. Nothing read them. The six athena UI models were hand-derived
off-pipeline into two states -- `PageLoaded` and `Ready` -- so **every error
state and every loading state was discarded**, and the error path, the thing most
worth testing, was not in the graph at all.

**Regions, not a product.** A page carries up to four independent status
variables (`setStatus`, `setSummaryStatus`, `setTrendStatus`, `setDriftStatus`).
Modelling a page as one machine over all of them would give 3^4 = 81 states of
which almost none are reachable independently. They are **independent regions**:
each panel loads on its own, so each variable is its own small machine and the
model never takes their product.

    MetricWorkspacePage.opened --[the summary request completes]--> summary=ready
                               --[the summary request completes]--> summary=error
                               --[the trend request completes]-->   trend=ready   ...

**Regions are orthogonal, and this model does not pretend otherwise.** Opening a
page starts every region loading *at once*; that is concurrency, not a choice.
Modelling it as one `open` transition per region made three siblings share one
trigger, which the determinism check correctly called ambiguous -- the model was
claiming the page picks one panel to load. So `open` leads to a single
`<Page>.opened` state and each region resolves from there under its own trigger.

The consequence, stated rather than discovered: a path covers **one region's
outcome**. "Summary ready *and* trend failed" is a combination this model cannot
express, because expressing it means taking the product of the regions -- 3^4 for
a four-region page, almost all of it unreachable.

**This is where UI guards come from.** `ui_synthesis.py` writes `guard=""`
unconditionally and every UI model in the estate has zero guarded transitions.
Here the two outcomes of one panel load are distinguished by a real, observable
condition -- the request succeeded or it did not -- which is what makes the pair
deterministic (M-17) instead of two unguarded siblings on one trigger.

**What is not recovered, and is not invented.** No click, submit or type action:
the pack says plainly that JSX handler bindings are not structural, and refuses
to guess. No page-to-page navigation. No element selectors. A model from this
source describes what a page *shows*, not what a user *does to it* -- and saying
so is better than a fabricated `click` that no test can bind to.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from metis_mcp.mbt.model import IMPLEMENTED, QUARANTINE, Model, State, Transition

# The state a page region is in before its request resolves. Every recovered
# variable has exactly these three values on the pilot estate.
LOADING = "loading"
READY = "ready"
ERROR = "error"

# The guard, in the form the existing complementarity checker understands.
# Prose ("the request succeeded") is unparseable, so `guards_conflict` flags it
# unverifiable and M-17 blocks -- correct, and useless if every UI guard is prose.
# A negated literal is recognised as mutually exclusive by propositional
# structure, which is exactly what these two outcomes are.
SUCCEEDED = "request_succeeded"

# `setSummaryStatus` -> `summary`; `setStatus` -> the page's own default region.
_SETTER = re.compile(r"^set([A-Za-z0-9]*?)Status$")
DEFAULT_REGION = "page"

INITIAL_STATE = "PageLoaded"


def region_of(setter: str) -> str:
    """X-7 tier 2: the region name is the code's own convention, not a guess."""
    match = _SETTER.match(setter or "")
    if not match:
        return (setter or DEFAULT_REGION).strip() or DEFAULT_REGION
    name = match.group(1)
    return (name[:1].lower() + name[1:]) if name else DEFAULT_REGION


def state_id(screen: str, region: str, value: str) -> str:
    return f"{screen}.{region}={value}"


def state_label(screen: str, region: str, value: str) -> str:
    """What a reviewer reads: `MetricWorkspacePage summary error`."""
    return f"{screen} {region} {value}"


@dataclass
class ReactUiSynthesisResult:
    model: Model | None = None
    pages: dict = field(default_factory=dict)      # screen -> [region, ...]
    findings: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.model is not None and not self.errors


def synthesise_react_ui(facts: dict, journey: str = "",
                        screens: set[str] | None = None) -> ReactUiSynthesisResult:
    """Build a `ui`-surface model from a `react-ui` report.

    `screens` scopes a multi-page report to the pages of one journey, the same
    way `--service` scopes the API side. Without it a single frontend report
    would produce one model containing every page of the estate.
    """
    result = ReactUiSynthesisResult()

    ui_states = list(facts.get("ui_states", ()))
    if not ui_states:
        # Distinguishable from "this frontend has no state": say which (§5.8).
        result.errors.append(
            "no ui_states recovered. Either the pack did not run over this "
            "frontend, or its status setters do not match the recovered "
            "convention. It is not evidence that the pages have no states.")
        return result

    # screen -> region -> {values}
    by_page: dict[str, dict[str, set[str]]] = {}
    for row in ui_states:
        screen = row.get("screen") or ""
        if not screen or (screens and screen not in screens):
            continue
        region = region_of(row.get("setter", ""))
        value = str(row.get("value", "")).strip()
        if not value:
            continue
        by_page.setdefault(screen, {}).setdefault(region, set()).add(value)

    if not by_page:
        result.errors.append(
            f"no ui_states matched the requested screens "
            f"({', '.join(sorted(screens or ())) or 'any'}). This report covers: "
            f"{', '.join(sorted({r.get('screen','') for r in ui_states if r.get('screen')}))}")
        return result

    states: dict[str, State] = {
        INITIAL_STATE: State(id=INITIAL_STATE, name=INITIAL_STATE, surface="ui",
                             is_initial=True, lifecycle_state=QUARANTINE)
    }
    transitions: dict[str, Transition] = {}

    # Which endpoint a region's data comes from, where the pack recovered one.
    # Used as evidence on the trigger, never to invent a call that was not seen.
    endpoints_by_screen: dict[str, list[str]] = {}
    for call in facts.get("api_calls", ()):
        screen = call.get("screen") or ""
        endpoint = call.get("endpoint") or ""
        if screen and endpoint:
            endpoints_by_screen.setdefault(screen, []).append(endpoint)

    for screen in sorted(by_page):
        regions = by_page[screen]
        result.pages[screen] = sorted(regions)

        # One state for "the page is open and nothing has resolved yet", and one
        # transition into it. Every region resolves from here.
        opened_id = f"{screen}.opened"
        states[opened_id] = State(
            id=opened_id, name=f"{screen} opened", surface="ui",
            lifecycle_state=QUARANTINE, page=screen, condition="opened")
        open_tid = f"ui::{screen}::open"
        transitions[open_tid] = Transition(
            id=open_tid, source=INITIAL_STATE, trigger=f"open {screen}",
            target=opened_id, guard="", implementation_status=IMPLEMENTED,
            lifecycle_state=QUARANTINE)
        for region in sorted(regions):
            values = regions[region]
            for value in sorted(values - {LOADING}):
                sid = state_id(screen, region, value)
                if sid not in states:
                    states[sid] = State(
                        id=sid, name=state_label(screen, region, value),
                        surface="ui", lifecycle_state=QUARANTINE,
                        page=screen, condition=f"{region}={value}")

            if LOADING not in values:
                # Without a loading value there is no recovered "not resolved
                # yet", so nothing establishes the precondition. Reported rather
                # than papered over with an invented entry point.
                result.unresolved.append(
                    f"{screen}.{region}: no '{LOADING}' state recovered; its "
                    f"{sorted(values)} state(s) have no recovered entry")
                continue

            # The request resolves one way or the other. **This is the guard the
            # UI surface has never had**: two outcomes of one trigger,
            # distinguished by an observable condition rather than left as
            # unguarded siblings (M-17).
            hint = ""
            candidates = [e for e in endpoints_by_screen.get(screen, ())
                          if region != DEFAULT_REGION and region in e.lower()]
            if candidates:
                hint = f" ({sorted(set(candidates))[0]})"

            for value in sorted(values - {LOADING}):
                tid = f"ui::{screen}::{region}::{value}"
                transitions[tid] = Transition(
                    id=tid, source=opened_id,
                    trigger=f"the {region} request completes{hint}",
                    target=state_id(screen, region, value),
                    guard=(SUCCEEDED if value == READY else f"NOT ({SUCCEEDED})"),
                    implementation_status=IMPLEMENTED,
                    lifecycle_state=QUARANTINE)

    for row in facts.get("unresolved_calls", ()):
        # X-13: what the pack could not resolve is carried through, not dropped.
        result.findings.append(
            f"{row.get('screen','?')}: unresolved call — {row.get('reason','no reason given')}")

    result.model = Model(id=f"{journey}-ui", states=states, transitions=transitions)
    return result


def format_react_ui(result: ReactUiSynthesisResult) -> str:
    if not result.ok:
        return "\n".join(["React UI synthesis FAILED", *(f"  {e}" for e in result.errors)])
    model = result.model
    lines = [f"React UI synthesis — {model.id}",
             f"  {len(result.pages)} page(s), {len(model.states)} state(s), "
             f"{len(model.transitions)} transition(s)"]
    for screen, regions in sorted(result.pages.items()):
        lines.append(f"    {screen}: {', '.join(regions)}")
    guarded = sum(1 for t in model.transitions.values() if t.guard)
    lines += ["", f"  {guarded} guarded transition(s) — the two outcomes of a panel "
                  f"load are distinguished, not left ambiguous"]
    if result.unresolved:
        lines += ["", "  NO ENTRY RECOVERED:"]
        lines += [f"    {u}" for u in result.unresolved]
    if result.findings:
        lines += ["", "  FINDINGS:"]
        lines += [f"    {f}" for f in result.findings]
    lines += ["",
              "  No click, submit or type action is modelled: JSX handler bindings",
              "  are not structurally recoverable and are not guessed (§5.8)."]
    return "\n".join(lines)
