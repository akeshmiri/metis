# Changelog

## 0.1.0 — unreleased

The first release. The engine was rebuilt from scratch for it. Anything
describing the previous one has been **deleted** rather than archived —
`docs/historical/` no longer exists, so a search that finds one of the v1 names
has found a stale reference and not a file to read. `git show 61814dc` is where
that history lives.

### Deployment

- **The Helm chart could not start a working pod, for four independent reasons,
  while rendering cleanly and passing `helm lint`.** Each was sufficient on its
  own, and none was visible without running the thing:

  | Defect | Effect |
  |---|---|
  | `MCP_TRANSPORT` set; `METIS_MCP_TRANSPORT` is what is read | the container ran `stdio` — waiting on a stdin nobody was attached to, while publishing a port nothing listened on. `server.main()` documents that exact failure as fixed; the fix could not reach a deployment through the wrong variable name |
  | `METIS_HTTP_HOST` never set | bound `127.0.0.1`, which inside a pod means the pod. The Service reached nothing |
  | liveness probe on `/healthz` | that endpoint is on the HTTP API. `metis-mcp-server` serves `/mcp` and 404s `/healthz` — verified by running the entrypoint — so every pod failed its probe and Kubernetes restarted it in a loop |
  | literal password in a secret volume | Kubernetes mounts one 0644 and `graph_session._password_from_file` refuses a literal secret in a file readable beyond its owner, so the chart could not authenticate at all |

  **Fourteen of the sixteen environment variables it set had no reader**: the
  four `OAUTH_*`, the five `METIS_SOURCE_DB_*` (the database layer was staged
  out in the 2026-08-31 re-baseline), `ANTHROPIC_API_KEY`, `METIS_LOG_LEVEL`,
  `LOG_LEVEL`, `NEO4J_URI`, `NEO4J_PASSWORD`. A variable nothing reads looks
  exactly like one something reads, which is how `MCP_TRANSPORT` sat beside the
  name that works.

  Conversely the switches that decide what a deployment may DO —
  `METIS_MCP_WRITE`, `METIS_EXECUTE`, `METIS_ALLOW_EXTERNAL_WRITES` — were set
  nowhere, so every deployment took the default silently. They are stated
  explicitly now: `off` should be a choice visible in the values file, not an
  accident of omission.

  The mounted config names the password variable (`password_env`) rather than
  carrying it, the secret volume mounts `0400`, `values-sbx.yaml` no longer
  configures two components that do not exist, and `files/metis-config.yaml` —
  which no template mounted — is deleted.

  `test_structure.py` asserts the chart configures nothing without a reader,
  sets the switches, keeps a literal secret out of the committed config, and
  does not probe an endpoint this process lacks. CI renders the chart on every
  push. Verified by `helm lint`, `helm template`, and by resolving the rendered
  config against the real `graph_session`; **a deploy on a real cluster is
  untested.**

### Documentation

- **The academy has an operator track.** Its eleven lessons were well written and
  written for the wrong reader: lesson 2 opens on `label_expression("Transition")`
  and lessons 9–11 are contributor documentation. A business analyst reading in
  order met a code property graph on the second page and never recovered.

  Six new lessons (12–17) assume no programming: what Métis is for, a
  plain-language glossary, four role-based first weeks, one real ticket followed
  end to end with the output the commands actually print, a walk through the six
  decision screens, and what each refusal means. The index now presents two
  tracks with the operator one first.

  **The numbers are identifiers, not a reading order.** A lesson's id is its
  filename, so renumbering would detach every lesson already landed from its own
  history — the duplicate-node failure content-derived identity exists to
  prevent. Each track carries its own order in the index instead.

  `topic: operator` makes "show me the operator material" one traversal, and the
  retrieval benchmark grew from 43 questions to 72 so the new track's
  findability is measured rather than assumed. Three new guards check the
  benchmark itself: every expected answer names a lesson that exists, every
  lesson is covered by at least one question, and no question is duplicated. The
  second of those immediately found two lessons whose findability had never been
  measured at all.

### The engine

- **The UIF contract is settled: the schema is authoritative.** Métis's own
  producer wrote documents that failed the schema Métis publishes for external
  producers, four ways — `metadata.status` was the tracker's raw string where an
  object is required, `scope.created_at` and `scope.last_updated_at` were
  required and absent, and `scope.primary_type` carried `Story` where a
  lowercase enum is declared. Every one was a producer defect rather than a
  contract that was too strict: the timestamps are IN the tracker responses and
  the reader never asked for them, and a workflow status is a classification in
  the schema and a quotation in the tracker.

  `tracker.to_uif` now normalises. **Nothing is invented to satisfy the schema**:
  an unrecognised workflow status omits `summary_status` rather than guessing
  what somebody's `Awaiting Signoff` means, an unrecognised priority is omitted
  rather than defaulted to `medium` (a middle value claims somebody triaged it),
  and the tracker's own wording survives as an observed fact in
  `facts.current_state` with its source. `primary_type` has a floor of `task`
  because the schema requires it — `task` asserts "a unit of work" and nothing
  about what kind.

  Both divergence tests are inverted rather than deleted, so the agreement is
  asserted where the disagreement was. `metadata.priority` is the first
  requirement ATTRIBUTE the graph can carry.

- **Requirement hierarchy, without a new label.**
  `JiraItem-[:LINKS_TO]->JiraItem` was catalogued with no writer and no reader —
  the dangling reference D-1 exists to prevent. What blocked the writer was that
  the UIF had nowhere to put a link; `links` is now in the schema, and
  `tracker._links_from` fills it from `fields.parent` and `fields.issuelinks` in
  the response the reader **already fetches**. No endpoint was added, so
  `ENDPOINTS` stays the closed GET allowlist (X-7a).

  An epic and its stories are two anchors with that edge, each `REPRESENTS`ing a
  `Requirement`, so *which requirements does this epic decompose into* is a
  traversal — `read.requirement_hierarchy`, both directions. `Epic` stays staged
  out: D-1's bar is a requirement question needing it AS A NODE, and this one
  does not.

  A linked item that was never fetched is planned as a bare anchor with
  `issue_type: unknown`, so hierarchy survives a partial fetch instead of
  merging nothing. A link leaving the tracker is skipped and counted rather than
  pointed at an anchor of the wrong kind. The demo corpus carries a real epic,
  a story beneath it and a defect linked to the story.

  Provenance, not traceability: the TRACKER asserts the link and Métis records
  the assertion. A `parent` edge does not say the child requirement implements
  the parent, and nothing reads it that way.


