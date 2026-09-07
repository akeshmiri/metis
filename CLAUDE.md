# Métis — Project Context for Claude Code

## What this project is

Métis recovers a behaviour model from code, compares it against what somebody
said the system *should* do, and generates human-executable test cases from the
part that survives human review.

**Read `docs/metis-application-spec.md` first.** It is the authoritative
specification, and the code cites its rule ids inline (`M-18`, `S-13`, `P-16`,
`D-1`, `GD-2`, `N-8`, …). When code and this file disagree, the code and the
spec win.

**Read `README.md` second** — it indexes the tree.

## The engine was rebuilt. Ignore anything describing the old one.

Commits `61814dc` and `4701389` replaced the v1 engine (`4701389` is the Intent → Specification → Feature rebuild; its message names a count that was true when it was written and is not now). These no longer exist: the 45-label
ontology, `structural_validation.py`, `layer8_heuristics.py`,
`confidence_tiering.py`, `guardrails/`, `quality_report.py`,
`demo_data/login_example.py`, `demo_data/generate_demo_data.py`,
`uif_intake.py`, `neo4j_test_support.py`, and every `metis_*` MCP tool
(`metis_get_traceability`, `metis_check_coverage`, `metis_list_skills`, …).

`docs/historical/` held that material — the v1 ontology, the hand-written
Cypher, the completed v1→v2 migration plan, the v1 design notes and academy, and
contracts for eighteen MCP tools. **It has been deleted.** Nothing in the tree
describes the old engine any more, so a search that finds one of the names above
has found a stale reference, not a file to read. `git show 61814dc` is where that
history lives now.

**The authored half of the knowledge graph lives in `metis-server/demo_data/`
and `metis-server/demo_project/`** — models, intent, criteria, decisions and the
academy, each a file a person wrote. The database is built from them and is
disposable; `rebuild_graph.sh` reads exactly those paths. **Decisions are
committed** (`demo_data/models/*.review.json`), and a model change lands in the
same pull request as the decisions it invalidates; `review apply` refuses a
decision whose model has moved, so the two halves have to travel together. What
is *recovered* from code has no file at all on purpose — its source is the
service's own tree.

**`graph/` is a design, not that half.** Its README described four directories
(`models/`, `intent/`, `criteria/`, `reviews/`) that do not exist and three CLI
verbs that do not either (`metis payload`, `metis generate`, `metis spec-kit`),
and the one file it holds — `fixtures.yaml` — has **no reader**: there is no
`--fixtures` flag on any verb. The fixtures *join* is real and documented in
`rendering/contract.py`; the wiring is not built. `graph/README.md` now says
that rather than describing the plan as the tree.

**`docs/` holds three things and the distinction between them is the point:**
the application spec (authoritative), `guide/` (**generated** from `labels.py`,
`intakes.json`, `stages.py` and the CLI parser — `metis guide --check` fails on
a diff, so it cannot drift), and `academy/` (**authored** reasoning, labelled as
such because it is not checkable the same way).

## Facts that decide how you work here

- **The ontology is 44 labels and it is closed.** `metis_mcp/ontology/labels.py`
  is the single source: `LABELS`, `ALLOWED_RELATIONSHIPS`, and `STAGED_OUT` (the
  deliberately-excluded labels, each with the trigger that would bring it back).
  The Cypher schema is **generated** from it. Adding a label or relationship is
  a reviewed change, not an edit (D-2).
- **A specialisation replaces its parent.** A classified transition is written
  `:ApiCall` or `:UiAction` **instead of** `:Transition`. Use
  `label_expression("Transition")` in queries and
  `landing.transition_label_for(surface)` when planning an edge into one — a
  hardcoded `:Transition` silently matches nothing.
- **Landing namespaces ids** as `{model_id}::{element_id}`
  (`landing.namespaced_id`). The bare id matches no node.
