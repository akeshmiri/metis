---
topics: operator
---
# 13 · The words we use

Several ordinary words mean something narrower here. Where a term is borrowed
from engineering, the plain sentence comes first and the precision comes second.

## The model

**State** — a situation the system can be in, described by what you could
*observe* about it. *Logged out*, *account locked*, *record archived*. Not a
screen and not a database row: a condition somebody could check.

**Transition** — one move from one state to another. *Submit valid credentials*
takes you from *logged out* to *logged in*. A transition is the unit everything
else attaches to: coverage is counted per transition, and an acceptance
criterion validates a transition.

**Trigger** — what causes a transition. A button press, an API call.

**Guard** — the condition that has to be true for a transition to happen.
*Account is not locked*. Métis records a guard **exactly as it found it** and
does not try to solve it; deciding what to actually send is a person's job.

**Model** — all the states and transitions for one journey on one surface,
together. `login-api` is a model.

**Journey** — a coherent piece of the system a person would name: *login*,
*records*, *billing*.

**Surface** — where the behaviour happens: `api` (a service) or `ui` (a screen).
The same journey usually has both, and they are separate models because they
genuinely behave differently.

## What is claimed, and by whom

**Requirement** — one statement of what the system should do, written by a
person. It has to be phrased in a checkable way (see *EARS* below), or Métis
will not treat it as a requirement.

**Acceptance criterion** — one **atomic** condition: one situation, one action,
one thing to check. *Given the account is locked, when valid credentials are
submitted, then the response is 423.* If a sentence contains "and" joining two
different checks, it is two criteria.

**EARS** — a way of phrasing requirements so they can be checked. It just means
the sentence follows a recognisable shape: *When ⟨trigger⟩, the system shall
⟨response⟩*. A Jira title like "Login is broken" has no such shape, so Métis
records it as something to formalise rather than pretending it is a requirement.

**Finding** — something Métis noticed that a person should look at. Not an error.
A ticket whose wording is not checkable becomes a finding saying so.

## Trust and status

**Quarantine** — found, not agreed. Everything Métis recovers starts here.

**Approved** — a person looked at it and accepted it. Only approved things are
used to generate tests.

**Disputed / Rejected / Deprecated** — the other outcomes a person can record.

**Provenance** — where a claim came from, and therefore how much it is worth:

| Grade | Meaning |
|---|---|
| `code_derived` | Written from the code it describes. Weakest — it agrees with the code because it was copied from it |
| `human_confirmed` | A person read it and stood behind it |
| `independently_authored` | Somebody wrote it without looking at the code. Strongest, because it can disagree |

That ladder is why Métis is careful about the word *correct*. A `code_derived`
criterion agreeing with the code proves nothing at all.

## Time

**Valid from / valid to** — when a claim started being true and when it stopped.
Nothing is deleted; a superseded requirement stays readable, so *what did we
believe in March* is a question you can ask.

**Revision** — how many times a requirement's wording has changed. Editing the
text creates revision 2 and leaves revision 1 in place with whatever decision it
already had.

## The two moments a person has to act

**G1 — model approval.** Before anything is generated. You are deciding: *is
this an accurate picture of what the system does, and do these criteria say what
we meant?*

**G2 — publication.** Before anything is written outside Métis. You are
deciding: *send this batch of test cases to the tracker.*

There are exactly two gates. Nothing else waits for you, and nothing passes
either one because time elapsed.

## Words you will see in reports

**Coverage** — how much of the behaviour has a test case. It answers *is this
tested*, never *does this work*.

**Unverifiable** — Métis found a condition it could not read well enough to
judge. It is reported as its own outcome, never quietly counted as a pass.

**Uncovered** vs **unmeasurable** — *uncovered* means no test reaches it;
*unmeasurable* means Métis could not tell either way. A report that merged them
would be worse than one that omitted both.

Next: [which parts are yours](14-your-first-week.md).