- **Requirement intake is a workflow now, and where it reads from is
  configuration.** It was the only major path with no workflow, no gate and no
  resumable run: `intake fetch` and `intake land` existed and nothing knew their
  order, while model recovery and test generation both had full gated
  workflows — backwards for a tool whose first job is requirement management.

  `metis workflow run intake` runs fetch → validate → land → **G1**. The
  `validate` stage opens the UIF schema that the intake skill has always pointed
  producers at and which nothing ever read, and it does not block: a
  non-conformant ticket lands as a `Finding` pointing at knowledge-capture,
  which is the honest outcome for free prose (S-13), not a failure of the run.

  A project profile may now carry a `requirements` block — the system, the
  items, and either a `fixture_dir` or a `base_url`. Which tracker and which
  scope are decisions a deployment makes and changes without a release, so they
  belong beside `journeys` rather than in whatever command somebody types.
  `token_env` NAMES a variable and is refused if it looks like a token
  (PLT-005), and an unsupported system is refused when the profile is READ
  rather than when a run later tries to fetch from it.

  `metis intake land <directory>` lands every `*.uif.json` in it, each
  independently — one non-conformant ticket must not take a backlog with it.

  **Still no crawl.** There is no JQL search or space walk: `tracker.ENDPOINTS`
  remains a closed allowlist of GET paths by key, and adding a search endpoint
  is an allowlist change that needs arguing for. The configuration schema is
  ready to receive one; the capability is not built.

  **It immediately found that Métis disagrees with its own schema.** The
  documents `tracker.to_uif` writes fail the UIF schema Métis publishes, four
  ways: `metadata.status` is a string where an object is required,
  `scope.created_at` and `scope.last_updated_at` are required and absent, and
  `scope.primary_type` carries the tracker's vocabulary (`Story`, `Bug`) where a
  lowercase enum is required. Nothing saw it because nothing validated — fetch
  wrote the documents, land read them, and neither opened the contract between
  them. Pinned by `test_metis_own_producer_disagrees_with_the_schema_it_publishes`.
  **Which side is authoritative is not decided here**: normalising
  `primary_type` changes what `JiraItem.issue_type` holds in the graph, and
  making `created_at` required means a producer that cannot supply it cannot
  produce a valid UIF at all.


- **All six human decisions can now be recorded.** §9.1 names six decision
  points and `review_ui/evidence.py` built a screen for every one, each refusing
  to render without its evidence (N-4). Three of them had nowhere to put an
  answer: `metis divergence` reported and nothing accepted a resolution,
  reconciliation proposed a match and nothing accepted a confirmation, `metis
  drift` classified and nothing accepted a decision. So the spec's "Primary. All
  six decisions" was two-thirds aspiration, and the evidence layer had been
  complete for long enough to look finished.

  `review.decisions` gained `resolve_divergence`, `confirm_match` and
  `decide_drift`; `ReviewState` gained a durable record for each (bumped to
  `metis.review-state/2`, and a `/1` file still loads). Both surfaces call the
  same functions, because N-1 requires every surface to produce the same record
  and a second implementation behind the web handler is how two surfaces drift
  into disagreeing — asserted directly by
  `test_every_surface_produces_the_same_record`.

  New: `metis decide divergence|match|drift`, and six routes on the review UI.
  Each refuses for its own reason — a divergence with no rationale is rejected
  because S-10 says neither side wins automatically, so a resolution with no
  recorded reason *is* the precedence rule S-10 forbids; a drift resolution must
  name an action the publisher implements, and there is no delete (T-16); a
  match screen still blocks without `why_proposed`, because wording similarity
  alone is never sufficient evidence (X-17).

  `Screen.fingerprint()` records what evidence was actually shown (N-13/N-14).
  The approval path binds to the model fingerprint, which is right there because
  the model is the evidence; these three are about anchored sides, a criterion
  and a transition, or a three-way comparison, and needed their own anchor.


- **A requirement that changes is a new revision, not an overwrite.** This is a
  breaking change to how the four validity-carrying labels are identified.

  A `Requirement`'s id used to be derived from its evidence anchor alone, so
  re-landing an edited Jira ticket resolved to the same node: the text was
  replaced in place, `revision` was rewritten to 1, and — because
  `lifecycle_state` rides in the `ON CREATE` clause — an **Approved**
  requirement silently acquired new wording and kept its approval. It never
  reappeared in `review queue`, because `NeedReview` tracks lifecycle and
  lifecycle had not moved.

  `identity.claim_id` now splits a claim's id into a stable logical key and a
  digest of its text (`REQ-3@6baff72b`), so a changed claim is a different node.
  It lands at `Quarantine` because it is new (S-4); the previous revision keeps
  the decision a human gave it (I-19); and `landing.plan_supersession` closes
  the old validity window through `landing.invalidate` — which had been written,
  tested, and called by nothing. `revision` moved to the write-once clause and
  is stamped from the graph rather than from the plan.

  No `SUPERSEDES` edge was added. "Every version of PROJ-14" is already the
  anchor's `REPRESENTS` edges, and "the current one" is those filtered on
  `valid_to = ''`, so a new relationship would be a second representation of a
  fact the graph holds — which D-1's bar refuses.

  `metis review queue` now prints the previous wording beside the new one for a
  superseded claim, because *this changed* is not something a reviewer can act
  on without seeing what it changed from.

  **Existing graphs need a re-ingest, not a migration.** Claims landed under the
  old scheme carry no digest, and `logical_key_of` reads such an id as its own
  key so they are still readable — but they cannot be superseded, because there
  is nothing to tell an old id apart from a logical key. The database is derived
  and disposable: `metis storage export`, wipe, and re-ingest. That is RD-9's
  rule applied to its own case.


