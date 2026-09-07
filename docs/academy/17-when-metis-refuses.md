---
topics: operator
---
# 17 · When Métis refuses

Métis refuses often, and on purpose. A refusal is the system working — it is
what stops a plausible wrong answer reaching you. This page is what each one
means and what to do next.

**The general rule:** if Métis could not establish something, it says so rather
than producing something that looks established. When you see a refusal, the
information you need is in it.

## Refusals you will meet

### `BLOCKED (G1): …`

**What it means.** Something is trying to generate from a model nobody has
approved. Generation reads only approved elements, so this is the gate doing its
job.

**What to do.** Review the outstanding elements and approve or reject them. The
message names which ones are still waiting — you can act on a list, not on a
count.

**What not to do.** There is no override and no timeout. An unreviewed model
stays unapproved indefinitely, and the safe failure is *no tests generated*
rather than *tests generated from a picture nobody checked*.

### `BLOCKED (M-18): …`

**What it means.** The model is not well-formed — usually two moves out of one
situation on the same trigger with no condition telling them apart, so the system
could go either way and no test could say which is right.

**What to do.** This is a real problem in the model, and it is usually a real
problem in the requirements too. Look at the pair it names.

### `the text is not EARS-conformant`

**What it means.** A ticket's wording has no checkable shape, so it lands as a
finding rather than a requirement.

**What to do.** Rewrite it: *When ⟨situation⟩, the system shall ⟨result⟩.*

**Why Métis will not do it for you.** It would have to guess what you meant, and
a fluent requirement nobody wrote is the most expensive kind of wrong — it reads
as agreed.

### `not-ready — N gap(s) mean this cannot be represented`

**What it means.** A claim was read before anything was landed, and one of the
readings found something that cannot become a node honestly — usually a need
with no stated behaviour. Landing it would create something nothing can ever be
checked against, so it would sit in the review queue forever.

**What to do.** Fix the claim. The message names the gap and what would close it.

**What not to do.** Look for the override. There is not one, and that is the
difference between this and a gate: a gate waits for somebody to decide, and
this is waiting for the sentence to change. Nobody can decide their way past it.

**What is *not* refused.** A claim nobody has costed, whose environments are
unlisted and which has no acceptance criteria yet, is imported — carrying all
three of those recorded beside it. Only *unrepresentable* is refused; unfinished
is normal, and refusing it would mean Métis only ever accepted work that was
already done.

### `the design is incomplete`

**What it means.** A test design is missing required inputs — usually the
architecture, the environments, or what "too slow" means. Nobody has answered
them, and the design says so above its first section rather than below its last.

**What to do.** Answer them, or record that nobody will. Both are outcomes; only
silence is not.

**Why it is not an error.** It is a status, and the sections that could be
derived are still there. What it prevents is reading a design built on half its
inputs as a finished one.

### `unmet — no such outcome was recovered`

**What it means.** An endpoint's own shape obliges some behaviour — a path
parameter obliges a not-found — and no such outcome was found in the model.

**What to do.** Decide which it is: the behaviour is genuinely unhandled, or
extraction did not see it. Métis cannot tell, and says so rather than guessing.

**What it is not.** A defect report. `unmet` is a claim about what was
*recovered*, and the outcomes that *were* recovered are printed beside it so the
question is answerable. One real example: `GET /metric/{id}` produces 200, 204
and 400 and no 404 — which may well be deliberate, and is worth somebody
confirming.

### `unverifiable`

**What it means.** Métis found a condition it could not read well enough to
judge. It is reported as its own outcome, never counted as a pass.

**What to do.** Read it yourself and record what you decide. You can proceed
past unverifiable guards deliberately; that choice is recorded rather than
silent.

### `NOT PERMITTED (N-9): …`

**What it means.** Your role does not carry that action. The message names the
roles that do.

### `NO GRAPH: …`

**What it means.** The database is not running or the credential is wrong. This
is infrastructure, not your work.

**What to do.** Pass it to whoever set the system up — the message says which of
the two it is.

### `NOT CONFIGURED: …`

**What it means.** Something was never set up, as opposed to being broken.

### `this review session is read-only`

**What it means.** The screen has nowhere to store your decision, so it declined
to take it.

**Why it refuses instead of accepting.** Taking the decision and dropping it would
be worse in every way: you would believe it was recorded.

### `cannot decide … : missing …`

**What it means.** A decision screen could not show everything needed to judge,
so it will not let you decide.

**What to do.** The message names exactly what is absent.

## Things that look like refusals and are not

**`0 covered`** — a real answer. Nothing is tested yet.

**`could not be measured`** — different from *uncovered*, and the more important
of the two. *Uncovered* means no test reaches it. *Unmeasurable* means Métis
could not tell either way, and reporting them as one number would be worse than
reporting neither.

**A finding** — a note for a person, not an error. A backlog of findings is a
list of work, not a list of failures.

**`{base}` in a test step** — deliberate. Métis does not know your hostname and
will not invent one.

**`<string, length 3..40, required>`** — also deliberate. That is the accepted
space, not a missing value. Choosing an actual value is a judgement about test
data, which is a person's job.

## What to do with a refusal you do not understand

Every refusal carries a rule id — `S-13`, `M-18`, `N-9`. Those are defined in
the application specification, and the code cites the same ids where it enforces
them. If a message names one, the reasoning behind it is written down somewhere
you can read.

---

That is the operator track. If you want to know *why* the system is built this
way — why nothing auto-approves, why a guard is preserved verbatim, why the
ontology is closed — the concepts track starts at
[lesson 1](01-what-metis-does-not-do.md).
