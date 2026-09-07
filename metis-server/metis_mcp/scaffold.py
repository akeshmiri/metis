"""
The handoff to a code generator that lives outside Métis (spec R8, X-6e, T-9c).

**Métis does not generate code, and this is not a step towards it.** The
`generators/` package emitted REST Assured and Playwright sources and was deleted
on purpose: what must be verified is a question about the system, and how to
express it in a framework is a question about the framework. A generator that
knew both would be wrong about one of them every time either changed.

What this module emits is the **flow manifest**: an ordered business flow with
everything a generator needs and nothing it must decide. It is specification, in
the same sense the `.feature` file is, and it is framework-neutral by
construction — it names no library, no annotation, no file layout.

    Métis                          the manifest              a generator
    ------------------------------ ------------------------- ------------------
    what the system does           operations, in order      tasks / methods
    what must hold first           preconditions             on_start / @Before
    what inputs are accepted       the space, never a value  a faker / builder
    what a caller must present     auth facts, with caveats  a client / fixture
    what counts as done            the expected outcome      an assertion

**The accepted space, never a value** (X-6e, T-9c). A field arrives as
`{"type": "string", "length": [3, 40], "required": true}`, not as `"abc"`. One
valid value is one case; the space is what a case is chosen from, and a manifest
carrying an example teaches the generator to emit that example forever.

**Where the translation rules live.** In `docs/academy/`, not here. The mapping
from a manifest to a Locust `TaskSet` or a JUnit class is knowledge about a
framework, it changes when the framework does, and it is exactly the kind of
thing the academy exists to hold — reviewable prose with a worked example rather
than a code path nobody reads. `metis scaffold --framework` names a target only
to select which academy lesson to point at; it never changes what is emitted.
"""
from __future__ import annotations

# Frameworks this manifest has a worked translation for. Naming one does NOT
# change the manifest -- it selects the lesson a reader is pointed at, and
# stating that plainly is what stops the list becoming a set of code paths.
KNOWN_TARGETS = {
    "locust": "docs/academy/09-generating-code-from-a-flow.md",
    "generic": "docs/academy/09-generating-code-from-a-flow.md",
}


def _operation(case, step, ordinal: int, model) -> dict:
    """One step of the flow, as an operation a generator can emit."""
    transition = model.transitions.get(step.transition_id)
    trigger = (transition.trigger if transition else "").strip()
    method, _, path = trigger.partition(" ")
    return {
        "ordinal": ordinal,
        "transition_id": step.transition_id,
        # `VERB /path` where the trigger carries one; otherwise the trigger
        # verbatim. Not parsed into something prettier -- a UI action's trigger
        # is a name, not a route, and forcing it into one would invent a route.
        "method": method if path else "",
        "path": path or trigger,
        "name": step.description,
        "guard": step.guard_verbatim,
        "expected": step.expected_result,
        "is_assertion": step.is_assertion,
    }


def flow_manifest(model, case, *, target: str = "generic",
                  payloads: dict | None = None,
                  auth: dict | None = None) -> dict:
    """One test case as a framework-neutral flow a generator can consume.

    `payloads` and `auth` are passed in rather than looked up, so this stays
    pure and testable without a graph: the caller composes it from
    `authoring.payload_shape` and `authoring.auth_facts`, which already state
    the accepted space and already carry their own caveats.
    """
    setup = [_operation(case, step, i, model)
             for i, step in enumerate(case.precondition_steps, start=1)]
    act = _operation(case, case.act_step, 0, model)

    return {
        "manifest_version": 1,
        "case_id": case.id,
        "name": case.name,
        "objective": case.objective,
        "model_id": case.model_id,
        "criterion": case.criterion,
        # The state the flow starts from, in the model's own words. A generator
        # turns this into a fixture; Métis does not say how.
        "given": case.given,
        # **Hoistable.** Cases sharing a precondition group share their setup, so
        # a generator can lift it into one `on_start` / `@BeforeAll` instead of
        # repeating it per case. Métis knows which cases share it; a generator
        # reading one case at a time cannot.
        "precondition_group": list(case.precondition_group),
        "setup": setup,
        "act": act,
        # Grouped conditions, each naming the steps it bites at (T-9). This is
        # what a data builder is generated from.
        "data_requirements": [
            {"condition": d.condition, "steps": list(d.steps)}
            for d in case.data_requirements
        ],
        # The accepted space per payload type. Never a value (X-6e).
        "payloads": payloads or {},
        # Carries its own caveat: declarative security is all extraction can
        # recover, so "nothing declared" and "open" are different answers and
        # `auth_facts` says which one this is.
        "auth": auth or {},
        "labels": list(case.labels),
        "target": target,
        "translation_rules": KNOWN_TARGETS.get(target, KNOWN_TARGETS["generic"]),
        "means": ("specification, not code (R8). The accepted space, never a "
                  "value (X-6e). A generator supplies the framework; Métis "
                  "supplies what must be true."),
    }


def flow_manifests(model, cases, *, target: str = "generic",
                   payloads: dict | None = None,
                   auth: dict | None = None) -> dict:
    """Every case as one document, with the shared setup reported once.

    A generator emitting a whole suite needs to know which cases share a
    precondition group before it writes the first file, not after — otherwise it
    repeats setup per case and a reviewer sees a suite that looks careless.
    """
    manifests = [flow_manifest(model, c, target=target, payloads=payloads,
                               auth=auth) for c in cases]
    groups: dict[tuple, list[str]] = {}
    for case in cases:
        groups.setdefault(tuple(case.precondition_group), []).append(case.id)

    return {
        "manifest_version": 1,
        "model_id": model.id,
        "target": target,
        "flows": manifests,
        # `[group] -> [case ids]`, so hoisting is a lookup rather than a
        # rediscovery. Reported even when every group is a singleton: "nothing
        # is shared" is a fact a generator should act on, not infer from silence.
        "shared_setup": [
            {"precondition_group": list(group), "cases": case_ids}
            for group, case_ids in sorted(groups.items())
        ],
        "translation_rules": KNOWN_TARGETS.get(target, KNOWN_TARGETS["generic"]),
        "means": ("Métis states the flow; the framework is somebody else's "
                  "decision and lives outside this repository (R8)."),
    }
