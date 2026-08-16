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
    payload["act"] = _act_detail(source.surface, transition.trigger)
    payload["assert"] = (
        {"expected_state": target.name, "observable": UNRECOVERABLE}
        if step.is_assertion else None
    )
    payload["anchor"] = UNRECOVERABLE  # populated once extraction lands (M-14)
    return payload


def _act_detail(surface: str, trigger: str) -> dict:
    """Surface-specific act detail, with unknowns marked rather than invented."""
    if surface == "api":
        return {"kind": "api_call", "method": UNRECOVERABLE, "path": UNRECOVERABLE,
                "derived_from_trigger": trigger}
    if surface == "ui":
        return {"kind": "ui_action", "action": UNRECOVERABLE, "element": UNRECOVERABLE,
                "derived_from_trigger": trigger}
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
            {"condition": r.condition, "steps": list(r.steps)}
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
