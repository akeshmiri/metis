"""
What a fact is FOR: whether the model can lead you to it (spec X-6d).

**"Has an edge" is the wrong question.** A method fifteen `CALLS` deep has
plenty and tells the model nothing; an `ExceptionMapping` that produces a 400 a
caller sees had none at all. Measured on a real twelve-endpoint service, following
only the edges a person would actually traverse — behaviour to evidence to
payload, with `CALLS` and `DECLARES_METHOD` excluded because reachability through
a call chain is connectivity rather than meaning:

    324 facts reachable from the model, 368 not

Of the 368, five were `ExceptionMapping` and two `Check` — user-visible behaviour
connected to nothing — and 359 were implementation detail the model could not
reach and had no reason to.

So each fact is classified against the model, and the three classes are acted on
differently:

    surface      what a caller sends, receives, or is answered with. MUST be
                 reachable from the model; if it is not, that is a gap a person
                 has to see, so it becomes a Finding rather than a silent node.
    supporting   named by a declared reader, bounded to what that reader needs.
    internal     neither. Not landed, and counted by label so the reduction is
                 visible (X-5a).

`surface` is decided by **the label's meaning as well as by the traversal**, and
that is not a shortcut. Traversal alone is circular for exactly the nodes that
matter: an orphaned `ExceptionMapping` is unreachable by definition, so a purely
structural test files it under `internal` and the gap disappears into the noise it
is supposed to be distinguished from.

Pure: it reads a plan's own nodes and edges and touches no database, which is
what lets the invariant be asserted in a suite that has none.
"""
from __future__ import annotations

from collections import defaultdict

# X-6d: a scalar field is `f_<name>_<what>` on its type. **Neo4j has no nested
# property** — a map value is not storable — so the choice was prefixed keys or
# parallel arrays, and parallel arrays break the moment one is filtered.
#
# Prefixed keys are awkward to query generically, which is the cost of the shape
# and the reason `expand_fields` exists: the encoder that writes them and the
# decoder that reads them sit in one module so they cannot drift apart.
FIELD_PREFIX = "f_"


def expand_fields(node: dict) -> dict:
    """`{f_title_required: 'true', …}` -> `{fields: {title: {required: 'true'}}}`.

    The nested document the flat properties encode. Everything that is not a
    field property is passed through unchanged, so this is safe to apply to a
    whole node.
    """
    out: dict = {}
    fields: dict = {}
    names = set(node.get("fields") or ())
    for key, value in (node or {}).items():
        if not key.startswith(FIELD_PREFIX):
            if key != "fields":
                out[key] = value
            continue
        # `f_<name>_<what>`, and a field name may itself contain an underscore,
        # so the split is anchored on the declared names rather than guessed at.
        rest = key[len(FIELD_PREFIX):]
        for name in sorted(names, key=len, reverse=True):
            if rest.startswith(name + "_"):
                fields.setdefault(name, {})[rest[len(name) + 1:]] = value
                break
    for name in names:
        fields.setdefault(name, {})
    if fields or names:
        out["fields"] = fields
    return out


SURFACE = "surface"
SUPPORTING = "supporting"
INTERNAL = "internal"

# Labels that are user-facing whatever the graph looks like. A caller invokes an
# Endpoint and is answered with a DeclaredOutcome or the status an
# ExceptionMapping produces. None of that depends on an edge existing, which is
# the point: these are the labels whose disconnection is a finding.
#
# `Parameter` was here until it was staged out. What a caller sends is still
# surface — it is now a value inside the transition's `c_inputs` rather than a
# node, and a property cannot be disconnected from anything.
INHERENTLY_SURFACE = frozenset({
    "Endpoint", "DeclaredOutcome", "ExceptionMapping",
})

# Labels that are user-facing when a payload chain reaches them, and internal
# otherwise. `RecordDto` is surface; a service's config class is not, and they
# are the same label.
# `Field` was here until X-6d made a field a property of its type rather than a
# node, so a payload's fields are surface by virtue of the type carrying them.
SURFACE_WHEN_REACHED = frozenset({"Class", "Enum"})

