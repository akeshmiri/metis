# Step 1 — Confirm project_test_id_conventions (REQ-METIS-CONN-06)

**Scope Lock:** the one project/repository being onboarded.

## Actions

1. Ask the user for the project's real traceability-tag convention (e.g.
   "REQ-METIS-*/CONST-* tags in a test module's docstring," matching what
   `connectors/test_suite_connector.py` currently implements for the
   `metis-server` project itself — see that file's docstring).
2. If the user can't state a real, confirmed convention: **halt here.**
   Per `REQ-METIS-CONN-06`, an unconfirmed convention is a setup gap, not
   something to guess at from the project's name or language. Do not
   assume a "probably standard" pattern.
3. If confirmed: record it. (This build resolves the convention via
   `connectors/test_suite_connector.py`'s hardcoded `TAG_PATTERN` import
   from `corpus.py` — a genuinely per-project-configurable convention
   resolved through `config_manager.py`, matching every other connector
   setting in this codebase, is a real follow-up task, not done yet for
   this connector specifically.)

## Stage Confirmation
`[C]ontinue to Step 2` / `[R]eview` / `[B]ack` / `[X]it` — halts
automatically (chain-mode failure) if step 2's action above wasn't
confirmed.
