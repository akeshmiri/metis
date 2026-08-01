# Step 3 — Confirm structural-extraction language coverage (CONST-063)

**Scope Lock:** the one project/repository being onboarded.

## Actions

1. Ask what languages make up the new project's codebase.
2. This build's Cognify structural extraction
   (`cognify/structural_extraction.py`) parses **Python only**, via the
   stdlib `ast` module — not Tree-sitter, and not any other language. This
   is a disclosed deviation from the connector manifest's stated design
   (see that file's docstring).
3. If the new project is majority-Python: proceed, but note explicitly
   that class/method extraction is Python-only — any non-Python files in
   the project will land as raw Episodes (Phase 2's connector still works
   for any file, since it just stores raw content) but will NOT get
   Class/Method structural extraction.
4. If the new project's majority language is NOT Python: **halt here**,
   per `CONST-063` — this portion of the pipeline is explicitly unsupported
   for that project, not silently producing incomplete or wrong structural
   data. Tell the user this plainly rather than running Cognify anyway and
   hoping the AST parse fails loudly (it would, but that's not the same as
   this skill honestly saying up front that it doesn't apply).

## Stage Confirmation
`[C]ontinue to Step 4` / `[R]eview` / `[B]ack` / `[X]it` — auto-halts on a
non-Python-majority project per the chain-mode failure rule.
