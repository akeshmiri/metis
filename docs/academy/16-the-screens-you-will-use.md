---
topics: operator
---
# 16 · The screens you will use

Someone starts the review interface with `metis ui` and gives you a link. It runs
on that person's machine; it is not a website and it is not shared.

**You will be asked to sign in before you can decide anything.** Reading needs no
credential — the model, the evidence and the coverage figures are all served to
anyone who can open the page. Deciding needs a token, because a decision records
*who* made it, and a name anybody can type is not a who. Ask whoever set the
system up for yours.

## What has a page, and what does not

Be aware of the boundary, because it decides where you work:

| Decision | Where you do it |
|---|---|
| **Approve the model** (G1) | a page |
| **Name a state** | a page |
| **Resolve a divergence** | the command line |
| **Confirm a match** | the command line |
| **Decide a drift item** | the command line |
| **Confirm publication** (G2) | the command line |

The last four are not missing by accident. Each one is *about* something Métis
has to be handed — two sides of a disagreement, a proposed match, a published
test case that has drifted — and a page cannot draw an item nobody supplied. The
command-line route for all of them is the same three steps, and every halt
message prints it with your journey already filled in:

```
metis review export --journey <journey> --surface api -o review.json
# open review.json, set `reviewer`, and mark each item approve / reject / defer
metis review apply --journey <journey> --surface api review.json
```

## The model view

The page you land on. It draws the system as a picture: every situation as a box,
every move between them as an arrow, and colour carrying two facts at once.

**Box colour is the decision state** — `Approved`, `Quarantine`, `Disputed` —
so you can see at a glance how much is still waiting on you.

**Arrow style is coverage** — whether a test case reaches that move yet.

Underneath, one line: *12 covered, 5 uncovered under all-transitions*. The last
part matters. Coverage is always relative to a criterion, and a figure without
one means nothing.

This picture is the single clearest artefact the system produces, and it is the
main reason a purpose-built screen exists rather than a conversation.

## The six decisions

Everything a person decides is one of six things, and each has its own required
evidence — which is checked, and which blocks the decision when it is missing.
That rule is enforced wherever the decision is taken, so the rest of this page
matters equally whether you are on a page or at the command line.

| Decision | You are answering |
|---|---|
| **Approve the model** | Is this an accurate picture, and do the criteria say what we meant? |
| **Name a state** | What should this situation be called? |
| **Resolve a divergence** | The code and the requirement disagree — which one is wrong? |
| **Confirm a match** | Does this criterion really validate that behaviour? |
| **Decide a drift item** | A published test case no longer matches. Update, deprecate, or leave it? |
| **Confirm publication** | Send this batch to the tracker |

### Approve the model

The gate. Before you can decide, you must be shown: the picture, every
validation finding, the gaps in **both** directions of the comparison, where each
element came from, and every state nobody has named.

If any of that is missing, **the decision is refused** and you are told what is
absent — not warned, not greyed out. Approving without evidence is the exact
failure the gate exists to prevent, so the refusal is the feature.

### Name a state

Métis proposes names and never assumes one. You get the raw observable signature
(what the system actually returns), candidate names mined from the acceptance
criteria, candidates from code conventions, and the names already used by
neighbouring states so you do not invent a third word for the same idea.

Naming is not agreement. Giving a state a sensible name does not approve it.

### Resolve a divergence

Both sides, with their sources: the code with its file, line and commit; the
criterion with its text and ticket. Plus the test paths currently blocked by the
disagreement, and what each choice implies:

- **Accept the code** — the criterion is stale; the requirement needs updating
- **Accept the criterion** — the implementation is wrong; this is a defect

**Neither is recommended.** No rule can decide which of a defect and a stale
requirement is right, so a resolution requires a written reason. Recording only
the outcome would make your choice indistinguishable from an automatic rule
attributed to you.

### Confirm a match

The criterion's text, the behaviour's full detail, the code anchor, and — the
part that matters — **why it was proposed**. You need to see that a match rests
on a route and a status code rather than on two sentences sounding alike, because
wording similarity is never sufficient evidence.

A rejection is recorded, not deleted. A proposal you refused must not come back
looking new next month.

### Decide a drift item

A test case was published, the model changed, and they no longer match. You see
three versions side by side: what was published, what was generated last time,
and what would be generated now.

If the case was **edited by hand**, Métis proposes nothing and says so.
Métis will not offer to overwrite somebody's work.

Nothing is ever deleted — the strongest action is *deprecate*.

### Confirm publication

The last gate, and the only thing that writes outside Métis. You see the whole
batch, every operation enumerated, and the target.

**A batch decision must show its contents.** An "approve all" that does not list
what it covers is prohibited outright.

## Two rules that protect you

**A decision whose evidence cannot be shown is blocked.** Not a warning, not a
greyed-out field — a refusal, naming what is missing.

**You cannot approve what you proposed.** If you wrote it, somebody else
approves it. This can be overridden when a team is too small for it, and the
override is recorded and visible in the audit trail. It is never silent.

## What is recorded

Every decision, through every route, produces the same record: who, when, what
was decided, why, and a fingerprint of the evidence that was in front of you.

That last field is the one that makes an audit meaningful. It records what you
were *shown*, not merely what existed — so a decision cannot later be defended
with information you never saw.

Next: [when Métis refuses](17-when-metis-refuses.md).
