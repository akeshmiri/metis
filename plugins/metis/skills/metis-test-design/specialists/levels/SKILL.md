---
name: metis-test-design-levels
description: Assign the level each condition is asserted at, report what already covers it under the three-grade taxonomy, and classify what can be automated at all. Use when a request is about test levels, the pyramid, whether something is already tested, or whether it can be automated.
allowed-tools:
  - design_sections
  - design_inputs
  - design_report
  - test_design
  - coverage
  - coverage_report
  - get_model
  - trace
  - product_risk
  - risk_priority
  - ask
  - run_status
  - list_workflows
---

# Métis test-design · levels

## Prerequisites, from the parent

The parent (`metis-test-design`) has already established, and this skill does
not re-derive:

- a design missing a required input is `incomplete`, never lean;
- the shape comes from `design_sections()` and is never restated in prose;
- rows are ordered by risk, and a band ranks — it never forecasts;
- Métis proposes every row and decides none of them.

This skill owns the `levels`, `profile` and `setup` sections.

## What this does

Three judgements per behaviour, and the value of the section is that they stay
apart:

- **level** — where the assertion sits in the pyramid. Not what it asserts.
- **existing** — what already reaches it, in three grades.
- **viability** — whether it can be automated at all, and why not.

Plus the join that neither figure makes alone: **depth achievable against depth
warranted.**

## The middle grade is the honest one

| Grade | Means |
|---|---|
| `covered` | a test reaches it **and** asserts its outcome |
| `endpoint_covered_outcome_unproven` | a test reaches the endpoint; **this outcome** is not evidenced |
| `uncovered` | nothing reaches it |

Promoting the middle grade to `covered` excuses real gaps. Demoting it to
`uncovered` discards real evidence. It stays its own grade and a person decides.

## Assignment is not execution

A level can be assigned from the model. Whether it can be **run** depends on
which environments exist, and nobody has told Métis. That is why `environments`
is a required asked input and why its absence makes every level below a
proposal.

## The band hides what, and `profile` is what it hides

A risk band says *how much there is to get wrong*. It does not say *what* — and
the answer changes the response:

| Factor | What it asks the design for |
|---|---|
| branching | more cases: one per condition combination |
| fan-in | a contract nobody may break; changing this outcome reaches every caller |
| fan-out | a decision table over the group, which is where a missing rule hides |
| unverifiable guards | no oracle — cover it another way, and say which |
| repair history | the strongest single signal here |

**"Test this more" is the answer to none of them**, and it is the only answer a
band alone supports.

**An unmeasured factor is a row saying so, never a blank.** A blank in a column
of counts reads as zero, and zero here reads as *simple*. `repairs` is the one to
watch: a file counted and never repaired is not the same as a file nobody
counted, and only `repairs_window` tells them apart — it is empty exactly when
nobody asked.

## Setup cost is computed, where the obvious version is guessed

The practice this comes from classifies a slice by its business verb — `get` and
`view` are cheap, `create` and `approve` are not. That is a stand-in for the real
question: how much has to be true before the assertion can happen. Métis answers
it directly, because `Path.setup_transition_ids` **is** the chain a test must
establish.

| Column | Recovered from |
|---|---|
| `effect` | the HTTP verb, or `unknown` — a UI trigger carries none, and calling one `read-only` would put the cheapest band on a write |
| `setup_depth` | the path, not a verb |
| `preconditions` | the setup chain. Paths sharing it share a precondition (P-14a) |
| `complexity` | the two above, by a stated rule a reader can disagree with |

**The pattern is not Métis's to pick.** Whether existing data can be reused, or
an isolated entity must be provisioned, depends on what the environment holds
and who owns cleanup — both `asked`. Métis costs the behaviour and states the
two facts behind the cost; choosing with that in hand is a person's job.

`escalate` is not a verdict that something is too hard. It says split it, stage
it, or make the cost visible — never hide it inside a precondition.

## Steps

`steps/01-assign.md`, then `steps/02-depth.md`.

## What this skill must not do

1. **Never award `automate` on a name** (X-6). It needs recovered evidence
   pointing at a source line; an unverifiable guard defers because there is no
   oracle, and an unresolved precondition is manual-only (P-8).
2. **Never report an assigned level as a schedulable one.** Without
   `environments`, nothing here can be run.
3. **Never collapse the three grades into covered/uncovered.** That is the whole
   subtlety, and both directions lose a real fact.
4. **Never read `covered` as `passing`** (C-11). A behaviour can be fully
   covered and currently failing.
