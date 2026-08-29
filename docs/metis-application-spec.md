# Métis — Application Specification

**Status:** approved · **Date:** 2026-08-15 · **Supersedes:** a 13-document
platform spec set (`docs/metis-v2/`), removed once this document carried
everything still true of it — the last item lifted across was the CPG build step,
now X-1(a)

Métis is a **structuring engine**: it turns unstructured information about how a
system should behave into an explicit, validated, user-perspective state machine,
and derives test coverage from it.

*Built incrementally, one section at a time; each section was reviewed before the
next was written. Every requirement in §1 is quoted from the product owner.*

| § | Section | Status |
|---|---|---|
| **1** | **Requirements** | **✅ agreed** |
| **2** | **The structured model** | **✅ agreed** |
| **3** | **End-to-end flow** | **✅ agreed** |
| **4** | **Model sources** | **✅ drafted** |
| **5** | **Code-derived state-transition extraction (R4/R5/R6)** | **✅ drafted** |
| **6** | **Coverage criteria and path generation** | **✅ drafted** |
| **7** | **Test-case rendering and publishing** | **✅ drafted** |
| **8** | **Data model** | **✅ drafted** |
| **9** | **Interfaces** | **✅ drafted** |
| **10** | **Trust requirements** | **✅ drafted** |
| **11** | **Non-functional requirements** | **✅ drafted** |
| **12** | **Out of scope** | **✅ drafted** |
| **13** | **Acceptance criteria** | **✅ drafted** |
| **14** | **Element identity, deduplication and incremental update** | **✅ drafted** |
| **15** | **Closing decisions (O-1 … O-4)** | **✅ drafted** |
| **16** | **The graph database's position** | **✅ drafted** |
| **17** | **Model manipulation** | **✅ drafted** |
| **18** | **Stakeholder specification** | **✅ drafted** |
| **19** | **Acceptance criteria for §§16–18** | **✅ drafted** |
| **20** | **Implementation readiness and the change to Métis** | **✅ drafted** |
| **21** | **How much the plan depends on Joern** | **✅ drafted** |

---

## 1. Requirements

| # | Requirement | Source |
|---|---|---|
| **R1** | Métis is a **central toolset that transforms unstructured information into a structured model** | *"a Metis that can be a centeral toolset for me to transfer all unstrcutred information to structured model"* |
| **R2** | The chain runs **requirement → model-driven testing → automatic test generation** | *"I can get from requierment to model driven testing with auto test generation"* |
| **R3** | Built from **all three owned systems — Atlas, Athena, Métis — combined** | *"using everything I have in my arsenal, Atlas, Athena, Metis all should get to gether"* |
| **R4** | A **state-transition model is generated from code, at a detailed level** | *"we need to generate state-transiton model from code on very detail level"* |
| **R5** | That model is **mapped to acceptance criteria** | *"and then map it with Aceetpance criteria"* |
| **R6** | Model derivation uses **static code analysis** | *"I need the to use static code analysing"* |
| **R7** | **Intake is implemented for Jira only** | *"The intake process should be implemented for jira only"* |
| **R8** | Output is **test cases for the test-management tool**, not executable code | Selected over executable-code generation |
| **R9** | **All model-source cases are supported** | *"I can see to ahve all of these cases"* |
| **R10** | The system is named **Métis**, with documentation sufficient to **build it from the ground up** | *"The new project will call Metis"* · *"...build a new system from the ground"* |
| **R11** | The model is a **state machine from the user's perspective** | *"we need model to be a machine state transion from user prespective"* |
| **R12** | Many sources, one model — **no duplicate elements** where a state or transition already exists | *"we need to ensure to not generate duplicate elements like state or transition is they are already exists"* |
| **R13** | Code changes produce **incremental model changes**, never a reset and rebuild | *"changes in code will result in incremental changes in model and not reset and rebuild on each changes"* |

### 1.1 Secondary constraints

| # | Constraint |
|---|---|
| C1 | Neo4j **Community edition only** |
| C2 | Jira accessed via a **cached export of real tickets**, not a live connection |
| C3 | **No external writes** in the first release — generate locally, publish dry-run |
| C4 | Deliver as **one proven vertical slice** before broadening |
| C5 | Analysis results **land in Neo4j** |
| C6 | The specification is **built step by step**, reviewed section by section |

### 1.2 Resolved conflict

**R4 versus the earlier "structural layers only" decision.** That deferral
excluded R4 and, consequently, R5 and much of R2. **Resolution: R4 stands.** The
structural layers become the *foundation* for extraction, not the endpoint.

| Layer | Role |
|---|---|
| 1–3 · structural | Classes, methods, call graph, endpoints, verified type registry — the substrate |
| **4 · state-transition extraction** | Recovers states, transitions, triggers and guards from code |
| **5 · AC mapping** | Links recovered transitions to acceptance criteria |

### 1.3 Requirement coverage map

| Requirement | Delivered by § |
|---|---|
| R1 | 2, 3, 4, 5 · R2 | 3, 6, 7 · R3 | 3 · R4 | 5 · R5 | 3, 5 |
| R6 | 5 · R7 | 3, 4 · R8 | 7 · R9 | 4 · R10 | all · R11 | 2 |
| R12 | 14 · R13 | 14 |

---

## 2. The structured model

### 2.1 A model is a user-perspective state machine, per surface

> A model describes a feature **as the interacting party experiences it**: states
> are situations that party can observe, transitions are interactions it performs.

**M-1.** A model is identified by one **journey** and one **surface**:
`<journey>-<surface>` — e.g. `login-ui`, `login-api`.

**M-2.** Two surfaces are supported:

| Surface | The "user" | A state is | A trigger is |
|---|---|---|---|
| **`ui`** | A person | A screen, mode or message shown — *"lockout screen displayed"* | A click, form submission, navigation |
| **`api`** | A client system | An observable response condition — *"`423 Locked` returned"* | An endpoint call |

**M-3 — the observability rule.** A state must be **distinguishable through its
own surface**, either directly (a different screen, a different status code) or
by consequence (a subsequent interaction produces a different outcome). A
condition the interacting party can neither see nor provoke a difference from is
**not a state** — it is internal detail, and modelling it produces untestable
preconditions.

**Why not the code's perspective.** An earlier draft defined a model as one state
variable's lifecycle. That is a *data* perspective. A tester can observe "I am on
the lockout screen"; they cannot observe `account.status`. A code-perspective
model generates preconditions no one can establish and outcomes no one can check.

**Evidence.** The login machine — the one model with known ground truth — already
works this way: `LoggedOut`, `Failed1`–`Failed4`, `AccountLocked`, `LoggedIn`,
`ForcedPasswordReset`, `MagicLinkSent` are user-perspective situations, not values
of any single database column.

### 2.2 Journeys group models across surfaces

**M-4.** A journey is a **grouping label**, not a machine. It groups the models of
one feature across its surfaces, using the existing array-valued
`functional_areas` property.

```
journey: login
   ├── model: login-ui    (screens, clicks)
   └── model: login-api   (endpoints, status codes)
```

**M-5 — cross-surface divergence is a finding.** Where the two surface models of
one journey disagree — a transition the API permits that the UI never exposes, or
a state reachable on one surface only — that is reported as a **finding for human
review**, never reconciled automatically. This frequently indicates a real
security or completeness gap.

#### 2.2.1 Surfaces stay separate; invocation links them

States are **not** shared between surfaces. `login-ui` and `login-api` each keep
their own states, because the observable situations genuinely differ — a screen is
not a status code.

**M-5a — two relationships, because they are two different claims.** A UI
interaction that reaches an API endpoint does **two** separable things, and one
edge conflating them made the graph read as though the flows merged:

```
UiAction  ──[:TRIGGERS]──►  ApiCall     one-to-many.  Starts that flow; the UI continues its own
UiAction  ──[:INVOKES]───►  ApiCall     one-to-one.   This UI outcome rendered that API outcome
```

The distinction is not presentational. A page *starts* a call and then carries on
with its own flow; nothing at that moment knows which outcome will occur; and **a
failing call frequently produces no UI transition at all**. `TRIGGERS` says the
call was made. `INVOKES` says a result was rendered.

A node carries `:ApiCall` or `:UiAction` **in addition to** `:Transition`, so the
surfaces are nameable in a query while the engine keeps one traversal — and
therefore one definition of what a flow is.

**M-5b — one trigger, several transitions.** A UI trigger that invokes an API
call produces **one UI transition per API outcome**. The click has no guard of its
own; its branching is determined by the API's guards.

Where the interaction and the result are separate events — a page that starts a
request and renders the answer later — the trigger carries `TRIGGERS` and each
rendered outcome carries `INVOKES`. An outcome the UI **starts and cannot
render** is M-5f's unhandled response, and is now a direct query rather than an
inference.

```
LoginForm --[click Sign In]--> Dashboard      INVOKES  LoggedOut--[POST /auth/login]-->LoggedIn
LoginForm --[click Sign In]--> ErrorShown     INVOKES  LoggedOut--[POST /auth/login]-->LoginFailed
LoginForm --[click Sign In]--> LockoutScreen  INVOKES  LoggedOut--[POST /auth/login]-->AccountLocked
```

**M-5c — inherited guards are referenced, never restated.** A UI transition may
carry two kinds of guard, recorded distinctly:

| Guard kind | Origin | Recorded as |
|---|---|---|
| **Local** | Client-side conditions evaluated before any call — field validation, enablement, permission checks in the client | A guard on the UI transition, verbatim with its own anchor (M-8) |
| **Inherited** | The guard of the API transition it invokes | A **reference** to that transition's guard, never a copy |

An inherited guard is never restated or paraphrased on the UI side, so the two
cannot drift apart. A UI transition that fails client-side validation never
reaches the API and therefore has a local guard and **no** `INVOKES` link.

**M-5d.** Purely client-side interactions — navigation, validation, display
toggles — have **no** `INVOKES` link. Their absence is meaningful, not missing data.

**M-5e — `INVOKES` is many-to-one.** The same API transition may be invoked from
several screens.

**M-5f — divergence becomes computable.** M-5's finding is now a query rather
than a judgement:

| Pattern | Finding |
|---|---|
| API transition with **no** inbound `TRIGGERS` or `INVOKES` | **API-only behaviour** — reachable by a client but never exposed through the UI. Frequently a real security or completeness gap |
| API transition **triggered** but with no inbound `INVOKES` | **Unhandled response** — the UI starts this call and can never render this result |
| UI transition whose `INVOKES` target no longer exists | The UI drives an endpoint the API model no longer has |
| API outcome with no corresponding UI transition | The UI cannot render that outcome — an unhandled response |

**M-5g.** `INVOKES` is **proposed by extraction and confirmed by a human**, like
every other cross-artefact link (F-7, X-18). Extraction proposes it by matching
the API call in the UI handler to an endpoint and response discriminator.

**Deferred: composition — the trigger fired, and this is what was done.** A Web
page that starts a request and renders the answer later *is* two machines on
separate timelines, so the condition named here was met. What changed is the
**link between them**: `TRIGGERS` and `INVOKES` now distinguish starting a flow
from observing its result, and coverage distinguishes the two accordingly (C-1).

Composition itself remains out of scope: the two machines still advance
separately and a generated path still spans one. Trigger to revisit again: a test
that must assert across both timelines in a single case.

### 2.3 What becomes a state

| Unfold into explicit states | Keep inside the guard |
|---|---|
| Bounded, enumerable, durable **and** distinguishable through the surface | Continuous or unbounded — elapsed time, amounts |
| | Evaluated fresh per interaction — credential validity |
| | Combinatorial — `A OR B` over independent conditions |

**M-6 — the unfolding rule.** Unfold when bounded, enumerable, durable **and**
observable per M-3. Otherwise keep as a guard.

**M-7 — residual guards.** When a variable is unfolded, that variable is
**removed** from the resulting transitions' guards; every remaining condition is
preserved verbatim.

```
Before:  LoggedOut --[!valid && attempts < 5]--> LoggedOut
         LoggedOut --[!valid && attempts >= 5]--> Locked

After unfolding `attempts`:
         Failed1 --[!valid]--> Failed2       residual guard, verbatim
         Failed4 --[!valid]--> Locked
         Failed2 --[valid && !locked]--> LoggedIn   ← recovery path, previously hidden
```

The pre-unfolding model cannot express *"what happens on a valid login after two
prior failures?"* Unfolding makes four separately testable recovery paths visible.
This is what *"on very detail level"* is aimed at.

### 2.4 What a guard is

| Rule | Statement |
|---|---|
| **M-8** | Preserved **verbatim** from source, with file and line recorded |
| **M-9** | A **test data requirement**, not a solved value |
| **M-10** | Unparseable ⇒ marked **unverifiable**; never dropped, never assumed true |
| **M-11** | A property of a transition, never a separate entity |

### 2.4a Guard dimensions and precedence — the combinatorial bound

A single endpoint varies along several axes: authentication, authorization,
header validity, payload validity, each field. Treating them as independent gives
a product — `3 auth × 2 authz × 10 payload = 60` per endpoint, ~1,500 for a
25-endpoint service. Almost all of it worthless.

**They are not independent. They are a short-circuit chain.**

**GD-1 — a guard is composed of ordered dimensions.** A dimension is one
independent axis of variation. Dimensions carry a **precedence order**: the order
in which the system actually evaluates them.

**GD-2 — a rejection transition's guard is prefix-determined.** For a transition
representing failure at dimension *k*:

```
guard(k) = (dimensions 1 … k−1 all pass) ∧ (dimension k fails)
```

**GD-3 — downstream dimensions are out of scope.** Dimensions *k+1 … n* are
**unconstrained** for that transition. Varying them produces no observable
difference, because evaluation never reaches them.

```
                 guard                                       variable axis
401   !authenticated                                         auth only
403   authenticated ∧ !authorized                            authz only
400   authenticated ∧ authorized ∧ !payload_valid            payload only
200   authenticated ∧ authorized ∧ payload_valid             the success path

1 + 1 + 10 + 1 = 13 tests, not 60
```

**GD-4 — determinism comes free.** Precedence-ordered guards are mutually
exclusive by construction, so M-17's determinism check is satisfied structurally
rather than by luck. Guard completeness reduces to *"does the chain terminate in a
success case?"*

**GD-5 — dimension classes are configuration.** Each dimension is classified —
`authentication`, `authorization`, `validation`, `business` — by configuration
matched against the recovered check. Classification is config; **order is a code
fact** (§5.4a).

**GD-6 — cross-cutting transitions are marked.** A transition whose failing
dimension is classified cross-cutting (typically `authentication`,
`authorization`) carries `cross_cutting: <class>`. It still lives in its own
model — every model is self-contained — but review and coverage may treat the
class as one thing rather than twenty-five.

**GD-7 — equivalence by code anchor.** Cross-cutting transitions across different
models that resolve to the **identical code anchor** (M-14: same file, line and
commit) form an **equivalence class**. They are the same behaviour reached from
different endpoints.

**GD-8 — class credit is anchor-gated, and only for cross-cutting classes.**
Covering one member of an equivalence class credits the class. Where anchors
**differ**, the transitions are distinct behaviour and are covered separately.

This is what stops twenty-five identical 401 transitions becoming twenty-five
reviews and twenty-five tests — while still catching the case where one endpoint's
auth check genuinely differs from the rest, which is exactly where a real
vulnerability hides.

**GD-9 — fail-closed on unknown order.** If the precedence order cannot be
recovered, dimensions are **not** assumed independent and are **not** assumed
ordered. The transition is flagged `precedence_unresolved`, and guard coverage for
it falls back to the full product with the explosion reported. Guessing an order
would silently drop real combinations.

### 2.5 Identity, provenance and change

| Rule | Statement |
|---|---|
| **M-12** | Stable identity — `<journey>-<surface>` |
| **M-13** | Every transition records the **source that produced it** |
| **M-14** | Every code-derived element records the **exact commit**, file and line |
| **M-15** | **Versioned, not overwritten** — re-extraction supersedes; both remain reconstructable |
| **M-16** | Divergence between sources for one model ⇒ **contradiction held for human resolution** |

### 2.6 Well-formedness

| Property | Failure means |
|---|---|
| **Determinism** | Ambiguous — one interaction matches two transitions |
| **Guard completeness** | An interaction matches **no** transition — silent, no error anywhere |
| **Reachability** | Dead state, or a missing transition |
| **AC coverage** | Behaviour nothing validates is an unverified claim |

**M-17.** Fail-closed — unparseable guards are reported unverifiable, never
assumed correct. **M-18.** Validation failure **blocks** generation.

### 2.7 Consequence for code extraction — specified in §5

| Model element | Recovered from |
|---|---|
| **Trigger** | Entry points — endpoint annotations, routes, handler methods |
| **Guard** | Conditions control-dominating the outcome |
| **Target state** | The **observable outcome** — status, redirect, rendered view, error code |
| **Source state** | Preconditions asserted, or fixpoint over the transition relation |

Recovering an *outcome-shaped* target state is a more involved analysis than
tracking one enum. Stated here so it is a known cost entering §5.

---

## 3. End-to-end flow

### 3.1 Three doors, one pipeline

All entry points resolve to the same thing — **a scope**: a set of models, a set
of transitions of interest within them, and a coverage criterion.

```
  ticket  ──┐
  model   ──┼──►  resolve scope  ──►  ensure models  ──►  validate
  change  ──┘                                                 │
                                                              ▼
        publish  ◄──  render  ◄──  generate paths  ◄──  reconcile (R5)
```

**F-1 — scope resolution.**

| Door | Input | Resolves to |
|---|---|---|
| **Ticket** | A Jira key | The ticket's ACs → the transitions they validate → the models containing them |
| **Model** | `<journey>-<surface>` | That model; all its transitions are of interest |
| **Change** | A commit or range | Transitions that differ from the prior model version → their models |

**F-2 — transitions of interest versus traversal.** The criterion applies to the
transitions *of interest*; generated paths may traverse others to reach them. A
path is never rejected for covering more than was asked.

**F-3.** Every run records its scope, criterion, model versions and source commit,
so any result is reproducible and any two runs are comparable.

### 3.2 Stages

| # | Stage | Input | Output | Blocks on |
|---|---|---|---|---|
| 1 | **Resolve scope** | Entry-point argument | Models + transitions of interest + criterion | Unresolvable scope |
| 2 | **Ensure models** | Scope | Models present and current for the named commit | No model exists and none can be derived |
| 3 | **Validate** | Models | Well-formedness findings | **Any failure (M-18)** |
| 4 | **Reconcile (R5)** | Models + ACs in scope | Matched pairs + two gap reports | Never blocks — findings are output |
| 5 | **Generate paths** | Validated models + criterion | Covering path set | Budget exceeded (reports, does not truncate silently) |
| 6 | **Render** | Paths | Draft test cases | A step that cannot be traced to a real transition |
| 7 | **Publish** | Drafts | Dry-run payload / created cases | **Absence of literal confirmation** |

### 3.3 Reconciliation runs in both directions (R5)

**F-4.** Stage 4 produces three outputs, not one:

| Output | Meaning |
|---|---|
| **Matched pairs** | `AcceptanceCriterion ↔ Transition` — the coverage basis |
| **Transitions with no AC** | **Unspecified behaviour** — the system does something no one wrote a criterion for |
| **ACs with no transition** | **Unimplemented or unmodelled** — a stated requirement with no corresponding behaviour |

**F-5.** The two gap types are **not symmetric and are never merged into one
number.** The first is a specification gap; the second is an implementation or
modelling gap. They go to different people.

**F-6.** Reconciliation runs **before** model approval, so its findings are
available as evidence to the reviewer deciding whether to approve.

**F-7.** A match is **proposed, never asserted.** Matching is a judgement, so a
proposed `VALIDATES` link is held for human confirmation. Name or wording
similarity alone never establishes a match.

### 3.4 Human gates

Two, and only two.

| Gate | Where | Rule |
|---|---|---|
| **G1 — model approval** | Between stages 4 and 5 | A model must be approved before anything is generated from it. Validation findings and reconciliation gaps are shown as evidence |
| **G2 — publication** | Stage 7 | No external write without a **literal affirmative confirmation** in that run. No timeout-implies-yes, no default-yes. One decision covers a batch |

**F-8.** Nothing is auto-approved and nothing auto-promotes on elapsed time. An
unreviewed model stays unapproved indefinitely — the safe failure is "no tests
generated", never "tests generated from an unreviewed model".

### 3.5 Failure behaviour

**F-9.** Fail-fast. A stage that fails **stops and reports**: what failed, why,
and the explicit action required. No recovery attempt, no auto-repair, no
alternative path, no substitute artefact.

**F-10.** A partial result is never presented as a complete one. If a budget or
limit is hit, the truncation is reported explicitly with what was omitted.

### 3.6 Where the three systems sit (R3)

| Layer | System | Stages |
|---|---|---|
| **Acquire** | **Athena** | Feeds stage 2 — Jira tickets and ACs, source at a named commit, test-management state |
| **Structure** | **Métis** | Stages 1–5 — models, validation, reconciliation, path generation |
| **Consume** | **Atlas** | Stages 6–7 — rendering and publishing |