- **Execution results are ingested, and coverage did not change meaning
  (§8.7, revised).** Six labels — `TestExecution`, `TestCycle`, `Defect`,
  `Metrics`, `Logs`, `Alert` — were staged out *with the condition that would
  bring them back*, and that condition was met. They land through
  `execution_intake`, at `Quarantine`, carrying
  `provenance: observed_from_running_system`, attached to the **`TestCase`** that
  ran and never to the transition it covers. C-10 still holds: nothing there
  writes the coverage ledger, asserted structurally in
  `test_execution_intake.py`. C-11 still holds: a coverage figure answers *is
  this tested*. What is new is a second figure answering *did it pass* — a
  transition may be fully covered and currently failing, and Métis can now see
  both halves without reporting one as the other.
- **Everything lands at `Quarantine`.** No source writes `Approved` (S-4).
  Generation reads only `Approved` (D-10).
- **The MCP surface is read-only by default, and by construction when it is**
  (N-8, revised). `METIS_MCP_WRITE` is `off` | `author` | `full`; at `off` — the
  default — the write modules are never imported, so fifty-six read-only tools
  are all that exist, five of them the authoring surface (X-6e): `call_recipe`,
  `auth_facts`, `payload_shape`, `journey_walkthrough`, `ask`. Enabling writes adds landing and the gates, each costing an
  identity, the evidence fingerprint, and a literal word. The CLI remains the
  fullest surface.
- **The engine is database-free on purpose.** Models, criteria, path generation,
  coverage and validation are pure. The whole test suite runs with no Neo4j.
- **Noise is dropped from intake on provable inertness, never on visibility or
  reachability (X-5a).** Both obvious axes are wrong and were measured: `private`
  was 59 of 389 methods on a real service and two of those were reachable from a
  handler — one guarding an endpoint and raising the cause of a 400 — so it
  deletes a rejection path and leaves all 166 accessors. Call-reachability drops
  a service implementation's 31 business methods, because the frontend does not
  resolve interface dispatch. **Fields are never filtered**: they are private by
  convention and carry `@Schema`, required-ness and validation bounds, and
  `mapper` builds its type registry from them. What may go is jointly inert —
  matching field, short body, no control structure, no call but operators — so a
  getter that branches survives. The count dropped is always reported.
- **Contact with the System Under Test is a tier, and `off` is the default
  (X-7a, revised).** X-7a said Métis never touches the system it models. That
  prohibition is lifted by an explicit product decision; what it protected is
  not. `METIS_EXECUTE` is `off` | `observe` | `run`, enforced in one place
  (`metis_mcp/execution.py`) the way `policy.py` enforces writes. At `off` —
  the default — `observers/` and `runners/` are **never imported**, so the old
  guarantee still holds by construction for any deployment that did not ask,
  and `test_execution.py` proves it in a subprocess. `observe` reads a live
  system (SQL, cluster logs); `run` also makes something happen (load) and costs
  the literal `execute` in the call. The clients are **optional extras**
  (`metis[execute]`, `metis[load]`), which is what keeps a default install
  dependency-light and the engine-free suite database-free.

  **The rule the tiers exist to keep**: a fact observed from a running system is
  labelled `observed_from_running_system` and never merged with one recovered
  from source. They are different claims, and §8.7 stages out the execution
  labels precisely because merging them turns coverage into correctness (C-11).
  `execution.describe()` reports the tier, what is installed, and what is not.
  `connectors/intakes.json` still declares every *intake*; `intakes.describe()`
  is still the capability map for those and still lists what does not work.
