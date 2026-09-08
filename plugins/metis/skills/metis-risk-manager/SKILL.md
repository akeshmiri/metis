---
name: metis-risk-manager
description: Run project risk management as a lifecycle — plan, identify, analyse, respond, monitor, close — routing to thirteen specialists, computing the arithmetic rather than reciting it, and producing one consolidated report in which a risk Métis derived from a model is never merged with one a person asserted. Use when a request concerns risk identification, a risk register, exposure or EMV, response strategies, a risk review or a risk report.
workflow: risk-review
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - risk_exposure
  - risk_emv
  - risk_pert
  - risk_categories
  - risk_register_check
  - risk_report
  - risk_candidates
knowledge-from:
  - standards
  - risk.register
  - risk.report
---

# Métis risk-manager

Risk management as a lifecycle, with one rule that is specific to this system
and load-bearing:

**A risk Métis derived from a model and a risk a person asserted are different
claims, and nothing here ever merges them.**

Every risk carries `derived_from: authored | model`. A model-derived risk says
*this behaviour is untested*. It does not say *this is likely to fail*. Averaging
the two lets a coverage gap read as a forecast — C-11
(`docs/metis-application-spec.md`) one domain over, and the same mistake that
makes a coverage figure look like a correctness figure.

## Routing — which specialist, and when

Fourteen specialists. Eleven carry one area of general project risk practice;
three are what Métis adds, and they are where a quality engineer spends the time. **Route on what the request asks for, not on the words it
uses.** When two seem to apply, the earlier step wins — the lifecycle runs in
order and a later step consumes the earlier one's output.

### The lifecycle, in order

| # | Route to | When the request asks to | Area |
|---|---|---|---|
| 1 | **`metis-risk-manager-framing`** | decide whether something is a risk at all, or write it so it can be acted on | §1 |
| 2 | **`metis-risk-manager-identification`** | *find* risks — produce candidates, rate none | §3 |
| 3 | **`metis-risk-manager-categorisation`** | tailor the taxonomy, or read where risk is concentrated | §4 |
| 4 | **`metis-risk-manager-qualitative`** | rank, score, band, heat-map | §5 |
| 5 | **`metis-risk-manager-quantitative`** | EMV, PERT, a reserve, a decision tree, sensitivity | §6 |
| 6 | **`metis-risk-manager-threat-response`** | choose a response to a **negative** risk | §7 |
| 6 | **`metis-risk-manager-opportunity-response`** | choose a response to a **positive** risk | §8 |
| 7 | **`metis-risk-manager-response-planning`** | turn a chosen strategy into owner, trigger, fallback, reserve | §10 |
| 8 | **`metis-risk-manager-monitoring`** | review, report, track, close, capture lessons | §11 |

### Across the lifecycle

| Route to | When the request asks to | Area |
|---|---|---|
| **`metis-risk-manager-register`** | create, structure, audit or clean up the register itself | §9 |
| **`metis-risk-manager-governance`** | decide who owns, who may accept, what escalates and what is recorded | §12 |

### What Métis adds, which no risk reference contains

| Route to | When the request asks about |
|---|---|
| **`metis-risk-manager-product-risk`** | risk in the **product** — what to test first, whether the untested part is the part that matters |
| **`metis-risk-manager-requirement-risk`** | the risk one requirement carries — is it safe to build? |
| **`metis-risk-manager-release-risk`** | the risk of shipping this scope now — what are we accepting? |

These three are the reason risk management lives inside Métis rather than beside
it. All three **gather** what Métis holds and **ask** for what it cannot derive,
and report `incomplete` until the asked half is answered.

**`product-risk` is a second discipline, not a fourteenth area.** The eleven
above are project risk management; risk-based testing is its own body of
practice (ISO/IEC/IEEE 29119-2), and none of its sections exist in the project
reference. `risk.areas.TESTING_AREAS` records that second map, and some of it is
owned by the test skills rather than by this family — prioritisation runs in
`metis-test-generate` and coverage measurement in `metis-coverage-report`,
because that is where the procedure actually runs.

