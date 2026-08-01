# Step 3 — QA and report (Drift Check equivalent, RPI Gate 4)

Real QA, exactly what `render_quality_deck`'s return dict reports —
nothing here is re-derived or assumed:

- **Content QA**: `content_qa_passed` — no leftover `REPLACE` placeholder
  text, and the deck's own `generated_at` timestamp is verbatim present
  in the rendered text (a real, checkable provenance anchor).
- **File QA**: `file_qa_passed` — the just-written file re-opens cleanly
  via python-pptx and reports the same slide count that was actually
  built.
- **Visual QA**: honestly reported as not built (`"not built -- no
  image-rendering/inspection infrastructure in this environment"`) — do
  not claim this passed; surface the limitation to whoever's about to
  present the deck.

Standalone mode pauses here and shows the human the actual rendered
result (`REQ-METIS-SLD-03`) before calling the deck done — do not
auto-advance past this step.
