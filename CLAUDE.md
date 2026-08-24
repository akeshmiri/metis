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

Commit `61814dc` replaced the v1 engine. These no longer exist: the 45-label
ontology, `structural_validation.py`, `layer8_heuristics.py`,
`confidence_tiering.py`, `guardrails/`, `quality_report.py`,
`demo_data/login_example.py`, `demo_data/generate_demo_data.py`,
`uif_intake.py`, `neo4j_test_support.py`, and every `metis_*` MCP tool
(`metis_get_traceability`, `metis_check_coverage`, `metis_list_skills`, …).

Superseded material lives in `docs/historical/` — the v1 ontology document, the
hand-written Cypher, the completed v1→v2 migration plan, the fifteen v1 design
notes (Constitution Amendments 1–5 and the memos around them), the v1 academy,
and contracts for eighteen MCP tools that no longer exist. Kept for its
reasoning, not as a description of anything current; each directory has a README
saying what is stale in it.

**`docs/` holds four things and the distinction between them is the point:**
the application spec (authoritative), `guide/` (**generated** from `labels.py`,
`intakes.json`, `stages.py` and the CLI parser — `metis guide --check` fails on
a diff, so it cannot drift), `academy/` (**authored** reasoning, labelled as
such because it is not checkable the same way), and `historical/`. Anything
design-shaped that is not the spec, the guide or a lesson is history.

## Facts that decide how you work here

- **The ontology is 61 labels and it is closed.** `metis_mcp/ontology/labels.py`
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
- **Everything lands at `Quarantine`.** No source writes `Approved` (S-4).
  Generation reads only `Approved` (D-10).
- **The MCP surface is read-only by default, and by construction when it is**
  (N-8, revised). `METIS_MCP_WRITE` is `off` | `author` | `full`; at `off` — the
  default — the write modules are never imported, so nineteen read-only tools
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
- **Métis never executes anything against the System Under Test (X-7a).** It
  reads intake sources and writes its own graph — it does not call the API it
  models, drive the UI, or query the database. `connectors/intakes.json` declares
  every intake and there is deliberately **no access mode that runs something**;
  `metis_mcp.intakes` loads it and `test_intakes.py` checks the declaration
  against the registered sources, the anchors and the catalogue, which is what
  the seven v1 manifests beside it never had. `intakes.describe()` is the
  capability map, and it lists what does **not** work.
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
uv run python -m pytest -q     # 1,503 tests in 69 files. Joern + a JDK are
                               # required (test_extraction.py builds real CPGs
                               # from demo_project/); no service, no network.
```

A live Neo4j (`metis-graph`) may be running locally. **It holds real work —
treat it as read-only** unless the user asks otherwise; use a disposable
container for anything that writes.

`METIS_NEO4J_PASSWORD` comes from the environment and never from an argument
(PLT-005).

## Things that are genuinely open

- **Publication is dry-run only.** `DryRunTransport` is the sole `Transport`
  (`mbt/cli.py`: "dry-run is the only transport registered in the first
  release"). `test-generate`'s `publish` stage builds and validates a real
  payload and sends nothing. Say so before someone passes a G2 confirmation
  expecting a write.
- **No `Component` nodes exist in the live graph**, so coverage reports there
  report "version not recorded (P-16)" until `persist` or `findings land` runs.
- **Intake creates a Requirement only from EARS-conformant text.** `intake land`
  carries a UIF into the graph as an `Episode` plus a `<Source>Item` anchor.
  Free prose — most Jira titles — lands as a `Finding` pointing at
  `knowledge-capture` instead, because `ears_pattern` has no empty form and
  guessing one is what `ac_mining` refuses to do (S-13). A UIF's *claimed*
  acceptance criteria are never trusted into `AcceptanceCriterion` nodes.
- **The academy is not landed in the graph.** `docs/academy/` is four
  authored lessons. The intent is that they land through normal intake so `ask`
  answers questions about Métis as it does about a product — and a lesson that
  reads badly through `ask` is then a finding about the tools. That needs a
  label which does not exist: `knowledge` lands `BusinessArea`/`BusinessEntity`/
  `Intent`, and a lesson is none of those. An ontology change under D-2, not
  yet argued for.
- **Component-level vs system-level acceptance criteria** — an OpenAPI document
  gives the component level mechanically; the system level needs the
  preconditions that produce a given set of parameters, and those are not
  derivable from a contract. Not designed yet.
- **The review UI trusts its identity header** and binds loopback. Honest for a
  localhost review tool, unacceptable for anything else.
