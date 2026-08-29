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
from metis_mcp.rendering.test_case import Step, TestCase, observable_result

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
        # The guard said in business language (D-8: a rendering of the raw
        # condition, which is never overwritten). Carried so a machine consumer
        # sees what a reviewer approved and not only what the code evaluates —
        # it reached the prose objective and stopped there.
        "guard_wording": getattr(transition, "guard_wording", "") or "",
        # **The ordered conditions, not the joined string.** `guard` is one
        # expression; a `Check` is one condition, at one line, in the position it
        # holds in the evaluation sequence — and that ordering is a test data
        # requirement, not trivia: if check 1 short-circuits, no fixture reaches
        # check 3 without satisfying check 1 first. Splitting the string cannot
        # recover it, and until now the expressions reached the payload only
        # inside `target_key`, which is an identity and not a stated fact.
        "guard_checks": [
            {"expression": c.expression, "order": c.order,
             "dimension_class": getattr(c, "dimension_class", ""),
             "anchor": getattr(c, "anchor", "")}
            for c in sorted(getattr(transition, "checks", ()) or (),
                            key=lambda c: getattr(c, "order", 0))
        ],
        "is_assertion": step.is_assertion,
        "wording_tier": step.wording_tier,
    }

    # T-9d: fields we cannot recover are present and explicitly marked, so an
    # automation layer can distinguish "not applicable" from "not yet known".
    payload["act"] = _act_detail(source.surface, transition.trigger, transition, model)
    payload["assert"] = _assert_detail(transition, target) if step.is_assertion else None
    # M-14 / T-9a: the guard's own `file:line@commit`. This was marked
    # unrecoverable while the pack was already emitting it and synthesis was
    # throwing it away.
    payload["anchor"] = transition.guard_anchor or UNRECOVERABLE
    return payload


def _assert_detail(transition, target) -> dict:
    """What a validation step can actually check about the target state.

    **This was `{"expected_state": name, "observable": UNRECOVERABLE}` —
    unconditionally.** The marker was not a finding about the model; it was
    hardcoded, so a transition whose status and response body were both recovered
    still reached automation as "nothing observable". The prose renderer beside
    it had it right the whole time: `observable_result` renders "200 with
    RecordDto" from exactly these fields, so the human-readable case stated the
    expectation while the machine payload next to it said nothing was known.
    T-9b — the payload restates model facts — was not being met.

    `observable_result` is reused rather than reimplemented, so the sentence a
    tester reads and the fact an emitter asserts cannot drift.

    **An empty `response_body` is a fact, not a gap.** `ResponseEntity<Void>`
    returns nothing and a test can assert that (M-2), so `expected_body` is ""
    where nothing comes back and `observable` falls to `UNRECOVERABLE` only when
    the status is absent too — T-9d, but meaning it rather than announcing it on
    every step. This only holds while every loader carries the field: a loader
    that drops it turns "no body" into a false assertion, which is why
    `cli.read_source` had to start reading it.
    """
    detail: dict = {"expected_state": target.name, "surface": target.surface}

    if target.surface == "api":
        status = transition.outcome_status
        detail["expected_status"] = status
        detail["expected_body"] = (getattr(transition, "response_body", "") or "").strip()
        media = tuple(getattr(transition, "media_types", ()) or ())
        if media:
            detail["media_types"] = list(media)
        detail["observable"] = (observable_result(transition, target)
                                if status is not None else UNRECOVERABLE)
        return detail

    condition = (getattr(target, "condition", "") or "").strip()
    detail["expected_condition"] = condition
    # Unconditional, unlike `_act_detail`'s copy, which carries `page` only
    # alongside a condition — so a page with no condition never reached the
    # payload and a UI case could not say where it was.
    detail["page"] = getattr(target, "page", "")
    detail["observable"] = condition or UNRECOVERABLE
    return detail


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
        # **Why this case exists.** A technique that varies the DATA produces
        # several cases over one walk, distinguished only by what the data must
        # be — `length = 65 (above the boundary of @Size(max=64))`. The prose
        # renders it as "Why this case"; the payload did not carry it, so a
        # generated artefact showed three near-identical tests with nothing
        # saying what made them different. That is the whole output of
        # `mbt.techniques` — boundary analysis and the declared constraints
        # (GD-3) — arriving nowhere a runner could see it.
        "data_note": case.data_note or "",
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


# ---------------------------------------------------------------------------
# Resolving a payload against authored fixtures (T-9c, X-6e)
# ---------------------------------------------------------------------------
#
# The payload states what the model recovered and marks what it did not. A
# fixtures file supplies the missing half. Joining them is deliberately a
# separate step producing a separate document, rather than an option on
# `build_payload`: the unresolved payload is the honest record of what the CODE
# says, and a reader has to be able to tell a fact recovered from source from a
# value a person chose. Merging them in place would destroy exactly that
# distinction.

RESOLVED_VERSION = "metis.resolved-payload/1"


def resolve_payload(payload: dict, fixtures) -> dict:
    """`payload` with authored selectors and values filled in, and a record of it.

    Returns a NEW document carrying:

      * `resolved`   — the payload with fixtures applied
      * `supplied`   — dotted path -> the fixture key that filled it
      * `unresolved` — dotted paths still `UNRECOVERABLE`, in the payload's order
      * `unused`     — fixture keys that matched nothing

    **`unused` is not noise.** A fixture that matched nothing is the shape of a
    renamed element or a typo, and it is invisible unless something says so —
    the same "report which side missed" rule `mbt.link_proposals` follows. A
    generator that silently ignored it would emit a TODO next to a selector the
    author believed they had already supplied.

    Nothing is guessed: a field with no fixture keeps `UNRECOVERABLE`.
    """
    import copy

    resolved = copy.deepcopy(payload)
    supplied: dict[str, str] = {}
    used: set[str] = set()

    def fill(node, prefix: str):
        if isinstance(node, dict):
            for key, value in list(node.items()):
                path = f"{prefix}.{key}" if prefix else key
                if value == UNRECOVERABLE and key == "element":
                    # The element's own name is the lookup key, and the payload
                    # already carries it beside the unrecovered field.
                    hint = node.get("element_hint")
                    chosen = fixtures.selector_for(hint) if isinstance(hint, str) else ""
                    if chosen:
                        node[key] = chosen
                        supplied[path] = f"selectors.{hint}"
                        used.add(hint)
                        continue
                node[key] = fill(value, path)
            return node
        if isinstance(node, list):
            return [fill(v, f"{prefix}[{i}]") for i, v in enumerate(node)]
        return node

    fill(resolved, "")

    # Values apply to data requirements, which name a CONDITION and the steps it
    # constrains. The condition text is the key: it is what the author saw.
    for requirement in resolved.get("data_requirements", ()):
        condition = requirement.get("condition")
        if isinstance(condition, str) and fixtures.value_for(condition) is not None:
            requirement["value"] = fixtures.value_for(condition)
            supplied[f"data_requirements.{condition}"] = f"values.{condition}"
            used.add(condition)

    known = set(fixtures.selectors) | set(fixtures.values)
    return {
        "schema": RESOLVED_VERSION,
        "fixtures_source": fixtures.source,
        "resolved": resolved,
        "supplied": dict(sorted(supplied.items())),
        "unresolved": unrecoverable_fields(resolved),
        "unused": sorted(known - used),
    }
