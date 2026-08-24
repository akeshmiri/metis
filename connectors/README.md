# Intakes — what Métis reads

`intakes.json` declares every kind of thing Métis ingests, validated against
`metis-intake-schema.json`. **It is loaded and checked**, which is the whole
point of it: `metis_mcp/intakes.py` reads it and `metis-server/test_intakes.py`
asserts every claim against the code — the registered sources, the intake
anchors, the label catalogue, and the modules it names. A declaration that drifts
from what Métis does fails a test.

```bash
uv run --directory metis-server python -c \
  "from metis_mcp import intakes; print(intakes.describe())"
```

## Why that emphasis

Seven connector manifests lived here for a long time and **nothing ever opened
them**. They described an `athena_internal_read` protocol against entity types
the current ontology does not have — `Repository`, staged out — and because no
code path read them, nothing ever noticed. This README used to say so:

> a directory of plausible configuration implies a feature, and finding out by
> running it is worse than being told.

They are now deleted rather than kept, because a real declaration exists beside
them and two descriptions of the same thing is worse than one stale one. The
reasoning survives in `v1-source/connectors/` and in git history.

## The rule the schema exists to enforce

**X-7a: Métis never executes anything against the System Under Test.** It reads
from intake sources and writes to its own graph. It does not call the API it
models, drive the UI it models, or run a query against the database it models.

The distinction that does the work: *a database Métis reads to learn structure is
an intake source; the same database reached to check a test's outcome is the
System Under Test.* Same server, different act, and only the first is available.

That is structural, not remembered. Every `access` mode is read-only —
`local_files`, `read_only_connection`, `authored_file`, `uif_document` — and
**there is no mode meaning "runs something"**. `executes_against_sut` is a schema
`const` of `false`, and the loader refuses a declaration that says otherwise.
Adding an executing mode is the change that would have to be argued for.

## Reading a status

| | |
|---|---|
| `working` | a reader exists and a test exercises it |
| `partial` | a reader exists and something material is missing, named in `limits` |
| `declared` | **no reader.** The capability does not exist, and this says so |

`declared` is the most useful row in the table, because it is the one somebody
would otherwise assume works. `describe()` prints every non-`working` intake with
its limits for the same reason.

## What the v1 connector manifests settled

`v1-source/connectors/` holds the seven manifests this file replaced. Comparing
them against `intakes.json` found one real omission and settled four apparent
ones. Recorded here so the next person to make the comparison does not have to
redo it.

**The omission.** v1's `test-suite` connector had no counterpart here — and
`code_analysis/packs/jvm-test-inventory` existed the whole time: a real pack,
named by `engine.TEST_INVENTORY`, consumed by `metis paths --inventory`, and
read by `test_levels.from_pack` to keep generation additive. It is declared now,
and `test_every_query_pack_is_declared_by_some_intake` is what stops the next
one hiding, because nothing checked code → declaration for packs.

**Settled, not missing:**

| v1 connector | why there is no intake for it |
|---|---|
| `grafana` | lands `Alert`, `Metrics`, `Logs` — all `STAGED_OUT`, each with the trigger that would bring it back |
| `locust-performance` | lands `TestExecution` — `STAGED_OUT`. Métis reports coverage, never outcome (C-11) |
| `bmad-method` | lands `Goal` — `STAGED_OUT` |
| `flatfiles` | "any dropped document" is deliberately refused. Free prose lands as a `Finding` pointing at knowledge-capture, never as a `Requirement` (S-13) |

**Two manifest fields were worth taking**, and are now in the schema:
`lands_from` (v1's `entity_type_mapping` — what in the source produces each
label, which `lands` alone cannot say) and `temporal` (where `t_recorded` comes
from, and how it misleads).

**One was not.** v1's `precedence_tier` declared which entity types a connector
was system-of-record for, and which connectors outranked it. Métis rejects this:
`behavior_model.corroborate_transition` surfaces a code-versus-model
disagreement as `Disputed` and never resolves it toward either side (I-8, S-10)
— *"neither automatically wins, because a precedence rule would decide a
question only a person can."* Two intakes disagreeing is the finding, not a
problem to be arbitrated away.
