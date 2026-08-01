# Step 1 — Gather content (R/P, RPI-gated)

Call `metis_mcp.academy.assemble_content(session, kind="quality_summary", scope=<scope or None>)`.
This is the exact same call `metis-site-renderer`'s own step 1 makes —
content is gathered once, in one real place
(`metis_mcp/dq_metrics.py`'s real Cypher computations underneath it), never
re-derived independently per renderer.

**Scope Lock:** the deck covers exactly the `scope` given (a service,
release, or `all`) — do not silently broaden to "everything interesting"
if the gathered content looks thin.

**Forbidden Substitutions:** if `quality_score` comes back `None` (not
computable — see the returned `note`), that is what goes on the slide.
Never substitute a guessed number, a prior run's cached number, or a
rounded "close enough" placeholder.

Confirm the gathered `summary` dict before proceeding to step 2 —
standalone mode pauses here per the Stage Confirmation Protocol.
