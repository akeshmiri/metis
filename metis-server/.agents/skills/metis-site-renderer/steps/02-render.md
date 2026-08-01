# Step 2 — Render

Run `script/build_site.py <output_dir>`, which wraps
`metis_mcp.site_renderer.render_site(output_dir, session)` directly.
Writes one real HTML file per Academy page (via the real `markdown`
library, not a hand-rolled parser) plus `index.html` linking all of them
and showing the current composite `quality_score`.

Safe to re-run any time — every file is fully rewritten from current
content each call, never patched incrementally.
