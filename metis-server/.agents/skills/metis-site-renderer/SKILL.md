---
name: metis-site-renderer
description: Generate a real, always-current static HTML site from Academy content (graph model basics, traceability, confidence tiers, EARS authoring) plus a live quality-score snapshot. Use when a user wants a browsable, linkable reference site -- not a point-in-time shareable artifact (use metis-deck-renderer for that).
---

# Métis site-renderer

§12.5 of `docs/metis-specification.md` — the second thin renderer over
`metis_mcp/academy.py`'s single real content-assembly stage
(`REQ-METIS-ACD-07`), sharing `steps/01-gather-content.md` with
`metis-deck-renderer` rather than duplicating it (`REQ-METIS-ACD-08`).
Follows `../shared/knowledge/anti-hallucination-protocol.md`'s RPI gates
and Stage Confirmation Protocol — read that file once, not repeated here.

**Chain mode:** regenerating the whole site is one deterministic pass
(render every Academy page + the index) — auto-advances through its
steps, no human confirmation needed between them (unlike
`metis-deck-renderer`, since nothing here is presented as final/shared
the way a deck is — regenerating a stale site is exactly the intended
behavior, `REQ-METIS-ACD-09`).

## Step index

1. `steps/01-gather-content.md` — same real call
   `metis-deck-renderer` makes: `metis_mcp/academy.py`'s
   `assemble_content()`
2. `steps/02-render.md` — `script/build_site.py` (wraps
   `metis_mcp/site_renderer.py`'s real `render_site`)

## Non-negotiable rules

- Never hand-author page content directly in this skill — every page's
  text comes from `academy/*.md` via `assemble_content(kind='academy_page')`,
  the same real files `metis_mcp/academy.py`'s tests check against.
- The site is stateless and safe to regenerate on any schedule — it's
  always a full rebuild from current graph/content state, never an
  incremental patch that could drift from reality.
