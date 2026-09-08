---
name: metis-risk-manager-product-risk
description: Assess the risk in the product rather than the project — typing a risk item, gathering the technical factors from the recovered model, asking for the business ones, and turning the result into where test effort goes. Use when a request is about product risk, risk-based testing, what to test first, or whether the untested part is the part that matters.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - product_risk
  - risk_priority
  - risk_coverage
  - risk_inputs
  - risk_exposure
  - risk_categories
  - get_model
  - coverage_report
  - test_design
knowledge-from:
  - risk.product
  - risk.detection
  - risk.prioritisation
---

# Métis risk-manager · product-risk

## Prerequisites, from the parent

The parent (`metis-risk-manager`) has already established, and this skill does
not re-derive:

- every risk carries `derived_from`, and a model-derived one says *this is
  untested*, never *this is likely to fail*;
- `probability: null` until a person sets one;
- no overall risk score, ever.

## What this does

**Three taxonomies, and only one of them is about the project.**
`risk_categories` returns all three and they are never merged into one
distribution — each is owned by different people, so a merged chart describes no
decision anybody makes.

| Family | What it classifies | Who owns the row |
|---|---|---|
| `categories` | the project — a vendor, a sponsor, a currency | whoever funds it |
| `product_categories` | what the software can be wrong about (ISO 25010) | whoever builds the feature |
| `process_categories` | how the quality work itself fails | whoever builds the pipeline |

**The third is the one most of this skill is about**, and it is the one the
project-management reference has no room for: requirements that cannot be
validated, test design with no oracle, test data, environments that drift,
automation nobody trusts, regression, release and rollback, observability,
technical debt, capability.

**Everything Métis derives from a model files under `process_categories`.** It
observes things about the quality work — untested behaviour, a self-confirming
criterion, a change nothing re-checks. None of those is a project risk, and
filing them as `Quality` said they were: two buckets in a ten-category taxonomy
about funding and vendors, neither addressable by anybody in particular.

This is the risk work that decides testing. ISO/IEC/IEEE 29119-2 makes risk the
basis of the whole test process, and `risk_priority` is the part that acts on it.

## The three axes, and why there are three

| Axis | Question | Where it comes from |
|---|---|---|
| Impact | if this is wrong, what is lost? | **asked** — six PRISMA business factors |
| Likelihood | how much is there to get wrong? | **gathered** — technical factors from the model |
| Detectability | would we find out? | **gathered** — the coverage ledger and executions |

The third is the one a 5×5 grid cannot express and the one Métis is unusually
placed to compute. FMEA has carried it since the 1960s as the D in
S × O × D; the project-management reference this family was built from does not
have it at all.

**A failing test scores best on detectability.** This reads backwards and is
correct: detection asks whether the net would catch it, and a red test is the net
catching it. The live defect is reported beside the score as its own finding.
Rating a caught failure as poorly-detected would push effort away from the
failures nobody can see.

## The standard behind this, and what it does not certify

**ISO/IEC 25010** — `../../references/iso-25010-quality-model.md`. Métis follows
the **2023** nine-characteristic model, not 2011's eight: Usability became
Interaction capability, Portability became Flexibility, and Safety was added.
Testability sits under Maintainability, which is why an untestable requirement
is a product risk and not only a process complaint.

**A coverage map, never a compliance claim.** `metis_mcp/standards.py` is the
registry — which standard governs which skill, what Métis computes against it,
and what it refuses to claim. Whether the result satisfies an obligation is a
judgement about the obligation, not a property Métis can compute.

## What this skill must not do

- **Never derive a probability from coverage.** Coverage says *untested*; it
  does not say *likely to fail*. The quantitative specialist puts it at its
  sharpest — that is "C-11 with a currency symbol on it" — and detectability is
  not an exception to it. Detection is a property of the safety net, not of the
  code under it.
- **Never multiply the three axes into one number.** That is an RPN, and 1×5×5
  and 5×5×1 both read as 25 — the number hides which axis is bad and therefore
  what to do. `risk_priority` orders lexicographically and says so.
- **Never report a risk-weighted coverage percentage.** An ordinal band cannot
  be summed or averaged. `risk_coverage` returns a pivot: of the N items in this
  band, k are uncovered.
- **Never treat `unmeasured` as a detectability value.** Where coverage could not
  be measured there is no answer; reporting 5 makes a measurement gap look like a
  blind spot, and reporting 1 makes it look like safety.
- **Never let a technical band stand in for an assessment.** It ranks by how much
  there is to get wrong, not by what is at stake. Without the business half you
  have ordered the work and not judged it.

## Steps

1. `steps/01-profile.md` — type the risk item, gather the technical factors, and
   read what is missing.
2. `steps/02-direct.md` — turn the profile into where effort goes, and hand off.