- **Behaviour recovery from code.** A Joern code property graph becomes states
  and transitions through a normalised contract — no engine type reaches the
  graph.
- **A closed ontology, and a schema generated from it.**
  `metis_mcp/ontology/labels.py` is the single source for the label set, the
  relationship catalogue, and the deliberately-excluded labels each with the
  trigger that would bring it back. The Cypher schema is generated from it, so
  the two cannot drift.
- **Two gates, and only two.** G1 before anything is generated, G2 before any
  external write. Nothing auto-approves and nothing auto-promotes on elapsed
  time. Every source lands at `Quarantine`; generation reads only `Approved`.
- **A read-only agent surface.** Nineteen MCP tools, none importing a write path
  (N-8). Landing, approval and publication go through the gated CLI.
- **Database-free by construction.** Models, criteria, path generation,
  coverage and validation are pure. The whole suite runs with no Neo4j.

### Risk management

- **A `risk-manager` skill family, and six tools under it.** Twelve areas of
  standard risk practice — the lifecycle, identification, the RBS, qualitative
  and quantitative analysis, threat and opportunity responses, the register,
  monitoring and governance — placed by the rule in
  `docs/academy/10-where-a-thing-belongs.md` rather than written as one document.

  Anything a unit test can assert became a tool: `risk_exposure`, `risk_emv`,
  `risk_pert`, `risk_categories`, `risk_register_check`, `risk_candidates`. The
  judgement became a parent skill and five specialists — `identification`,
  `qualitative`, `quantitative`, `response`, `monitoring` — split where the
  *procedure* differs rather than one per topic. What would still be true if
  Métis were deleted became four `references/` files. `knowledge/` is generated
  from the module docstrings, as everywhere else.

  **The tools refuse the input that belongs to the other scale**, which is the
  part that earns them their place: a 5×5 score is an ordinal rank and an EMV is
  a quantity. `risk_emv(3, 100000)` returns `300000` — five times too large,
  entirely plausible, and destined for a budget — so it is refused with the name
  of the tool the input belongs to. `risk_pert` refuses estimates that are out of
  order rather than sorting them.

  **A risk Métis derived from a model is never merged with one a person
  asserted.** Every row carries `derived_from`, every summary reports the split,
  and a model-derived candidate carries `probability: null` and keeps it until a
  person sets one. A model-derived risk says *this behaviour is untested*, not
  *this is likely to fail*; merging the two lets a coverage gap read as a
  forecast, which is C-11 one domain over.

  `Risk` is **not** a graph label. The argument, the case against, and the
  condition that would reverse it are in
  `docs/academy/PROPOSAL-risk-in-the-graph.md`: D-1 wants a named writer and a
  named reader, and today it has neither.

### Risk management reaches requirements and releases

- **The twelve areas of the reference are each owned by one skill, and that is a
  test rather than a claim.** `metis_mcp/risk/areas.py` maps every area to the
  skill responsible; `test_risk.py` asserts both directions, so an area whose
  skill is renamed fails, and a new specialist that claims no area fails too.
  Thirteen specialists now, under `metis-risk-manager`, and **none of them has an
  agent** — the parent's agent routes to them as skills.

- **Every assessment declares what Métis gathers and what it must ask, and an
  assessment missing a required input reports `incomplete` rather than a clean
  bill.** This is `depth_consulted` one domain over, in a more dangerous place:
  Métis can gather nine facts about a requirement and none of them is business
  criticality, so an assessment built from what is reachable looks thorough while
  missing the input that decides the answer. `risk/inputs.py` declares both
  halves — the `gathered` ones name the tool that supplies them, the `asked` ones
  carry the exact words to put to a person — and every input states what its
  absence means, asserted never to read as reassurance.

  `requirement_risk` gathers EARS conformance, criteria and their provenance,
  approval state, supersession and coverage, then reports the five it cannot
  derive. `release_risk` **consumes** `coverage_report` and the readiness ladder
  rather than recomputing them — two engines answering one question is how a
  reader ends up asking which to believe.

- **The output is a Markdown document people and agents edit, and regeneration
  never overwrites their half.** SP-1's discipline, one domain over: `probability`,
  `owner`, `response`, `status` and `notes` are preserved across a regeneration,
  and so is any row somebody added — the eleven categories Métis cannot see are
  most of a real register. Without that, the second run would silently delete
  every rating anybody set and look successful doing it.

- **A sixth… eighth workflow, `risk-review`**, with `gather` → `open-questions`
  → `assess` → **`risk-acceptance`** → `document`. `open-questions` never blocks
  because the questions are its product (F-4), and the gate exists so a person
  takes ownership of the ratings — without it the run would present the half
  Métis can see as the whole. It has **no preconditions on purpose**: a risk
  review of an unapproved model is exactly when it is most useful.

- Also: `metis risk assess requirement|release`, with `--check` for CI; six new
  MCP tools across two sessions (34 → 44); `risk_report`'s consolidated view; and
  two `references/` files for the fundamentals and the governance that would
  still be true if Métis were deleted.

### Test design, as a discipline

`metis-test-generate` renders cases from an approved model. Nothing decided what
those cases should be about, at which level, or what remained unknown — the
`test_design` tool answered two classification questions (automatable, worth
load) and the rest of the machinery existed and was reachable from nowhere:
`mbt/design.py`'s decision tables and pairwise generation were wired only as
coverage criteria, and `mbt/techniques.py`'s partitions and boundaries only
through them.

`metis_mcp/design/` assembles them into a document. Nine sections in six groups;
seven specialists and a parent; a `test-design` workflow that halts at its own
acceptance gate; `metis design` to write it and `metis design --verify` to check
an edited one.