**F-11 — Contract 1.** Métis reads Athena's already-landed data. It never
re-fetches from an original source.
**F-12 — Contract 2.** The graph is the interface to consumers. They query it;
they never re-derive.

### 3.7 Committed by this section

- Three entry points resolving to one scope abstraction (F-1, F-2)
- Seven stages with explicit blocking conditions (§3.2)
- Two-direction reconciliation producing two distinct, non-merged gap types (F-4, F-5)
- Matches proposed, never asserted (F-7)
- Exactly two human gates (§3.4)
- Fail-fast with no recovery (F-9, F-10)
- The three-system layer mapping and its two contracts (§3.6)

### 3.8 Deferred to later sections

| Question | Section |
|---|---|
| How matching in stage 4 actually works | 5 |
| Criteria and path-generation algorithm | 6 |
| Draft format and publication mechanics | 7 |

---

## 4. Model sources

### 4.1 Why this section is load-bearing — the circularity problem

**A model extracted from code, used to generate tests, produces tests that verify
the code does what the code does.** That is circular. It cannot find a defect in
the logic itself.

Code-derived models earn their value three other ways:

| Value | Mechanism |
|---|---|
| **Exhaustive coverage** | Every path is covered, including those a human would not think to write |
| **Regression detection** | A model diff between commits exposes unintended behaviour change |
| **Divergence from intent** | Comparing code-derived behaviour against acceptance criteria — **this is where real defects surface** |

The third is R5, and it is why R5 is load-bearing rather than decorative. *The
code locks after 3 attempts; the acceptance criterion says 5* is a defect that no
amount of testing the code against itself will ever reveal.

**S-1.** Métis MUST NOT present code-derived tests as evidence that behaviour is
*correct*. They are evidence that behaviour is *covered*. Correctness comes from
reconciliation against intent.

### 4.2 The three sources

**S-2.** Three sources, one interface. Each produces **candidate** model elements;
none writes an approved model directly.

| Source | Derives a model from | Represents | Section |
|---|---|---|---|
| **Code-extracted** | Static analysis of source at a named commit | **What the system does** | §5 |
| **AC-mined** | Acceptance-criteria prose from Jira | **What was specified** | §4.5 |
| **Human-authored** | A guided modelling session | **What is intended** | §4.6 |

**S-3.** The two-model comparison that makes §4.1's third value real requires at
least one *intent* source (AC-mined or authored) alongside the code source.
**A deployment running only code extraction gets coverage, not correctness** —
and Métis must say so rather than let the omission pass unnoticed.

### 4.3 Layered architecture — how sources combine

This resolves the contradiction between M-13 (*every transition records its
source*) and M-16 (*divergence between sources is a contradiction*). Both hold,
at different layers.

```
  code-extracted ──┐
  AC-mined       ──┼──► candidate elements  ──► reconcile ──► approved model
  human-authored ──┘    (lifecycle: Quarantine)      │        (per-element
                                                     │         provenance)
                                              divergences
                                                     ▼
                                          Disputed (blocks paths)
```

**S-4.** Each source produces candidate `State` and `Transition` elements at
`Quarantine`. No source writes at `Approved`.

**S-5.** Reconciliation compares candidates for the same `<journey>-<surface>`:

| Outcome | Result |
|---|---|
| Sources **agree** on an element | Eligible for approval |
| Only one source **proposes** an element | Eligible for approval, flagged single-source |
| Sources **disagree** on an element | Marked **`Disputed`** |

**S-6.** Approval promotes elements from `Quarantine` to `Approved`. Elements are
**promoted in place, never copied** — one set of nodes per model, carrying
`lifecycle_state` and `source`.

**S-7 — per-element provenance.** Every approved element records which source
produced it, who approved it, and — where applicable — which divergence it
resolved. A human may accept a code-derived transition while renaming its states;
both facts are recorded on the same element.

### 4.4 Divergence blocks generation, precisely

**S-8.** A `Disputed` element **blocks path generation for any path traversing
it** — not the whole model. Paths avoiding the disputed element still generate.

This matters: one contested transition in a twenty-transition model should not
stall the other nineteen.

**S-9.** A divergence is **the primary finding**, not an obstacle to route around.
It is surfaced with both sides stated:

```
DIVERGENCE  login-api / transition "lockout"
  code-extracted : guard  attempts >= 3      (AuthController.java:88, commit a3f21c)
  AC-mined       : guard  attempts >= 5      (PROJ-1421, AC-2)
  paths through this transition: BLOCKED pending resolution
```

**S-10.** Neither source automatically wins. There is no precedence rule, because
a precedence rule would silently decide which of a defect and a stale requirement
is correct — the exact judgement a human must make.

**S-11.** Resolution is recorded: which side was accepted, by whom, and why. A
resolution is itself evidence, and it survives re-extraction.

### 4.5 AC-mined models

**S-12.** Derives candidate states and transitions from acceptance-criteria prose,
via staged extraction with **deterministic verification** of every proposal.

**S-13.** A proposal that cannot be grounded in the source text is **blocked, not
written** — however well-formed it appears. Fluent well-formedness is what a
fabrication looks like.

**S-14.** AC-mined elements record the exact acceptance criterion and text span
they derive from.

**S-20 — an acceptance criterion is atomic: one condition, one action, one
validation.** A criterion carrying three conditions is three criteria wearing one
id, and a reviewer can only accept or reject the bundle. Enforced in two places,
at two strengths, and the difference is deliberate:

| Where | Strength | Why |
|---|---|---|
| `model_sources.knowledge` — a person writing criteria | **Blocking** | A compound criterion is a correctable input. Letting it through mines several behaviours into one transition, and no later stage can take them apart again |
| `mbt.validation.check_ac_atomicity` — a guard recovered from code | **Advisory** | The transition is well-formed; only the shape of the criterion it can carry is imperfect. Blocking generation over the wording of a document would stop tests for behaviour that is entirely sound |

**S-20a — §2.4a's equivalence classes are a coverage economy, not a criteria
economy.** GD-6 to GD-8 stop twenty-five identical 401 transitions becoming
twenty-five reviews and twenty-five tests. They say nothing about how many
criteria a specification carries: coverage may credit a class, and the criteria
stay one per behaviour. Conflating the two loses requirements, not tests.

**S-20b — a compound guard decomposes rather than splitting.** GD-2 already gives
the reading: a rejection guard is `(dimensions 1..k-1 pass) AND (dimension k
fails)`, so the prefix is the **context the interaction happens in** and only the
last dimension is the **condition under test**. The prefix renders into the Given;
the deciding condition is the criterion's condition. Emitting one criterion per
conjunct instead would be false — from `authenticated AND NOT authorized -> 403`,
*"when a request is made, and authenticated, then 403"* claims something the
system does not do.

A guard containing an `OR` is the case that does not decompose. Deciding which
branch decides needs real boolean reasoning, M-17 forbids guessing, and it is
therefore reported as non-atomic rather than split on an assumption.

**Honest limitation.** Acceptance criteria rarely describe a complete state
machine. AC-mined models are typically **partial** — a few transitions, not a
closed machine. They are valuable as the *intent* side of a comparison, and are
usually insufficient alone as a generation source. §2.6's well-formedness checks
will report them incomplete, correctly.

### 5.2a Web structure, and 5.2b data structure — authored (D-14)

**S-34 — the Web structure layer is the UI counterpart of the API evidence
layer.** `Endpoint`/`Parameter`/`Field` are what a call is made of; `Page`,
`Menu`, `UiTable`, `Form`, `Dialog`, `Row`, `Pagination`, `Sort`, `Action`,
`Event` and `Navigation` are what an interaction is made of. A `UiAction`
transition points at an `Action` with `DERIVED_FROM`, exactly as an `ApiCall`
points at its `Endpoint`. One relationship — `HAS_ELEMENT` — spans the tree, so
*"every control on this page, at any depth"* is one query.

**S-35 — both layers are authored, and that is a real writer.** No pack
identifies component types: `react-ui` recovers screens, routes and status
variables; `js-ui` recovers `addEventListener` bindings whose element selector
its own comment calls "frequently NOT recoverable"; neither distinguishes a
library `<DataGrid>` from a hand-rolled `<div role="table">`. A person knows, and
says so in a checked-in file reviewed like any other change. An extractor that
can later fill part of it in writes the same labels through the same planner.

**S-36 — containment rules live in the catalogue, not in the validator.** A `Row`
belongs to a `UiTable` and not to a `Menu`; the file checker asks
`is_allowed(...)` rather than restating the rule, so the two cannot drift.

**S-37 — `Table` is the database table.** The UI one is `UiTable`. `Table`
unqualified means the stored relation, as it did in this repository's earlier
ontology and as it does in most of engineering, and `MATCH (t:Table)` returning
page controls would be a trap.

**S-38 — an unclassified object stays a worklist.** `UiElement` and `DbObject`
are bases whose specialisations replace them, so an element or object whose kind
nobody established is findable rather than absent — the same argument `Transition`
makes. This is what makes *"and other database elements like function, view, …"*
expressible without a label per object type.

**S-39 — `Datasource` is not `Database`.** Several datasources commonly address
one database, and `dialect` is required: which SQL a connection speaks decides
what a test can issue through it, and a connection string does not disclose it.

**S-40 — the count is a warning.** D-1 rejected a ~45-label ontology; this is
45 again. Every label added since carries a named writer and a named reader,
which the original thirty-three did not — but the next addition should be staged
unless both halves are real today.

### 4.5a OpenAPI as a source — the component level (X-2, GD-2)

**S-29 — a published contract is a fourth model source, with its own extraction
method.** An OpenAPI document flows through the same `contract.ExtractionReport`
a code pack emits, so synthesis needs no change — but `declared_contract` is not
`static_analysis`. A code model records what the system *does*; this records what
its contract *declares*. Where they differ, that difference is the finding (§4.1),
and it is invisible if both arrive wearing one provenance.

**S-30 — the component level is generated, never authored.** Every endpoint,
parameter, constraint and declared response is in the document already. Writing
criteria for them by hand invites drift against the contract, and S-19's
`code_derived` grade already describes what such a criterion is worth.

**S-31 — the system level is not in the document and never will be.** A contract
says *which* statuses occur; it does not say under what preconditions. The
knowledge file (§4.6a) supplies those. The split is not a limitation to work
around — it is the honest boundary between two different kinds of knowledge.

**S-32 — guards are derived only where the document grounds them.** GD-2's chain
is recoverable for the dimensions OpenAPI actually declares:

| Declared in the document | Dimension | Guard for its rejection |
|---|---|---|
| `security` on the operation | authentication | `NOT authenticated` |
| scopes or roles on that requirement | authorization | `authenticated AND NOT authorized` |
| a `requestBody` schema | validation | `authenticated AND NOT payload_valid` |

A status the document declares and does not condition — a 404, a 409 — is left
**unguarded and reported**. `check_guard_completeness` surfacing it is the tool
working; inventing `record_exists` is what S-13 forbids. In practice this is
exactly where a system-level criterion is needed, so the gap is also the
worklist.

**S-33 — `in: cookie` blocks only when it would make every request wrong.** The
contract's locations are named after the HTTP position and a cookie is never
folded into `header`. A *required* cookie is a parse error and X-5 refuses the
report: every generated request would omit a value the server demands. An
optional one is a note. Both are reported; only one stops the run.

### 4.6a The business glossary — what the nouns mean (D-13)

A criterion says *"when they archive a record"*. Two questions follow and neither
had an answer: what is a record, and what does archiving one change.

**S-21 — business nouns are defined, at two levels.** A `BusinessArea` groups; a
`BusinessEntity` carries its properties and the **impact** of acting on it.
Impact is the half a schema cannot supply and the half an author actually needs:
*archiving is reversible for 30 days, then permanent*.

**S-22 — the glossary is not the evidence layer.** `Class` and `Field` record
what the code declares; a `BusinessEntity` records what the business means. They
disagree regularly, and that disagreement is a finding (§4.1). One label for both
would hide it.

**S-23 — nouns are matched into criteria by whole-word name, never by
similarity.** X-17's rule, applied here: an entity the glossary does not define
is not tagged, and the omission is visible rather than approximated.

### 4.6b The specification as Gherkin (§18)

**S-24 — one Requirement is one Feature; one AcceptanceCriterion is one
Scenario.** Cucumber's own convention, and expressible only because a criterion
now has a requirement above it (`HAS_AC`).

**S-25 — every traceability fact rides in a tag, not a comment**, because a tag
survives the round trip. `@inferred` and `@complement_of:` are load-bearing:
without them a derived criterion returns ungrounded and is correctly refused
(S-13).

**S-26 — a `.feature` is a source, not only an output.** It reads back into the
same criteria, byte-identically on a second render. The author's own words are
preserved: the clauses are *sliced* from the original sentence, never rebuilt
from the mining parser's normalised groups, which strip `the` and `they` for
reasons that belong to state naming and not to prose.

**S-27 — the parsed subset is stated, and anything outside it is refused.**
`Scenario Outline`, `Examples`, `Background` and `Rule` are real Gherkin and are
not read. Reading such a file anyway would drop its rows and report a clean
parse.

**S-28 — it is not executable.** R8 stands: Métis emits test cases, not test
code. A `.feature` with no step definitions is a specification that happens to be
machine-readable, and presenting it as a suite would claim a capability that does
not exist.

### 4.6 Human-authored models

**S-15.** A guided modelling session produces states, transitions, triggers and
guards, with acceptance criteria and — where available — code-extracted
candidates shown as context.

**S-16.** Human-authored elements carry no code anchor and are exempt from
`M-14`'s commit requirement, but still require the author's identity and the
session's date.

### 4.7 When no model exists

**S-17.** Stage 2 (*ensure models*) checks for an `Approved` model for the scope.
If none exists it **reports which sources are available and stops.** It does not
silently auto-derive.

```
No approved model for login-api.
  Available: code extraction (repo auth-svc @ HEAD)
             AC mining      (PROJ-1421, 6 acceptance criteria)
  Run one of these to produce candidates, then review.
```

**S-18.** Deriving candidates is always an explicit action. This follows F-9's
fail-fast discipline: the system reports what it can do and waits, rather than
choosing a source on the user's behalf.

### 4.8 Two ways a model meets acceptance criteria — both used

R5 is satisfied by two complementary mechanisms, and they should not be confused.

| Mechanism | Where | What it compares |
|---|---|---|
| **Matching** (§3.3) | Stage 4, per transition | An existing transition against AC *text* — produces `VALIDATES` links and the two gap reports |
| **Comparison** (§4.4) | Reconciliation, per model | A code-derived *machine* against an AC-mined *machine* — produces divergences |

Matching answers *"is this behaviour specified?"* Comparison answers *"does the
specification agree with the implementation?"* Both are needed; neither
substitutes for the other.

### 4.9 Committed by this section

- The circularity limit stated explicitly, and what actually breaks it (§4.1, S-1)
- Three sources, all producing candidates only (S-2, S-4)
- Layered architecture resolving M-13 / M-16 (§4.3)
- Promotion in place with per-element provenance (S-6, S-7)
- Divergence blocks only traversing paths (S-8)
- No automatic precedence between sources (S-10)
- Grounding required for mined proposals (S-13)
- Criteria are atomic; equivalence classes economise tests, never requirements (S-20)
- No silent auto-derivation when a model is missing (S-17, S-18)
- Matching and comparison as distinct R5 mechanisms (§4.8)

### 4.10 Deferred to later sections

| Question | Section |
|---|---|
| Graph representation of candidates, versions and divergences | 8 |
| The review interface for approving and resolving | 9 |

---

## 5. Code-derived state-transition extraction (R4 · R5 · R6)

**Scope note.** Both surfaces are extracted in the first slice, per decision.
This is broader than C4's one-slice discipline would suggest; the cost is two
extraction pipelines before either is proven, and it is accepted deliberately so
that M-5 cross-surface divergence is available from the start.

### 5.1 Engine

**X-1.** Extraction uses a **code property graph** — a unified representation of
syntax, control flow, control dependence and data dependence over the source.

**X-1 (a) — the two steps, and where each artefact lives.** Extraction is a
build followed by a query, and the CPG is **never stored in the Métis graph**:

```
joern-parse <src> --output cpg.bin --language <frontend>          # build, per (repo, commit)
joern --script <pack>/query.sc --param cpgPath=cpg.bin \
      --param commit=<sha> --param repo=<name> --param out=<report.json>
```

`cpg.bin` is an artefact keyed by `(repo, commit_sha)` and kept outside the
graph. Frontends in use: `javasrc2cpg` (JVM) and `jssrc2cpg` (JS/TS). Métis reads
the **report**, not the CPG — `model_sources.CodeExtractedSource` takes a pack's
validated JSON, so the engine is a build dependency of extraction rather than a
runtime dependency of Métis.

**X-1a — the engine is Joern.** Pinned, with the rationale recorded so it is not
re-litigated:

| Constraint | Why it is binding |
|---|---|
| **Apache-2.0 on private code** | The estate is closed-source. A licence permitting only open-source analysis is disqualifying, not inconvenient |
| **Control dependence** | Without CDG, guards cannot be recovered. This alone eliminates structure-only tools |
| **Multi-language** | Java first (RD-1 of §1), but the estate is not Java-only |
| **Java frontend maturity** | `javasrc2cpg` and `jimple2cpg` are its two most mature frontends — the most favourable case for the first target (§15.1) |

**Evaluated and rejected**, recorded so the evaluation is not repeated:

| Tool | Rejected on |
|---|---|
| CodeQL | **Licence** — free only for OSI-licensed open source, research, or GitHub-hosted OSS. Also no graph export |
| Semgrep CE | Interprocedural and cross-file analysis are paid; CE has no CDG and no graph export |
| jQAssistant | **No control dependence** — cannot recover a guard, whatever else it offers |
| SootUp / WALA | Highest precision, but a framework rather than a query tool, and single-language. Held as the escalation if extraction quality proves insufficient |

R11's shift to a user-perspective model changed the extraction *target* after the
engine was chosen, so the choice is re-confirmed against the new target:

| Model element needed | CPG facility |
|---|---|
| Trigger — entry points | Annotations, routes, handler methods |
| Guard — conditions permitting an outcome | **Control dependence** (the reason a plain AST is insufficient) |
| Target state — observable outcome | Return/response construction reachable from the handler |
| Source state — preconditions | Reads compared against literals, dominating the outcome |

All four are recoverable. Control dependence is the non-negotiable capability;
any engine lacking it cannot recover guards and is disqualified regardless of
other merits.

**X-2.** The engine runs as a **sidecar**. Its graph is never merged into the
Métis graph — it is queried, and only ontology-shaped results are landed.

**X-3.** The engine version and query set are **pinned and versioned together**.
An engine upgrade is a reviewed change with a full re-run of extraction tests.

### 5.2 What is extracted, per surface

| | **`api` surface** | **`ui` surface** |
|---|---|---|
| **Trigger** | Endpoint annotation / route → handler method | Event handler, form submit, route definition |
| **Target state** | Response construction: status code + error discriminator + body shape | View resolution / navigation target / displayed message |
| **Guard** | Conditions control-dominating the response | Conditions control-dominating the outcome |
| **Source state** | Session/entity reads compared against literals | Same, plus current route |

**X-4.** UI extraction is **framework-dependent**. Supported frameworks are
declared in configuration. An unrecognised framework is **reported, never
guessed** — a fabricated UI model is worse than none, because it looks
authoritative.

### 5.3 The extraction pipeline

Seven steps. Each is independently testable.

| # | Step | Produces |
|---|---|---|
| 1 | **Identify entry points** | Candidate triggers |
| 2 | **Identify observable outcomes** | Candidate target states, as raw signatures |
| 3 | **Recover guards** | The conjunction of conditions dominating each outcome, verbatim with file and line |
| 4 | **Recover source states** | Preconditions asserted, or fixpoint over the transition relation |
| 5 | **Unfold** | Explicit states per M-6, with residual guards per M-7 |
| 6 | **Name states** | Resolved names via the cascade (§5.4) |
| 7 | **Emit candidates** | `State` / `Transition` elements at `Quarantine` |

**X-7a — Métis never executes anything against the System Under Test.** It reads
from intake sources and it writes to its own graph. It does not call the API it
models, drive the UI it models, or run a query against the database it models —
not to extract, not to verify, and not to check the outcome of a test it
generated. A generated test case is for a person or a pipeline to run; running it
is not Métis's act.

The distinction that does the work: **a database Métis reads is an intake source;
the same database reached to check a test's outcome is the System Under Test.**
Same server, different act, and only the first is available.

This is structural rather than remembered. `connectors/intakes.json` declares
every intake with an `access` mode, and **there is no mode meaning "runs
something"** — the four are `local_files`, `read_only_connection`,
`authored_file` and `uif_document`. `executes_against_sut` is a schema `const`
of `false`, and `metis_mcp.intakes.load` refuses a declaration that says
otherwise. Adding a mode that executes is the change that would have to be argued
for, which is the point.