Route to `product-risk` when the subject is the **thing being built**; to the
eleven when it is the **project building it**. "The vendor may be late" and
"this endpoint's authorisation is asserted by nothing" are both risks and share
no reader, no rater and no taxonomy.

### Keep these yourself

| Stay here | Where |
|---|---|
| Planning: scales, thresholds, appetite, ownership | `steps/01-plan.md` |
| The lifecycle when a request spans several steps | `steps/02-lifecycle.md` |

Planning stays here because every specialist's prerequisites refer back to it: a
scale settled inside one of them would not be in scope for the others.

The reasoning behind the register, the report and the gather-or-ask ledger is in
`knowledge/index.md` — generated from the module docstrings that are its source
of truth, so it cannot drift from the code it explains. Read a fragment when you
need the why, not before.

## The consolidated report

`risk_report(register_json)` — and `metis risk report <file>` for a person — is
the one place the whole register is summarised. `metis-risk-manager-monitoring`
drives it on a cadence; this is what it produces:

- the band distribution, **with authored and model-derived counted apart in every
  band**;
- risks that are unrated, counted rather than dropped — a model-derived half with
  no probabilities set would otherwise make the register look empty;
- the category distribution, **including the categories nothing is recorded
  under**, because an empty category is either safe or unexamined and the report
  cannot tell you which;
- which open High and Very High risks have no owner or no response;
- the coherence findings from `risk_register_check`.

**It computes no overall risk score, and says so in its own output.** A single
headline number is what a consolidated report is most often asked for and the one
thing it must not produce: an exposure is an ordinal rank, the register holds two
kinds of claim, and a model-derived risk has no probability at all. Bands are
recomputed from probability × impact rather than read from a stored `score`, so a
stale column cannot move the distribution.

Assemble the narrative around the tool's output; never assemble the figures by
reading rows.

## Compute, never recite

| Question | Tool |
|---|---|
| How does this rank? | `risk_exposure(probability, impact)` |
| What is it worth in money? | `risk_emv(probability, financial_impact)` |
| What is the estimate, and the spread? | `risk_pert(optimistic, most_likely, pessimistic)` |
| Which categories exist? | `risk_categories()` |
| Is this register self-consistent? | `risk_register_check(register_json)` |
| What does the register say? | `risk_report(register_json)` |
| What can Métis observe? | `risk_candidates(...)` |

**Never compute one of these in your head or in prose.** A 5×5 score and an EMV
are different kinds of number, and the tools refuse the input that belongs to the
other. `risk_emv(3, 100000)` is refused precisely because `300000` would look
completely normal and be five times too large.

## The standard behind this, and what it does not certify

**ISO 31000** — `references/iso-31000-risk-management.md`. It is **guidance with
no conformity assessment**, so "complies with ISO 31000" is a category error and
Métis makes no such claim. The reference maps this family's stages onto the
published process and names the one step that is not automated: communication
and consultation is a conversation with people.

**ISO/IEC/IEEE 29119-2** — `references/iso-29119-2-risk-based-testing.md`, for
the risk-based test strategy half.

**A coverage map, never a compliance claim.** `metis_mcp/standards.py` is the
registry — which standard governs which skill, what Métis computes against it,
and what it refuses to claim. Whether the result satisfies an obligation is a
judgement about the obligation, not a property Métis can compute.

## What this skill must not do

- **Never invent a probability.** A model-derived candidate has
  `probability: null` and it stays null until a person sets one. A number put
  there to fill the column reads as a forecast Métis never made.
- **Never merge the two derivations** in a chart, a total or an average.
- **Never produce a single overall risk score**, however it is asked for. Offer
  the band distribution and the top risks instead, and say why.
- **Never present a score as a measurement.** `risk_exposure` returns a `basis`
  line saying the score is ordinal. If you report the score, report that too.
- **Never decide whether a risk is real.** That is judgement and it belongs to a
  person. Métis checks a register for self-contradiction, not for truth.
- **Never treat an empty candidate list as "no risk".** `risk_candidates` reports
  `depth_consulted`; when it is false, nobody looked at coverage depth.
