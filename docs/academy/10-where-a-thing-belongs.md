---
topics: concepts
---
# 10 · Where a thing belongs

Métis has three surfaces an agent meets — MCP tools, skills, agents — and four
places prose can live inside a skill. This is the rule for choosing, and the
reason it is written down at all.

## Why a written rule, and not just good taste

The sibling project this was ported from has a convention document governing its
skills and none governing its agents. Its skill layer is healthy. **Eight of its
eleven agent files carry unresolved merge-conflict markers**, and the "two
halves" every agent has are the two sides of one bad merge nobody resolved. Its
hand-written skill catalogue drifted to roughly forty-five names matching no
directory on disk; its *generated* registry did not drift at all.

Two lessons, and they are the whole argument for this page:

- **The layer with a written rule stayed healthy. The layer without one rotted.**
- **Generated indexes survive. Hand-maintained indexes do not.**

Métis had its own version of the second failure. Nine agents were generated, and
they came out 97 lines each with 93 byte-identical — because the generator had
only two facts per skill to work with, and nothing asserted that two agents
should differ.

## The rule

| Surface | Holds | The question that decides it |
|---|---|---|
| **MCP tool** | a question with a determinate answer the engine computes | *could a unit test assert its output?* |
| **Skill** (`SKILL.md`) | the procedure, its order, its gates, its refusals | *does it tell a model what to do where the answer is not determinate?* |
| **`steps/`** | one stage: what to run, what to report, what not to substitute | *does it have a position in a sequence?* |
| **`knowledge/`** | Métis's own reasoning, cited by a step | *is it a decision we made, with the reason?* |
| **`references/`** | facts about systems Métis does not own | *would it still be true if Métis were deleted?* |
| **Agent** | scope and routing: which skill, which tools, which workflow | *does it change what is permitted, or which skill runs?* |

## The folder tree is a context budget

This is the part that does the work, and it is not an ontology.

```
SKILL.md      always paid for
steps/        one at a time
knowledge/    only when a step cites it
references/   only on lookup
```

So the question "should this go in `SKILL.md` or `knowledge/`?" is not about
subject matter. It is: **would skipping this silently break correctness?** If
yes, it belongs in `SKILL.md`, which is loaded every time. If it is supporting
reasoning that matters only while executing one step, it belongs in
`knowledge/`, where nobody pays for it until they need it.

**Emptiness is a decision and it is recorded.** Every skill has a
`knowledge/index.md` even when there is nothing in it, saying where the content
went instead. An absent directory is something a reader has to interpret.

## Where the reasoning actually lives

Métis carries about 11,700 lines of docstring and comment inside `metis_mcp/` —
roughly 37% of its non-blank Python, and more than the application spec, the
whole skill tree, this academy, the guide, `CLAUDE.md` and the README combined.
That is the real design knowledge: why a rule exists, what broke before it did,
which alternative was rejected.

It stays in the code, because it belongs beside the decision it explains — and
`metis knowledge` (folded into `metis guide`) generates a copy into the skill
that needs it. The docstring is the source of truth; `--check` fails on a diff.
Moving the prose out would put it where an agent can read it and take it away
from where it is maintained, which is the reason it is good.

**Module docstrings only.** Function docstrings are 7,579 lines and would make a
`knowledge/` file more expensive than the `SKILL.md` it was meant to relieve.

## Promotion and demotion: count the consumers

For anything shared:

- **one consumer** → it belongs to that skill
- **two or more** → promote it to `shared/`
- **zero** → flag it; do not move it, and do not delete it on a hunch

## What Python does, and what the model does

Stated because Métis already works this way and never said so:

> **Python computes the skeleton → the model writes the prose → Python verifies
> the prose.**

Path generation is deterministic. Rendering produces sentences. The tests assert
what the sentences must contain. The model is the only part allowed to be
creative, and it is bracketed on both sides by code that is not.

Anything that must be reproducible — path resolution, evidence collection,
structural correctness, gate evaluation — is Python. Anything requiring judgement
— classification, framing, synthesis — is markdown instruction executed by a
model.

## What to remember

- **`SKILL.md` is always paid for; `knowledge/` is not.** That, not subject
  matter, is what decides.
- **`knowledge/` is our reasoning; `references/` is the world's facts.**
- **Consumer count decides promotion.** One → local. Two → shared. Zero → flag.
- **An agent is a scope document**, not a second copy of the skill.
- **Generate the index, or it drifts.** Both projects have the scar.
