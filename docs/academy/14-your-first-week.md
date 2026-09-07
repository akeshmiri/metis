---
topics: operator
---
# 14 · Your first week

Four roles, four different first hours. Find yours.

## If you are a business analyst or product owner

**Your job here is to get what people said into Métis, phrased so it can be
checked, and to settle disagreements when the code says otherwise.**

Day one, in order:

1. **Bring in what already exists.** Point Métis at the tickets or wiki pages
   that state requirements. It reads them and produces one document per item,
   with every field traced back to the response it came from — nothing inferred.
2. **Expect about half of them to bounce.** A ticket titled *"Archive is broken
   again"* is not a requirement; it becomes a finding saying so. That is the
   system working, not failing. Those are the ones you rewrite.
3. **Rewrite them into checkable sentences.** *When a record has been archived,
   the system shall reject an update with 409.* Now it has a shape Métis can hold
   as a requirement.
4. **Break each into atomic criteria** — one situation, one action, one check.

What to expect: the first pass over an existing backlog is the largest single
piece of work, and most of it is rewording rather than deciding.

**What Métis will refuse to do for you:** invent the phrasing. It will not guess
what a vague ticket meant, because a well-formed requirement nobody actually
wrote is the most expensive kind of wrong.

## If you are a QA lead

**Your job here is coverage you can defend, and knowing what is not covered.**

1. **Read the coverage report** for a scope. Three numbers matter, and the third
   is the one to look at first: covered, uncovered, and **could not be measured**.
2. **Check the criterion.** Coverage is always relative to a criterion — *every
   transition*, *every guard*, *every pair*. A figure without one means nothing.
3. **Generate test cases** from the approved model. They come out as plain steps,
   each traceable to the requirement behind it.
4. **Do not read coverage as quality.** A transition can be fully covered and
   currently failing. Métis reports those as two separate figures on purpose.

## If you are a reviewer

**Your job here is the gate. Nothing is generated until you decide.**

You will see a queue of things awaiting a decision. For each, the screen shows
you the evidence: what was found, where it came from, what validates it, and
what is still outstanding.

Two rules protect you:

- **A screen that cannot show its evidence will not let you decide.** If the
  information needed to judge is missing, you get a refusal instead of a
  half-filled page. Approving without evidence is the exact failure the gate
  exists to prevent.
- **You may not approve what you proposed.** If you wrote the criterion, someone
  else approves it. That can be overridden, and the override is recorded
  visibly — never silently.

Lesson 16 walks the screens.

## If you are a developer

You have the rest of the academy. Start at
[lesson 1](01-what-metis-does-not-do.md) — the concepts track assumes you read
code and goes considerably deeper.

The one thing worth knowing before you do: **Métis is not a linter and does not
review your code.** What it can tell you that a linter cannot is *which recovered
behaviour your change touches, and whether anything validates it*.

## What the first month actually looks like

| Week | What happens |
|---|---|
| 1 | Requirements come in. Most need rewording. Nothing is approved yet |
| 2 | The model is recovered from code. The first disagreements appear |
| 3 | Review. This is the slow week, and it is slow on purpose |
| 4 | Test cases from the part that survived review |

**The bottleneck is week 3 and it is meant to be.** An unreviewed model produces
nothing at all, which is the safe failure — the alternative is test cases
generated from a picture nobody checked.

Next: [one requirement, end to end](15-one-requirement-end-to-end.md).