- **The template is data, and it is served rather than restated.**
  `design_sections()` returns every group, section, column and closed
  vocabulary. A "template" written as prose in a skill is a shape a model
  imitates, and two runs imitate it differently. `test_design_areas.py` fails
  any skill that reproduces a section's column headings, which is
  `test_no_plugin_readme_hand_lists_the_tools` one layer over.
- **Every closed vocabulary is imported from the module that owns it** — the six
  test levels, the three existing-coverage grades, the viability and performance
  verdicts, the four risk bands — and a test asserts each is the same tuple. A
  second copy is how a design starts reporting a level the coverage ledger has
  never heard of.
- **Architecture and the design specification are `asked`, not gathered.** Métis
  could summarise what it recovered and call that an architecture; the summary
  would be the implementation restated as its own intent, which is S-19 in a new
  place. Seven asked inputs are required, and the design reports `incomplete`
  with that word **above** the first section.
- **A section with rows and missing inputs is marked partial.** That is the
  dangerous case — a table with content in it, resting on inputs nobody
  supplied. An empty section announces itself; this one has to be told to.
- **Risk decides the order and never the probability.** Rows follow
  `risk.prioritisation.order`, the same keys the `prioritise` stage applies to
  generated paths, and a test asserts the two orderings are equal — so a design
  and the batch built from it cannot disagree about what matters first. No
  design table has a probability column and `test_no_section_carries_a_probability`
  forbids one being added.
- **`TestDesign` stays staged out.** Its recorded trigger was "a concrete need
  appears" and the need appeared, so
  `docs/academy/PROPOSAL-test-design-in-the-graph.md` answers it: a node whose
  seven defining fields are unanswered is a form rather than a fact, and nothing
  would read it yet. Four conditions that would reverse it are named.

### §22 and §23 are agreed, and a design can now carry a picture

Both sections moved from **drafted** to **agreed** on review.

**`machine` is the fifteenth section and the only one Métis draws.** The practice
this family was compared against mandates a use-case diagram and a flow chart on
every design, drawn by hand. Métis has the machine already, so it renders what it
recovered — a `stateDiagram-v2` of the states and transitions in scope — and
draws nothing it did not. **No actors**: an actor is an `asked` input, and a
diagram inventing one would put a person on the page nobody named.

**`Section.render` is `table` or `diagram`, declared rather than inferred.** A
diagram has no columns, so the merge has nothing to preserve — and, more to the
point, nothing to lose when the section is rewritten whole. The renderer, the
merge and `verify` each read the mode instead of guessing from an empty column
list, and the section tells a reader in its own output that an annotation added
to the diagram will not survive.

**The cap is reported, never applied silently** (P-3b). Above forty transitions
the diagram is omitted **whole** and the note says how many there were: a picture
showing forty of fifty-six with no note is worse than no picture, because it
looks complete. Measured on the real estate — `athena-metric` draws, `athena-tms`
declines and says why.

Three refusals in the drawing itself: a state name is substituted into a usable
mermaid id rather than quoted and hoped for (an unparseable id breaks the whole
block, not one line); a guard containing `:`, `<` or `>` is escaped, because a
colon ends a mermaid label early; and the node order is deterministic, since P-7
reaches the picture too.

### The final review found a stale claim in the specification

**§2.2.1 said a classified transition carries `:ApiCall` "in addition to"
`:Transition`. It does not — it carries it INSTEAD.** Verified against a live
graph: the nodes are `['ApiCall', 'NeedReview']`, with no `:Transition` on them.

It was wrong in the direction that costs a reader most. `MATCH (t:Transition)`
reads as the obvious query, returns only the unclassified transitions, and fails
**silently** — a plausible count beside an empty result. `label_expression`'s own
docstring has said the opposite for as long as it has existed, and CLAUDE.md
too; the spec was the copy nobody checked.

### Academy and documentation brought up to date

- **Lesson 11's routing table was missing three whole families** — test-design,
  business-analyst and risk-manager — and still described `intake` as
  `fetch → validate → land → G1`, which stopped being true when the reading
  moved in front of the landing.
- **Lesson 05 promised "only two gates" to a reader who now meets four halting
  things.** It distinguishes them now: a gate waits for a *decision*, a
  workflow-owned halt waits for *ownership*, and a blocking stage waits for
  nothing at all because the claim itself has to change.
- **Lesson 17 gained the three refusals this work introduced** — `not-ready`,
  `incomplete`, and `unmet` — each with what it is *not*, since all three are
  easy to read as defects and none is one.
- **Lesson 06 gained the pipeline diagram**, including the two dotted lines that
  surprise people: test design runs against an *unapproved* model on purpose,
  and never feeds generation.
- **The README module tree was missing `design/`, `risk/`, `analysis/` and
  `document_table.py`.**

### Diagram checks are tests now, not something somebody remembers to run

Three, across every document under `docs/`: the declared type is one this
repository draws, the brackets and `subgraph`/`end` balance, and every labelled
edge between two ontology labels is a relationship the ontology permits. Each
has a sabotage check — a `flowhart` typo and an unclosed label both fail, and
were made to fail before being trusted.

Ten diagrams now: eight in the specification, two in the academy.

### The specification carries the new work, and gains diagrams

**§22 (Test design) and §23 (Pre-import analysis)** are written, with `TD-1…36`
and `BA-1…12`. Both prefixes were free in the spec and unused in the code, and
both are registered in `test_independence`'s prefix list beside `PLT`, `CGA` and
`ONT` — a numbered rule is ticket-shaped by the same coincidence that list
exists to disambiguate.

**Six mermaid diagrams, and a stated rule for when to draw one.** ASCII stays
for a flow that reads as a sentence — forty-three of those predate the note and
none was converted. Mermaid is for a structure ASCII cannot hold honestly: a
state machine, a graph of labels and edges, a decision with more than two
outcomes.