- **Four rules that were prose are now computed, and each says what it does
  not check.** They were carried over from the sibling project as knowledge
  files a model was asked to apply, and the placement rule
  (`docs/academy/10-where-a-thing-belongs.md`: *could a unit test assert its
  output?*) says a checkable rule is a tool. `check_ears` exposes
  `ears_checker.check_ears_conformance` — already pure, already tested, already
  deciding `Requirement` vs `Finding`, and previously reachable from nowhere, so
  the answer arrived at landing time. `ac_quality` checks an authored criterion
  for unmeasurable qualifiers and non-atomicity; it is **advisory and blocks
  nothing** (S-4), and two of the sibling's rules deliberately did not cross
  because a Métis criterion *is* a Given/When/Then sentence and they would have
  flagged every criterion Métis drafts. `validate_intake` opens the UIF schema
  the intake skill has always pointed producers at and nothing ever read.

  **Opening it found Métis disagreeing with itself, and that is now closed.**
  `tracker.to_uif` — Métis's own producer — wrote documents that failed the
  schema Métis publishes for external producers, four ways, and the landing
  fixture failed it five. Nothing could see it because nothing validated between
  `intake fetch` and `intake land`. The schema was made authoritative and the
  producer changed to match; every departure was a producer defect rather than a
  contract that was too strict.
  `test_intakes.test_the_landing_path_and_the_declared_schema_now_agree` and
  `..._metis_own_producer_satisfies_the_schema_it_publishes` assert the agreement
  from both sides. The test that used to assert the *divergence* is gone, which
  is what it was written to do.
  `duplicate_check` computes the four-verdict guard in
  `plugins/metis/skills/shared/knowledge/duplicate-guard.md`, where `unknown`
  blocks; it rides at the author tier with `publication_drift` because
  `PublicationLedger` is in a `WRITE_PATH`. The prose files stay: they say *why*
  the rules hold, which is the half that is not computable.

