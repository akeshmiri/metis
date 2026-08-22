"""
Automation-support payload (application spec §7.4a).

R8 chose human-readable test cases over executable code. But a case that is only
prose forces an automation engineer to re-derive from English what the model
already knows precisely. Every case therefore carries a machine-readable
companion: prose for the tester, payload for whoever automates it later.

Three rules govern it:

  * **T-9b** derived, never authored -- it restates model facts in a consumable
    shape and introduces nothing.
  * **T-9c** conditions, not values. It states that a step requires
    `!credentials_valid`; it does not invent a username.
  * **T-9d** an unrecoverable detail is **absent and marked**, never guessed. A
    fabricated selector looks usable, which makes it worse than an empty field.
"""
from __future__ import annotations

from metis_mcp.mbt.model import Model
from metis_mcp.rendering.test_case import Step, TestCase

UNRECOVERABLE = "__unrecoverable__"


def _step_payload(model: Model, step: Step) -> dict:
    transition = model.transitions[step.transition_id]
    source = model.states[transition.source]
    target = model.states[transition.target]

    payload: dict = {
        "transition_id": transition.id,
        "surface": source.surface,
        "trigger": transition.trigger,
        "from_state": source.name,
        "to_state": target.name,
        # T-9c: the condition, never a solved value.
        "guard": transition.guard or None,
        "is_assertion": step.is_assertion,
        "wording_tier": step.wording_tier,
    }

    # T-9d: fields we cannot recover are present and explicitly marked, so an
    # automation layer can distinguish "not applicable" from "not yet known".
    payload["act"] = _act_detail(source.surface, transition.trigger, transition, model)
    payload["assert"] = (
        {"expected_state": target.name, "observable": UNRECOVERABLE}
        if step.is_assertion else None
    )
    # M-14 / T-9a: the guard's own `file:line@commit`. This was marked
    # unrecoverable while the pack was already emitting it and synthesis was
    # throwing it away.
    payload["anchor"] = transition.guard_anchor or UNRECOVERABLE
    return payload


def _act_detail(surface: str, trigger: str, transition=None, model=None) -> dict:
    """Surface-specific act detail, with unknowns marked rather than invented.

    **Method and path are not unknowns.** They were marked `UNRECOVERABLE` while
    the trigger sitting beside them read `GET /metric/{id}` -- T-9d exists so an
    automation layer can tell "not applicable" from "not yet known", and marking
    a field we hold makes it say the wrong one.
    """
    if surface == "api":
        verb, _, path = trigger.partition(" ")
        detail = {"kind": "api_call",
                  "method": verb.upper() if verb.isalpha() else UNRECOVERABLE,
                  "path": path.strip() or UNRECOVERABLE,
                  "derived_from_trigger": trigger}
        if transition is not None:
            # Conditions on the request, never values (T-9c).
            detail["inputs"] = [dict(p) for p in (transition.inputs or ())]
            detail["security"] = [dict(s) for s in (transition.security or ())]
            if transition.outcome_status is not None:
                detail["expected_status"] = transition.outcome_status
        return detail
    if surface == "ui":
        # Same defect the API branch had: both fields were marked unrecoverable
        # while the trigger beside them read `click toggle`. T-9d exists so an
        # automation layer can tell "not applicable" from "not yet known", and
        # marking a field we hold makes it say the wrong one.
        #
        # The split is honest about what each pack recovers: `js-ui` gives a real
        # event and a receiver *variable* (never a selector, which it refuses to
        # guess); `react-ui` gives no action at all, because JSX handler bindings
        # are not structurally recoverable — so that stays marked.
        verb, _, rest = trigger.partition(" ")
        known_events = ("click", "submit", "change", "input", "scroll", "open")
        recognised = verb.lower() in known_events
        detail = {"kind": "ui_action",
                  "action": verb.lower() if recognised else UNRECOVERABLE,
                  # Only meaningful when the trigger really is `<event> <target>`.
                  # `react-ui` triggers read "the summary request completes", and
                  # splitting that on the first space yields a fragment of a
                  # sentence — a field that looks like a target and is not.
                  "element_hint": (rest.strip() or UNRECOVERABLE) if recognised
                                  else UNRECOVERABLE,
                  # Never a selector: `js-ui` refuses to guess one, and an
                  # automation layer must not bind to a variable name as if it
                  # were one.
                  "element": UNRECOVERABLE,
                  "derived_from_trigger": trigger}
        if transition is not None:
            state = model.states.get(transition.target) if model else None
            if state is not None and getattr(state, "condition", ""):
                # The expected page condition — what a tester actually asserts.
                detail["expected_condition"] = state.condition
                detail["page"] = getattr(state, "page", "")
        return detail
    return {"kind": "unknown_surface", "derived_from_trigger": trigger}


def build_payload(model: Model, case: TestCase) -> dict:
    """The machine-readable companion to one rendered test case."""
    return {
        "schema": "metis.automation-payload/1",
        "case_id": case.id,
        "model_id": case.model_id,
        "criterion": case.criterion,
        "target_key": case.target_key,
        "precondition_group": list(case.precondition_group),
        "setup": [_step_payload(model, s) for s in case.precondition_steps],
        "act": _step_payload(model, case.act_step),
        # Structured, not flattened to strings: an automation layer needs to know
        # which steps each condition applies to (T-9c -- conditions, not values).
        "data_requirements": [
            {"condition": r.condition, "steps": list(r.steps), "kind": r.kind}
            for r in case.data_requirements
        ],
        "labels": list(case.labels),
    }


def unrecoverable_fields(payload: dict) -> list[str]:
    """Every field explicitly marked unrecoverable, as dotted paths.

    Exposed so a report can state what an automation layer will still have to
    supply, rather than leaving it to be discovered during implementation.
    """
    found: list[str] = []

    def walk(node, prefix: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{prefix}.{key}" if prefix else key)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{prefix}[{index}]")
        elif node == UNRECOVERABLE:
            found.append(prefix)

    walk(payload, "")
    return found