| Where | What it shows |
|---|---|
| §2.4a | the short-circuit chain: `1+1+9+1 = 13` against `3x2x10 = 60` |
| §3.4 | the two lettered gates, the two workflow-owned halts, and the blocking stage that is none of them |
| §8.0 | the claim chain and the evidence chain, and the transition where they meet |
| §22.4 | the fourteen design sections in six groups |
| §22.4 | the three states a section can be in, and which is the dangerous one |
| §23.1 | intake, with the reading moved in front of the landing |

**The diagrams are guarded, because the convention promises they are checkable.**
`test_every_labelled_edge_in_a_spec_diagram_is_a_real_relationship` resolves each
mermaid node id to its label and asserts every drawn relationship is one the
ontology permits — 11 edges checked. It was written after the §8.0 draft claimed
`Specification -[:IMPLEMENTS]-> ApiCall`, which is backwards: an `Endpoint`
implements a `Specification`, and that direction is the whole of §4.1's
comparison. A second guard asserts the hand-written section index and the
sections themselves agree.

### Two academy lessons

`18-designing-what-to-test` (contributor track) and
`19-before-a-claim-becomes-a-node` (operator track), with nine benchmark
questions between them — `test_the_benchmark_covers_every_lesson` refuses a
lesson whose findability is unmeasured, which is what caught them.

### Negative obligations, and the factors a band hides

**`obligations` — what an endpoint's own shape obliges it to do.** A path
parameter obliges a not-found; a declared security requirement obliges a
refusal; a body or a required query parameter obliges a rejection; an enumerated
input obliges a case per constant. Every row names the **recovered fact** that
raised it, because a route that merely looks like it should have one obliges
nothing (X-6).

**The difference from the practice this came from is the whole point.** That one
writes the negative scenario outright with the status hardcoded — 400, 401/403,
404. Métis knows what the endpoint was actually seen to produce, so it reports
the recovered set and asks: *`GET /metric/{id}` produces 200, 204 and 400, and no
404.* That is a question somebody can answer; "missing 404" is one they cannot.
`unmet` says no such outcome was **recovered** — whether the behaviour is
unhandled or extraction did not see it is something only a person can settle, and
saying otherwise would assert a conclusion from an absence.

Either status of a pair satisfies its obligation: 401 and 403 are both a
refusal, 400 and 422 are both a rejection, and insisting on one of each would
report an endpoint unmet for choosing the other.

Run across the four Athena journeys: **17 endpoints take a path parameter and
carry no not-found**, and 10 accept input with no rejection recovered. One of
them returns 204 where a 404 might be expected — exactly the design decision a
person should confirm.

**`profile` — the factors behind the band.** `product.technical_profile` returns
the individual factors deliberately, and says why in its own docstring: *a single
band says how much there is to get wrong and hides what, and the answer changes
the response — high branching is met with more test cases, high fan-in is met
with a contract nobody may break.* Nothing read them. `test_design` surfaced the
band, `prioritisation` ordered by it, and the available response was always "test
this more", which is the answer to neither.

Each factor now carries the design response it asks for. And **an unmeasured
factor is a row saying so, never a blank** — a blank in a column of counts reads
as zero, and zero here reads as *simple*. `repairs` is separated further: a file
counted and never repaired is not a file nobody counted, and `repairs_window` is
the only thing that tells them apart.

### Condition completeness, and setup cost computed rather than guessed

Two sections ported from the sibling project's test designer, where both are
prose a model is asked to apply. The placement rule
(`docs/academy/10-where-a-thing-belongs.md`) says a checkable rule is a tool.

**`conditions` — the denominator.** A positive case says what the system does.
It does not say what the system must reject, prevent, limit or leave alone, and
counted as coverage for those it excuses exactly the gaps testing is for.
`shared/knowledge/requirement-condition-coverage.md` has stated this since it was
written and nothing applied it.

Every behaviour now gets a row for **all eight classes**, including the ones that
do not apply — that is the whole mechanism. A `boundary` row marked
`not-applicable` *with a reason* is the point; a class that silently disappears
is the failure. Métis reaches six of the eight from what it already recovered:
the transition itself, a rejecting sibling, the guard's partitions, its numeric
boundaries, the machine, and declared security. `dependency-failure` and
`non-goal` come back `clarify` and say why — what happens when something outside
this code stops answering, and what was deliberately excluded, are not in the
source it read.

**`proposed` and `decision` are separate columns.** Métis's reading is computed;
the decision is a person's. A class it could not reach reads `clarify`, which is
neither "we will test it" nor "it does not apply" — and an absent authorisation
check is `clarify` rather than `not-applicable`, because declarative security is
all extraction sees and "nobody looked" is not "open".

**`setup` — cost from the chain, not from a verb.** The practice this comes from
classifies a slice by its business verb: `get` and `view` are cheap, `create` and
`approve` are not. That is a stand-in for the real question — how much has to be
true before the assertion can happen — and Métis already answers it, because
`Path.setup_transition_ids` **is** the chain a test must establish.

Three things it refuses:

- **The effect is `unknown` where the trigger carries no HTTP verb.** A UI
  action's trigger is `submit_valid_credentials`; a rule falling through to
  `read-only` would call a credential submission a read and hand it the cheapest
  band.
- **The setup pattern is a human column.** Whether existing data can be reused,
  or an isolated entity must be provisioned, depends on what the environment
  holds and who owns cleanup — both `asked`. Métis costs the behaviour and states
  the two facts behind the cost; choosing with that in hand is a person's job.
- **`escalate` is not a verdict that something is too hard.** It says split it,
  stage it, or make the cost visible — never hide it inside a precondition.

**`shortest_setup` gained a `generatable_only` parameter, and the default is
unchanged.** Reaching a state is a property of the machine; whether the route may
be generated *from* is D-10, and only generation is bound by it. The first
version of `build_setup` called `generate` and therefore produced an empty
section for every real model — 56 behaviours excluded as `excluded_unapproved`
— while its `empty_means` blamed reachability. A design is a pre-approval
artefact: the `test-design` workflow has no approval precondition precisely
because designing before approval is when it changes a decision.

### Three defects that kept the guard-dimension engine unreachable

