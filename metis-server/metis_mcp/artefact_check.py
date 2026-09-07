"""
The confirmation ladder for generated ARTEFACTS — a curl, a scaffold manifest.

**The same discipline `sql_analysis.confirm` applies to a statement**, and for
the same reason: "we generated it" and "we know it works" are different claims,
and returning the first while implying the second is the confident-wrong output
this codebase exists to refuse.

**The ladder is shorter here, and the missing rung is the point.** SQL has
`EXPLAIN`: a way to ask the target what it *would* do without doing it. HTTP has
no equivalent. There is no way to ask a server what a `POST` would do except by
sending it, so this ladder is:

    shaped  -> static -> executed

with no `planned` between them. Inventing one — a "dry run" that checks a URL
resolves, say — would name a rung nothing actually climbs.

**Which tier `executed` needs depends on the method, not on the artefact.**
`execution.py` separates `observe` (read a live system) from `run` (make
something happen) because reading a replica is recoverable and a load test
against the wrong host is an outage. A `GET` is a read. A `POST`, `PUT`, `PATCH`
or `DELETE` makes something happen in somebody's system, and it is not Métis's
system. So the two sit at different tiers, decided by the verb.

**`static` is the rung that matters and the one Métis can always reach.** It is
X-6e restated as a check: a generated artefact states the accepted space and
never a value. A curl carrying `"name": "test123"` instead of
`<string, length 3..40, required>` has invented test data, which is worse than an
obvious gap because it looks runnable and is wrong. That is checkable here, with
no target and no tier.
"""
from __future__ import annotations

import json
import re

SHAPED, STATIC, EXECUTED = "shaped", "static", "executed"
RUNGS = (SHAPED, STATIC, EXECUTED)

# A method that only reads may be confirmed at `observe`. Anything else changes
# somebody else's system and needs `run`.
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# What a placeholder looks like. `_placeholder` emits `<kind, constraint, ...>`
# or `<a|b|c>` for an enum, and `build` renders an unknown base as `{base}`.
_PLACEHOLDER = re.compile(r"<[^<>]+>|\{[a-z_]+\}", re.I)

# Values that are obviously invented rather than described. Deliberately a short,
# specific list: a broad heuristic would flag a legitimate enum member — `<a|b>`
# renders real allowed values — and a check people learn to ignore is worse than
# no check.
_INVENTED = re.compile(
    r"\b(test123|foo|bar|baz|example\.com|john\.doe|jane\.doe|lorem|"
    r"changeme|password123|dummy|placeholder1|abc123)\b", re.I)


def shape_of_curl(command: str) -> dict:
    """Is this a well-formed command whose body is well-formed JSON?

    **Not "does it run".** It checks what can be checked without a shell and
    without a server: the quoting balances, and a `-d` payload parses as JSON.
    A curl that fails here is one Métis emitted wrong, which is a defect in
    Métis rather than a fact about the target.
    """
    text = (command or "").strip()
    if not text:
        return {"ok": False, "reason": "no command given"}

    problems = []
    if not text.startswith("curl"):
        problems.append("does not begin with `curl`")

    # Comment lines carry the reasons and notes; they are not part of the
    # command and must not be counted for balance.
    body = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))
    if body.count("'") % 2:
        problems.append("unbalanced single quotes")

    payload = _payload_of(body)
    if payload is not None:
        try:
            json.loads(payload)
        except json.JSONDecodeError as e:
            problems.append(f"the -d payload is not valid JSON: {e}")

    return {
        "ok": not problems,
        "problems": problems,
        "means": ("a shape check. It says the command is well formed, not that "
                  "the target accepts it"),
    }


def _payload_of(command: str) -> str | None:
    """The `-d '...'` payload, or None. Quote-aware rather than regex-greedy."""
    marker = command.find("-d '")
    if marker < 0:
        return None
    start = marker + len("-d '")
    end = command.find("'", start)
    return command[start:end] if end > start else command[start:]


def x6e_violations(artefact: str) -> list[dict]:
    """Where a generated artefact states a VALUE instead of a space (X-6e).

    The rule: *what is generated states the accepted space, never a value.* A
    curl carries `<string, length 3..40, required>`; a base URL renders as
    `{base}` with its reason; a UI element with no authored selector raises
    rather than guessing.

    **Reported as candidates.** A real enum renders its real members, so a
    literal is not automatically a violation — which is why the invented-value
    list is short and specific rather than a heuristic that fires on anything
    concrete.
    """
    found = []
    for match in _INVENTED.finditer(artefact or ""):
        found.append({
            "value": match.group(0),
            "why": ("reads as invented test data rather than a described "
                    "space. A value that looks runnable and is wrong is worse "
                    "than a visible gap, because nobody can tell it is wrong "
                    "by looking (X-6e)"),
        })

    # A concrete host where `{base}` belongs. Métis does not know a hostname and
    # must not invent one; a real one here came from somewhere it should not.
    for match in re.finditer(r"https?://(?!\{)[a-z0-9.-]+", artefact or "", re.I):
        host = match.group(0)
        if "example" in host.lower() or "localhost" in host.lower():
            continue          # a documented placeholder host, not an invention
        found.append({
            "value": host,
            "why": ("a concrete host where `{base}` belongs unless a profile "
                    "supplied it. Métis does not know a hostname (X-6e)"),
        })
    return found


