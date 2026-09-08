---
topics: practice
---
# 11 · Which skill, and why that one

Métis has forty skills. This is how to pick one, and — more usefully — why
the boundaries fall where they do, which is the part no individual skill can
explain about itself.

## Start from the question you actually have

| You want to… | Reach for | Because |
|---|---|---|
| bring in what somebody *said* the system should do | `metis-intake-processor` | a tracker item is a claim, and it lands as one |
| turn a stated rule into checkable criteria | `metis-knowledge-capture` | mining is judgement, and it stops at `Quarantine` |
| find out what the code *actually* does | `metis-model-build` | recovery, not reading — the model comes from a code property graph |
| the same, from a repository you haven't got yet | `metis-model-build-code` | it starts one step earlier: `metis checkout` |
| check the machine is well-formed | `metis-behavior-modeling` | determinism and guard completeness are properties of the model, not of a run |
| decide approve or reject on what was recovered | `metis-review-assist` | G1 is a person's decision, and this walks them to it |
| turn an approved model into test cases | `metis-test-generate` | generation reads only `Approved` (D-10) |
| …for an API surface | `metis-test-generate-api` | the guard is the endpoint's own; the space comes from the contract |
| …for a UI surface | `metis-test-generate-ui` | a guard may be inherited (M-5c), and a selector is authored or absent |
| know how covered something is | `metis-coverage-report` | and what could **not** be measured, which is the half that makes the rest safe |
| answer "is it ready to ship?" | `metis-release-readiness` | it needs execution evidence, and says so when it has none |
| touch the running system — read a database or cluster, or drive load | `metis-system-contact` | it states the `METIS_EXECUTE` tier before it acts, and a fact observed there is never merged with one recovered from source |
| see what a change puts at risk | `metis-change-impact` | the model knows which behaviour a diff touches |
| put the specification where the team reads it | `metis-spec-writeback` | a spec only Métis can see is one nobody reads |
| work out whether a half-formed idea can be imported at all | `metis-business-analyst` | four readings, and only one of them can refuse |
| decide what testing a behaviour should consist of | `metis-test-design` | coverage says *whether* it is tested; this says *what* testing it means |
| …which technique, and how many cases | `metis-test-design-technique` | chosen from the guard, never from a name (X-6) |
| …what the data must satisfy | `metis-test-design-data` | conditions on the accepted space, never values (M-9) |
| …which level, and can it be automated | `metis-test-design-levels` | assignment is not execution, and nobody has said what the environments are |
| assess the risk a requirement or release carries | `metis-risk-manager` | a risk Métis derived is never merged with one a person asserted |

## Why thirteen and not one

Because the refusals differ, and a skill is mostly its refusals.

`metis-knowledge-capture` must refuse to invent a criterion from prose that is
not EARS-conformant. `metis-test-generate` must refuse to emit a value where the
model states a space. `metis-release-readiness` must refuse a verdict built on
coverage alone. Those are three different disciplines, and a single skill
carrying all of them would carry none of them well — the one that mattered would
be buried among the dozen or more that did not apply.

## Why some skills drive a workflow and some do not

Ten of them drive one of the ten workflows end to end — one each, with none
left over in either direction. The others wrap
something smaller:

- `metis-behavior-modeling` wraps a **stage** — validation, which runs inside
  other workflows too
- `metis-review-assist` wraps a **gate** — G1, which is a person's decision, not
  a stage that can run

`metis-change-impact` used to be a third. It wrapped `impact` — one question,
read-only, no gate — and it now also drives `change-approval`, because
*approving a change* turned out to be an end-to-end act with a decision at the
end of it rather than a question. The question is still answerable on its own;
the workflow is what acts on the answer.

"Drives no workflow" is a description, not a deficiency. The router says so
rather than leaving a reader to wonder which of the six a skill belongs to.

**`metis-intake-processor` used to be on that list**, described as wrapping "an
intake — landing a document is not a pipeline". That was true of one document
and wrong about a backlog. Requirement ingestion was the only major path with no
workflow, no gate and no resumable run, while model recovery and test generation
both had full ones — backwards for a tool whose first job is requirement
management. It drives `intake` now — and the order moved once more, because
landing a claim before anybody had read it meant the first sight of what was
wrong with it came after it was a node:

    fetch → validate → analysis → readiness → land → requirement-risk → G1

The two new stages are lesson 19's subject. `readiness` is the one to know: it
is a **blocking stage and not a gate**, because there is no literal that passes
it — a need nobody has specified is fixed by specifying it.

## The two you will reach for and not find

**There is no "review my code" skill.** `metis-change-impact` grades what a diff
leaves *unasserted* — behaviour nothing validates, coverage that is positive-only
— and says plainly that style, naming and lint are not reviewed. Métis has no
language server; a second opinion here would be worse than the tools your
repository already runs.

**There is no "write the test code" skill.** Métis emits BDD scenarios and a flow
manifest; binding them to a framework happens outside, and
[lesson 9](09-generating-code-from-a-flow.md) is the seam.

## When two fit equally well

Ask. The router returns no match on a tie deliberately — two workflows scoring
equally is exactly when a person should choose, and a run started in the wrong
one produces a confident artefact about the wrong thing.

## What to remember

- **Pick by the question, not by the noun.** "Coverage" appears in three skills;
  what differs is whether you want a figure, an adequacy judgement, or a
  readiness call.
- **A skill is mostly its refusals** — that is why there are thirteen.
- **Driving no workflow is a description.** Four of them wrap a stage, a tool, an
  intake or a gate.
- **On a tie, ask.** Guessing is how a run lands in the wrong place.
