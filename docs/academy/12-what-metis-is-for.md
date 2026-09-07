---
topics: operator
---
# 12 · What Métis is for

*This is the first page of the operator track. If you are a business analyst,
product owner, QA lead or reviewer, start here. Nothing on this page assumes you
can read code.*

## The problem it exists for

Somebody wrote down what the system should do. Somebody else wrote the code.
Time passed.

Now nobody can say, with evidence, whether those two things still agree. The
document says a locked account unlocks after 30 minutes. Does it? The only way
to find out is to read the code, and the people who wrote the document usually
cannot.

Métis answers that question by doing three things in order:

1. **It reads the code and works out what the system actually does** — not what
   the comments say, not what the tickets say. What the code does.
2. **It compares that against what people said it should do** — the tickets, the
   wiki pages, the acceptance criteria somebody wrote.
3. **It shows you where those two disagree**, and turns the part you approve into
   test cases a person can execute.

## The finding that justifies the whole thing

> *The code locks the account after 3 failed attempts. The acceptance criterion
> says 5.*

That is the output. Not a test that passes, not a coverage number — a **stated
disagreement between two sources**, with a line of code on one side and a ticket
on the other.

No amount of testing the code against itself will ever produce it. A test
generated from the code proves the code does what the code does, which is true
and useless. The comparison is the point.

## What it will not do, and why that is deliberate

**It will not tell you the system is correct.** It can tell you a behaviour is
*tested*. Whether the behaviour is *right* is a judgement about what the business
wanted, and Métis has no way to know that — so it never claims to.

**It will not approve anything itself.** Everything it recovers arrives marked
*Quarantine*, which means "found, not agreed". A person moves it to *Approved*.
Nothing is generated from anything that has not been approved by a human, and
nothing gets approved because time passed.

**It will not guess.** When it cannot work something out, it says so rather than
producing a plausible answer. A test step will say `<a string, 3 to 40
characters, required>` rather than inventing `"test123"`. That is not
incompleteness — a made-up answer that looks real is worse than a visible gap,
because you cannot tell it is wrong.

## What you get out of it

| | |
|---|---|
| **A map of what the system does** | Every situation the system can be in, and every way it moves between them |
| **A list of disagreements** | Where the code and the written requirements do not match |
| **Test cases a person can run** | In plain steps, traceable back to the requirement they came from |
| **An honest coverage figure** | What is tested, what is not, and — the important part — **what could not be measured at all** |

## Where you fit

You will spend your time in one of four places, and the next lessons take each
in turn:

- **Bringing requirements in** — from Jira, Confluence, or your own writing
- **Reviewing what Métis found** — the approve/reject decisions that gate
  everything else
- **Reading the reports** — coverage, readiness, what changed
- **Acting on disagreements** — deciding whether the code is wrong or the
  requirement is stale

Next: [the words this system uses](13-the-words-we-use.md), because several of
them mean something narrower here than in ordinary speech.