`mbt/dimensions.py` is four hundred lines implementing §2.4a's whole
combinatorial answer — the short-circuit chain that turns
`3 auth x 2 authz x 10 payload = 60` cases into 13, with GD-8's equivalence
credit gated on an identical code anchor. It had 43 passing tests and **no
caller outside them**. Three separate silent failures were why, and each was
found by running the thing rather than reading it.

**1. The evidence edges were planned and never landed.** `plan_landing` walks
`EVIDENCE_RELATIONSHIPS` over each transition's `evidence` tuple and plans all
five kinds. The model plan is landed *before* `_land_evidence` creates the nodes
two of them point at, so `-[:DERIVED_FROM]->DeclaredOutcome` and
`-[:CONSTRAINED_BY]->Check` MERGEd against nodes that did not exist yet — `land`
reports that as `unmatched` and does not fail. `Endpoint`, `Class` and
`ExceptionMapping` survived only because `_plan_derivation_edges` and
`_plan_payload_edges` re-plan them after the evidence layer exists; the other
two had no such pass.

Measured on a real estate: **0 of 176 transitions carried a check**, while 47
`Check` nodes and 88 `GUARDED_BY` edges sat in the same graph.
`_plan_outcome_edges` is the missing second pass, and
`test_every_evidence_label_written_by_the_raw_layer_has_a_second_pass` guards the
class of bug rather than the instance.

**2. `GuardCheck` had no `id`, which is the field `build_chain` reads.** So even
once the data flowed, the first real call raised `AttributeError`. The producer
and the consumer were written against different shapes and, having nothing
between them, never met. `id` is last in the dataclass rather than first,
deliberately: putting it first made `GuardCheck("t.isEmpty()")` mean
*id = the expression, expression = empty* — a silent reinterpretation instead of
an error.

**3. The loader selected `c.anchor`, a property no `Check` node has.**
`_anchor_props` writes `anchor_file` / `anchor_line` / `anchor_commit`, because a
Neo4j property cannot hold a map and a reviewer filters on file. Every
`GuardCheck.anchor` therefore came back empty — T-9a's traceability claim
silently failed, and worse, **GD-8 gates equivalence-class credit on an identical
anchor**, so unrelated checks all reading `""` would have been credited as one
behaviour. `_anchor_of` assembles the three, and returns `""` rather than
`":0@"` for an absent one precisely so absence cannot compare equal.

All three verified end to end against a disposable Neo4j: 0 unmatched edges, 12
`DERIVED_FROM->DeclaredOutcome`, 2 `CONSTRAINED_BY->Check`, transitions carrying
their checks, and `build_chain` producing a classified chain with a real `Cost`.

**An existing graph does not gain this until it is re-extracted.** The fix is in
the landing path; the edges are written when a model is landed, not repaired in
place.

### The design gained the section those four hundred lines were written for

`dimensions` — one row per dimension of each behaviour's chain, carrying the
recovered condition, its class, its **evaluation** order (never source line
position, X-10d), what it contributes to the bounded count, the reduction
(`4 of 8`) and the anchor. Owned by `metis-test-design-technique`, because the
chain is what bounds the coverage items that specialist derives.

Two refusals travel with it unsoftened: **GD-9**, where precedence could not be
recovered, reports the full product rather than generating it; and **X-10c**,
where a check matched no declared class, keeps its position in the chain and
renders a blank `Class` — a recovered fact, which is why `""` is in the column's
closed vocabulary and `--verify` accepts it.

`guard_dimensions` is gathered only where a chain can actually be built, so a
model with no recovered check reads as *unavailable* rather than as
*complete and empty*.

### Intent became a pre-processor

`intake` ran fetch → validate → land → assess risk. The first moment anybody saw
what was wrong with a claim was **after it was a node in the graph**, and nothing
consulted the intent validator, the wording checkers, the design ledger and the
risk ledger together at all. `model_sources.intent.validate` was reachable only
from `metis intent check` on the CLI, so no workflow and no agent could use it.

`analysis` and `readiness` now run **before** `land`, in both `intake` and a new
standalone `intent-review` workflow for the authored path. `metis_mcp/analysis/`
composes four readings, each seeing a hole the other three cannot.

- **Every gap names the aspect that found it and what would close it.** A gap
  with no closer is a complaint.
- **`readiness` is a blocking stage and not a gate.** §3.4 keeps one halt per
  workflow so each halt has one meaning, and this is not a halt: there is no
  literal that passes it, because the claim itself has to change. F-9's contract
  instead — a failed stage that names the action required.
- **The refusal is narrow, and both sides are tested.** `not-ready` means the
  claim cannot be represented (D-1). A claim nobody has costed, whose
  environments are unlisted and which has no criteria, is `ready` and lands
  carrying every one of those gaps. Refusing those would mean Métis only ever
  accepted claims that were already finished, which is not what intake is for.
- **Three of the four readings are owned outside the family.**
  `metis-knowledge-capture`, `metis-test-design` and
  `metis-risk-manager-requirement-risk` already run those procedures;
  `analysis/areas.py` records the hand-off and a test checks it in both
  directions.

### Two defects found by running the new code

- **The intent aspect reported a missing specification twice.** `intent.validate`
  already reports it and `readiness.analyse` re-derived it, so every unspecified
  need was filed under two ids. A duplicated gap inflates the count a reader
  judges a claim by, and the second row looks like a second problem.
- **Deduplicating it then let an unspecified need come back `ready`.** The fix
  moved the row onto the validator's output, which a hand-maintained set of
  "serious" problems did not name — so the blocking verdict silently
  disappeared. The set is gone: **every validator problem blocks, because
  `cmd_intent_land` refuses the file over any of them.** One definition rather
  than two, which is the shape that cannot drift.

### One merge implementation, three documents

`risk/document.py` held ~120 lines of table machinery — cell encoding, scoped
section reads, positional row parsing, and the merge that preserves human
columns and hand-added rows. Copying it into a second family is how the two
would start disagreeing about what `—` means.

