# The risk breakdown structure

Standard practice. The canonical list is in `risk_categories()`, which is the
implementation and the thing to call — this file says what an RBS is *for*, which
a tool cannot.

## What it is for

An RBS is a taxonomy of risk *sources*, hierarchical the way a WBS is a taxonomy
of work. It does three things a flat list cannot:

1. **It prompts.** Walking ten categories asking "what could go wrong here"
   finds risks that free brainstorming misses, because unprompted recall
   clusters around whatever the team is currently worried about.
2. **It reveals absence.** A category with no risks in it is the interesting
   one — either genuinely safe, or nobody looked. `risk_categories` and
   `rbs.distribution` report empty categories rather than dropping them, for
   exactly this reason: a chart built only from present keys cannot show a gap.
3. **It aggregates.** Exposure by category shows where the project is actually
   fragile, which a ranked list of individual risks does not.

## It is organisational, and narrowing is expected

The set Métis ships is a starting point. A regulated business will split
Compliance into several; a small internal project may merge four. **Narrow it in
one place** and use the narrowed set everywhere — the failure mode is a register
carrying `Tech`, `Technical` and `technical` as three rows in one chart, which is
why the category is validated rather than free text.

## Depth

Two levels is usually right: a category, and a sub-category naming the source.
Three levels is a taxonomy nobody maintains. The test is whether the extra level
changes a response — if it does not, it is filing.
