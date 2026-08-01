---
name: metis-deck-renderer
description: Generate a real, point-in-time PowerPoint quality-snapshot deck from the live Métis graph (composite quality_score, DQ metric breakdown). Use when a user wants a shareable, dated .pptx snapshot for a periodic report or leadership review -- not for an always-current view (use metis-site-renderer or a direct metis_quality_score call for that).
---

# Métis deck-renderer

§4.6.1 / §12.5 of `docs/metis-specification.md` — a **renderer**, not an
independent content-producing skill (§4.6.1's own scope correction).
Stage 1 (gather content) is `metis_mcp/academy.py`'s single real
content-assembly stage, shared verbatim with `metis-site-renderer` — this
skill only does stages 2-4: turning that already-gathered, already-grounded
content into a `.pptx` file. Follows
`../shared/knowledge/anti-hallucination-protocol.md`'s RPI gates and Stage
Confirmation Protocol — read that file once, not repeated here.

**Standalone mode:** one deck per invocation — always pauses for
confirmation after generation and before declaring the deck done
(`REQ-METIS-SLD-03`).

## Real, disclosed scope narrowing

No custom `.potx` template exists — `script/build_deck.py` uses
python-pptx's own built-in default theme, not a hand-designed brand
template (see `templates/theme-tokens.md`). Visual QA (render to images,
inspect for overflow/overlap/contrast) is genuinely not built — no
image-rendering-and-inspection infrastructure exists in this environment.
Content QA (every claim traces to real data, no leftover placeholder
text) and File QA (the written file re-opens cleanly) ARE real and run on
every generation — see `metis_mcp/pptx_renderer.py`'s own return dict.

## Step index

1. `steps/01-gather-content.md` — calls `metis_mcp/academy.py`'s
   `assemble_content(kind='quality_summary')`
2. `steps/02-generate.md` — `script/build_deck.py` (wraps
   `metis_mcp/pptx_renderer.py`'s real `render_quality_deck`)
3. `steps/03-qa-and-report.md` — content QA + file QA, honest about
   skipped visual QA

## Non-negotiable rules

- Never fabricate a metric value for a slide — `metis_mcp/dq_metrics.py`'s
  real `value: None` (with a reason) for a not-yet-computable metric is
  shown as "no real data yet," never silently dropped or guessed.
- Never regenerate a previously-shared deck "to fix staleness" — a shared
  deck is a fixed record of its own generation time (§12.5's own stated
  design point); generate a NEW deck instead.