It is `metis_mcp/document_table.py` now, with three callers. `test_risk.py` is
the regression guard on the extraction: it still passes unchanged, which is what
says the move was faithful. Row ids in all three documents are **content-derived**
— an id that counted rows off would move every recorded decision one row down the
moment something was added above it.

### Defects the risk work exposed in code that already shipped

- **Every gate printed a resume command argparse rejects.** All three —
  publication, spec-writeback and now risk — rendered
  `metis workflow resume <workflow>--<scope>`, while `--scope` is a required
  flag. Following the instruction was impossible. The router had documented the
  correct form the whole time.

- **`EARSResult` has `.conformant`, not `.conforms`**, and the first draft of
  `requirement_risk` read the second — an `AttributeError` on every call, caught
  by checking the API instead of trusting memory.

- **`release_risk` was written against three payload keys `coverage_report` does
  not emit.** `coverage` is a nested dict rather than a percentage, the findings
  live under `validation.blocking_detail` and only with `detail=True`, and
  `unmeasured` is a **string** when everything was measured — which the
  derivation would have iterated one character at a time.

- **`required: False` was pruned from every tool payload**, so an optional
  missing input was indistinguishable from a required one — the distinction the
  whole ledger rests on. `probability: null` had the same problem. Both are in
  `_ALWAYS_KEPT` now, alongside `depth_consulted`.

- **The document's own parser read the gathered-facts table as six malformed risk
  rows**, so a correct regeneration printed a warning naming things that were
  never risks. A warning that cries wolf is one people learn to ignore, which
  would then hide the case it exists for.

### Three defects found by running the new code against a real graph

Each was pre-existing, each passed the whole suite, and each was invisible until
something exercised the path end to end.

- **`change_review` could not produce a blocking finding for any diff.**
  `findings_for` read `impact["transitions"]` and `row["transition"]`;
  `impact.impact()` has only ever emitted `impacted_transitions` and `id`, so the
  loop body never ran and `critical`, `major` and `minor` were unreachable. Every
  review returned "no blocking finding from the behaviour model" — for a tool
  documented as producing the list `open_merge_request` refuses over. Eleven
  tests passed throughout because the fixture invented the payload shape it
  wanted. `test_the_fixture_matches_what_impact_really_returns` now reads
  `impact.py` and fails on a rename from either side. Provenance is also read
  from each criterion inline, because `change_review` never passed the
  `provenance` argument and `minor` was unreachable even after the key fix.

- **A configured-but-unreachable graph crashed every graph-backed MCP tool with
  a raw driver traceback.** Sixteen call sites caught `GraphNotConfigured`; none
  caught `ServiceUnavailable`, and no tool in `server.py` mentioned it.
  `GraphUnreachable` is now a subclass — so every existing handler catches it —
  translated once at the session boundary, and it says the database did not
  answer rather than telling somebody to set a variable that is already set.

- **The call sites discarded the exception's own message.** A malformed
  `.metis/config.json` and an unset `password_env` both raise
  `GraphNotConfigured` with a precise repair, and all sixteen sites replaced it
  with the constant "no graph is configured — set `METIS_NEO4J_URI`". A stray
  comma in a config file was reported as a missing environment variable.
  `impact.py` carried a second hardcoded copy of the same text.

Two smaller ones, caught by guards already in the suite: `depth_consulted` and
`probability` were deleted by `_prune` exactly when they were `false` and `null`
— which is the case each exists to report. Both are in `_ALWAYS_KEPT` now.

### Known limitations

Named here rather than discovered on contact.

- **Intake lands, but does not invent.** All six sources produce a Unified
  Intake Format document, and `intake land` carries it into the graph as an
  `Episode` (the ingestion run) plus one `<Source>Item` anchor (the artefact —
  a Jira issue, a Confluence page, an OpenAPI document). Two things it
  deliberately will not do: a UIF's *claimed* acceptance criteria never become
  `AcceptanceCriterion` nodes, because an upstream extractor's labelling is not
  evidence; and free prose never becomes a `Requirement`, because
  `ears_pattern` has no empty form and inventing one produces a well-formed
  statement nobody wrote. Non-conformant text lands as a `Finding` naming what
  has to happen next.
- **Component-level vs system-level acceptance criteria.** An OpenAPI document
  gives the component level mechanically. The system level needs the
  preconditions that produce a given set of parameters, and those are not
  derivable from a contract. Not designed yet.
- **Publication is dry-run by default, and a live transport exists.**
  `DryRunTransport` is the default: `test-generate`'s `publish` stage builds the
  real payload, validates it, and makes no network call. `--transport
  zephyr-scale` does write to a tracker, and needs two keys rather than one — a
  G2 confirmation supplied in that run, *and*
  `METIS_ALLOW_EXTERNAL_WRITES=yes` on the installation, which whatever drives
  the run cannot set for itself (T-20). `publishing.TRANSPORTS` is the list, and
  the CLI's choices are derived from it.
- **Coverage answers one question.** *Is this behaviour tested?* — never *is it
  working?* (C-11). Execution results **are** ingested now, and that is what
  keeps the two apart rather than merging them: they land through
  `execution_intake` at `Quarantine`, carrying
  `provenance: observed_from_running_system`, attached to the `TestCase` that
  ran and never to the transition it covers. Nothing there writes the coverage
  ledger, asserted structurally in `test_execution_intake.py`. So there are two
  figures — *is this tested* and *did it pass* — and a transition may be fully
  covered and currently failing.
- **The review UI trusts its identity header** and binds loopback. That is
  honest for a localhost review tool and unacceptable for anything else.
- **Connector manifests have no reader.** `connectors/` holds seven manifests
  and the JSON Schema they validate against, describing sources Métis was
  designed to ingest from. No loader exists in this build. The schema is a real
  contract; the capability is not there yet — see `connectors/README.md`.