Publication (§18) is the deliberate exception and is gated separately: writing a
test case into a test-management tool is an external write behind G2 and
`METIS_ALLOW_EXTERNAL_WRITES`, and it still touches no System Under Test.

**X-5.** A partially-parsed source tree **fails the run.** No partial extraction
report is emitted. A partially parsed repository silently under-reports, and
under-reporting is indistinguishable from clean code.

**X-5a — intake noise is filtered on provable inertness, never on visibility or
reachability, and the reduction is reported.** Extraction may drop elements that
cannot carry behaviour, because a graph in which the entry points are outnumbered
nine to one by accessors is harder to review, and a reviewer who stops reading is
a gate that does not function. What it may drop is narrow, and the two obvious
axes are both wrong:

- **Not visibility.** A private method can be the guard on an entry point and can
  raise the exception its own `@ExceptionHandler` maps. Measured on a
  twelve-endpoint service: `private` was 59 of 389 methods, two of them reachable
  from a handler, and one of those two guarded an endpoint and raised the cause of
  a 400 — so the filter would have deleted a rejection path while leaving all 166
  accessors in place. For **fields** the axis is worse than wrong, it is
  inverted: a DTO's fields are private, and they are where `@Schema`
  descriptions, required-ness and validation bounds live — the inputs test design
  is derived from.
- **Not call-reachability from an entry point.** On the same service only 46 of
  389 methods were reachable, but that is largely the frontend not resolving
  interface dispatch: dropping the remainder would have deleted a service
  implementation's 31 business methods, where the guards and the throws are.

An element may be dropped only when its inertness is **structural and joint** —
for an accessor, that means a matching field exists, the body is short, and it
contains no control structure and no call other than operators. Any one of those
alone is insufficient: a getter that branches is behaviour whatever it is named.

Filtering is a **fact about a codebase, so a project declares it** (`drop_noise`),
and the count dropped with its reason is emitted in the report either way. This is
X-5 one level down: a reduction nobody can see is indistinguishable from a
repository that never contained those elements.

**X-6.** Every extracted element records the exact commit, file and line
(M-14). An element without a code anchor is not emitted.

**X-6d — a fact earns its place by what the model can reach, and a user-facing
fact the model cannot account for is a finding rather than a node.** "Has an
edge" is the wrong test: a method fifteen `CALLS` deep has plenty and tells the
model nothing, while an `ExceptionMapping` producing a 400 a caller sees had
none. Every fact is classified against the model:

| | |
|---|---|
| `surface` | what a caller sends, receives, or is answered with. `Endpoint`, `Parameter`, `DeclaredOutcome` and `ExceptionMapping` **by their label**; `Class`, `Enum` and `Field` when a payload chain reaches them |
| `supporting` | named by a declared reader, bounded to what that reader needs |
| `internal` | neither — **not landed**, counted by label and reported (X-5a) |

`surface` is decided by the label's meaning as well as by traversal, and that is
not a shortcut: traversal alone is circular for exactly the nodes that matter,
because an unreferenced `ExceptionMapping` is unreachable *by definition* and a
purely structural test files it under `internal`, which is the noise it is
supposed to be distinguished from.

A `surface` fact no path of meaningful edges reaches from the model is a **gap**,
reported where a person will see it. It is not always a defect: a
`@ControllerAdvice` bean applies to every controller and nothing says which
endpoints can reach its throw, so no rejection is attributed to it and the
mapping is correctly left unreached. The graph's report and synthesis's own
finding must then agree on the count — two representations of one fact that can
disagree is where this system's real defects come from.

Reachability is judged over **meaningful** edges only: the behaviour-to-evidence
and payload chains. `CALLS` and `DECLARES_METHOD` are excluded, because on a real
service they took apparent reachability from 324 nodes to 546 while telling the
model nothing, which would have made the invariant unfalsifiable.

**X-6b — a payload is a graph, not a type name, and its validation is data, not
prose.** The request and response of an entry point must be reachable as a
structure a test case can be constructed from:

    Endpoint -ACCEPTS-> Parameter -OF_TYPE-> Class -HAS_FIELD-> Field -OF_TYPE-> Class …

followed as far as the declared types go, stopping on a type already on the path
and on any type the repository does not declare (REQ-CGA-010 — no stub for a JDK
type). Without that last edge a field whose type is another payload is a dead
end, and the payload a case has to build is only ever one level deep.

**Validation lands as typed properties on the element it constrains, not as the
annotation text.** `constraints: ["@Size(max = 40)"]` is a string every consumer
must re-parse, and two consumers parsing it slightly differently is a defect
nobody can see; `expected_max_length: 40` is a bound a boundary criterion reads
directly. The vocabulary Métis honours is closed, for the same reason the
ontology is, and an annotation outside it **stays in `constraints` and becomes no
property** — visible as unhandled rather than silently dropped (X-5a).

An `Enum` is the one type whose value space is fully known from source: its
constants are the equivalence partitions of every field of that type, so such a
field carries them as `allowed_values` and needs no boundary analysis at all.


**X-6a — a declared rejection is a user path; a declared success is a recovery
gap.** An outcome may be *constructed* (the code was seen building it) or only
*declared* (an annotation says it exists). Both become transitions where they are
**rejections**, because §2.1's model is every path a user can take and "I send a
request that is rejected" is one of them whether or not the handler builds the
response itself — most often it does not, delegating to a framework exception
handler the analysis unit cannot see. A declared **2xx** with no construction is
the opposite case: the pack failed to find a success that exists, so modelling it
would assert a conditional behaviour where there is an unconditional one. Every
transition records `outcome_source`, because an `@ApiResponse` can simply be
wrong and a reviewer must see which kind of claim they are approving.

**X-6b — the precondition claims only what was traced.** A rejection's guard is
GD-2's prefix over the recovered dimension chain. Where the bean-validation chain
closes — a validation annotation on the bound parameter, a constrained type, and
an exception mapping from that framework exception to this status — the
precondition names payload validity and carries every anchor behind it. Where any
link is missing the precondition states only what the annotation states: that the
request can be rejected. **It never names a cause it did not trace.** A framework
typically maps several distinct exceptions onto one status, so a guessed cause is
wrong rather than vague, and a fixture built from it establishes the wrong
precondition and never reaches the path. The weaker form is not a lesser element:
it is a real path whose setup an acceptance criterion or a person can sharpen
later (§4.3), and reconciliation attaches that to the same transition.

**X-6c.** Where two framework handlers map one exception to **different** statuses
and neither declares a precedence, the exception is excluded from the map and
reported. Agreement across handlers is not a conflict — the status is certain even
where the response body is not (GD-9).

### 5.4 State naming — an ordered cascade

**X-7.** A state's name is resolved by the first tier that yields one:

| Tier | Source of the name | Condition |
|---|---|---|
| **1** | The **AC-mined model's** state vocabulary | An evidence-based semantic alignment exists |
| **2** | A **naming convention in code** | An enum constant, annotation value, or error discriminator that reads as a name |
| **3** | **A human**, during review | Always available as the backstop |

**X-8.** Every name records **which tier produced it**. A name is not a neutral
label — its provenance determines how much weight it carries.

**X-9.** Tier 1 alignment must be **evidence-based** — matching on the observable
signature, not on string similarity between an AC's wording and a raw outcome.
A low-confidence alignment **falls through to tier 2**; it is never forced.

**X-10.** A placeholder name never persists. If no tier resolves a name, the model
remains incomplete and cannot be approved.

### 5.4a Recovering guard dimensions and precedence

**X-10a — order is a code fact.** The precedence chain (GD-1) is recovered from
the actual evaluation order: filter or middleware chain position, then
method-level annotations, then in-body checks in control-flow order.

**X-10b — classification is configuration.** Each recovered check is matched
against declared dimension classes, per framework:

```yaml
dimension_classes:
  - class: authentication
    cross_cutting: true
    matches: [ security filter chain, pre-authentication annotations ]
  - class: authorization
    cross_cutting: true
    matches: [ method-level authorisation annotations, role predicates ]
  - class: validation
    cross_cutting: false
    matches: [ bean-validation annotations, explicit field checks ]
```

**X-10c.** An unclassified check keeps its recovered **position** but no class. It
still participates in the precedence chain — the scope rule (GD-3) works on order
alone — it simply cannot be marked cross-cutting.

**X-10d — never infer order from source line position.** Evaluation order is
determined by the framework's chain and by control flow, not by where a check
happens to appear in a file. Where the two disagree, control flow governs; where
control flow cannot resolve it, GD-9's fail-closed rule applies.

### 5.5 The naming trap — naming is not agreement

**X-11.** Naming a code-extracted state using the AC-mined vocabulary (tier 1)
**MUST NOT** be treated as evidence that the two models agree.

This is a real circularity risk and it would silently destroy §4.4's central
value. If a code state is *named* from an acceptance criterion and the system then
"discovers" that the code model and the AC model agree, it has discovered only its
own naming step. The divergence detection that justifies the whole approach would
report agreement everywhere and find nothing.

**X-12.** Naming alignment and semantic agreement are recorded as **separate
facts**. Comparison (S-5) operates on transition structure — source state,
trigger, guard, target state — **never on state names alone.**

### 5.6 Determining unfolding bounds

M-6 requires a condition to be *bounded and enumerable* before unfolding. §2
deferred how the bound is found.

**X-13.** Bounds are derived from the **literals appearing in guards over that
variable**. If guards reference `attempts < 5` and `attempts >= 5`, the bound is
5, and the variable unfolds into states for 0…5.

**X-14.** If no literal bound is recoverable, the variable is **not unfolded** and
remains a guard. An unbounded unfolding is infinite; guessing a bound fabricates
states that do not exist.

### 5.7 Matching transitions to acceptance criteria (R5)

This is §3.3's *matching* mechanism, distinct from §4.4's *comparison*.

**X-15.** Matching runs in three stages:

| Stage | Mechanism | Purpose |
|---|---|---|
| 1 | **Deterministic pre-filter** | Narrow candidates by functional area, and by trigger or endpoint referenced in the AC text |
| 2 | **Judgement over a bounded candidate list** | Decide which candidates the AC actually describes, given the transition's full tuple and its code anchor |
| 3 | **Human confirmation** | A proposed link is confirmed or rejected |

**X-16.** Stage 1 always runs first. A judgement step over an unfiltered candidate
set is both expensive and less accurate.

**X-17 — name similarity is never sufficient.** An endpoint called
`/password-reset` and an acceptance criterion mentioning "password reset" is a
**candidate for review**, not evidence of a match. This is the shortcut that would
make coverage numbers meaningless while appearing to solve the matching problem.

**X-18.** A match is **proposed, never asserted** (F-7). Matching is a judgement
and is treated as one throughout.

**X-19 — a join that cannot be made yet is proposed, never dropped and never
invented.** Two facts that belong together frequently arrive from different
intakes at different times. Both obvious responses are wrong: dropping the join
loses a real relationship, and writing the edge anyway produces one pointing at
a node that may not exist — which `land` reports as `unmatched` without
failing, so both stages report success over a broken chain.

A proposal is therefore a first-class record carrying **the basis it was made
on**, and resolution has **three** outcomes, not two:

| | |
|---|---|
| `confirmed` | the confirming intake ran and holds the target — this becomes an edge, or a property |
| `refuted` | it ran and does **not** hold the target — the belief was wrong, and that is a finding |
| `proposed` | it has **not run** — the join may yet resolve |

Collapsing `refuted` into `proposed` is the specific failure this rule exists to
prevent: a retry treats "no" as "not yet" and never stops, and a reviewer never
learns their proposal was wrong.

An intake **declares** which joins it can offer and which it can settle, so a
new intake adds a row rather than code. Where the confirming side supplies a
value rather than a target node — a selector is how to reach an element, not a
thing in the system — the join resolves to a **property**, and landing it as a
node would put a locator string in the label space.

**X-19a — a query is a node, labelled by its dialect.** What an application asks
a database is a fact about its behaviour and belongs in the graph with the
statement it sends. It is written as `Postgres` / `Oracle` / `MySql` **instead
of** `:Query`, so every estate-wide question uses `label_expression("Query")`.

A query for which **no statement could be produced** — an unparseable form, or a
derived method whose table no catalogue confirms — lands as `JpaQuery` with its
raw text and the reason. Landing it as its dialect would place it in the set a
reader queries when they want runnable statements, with an empty `query`; a
plausible-looking statement that does not run is worse than an absent one.

### 5.8 Limits — stated, not discovered later

| Limit | Consequence | Handling |
|---|---|---|
| **Only explicitly-represented behaviour is recoverable** | State held across services, or implied by data presence, will not appear | Report "no model recovered" honestly rather than emit a degenerate one |
| **Data-flow analysis is not sound** | False and missing transitions both occur | Everything lands at `Quarantine`; nothing auto-approves |
| **Unresolved source states** | A transition may have no recoverable source state | Emitted **without** a source state, flagged — never given a guessed one |
| **No frequency or liveness information** | Static analysis cannot say a transition never fires in production | Accepted. Execution data is a partial substitute |
| **Absence is not evidence of absence** | An AC matching no transition may be unimplemented, or implemented invisibly to the analysis | Reported as a finding for triage, never as a proven gap |
| **Framework coverage varies** | UI extraction quality differs sharply by framework | Declared support only; unsupported ⇒ reported (X-4) |

### 5.9 Committed by this section

- Control dependence as the disqualifying capability for engine choice (X-1)
- Sidecar isolation; pinned engine and query set (X-2, X-3)
- Both surfaces extracted, with UI framework support declared not guessed (X-4)
- A seven-step pipeline, failing on partial parse (§5.3, X-5), dropping only
  provably inert intake, reported (X-5a), and landing payloads as a graph with
  typed validation (X-6b)
- The naming cascade with recorded provenance and human backstop (§5.4)
- **Naming is not agreement** — the circularity guard (X-11, X-12)
- Bounds from guard literals; no guessed bounds (X-13, X-14)
- Three-stage matching, pre-filter first, name similarity never sufficient (§5.7)
- Limits stated up front (§5.8)

### 5.10 Deferred to later sections

| Question | Section |
|---|---|
| Graph representation of extracted candidates and anchors | 8 |
| Review interface for naming and confirming matches | 9 |

---

## 6. Coverage criteria and path generation

**This is the component that exists in none of the three systems.** Everything
else in this specification is either working code or a thin adapter over it.
Without this section there is no model-*driven* testing — only test stubs
triggered per transition.

### 6.1 What a criterion is

**P-1.** A coverage criterion is a function from a model to a **set of required
elements**. Generation succeeds when every required element is covered by at least
one path, or is reported uncoverable with a reason.

### 6.2 The criteria ladder

Under P-5 a criterion determines **how many tests exist per transition, and with
what setup and data variation** — never how many assertions a test makes.

| Criterion | Produces | Typical use |
|---|---|---|
| **All states** | One test per state, validating arrival at it | Smoke coverage |
| **All transitions** *(default)* | **One test per transition** | **The standard working criterion** |
| **All transition pairs** | The same transition tested once **per arrival path** — different setup, same single assertion | Deeper regression where how you got there matters |
| **Guard coverage** | The same transition tested once **per data combination** — different data, same single assertion | Security and boundary-sensitive journeys |

**P-1a.** Every criterion preserves one validation per test. Deeper criteria add
**more tests**, never more assertions per test.

**P-2.** The default is **all transitions**, on **both surfaces**. It is the
criterion whose coverage number is meaningful without qualification and whose
cost is predictable.

**P-2a.** Guard coverage is **opt-in per journey**, requested where combination
depth is genuinely wanted — typically an API surface with negative and boundary
cases. Making it a default would multiply cost on every journey, including those
where all-transitions is sufficient.

**P-3.** Guard coverage may be **unsatisfiable** where guards are not
complementary — an atomic condition may have no reachable path making it false.
Unsatisfiable requirements are **reported as such**, never silently dropped. A
criterion that quietly reduces its own requirements reports success it did not
achieve.

**P-3a — guard coverage is bounded by dimension scope.** For a transition failing
at dimension *k* (GD-2), guard coverage varies **only dimension *k***:

| Dimensions | Treatment |
|---|---|
| 1 … *k−1* | Held at **pass** — required to reach this transition at all |
| ***k*** | **Varied** — this is the axis under test |
| *k+1* … *n* | **Not varied** — unreachable, so variation is unobservable (GD-3) |

This is what makes guard coverage affordable. Without it, the criterion produces
the full product and most of it asserts nothing.

**P-3b.** Where precedence is unresolved (GD-9), the bound does **not** apply.
Guard coverage falls back to the full product and the resulting test count is
reported as an explosion warning, not silently generated.

**P-3c — cross-cutting class credit.** Transitions in an equivalence class
(GD-7) are covered once for the class, provided their code anchors are identical
(GD-8). Anchors that differ are covered separately — a per-endpoint deviation in a
cross-cutting check is precisely where a real vulnerability hides, and must never
be credited away.

**P-4.** A coverage figure is **never reported without naming its criterion.**
"87% covered" is meaningless; "87% of transitions, 41% of transition pairs" is a
statement.

### 6.3 Path generation

**P-5 — objective: one validation per test.** A path has exactly **one validated
transition**. Everything before it is **setup**, not assertion.

```
Arrange   traverse initial state → the validated transition's source state
Act       fire that transition's trigger, with data satisfying its guard
Assert    observe its target state          ← the single validation
```

**Why one validation.** A test that asserts several things cannot say which one
broke. A failure at step three of a chained path invalidates every later step and
reports nothing useful. One validation per test makes every failure localise to a
single transition, and makes automation straightforward.

**P-5a — setup is not coverage.** Transitions traversed during Arrange are
**not** credited as covered. They are arrangement. Only the validated transition
is credited. Crediting setup would claim assertions that were never made.

**P-6 — the algorithm.**

```
required ← criterion(model)              # transitions to validate
paths    ← ∅

for each e in required            (deterministic order):
    setup ← shortest path: initial state → source(e)      (BFS)
    if setup not found within the setup cap:
        report e uncoverable, with the reason
        continue
    paths ← paths + Path(setup = setup, validated = e)
```

Generation is one path per required element. There is no chaining and no
set-cover optimisation, because coverage is no longer the thing being minimised —
diagnosability is being maximised.

**P-6a — minimise setup, not path count.** The optimisation objective is the
**shortest setup** that reaches each validated transition. Path count follows from
the criterion and is not reduced.

**P-7 — determinism.** Element ordering and shortest-path tie-breaking use a
**total order** over states and transitions. The same model and criterion produce
**byte-identical** paths on every run. Without this, coverage cannot be compared
between runs and regression is undetectable.

**P-8 — path boundaries.** Setup starts at an initial state. A path never starts
mid-machine — a tester must be able to establish the starting condition.

