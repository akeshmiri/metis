# Theme tokens

**Real, disclosed state:** no custom brand `.potx` template has been
designed for this skill yet — `script/build_deck.py` uses python-pptx's
own built-in default presentation theme (`Presentation()` with no
template argument). `REQ-METIS-SLD-02` ("`script/` and `templates/` are
versioned independently") is honored structurally (this folder is
already separate from `script/`), but there is no real theme to version
yet — this file is the placeholder that makes that gap visible rather
than silently absent.

When a real brand template exists (a `.potx` file), it goes in this
folder, and `script/build_deck.py` loads it via
`Presentation("templates/<name>.potx")` instead of the current bare
`Presentation()` call — a one-line change, not a rewrite.