- **Repository classification and ZDR are declarations, not gates.** The
  `zdr` and `repositories` blocks in the shipped configuration record a policy
  decision and nothing reads them. The `CONST-051`–`053` rules they cited are v1
  constitution rules the current specification does not carry, and no module
  implements the fail-closed blocking the comments described. The comments now
  say so; the control still has to be built before the claim can be made.
- **Project-level `.metis/config.*` is not read.** There is one default,
  `~/.metis/config.json`, or one override, `METIS_CONFIG_PATH`, which when set is
  the only candidate — a per-repository override of a machine's connection makes
  "which database did that write go to" unanswerable from the command alone. A
  project-local file is *reported* rather than silently skipped, and the checked-in
  `metis-server/.metis/config.yaml` is a record, not a live setting.

### Packaging

- `pyproject.toml` declared ten dependencies; seven had no importer anywhere in
  the tree and are gone. The wheel shipped four modules and none of the twelve
  subpackages, because `packages` was a literal list — it is now a recursive
  find, and CI builds, installs and resolves the console script so this cannot
  regress unseen.
- The three Dockerfiles and Helm components that referenced directories the
  rebuild deleted have been removed.
- **Settings that nothing read have been removed from every shipped config.**
  `graph.backend` selected between the v1 LocalGraphStore and Neo4jGraphStore
  and offered a `local | neo4j` choice where one path exists;
  `token_optimization.headroom_enabled` configured a module three deleted tools
  used. `test_independence.py` now asserts no config file offers either, across
  all five files rather than the one that carried the old `atlas` block.
- **The last back-compat path in cross-surface analysis is gone.** An unhandled
  outcome is a direct `TRIGGERS` query. The same-trigger heuristic kept as a
  fallback for journeys predating the `INVOKES`/`TRIGGERS` split reported
  findings derived from the very conflation `TRIGGERS` exists to remove, without
  saying so; re-extraction is the fix for an old journey.

### The rebuild, which had never completed

`rebuild_graph.sh` reached its own last stage for the first time. Five defects,
each of which hid the next:

- **A correct refusal was fatal.** `records-page` mutates through signatures
  computed at run time, so `js-ui` recovers the handlers and refuses to name an
  observable outcome (§5.8). Under `set -e` that killed the run at stage 3b, so
  the login model, the acceptance criteria and the cross-surface proposals never
  ran. It is reported and non-fatal now, and the refusal itself is a condition in
  `test_extraction.py` so it cannot be "fixed" into a guess.
- **The whole intent side was refused at the gate.** `land_spec_criteria.py`
  hand-builds its rows and never set `search_text`, `valid_from` or `valid_to`,
  so all 24 `AcceptanceCriterion` writes were rejected and the demo graph had no
  criteria at all — the half a recovered model is meant to be compared against.
  Now covered by `test_spec_criteria_landing.py`, which reuses `ontology.validate`
  rather than naming the three properties, so a fourth cannot slip through.
- **Cross-surface proposals raised `TypeError` on two constructors** — `LinkSet`
  without `journey`, `InvokesLink` without `proposed_by` and with a string where
  a dict belongs. The stage had never once executed.
- **The join key could not match.** It compared a screen name against a
  transition id, which is an opaque namespaced hash — so the stage reported a
  confident `0 INVOKES`, which reads as "these surfaces share nothing" rather
  than "my join matched nothing". `triggers` was also never populated, so
  `persist_triggers` wrote zero while the caller printed it as a count.
- **The derivation now lives in `mbt/link_proposals.py`**, pure and tested
  (`test_link_proposals.py`). It returns its misses instead of folding them into
  a zero, so an unmatched screen is distinguishable from an unmatched endpoint.

### The academy is landed

`docs/academy/` — eight lessons — lands as `:Lesson` at stage 4b of the rebuild,
into the **same** graph as the product facts. Neo4j cannot join across databases
in one session, so a separate academy database would put the lessons where
`search_knowledge` could never see them beside a criterion; separation is by
label and episode instead. A single `/search?q=archive` now returns both an
`AcceptanceCriterion` and a `Lesson`.

Measured rather than asserted: `metis retrieval-bench` over the academy scores
**10/15 top-1, 14/15 top-3, 0/15 absent** on keyword alone. Nothing is
unreachable; ranking is the gap, and it is the case `--hybrid` exists for. The
expected answers were written from the content before any search was run.

**And a miss is now recordable, not just printable.** `retrieval-bench --land`
writes each miss as an advisory `Finding` `ABOUT` the node that should have won —
`retrieval_rank` where it was reached but out-ranked, `retrieval_absent` where it
was not reached at all, kept apart for the reason `score` keeps them apart. This
closes the loop the academy was landed for: a lesson that reads badly through
`ask` becomes a finding about the *tools*, rather than living in whoever last ran
the command.

Two properties of it worth stating. The episode id is content-derived, so
re-running after no change is a no-op rather than a second record of one
measurement. And the remedy says explicitly that the fix is **not** to edit the
material to contain the query's words — prose written to satisfy a search stops
being readable by people, and would leave the benchmark grading text written to
please it. No ontology change: `Finding` already exists and `ABOUT` already
targets any label.

### Configuration

- **`~/.metis/config.json` is the one config file**, or `METIS_CONFIG_PATH` when
  set, which is then the *only* candidate. Project-local `.metis/config.*` is
  reported rather than read. `QUICKSTART.md` had claimed there was no config file
  at all, and `metis-server/.metis/config.yaml`'s own header claimed it overrode
  the host — both the reverse of what `config_paths` does.
- **`rebuild_graph.sh` no longer demands the password in the environment.** It
  had a bare `:?` guard, so moving the secret into the config file — the
  arrangement the tool recommends — broke the rebuild while `metis` kept working.
  It asks `graph_session.resolve()` now: one resolver, not two.
- **Three `test_api.py` tests were passing by accident.** They delete
  `METIS_NEO4J_PASSWORD` and expect a 204, which only means "no graph" if the
  environment is the only password source. With a config file present `resolve()`
  succeeded and answered 200. They now neutralise ambient configuration the way
  `test_graph_session.py` already did.
