# Step 2 — Generate

Run `script/build_deck.py <output_path> [scope]`, which wraps
`metis_mcp.pptx_renderer.render_quality_deck(session, output_path, scope)`
directly — the script holds no content logic of its own (§4.6.1's
content-boundary rule: `script/` is generation logic only).

Real output, per the actual implementation (not aspirational): a title
slide (scope + a real, verbatim `generated_at` timestamp), a composite
quality-score slide, and — only if any DQ metric actually has real
computed data — a metrics slide. A metric with `value: None` is never
padded onto that slide as a fake row.
