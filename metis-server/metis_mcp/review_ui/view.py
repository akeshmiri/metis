"""
The model view (application spec §9.3; N-2).

**N-2 makes this the centrepiece**, and it is the main justification for a
purpose-built interface over a conversational one: a rendered state machine, with
states as nodes and transitions as edges, coloured by lifecycle state, carrying a
**coverage overlay** showing which transitions the current path set covers.

Self-contained by construction: the output is one HTML document with inline SVG
and inline CSS, no external stylesheet, no script, no font, no image. That is not
only a deployment convenience -- a review artefact that renders differently
depending on what a CDN served that day is not evidence of what a reviewer saw
(N-14).

Layout is a deterministic layered walk rather than a force-directed simulation.
Two reasons, and the first is the real one: **P-7's determinism discipline applies
to anything a decision is recorded against.** A diagram that moves between runs
cannot be the thing an approval was audited against. The second is that a
simulation would need a library, and no external asset may be loaded.
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field

from metis_mcp.mbt.model import (
    APPROVED,
    DEPRECATED,
    DISPUTED,
    PLANNED,
    QUARANTINE,
    REJECTED,
    Model,
)

# Lifecycle colours. Chosen to stay distinguishable in greyscale as well as
# colour, because a printed review pack is a real thing.
_LIFECYCLE_COLOUR = {
    APPROVED: ("#1b7f3b", "#e8f5ec"),
    QUARANTINE: ("#8a6d1f", "#fdf6e3"),
    DISPUTED: ("#a3261d", "#fdeceb"),
    REJECTED: ("#5a5a5a", "#eeeeee"),
    DEPRECATED: ("#5a5a5a", "#f4f4f4"),
}
_DEFAULT_COLOUR = ("#333333", "#ffffff")

# Coverage overlay (C-1).
COVERED_DIRECT = "#1b7f3b"
COVERED_INDIRECT = "#2f6fa8"
UNCOVERED = "#a3261d"
EXCLUDED = "#9a9a9a"


@dataclass
class Node:
    id: str
    label: str
    lifecycle: str
    is_initial: bool
    column: int
    row: int


@dataclass
class Edge:
    id: str
    source: str
    target: str
    label: str
    guard: str
    lifecycle: str
    coverage: str
    note: str = ""


@dataclass
class Layout:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    unplaced: list[str] = field(default_factory=list)

    @property
    def columns(self) -> int:
        return max((n.column for n in self.nodes), default=0) + 1


def layered_layout(model: Model) -> Layout:
    """Assign each state a column by BFS distance from an initial state.

    Deterministic: states are visited in sorted id order at every step, so the
    same model always produces the same picture (P-7's discipline). A state
    unreachable from any initial state is placed in a final column and listed in
    `unplaced` -- shown, never hidden, because `validation.check_reachability`
    treats it as blocking and a reviewer must see what is being objected to.
    """
    layout = Layout()
    initial = model.initial_state_ids()
    depth: dict[str, int] = {sid: 0 for sid in sorted(initial)}
    frontier = sorted(initial)

    outgoing: dict[str, list] = {}
    for tid in model.transition_ids():
        t = model.transitions[tid]
        outgoing.setdefault(t.source, []).append(t)

    while frontier:
        current = frontier.pop(0)
        for t in sorted(outgoing.get(current, []), key=lambda x: x.id):
            if t.target not in depth:
                depth[t.target] = depth[current] + 1
                frontier.append(t.target)

    orphan_column = max(depth.values(), default=-1) + 1
    for sid in model.state_ids():
        if sid not in depth:
            depth[sid] = orphan_column
            layout.unplaced.append(sid)

    by_column: dict[int, list[str]] = {}
    for sid in sorted(depth, key=lambda s: (depth[s], s)):
        by_column.setdefault(depth[sid], []).append(sid)

    for column, ids in sorted(by_column.items()):
        for row, sid in enumerate(ids):
            state = model.states[sid]
            layout.nodes.append(Node(
                id=sid, label=state.name or sid, lifecycle=state.lifecycle_state,
                is_initial=state.is_initial, column=column, row=row))
    return layout


def build_layout(model: Model, ledger=None) -> Layout:
    """Layout plus the coverage overlay (spec N-2, C-1)."""
    layout = layered_layout(model)
    for tid in model.transition_ids():
        t = model.transitions[tid]
        coverage, note = _coverage_of(tid, t, ledger)
        layout.edges.append(Edge(
            id=tid, source=t.source, target=t.target, label=t.trigger,
            guard=t.guard, lifecycle=t.lifecycle_state, coverage=coverage, note=note))
    return layout


def _coverage_of(tid: str, transition, ledger) -> tuple[str, str]:
    """C-8: a transition covered only indirectly is reported as such, never as
    equivalently tested."""
    if transition.implementation_status == PLANNED:
        return EXCLUDED, "planned — not built yet, correctly not a gap (P-11)"
    if ledger is None:
        return EXCLUDED, "no coverage computed"
    mechanisms = ledger.mechanisms_for(tid)
    if "direct" in mechanisms:
        return COVERED_DIRECT, "direct"
    if "indirect" in mechanisms:
        return COVERED_INDIRECT, "indirect only — its combinations were never exercised (C-8)"
    reason = next((r for t, r in ledger.uncovered if t == tid), "")
    return UNCOVERED, reason or "uncovered"


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

_COL_WIDTH = 240
_ROW_HEIGHT = 92
_NODE_W = 168
_NODE_H = 46
_MARGIN = 40


def _xy(node: Node) -> tuple[int, int]:
    return (_MARGIN + node.column * _COL_WIDTH, _MARGIN + node.row * _ROW_HEIGHT)


def render_svg(layout: Layout) -> str:
    """Inline SVG. No script, no external asset (see the module docstring)."""
    if not layout.nodes:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="40"></svg>'

    positions = {n.id: _xy(n) for n in layout.nodes}
    width = _MARGIN * 2 + layout.columns * _COL_WIDTH
    height = _MARGIN * 2 + (max(n.row for n in layout.nodes) + 1) * _ROW_HEIGHT

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" role="img" aria-label="state machine">',
        '<defs>',
    ]
    for name, colour in (("d", COVERED_DIRECT), ("i", COVERED_INDIRECT),
                         ("u", UNCOVERED), ("x", EXCLUDED)):
        parts.append(
            f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{colour}"/></marker>')
    parts.append('</defs>')

    for edge in layout.edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        x1, y1 = positions[edge.source]
        x2, y2 = positions[edge.target]
        marker = {COVERED_DIRECT: "d", COVERED_INDIRECT: "i",
                  UNCOVERED: "u"}.get(edge.coverage, "x")
        dashes = ' stroke-dasharray="6 4"' if edge.coverage in (UNCOVERED, EXCLUDED) else ""

        if edge.source == edge.target:                       # self-loop
            path = (f"M {x1 + _NODE_W // 2} {y1} "
                    f"C {x1 + _NODE_W + 60} {y1 - 52}, "
                    f"{x1 + _NODE_W + 60} {y1 + 52}, {x1 + _NODE_W // 2} {y1 + 6}")
        else:
            mid = ((x1 + _NODE_W + x2) // 2, (y1 + y2) // 2 - 18)
            path = (f"M {x1 + _NODE_W} {y1} Q {mid[0]} {mid[1]} {x2} {y2}")

        parts.append(
            f'<path d="{path}" fill="none" stroke="{edge.coverage}" stroke-width="2"'
            f'{dashes} marker-end="url(#arrow-{marker})"><title>'
            f'{html.escape(edge.id)}: {html.escape(edge.label)}'
            + (f' [{html.escape(edge.guard)}]' if edge.guard else '')
            + f' — {html.escape(edge.note)}</title></path>')

    for node in layout.nodes:
        x, y = positions[node.id]
        stroke, fill = _LIFECYCLE_COLOUR.get(node.lifecycle, _DEFAULT_COLOUR)
        top = y - _NODE_H // 2
        parts.append(
            f'<g><rect x="{x}" y="{top}" width="{_NODE_W}" height="{_NODE_H}" rx="8" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{3 if node.is_initial else 1.5}"/>'
            f'<title>{html.escape(node.id)} — {html.escape(node.lifecycle)}</title>'
            f'<text x="{x + _NODE_W // 2}" y="{y + 1}" text-anchor="middle" '
            f'font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="13" '
            f'fill="#111">{html.escape(node.label[:22])}</text>'
            f'<text x="{x + _NODE_W // 2}" y="{y + 15}" text-anchor="middle" '
            f'font-family="system-ui,sans-serif" font-size="9" fill="{stroke}">'
            f'{html.escape(node.lifecycle)}</text></g>')

    parts.append("</svg>")
    return "".join(parts)


_CSS = """
:root { color-scheme: light dark; }
body { font: 14px/1.5 system-ui, sans-serif; margin: 0; padding: 24px;
       background: #fff; color: #111; }
h1 { font-size: 20px; margin: 0 0 4px; }
.sub { color: #555; margin: 0 0 20px; }
.legend { display: flex; flex-wrap: wrap; gap: 16px; margin: 16px 0 24px;
          font-size: 12px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.swatch { width: 22px; height: 3px; display: inline-block; }
.dot { width: 11px; height: 11px; border-radius: 3px; display: inline-block; }
figure { margin: 0 0 28px; overflow-x: auto; border: 1px solid #e2e2e2;
         border-radius: 8px; padding: 12px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #ececec;
         vertical-align: top; }
th { font-weight: 600; color: #444; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.caveat { margin-top: 24px; padding: 12px 14px; border-left: 3px solid #8a6d1f;
          background: #fdf6e3; font-size: 13px; }
@media (prefers-color-scheme: dark) {
  body { background: #14161a; color: #e8e8e8; }
  .sub, th { color: #a8a8a8; }
  figure { border-color: #2c3038; }
  th, td { border-bottom-color: #23262c; }
  .caveat { background: #241f10; border-left-color: #b08d2a; }
}
"""


def render_html(model: Model, layout: Layout, title: str = "",
                coverage_summary: str = "") -> str:
    """The full model view: diagram, legend, and the transition table (N-2).

    The table is not decoration. The diagram shows shape; the table carries the
    verbatim guard and the coverage reason, and T-5's discipline -- the exact
    recovered condition is the authoritative statement -- applies to a review
    screen at least as much as to a test case.
    """
    heading = title or f"{model.id} — model view"
    rows = []
    for edge in layout.edges:
        label = {COVERED_DIRECT: "direct", COVERED_INDIRECT: "indirect only",
                 UNCOVERED: "uncovered", EXCLUDED: "excluded"}[edge.coverage]
        rows.append(
            f"<tr><td><code>{html.escape(edge.id)}</code></td>"
            f"<td>{html.escape(edge.source)}</td>"
            f"<td>{html.escape(edge.label)}</td>"
            f"<td>{html.escape(edge.target)}</td>"
            f"<td><code>{html.escape(edge.guard) if edge.guard else '—'}</code></td>"
            f"<td>{html.escape(edge.lifecycle)}</td>"
            f"<td style=\"color:{edge.coverage}\">{label}</td>"
            f"<td>{html.escape(edge.note)}</td></tr>")

    legend = "".join(
        f'<span><i class="swatch" style="background:{colour}"></i>{name}</span>'
        for name, colour in (("covered directly", COVERED_DIRECT),
                             ("covered indirectly", COVERED_INDIRECT),
                             ("uncovered", UNCOVERED),
                             ("excluded", EXCLUDED)))
    legend += "".join(
        f'<span><i class="dot" style="background:{fill};border:1.5px solid {stroke}">'
        f'</i>{state}</span>'
        for state, (stroke, fill) in _LIFECYCLE_COLOUR.items())

    unplaced = ""
    if layout.unplaced:
        unplaced = (f'<p class="sub">Unreachable from any initial state, shown in the '
                    f'final column: <code>{html.escape(", ".join(layout.unplaced))}'
                    f'</code>. Reachability treats this as blocking (§2.6).</p>')

    return (
        f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{html.escape(heading)}</title><style>{_CSS}</style></head><body>"
        f"<h1>{html.escape(heading)}</h1>"
        f"<p class=\"sub\">{len(layout.nodes)} states, {len(layout.edges)} transitions."
        f"{' ' + html.escape(coverage_summary) if coverage_summary else ''}</p>"
        f"<div class=\"legend\">{legend}</div>"
        f"<figure>{render_svg(layout)}</figure>"
        f"{unplaced}"
        f"<table><thead><tr><th>id</th><th>from</th><th>trigger</th><th>to</th>"
        f"<th>guard (verbatim)</th><th>lifecycle</th><th>coverage</th><th>note</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        f"<p class=\"caveat\">This shows what is <strong>tested</strong>, not what is "
        f"<strong>working</strong>. A transition may be fully covered and currently "
        f"failing; the ledger records coverage, not execution outcome (C-10, C-11)."
        f"</p></body></html>")