**P-8a — the setup cap.** Setup length is capped (default **10** steps, from
§11.1's measurements). A transition whose shortest setup exceeds the cap is
reported uncoverable with its required setup length, never silently dropped. The
cap bounds arrangement effort, not assertion count.

### 6.4 Loops

**P-9.** A path may revisit a state **at most once**, and only to cover a loop
transition; thereafter it must progress. This keeps the path set finite and
predictable.

**P-10.** M-6's unfolding already converts most apparent loops into distinct
states — `Failed1 → Failed2 → Failed3` is a simple path, not a loop. P-9 therefore
applies mainly to genuine self-loops.

### 6.5 Interaction with disputed and excluded elements

**P-11.** Path generation **excludes** `Disputed` transitions (S-8) and `planned`
transitions. Both are excluded for different reasons and both are reported
separately:

| Excluded | Reason | Reported as |
|---|---|---|
| `Disputed` | Sources disagree; awaiting resolution | **Blocked** — coverage is pending, not absent |
| `planned` | Behaviour not yet built | **Out of scope** — correctly not a gap |

**P-12.** Where exclusion makes a required element unreachable, that element is
reported **uncoverable-by-exclusion**, naming the blocking element. Silently
lowering the denominator would inflate the coverage figure.

### 6.6 Budgets

**P-13.** Generation runs under a configured path budget. If the budget is
exhausted before the criterion is satisfied, generation **stops and reports** what
was covered and what remains. It never silently samples, truncates or degrades to
a weaker criterion.

### 6.7 The path artefact

**P-14.** A generated path is a first-class, persisted artefact carrying:

| Field | Content |
|---|---|
| **`validated_transition`** | **The single transition this path asserts** (P-5) |
| **`setup_transitions[]`** | The ordered Arrange prefix — traversed, **not** credited (P-5a) |
| Criterion | Which criterion it was generated for |
| Setup data requirements | Conditions the Arrange steps require |
| Validation data requirements | Conditions the validated transition's guard requires (M-9 — conditions, not solved values) |
| Provenance | Model version, source commit, generator version, generation run |

**P-14a — shared setup is explicit.** Paths whose `setup_transitions` are
identical share a **precondition group**, keyed by that setup sequence. This is
what makes *"open the login page"* one shared precondition across every test that
starts there, rather than repeated prose in each case.

**P-15.** Paths are separate from test cases. A path is *what must be covered*; a
test case is *the artefact rendered from it*. Keeping them distinct makes coverage
computable and leaves a second renderer available later without remodelling.

### 6.8 Coverage reporting

**P-16.** A coverage report states, always together:

- the **criterion** applied;
- **required** elements, and how many were covered;
- **uncovered** elements, each with a reason —
  *unreachable within the cap* · *blocked by a disputed element* ·
  *excluded as planned* · *budget exhausted*;
- the **model version and commit** the figure refers to.

**P-17.** Coverage is reported **per model**, and rolled up per journey only with
the criterion carried through. A journey-level figure that averages two surfaces
under different criteria is not a measurement.

### 6.8a Coverage attribution — what is tested, where, and how

The two surfaces have **different combination spaces**. A UI test may never reach
an API transition (client-side validation stops it), and an API may accept
combinations the UI cannot produce. Coverage must therefore record not just
*whether* a transition was exercised but *how*.

**C-1 — three coverage mechanisms.**

| Mechanism | Meaning | Counts as covered? |
|---|---|---|
| **Direct** | A path generated against this model traverses this transition | ✅ |
| **Indirect** | A path on another surface **rendered** this outcome, through `INVOKES` (M-5a) | ✅ |
| **Initiated** | A path on another surface **started** this call, through `TRIGGERS` (M-5a) | ❌ **reported, never counted** |
| **Uncovered** | None of the above | — |

**Why `initiated` is not coverage.** C-3's argument — that a UI transition's
inherited guard makes the credit structural — holds for `INVOKES`, where an
outcome was observed. It does not hold for `TRIGGERS`: at the moment the request
leaves, no outcome has occurred. Counting it would mark the 500 a page never
handles as tested, which is the exact gap M-5f exists to surface. The fact that
the call was made is real and is reported beside the covered figure, never
inside it.

**C-2 — indirect coverage counts, but not for every criterion.**

| Criterion | Indirect coverage credited? |
|---|---|
| All states | ✅ Yes |
| **All transitions** | ✅ **Yes** — the transition was genuinely exercised |
| All transition pairs | ⚠️ Only where the invoking path traverses the same pair |
| **Guard coverage** | ❌ **Never** |

**Why guard coverage is excluded.** Guard coverage requires each atomic condition
exercised both true and false. A UI path can only ever produce the combinations
the UI is capable of submitting. Crediting it would claim combination coverage
that was never achieved — the precise failure of *"one test case covering the
whole path as tested."*

**C-3 — indirect credit is structural, not a judgement.** M-5c makes a UI
transition's inherited guard a *reference* to the API transition's guard. A UI
path traversing that UI transition therefore necessarily satisfies that API
guard. No scenario-similarity heuristic is needed or permitted.

**C-4 — surface-only transitions are expected, not gaps.**

| Case | Coverage | Reported as |
|---|---|---|
| **UI-only** — client-side validation, navigation, display (no `INVOKES`, M-5d) | UI paths only | Normal. Never a gap against the API model |
| **API-only** — no inbound `INVOKES` (M-5f) | **Direct API paths only.** A UI path can never cover it | A finding *and* a direct-coverage requirement |

**C-5 — criteria are chosen per model, defaulting the same on both.** Both
surfaces default to all-transitions (P-2). Guard coverage is requested per journey
where combination depth is wanted — typically an API surface. A journey-level
figure never averages across surfaces (P-17).

### 6.8b The coverage ledger

**C-6.** Every coverage claim is recorded as a row, so *what is tested, where, and
how* is queryable rather than inferred:

| Transition | Surface | Mechanism | Test case | Criterion | Notes |
|---|---|---|---|---|---|
| `api:LoggedOut→LoggedIn` | api | direct | TC-101 | all-transitions | |
| `api:LoggedOut→LoggedIn` | api | indirect | TC-205 (ui) | all-transitions | via `INVOKES` |
| `api:LoggedOut→LoggedIn` | api | direct | TC-118 | guard coverage | `!locked` false branch |
| `ui:LoginForm→ValidationError` | ui | direct | TC-207 | all-transitions | UI-only, no `INVOKES` |
| `api:LoggedOut→RateLimited` | api | **uncovered** | — | — | **API-only** (M-5f) |

**C-7.** The ledger answers, for any transition:

- is it covered, and to what criterion;
- by which test cases, on which surface;
- directly or indirectly;
- and — where uncovered — why (unreachable, blocked by a disputed element,
  excluded as planned, budget exhausted, or **API-only and untested**).

**C-8.** A transition covered **only** indirectly is reported as such. It is not
presented as equivalently tested to one with direct coverage, because its
combinations were never exercised.

**C-9 — pair tracking.** The ledger is keyed by transition, so every
state-to-state movement in the model carries its own test status. A coverage
report may be pivoted by state pair, by surface, or by criterion without
recomputation.

**C-10 — the ledger records coverage, not outcome.** A row states that a test
case *covers* a transition. It does **not** state whether that case ran, passed
or failed; execution results remain in the test-management tool and are out of
scope (§8.7).

**C-11 — say so plainly in reports.** A coverage figure therefore answers *"is
this behaviour tested?"* and **not** *"is this behaviour working?"* A transition
may be fully covered and currently failing, and the ledger cannot tell the
difference. Reports must not imply otherwise.

**Staging trigger.** Ingesting execution results — reinstating `TestCycle` and
`TestExecution` from §8.7 — becomes justified the first time someone reads a
coverage report as a statement about quality rather than about test existence.

### 6.9 Committed by this section

- Criterion as a function to required elements (P-1)
- A four-rung ladder, all-transitions as default (§6.2)
- Unsatisfiable requirements reported, never dropped (P-3)
- Coverage never stated without its criterion (P-4, P-17)
- Minimise count subject to a length cap, for human executability (P-5)
- Deterministic, byte-identical generation (P-7)
- Single-revisit loop rule (P-9)
- Disputed and planned excluded, reported distinctly, denominator never lowered silently (P-11, P-12)
- Budget exhaustion stops and reports (P-13)
- Path as a persisted artefact distinct from a test case (P-14, P-15)

### 6.10 Deferred to later sections

| Question | Section |
|---|---|
| Graph representation of paths | 8 |

---

## 7. Test-case rendering and publishing

### 7.1 One path, one test case

**T-1.** Each generated path renders to exactly one test case. The path is the
unit of coverage; the test case is its human-executable form.

### 7.2 The mapping

A test case has **one validation** (P-5). Its structure is arrange-act-assert.

| Test-case field | Derived from |
|---|---|
| **Name** | The validated transition — source state, trigger, target state |
| **Objective** | The acceptance criterion validating **that one transition** |
| **Precondition** | The **setup path**, rendered as arrangement steps, plus the data it requires |
| **Step (the Act)** | The validated transition's trigger, rendered per §7.3 |
| **Expected result (the Assert)** | The validated transition's target state, as an **observable** outcome (M-3) |
| **Labels** | Source ticket key(s), functional areas, criterion, model version, precondition group |

**T-1a.** A test case asserts **exactly one** expected result. Setup steps carry
no assertions — they are arrangement, and a failure during setup is reported as a
**blocked** test, not a failed one.

**T-2.** Every step — setup or act — maps to exactly one real transition. **No
narrative filler steps**, no "verify the page loads correctly" corresponding to
nothing in the model.

**T-3.** The expected result is a real target state. A rendering whose expected
result cannot be traced to a state in the model fails the stage (F-9).

**T-3a — shared preconditions are rendered once.** Test cases in the same
precondition group (P-14a) reference **one shared precondition definition** rather
than repeating it. Where the test-management tool has no shared-precondition
concept, the text is emitted identically in each case and the group is recorded in
labels, so the relationship survives.

### 7.3 Rendering a step — a grounded cascade

Prose is a **generated judgement**, so it carries the same discipline as every
other judgement in this specification.

**T-4.** Step wording resolves by the first tier that yields it:

| Tier | Wording from | Condition |
|---|---|---|
| **1** | The **confirmed acceptance criterion** validating this transition | A human-confirmed match exists (X-18) |
| **2** | **Generated prose** describing the trigger and its guard | Always available |
| **3** | **Verbatim** trigger and guard, untranslated | Fallback if generation is unavailable or ungrounded |

**T-5.** The **verbatim guard is always attached**, whichever tier produced the
wording. Prose is a convenience; the exact recovered condition is the
authoritative statement and remains auditable with its file and line.

```
Step 2 · Submit the form with invalid credentials
  Expected result: Login rejected; second failed attempt recorded
  Condition:       !credentials_valid && attempts < 5
                   AuthController.java:88 @ a3f21c
  Source:          AC-2 of PROJ-1421 (confirmed match)
```

**T-6.** Generated prose MUST NOT introduce behaviour absent from the transition
it renders. A rendering that adds an action, a check, or a condition not present
in the model is rejected, not published with a caveat.

**T-7.** Prose is **regenerable and never authoritative.** It is not stored back
into the model, and re-rendering never alters the model.

### 7.4 Test data

**T-8.** Guards appear as **data requirements**, not solved values (M-9). A test
case states the condition the data must satisfy; it does not invent an account,
a password or an attempt count.

**T-9.** Data requirements are aggregated into a **Test Data Requirements**
section as well as appearing per step, so a tester can prepare the fixture before
executing rather than discovering requirements mid-run.

### 7.4b The authoring surface — the call, the scaffold, the answer

A model you can traverse is not yet a model you can act on. **X-6e** says the
graph must yield the artefact somebody runs, and yield it under the same rules
that govern every other rendered thing.

**T-9c holds: the space, not a value.** A generated call carries placeholders
describing what each field accepts — `<OOBSMS_TWILIO|OOBPHONE_TWILIO|QUESTIONS>`,
`<string, length 3..40, required>` — and never a sample. That is not caution for
its own sake: a single valid value is one test case, where the accepted space is
what a case is *chosen from*, so the space is the more useful answer as well as
the honest one. A rendered call contains no literal that was not recovered, and a
test asserts it.

**T-9d holds: what could not be recovered is marked.** A base URL lives in
deployment config, not in a controller, so it renders as `{base}` with the reason
attached. A UI element with no authored selector renders as a stub that raises,
never as a plausible `#export-button` — a fabricated selector looks usable, which
is what makes it worse than an empty field.

Three surfaces, and they are not equally ready, which the output states:

| surface | yields | bounded by |
|---|---|---|
| `api` | a `curl` with its outcomes and what produces each rejection | the base URL, which is not in source |
| `ui` | a Page Object whose methods chain along `NAVIGATES_TO` | **selectors, which no pack can recover** — §5.2a is authored for exactly this reason |
| data | a `SELECT` over the catalogue's own columns | generation only; **nothing in Métis executes SQL**, and a connection to a real database is a capability decision rather than a rendering one |

**Answering is composition, never narration.** The tools state facts —
`call_recipe`, `auth_facts`, `payload_shape`, `journey_walkthrough` — and `ask`
routes a question to them and returns what they said. It **may state nothing
absent from their output**, which is T-6 applied one level up, and a question no
tool answers is reported as unroutable rather than answered from general
knowledge. A fluent wrong sentence about how authentication works is the most
expensive thing this system could produce.

The auth answer carries its own caveat for the same reason. Declarative security
is all extraction can see; a filter chain or a gateway enforces authentication
invisibly to it. Measured on a real service: **zero endpoints declared any**, and
its identity travelled as ordinary header parameters — so "nothing declared" and
"open" are different claims, and only the first is ever made.

### 7.4a Automation-support detail

R8 selected human-readable test cases, not executable code. But a case that is
only prose forces an automation engineer to re-derive from English what the model
already knows precisely.

**T-9a.** Every test case carries a **machine-readable companion payload**
alongside its human-readable form. The prose is for the tester; the payload is for
whoever automates it later.

| Field | `api` surface | `ui` surface |
|---|---|---|
| **Act** | HTTP method and path | Action type and element reference, where recoverable |
| **Assert** | Expected status and error discriminator | Expected view or route, and displayed message |
| **Guard data** | Conditions as structured predicates, not prose | Same |
| **Setup** | The ordered setup transitions, each with its own act/assert detail | Same |
| **Anchors** | `file:line@commit` for trigger and guard | Same |
| **Linkage** | — | The `INVOKES` target: which API behaviour this UI test drives (M-5a) |
| **Identity** | Path identity, precondition group, model version | Same |

**T-9b.** The payload is **derived, never authored.** It restates model facts in a
consumable shape; it introduces nothing (T-6).

**T-9c.** The payload contains **conditions, not values** (M-9). It states that a
step requires `!credentials_valid`; it does not invent a username. Solving
conditions to concrete data remains out of scope (§12).

**T-9d.** Where a detail is not recoverable — a UI element with no stable
selector, for instance — the field is **absent and marked unrecoverable**, never
filled with a guess. A fabricated selector is worse than an empty one, because it
looks usable.

### 7.5 Identity

**T-10.** A test case's identity is **content-derived from its path**: the model
identity plus the ordered transition sequence. The criterion is metadata, not
identity — the same walk generated under two criteria is one path and one test
case.

**T-10a — a technique that varies the DATA varies the case.** T-10 was written
when every criterion selected *paths*, and it is exactly right about the
criterion being metadata: the same walk under `all-transitions` and
`guard-coverage` is one case. It did not anticipate a technique that produces
several cases over **one** walk, differing only in what they send.

Boundary analysis does: `attempts = 4`, `= 5`, `= 6` are three tests over one
transition, and finding the off-by-one is the entire point of running it.
Pairwise does: seven optional inputs give eight cases that traverse identical
transitions. Under T-10 as first written all five boundary cases hashed to one
id, so publishing them wrote one and silently discarded four — the technique
appeared to run and produced a single test.

So identity is the walk **plus the data requirement that distinguishes the
case**. The criterion stays out of it, which is T-10's actual claim: two
criteria that select the same walk *with the same data* still yield one case.

**T-11.** Stable identity is what makes §7.6's drift detection possible. Without
it, every regeneration would appear to be an entirely new suite. T-10a preserves
this: a data requirement is derived deterministically from the model, so the same
model regenerates the same ids.

### 7.6 Re-generation and drift

**T-12.** Regeneration performs a **three-way comparison**, not a two-way one:

```
        last generated  ─┐
                         ├─►  drift report
        currently published ─┤
                         │
        newly generated ─┘
```

**T-13.** Three-way comparison distinguishes two changes that a two-way diff
would conflate:

| Difference | Meaning |
|---|---|
| newly generated ≠ last generated | **The model changed** — behaviour moved |
| currently published ≠ last generated | **A human edited the published case** — manual work exists |

**T-14.** The drift report classifies every case:

| Class | Meaning | Default action |
|---|---|---|
| **Unchanged** | Nothing to do | None |
| **New** | A path with no published case | Propose creation |
| **Changed** | The model moved | Propose update, showing the diff |
| **Manually edited** | Published content differs from what Métis last generated | **Propose nothing** — surface for a human decision |
| **Obsolete** | A published case whose path no longer generates | Propose deprecation, never deletion |

**T-15.** **Nothing is written without a decision.** In particular, a manually
edited case is never overwritten by regeneration — a tester's added steps,
environment notes or data are real work, and silently destroying them would
teach people not to trust the tool.

**T-16.** An obsolete case is **deprecated, never deleted**. Its execution history
is evidence.

### 7.7 Publication

**T-17.** Drafts are written locally and shown **in full** before any external
action.

**T-18.** No external call occurs without a **literal affirmative confirmation**
in that run (G2). No timeout-implies-yes. No default-yes.

**T-19.** A batch receives **one decision covering the batch**, not a gate per
case — a per-case gate produces reflexive approval.

**T-20.** **One component owns external writes.** No other component calls the
test-management API. A single owner is what makes T-18 verifiable: there is
exactly one place to assert against.

**T-21.** In the first release, publication runs **dry-run only** (C3). The real
path is built and gated, and the dry-run payload is validated.

**Acceptance test for the gate:** withhold confirmation, assert **zero** external
calls were attempted, against a stub that records every attempt.

### 7.8 Traceability carried into the artefact

**T-22.** A published test case carries enough to reconstruct its origin without
the graph: source ticket key(s), model identity and version, source commit,
criterion, and the covered transitions.

**T-23.** In the graph, the full chain resolves with no orphans:

```
TestCase → TestPath → Transition → AcceptanceCriterion → Requirement → JiraItem
```

### 7.9 Committed by this section

- One path, one test case (T-1)
- Every step maps to a real transition; no filler (T-2, T-3)
- Grounded rendering cascade, AC wording preferred (T-4)
- Verbatim guard always attached and authoritative (T-5)
- Prose never introduces behaviour, never becomes authoritative (T-6, T-7)
- Data as requirements, aggregated for fixture preparation (T-8, T-9)
- Content-derived identity enabling drift detection (T-10, T-11)
- **Three-way drift comparison distinguishing model change from manual edit** (T-12, T-13)
- Manually edited cases never overwritten (T-15)
- Obsolete cases deprecated, never deleted (T-16)
- Single write owner, literal confirmation, batch decision (T-18 – T-20)

### 7.10 Deferred to later sections

| Question | Section |
|---|---|
| The review and confirmation interface | 9 |

---

## 8. Data model

### 8.1 Principles

**D-1 — every label earns its place.** A label is included only when something in
§§2–7 writes it and something reads it.

*Written before the rebuild:* the **v1** ontology carried ~45 labels; this
application needs twelve. Retaining the other thirty-three would advertise
capability that does not exist — the precise failure this specification corrects.

*Where it landed:* **fifty-six** (§8.2), and the number is a warning to
heed rather than explain away. What makes it a different set from v1's is that
every label added since carries a named writer and a named reader, which the
original thirty-three did not — the business, Web and data layers were each
asked for by name to answer a question the graph could not. The check on any
further growth is `test_ontology.py`'s: name the writer, name the reader, and if
either is "a file somebody will write one day", stage it in §8.7 instead.

**D-2 — the ontology is closed.** Adding a label or relationship is a reviewed
change touching four places together: the schema, the structural validator, the
relationship catalogue, and this section. A label present in three of the four is
a bug in the fourth, not a variant reading.

**D-3 — nothing is destructively overwritten.** Supersession creates a new
version; the prior one remains reconstructable (M-15).

### 8.2 Labels — sixty-five, and closed

The count is pinned by `test_ontology.py`
(`assert len(KNOWN_LABELS) == 65`), so this table and
`metis_mcp/ontology/labels.py` cannot drift apart without a test failing. D-1
governs additions: name the writer and name the reader, or stage it in §8.7.

**A specialisation is written instead of its parent.** `ApiCall` and `UiAction`
carry that label *only* — never together with `:Transition`, which is left
meaning "unclassified" and therefore findable. A query or a planned edge written
against `:Transition` matches a classified transition **not at all, and reports
no error**. Use `ontology.label_expression("Transition")` to match any of them,
and `landing.transition_label_for(surface)` to plan an edge into one.


| # | Label | Purpose | Written by |
|---|---|---|---|
| 1 | **`Episode`** | Immutable record of one ingested unit; everything derived points back to one | Intake (§3.2 stage 2) |
| 2 | **`JiraItem`** | Evidence anchor for one Jira issue; survives its Requirement being rejected | Intake |
| 3 | **`Requirement`** | One requirement statement | Intake |
| 4 | **`AcceptanceCriterion`** | One atomic, testable condition | Intake |
| 5 | **`State`** | One observable situation on one surface (M-3) | Model sources (§4) |
| 6 | **`Transition`** | One interaction: trigger, guard, source and target state | Model sources (§4) |
| 7 | **`Component`** | One deployable component at one commit — `<journey>-<surface>` | Extraction / approval |
| 8 | **`ApiCall`** | A `Transition` on the api surface — written **instead of** `:Transition`, not alongside it (see below) | Extraction (§5) |
| 9 | **`UiAction`** | A `Transition` on the ui surface: one interaction or observation | Web extraction (§5.2) |
| 10 | **`Page`** | One screen of a web surface; its states are the conditions it shows | Web extraction (§5.2) |
| 11 | **`Scenario`** | One covering walk (P-14) | Path generation (§6) |
| 12 | **`TestCase`** | One rendered, human-executable artefact | Rendering (§7) |
| 13 | **`Finding`** | A divergence, gap, unverifiable guard, or drift item | Reconciliation, validation, drift |

**`NeedReview` — a marker, not a thing in the world.** It is carried *alongside*
a node's real label, never instead of one, and it says exactly what
`lifecycle_state` already says: a human still owes a decision here
(`Quarantine` or `Disputed`).

It exists for the one question the property cannot answer. `lifecycle_state` is
indexed on 54 labels, so asking it of any *one* of them is cheap; there is no
way to ask it of *all* of them without scanning every node in the graph.
`MATCH (n:NeedReview)` is the review queue, whatever the node happens to be.

**`lifecycle_state` remains authoritative and this is never consulted to decide
anything.** The marker is maintained from it — set by `landing.land` when a node
arrives in a reviewable state, removed by the same statement that records a
decision. Two representations of one fact is where most of this codebase's real
defects have come from, so the rule is that they cannot disagree, and
`test_ontology.py` asserts it rather than trusting it.

| 51 | **`Lesson`** | One authored academy lesson about Métis itself — the only label whose subject is this system (D-2; see `docs/academy/PROPOSAL-landing-the-academy.md`) | `model_sources.lessons` / search |
| 52 | **`Passage`** | One section of a document, embedded on its own — searched, never shown, and rolled up to the document that contains it. Added under D-2 on a measurement: per-section vectors scored 32/36 against 26/36 for whole-document ones, because a Neo4j vector index carries one vector per node and per-section similarity is not expressible as a property | `model_sources.lessons` / both search paths |
| 53 | **`Topic`** | A subject shared by documents that cover the same ground — one node many documents point at, so "what else covers this" is a traversal rather than a second search. Topics nest (`Topic-[:BELONGS_TO]->Topic`), and a corpus's root is named after the SYSTEM it documents — declared in the corpus index, refused when absent, because a folder name says where files sit and nothing about what they are about. Authored, never inferred; deliberately not `BusinessArea`, which is what a *product* is about | `model_sources.lessons` / `related_by_topic` |
| 57 | **`NeedReview`** | Marker: a human still owes a decision on this node | Landing, finding writer |

**The evidence layer.** The nine below hold the processed intake the control-flow
model above is derived from. They were added together because they are one
claim, and four of them (`Endpoint`, `Class`, `Method`, and `Repository`'s
neighbours) come off §8.7's staging list under D-11 — see **D-12**.

| # | Label | Purpose | Written by |
|---|---|---|---|
| 14 | **`Endpoint`** | One HTTP entry point as recovered from code (Layer 2) | Raw landing (§5) |
| 15 | **`Parameter`** | One input an endpoint reads: where it rides and what it must be | Raw landing |
| 65 | **`SecurityScheme`** | One declared security requirement on an endpoint: the scheme, the declaration verbatim, and the roles it demands. **A node because a scheme with two roles has no positional representation** — the three parallel `security_*` arrays it replaces were misaligned on a third of a real corpus | Raw landing |
| 16 | **`Class`** | One declared type: a controller, a service, or a payload schema | Raw landing |
| 58 | **`Enum`** | A type whose instances are a closed set of named constants. **Specialises `Class` and is written instead of it** — an enum's `constants` ARE the equivalence partitions of any field of that type, so it needs no boundary analysis. Numbered 57 and sitting here for the same reason `NeedReview` is numbered 56 and sits above row 14: the ordinal is order of addition, the position is the layer | Raw landing |
| 17 | **`Field`** | One field of a type, with the constraints declared on it | Raw landing |
| 18 | **`Method`** | One method, from Layer 1's structural pass | Raw landing |
| 59 | **`Query`** | One thing the application asks a database, with the statement it sends. **Written as its dialect, never as `:Query`** — so every estate-wide question uses `label_expression("Query")` | Raw landing (X-19a) |
| 60 | **`Postgres`** · **`Oracle`** · **`MySql`** | The dialect a query is sent in. Labels rather than a property because `MATCH (q:Oracle)` is the question people ask; they specialise `Query`, so the estate-wide form still exists and a service talking to two databases stays one queryable set | Raw landing |
| 61 | **`JpaQuery`** | A repository call whose statement could not be recovered — carried raw with its reason, for a person to complete. The tier that exists so nothing is guessed | Raw landing |
| 19 | **`DeclaredOutcome`** | One observable result of an entry point, as recovered | Raw landing |
| 20 | **`Check`** | One condition evaluated on a path — a guard's own evidence | Raw landing |
| 21 | **`ExceptionMapping`** | An `@ExceptionHandler`'s exception → status mapping | Raw landing |
| 22 | **`Route`** | One frontend route: the path that renders a page | Raw landing (§5.2) |
| 23 | **`BusinessArea`** | One business domain grouping entities and requirements | The glossary source (§4.6a) |
| 24 | **`BusinessEntity`** | One business noun: what it is, and what acting on it changes | The glossary source (§4.6a) |
| 25 | **`UiElement`** | One thing on a page whose type has not been established | The web-structure source (§5.2a) |
| 26 | **`Menu`** | A navigation or command grouping | The web-structure source (§5.2a) |
| 27 | **`UiTable`** | A tabular listing of records on a page | The web-structure source (§5.2a) |
| 28 | **`Form`** | A set of inputs submitted together | The web-structure source (§5.2a) |
| 29 | **`Dialog`** | A modal surface raised over a page | The web-structure source (§5.2a) |
| 30 | **`Row`** | One record's line in a table, and the controls it carries | The web-structure source (§5.2a) |
| 31 | **`Pagination`** | A table's paging control | The web-structure source (§5.2a) |
| 32 | **`Sort`** | A table's ordering control | The web-structure source (§5.2a) |
| 33 | **`Action`** | An affordance a person can invoke — the thing a click lands on | The web-structure source (§5.2a) |
| 34 | **`Event`** | The interaction that invokes an action (click, submit, change) | The web-structure source (§5.2a) |
| 35 | **`Navigation`** | A control that moves to another page | The web-structure source (§5.2a) |
| 36 | **`Datasource`** | A configured connection through which statements run | The data-structure source (§5.2b) |
| 37 | **`Database`** | One database instance | The data-structure source (§5.2b) |
| 38 | **`Schema`** | A named grouping of objects within a database | The data-structure source (§5.2b) |
| 39 | **`DbObject`** | A database object whose kind has not been established | The data-structure source (§5.2b) |
| 40 | **`Table`** | A stored relation | The data-structure source (§5.2b) |
| 41 | **`View`** | A derived relation | The data-structure source (§5.2b) |
| 42 | **`Function`** | A callable routine | The data-structure source (§5.2b) |
| 43 | **`Column`** | One column, with the constraints declared on it | The data-structure source (§5.2b) |
| 44 | **`ConfluenceItem`** | Evidence anchor for one Confluence page | Intake landing (§3.2 stage 2) |
| 45 | **`OpenApiItem`** | Evidence anchor for one OpenAPI/Swagger document | Intake landing |
| 46 | **`ZephyrItem`** | Evidence anchor for one Zephyr Scale item | Intake landing |
| 47 | **`DatasourceItem`** | Evidence anchor for one analysed database schema | Intake landing |
| 48 | **`CodeItem`** | Evidence anchor for one analysed source tree at one revision | Intake landing |
| 49 | **`SpecDocument`** | One rendered journey specification, stored in the graph | `specgen.specification` |
| 50 | **`EntityDocument`** | One rendered business-entity specification | `specgen.entity` |
| 52 | **`Intent`** | One stated need, before anybody has specified how it behaves | Knowledge capture |
| 53 | **`Specification`** | One specified behaviour — where intent and code meet (§4.1) | Knowledge capture / extraction |
| 54 | **`Feature`** | One user-facing capability, grouping the scenarios that show it | Knowledge capture |
| 55 | **`RestServer`** | A `Component` serving an API surface — written **instead of** `:Component` | Extraction / approval |
| 56 | **`WebServer`** | A `Component` serving a web surface — written **instead of** `:Component` | Extraction / approval |

**D-13 — the business layer is what the nouns mean, and it is deliberately not
the evidence layer.** `Class` and `Field` record what the code *declares*;
`BusinessEntity` records what the business *means*. The two disagree regularly,
and that disagreement is a finding — sharing one label to avoid it would hide
exactly the divergence §4.1 says the platform exists to surface.

Its reader is the one that justifies it: a criterion's nouns previously existed
only as words inside prose, so *"what does this mean, and what else touches it"*
was not a question the graph could answer. **An entity's properties are JSON
text, not nodes**, on `Transition.inputs`' reasoning — the reader renders them
all, none queries one. Promote when one does, as `Parameter` was.

**D-12 — the evidence layer is contract-shaped, and X-2 still holds.** What lands
is `code_analysis.contract`'s dataclasses, which are already normalised and
engine-independent; **no engine node type, id or schema enters the graph**, so an
upgrade still touches only the pack. That is the difference between *landing
ontology-shaped code structure* — which §8.7 explicitly stages — and *merging the
engine's graph*, which X-2 forbids and this does not do.

The trigger §8.7 predicted was impact analysis. The trigger that actually fired
was narrower and stronger: the control-flow layer could not say what it was
derived from. Every one of these facts sat in a JSON file outside the repository,
so "which endpoint produced this transition" and "which transitions send a field
constrained `@NotNull`" were not questions the graph could answer.

**D-13 — `Method` and `CALLS` were landed ahead of their reader, and that clause
has now been exercised.** Their stated trigger, impact analysis, is not built.
D-1 requires a reader, and this rule said: *if nothing comes to query the call
graph, remove them rather than let the ontology accrete.*

Nothing came. The nearest thing to a reader is `behavior_model.corroborate`,
which queries `Method` and `CALLS` and **is called by nothing**; measured on a
twelve-endpoint service it would need 17 of the 199 methods landed. So the call
graph is **not landed by default** (`include_call_graph`), and what stays is
every method something points at — the handlers behind
`Endpoint-[:HANDLED_BY]->Method` and the `@ExceptionHandler`s behind
`ExceptionMapping-[:HANDLED_BY]->Method`.

"Off" therefore means **bounded, not absent**, and the distinction was a defect:
the flag predates both of those edges, so switching it off left the graph unable
to say which method serves a route. The count dropped is reported (X-5a).

**Not nodes, by decision:**

| Concept | Represented as | Why |
|---|---|---|
| **Journey** | `functional_areas` array property (M-4) | A grouping label, not a referenceable entity |
| **Surface** | `surface` property on States, Transitions, Component | An attribute of a model, not a thing |
| **Guard / trigger** | Properties of `Transition` (M-11) | No existence apart from their transition |
| **Code structure** | `Class` / `Method` nodes **plus** anchor properties | Superseded by D-12. The *engine's* graph still stays in the sidecar (X-2); what lands is the contract's own shape, and every node keeps its `commit`/`file`/`line` anchor |
| **Repository** | The extraction unit, named on every anchor | Still staged out (§8.7): nothing writes or reads it |

### 8.3 Relationships

| From | Relationship | To | Meaning |
|---|---|---|---|
| `JiraItem` | `REPRESENTS` | `Requirement` | System-of-record source |
| `ConfluenceItem` / `OpenApiItem` / `ZephyrItem` / `DatasourceItem` / `CodeItem` | `REPRESENTS` | `Requirement` | The same edge, per intake source |
| `SpecDocument` | `DESCRIBES` | `Component` | The component version this specification renders |
| `EntityDocument` | `DESCRIBES` | `BusinessEntity` | The business noun this specification defines |
| `SpecDocument` / `EntityDocument` | `CITES` | `AcceptanceCriterion` | A criterion rendered in this document — what makes the round trip checkable without parsing markdown |
| `JiraItem` | `LINKS_TO` | `JiraItem` | A real Jira issue link — provenance, not traceability |
| `Intent` | `SPECIFIED_BY` | `Specification` | A need, once somebody has said how it behaves |
| `Specification` | `HAS_AC` | `AcceptanceCriterion` | The conditions the behaviour breaks into |
| `Specification` | `SPECIFIES` | `Requirement` | Keeps §7.8's chain reaching a Requirement (A-24) |
| `Specification` | `REALISED_BY` | `Feature` | The capability this behaviour is part of — the edge `feature.derive` establishes, since it groups specifications |
| `AcceptanceCriterion` / `Requirement` | `REALISED_BY` | `Feature` | The capability it is part of |
| `Feature` | `HAS_SCENARIO` | `Scenario` | The walks that demonstrate it |
| `Endpoint` / `Action` | `IMPLEMENTS` | `Specification` | The code side reaching the same node, by its own verb |
| `RestServer` | `EXPOSES` | `Endpoint` | The entry points it serves |
| `WebServer` | `HAS_PAGE` | `Page` | The screens it serves |
| `RestServer` / `WebServer` | `CONTAINS` | `Transition` | Its behaviour at one commit |
| `Requirement` | `HAS_AC` | `AcceptanceCriterion` | Its atomic conditions |
| `AcceptanceCriterion` | `VALIDATES` | `Transition` | Confirmed match (X-18) |
| `State` | `WHEN` | `Transition` | Source state — the implicit *Given* |
| `Transition` | `THEN` | `State` | Resulting target state |
| `UiAction` | `TRIGGERS` | `ApiCall` | This interaction **starts** that API flow; the UI continues its own (M-5a). One-to-many; human-confirmed |
| `UiAction` | `INVOKES` | `ApiCall` | This UI outcome **rendered** that API outcome (M-5a, M-5b). Many-to-one; human-confirmed |
| `Component` | `HAS_PAGE` | `Page` | A screen this web component presents |
| `Page` | `SHOWS` | `State` | A condition this page can be observed in (M-2, M-3) |
| `Component` | `CONTAINS` | `State` \| `Transition` | Membership of this component version |
| `Scenario` | `GENERATED_FROM` | `Component` | The exact component version this path covers |
| `Scenario` | `COVERS` *(with `sequence`)* | `Transition` | Ordered traversal — makes coverage computable |
| `Scenario` | `PRODUCES` | `TestCase` | The rendered artefact |
| `Finding` | `ABOUT` | any | What the finding concerns |

**Inside the evidence layer:**

| From | Relationship | To | Meaning |
|---|---|---|---|
| `Component` | `EXPOSES` | `Endpoint` | The entry points this deployable presents |
| `Endpoint` | `SECURED_BY` | `SecurityScheme` | A declared security requirement a caller must satisfy |
| `Endpoint` | `ACCEPTS` | `Parameter` | What a caller must send |
| `Parameter` | `OF_TYPE` | `Class` | The payload schema — the same node as the declared type |
| `Endpoint` | `RETURNS` | `Class` | The declared response body type |
| `Class` | `HAS_FIELD` | `Field` | Its declared fields and constraints |
| `Class` | `DECLARES_METHOD` | `Method` | Its methods |
| `Endpoint` | `HANDLED_BY` | `Method` | The handler behind the route |
| `Method` | `CALLS` | `Method` | A resolved call edge (Layer 1) |
| `Method` | `ISSUES` | `Query` | A query this method sends to a database |
| `Query` | `QUERIES` | `Table` | A table this query reads or writes |
| `Query` | `QUERIES` | `View` | A view this query reads |
| `Query` | `USES` | `Column` | A column this query names — a test-design input, because it is what a fixture has to populate |
| `Endpoint` | `DECLARES` | `DeclaredOutcome` | A result this entry point can produce |
| `DeclaredOutcome` | `GUARDED_BY` | `Check` | The condition selecting this outcome |
| `ExceptionMapping` | `HANDLED_BY` | `Method` | The `@ExceptionHandler` that maps it |
| `Route` | `RENDERS` | `Page` | The page this frontend route shows |
| `Page` | `CALLS` | `Endpoint` | An API call this page makes |

**From the control flow back to its evidence** — this is what the second layer is
for:

| From | Relationship | To | Meaning |
|---|---|---|---|
| `Transition` | `DERIVED_FROM` | `Endpoint` \| `DeclaredOutcome` \| `ExceptionMapping` | What this behaviour was recovered from |
| `Transition` | `EXERCISES` | `Parameter` | An input this transition sends |
| `Transition` | `REQUIRES` | `Field` | A field constraint a case must satisfy or violate (GD-3) |
| `Transition` | `EXPECTS` | `Class` | The response body a case should assert |
| `Transition` | `CONSTRAINED_BY` | `Check` | The recovered condition behind its guard |

**D-14 — provenance is an edge, not a property.** `source_episode_id` says which
*ingest* produced an element; it cannot say which endpoint, which outcome or
which field. A transition that cannot name its own evidence is a claim a reviewer
has to take on trust, which is the same objection §8.5 raises about an unanchored
guard.

**D-4.** `AcceptanceCriterion -[:VALIDATES]-> Transition` is the **only** path from
requirements to behaviour. A `TestCase` never links directly to a `Requirement` —
traceability always routes through an acceptance criterion and a transition.

**Business layer edges (D-13).**

| From | Relationship | To | Meaning |
|---|---|---|---|
| `BusinessEntity` | `BELONGS_TO` | `BusinessArea` | Which domain this noun lives in |
| `Requirement` | `BELONGS_TO` | `BusinessArea` | Which domain this requirement governs |
| `AcceptanceCriterion` | `REFERENCES` | `BusinessEntity` | A business noun this criterion acts on or constrains |

`REFERENCES` is the edge that makes impact answerable in either direction:
*which criteria touch this entity*, and *which entities does this requirement
depend on*. It never replaces D-4's route — traceability from a test case still
runs through an acceptance criterion and a transition, and a `BusinessEntity` is
never on that path.


**Web structure and data edges (D-14).**

| From | Relationship | To | Meaning |
|---|---|---|---|
| `Datasource` | `CONNECTS_TO` | `Database` | Which database this connection addresses |
| `Table` / `View` | `HAS_COLUMN` | `Column` | A column it declares |
| `Dialog` / `Form` / `Menu` / `Page` | `HAS_ELEMENT` | `Action` / `Dialog` / `Event` / `Form` | A control this surface presents |
| `Database` / `Schema` | `HAS_OBJECT` | `DbObject` / `Function` / `Table` / `View` | An object it contains |
| `Database` | `HAS_SCHEMA` | `Schema` | A grouping it contains |
| `Navigation` | `NAVIGATES_TO` | `Page` | Where this control goes |
| `Action` | `ON_EVENT` | `Event` | The interaction that invokes this action |
| `BusinessEntity` | `STORED_IN` | `Table` | Where this business noun is persisted |

### 8.4 Versioning

**D-5.** A `Component` node is created on every extraction or approval that changes a
model's element set. It carries `journey`, `surface`, `version`, `commit_sha`,
`created_at`, `approved_by`.

**D-6.** Elements are **shared across versions where unchanged** — a `CONTAINS`
edge from each version that includes them. An unchanged transition is not
duplicated per version.

**D-7.** *"Which version did this path cover?"* is one edge
(`GENERATED_FROM`), and *"what changed between v2 and v3?"* is a set difference
over `CONTAINS`. Both were the reason for choosing an explicit version node over
a purely temporal representation.

### 8.5 Baseline properties

**D-8.** Every node carries:

| Property | Rule |
|---|---|
| `id` | **Content-derived**, never sequential. Two workers processing the same input converge on the same id, so a duplicate write is a no-op rather than a duplicate |
| `source_episode_id` | The Episode justifying it. **Enforced without exception — but not always by the schema; see D-8a.** An `Episode` is exempt: it is the provenance record and cannot point at one |
| `name` | Display data, not an identity key |
| `lifecycle_state` | §8.6 |
| `created_at` | UTC |

**Model-specific properties:**

| Label | Properties |
|---|---|
| `AcceptanceCriterion` | `revision`, `provenance` (S-19 grade — see D-9b) |
| `State` | `surface`, `functional_areas[]`, `name_provenance` (naming tier, X-8) |
| `Transition` | `trigger`, `guard_expression`, `guard_anchor` (file:line@commit), `implementation_status`, `extraction_method` (M-13), `surface`, `functional_areas[]`, `source_state_unresolved` |
| `Component` | `component` (stable id), `journey`, `surface`, `version`, `commit_sha`, `approved_by` |
| `Scenario` | `criterion`, `sequence_length`, `generator_version`, `data_requirements[]` |
| `TestCase` | `content_hash`, `last_generated_hash`, `published_id`, `published_status`, `level` |
| `Finding` | `finding_type`, `severity`, `resolution`, `resolved_by` |

**D-8a — which layer enforces what, by edition.** Property-**existence**
constraints are an Enterprise-only feature. Under DD-2's Community decision they
**cannot be created**, verified against a live Neo4j 5 Community instance
(`Property existence constraint requires Neo4j Enterprise Edition`).

| Rule | Community | Enterprise |
|---|---|---|
| `id` uniqueness | **Schema** | Schema |
| Required-property existence | **Application gate** (`metis_mcp/ontology/validation.py`) | Schema *and* gate |
| Enum membership | **Application gate** (ONT-012) | Application gate |
| Relationship-triple legality | **Application gate** | Application gate |

An earlier draft of D-8 said existence was "schema-enforced, no exceptions". That
was true only on Enterprise, and asserting it under a Community deployment would
claim a guarantee the database is not providing. Both DDL variants are generated
(`metis2-01-constraints.cypher`, `…-enterprise.cypher`) so the difference is
explicit rather than discovered.

**D-8b.** The rule itself is unchanged: no node may exist without
`source_episode_id`. Only the enforcing layer differs. On Community the
application gate is the *sole* guarantee, which raises the cost of any write path
that bypasses it — hence D-10's requirement that every write goes through
validation.

**D-9.** `TestCase.last_generated_hash` is what makes §7's three-way drift
comparison possible. Without it, a manual edit and a model change are
indistinguishable.

**D-9a — `TestCase.level` and additive generation (REQ-METIS-PG-01).** `level` is
one of `unit`, `integration`, `api_functional`, `web_functional`, `e2e`,
`performance` — where a case sits in the pyramid, not what it asserts.

Generation **never fires for a layer already covered**. Measured on the pilot
estate: of 145 transitions, 83 are already covered by integration tests that
pass, and generating for them produced review burden and a flattering coverage
figure in exchange for nothing.

**Covering an endpoint is not covering a transition**, and the grading keeps the
two apart:

| Grade | Meaning | Generates? |
|---|---|---|
| `covered` | a test reaches it **and** asserts its outcome | no |
| `endpoint_covered_outcome_unproven` | a test reaches the endpoint; this outcome is not evidenced | **yes** |
| `uncovered` | nothing reaches it | yes |

The middle grade exists because a test that calls `GET /{id}` and asserts `200`
is evidence for the 200 transition and says nothing about the 204 one. Promoting
it to `covered` would excuse real gaps; demoting it to `uncovered` would discard
real evidence. It is reported as the judgement it is.

A skipped target is recorded in `CriterionResult.unsatisfiable` **naming the test
that covers it** — P-12 forbids quietly lowering the denominator, and "already
tested" is a different fact from "not covered".

**D-9b — `AcceptanceCriterion.provenance` is what makes S-19 storable.** One of
`code_derived`, `human_confirmed`, `independently_authored`, indexed, defaulting
to the weakest grade for the same fail-closed reason a model source lands at
Quarantine (S-4).

| Grade | How it is earned | Supports |
|---|---|---|
| `code_derived` | drafted from an extracted model | coverage only |
| `human_confirmed` | a person **edited** the text, or explicitly **affirmed it as intent** | correctness |
| `independently_authored` | written without reading the code | correctness, strongest |

The property is indexed because the question it answers is a filter rather than a
lookup: *which criteria in this scope are still `code_derived`* is precisely what
separates a coverage claim from a correctness one, and §3's run status depends on
it.

This property was missing until the workflow layer was built, and its absence was
not cosmetic: `review/decisions.py` computed the promoted grade correctly and had
nowhere to put it, so **every promotion was discarded**. A grade the graph cannot
store is a grade that does not exist — which is why the enum is owned by
`ontology/labels.py` and re-exported to `reconciliation/matching.py`, not the
other way round.

### 8.6 Lifecycle states

| State | Meaning | Set by |
|---|---|---|
| `Quarantine` | A candidate awaiting review | Every model source (S-4) |
| `Approved` | Confirmed; usable for generation | Human approval (G1) |
| `Disputed` | Sources disagree; blocks traversing paths (S-8) | Reconciliation |
| `Rejected` | Reviewed and declined | Human |
| `Deprecated` | Superseded; retained as evidence (T-16) | Drift resolution |

**D-10.** Path generation reads **only** `Approved` elements.

### 8.7 Deliberately excluded, and when they return

| Excluded | Returns when |
|---|---|
| `Goal`, `Capability`, `Epic` | A backlog hierarchy is actually queried — not for test generation |
| `Release`, `TestCycle`, `TestExecution` | Execution results are ingested and release reporting is required |
| `Defect`, `Incident`, `Alert`, `Metrics`, `Logs` | Operational data enters scope |
| `Constitution`, `Constraint` | Formal governance is adopted |
| `Repository`, `Class`, `Method`, `Endpoint` | Impact analysis needs code structure in the graph, not just anchors |
| `TestDesign`, `TestSuite`, `MicroRequirement` | A concrete need appears — none exists in §§2–7 |
| `Revision` | Property-level history is designed **and** something writes it. It was declared with neither a writer nor a reader, and its wildcard `HAS_REVISION` edge was the widest hole in a closed catalogue. The integer `revision` property on `Requirement` and `AcceptanceCriterion` is what the graph uses today |
| `Run` | Two generation runs need comparing **in the graph** — F-3's comparability half. Its reproducibility half already rides on `Component` (version, commit) and on `.metis/runs/*.json` (scope, criterion), which is what `workflow status` reads. `Run` was written by `plan_persist` and `finding_writer` and matched by no query: a writer with no reader is what D-1 exists to prevent |

**D-11.** This list is the staging plan, not a rejection. Each entry names the
trigger that justifies adding it, so growth is deliberate rather than accretive.

### 8.8 Committed by this section

- Twelve labels, each with a named writer and reader (D-1, §8.2)
- Closed ontology under a four-place governance rule (D-2)
- Journey, surface, guard and code structure as properties, not nodes (§8.2)
- Traceability only via `AcceptanceCriterion → Transition` (D-4)
- Explicit `Component` versions with shared unchanged elements (D-5, D-6)
- Content-derived ids making duplicate writes no-ops (D-8)
- `last_generated_hash` as the enabler of three-way drift detection (D-9)
- Five lifecycle states; generation reads only `Approved` (§8.6, D-10)
- An explicit staging list for excluded labels (D-11)

### 8.8a Validity in time (D-15, D-16)

**D-15 — validity is a second axis, not a refinement of lifecycle.**
`lifecycle_state` answers *has a human looked at this*; validity answers *was
this ever true, and is it still*. They are independent, and a fact may be
`Approved` and no longer valid. Collapsing them loses both answers, and a system
whose purpose is comparing what the code does **now** against what somebody said
**then** cannot express "true until release 4.2" with either alone.

Four labels carry it — `Intent`, `Specification`, `Requirement`,
`AcceptanceCriterion` — because "true until" means something for a claim and
nothing for a `Method` or a `Class`, which are facts about a commit. An
`Episode` is exempt for the same reason it is exempt from the baseline: it is
already immutable and content-addressed.

`valid_from` is required. `valid_to` is required **and may be empty**: `""` is
the honest representation of "still true", where absent would be
indistinguishable from "nobody recorded it" — the same conflation
`Transition.guard_expression` refuses.

**Invalidation sets `valid_to`. Nothing is deleted.** The superseded fact
remaining answerable is the point: *what did we believe in March* is a question
the graph should answer, not one it should have forgotten. Invalidation is
therefore not a lifecycle decision and does not disturb one — retracting a
reviewer's approval would misrepresent what they decided.

Two consequences bind implementations:

* **Validity properties are written once.** They ride in the `ON CREATE SET`
  clause. Were `valid_to` re-asserted on every landing, a routine re-extraction
  would reset a superseded fact to valid — an invalidation an unrelated re-run
  can undo is not an invalidation.
* **A read that ignores `valid_to` answers the wrong question.** It reports what
  was ever believed while appearing to report what is believed now, and that
  failure looks exactly like success. Every read over a validity-carrying label
  filters on validity, or is recorded as a known exception.

**D-16 — search indexes are generated from the catalogue, like every other
constraint.** Free-text and semantic search are schema features of the graph
database, not application code, so they are declared beside the labels they
serve and emitted by the same generator. Two lists in two files is the drift the
generated schema exists to prevent.

Full-text uses a stemming analyzer: with the default tokeniser, a search for
`lock` returns nothing for a criterion reading "the account is locked", which
beats substring matching on ranking and loses to it on word forms.

An embedding is meaningless outside the model that produced it. A vector
therefore records which model wrote it, and a query whose model disagrees is
**refused rather than answered** — the failure is otherwise silent and
confidently wrong, which is X-3's lesson in a different costume. A corpus
carrying more than one model is refused for the same reason: part of it would be
unreachable without anybody being told.

### 8.9 Deferred to later sections

| Question | Section |
|---|---|
| Interfaces over this model | 9 |
| Retention and volume expectations | 11 |

---

## 9. Interfaces

### 9.1 Why this section carries risk

The specification contains **six human decision points**. If performing them is
awkward, the system stalls at its own gates — and because nothing auto-promotes
(F-8), a stalled gate means no output at all. The interface is therefore not
presentation; it is throughput.

| # | Decision | Where |
|---|---|---|
| 1 | Approve a model | G1, §3.4 |
| 2 | Name a state | Tier 3, X-7 |
| 3 | Resolve a divergence | S-11 |
| 4 | Confirm an AC↔transition match | X-18 |
| 5 | Decide a drift item | T-14 |
| 6 | Confirm publication | G2, §3.4 |

### 9.2 Surfaces

| Surface | Role |
|---|---|
| **Web review UI** | **Primary.** All six decisions, plus model visualisation and coverage |
| **CLI** | Automation, CI, scripted runs, export/import of review decisions |
| **Agent / MCP tools** | Read-only query and explanation from a development session |
| **HTTP API** | The UI's backend; also the integration point for other tools |

**N-1.** Every decision recorded through any surface produces the same audit
record. No surface has a privileged or unlogged path.

### 9.3 The review UI

**N-2 — the model view is the centrepiece.** A rendered state machine: states as
nodes, transitions as edges, coloured by lifecycle state
(`Approved` / `Quarantine` / `Disputed`), with a **coverage overlay** showing
which transitions the current path set covers.

This is the single clearest artefact the system produces, and it is the main
justification for a purpose-built interface over a conversational one.

**N-3 — evidence requirements per decision.** Each decision screen must present
enough to decide without leaving it:

| Decision | Must show |
|---|---|
| **Approve model** | The machine; all validation findings; reconciliation gaps both directions; per-element source; every unnamed state |
| **Name a state** | The raw observable signature; AC-mined candidates (tier 1); code-convention candidates (tier 2); names already used by sibling states |
| **Resolve divergence** | Both sides with full anchors — code `file:line@commit` versus AC text and ticket key; the paths currently blocked; what each choice implies |
| **Confirm match** | The AC text; the transition's full tuple; the code anchor; **why it was proposed** (which pre-filter matched) |
| **Decide drift** | The three-way comparison (T-12) with the class assigned; exactly what would change if applied |
| **Confirm publication** | Full draft content for the whole batch; the target; the dry-run payload |

**N-4.** A decision screen that cannot show its required evidence **blocks the
decision** rather than presenting a partial view. Approving without evidence is
the failure the gate exists to prevent.

**N-5 — batch operations are supported, batch blindness is not.** Multiple items
may be decided together (T-19), but the UI must show what is being decided. A
"approve all" that does not enumerate its contents is prohibited.

### 9.4 CLI

**N-6.** Covers the pipeline and automation:

```
metis extract   <repo> --surface api|ui --commit <sha>
metis mine      <ticket>
metis model     validate <journey>-<surface>
metis reconcile <journey>-<surface>
metis paths     generate <scope> --criterion all-transitions --max-steps N
metis render    <path-set>
metis publish   <draft-set> --dry-run
metis report    coverage <scope>
metis review    export|apply <scope>          # decisions as a reviewable file
```

**N-7.** `review export` / `review apply` allow decisions to be made in a
diffable, version-controllable file. This is the escape hatch for volume and for
teams who prefer review-as-code.

### 9.5 Agent / MCP surface

**N-8 (superseded 2026-08-23).** *Originally:* read-only; no decision may be
taken through this surface, because decisions require the evidence presentation
of N-3 and a chat session cannot provide it.

**That prohibition was lifted by an explicit product decision.** The reasoning
behind it was not, and it is now carried by four invariants instead of one rule:

| | |
|---|---|
| **off by default** | `METIS_MCP_WRITE` is `off` \| `author` \| `full`, and an unconfigured server is read-only *by construction* — the write modules are not imported at all |
| **everything lands at `Quarantine`** | S-4. Authoring is not approving; only the gate module may write `Approved` |
| **a gate costs its literal** | G1 needs `approve`, G2 needs `publish`, in that call. No default, no timeout, no truthy value |
| **every write is audited** | through `roles.record_decision(..., surface="mcp")` — the same function every other surface uses (N-1) |

**N-8a.** Identity on this surface is *asserted by the caller and trusted*, as
the review UI trusts its identity header. Honest for a localhost tool;
unacceptable for anything reachable by others, and `describe_policy` says so to
any agent that asks.

Read-only remains the default and the recommended deployment. What changed is
that it is now a configuration rather than a property of the code — and the
tests that used to prove the prohibition now prove the four invariants above.

### 9.6 Roles

**N-9.** Four roles:

| Role | May |
|---|---|
| **Viewer** | Read everything |
| **Contributor** | Run extraction and mining; propose models; generate paths; render drafts |
| **Reviewer** | Contributor, plus: approve models, name states, resolve divergences, confirm matches, decide drift |
| **Publisher** | Reviewer, plus: confirm external publication |
| **Admin** | All, plus configuration and user management |

**N-10 — separation of proposal and approval.** By default, the identity that
proposed a model element **may not approve it.** The reviewer gate is meaningless
if the proposer can approve their own proposal.

**N-11.** N-10 is configurable, because a small team may have no second reviewer.
Where it is disabled, **every self-approval is recorded as such** and appears in
the audit view. The override is visible, not silent.

**N-12.** Publication is separated from review because it writes to a system
outside Métis's control and is the least reversible action. In a small team the
same person may hold both roles; the **actions remain separately logged**.

### 9.7 Identity and audit

**N-13.** Every decision records: who, when, what was decided, and **what evidence
was presented at the time.**

**N-14.** The last clause matters. An approval must be auditable against what the
reviewer actually saw — not against what the graph looks like today. Without it,
a later reader cannot distinguish a careless approval from a reasonable decision
on then-available information.

**N-15.** The audit record is append-only. A decision may be superseded; it is
never edited or removed.

### 9.8 Build order — scope is not sequence

All of §9 is in scope. It need not be built first, and should not be.

**N-16 — recommended order**, so the riskiest unproven component is proven
earliest:

| Stage | Build | Rationale |
|---|---|---|
| 1 | CLI + the MBT engine (§6) against a known-good model | The engine exists nowhere; if it fails, nothing else matters |
| 2 | CLI review via `export` / `apply` (N-7) | Unblocks the six decisions without a front end |
| 3 | Extraction (§5), one surface, then the second | Two pipelines, sequenced |
| 4 | Web review UI (§9.3) | Once there is review volume to justify it |
| 5 | Roles and identity (§9.6) | Once more than one person operates it |

**N-17.** Stages 4 and 5 are **in scope, later** — not deferred indefinitely and
not quietly dropped. Building them before stage 1 would mean constructing an
interface and a permission model around an engine not yet known to work.

### 9.9 Committed by this section

- Four surfaces; identical audit from all of them (N-1)
- The model view with coverage overlay as the centrepiece (N-2)
- Per-decision evidence requirements, blocking when unavailable (N-3, N-4)
- Batch decisions permitted, batch blindness prohibited (N-5)
- Review-as-code via export/apply (N-7)
- Agent surface read-only; no decisions without evidence (N-8)
- Five roles; proposal separated from approval by default (N-9, N-10)
- Self-approval override visible and recorded, never silent (N-11)
- Audit records the evidence presented, not just the outcome (N-13, N-14)
- Build order sequencing the engine ahead of interface and roles (N-16)
- An HTTP API whose gates survive the transport (N-18, N-19)

### 9.6 The HTTP API (N-18, N-19)

**N-18 — a network surface authenticates; it does not trust what it is told.**
The review UI reads identity from a header and trusts it, which is honest for a
tool bound to loopback and unacceptable for anything reachable otherwise. On a
network a trusted header is an impersonation hole leading directly into both
gates, and every audit record it produces records whoever the caller claimed to
be.

Credentials are bearer tokens checked against a store of **digests**, so a leaked
configuration file leaks nothing replayable. The environment names the store's
path and never a secret (PLT-005). A raw token in the store is refused at load,
because otherwise the file silently becomes a secret without anybody deciding
that; a malformed line or an unknown role is refused rather than skipped, because
a skipped line is a principal who believes they have access and does not.

Nothing else changes. Capability is decided where it was already decided, the
audit record is written by the function that already writes it — differing only
in the surface it names — and a decision that cannot present its evidence is
blocked rather than partially taken. A rule enforced in the router would be a
rule the other surfaces do not have.

**N-19 — a confirmation is bound to a run, and consumed once.**
G2 requires a literal affirmative confirmation *in that run*. On a terminal that
phrase enforces itself: the run is the process the operator is looking at. HTTP
has no run — a request body carrying the affirmative word is a string an attacker
can replay, a proxy can retry, and a client library can resend on a timeout it
judged transient. Any of those re-confirms a publication nobody re-authorised.

A confirmation over HTTP is therefore issued as a single-use ticket bound to the
batch that was shown and the identity it was shown to, and consumed on first
acceptance. A ticket that has been used, a batch that changed after it was shown,
and a confirmation presented by a different identity are each refused, and the
ticket is consumed **before** the literal word is checked so that a caller cannot
probe for a valid ticket by sending wrong words at it.

Reads answer with the same content as the agent surface. Where they cannot answer
at all — no graph configured — they return **no content** rather than a success
carrying a failure, because a success a client must read the body to disbelieve
is a trap laid across every client library's happy path. A read that legitimately
finds nothing is a different answer and says so.

---

## 10. Trust requirements

Ten requirements. Each derives from a rule already committed; this section states
them as the properties the system must never violate, so a change that breaks one
is visible as a breach rather than a refactor.

| # | Requirement | Derived from |
|---|---|---|
| **TR-1** | **Everything traces to its source.** Every model element resolves to the exact text or code anchor that justified it — file, line and commit, or ticket and text span | M-8, M-14, X-6 |
| **TR-2** | **Nothing auto-promotes.** No element becomes `Approved` without an explicit human decision. No promotion on elapsed time, ever | S-4, F-8 |
| **TR-3** | **Conflicts are preserved, never resolved automatically.** Divergence between sources is the product, not an obstacle | M-16, S-9, S-10 |
| **TR-4** | **Deterministic code is preferred to generated judgement**, and every judgement step is justified, bounded and verified | X-15, X-16, T-6 |
| **TR-5** | **Ungrounded proposals are blocked**, however well-formed. Fluent well-formedness is what a fabrication looks like | S-13, T-6 |
| **TR-6** | **Re-running is idempotent.** Content-derived identity makes a duplicate write a no-op, not a duplicate | D-8, T-10 |
| **TR-7** | **Decisions record their evidence**, not merely their outcome. An approval is auditable against what the reviewer saw | N-13, N-14 |
| **TR-8** | **No silent degradation.** Truncation, exclusion, budget exhaustion and unsatisfiable requirements are always reported; the denominator is never quietly lowered | P-3, P-12, P-13, T-10 |
| **TR-9** | **Naming is not agreement.** Aligning a code-derived state's name to an acceptance criterion is never evidence that the two models agree | X-11, X-12 |
| **TR-10** | **Coverage is never stated without its criterion**, its model version and its commit | P-4, P-16, P-17 |

**TR-11 — the honesty requirement.** Métis MUST NOT present code-derived tests as
evidence that behaviour is *correct*. They are evidence that behaviour is
*covered*. Correctness comes only from reconciliation against intent (§4.1, S-1).

---

## 11. Non-functional requirements

### 11.0 Platform (PLT-002, PLT-003, PLT-005, PLT-006, PLT-007)

Five rules. The first three the code cited from the beginning and this document
never defined — written here because a citation of a rule nobody wrote is a
dangling reference that reads as authority. The last two govern how the graph is
reached and how its schema is stated; one of them the code already meets, and
one of them it does not. Which is which is said in the rule, because a rule
stated as though it were satisfied is the same dangling reference in the other
direction.

**PLT-002 — a connection resolves in one order, and the order is stated.**
Explicit arguments, then the environment, then a configuration file. No
component decides its own precedence, so a connection that works in one place
and not another is a difference in inputs rather than in code.

**PLT-003 — there is no default credential, and a missing one halts.**
A system that connects with a guessed credential is a system nobody can reason
about: it is unclear afterwards which database was written, under whose
authority. A missing credential is a halt carrying an instruction, never a
fallback.

**PLT-005 — a secret is named, never passed.**
The environment names the variable holding a credential; the credential itself
never reaches an argument. The rule is not "it must come from the environment" —
it is that the secret must not reach a process listing, a shell history, or any
log that captures a command line. A configuration file may name the variable; a
configuration file that contains the secret is refused where it can be detected,
and where a legacy file holds one it is read only if its permissions restrict it
to its owner, and the run says on stderr that it did so. A world-readable secret
read in silence is worse than either alternative.

**PLT-006 — the graph is reached through Cypher over Bolt, behind one thin
repository layer.**
One protocol and one seam. No component opens its own driver, embeds its own
connection policy, or reaches the database by any route but Cypher over Bolt;
every query lives behind a repository whose job is to run Cypher and return
rows, holding no domain logic of its own. The reason is not tidiness. A query
written inside application logic is invisible to the ontology's guards — a label
renamed in `labels.py` leaves it matching nothing, and matching nothing returns
an empty result that reads as an empty database. Concentrating the queries makes
that class of failure findable in one place, and makes "what does this system ask
of the graph" answerable by reading a file rather than the whole tree.

**The code does not meet this yet, and the distance is measured rather than
estimated: 81 queries across 19 modules.** `mbt/graph_loader.py` holds 19,
`mbt/finding_writer.py`, `mbt/graph_writer.py` and `model_sources/landing.py`
nine each, `authoring.py` and `behavior_model.py` seven each, and a dozen more
carry one or two. `mbt/graph_session.py` is already the single connection seam
(PLT-002 resolves there and nowhere else), so the protocol half of this rule
holds today; the repository half does not. Stated as a rule now because the
direction is decided — every new query belongs behind the seam, and the existing
ones move as the modules holding them are touched.

**PLT-007 — the schema is declared, never written.**
Constraints and indexes are generated from the ontology, not maintained beside
it. `metis_mcp/ontology/labels.py` is the single declaration of the label set,
the relationship catalogue and the indexed properties; `metis_mcp/ontology/schema.py`
generates `schema/metis2-*.cypher` from it. A hand-edit to a generated file is
the exact drift the generation exists to prevent.

**The code meets this today**, and two tests keep it true:
`test_generated_schema_covers_every_label` and the check that the committed
schema matches what the generator produces — so an ontology change that forgets
to regenerate fails rather than ships. This is the reason D-2's four-place rule
costs two places and not four: the validator and the schema are generated from
one source and are structurally incapable of disagreeing, leaving only the two
prose places to be checked.

### 11.1 Scale — assumptions, flagged for confirmation

**Measured**, not assumed. Sources: the login model, and five real Java/Spring
services.

| Dimension | Figure | Measured from |
|---|---|---|
| Endpoints per service | **4 – 25** | `athena-boot-kube` 4 · `git` 6 · `pipeline` 12 · `core` 22 · `tms` 25 |
| Controllers per service | 3 – 14 | Same |
| States per journey model | **10** | The login model |
| Transitions per journey model | **17** | The login model |
| Longest simple path | **8 steps** | The login model |
| **Longest setup required** | **5 steps** | The login model — `t15` (admin-unlock) needs the whole failure chain to reach `AccountLocked`. Total path length is 6; the *setup* is one shorter. Verified by `test_mbt.py` |
| Outcomes per endpoint | 2 – 4 typical | Success, validation failure, auth or not-found |
| Transitions in a whole-service model | up to ~**75** | 25 endpoints × 3 outcomes |
| Model versions retained | all | M-15 |

**Generation output, measured** — run against the login model by the built engine,
not projected:

| Criterion | Tests | Setup length (min–max, median) | Precondition groups | Uncoverable |
|---|---|---|---|---|
| all-states | 9 | 0 – 4, median 1 | 7 | 0 |
| **all-transitions** *(default)* | **16** | **0 – 5, median 2** | **9** | 0 |
| all-transition-pairs | 30 | 0 – 6, median 3 | 15 | 0 |
| guard coverage | 21 | 0 – 5, median 2 | 9 | 18 *(P-3: no complementary sibling)* |

Setup-length distribution at the default criterion: `0:3  1:5  2:3  3:2  4:2  5:1`.

**NF-1c — setup length, not test count, drives review and execution effort.** Ten
of sixteen tests need two setup steps or fewer; one needs five. A flat "16 tests"
figure hides that, and it is the distribution a reviewer and a manual tester
actually feel.

**NF-1d — precondition groups are the real unit of setup work.** Sixteen tests
share **nine** distinct preconditions; three need none at all. Preparing nine
fixtures covers the suite, which is the practical payoff of P-14a's grouping.

**NF-1e — deeper criteria cost more than their test count suggests.** Transition
pairs produce 1.9× the tests *and* raise median setup from 2 to 3. Guard coverage
produces 21 tests but reports **18 unsatisfiable targets** on this model, because
most guards have no complementary sibling to exercise the false case (P-3) — a
figure worth knowing before opting a journey into it.

**NF-1 — the setup cap follows from this.** The login model's longest required
setup is 6; the default cap of **10** (P-8a) is that with headroom, and stays
within what a person executes reliably by hand.

**NF-1a.** A whole-service model near 75 transitions produces ~75 tests under
all-transitions. That is a volume signal, not a generation problem — and it is the
point at which §9.3's review UI stops being optional.

**NF-1b.** These figures come from one hand-authored model and five services of
one system. They are **evidence, not a population**. Re-measure once real
extracted models exist.

### 11.2 Performance

| Concern | Target |
|---|---|
| Model validation | Interactive — under a second for a typical model |
| Path generation | Seconds for a model of ~60 transitions |
| Rendering | Seconds for a full path set |
| Extraction | **Batch only.** Minutes to hours; never in a request path |
| Review UI | Interactive for all six decision screens |

### 11.3 Determinism

**NF-2.** The same model version, criterion and step cap produce **byte-identical**
paths on every run, on any machine. This is not a performance property — without
it, coverage cannot be compared between runs and regression is undetectable.

### 11.4 Resumability

**NF-3.** Extraction and generation resume from checkpoint after interruption and
produce a result identical to an uninterrupted run.

### 11.5 Retention

| Retained | Duration |
|---|---|
| Episodes | Indefinitely — provenance depends on them |
| Model versions | Indefinitely (M-15) |
| Superseded test cases | Deprecated, never deleted (T-16) |
| Audit records | Append-only, indefinitely (N-15) |

### 11.6 Availability

**NF-4.** Single instance. No high-availability target, consistent with C1
(Community edition — no clustering or online backup).

**NF-5.** Backup is a scheduled offline dump with a **verified restore drill**.
An untested backup is not a backup.

---

## 12. Out of scope

Each entry names why, so its absence is a decision rather than an oversight.

| Excluded | Why | Returns when |
|---|---|---|
| **Composition of two machines** | No demonstrated need; the login model needs none (§2.2) | Two machines advance on separate timelines and one test must span both |
| **Executable test code generation** | R8 selected test cases; code needs a verified type registry and real payloads | Test cases prove valuable and automation is the next increment |
| **Solving guards to concrete values** | Guards are data *requirements* (M-9) | A constraint solver is justified by volume of manual data preparation |
| **Writing back to requirement tickets** | Jira remains the system of record | Never, by design |
| **Dynamic / runtime behaviour extraction** | R6 selected static analysis | Static recall proves insufficient |
| **The 33 unused ontology labels** | Each lacks a writer (D-11) | Per the staging triggers in §8.7 |
| **Live Jira connection** | C2 — cached export | The graph must be current rather than a snapshot |
| **Real external publication** | C3 — dry-run only in the first release | Access is granted and drift handling is proven |
| **Multi-tenancy** | Single deployment | Not anticipated |
| **High availability** | C1 | Downtime or a backup-interval data loss actually costs something |

---

## 13. Acceptance criteria

The application is accepted when all of these hold against a real feature.

### 13.1 Model

| # | Criterion |
|---|---|
| **A-1** | A model failing determinism, guard completeness or reachability **blocks** generation, with the finding shown (M-18) |
| **A-2** | An unparseable guard is reported **unverifiable**, never assumed true (M-17) |
| **A-3** | A bounded, enumerable, observable counter **unfolds** into explicit states, with residual guards preserved verbatim (M-6, M-7) |
| **A-4** | Every state satisfies the observability rule — it is distinguishable through its own surface (M-3) |

### 13.2 Extraction

| # | Criterion |
|---|---|
| **A-5** | Every extracted element carries commit, file and line; an element without an anchor is not emitted (X-6) |
| **A-6** | A partially-parsed source tree **fails the run**; no partial report is emitted (X-5) |
| **A-6a** | Intake noise is filtered on joint structural inertness, never on visibility or reachability; a getter that branches survives, fields are never filtered, and the count dropped is reported (X-5a) |
| **A-6b** | A payload is reachable as a graph to its full declared depth, and its validation is typed properties rather than annotation text; an unrecognised constraint stays visible in `constraints` (X-6b) |
| **A-6d** | Every fact is classified against the model; an `internal` fact is not landed and the reduction reported, and a `surface` fact the model cannot reach is raised as a gap whose count agrees with synthesis's own finding (X-6d) |
| **A-6e** | A generated call, Page Object or query contains no literal that was not recovered; an unrecoverable detail is marked, and `ask` states nothing its tools did not (X-6e) |
| **A-7** | A state named from the AC vocabulary is **not** thereby counted as agreeing with the AC-mined model (X-11, X-12) |
| **A-8** | An unrecognised UI framework is reported, not guessed (X-4) |

### 13.3 Reconciliation

| # | Criterion |
|---|---|
| **A-9** | Reconciliation reports **both** gap types separately: transitions with no AC, and ACs with no transition (F-4, F-5) |
| **A-10** | A divergence blocks only paths **traversing** the disputed element; other paths still generate (S-8) |
| **A-11** | Neither source wins automatically; resolution is recorded with who and why (S-10, S-11) |
| **A-12** | A match proposed on name similarity alone is **not** accepted as evidence (X-17) |
| **A-12a** | An API transition with **no** inbound `INVOKES` is reported as API-only behaviour (M-5f) |
| **A-12b** | A UI trigger invoking an API call yields **one UI transition per API outcome**, each with an `INVOKES` link (M-5b) |
| **A-12c** | A UI transition's guard **references** its invoked API transition's guard rather than restating it (M-5c) |

### 13.4 Generation

| # | Criterion |
|---|---|
| **A-13** | All-transitions coverage over a known model covers **every** implemented transition — set equality, `planned` excluded |
| **A-14** | The same model version, criterion and cap produce **byte-identical** paths on repeat runs (P-7) |
| **A-15** | Path count is materially **below** transition count — paths chain rather than one-per-transition |
| **A-16** | An element unreachable within the cap, or blocked by exclusion, is reported with its reason; the denominator is not lowered (P-12) |
| **A-17** | No coverage figure is reported without its criterion, model version and commit (P-4, P-16) |
| **A-17a** | A UI path invoking an API transition credits it for **all-transitions**, and **never** for guard coverage (C-2) |
| **A-17b** | A transition covered only indirectly is reported as such, not as equivalently tested (C-8) |
| **A-17c** | An API-only transition (no inbound `INVOKES`) is **never** credited by any UI path (C-4) |
| **A-17d** | A UI-only transition is not reported as a gap against the API model (C-4) |
| **A-17e** | The ledger answers, per transition: covered to which criterion, by which cases, on which surface, directly or indirectly (C-7) |

### 13.5 Rendering and publication

| # | Criterion |
|---|---|
| **A-18** | Every step maps to a real transition and every expected result to a real target state; no filler steps (T-2, T-3) |
| **A-19** | The verbatim guard is attached to every step regardless of how the wording was produced (T-5) |
| **A-20** | Regeneration distinguishes a **model change** from a **manual edit** via three-way comparison (T-12, T-13) |
| **A-21** | A manually edited published case is **never** overwritten (T-15) |
| **A-22** | Withholding confirmation produces **zero** external calls — asserted against a stub recording every attempt (T-18) |
| **A-23** | Dry-run produces a valid payload and makes no network call (T-21) |

### 13.6 Traceability and trust

| # | Criterion |
|---|---|
| **A-24** | The full chain resolves with no orphans: `TestCase → TestPath → Transition → AcceptanceCriterion → Requirement → JiraItem` (T-23, D-4) |
| **A-25** | Re-running any operation produces no duplicates (TR-6) |
| **A-26** | Every decision records who, when, what, and **the evidence presented** (TR-7) |
| **A-27** | A self-approval, where permitted, is recorded as such and visible in the audit view (N-11) |
| **A-28** | No report presents code-derived coverage as evidence of correctness (TR-11) |

---

## 14. Element identity, deduplication and incremental update

### 14.1 One mechanism, two requirements

Two requirements were raised separately:

| # | Requirement |
|---|---|
| **R12** | Many sources, one model — **never create a duplicate** state or transition that already exists |
| **R13** | Code changes produce **incremental model changes**, never a reset and rebuild |

They share a root cause. Both need **an element identity that is stable
independent of which source produced it and independent of which run produced
it.** Solve that once and deduplication (across sources) and incrementality
(across runs) both follow.

**I-1.** The natural key defined below is also the **correspondence mechanism**
that §4.5's reconciliation assumed without specifying. "Sources agree on an
element" is now defined: *they produced elements with the same natural key.*

### 14.2 Natural keys

**I-2.** Identity is a **natural key over meaning**, not a hash over
representation. Representation changes constantly; meaning does not.

| Element | Key | Attributes that may change without changing identity |
|---|---|---|
| **`State`** | `(model, surface, observable_signature)` | Name, name provenance, functional areas, code anchor |
| **`Transition`** | `(model, source_state, trigger, target_state)` | **Guard**, code anchor, extraction method, source-state-resolved flag |

**I-3.** `observable_signature` is surface-specific:

| Surface | Signature |
|---|---|
| `api` | Response status plus error discriminator |
| `ui` | View or route identifier |

**I-4.** The transition key references state keys, so **state identity resolves
first**. A change in a state's signature propagates to the identity of every
transition touching it — see §14.7.

### 14.3 When two transitions share a triple

Two transitions may legitimately share `(source, trigger, target)` and differ
only by guard — two distinct reasons to reach the same state.

**I-5 — matching, not hashing.** Correspondence is resolved in four steps:

```
1. find existing elements with the same natural key
2. exactly one match   -> same element; any guard difference is MODIFIED
3. several matches     -> disambiguate by normalised-guard similarity;
                          best match wins, ties are proposed for review
4. no match            -> ADDED
```

**I-6.** Guard normalisation is **minimal and deterministic** — whitespace and
canonical operand ordering only. It never rewrites, simplifies or interprets a
condition. A guard whose text differs beyond normalisation is treated as changed,
erring toward re-review rather than assuming equivalence.

### 14.4 Deduplication across sources (R12)

**I-7.** Elements from different sources with the **same natural key are one
element**, carrying multiple source attributions — not two elements.

**I-8.** Same key, differing attributes resolves per §4.5:

| Situation | Result |
|---|---|
| Same key, same guard | Sources **agree** — eligible for approval, two attributions recorded |
| Same key, different guard | **Divergence** (S-9) — `Disputed`, blocks traversing paths |
| Key present in one source only | Single-source element, flagged as such |

**I-9.** A source **never** creates an element that already exists. It contributes
an attribution to the existing one. This is R12, stated as an invariant.

### 14.5 Incremental update across runs (R13)

**I-10.** Re-extraction **never resets a model.** It produces a candidate element
set, which is matched against the current version by natural key, yielding a
delta.

**I-11.** Every element in a delta carries `delta_type`:

| Delta | Meaning | Effect |
|---|---|---|
| `ADDED` | Key not present in the prior version | New element at `Quarantine` |
| `MODIFIED` | Key present, attributes differ | Existing element updated; approval treated per §14.6 |
| `REMOVED` | Key absent from the new candidate set | Element **not** included in the new `Component` version |
| `UNCHANGED` | Key present, attributes identical | Shared into the new version (D-6) |

**I-12.** `REMOVED` never deletes. The element remains in prior versions and stays
reconstructable (D-3). "Removed" means *not a member of this version*.

**I-13 — the convergence invariant.** Extraction **may** be scoped to changed
files as an optimisation, but a scoped extraction and a full extraction of the
same commit **MUST produce the same model**. Correctness never depends on the
optimisation. This is directly testable and should be tested.

### 14.6 What survives re-extraction

**I-14.** Element facts are partitioned, and re-extraction may only replace one
partition.

| **Human facts — always preserved** | **Machine facts — replaced by extraction** |
|---|---|
| Resolved state name and its provenance | Guard expression |
| Confirmed AC↔transition matches | Code anchor — file, line, commit |
| Divergence resolutions and their rationale | Extraction method metadata |
| Human annotations | Observable-signature detail |
| Approval decisions *(subject to §14.7)* | Source-state-resolved flag |

**I-15.** Re-extraction **may propose** a different name (via the X-7 cascade) but
**never overwrites** a resolved one. A proposal is surfaced for review.

**I-16.** Human work is never silently discarded. This is the requirement hiding
inside R13 — without it, every code change resets the review burden and the
system becomes unusable within weeks.

### 14.7 What invalidates approval — scoped, not global

**I-17.** Approval is revoked **only** where behaviour actually changed:

| Change | Approval |
|---|---|
| Guard changed beyond normalisation | **Revoked** for that transition |
| Code anchor moved, guard identical | **Retained** — a refactor is not a behaviour change |
| Name changed | **Retained** — presentation, not behaviour |
| Element `ADDED` | New element unapproved; existing ones unaffected |
| Element `REMOVED` | Remaining approvals unaffected |

**I-18 — group propagation.** Determinism and guard completeness are properties
of a **`(state, trigger)` group**, not of one transition. Adding, modifying or
removing any member therefore **revalidates the whole group**, and revokes
approval for the group if validation now fails.

Without I-18 a newly added transition could silently break determinism for its
siblings while they remain approved — generating tests from a model that no
longer satisfies M-18.

**I-19.** Revocation returns an element to `Quarantine` with the **reason**
recorded and the prior approval retained in history. A reviewer sees what changed
and what they previously decided.

### 14.8 Renames and moves — the natural-key weak point

**I-20.** A change to a state's `observable_signature` (for example `401` → `403`)
changes its natural key, and would otherwise appear as `REMOVED` + `ADDED`,
discarding its name, matches and approval.

**I-21.** Where a `REMOVED` and an `ADDED` element in the same delta are
**highly similar**, the pair is proposed as a **rename or move** for human
confirmation. On confirmation, identity — and all human facts — carry across.

**I-22.** A rename is **proposed, never assumed** (consistent with F-7, X-18).
An unconfirmed pair remains `REMOVED` + `ADDED`.

### 14.9 Effect on paths and test cases

**I-23.** A model delta propagates to generated artefacts:

| Delta | Effect on paths | Effect on test cases |
|---|---|---|
| `ADDED` transition | Criterion now has an uncovered element | New path, then a new case proposed |
| `MODIFIED` guard | Paths remain structurally valid | Step condition changed ⇒ drift class **Changed** (T-14) |
| `REMOVED` transition | Paths traversing it are invalid | Drift class **Obsolete**; deprecated, never deleted (T-16) |
| Approval revoked (I-17) | Paths through the element are blocked | Regeneration blocked until re-approved |

**I-24.** §7's three-way drift comparison operates on top of this delta. §14
answers *what changed in the model*; §7 answers *what to do about the published
test cases*.

### 14.10 Committed by this section

- One identity mechanism serving both R12 and R13 (I-1)
- Natural keys over meaning, not hashes over representation (I-2)
- Guard as a mutable attribute, not part of transition identity (I-2)
- Four-step matching with similarity disambiguation (I-5)
- Minimal, non-interpreting guard normalisation (I-6)
- A source contributes an attribution, never a duplicate (I-9)
- Delta vocabulary; `REMOVED` never deletes (I-11, I-12)
- **Scoped and full extraction must converge** (I-13)
- Human facts and machine facts partitioned; only machine facts are replaced (I-14, I-15)
- Approval revoked only for real behaviour change (I-17)
- **Group revalidation for `(state, trigger)` sets** (I-18)
- Renames proposed on similarity, never assumed (I-21, I-22)

### 14.11 Additional acceptance criteria

| # | Criterion |
|---|---|
| **A-29** | Two sources producing the same natural key yield **one** element with two attributions — never a duplicate (I-9) |
| **A-30** | Re-extraction after a comment-only or formatting change produces **zero** deltas |
| **A-31** | Re-extraction after a guard change produces exactly one `MODIFIED` transition; every other element is `UNCHANGED` |
| **A-32** | A resolved state name, a confirmed match and a divergence resolution all **survive** re-extraction (I-14) |
| **A-33** | A code anchor moving with an identical guard **retains** approval (I-17) |
| **A-34** | Adding a transition to a `(state, trigger)` group **revalidates the group**, and revokes group approval if determinism now fails (I-18) |
| **A-35** | Scoped extraction of a commit produces a model **identical** to full extraction of the same commit (I-13) |
| **A-36** | A signature change producing a similar `REMOVED`/`ADDED` pair is **proposed as a rename**, not silently applied (I-21) |

---

## Open items

| # | Item | Needed for |
|---|---|---|
| **O-1** | Scale figures in §11.1 are assumptions — confirm or replace | §6 tuning |
| **O-2** | Which real feature replaces the login model as the first target | Build start |
| **O-3** | Step cap default for path generation | §6.3 |
| **O-4** | Team size — determines whether N-10's separation of proposal and approval is workable or must be overridden | §9.6 |

**All four are now closed.**

| # | Resolution |
|---|---|
| **O-1** | **Measured, not assumed** — §11.1 |
| **O-2** | **A small Athena service, `api` surface only** — §15.1 |
| **O-3** | **Premise superseded** — one validation per test (P-5); setup capped at 10 — §15.2 |
| **O-4** | **A wider team with distinct roles** — N-10 enforced, no override — §15.3 |

---

## 15. Closing decisions

### 15.1 First real target (O-2)

**A small Athena service, `api` surface only** — `athena-boot-git` (6 endpoints,
4 controllers) or `athena-boot-kube` (4 endpoints, 3 controllers).

| Why it works | What it does not prove |
|---|---|
| Available immediately; no access to arrange | The **`ui` surface** — Athena services have no UI |
| Java/Spring — the best-supported extraction frontend | **`INVOKES`** links (M-5a) and everything built on them |
| Code is owned, so ground truth is checkable | **Cross-surface divergence** (M-5f) — the highest-value finding |
| Small enough that a wrong result is diagnosable | **R5 reconciliation** against real Jira acceptance criteria, unless the service has them |

**O-2a.** These four gaps are **deferred, not descoped.** A second target with both
surfaces and real acceptance criteria is required before A-12a–A-12c and
A-17a–A-17d can be evaluated at all.

**O-2c — the analysis unit is the multi-module build, not one module.** Measured
against this exact target, not projected:

| Analysis unit | `ResponseEntityUtils.okOrNoContent` | Guard recoverable? |
|---|---|---|
| `athena-boot-git` alone | `<unresolvedSignature>` | **No** |
| `athena-boot-git` + `athena-common` | `return t.isEmpty() ? noContent() : ok(t)` | **Yes** |

Real controllers delegate response construction to a shared utility. Analysed
alone, a module's handlers show their outcome as an unresolved call, so the
condition selecting `200` from `204` is invisible — and Layer 4 would report
**zero guards**, which reads as "this service has no conditions" rather than
"the helper was out of scope".

**O-2d.** `code_analysis.mapper.analysis_unit_is_sufficient()` detects this
before Layer 4 runs, by finding calls whose callee was never emitted. §13.14's
pilot-gate criterion 4 (guards recovered ≥ 0.9) **cannot be met on a
single-module unit** for a codebase shaped this way, so the unit must be chosen
deliberately rather than by repository directory.

**O-2e — what a probe of the pilot target established.** Outcomes *are* declared:
`@ApiResponse(responseCode = …)` yields 200, 204, 201 and 400 on the real
controllers, which become target states. Twelve such annotations exist in this one
module. Layer 4 therefore has a real substrate here; what it lacks is guard
recovery, and O-2c says exactly what fixes that.

**O-2e is met.** Across the whole pilot estate the packs recover 44 declared
rejections, and synthesis discarded every one of them on a single line until
X-6a/X-6b were written. All 44 are now modelled (145 → 189 API transitions):
25 with a traced bean-validation precondition and four anchors each, 19 with the
annotation's own weaker claim. The declared **409s** are excluded — three
controllers declare one *and* construct it with a real guard, so taking both
would give one behaviour two transitions. Determinism holds across all seven
service models with **zero blocking findings**, because the endpoints that gain a
rejection also gain GD-4's matching prefix on their existing transitions; without
that, a guarded rejection beside an unguarded success is a conflict.

**O-2b.** The pilot proves the **spine** — extract → validate → reconcile →
generate → render — and leaves the **cross-surface half unproven.** State this
whenever pilot results are reported, so a green pilot is not mistaken for a green
specification.

### 15.2 Test shape (O-3)

O-3 asked for a step cap. The answer replaced the premise: **tests are focused,
with one validation each**, and shared preconditions are expected rather than
avoided.

| Consequence | Where |
|---|---|
| A path has one validated transition; the rest is setup | P-5, P-5a |
| Setup is not credited as coverage | P-5a |
| Deeper criteria add more tests, never more assertions | P-1a |
| Optimisation minimises **setup length**, not path count | P-6a |
| Setup capped at **10** steps (the login model needs at most 6) | P-8a |
| Paths sharing a setup form a **precondition group** | P-14a, T-3a |
| A setup failure is **blocked**, not failed | T-1a |
| Every case carries a machine-readable payload for automation | §7.4a |

**O-3a — the cost, accepted deliberately.** One test per transition produces more
test cases with repeated setup than a chaining strategy would. That trade was made
knowingly: a chained test cannot say which transition broke, and a failure at step
three invalidates everything after it.

### 15.3 Operators and roles (O-4)

**A wider team with distinct roles.**

**O-4a.** **N-10 is enforced, not overridden.** The identity that proposed a model
element may not approve it. N-11's override exists but is not expected to be used;
any use stays visible in the audit view.

**O-4b.** Contributor, Reviewer and Publisher (§9.6) are held by **different
people**. Publication separation (N-12) is real rather than nominal.

**O-4c.** Identity is required from the first release — every decision records who
made it (N-13). Not deferrable: an audit trail cannot be reconstructed
retrospectively.

**O-4d.** This raises the priority of §9.3's review UI. With several people and
enforced separation, **review throughput becomes the binding constraint on
output** (§9.1). N-16's build order still holds — engine first — but the UI should
not slip far behind extraction.

### 15.4 Revised acceptance criteria

| # | Criterion |
|---|---|
| **A-15** *(replaces the chaining assumption)* | Each generated path has **exactly one** validated transition; setup transitions are not credited as covered (P-5, P-5a) |
| **A-37** | A test case asserts exactly one expected result (T-1a) |
| **A-38** | Transitions sharing a source state produce paths in the **same precondition group** (P-14a) |
| **A-39** | A failure during setup is reported **blocked**, not failed (T-1a) |
| **A-40** | Guard coverage produces **multiple tests** for one transition, each with a single assertion (P-1a) |
| **A-41** | Every test case carries a machine-readable payload restating only model facts (T-9a, T-9b) |
| **A-42** | An unrecoverable automation detail is **absent and marked**, never guessed (T-9d) |
| **A-43** | A transition whose shortest setup exceeds the cap is reported uncoverable **with its required setup length** (P-8a) |

### 15.5 Guard-dimension acceptance criteria

| # | Criterion |
|---|---|
| **A-44** | A rejection transition's guard is prefix-determined: earlier dimensions pass, its own fails (GD-2) |
| **A-45** | Guard coverage for a rejection varies **only its failing dimension**; downstream dimensions are not varied (GD-3, P-3a) |
| **A-46** | An endpoint with auth, authz and 10 payload variants yields **13** tests, not 60 (GD-3 worked example) |
| **A-47** | Precedence-ordered guards pass the determinism check **structurally**, not incidentally (GD-4) |
| **A-48** | Cross-cutting transitions sharing an **identical** code anchor form one equivalence class; covering one credits the class (GD-7, GD-8) |
| **A-49** | Cross-cutting transitions with **differing** anchors are covered **separately** — a per-endpoint auth deviation is never credited away (GD-8, P-3c) |
| **A-50** | Unresolvable precedence flags `precedence_unresolved`, falls back to the full product, and **reports the explosion** rather than generating it silently (GD-9, P-3b) |
| **A-51** | Evaluation order is taken from framework chain and control flow, **never** from source line position (X-10d) |

---

## 16. The graph database's position

### 16.1 Three jobs, not one

The graph sits in the **STRUCTURE** layer (§3.6) and is Contract 2's interface —
the thing consumers query instead of re-deriving. It does three distinct jobs:

| # | Job | Why a graph |
|---|---|---|
| **1** | **It is the model** | A state machine *is* a graph. States are nodes, transitions are edges. No impedance mismatch, no reassembly |
| **2** | **It holds the traceability web** | `TestCase → TestPath → Transition → AcceptanceCriterion → Requirement → JiraItem` is a **path query**, not five joins |
| **3** | **It carries provenance and versions** | `Component -[:CONTAINS]->` is set membership; a version diff is a set difference |

### 16.2 The queries that justify it

| Question | Shape |
|---|---|
| What does this test trace back to? | Path traversal, 5 hops |
| Which transitions have no acceptance criterion? | Pattern: `Transition` with no inbound `VALIDATES` |
| Which acceptance criteria match no transition? | The mirror pattern |
| Generate covering paths | Walks over the model itself (§6.3) |
| What changed between v2 and v3? | Set difference over `CONTAINS` |
| Which cross-cutting transitions are equivalent? | Group by code anchor (GD-7) |
| Which API behaviour does this UI test drive? | `INVOKES` traversal (M-5a) |
| What does this code change put at risk? | Reachability from the changed anchor |

### 16.3 Honest scope

**GR-1.** A relational store could hold all of this. The graph is chosen because
the primary artefact **is** a graph and the dominant queries are traversals — not
because relational modelling is incapable. This is a fit argument, not a
capability one, and should not be oversold.

**GR-2 — what the graph is not:**

| Not | Where it lives instead |
|---|---|
| The code property graph | The extraction sidecar, never merged (X-2) |
| A document store | Generated documents are renderings (§18), not stored truth |
| An execution-results warehouse | The test-management tool (C-10, §8.7) |
| A metrics warehouse | Out of scope (§12) |

**GR-3.** One instance, Community edition (C1). No clustering, no online backup;
backup is a scheduled offline dump with a verified restore drill (NF-5).

---

## 17. Model manipulation

The model will sometimes be wrong — extraction is not sound (§5.8), and intended
behaviour sometimes differs from implemented behaviour. **Editing is a
first-class operation**, not an escape hatch.

### 17.1 The override

**E-1.** A human change to a model element is an **override**: a human fact
(I-14) layered on the element, never a silent mutation of it.

**E-2.** Every override records: the element, the property, the previous value,
the new value, the author, the timestamp, a **rationale**, and a
**classification** (E-4). Rationale is required, not optional.

**E-3 — operations.** Add a state or transition · remove one · modify any
property (guard, trigger, target, name, `implementation_status`). Splitting or
merging states is composed from these, not a primitive.

### 17.2 Every edit is classified — and the two classes mean opposite things

**E-4.** At the point of editing, the author states what the edit asserts:

| Class | Meaning | Produces |
|---|---|---|
| **`extraction_error`** | The extractor got this wrong; the code is fine | A finding against **Métis** — feeds query-pack improvement (X-3) |
| **`intended_divergence`** | The code is wrong, or intended behaviour differs | A finding against **the product** — a candidate defect |

**E-5.** This distinction is the point of E-4. Without it, every correction looks
alike, and neither *"our extraction is unreliable"* nor *"we found a defect"* can
be measured.

**E-6 — what the classes mean for each operation:**

| Operation | `extraction_error` | `intended_divergence` |
|---|---|---|
| **Add** an element | Extraction missed real behaviour | Behaviour that **should** exist but does not — a gap |
| **Remove** an element | A false positive from unsound analysis | The code does something it **should not** — a defect |
| **Modify** a guard | Extraction misread the condition | The condition is wrong in the code |

Removal classified as `intended_divergence` is worth calling out: it means *the
system does this and it should not*. That is one of the most valuable findings the
platform can produce, and it arrives through the editor.

### 17.3 Overrides survive re-extraction

**E-7.** An override is a human fact and is **never silently overwritten** (I-16).
Re-extraction replaces machine facts underneath it; the override continues to
apply.

**E-8 — staleness.** When re-extraction changes the underlying machine value, the
override is **flagged stale** and surfaced for revalidation:

```
STALE OVERRIDE  login-api / t7 / guard
  your value      attempts >= 5        (you, 2026-08-10, "AC says 5")
  was extracted   attempts >= 3
  now extracted   attempts >= 5        ← code now agrees with you
  -> resolve: keep override | drop as resolved | re-classify
```

**E-9.** A stale override is **not** auto-resolved even when the code catches up
with it. Someone confirms that the divergence is closed; the system does not
assume it.

**E-10 — override density is reported.** A heavily overridden code-derived model
is a weaker claim about the code. Density is shown on the model view and in the
generated specification (§18), so nobody reads such a model as a faithful mirror
of the implementation.

### 17.4 Editing does not bypass the gates

**E-11.** An edit returns the affected element to `Quarantine`. It is a
**proposal**, exactly like any source's output (S-4).

**E-12.** Under N-10, the editor may not approve their own edit. With distinct
roles (O-4) this holds without override.

**E-13.** Editing a member of a `(state, trigger)` group triggers **group
revalidation** (I-18). An edit can break determinism for siblings just as an
extraction can.

**E-14.** The friction is deliberate and is stated plainly: editing is not a fast
path around review. It is a way to correct the model *through* review.

---

## 18. Stakeholder specification

Stakeholders should not have to read a model to understand a feature. §9's review
UI serves operators; this serves everyone else.

### 18.1 Generated, never authored

**SP-1.** A journey specification is **generated from the model**. It is a
rendering, not a second source of truth — the same discipline as test-case
rendering (T-7) and for the same reason.

**SP-2.** Every statement traces to a model element. Nothing is added for
readability (T-6).

**SP-3 — the model is already Given/When/Then.** `State -[:WHEN]-> Transition
-[:THEN]-> State` renders almost mechanically:

```
Given the user is Logged Out
When  they submit valid credentials
      and the account is not locked
Then  they are Logged In
```

### 18.2 Contents

| Section | From |
|---|---|
| **Purpose** | The requirements linked to this journey |
| **Situations a user can be in** | States, with their observable signature described |
| **Behaviour rules** | Transitions as Given/When/Then (SP-3) |
| **Acceptance criteria** | `VALIDATES` links, and which rules have none |
| **What is tested** | Coverage with its criterion (P-4) and the C-11 caveat |
| **Open questions** | Divergences, unspecified behaviour, unimplemented criteria |
| **Diagram** | The model view (N-2) |
| **Provenance** | Model version, commit, generated timestamp, override density (E-10) |

### 18.3 Status must be visible

**SP-4.** A specification **must not present unapproved behaviour as agreed
behaviour.** Every rule carries its lifecycle state, and anything not `Approved`
is visibly marked:

```
⚠ PROPOSED — not yet approved
Given the user is Locked Out
When  an administrator unlocks the account
Then  they are Logged Out

⛔ DISPUTED — sources disagree; see finding F-114
```

**SP-5.** This is the single most important rule in this section. A generated
document carries the authority of a specification. Presenting a quarantined
extraction as settled behaviour would launder an unreviewed machine guess into an
apparent decision.

### 18.4 Living page and dated export

**SP-6.** Two outputs from one content assembly:

| Output | Behaviour |
|---|---|
| **Living page** | Always current. Regenerated on every model change. The reference |
| **Dated export** | Frozen on generation. For sign-off, circulation and audit |

**SP-7.** A dated export records the **model version and commit** it was generated
from, so it is reproducible and its staleness is measurable.

**SP-8.** An export is **never silently updated** — staleness is its purpose
(§7.6's principle, applied to documents). The living page is where current truth
lives.

**SP-9.** Where an export's model version is no longer current, that fact is
retrievable: *"generated from v3; the model is now v7"*.

---

## 19. Acceptance criteria for §§16–18

| # | Criterion |
|---|---|
| **A-52** | Every override records author, timestamp, previous value, new value, rationale and classification (E-2) |
| **A-53** | An override is classified `extraction_error` or `intended_divergence`, and the two produce findings against different targets (E-4, E-5) |
| **A-54** | An override **survives** re-extraction and is never silently overwritten (E-7) |
| **A-55** | When the underlying machine value changes, the override is flagged **stale**, not auto-resolved — even when the code now agrees with it (E-8, E-9) |
| **A-56** | An edit returns the element to `Quarantine` and cannot be approved by its own author (E-11, E-12) |
| **A-57** | Editing a member of a `(state, trigger)` group revalidates the group (E-13) |
| **A-58** | Override density is reported on the model view and in the generated specification (E-10) |
| **A-59** | A generated specification marks every non-`Approved` rule visibly and never presents it as agreed behaviour (SP-4, SP-5) |
| **A-60** | Every statement in a generated specification traces to a model element; nothing is added for readability (SP-2) |
| **A-61** | A dated export records its model version and commit, and is never silently updated (SP-7, SP-8) |
| **A-62** | An export generated from a superseded version can report that it is stale (SP-9) |

---

## 20. Implementation readiness

### 20.1 Readiness — where each gap stands

**The design was complete before the implementation plan was.** These are
different things, and conflating them is how a build starts on assumptions.
That was written before the build; the build has since happened, and this
register records what closed it.

**Design-complete:** 19 sections, 70 acceptance criteria, all 13 requirements
traced, every deferral given a named trigger.

| # | Gap | Status |
|---|---|---|
| ~~RD-1~~ | ~~The extraction engine is not named~~ | **✅ Closed** — Joern pinned (X-1a) |
| ~~RD-2~~ | ~~No schema DDL — no constraint or index script~~ | **✅ Closed** — `metis_mcp/ontology/schema.py` generates `schema/metis2-*.cypher` from `labels.py`, Community and Enterprise. The generator cites RD-2 |
| ~~RD-3~~ | ~~No module layout for the new code~~ | **✅ Closed** — thirteen packages under `metis_mcp/`, plus `code_analysis/` |
| **RD-17** | **Cypher is embedded in application logic, not behind a repository.** PLT-006 states the rule; the code does not meet it | **Open.** Measured: 81 queries across 19 modules — `mbt/graph_loader.py` 19, `mbt/finding_writer.py`/`mbt/graph_writer.py`/`model_sources/landing.py` 9 each. The connection half already holds (`mbt/graph_session.py` is the one seam, PLT-002). Consequence while open: a query naming a renamed label returns nothing and reads as an empty database, and nothing checks for it outside `test_ontology.py`'s Cypher scan |
| **RD-4** | **No work breakdown.** N-16 gives an order, not tasks or sequencing within stages | **Open.** The only artefact was `PLAN.md`, deleted with the rest of the v1 material and never audited. Least consequential of the seven: the order N-16 gives has proved sufficient |
| ~~RD-5~~ | ~~No test strategy for the new system~~ | **✅ Closed** — a suite that runs with no external dependency, in seconds, on any machine; §13's criteria each have an executing test. `metis-server/test_*.py` |
| ~~RD-6~~ | ~~Framework configuration schemas (X-4, X-10b) sketched, not specified~~ | **✅ Closed** — `code_analysis/framework_config.py`, the `frameworks` CLI verb, `test_framework_config.py` |
| ~~RD-7~~ | ~~Review UI specified by obligation, not design~~ | **✅ Closed** — `metis_mcp/review_ui/{server,view,evidence}.py`; a screen that cannot show its evidence blocks the decision (N-3) |

Six of the original seven are closed; RD-4 stays open and RD-17 joins it.
**This register used to appear twice** — here and again at §20.7 — and the two
copies disagreed about RD-3, one listing it open and the other closed. There is
one register, and it is this one.
### 20.2 The migration itself — completed

The plan that took Métis from the v1 engine to this one (the line-by-line reuse
audit, RD-8's "not an incremental change", RD-9's re-ingest-don't-migrate, and
RD-10…RD-16's Phase A/B/C cutover) **completed at commit `61814dc`**. The plan
document was kept for a while and has since been deleted; `git show 61814dc` is
where that history now lives.

It is out of this document because a finished plan in a specification reads as
an instruction. Its content had also gone stale in a way that matters: it
targets twelve labels where the ontology settled at forty-five, and it places
modules beside files the rebuild deleted.

What it produced is the tree described by §§1–19: the MBT engine, the four model
sources, the closed ontology and its generated schema, the review UI, and the
read-only agent surface — each of which was `Existing LOC: 0` when the plan was
written.

## 21. How much the plan depends on Joern

Recorded so this is not re-derived under schedule pressure.

### 21.1 Footprint, measured

| Measure | Value |
|---|---|
| §5 (extraction) | 221 lines of 2,580 — **8.6%** of the specification |
| Rules requiring code extraction | 32 (23 `X-`, 9 `GD-`) |
| Acceptance criteria touching extraction, anchors or dimensions | **20 of 70** (~29%) |

**Effort is understated by these figures.** §5 is plausibly the **largest single
work package** — CPG sidecar, versioned query packs with fixture tests, the naming
cascade, precedence recovery, per-framework configuration, the pilot gate — and it
carries the most technical risk (unsound analysis, framework variance, the naming
trap X-11).

### 21.2 The chain is source-agnostic by construction

**J-1.** Joern is **one of three interchangeable model sources** (S-2), not a
foundation. F-29 states it directly: the MBT engine never knows which source
produced a model.

Unaffected by the absence of code extraction — **identical behaviour**:

§2 model semantics · §3 flow · §6 MBT engine and path generation · §7 rendering
and publishing · §8 data model · §9 interfaces · §14 identity, deduplication and
incremental update · §17 editing · §18 stakeholder specification.

### 21.3 What genuinely requires it

| Capability | Without a code source |
|---|---|
| **R4, R6** | Not delivered — these requirements *are* code extraction |
| **Code-vs-intent divergence (R5)** | Lost. Only intent-vs-intent comparison remains (authored vs AC-mined), which catches design-vs-requirement mismatches but **not implementation defects** |
| Regression detection across commits | Lost |
| "Behaviour nobody specified" (the DQ-024 question) | Unfalsifiable again |
| Guard-dimension precedence (GD-1…9) | Must be **declared by hand** rather than recovered |
| Incremental update **from code** (R13) | Only from edits |

**J-2.** §4.1 already established that code-derived tests are circular — their
worth comes from comparison against intent. **Nothing except a code source
supplies the "what the implementation actually does" side of that comparison.**
That is precisely what Joern is for, and why it is not substitutable by a second
intent source.

### 21.4 Decision, and the fallback if it is ever needed

**J-3 — decision: unchanged.** Joern stays as specified, third in N-16's build
order. The MBT engine is proven against a hand-authored model first, so extraction
risk is taken only after the chain around it works.

**J-4 — the fallback exists and is documented.** If extraction proves
unworkable during Phase B, the chain still functions on authored and AC-mined
models. Removing code extraction costs §21.3's capabilities and nothing else — no
redesign, no rework of §§6–9, §14, §17 or §18.

**J-5 — the trigger.** Consider the fallback only if §13.14's pilot gate fails on
criteria 1–5 against a real service. Recognise it as a **scope decision with named
losses** (§21.3), never as a quiet deferral — that quiet deferral is exactly what
removed R4 once already and produced a requirements-management platform instead of
model-driven testing.