def confirm_curl(command: str, *, execute=None, target: str = "") -> dict:
    """Take a generated call as far up the ladder as this deployment allows.

    Same contract as `sql_analysis.confirm`: the rung reached is always named,
    and stopping is an answer rather than a failure.
    """
    shape = shape_of_curl(command)
    if not shape["ok"]:
        return {
            "ok": False,
            "confirmed_to": None,
            "rungs": {SHAPED: shape},
            "stopped_because": "; ".join(shape.get("problems", ())
                                         or [shape.get("reason", "")]),
            "means": "nothing further was attempted on a malformed command",
        }

    violations = x6e_violations(command)
    placeholders = len(_PLACEHOLDER.findall(command or ""))
    rungs = {
        SHAPED: shape,
        STATIC: {
            "ok": not violations,
            "x6e_violations": violations,
            "placeholders": placeholders,
            "means": ("X-6e as a check: the artefact states the accepted space "
                      "and never a value. Clean here means nothing INVENTED "
                      "was found, not that the call is correct"),
        },
    }

    method = _method_of(command)
    # An unrecovered verb gets `run`, because it is the stricter of the two and
    # this is exactly the case where guessing wrong is expensive.
    needed = "observe" if method in READ_METHODS else "run"

    if execute is None:
        from metis_mcp import execution as execute
    tier = getattr(execute, "tier", lambda: "off")()

    if tier == "off":
        stopped = (f"METIS_EXECUTE is `off`, so nothing was sent. This call has "
                   f"been CHECKED, not confirmed — it would need `{needed}` "
                   f"because it is a {method}")
    elif tier != needed and needed == "run":
        stopped = (f"this is a {method}: it makes something happen in a system "
                   f"that is not Métis's, so it needs `run` and the tier is "
                   f"`{tier}`. A GET would be confirmable at `observe`")
    elif not target:
        stopped = (f"tier `{tier}` permits it and no target was named. A call "
                   f"is against ONE deployment; sending it at an unnamed one "
                   f"would be confirming against nothing")
    else:
        stopped = (f"tier `{tier}` and target {target!r} permit sending this. "
                   f"Métis opens no HTTP connection from a check — that is a "
                   f"runner's act, at the tier that records it (N-1)")

    return {
        "ok": True,
        "confirmed_to": STATIC,
        "rungs": rungs,
        "needs_tier": needed,
        "method": method,
        "stopped_because": stopped,
        "means": ("there is no `planned` rung for HTTP. SQL has EXPLAIN; there "
                  "is no way to ask a server what a POST would do except by "
                  "sending it, and naming a rung nothing climbs would be worse "
                  "than having three"),
    }


def _method_of(command: str) -> str:
    """The HTTP verb, or `__unrecoverable__` when the recipe could not name one.

    **`__unrecoverable__` must not be guessed into a verb.** `recipe.build`
    writes it when extraction could not recover the method, and inferring `POST`
    from the presence of a body would turn "Métis does not know" into a
    confident answer — and one that decides which TIER the call needs. A verb
    nobody recovered gets the stricter tier, not the convenient one.
    """
    match = re.search(r"-X\s+(\S+)", command or "")
    if match:
        verb = match.group(1).strip("'\"")
        return verb.upper() if verb.isalpha() else verb
    # curl's own defaults, which are facts about curl rather than inferences
    # about the endpoint: GET, or POST when given a body.
    return "POST" if "-d '" in (command or "") else "GET"


def confirm_scaffold(manifest) -> dict:
    """The same two reachable rungs for a scaffold manifest.

    No `executed` rung at all: a scaffold is consumed by a code generator
    outside Métis, so there is nothing here to run. Saying so is the point —
    `flow_scaffold`'s output is checked for shape and for X-6e and then handed
    over, and pretending otherwise would claim a confirmation nobody performed.
    """
    if isinstance(manifest, str):
        try:
            parsed = json.loads(manifest)
            text = manifest
        except json.JSONDecodeError as e:
            return {
                "ok": False, "confirmed_to": None,
                "rungs": {SHAPED: {"ok": False,
                                   "problems": [f"not valid JSON: {e}"]}},
                "stopped_because": f"the manifest is not valid JSON: {e}",
            }
    else:
        parsed, text = manifest, json.dumps(manifest, sort_keys=True)

    violations = x6e_violations(text)
    return {
        "ok": True,
        "confirmed_to": STATIC,
        "rungs": {
            SHAPED: {"ok": True, "problems": [],
                     "operations": len(parsed.get("operations", []))
                     if isinstance(parsed, dict) else None},
            STATIC: {"ok": not violations, "x6e_violations": violations},
        },
        "stopped_because": ("a scaffold is consumed by a generator outside "
                            "Métis. There is nothing here to execute, so there "
                            "is no rung above `static` — not a limitation, a "
                            "fact about what this artefact is"),
    }
