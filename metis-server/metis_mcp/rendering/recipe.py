"""
The call recipe: how to exercise one endpoint (spec §7.4b, X-6e).

A model that can be traversed is not yet a model you can act on. This turns what
the graph holds about one entry point into the thing a person actually runs — a
curl for `api` — and states, beside it, what makes the call fail.

**T-9c stands: conditions, not values.** `payload.py` says a step requires
`!credentials_valid` and never invents a username; the same rule applies here, so
every placeholder describes the *accepted space* rather than one sample:

    "mfaChallengeType": "<OOBSMS_TWILIO|OOBPHONE_TWILIO|QUESTIONS>"

That is also what a test strategy needs. A single valid value tells you one case;
the space tells you the partitions and the boundaries, which is what a case is
chosen from. A rendered recipe therefore contains **no literal that was not
recovered** — asserted, because a plausible-looking value is exactly the failure
T-9c exists to prevent.

**T-9d: an unrecoverable detail is absent and marked.** A base URL lives in
deployment config, not in a controller, so it renders as `{base}` with the reason
attached rather than as a guess that looks runnable.
"""
from __future__ import annotations

from metis_mcp.ontology.facts import expand_fields

UNRECOVERABLE = "__unrecoverable__"

# What a caller must be told when nothing was recovered. Security enforced in a
# filter chain or at a gateway is invisible to extraction, so "no declaration"
# and "open" are different claims and only the first is ever made.
NO_SECURITY_NOTE = (
    "no security is declared on this endpoint in source. That is not the same "
    "as open: a filter chain or a gateway can enforce authentication invisibly "
    "to extraction"
)


def _placeholder(name: str, spec: dict) -> str:
    """The accepted space for one field, as text. Never a value."""
    allowed = spec.get("allowed_values")
    if allowed:
        return "<" + "|".join(allowed) + ">"

    kind = (spec.get("type") or "").rsplit(".", 1)[-1] or "value"
    bits: list[str] = [kind.lower()]
    lo, hi = spec.get("expected_min_length"), spec.get("expected_max_length")
    if lo is not None or hi is not None:
        bits.append(f"length {lo if lo is not None else 0}..{hi if hi is not None else '?'}")
    lo, hi = spec.get("expected_min_size"), spec.get("expected_max_size")
    if lo is not None or hi is not None:
        bits.append(f"{lo if lo is not None else 0}..{hi if hi is not None else '?'} items")
    for key, label in (("expected_min", "min"), ("expected_max", "max"),
                       ("expected_pattern", "matching"), ("expected_format", "format"),
                       ("expected_temporal", "must be")):
        if spec.get(key):
            bits.append(f"{label} {spec[key]}")
    if spec.get("required") == "true":
        bits.append("required")
    return "<" + ", ".join(bits) + ">"


def body_template(payload_type: dict, seen: tuple[str, ...] = ()) -> dict:
    """The request body as placeholders, following nested types.

    `seen` stops a self-referential payload: a type that contains itself is legal
    Java and would otherwise recurse forever.
    """
    name = payload_type.get("type") or ""
    if name in seen:
        return {"__recursive__": name}
    out: dict = {}
    for field_name, spec in sorted((payload_type.get("fields") or {}).items()):
        nested = spec.get("__nested__")
        if nested:
            inner = body_template(nested, (*seen, name))
            out[field_name] = [inner] if spec.get("element_type") else inner
        else:
            out[field_name] = _placeholder(field_name, spec)
    return out


def build(endpoint: dict, *, base_url: str = "", payload_types: tuple = (),
          outcomes: tuple = (), rejections: tuple = ()) -> dict:
    """Everything needed to render a recipe, and what could not be recovered.

    Derived, never authored (T-9b): it restates what the graph holds in a shape
    somebody can run, and introduces nothing.
    """
    unrecoverable: list[tuple[str, str]] = []
    if not base_url:
        unrecoverable.append((
            "base_url",
            "a base URL lives in deployment config, not in a controller — set "
            "`base_url` in the project profile"))

    headers: dict[str, str] = {}
    query: dict[str, str] = {}
    path_params: dict[str, str] = {}
    for parameter in endpoint.get("parameters") or ():
        where = parameter.get("location", "")
        slot = {"header": headers, "query": query, "path": path_params}.get(where)
        if slot is None:
            continue
        kind = (parameter.get("type_name") or "").rsplit(".", 1)[-1].lower() or "value"
        required = ", required" if parameter.get("required") else ""
        slot[parameter.get("name", "")] = f"<{kind}{required}>"

    consumes = list(endpoint.get("consumes") or ())
    body = None
    if payload_types:
        # `application/json` only when a body exists and nothing was declared —
        # stated as an assumption rather than presented as recovered.
        if not consumes:
            unrecoverable.append((
                "content_type",
                "no `consumes` is declared; `application/json` is assumed "
                "because a body was recovered"))
        body = body_template(payload_types[0])

    schemes = endpoint.get("security_schemes") or ()
    security = {"declared": bool(schemes), "schemes": list(schemes),
                "roles": list(endpoint.get("security_roles") or ())}
    if not schemes:
        security["note"] = NO_SECURITY_NOTE
        # The honest alternative, and on the pilot service the real answer:
        # authentication may be travelling as an ordinary header parameter.
        if headers:
            security["headers_the_caller_must_send"] = sorted(headers)

    return {
        "schema": "metis.call-recipe/1",
        "method": endpoint.get("http_method", UNRECOVERABLE),
        "path": endpoint.get("path", UNRECOVERABLE),
        "base_url": base_url or "{base}",
        "headers": headers,
        "query": query,
        "path_params": path_params,
        "content_type": (consumes[0] if consumes else
                         ("application/json" if body is not None else "")),
        "body": body,
        "security": security,
        "outcomes": list(outcomes),
        "rejections": list(rejections),
        "unrecoverable": unrecoverable,
    }


def as_curl(recipe: dict) -> str:
    """The recipe as a runnable-shaped command. Placeholders, never values."""
    import json

    lines = [f"curl -X {recipe['method']} '{recipe['base_url']}{recipe['path']}'"]
    if recipe.get("content_type"):
        lines.append(f"  -H 'Content-Type: {recipe['content_type']}'")
    for name, placeholder in sorted(recipe.get("headers", {}).items()):
        lines.append(f"  -H '{name}: {placeholder}'")
    if recipe.get("body") is not None:
        rendered = json.dumps(recipe["body"], indent=2, sort_keys=True)
        lines.append("  -d '" + rendered + "'")
    out = " \\\n".join(lines)

    notes = [f"# {what}: {why}" for what, why in recipe.get("unrecoverable", ())]
    for status, cause in recipe.get("rejections", ()):
        notes.append(f"# {status} when {cause}")
    if not recipe["security"]["declared"]:
        notes.append("# " + NO_SECURITY_NOTE)
    return out + ("\n" + "\n".join(notes) if notes else "")


def expand_payload(node: dict, nested: dict | None = None) -> dict:
    """A Class node's flat `f_*` properties as the nested document a body needs.

    `nested` maps a field's declared type to the already-expanded document for
    it, which is how `Class-[:OF_TYPE]->Class` becomes a nested body rather than
    a type name in a string.
    """
    expanded = expand_fields(node)
    fields = expanded.get("fields", {})
    for spec in fields.values():
        target = (nested or {}).get(spec.get("type")) or \
            (nested or {}).get(spec.get("element_type"))
        if target:
            spec["__nested__"] = target
    return {"type": node.get("name"), "fields": fields}
