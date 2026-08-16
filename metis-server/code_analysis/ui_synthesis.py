"""
UI-surface model synthesis, Layer 4 (application spec §5.2, M-2, M-3, M-5d).

Turns `packs/js-ui`'s recovered facts into a `ui`-surface Model. The API
counterpart lives in `synthesis.py`; this is deliberately a separate module
because the two surfaces recover genuinely different things -- a screen is not a
status code (M-3) -- and a shared "synthesise" that branched on surface would
hide that.

**What a UI state is here.** M-2 says a `ui` state is a screen, mode or message
shown. On a component-driven page that is the *observable signature* of a DOM
mutation: `aria-expanded=false`, `class=is-visible`, `class=active`. Those are
exactly what a tester can see and assert against, which is M-3's test.

**Unrecoverable signatures are dropped from the model and reported, never
guessed.** A mutation whose class or attribute name is computed at runtime is
real behaviour that this pack cannot see. Emitting a state called
`__unrecoverable__` would create an untestable precondition; §5.8's rule is to
report honestly rather than emit a degenerate model.

**M-5d is the finding, not an omission.** Where the recovered facts contain no
API call, every transition is client-side only: no `INVOKES` link is proposed,
and none of these transitions is a gap against any API model (A-17d). That is
stated in the result rather than left to be inferred from an empty list.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from metis_mcp.mbt.model import IMPLEMENTED, QUARANTINE, Model, State, Transition

UNRECOVERABLE = "__unrecoverable__"
INITIAL_STATE = "PageLoaded"

# Signatures that are literals but not observable states: a number, or a value
# that is plainly an event name rather than a class. Reported, not modelled.
_NOT_A_SIGNATURE = re.compile(r"^\d+$|^(click|focus|blur|scroll|mouseenter|mouseleave)$")


def state_name(kind: str, signature: str) -> str:
    """`class`/`is-visible` -> `IsVisible`; `attribute`/`aria-expanded|false` ->
    `AriaExpandedFalse`.

    Deterministic and endpoint-independent, exactly as the API side's
    `state_name` is: two handlers producing the same observable signature are
    producing one state, and must converge on one node.
    """
    parts = re.findall(r"[A-Za-z0-9]+", signature)
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Unnamed"


@dataclass
class UiSynthesisResult:
    model: Model | None = None
    errors: list[str] = field(default_factory=list)
    unrecoverable: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    api_calls: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.model is not None and bool(self.model.transitions)

    @property
    def is_client_side_only(self) -> bool:
        return not self.api_calls


def synthesise(facts: dict, journey: str = "") -> UiSynthesisResult:
    """Build a `ui`-surface model from a `js-ui` pack report."""
    result = UiSynthesisResult()
    triggers = {t["id"]: t for t in facts.get("triggers", ())}
    outcomes = list(facts.get("outcomes", ()))
    result.api_calls = list(facts.get("api_calls", ()))

    if not triggers:
        result.errors.append(
            "no event handlers recovered. Likely causes: the analysis unit does "
            "not include the handler registration, or the framework registers "
            "handlers declaratively rather than through addEventListener. This is "
            "NOT evidence that the page has no behaviour (§5.8)")
        return result

    states: dict[str, State] = {
        INITIAL_STATE: State(id=INITIAL_STATE, name=INITIAL_STATE, surface="ui",
                             is_initial=True, lifecycle_state=QUARANTINE)}
    transitions: dict[str, Transition] = {}

    for outcome in outcomes:
        signature = outcome.get("signature", "")
        trigger = triggers.get(outcome.get("trigger_id", ""))
        if trigger is None:
            continue
        if signature == UNRECOVERABLE:
            result.unrecoverable.append(
                f"{outcome['anchor']['file'].split('/')[-1]}:"
                f"{outcome['anchor']['line']} — a {outcome['kind']} mutation whose "
                f"name is computed at runtime. Real behaviour this pack cannot see; "
                f"not modelled, because a state nobody can name is a precondition "
                f"nobody can establish (§5.8, X-10)")
            continue
        if _NOT_A_SIGNATURE.match(signature):
            result.unrecoverable.append(
                f"{signature!r} is a literal but not an observable signature — "
                f"not modelled (M-3)")
            continue

        target = state_name(outcome["kind"], signature)
        if target not in states:
            states[target] = State(id=target, name=signature, surface="ui",
                                   lifecycle_state=QUARANTINE)

        event = trigger.get("event", "")
        element = trigger.get("element", UNRECOVERABLE)
        trigger_text = (f"{event} {element}" if element != UNRECOVERABLE
                        else f"{event} (element unrecoverable)")
        transition_id = f"ui::{INITIAL_STATE}::{event}_{element}::{target}"
        if transition_id in transitions:
            continue
        transitions[transition_id] = Transition(
            id=transition_id, source=INITIAL_STATE, trigger=trigger_text,
            target=target, guard="", implementation_status=IMPLEMENTED,
            lifecycle_state=QUARANTINE)

    if not transitions:
        result.errors.append(
            f"{len(triggers)} handler(s) recovered but no observable outcome could "
            f"be named. Every mutation's signature was computed at runtime; the "
            f"page has behaviour, this pack cannot see what it looks like (§5.8)")
        return result

    model = Model(id=f"{journey or 'ui'}-ui", states=states, transitions=transitions)
    model.reindex()
    result.model = model

    if result.is_client_side_only:
        result.findings.append(
            f"M-5d: zero API calls in {len(triggers)} handler(s). Every transition "
            f"is client-side only — navigation, validation or display. No INVOKES "
            f"link is proposed, and none of these is a gap against any API model "
            f"(A-17d). The absence is meaningful, not missing data")
    else:
        result.findings.append(
            f"{len(result.api_calls)} API call(s) recovered — each PROPOSES an "
            f"INVOKES link, for human confirmation (M-5g)")
    if result.unrecoverable:
        result.findings.append(
            f"{len(result.unrecoverable)} mutation(s) not modelled because their "
            f"signature is not statically recoverable. Reported, never guessed "
            f"(T-9d)")
    return result


def format_ui_synthesis(result: UiSynthesisResult) -> str:
    lines = ["UI synthesis"]
    if result.model:
        lines.append(f"  {len(result.model.states)} state(s), "
                     f"{len(result.model.transitions)} transition(s), all at Quarantine")
    else:
        lines.append("  no model")
    for error in result.errors:
        lines.append(f"  ERROR: {error}")
    for finding in result.findings:
        lines += ["", f"  {finding}"]
    if result.unrecoverable:
        lines += ["", "  NOT MODELLED (reported, never guessed):"]
        lines += [f"    {u}" for u in result.unrecoverable[:6]]
        if len(result.unrecoverable) > 6:
            lines.append(f"    ... and {len(result.unrecoverable) - 6} more")
    return "\n".join(lines)