- **A risk assessment declares what Métis gathered and what it must ask, and an
  unanswered required input makes it `incomplete` rather than clean.**
  `risk/inputs.py` holds both halves: `gathered` inputs name the tool that
  supplies them, `asked` inputs carry the exact question, and every input states
  what its absence means — asserted never to read as reassurance. It is
  `depth_consulted` one domain over. `requirement_risk` and `release_risk` gather
  their half and report the rest as open questions; `release_risk` **consumes**
  `coverage_report` and never recomputes a readiness figure. The output is a
  Markdown document people and agents edit, and `risk/document.merge` preserves
  `probability`, `owner`, `response`, `status`, `notes` and any hand-added row
  across a regeneration (SP-1's rule, one domain over). The `risk-review`
  workflow halts at `risk-acceptance` so a person owns the ratings.
  `risk/areas.py` maps the reference's twelve areas to the skills that own them,
  and `test_risk.py` asserts both directions.

- **Risk management is a generic toolkit with one optional wire into the model.**
  `metis_mcp/risk/` is pure: exposure on the 5x5, EMV, PERT, the RBS taxonomy and
  the register's coherence rules, none of which need a graph. Only
  `risk.candidates` reads what Métis recovered, and only through
  `change_review.findings_for`. **The rule that makes the mix safe**: every risk
  carries `derived_from: authored | model` and the two are never merged in a
  total, an average or a chart. A model-derived risk says *this behaviour is
  untested*; it does not say *this is likely to fail*, and it carries
  `probability: null` until a person sets one. Merging them is C-11 one domain
  over. `Risk` is deliberately **not** a label — see
  `docs/academy/PROPOSAL-risk-in-the-graph.md` for the argument and the condition
  that would reverse it.

- **A claim that changes is a new node; an element that changes is the same
  node, modified.** The two halves of the graph have different identity rules
  and the difference is load-bearing. A `Transition` persists across a guard
  edit — its natural key is its meaning — so `identity.carry_human_facts`
  revokes approval explicitly (I-17/I-18). A `Requirement` does not: *shall
  reject* and *shall refresh* are two claims, not one with a changed attribute,
  so `identity.claim_id` puts a digest of the text in the id
  (`REQ-3@6baff72b`) and the new wording lands at `Quarantine` because it is
  **new**. `landing.plan_supersession` closes the previous window through
  `landing.invalidate`. `revision` is stamped from the graph, not the plan —
  every writer hardcodes `1` because a plan builder cannot know the history.
  Applies to the four `VALIDITY_LABELS` only. Existing graphs re-ingest rather
  than migrate; a pre-digest id still reads as its own logical key, so it is
  readable but cannot be superseded.

- **A fact serves the model or it is not landed (X-6d), and a field is a
  property of its type (X-6d), not a node.** `Field` is staged out; a scalar is
  `f_<name>_*` on its `Class` and a complex one is a `Class-[:OF_TYPE]->Class`
  edge. `ontology.facts` holds the encoder and the decoder together so the flat
  form and the nested document cannot drift.
- **What is generated states the accepted space, never a value (X-6e).** A curl
  carries `<string, length 3..40, required>`; a base URL renders as `{base}` with
  its reason; a UI element with no authored selector raises rather than guessing.
  `ask` composes the read tools and may say nothing they did not — a fluent wrong
  answer about how auth works is the worst thing this system can produce.
- **Tests use `demo_project/`, never a real project.** It is a Records service
  written to be *extracted*: Spring source, a deviating OpenAPI document,
  hand-written criteria, a React app and a DOM page. Every file is a condition
  asserted in `test_extraction.py`, which is the only behavioural test the five
  query packs have — before it they were checked by grepping the Scala.
  `demo_project/README.md` says what each condition proves. **When a real project
  exposes a defect, reproduce the condition there first, then fix it**; a fix with
  no condition behind it is a fix nothing defends. No company or customer name may
  appear in a test, a fixture, or a `pack.yaml` claim.

## Where a thing belongs

**Read `docs/academy/10-where-a-thing-belongs.md` before adding a tool, a skill,
an agent or a knowledge file.** It is the placement rule, and it exists because
the sibling project this was ported from has a written convention for its skills
and none for its agents: the skill layer is healthy and **eight of its eleven
agents carry unresolved merge-conflict markers**. The layer with a rule survived.

The short form:

- **MCP tool** — could a unit test assert its output?
- **skill** — does it tell a model what to do where the answer is not determinate?
- **`knowledge/`** — is it a decision we made, with the reason? (generated from
  module docstrings; `metis guide --check` fails on a diff)
- **`references/`** — would it still be true if Métis were deleted?
- **agent** — does it change what is permitted, or which skill runs?

**The folder tree is a context budget, not an ontology.** `SKILL.md` is paid for
every time; `steps/` one at a time; `knowledge/` only when a step cites it. And
for anything shared: one consumer → skill-local, two or more → `shared/`, zero →
flag it rather than move it.

**A skill declares its own scope** in frontmatter — `workflow:` (the one it
drives, or omitted) and `allowed-tools:`. The agents are generated from those, so
scoping a skill is editing one file, and `test_agents.py` asserts no two agents
end up identical.

## Working style — this is the part that matters

The demonstrated pattern here is: **claims get checked by running them, and when
a check finds a bug it gets fixed and disclosed, not smoothed over.** Real
examples, all found by running the thing rather than reading it:

- The `coverage` MCP tool read `r.covered` and `r.how`; `LedgerRow` has never had
  either. It raised `AttributeError` for any model with rows, and no test caught
  it because none called it.
- A `VALIDATES` edge planned against `:Transition` passed the ontology check —
  `is_allowed` walks the specialisation chain — and then merged nothing, because
  the node carries `:ApiCall`. `land` reports that as `unmatched`; it does not
  fail. Both stages "landed", the counts looked plausible, the chain was broken.
- `plugins/metis/agents/` held four agents for deleted skills naming twelve
  nonexistent tools, each carrying a "GENERATED — do not hand-edit" banner while
  no generator had written there in a long time.

So: build it, run it, and check a **specific, verifiable output**. Not "it
imports". Not "the tests pass" when no test covers the path you changed.

Two habits that follow from this:

- **A silent success is the failure mode to hunt for.** Counts that come from
  `len(rows)` rather than the database, an `OPTIONAL MATCH` that always returns
  null, a table generated by nothing. Prefer a check that can fail.
- **Report what actually happened.** If a stage was skipped, say so. If a figure
  omits something the spec requires, say that instead of printing the figure.

## Environment

```bash
cd metis-server
uv venv                        # uv is installed; use it, not python3 -m venv
uv pip install -e ".[test]"    # the extra is what brings pytest
uv run python -m pytest -q     # No service, no network -- but a subset needs
                               # Joern 4.0.604
                               # and a JDK, and conftest.py FAILS rather than
                               # skips without them (deliberately: it is the
                               # only behavioural test the five query packs
                               # have). Without Joern installed those error
                               # rather than skip, and the rest still pass.
                               #
                               # No counts here on purpose: they are derivable
                               # (`pytest --collect-only -q`) and drifted four
                               # times in one session. What is NOT derivable is
                               # below -- the prerequisites and the ignore list.
                               #
                               # Two macOS prerequisites, both now DIAGNOSED by
                               # `metis doctor` rather than left to be guessed:
                               # GNU coreutils (`brew install coreutils`, for the
                               # `greadlink` Joern's launcher shells out to), and
                               # a symlink because 4.0.604's macOS-arm build
                               # ships `astgen-macos-arm` while jssrc2cpg asks
                               # for `astgen-macos`. Run `metis doctor` first; it
                               # prints the exact repair for each.

# The engine-free half, which is what you can run with no Joern:
uv run python -m pytest -q --ignore=test_extraction.py --ignore=test_recipe.py \
    --ignore=test_connectivity.py      # 0 errors, no Joern needed
```

CI runs these as two jobs on the same triggers — `test` (engine-free) and
`extraction` (installs a pinned Joern and runs exactly those three files).
Until 2026-08-24 no CI step installed Joern at all, so every run errored in 89
tests; if you add another engine-dependent file, name it in **both** jobs.

**Naming them in both jobs is necessary and was not sufficient.** Both lists
carried `test_data_layer.py` and `test_data_cli.py` long after the rebuild
deleted them — silently ignored in the engine-free job, and a hard `exit 4` in
the extraction one, which therefore ran **nothing** while the fast job stayed
green. `test_structure.py::test_every_test_file_runs_in_exactly_one_ci_job`
reads `ci.yml` and asserts the two lists partition `test_*.py` exactly, so a
name that stops matching a file fails a test rather than a job.

The CLI is `metis` (`metis doctor`, `metis guide --check`, …). It is a console
script now; before 2026-08-24 only `metis-mcp-server` was declared and the CLI
was reachable only as `python -m metis_mcp.mbt.cli`, while error messages told
people to run `metis doctor`.

A live Neo4j (`metis-graph`) may be running locally. **It holds real work —
treat it as read-only** unless the user asks otherwise; use a disposable
container for anything that writes.

`METIS_NEO4J_PASSWORD` comes from the environment and never from an argument
(PLT-005, now defined in spec §11.0 along with PLT-002 and PLT-003).

**Four runtime dependencies**, still: `mcp`, `neo4j`, `PyYAML`, `fastapi`. The
SUT-contact clients (`psycopg2`, `kubernetes`, `locust`) are optional extras and
a default install has none of them — `execution.REQUIREMENTS` names each one so
a refusal says which extra is missing rather than surfacing an ImportError three
frames down. The fourth
is newer and smaller than it looks — `mcp` already brings starlette, pydantic
and uvicorn, so FastAPI's whole substantive tree was installed before the HTTP
surface existed. No embedding provider is bundled: semantic search is a Protocol
with no implementation, and a default install loads no model.

- **Test design is a discipline now, and its shape is data rather than prose.**
  `metis_mcp/design/` is pure: `inputs.py` is the gather-or-ask ledger,
  `sections.py` is the template registry, `builders.py` computes rows from what
  `mbt/techniques.py`, `mbt/design.py`, `mbt/test_levels.py`, `viability.py`,
  `rendering/contract.py` and `risk/prioritisation.py` already knew, and
  `document.py` renders and merges. Nine sections in six groups, carried by a parent and seven specialists.
  **The template is served by `design_sections()` and never restated in a
  `SKILL.md`** — a template a model imitates is imitated differently every run,
  and `test_design_areas.py` fails a skill that reproduces a section's columns.

  **Every closed vocabulary is imported from the module that owns it**: the six
  test levels, the three existing-coverage grades, the viability and performance
  verdicts, the four risk bands. A second copy is how a design starts reporting
  a level the coverage ledger has never heard of.

  **The risk wiring is four wires, each checkable.** Rows are ordered by
  `risk.prioritisation.order` — the same keys the `prioritise` stage applies to
  generated paths, asserted equal in `test_design_sections.py`, so a design and
  the batch built from it cannot disagree about what matters first. A band is
  `derived_from: model`, and **no design table has a probability column** —
  `test_no_section_carries_a_probability` forbids one. Depth warranted against
  depth achievable becomes an open question with an owner rather than a figure.
  The rating itself routes to `metis-risk-manager-product-risk`.

  **Architecture and the design specification are `asked`, not gathered.** Métis
  could describe an architecture by summarising what it recovered, and that
  description would be the implementation restated as its own intent — S-19 in a
  new place. So both are questions, seven asked inputs are required, and the
  design reports `incomplete` with that word above the first section rather than
  below the last. A section built without some of its inputs is marked
  **partial**: a table with content in it, resting on inputs nobody supplied, is
  the dangerous case, because an empty section at least announces itself.

- **An endpoint's shape obliges negative behaviour, and `unmet` is a question.**
  The `obligations` section derives four obligations from recovered facts — a
  path parameter, a declared security requirement, a body, an enumerated input —
  and judges each against the statuses the endpoint was **seen to produce**. The
  sibling project asserts these scenarios outright with the status hardcoded;
  Métis reports the recovered set instead, because "produces 200, 204 and 400,
  and no 404" is answerable and "missing 404" is not. Across the four Athena
  journeys that found 17 endpoints with a path parameter and no not-found.

- **A risk band hides which factor drove it, and `profile` is what it hides.**
  `product.technical_profile` returns the individual factors deliberately and
  argues why in its own docstring — and nothing read them, so the only available
  response was "test this more". Each factor now carries the response it asks
  for, and an unmeasured one is a **row saying so** rather than a blank: a blank
  among counts reads as zero, and zero reads as simple.

- **A design section is a table or a diagram, and the mode is declared.**
  `machine` renders the state machine in scope as mermaid — the only picture
  Métis draws, and it draws only what it recovered: no actors, because an actor
  is an `asked` input. A diagram has no columns, so `merge` carries nothing and
  `verify` checks only its heading; the section says in its own output that an
  annotation added to it is lost on the next run. Above forty transitions it is
  omitted **whole** with the count stated, because a part-drawn machine looks
  complete (P-3b).

- **The condition inventory is computed, and two of its eight classes are
  honestly undrawn.** `shared/knowledge/requirement-condition-coverage.md` was
  prose a model was asked to apply; the `conditions` section applies it. Every
  behaviour gets a row for all eight classes — including the ones that do not
  apply, **with a reason**, because a class that silently disappears is the
  failure the rule exists to prevent. Six are reached from recovered facts;
  `dependency-failure` and `non-goal` come back `clarify` and say why. `proposed`
  is Métis's reading and `decision` is a person's, and an absent authorisation
  check is `clarify` rather than `not-applicable` — declarative security is all
  extraction sees, so that is "nobody looked", never "open".

- **Setup cost comes from the setup chain, and `shortest_setup` is parameterised
  rather than duplicated.** `Path.setup_transition_ids` is the chain a test must
  establish, so the cost band is computed from it and from the HTTP verb — and
  the verb yields `unknown` rather than `read-only` where there is none, because
  calling a UI credential submission a read would hand it the cheapest band.
  The **setup pattern is a human column**: whether reuse is safe depends on
  stable data and cleanup ownership, both `asked`.

  `generatable_only=False` is what the design passes. Reaching a state is a
  property of the machine; whether the route may be generated *from* is D-10 and
  binds only generation. Calling `generate` here emptied the section for every
  real model — everything excluded as `excluded_unapproved` — while the
  `empty_means` blamed reachability, which is the wrong reason reported
  confidently.

- **The guard-dimension chain is reachable now, and three silent defects were
  why it was not.** `mbt/dimensions.py` implements the GD-1..GD-9 reduction and
  had no caller outside its own tests. The evidence edges to `DeclaredOutcome`
  and `Check` were planned by the model plan and landed before their target
  nodes existed, so `land` reported them `unmatched` and moved on —
  **0 of 176 transitions carried a check** on a real estate while 47 `Check`
  nodes sat in the same graph. `GuardCheck` then had no `id`, which is what
  `build_chain` reads. And the loader selected `c.anchor`, a property no `Check`
  has, so every anchor was empty — which matters beyond display, because GD-8
  gates equivalence-class credit on an **identical** anchor and unrelated checks
  all reading `""` would be credited as one behaviour.

  `_plan_outcome_edges` is the second pass the two deferred labels lacked, and
  `test_every_evidence_label_written_by_the_raw_layer_has_a_second_pass` guards
  the class rather than the instance: a sixth evidence label added without a
  second pass fails a test instead of silently never landing. **An existing
  graph does not gain any of this until it is re-extracted.**

- **A test design is a Markdown document and `TestDesign` stays staged out.**
  The label's recorded trigger was "a concrete need appears" and the need has
  appeared, so `docs/academy/PROPOSAL-test-design-in-the-graph.md` answers it
  rather than leaving the question open: a node whose seven defining fields are
  unanswered is a form, not a fact, and nothing would read it yet. The proposal
  names four conditions that would reverse it and says which is likeliest.

- **Intent is a pre-processor, and `intake` no longer lands before it reads.**
  The workflow ran fetch → validate → land → assess risk, so the first moment
  anybody saw what was wrong with a claim was after it was a node. `analysis`
  and `readiness` now sit **before** `land`. `metis_mcp/analysis/` composes four
  readings that each see a hole the other three cannot — intent (is there a need,
  did anybody say how it behaves), requirement (can two people satisfy the
  wording), design (could anything ever test it), risk (what does being wrong
  cost) — and every gap names the aspect that found it and what closes it.

  **`readiness` is a blocking stage and deliberately not a gate.** §3.4 keeps one
  halt per workflow so each halt has one meaning, and this is not a halt: there
  is no literal that passes it, because a need nobody has specified is fixed by
  specifying it. That makes it F-9's contract — a stage that fails, names what
  failed, and states the action required.

  **The refusal is narrow, and both sides are asserted.** `not-ready` means the
  claim cannot be *represented* (D-1). A claim nobody has costed, whose
  environments are unlisted and which has no criteria yet, is `ready` and lands
  carrying every one of those gaps — refusing it would mean Métis only accepted
  claims that were already finished. **Every validator problem blocks**, because
  `cmd_intent_land` refuses the file over any of them: one definition rather than
  two, and the first version kept two and got it wrong.

  Three of the four readings are owned outside the business-analyst family
  (`metis-knowledge-capture`, `metis-test-design`,
  `metis-risk-manager-requirement-risk`) and `analysis/areas.py` records the
  hand-off so a test can check it.

- **One merge implementation, three documents.** `metis_mcp/document_table.py`
  holds cells, scoped section reads, positional row parsing and the merge that
  preserves human columns and hand-added rows. `risk/document.py` was the
  original and now sits on it; `design/document.py` and `analysis/document.py`
  are the other two callers. `test_risk.py` is the regression guard on the
  extraction. Row ids are **content-derived** in all three, so a decision follows
  the condition it was made about rather than the position that condition
  happened to occupy — an id that counted rows off would move every recorded
  decision one row down the moment something was added.

## Things that are genuinely open

- **Publication has a live transport, and dry-run is the default.** This entry
  said "dry-run only" and was wrong in the dangerous direction — it told a reader
  Métis cannot write to their tracker when it can. `publishing.TRANSPORTS`
  registers `dry-run` and `zephyr-scale`, and both the CLI (`mbt/cli.py`) and the
  `test-generate` workflow (`workflow/handlers.py`) select the live one on
  `--transport zephyr-scale`. **Two keys are required**: the G2 literal in that
  run, plus `METIS_ALLOW_EXTERNAL_WRITES=yes` on the installation — the first can
  come from whatever drives the run, including an agent, and the second cannot.
  Without the flag you still get a dry run that builds and validates a real
  payload and sends nothing.
- **No `Component` nodes exist until `persist` runs, so a coverage figure has no
  VERSION until something has been generated.** That half is correct and stays:
  a `Component` means "what was generated and published", it requires a
  `version`, and landing has none — inventing one would put a fiction where
  P-16 wants a fact.
  **The commit half was an omission and is fixed.** Landing knows the commit,
  and it was reachable only by splitting the Episode's joined `evidence` string
  — which the comment beside `proposed_by` says not to depend on. It is its own
  `Episode.commit` property now, and `coverage` / `coverage_report` report it
  labelled by where it came from: an extraction commit is a weaker claim than
  one a published version was cut from, and merging them would overstate the
  second. `graph_smoke.py` asserts a code episode always records one.
- **Intake creates a Requirement only from EARS-conformant text.** `intake land`
  carries a UIF into the graph as an `Episode` plus a `<Source>Item` anchor.
  Free prose — most Jira titles — lands as a `Finding` pointing at
  `knowledge-capture` instead, because `ears_pattern` has no empty form and
  guessing one is what `ac_mining` refuses to do (S-13). A UIF's *claimed*
  acceptance criteria are never trusted into `AcceptanceCriterion` nodes.
- **The academy lands, and `rebuild_graph.sh` lands it by default.**
  `docs/academy/` is nineteen authored lessons on three tracks — operator
  (12-17, 19; assumes no programming), concepts (01-08) and contributor
  (09-11, 18);
  the numbers are stable identifiers, not a reading order, because a lesson's
  number is its natural key in the graph. `Lesson` is a real label with a
  writer (`model_sources/lessons.py`) and a CLI verb (`metis lessons`), so the
  ontology change this entry used to call for has been made — `knowledge` still
  lands `BusinessArea`/`BusinessEntity`/`Intent` and a lesson is still none of
  those, which is why `Lesson` is its own label rather than a fourth one there.
  Stage 4b of the rebuild lands them at `Quarantine` like every other source.

  **They land in the same graph as the product facts, on purpose.** The intent
  is that `ask` answers a question about Métis the way it answers one about a
  product, and Neo4j cannot join across databases in one session — so a separate
  academy database would put the lessons somewhere `search_knowledge` could
  never see them beside a criterion. Separation is by label and by episode. What
  `ask` reaches them: a question naming this system rather than a product is
  answered from the academy, with the topics it belongs to and what to read
  next. `retrieval-bench --land` turns a ranking miss into an advisory
  `Finding`, so a lesson that reads badly through `ask` becomes a finding about
  the tools — the loop this was for, closed.

  **Lessons are linked, not isolated.** `Topic` is a shared node many documents
  point at (`Lesson-[:BELONGS_TO]->Topic`), so "what else covers this" is a
  traversal rather than a second search. A topic is read from the document's own
  frontmatter and **never inferred** — a title is not a topic.
- **Component-level vs system-level acceptance criteria** — an OpenAPI document
  gives the component level mechanically; the system level needs the
  preconditions that produce a given set of parameters, and those are not
  derivable from a contract. Not designed yet.
- **The review UI authenticates its decisions and not its reads.** It used to
  trust `X-Metis-User` outright, which defeated N-10, the role table and the
  audit record together. `_identity` now resolves the actor through
  `api/auth.py` — one credential store, two transports — and a browser signs in
  at `/login` for a session cookie. **Reads stay open on the bound interface**:
  requiring a token on page navigation would make the UI unusable, so widening
  `--host` is still a disclosure decision even though decisions are gated.
  Two of the six decisions are rendered pages (approve, name-a-state); the other
  four are JSON only, because each is *about* an item the review context does
  not hold and a page cannot draw one nobody supplied.
