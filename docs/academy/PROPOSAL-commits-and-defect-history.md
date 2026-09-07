---
system: metis
topics: [ontology, risk, evidence]
---

# Proposal — `Commit` as a node, and defect history as evidence

**Status: ACCEPTED, 2026-09-06.** A `Commit` label with `FIXES` and `TOUCHES`
edges, landed at intake. What is refused is the thing it would be easy to build
by accident: `Defect` nodes synthesised from commit messages.

## What exists today

The ticket half is already there and is better than it looks:

| Node | What it is |
|---|---|
| `JiraItem`, `ZephyrItem`, `ConfluenceItem`, `OpenApiItem`, `CodeItem` | the source anchor an intake lands |
| `Defect` | a reported fault — `summary`, `status`, `provenance`, `external_key` |

with `<Source>Item -REPRESENTS-> Requirement`, `JiraItem -LINKS_TO-> JiraItem`,
`Defect -CONCERNS-> Requirement` and `Defect -OBSERVED_IN-> TestExecution`.

What is missing is everything on the code side. `Episode.commit` is a **property**
— one string naming the commit an extraction ran against. There is no node for a
commit, so nothing can say *this change fixed that ticket* or *this file has been
repaired eleven times this year*, which is the single strongest defect predictor
in the literature and the one PRISMA factor Métis has to ask for.

## The case for

**Defect history is a gathered fact and Métis is asking for it.**
`risk/product.py` declares `defect_history` as an `ASKED` input with
`absent_means: "no history offered. Métis sees one snapshot of execution results
and cannot supply a trend"`. That was true and it need not be: the repository is
right there, and `engine.changed_files` already shells out to git for a commit
range.

**It is the join nothing else can make.** A ticket says *what* was wrong. A
commit says *where it was fixed*. Neither alone reaches the code; together they
put a defect on a `Class` — and from there on the `Transition` risk already
bands. Every other route to that join is a person reading two systems.

**The nodes it needs mostly exist.** `Defect` carries `external_key` precisely so
it can be tied to a tracker item. This adds the third corner.

## The case against, which is D-1's bar

D-1 refuses a writer with no reader, and the honest risks here are two.

**A commit is not a defect, and the shortcut is very tempting.** Matching
`/\b(fix|bug|hotfix|patch)\b/` against a commit subject and creating a `Defect`
would produce a graph full of faults nobody reported. Commit messages say
"fix typo", "fix build", "fix review comment". A `Defect` node means somebody
observed a fault; a commit message means somebody typed a word. Merging them is
C-11's shape one domain over — an inference wearing a report's label.

**Git history is unbounded and mostly irrelevant.** A five-year repository has
tens of thousands of commits and none of the old ones tells you anything about
the code as it stands. Landing all of them makes the graph a second copy of git.

## What is accepted, and the rules that make it safe

**One new label.**

    Commit    sha, subject, committed_at, provenance, is_fix, fix_basis

**Three new relationships.**

    Commit -TOUCHES-> Class          the file it changed
    Commit -FIXES->   JiraItem       where the subject names a ticket key
    Defect -CONCERNS-> AcceptanceCriterion   (widens the existing CONCERNS)

**Rule 1 — Métis never creates a `Defect` from a commit.** `is_fix` is a
*classification of the commit*, with `fix_basis` naming the pattern that matched,
and it is a claim about the message and not about the code. A `Defect` node is
created only where something reported one: a tracker item typed as a bug, or an
observed `TestExecution` failure. Where a commit subject carries a ticket key,
the edge is `FIXES` to the **item**, because the item is the report.

`test_history.py` asserts no `Defect` is ever planned from a commit, on both the
reporting and the fetching path.

**Rule 1a — a missing item is reported, and may be fetched. It is never dropped.**
The first implementation skipped the edge in silence where the graph did not hold
the ticket, and that is this codebase's own named failure mode: a commit saying it
fixed `ABC-123` when Métis has never heard of `ABC-123` is *information* — the
backlog was never intaken, or the team references a project nobody mentioned —
and a plan that quietly omits the edge reports a clean landing over a broken
chain. Every unresolved key now lands in `plan.skipped` with the reason.

Reporting is the floor, not the ceiling. `plan_repairs` takes an optional
`fetch_missing` callable: given one, the missing items are read from the tracker
**first**, landed as anchors at `Quarantine`, and the commit is then linked to a
node that exists by the time the plan is written. It is injected for the same
reason `tracker.read` injects its transport — no HTTP library is a dependency of
Métis, the credential never passes through the module (PLT-005), and a test
supplies a stub. Absent, nothing reaches the network: fetching is a call somebody
has to ask for.

A tracker that cannot be read is reported with the transport failure named, and
the repairs still land. A tracker being down is a fact about the run, not a
reason to lose the history.

A fetched item's `issue_type` is whatever the tracker says, and `unknown` where it
says nothing — never defaulted to `Bug`, which would assert a defect nobody
typed. That is Rule 1 again, one field over.

**Rule 2 — the window is stated and bounded.** History is read for an explicit
commit range, the same one `impact` already takes, and the range is recorded on
the `Episode`. A count with no window is not a measurement; "eleven fixes" means
nothing without "since when".

## What this does not do

- **No author, no blame.** `Commit` carries no author field. Defect counts per
  person are a management use of a quality signal and this system will not supply
  the column.
- **No line-level attribution.** `TOUCHES` reaches the file's `Class`, not a
  method. A finer join needs a diff parse and buys nothing the band can use.
- **No defect prediction.** The count feeds `product.technical_profile` as one
  ordinal factor beside branching and coupling. It ranks; it does not forecast,
  and `MEANS` says so.

## The condition that would reverse it

If, after two releases against a real repository, `defect_history` is still
consulted through the register by hand rather than through the graph — because
the fix pattern turned out to be too noisy to trust, or because teams do not put
ticket keys in commit messages — then `Commit` has a writer and no reader, and it
should be staged out with that finding recorded. The `ASKED` input stays declared
either way, so the question survives the node being removed.