# The edges a person or a model actually follows. `CALLS` and `DECLARES_METHOD`
# are deliberately absent — see the module docstring.
SEMANTIC_EDGES = frozenset({
    "DERIVED_FROM", "EXERCISES", "REQUIRES", "EXPECTS", "ACCEPTS", "RETURNS",
    "OF_TYPE", "HAS_FIELD", "DECLARES", "HANDLED_BY", "GUARDED_BY",
    "CONSTRAINED_BY", "EXPOSES", "WHEN", "THEN", "CONTAINS", "ABOUT",
})

# Reached from an Endpoint, this is the payload and outcome chain: what a caller
# sends and what it is answered with.
PAYLOAD_EDGES = frozenset({
    "ACCEPTS", "RETURNS", "OF_TYPE", "HAS_FIELD", "DECLARES", "HANDLED_BY",
    "CONSTRAINED_BY",
})

# Referenced by the `source_episode_id` property rather than by an edge, and the
# catalogue declares no relationship for it. Checked against the catalogue in
# `test_connectivity.py` so this allowance cannot outlive its reason.
EDGE_FREE = {"Episode": "referenced by the source_episode_id property; the "
                        "catalogue declares no relationship for it"}


def _adjacency(edges, keep) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.rel_type not in keep:
            continue
        out[edge.from_id].add(edge.to_id)
        out[edge.to_id].add(edge.from_id)
    return out


def _walk(seeds, adjacency) -> set[str]:
    seen, frontier = set(seeds), list(seeds)
    while frontier:
        node = frontier.pop()
        for nxt in adjacency.get(node, ()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return seen


def classify(nodes, edges) -> dict[str, str]:
    """`node id -> surface | supporting | internal`.

    `nodes` is anything with `.label` and a `.properties["id"]`; `edges` anything
    with `.from_id`, `.to_id` and `.rel_type` — which is what both landing plans
    already produce.
    """
    by_id = {n.properties["id"]: n.label for n in nodes}
    endpoints = [i for i, lab in by_id.items() if lab == "Endpoint"]

    payload_reach = _walk(endpoints, _adjacency(edges, PAYLOAD_EDGES))
    out: dict[str, str] = {}
    for node_id, label in by_id.items():
        if label in INHERENTLY_SURFACE:
            out[node_id] = SURFACE
        elif label in SURFACE_WHEN_REACHED and node_id in payload_reach:
            out[node_id] = SURFACE
        elif label == "Check":
            # A guard explains a user-visible branch, so it is evidence a
            # reviewer needs — but only where it was actually attributed.
            out[node_id] = SUPPORTING
        else:
            out[node_id] = INTERNAL
    return out


def unreachable_surface(nodes, edges, model_labels=("State", "ApiCall", "UiAction")):
    """Surface facts the model cannot lead you to — the gap worth a Finding.

    Returns `(id, label, reason)`. Empty is the goal; five `ExceptionMapping`
    nodes were the whole population on a real service, and the reason they were
    invisible is that nothing had ever asked this question.
    """
    by_id = {n.properties["id"]: n.label for n in nodes}
    classes = classify(nodes, edges)
    seeds = [i for i, lab in by_id.items() if lab in model_labels]
    reach = _walk(seeds, _adjacency(edges, SEMANTIC_EDGES))
    return [
        (node_id, by_id[node_id],
         f"{by_id[node_id]} is user-facing and no path of meaningful edges "
         f"reaches it from the model — a caller can observe it and no modelled "
         f"behaviour accounts for it")
        for node_id, kind in sorted(classes.items())
        if kind == SURFACE and node_id not in reach
    ]


def disconnected(nodes, edges) -> list[tuple[str, str]]:
    """Nodes no edge touches at all, minus the labels allowed to be edge-free."""
    touched = set()
    for edge in edges:
        touched.add(edge.from_id)
        touched.add(edge.to_id)
    return [(n.properties["id"], n.label) for n in nodes
            if n.properties["id"] not in touched and n.label not in EDGE_FREE]
