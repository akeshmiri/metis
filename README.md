# Métis

Métis recovers what a system **does** from its code, compares that against what
somebody **said it should do**, and generates human-executable test cases from
the part that survives review.

The comparison is the point. A model extracted from code and used to generate
tests proves the code does what the code does — that is circular, and it cannot
find a defect in the logic itself (§4.1). *The code locks after 3 attempts; the
acceptance criterion says 5* is the kind of finding no amount of testing the
code against itself will ever produce.

**Start with [`docs/metis-application-spec.md`](docs/metis-application-spec.md).**
It is the authoritative specification — every rule id used in the code
(`M-18`, `S-13`, `P-16`, `D-1`, `GD-2`, `N-8`, …) is defined there, and the code
cites them inline.

## Two gates, and only two

Nothing auto-approves and nothing auto-promotes on elapsed time.

| Gate | Where | Rule |
|---|---|---|
| **G1 — model approval** | before anything is generated | Validation findings and reconciliation gaps are the evidence |
| **G2 — publication** | before any external write | A literal affirmative confirmation, in that run |

An unreviewed model stays unapproved indefinitely. The safe failure is "no tests
generated", never "tests generated from an unreviewed model".

## Knowledge has two stages

| Stage | What it is | Where it lives |
|---|---|---|
| **1 — documentation** | A `Requirement` and its atomic `AcceptanceCriterion`s. Text; true or false on its own terms | a knowledge file, reviewable before any database exists |
| **2 — graph** | The same facts as nodes, plus the behaviour mined from them, plus the traceability between the two | Neo4j |

An acceptance criterion is **atomic**: one condition, one action, one validation
(S-20).

## The tree

```
docs/                            the spec, the guide, the academy, and history
├── metis-application-spec.md    THE specification — read this first
├── guide/                       GENERATED from labels.py, intakes.json,
│                                stages.py and the CLI parser. `metis guide
│                                --check` fails on a diff, so it cannot drift
├── academy/                     AUTHORED reasoning — labelled as such because
│                                it is not checkable the way the guide is
└── historical/                  superseded, kept for its reasoning.
    │                            every directory has a README saying what is stale
    ├── design-notes-v1/         the 15 v1 design notes (Amendments 1–5 and friends)
    ├── metis-specification-v1.md            the v1 platform spec
    ├── metis-ontology-specification-v1.md   the v1 ontology
    ├── migration-plan-v1-to-v2.md           the rebuild plan; completed at 61814dc
    ├── mcp-contracts-v1/        contracts for 18 tools that no longer exist
    ├── schema-v1/               hand-written Cypher (now generated)
    ├── academy/                 v1 explainers + the site built from them
    ├── atlas-test-design-port/  the unwired Atlas test-design skill
    └── PLAN-v1.md               the v1 build plan

metis-server/                    the engine. Python, no framework.
├── metis_mcp/
│   ├── ontology/                THE ontology: 63 labels + the relationship
│   │                            catalogue. The Cypher schema is GENERATED from
│   │                            labels.py, so the two cannot drift.
│   ├── mbt/                     model-based testing: criteria, path generation,
│   │                            coverage ledger, validation, rendering, the CLI,
│   │                            and link_proposals.py — cross-surface INVOKES/
│   │                            TRIGGERS derivation, pure so its join key is
│   │                            assertable
│   ├── model_sources/           the five registered sources — authored, code,
│   │                            web, ac-mined, openapi — plus knowledge.py
│   │                            (stage 1), landing.py (stage 2) and lessons.py
│   │                            (the academy, landed as :Lesson). Every source
│   │                            produces candidates at Quarantine; none writes
│   │                            Approved.
│   ├── workflow/                the five workflows, their stages and gates.
│   │                            The one place that knows the order.
│   ├── reconciliation/          AC ↔ transition matching, and the two gap
│   │                            reports that are never merged into one number
│   ├── identity/                natural keys — deduplication across sources and
│   │                            incremental update across runs are one lookup
│   ├── review/                  review-as-code: export → decide → apply
│   ├── review_ui/               the reviewer's screens; a screen that cannot
│   │                            show its evidence blocks the decision
│   ├── publishing/              three-way drift detection, then G2
│   ├── specgen/                 the stakeholder specification (§18)
│   ├── overrides/               human edits as layered facts, never mutations
│   ├── retrieval/ (retrieval.py)  keyword + semantic, fused by RANK not score —
│   │                            no model is bundled and none is loaded by default
│   ├── api/                     the HTTP surface: bearer auth against a digest
│   │                            store, and a G2 confirmation bound to one run
│   └── server.py                the MCP surface: nineteen read-only tools,
│                                plus a gated write half (METIS_MCP_WRITE)
├── code_analysis/               Joern query packs → normalised contract →
│                                synthesis. No engine type reaches the graph.
├── schema/                      GENERATED Cypher (Community only — C1)
└── test_*.py                    77 test files, 1,688 tests, no Neo4j required.
                                 Joern is needed for five of them (see CLAUDE.md)

.mcp.json                        registers the MCP server for this repo — stdio,
                                 nineteen read-only tools, no absolute paths
plugins/metis/                   the five skills, and the generated agent files
plugins/metis-mcp/               MCP server registration, for a marketplace install
metis-chart/                     Helm chart (one component: the MCP server)
connectors/                      connector manifests + their schema.
                                 Designed; nothing reads them yet (see its README)
```

## Running it

```bash
cd metis-server
uv venv && uv pip install -e ".[test]"   # the extra is what brings pytest
uv run python -m pytest -q            # the whole suite; no database needed
uv run python -m metis_mcp.mbt.cli workflow list
```

**Joern and a JDK are test prerequisites**, and neither is pip-installable so the
`[test]` extra cannot bring them. `test_extraction.py` builds real CPGs from
`demo_project/` and runs the shipped query packs over them — before it existed the
packs had no behavioural test at all, and their correctness claims were prose in a
manifest. A missing Joern **fails** rather than skipping, because a skip would
quietly restore that. Run `uv run python -m metis_mcp.mbt.cli doctor` to check.
The CPGs are cached by a hash of the corpus, so this costs ~25s once and ~7s
afterwards.

The engine is otherwise deliberately database-free: models, criteria, path
generation and coverage are all pure, so the suite needs no external service.
Only landing, loading and reporting against a live graph need Neo4j — set
`METIS_NEO4J_URI`/`METIS_NEO4J_USER` and provide `METIS_NEO4J_PASSWORD` in the
environment (never as an argument).

See [`metis-server/QUICKSTART.md`](metis-server/QUICKSTART.md) for the full setup.

## Things it will not do

- **Present code-derived tests as evidence that behaviour is correct.** They are
  evidence that it is *covered* (S-1).
- **Report coverage as quality.** A coverage figure answers *is this behaviour
  tested?* and never *is it working?* (C-11).
- **Guess.** An unparseable guard is reported `unverifiable` — a third outcome,
  never folded into a pass (M-17). A request matching two workflows equally asks
  rather than picking.
- **Decide through the agent surface.** The MCP tools are read-only by
  construction (N-8); decisions need the evidence presentation the review UI and
  the CLI provide.
