# CONST-053 Confirmation Record & Procurement Checklist

This is not a design decision to make — it's a status to confirm with Anthropic
and record. This document is (1) the checklist to bring into that
conversation and (2) the formal record once it's answered. `CONST-051`'s
classification gate (implemented in `metis-mcp-server`'s `classification_gate.py`,
alongside this document) reads the recorded answer below and enforces it —
so filling this in is what actually turns the policy on, not just documents it.

---

## 1. What to actually ask Anthropic

Based on Anthropic's current documented policy (checked directly, not assumed):
the commercial API defaults to 30-day retention with no training on customer
data; a Zero Data Retention (ZDR) agreement is available for eligible
enterprise customers via a direct commercial agreement — it is **not
self-serve**, requires Anthropic's approval, and covers the Messages/Token
Counting APIs specifically, **not** Batch processing, the Files API, or the
Console/Workbench. Bring these specific questions, not a general "can we get
ZDR":

1. **Is our organization eligible for a Zero Data Retention agreement**, and what's the actual process/timeline to get one in place?
2. **Which API surfaces does our ZDR agreement cover?** Confirm explicitly: Messages API (what Cognify extraction and the Layer 6 judge actually use, per `metis-cost-review-15k-tests.md`'s cost model) — yes/no. Batch API (if cost optimization later routes extraction through batch calls) — separately yes/no, since ZDR does not automatically extend there.
3. **Which specific models are covered?** Confirm the extraction model (`claude-haiku-4-5-20251001`) and judge model (`claude-sonnet-5`) — both already set in the Helm chart's `values.yaml` — are ZDR-eligible. Note: Anthropic's "Covered Models" (currently Claude Fable 5 and Claude Mythos 5) require 30-day retention and are explicitly **excluded** from ZDR regardless of an org's standing agreement — if anyone on the team ever considers routing Métis through those model tiers instead of Haiku/Sonnet, that decision would need re-confirming against this same question.
4. **What does ZDR guarantee, precisely?** Confirm: no storage of inputs/outputs beyond what's needed for abuse-screening; User Safety classifier results are still retained even under ZDR (this is normal, not a gap — confirm the org accepts this as expected, not a surprise later).
5. **What's the retention/DPA path if ZDR isn't approved in time for Phase 0?** Get a real answer on what the standard 30-day-retention terms mean for source code specifically — is source code content treated any differently than other prompt content under the standard Commercial Services Agreement's no-training guarantee?

## 2. What to have ready before the call

- A rough estimate of ingestion volume (already computed: `metis-cost-review-15k-tests.md`'s real numbers — 15,000+ tests, 100,000 Jira tickets — Anthropic's sales team will want a usage-scale picture, not just "we want ZDR")
- A list of which repositories are expected to be `Confidential`-tier (per `CONST-052`) at Phase 0 launch, even a rough one — this affects how urgent the ZDR timeline actually is
- Confirmation of who internally owns this relationship (legal/procurement/security — whoever signs a commercial agreement, not just engineering)

## 3. The formal record — fill in once answered

| Field | Value |
|---|---|
| Date confirmed | `[ ]` |
| Confirmed by | `[ ]` |
| ZDR agreement status | `[ ]` — one of: Active / In progress (expected date: ___) / Declined / Not yet requested |
| Covered API surfaces | `[ ]` — e.g. "Messages API only" |
| Covered models | `[ ]` — confirm Haiku 4.5 / Sonnet 5 explicitly |
| Effective date | `[ ]` |
| Renewal/review date | `[ ]` — recommend tying this to the same cadence as `CONST-035`'s metric review, so it doesn't quietly lapse unnoticed |

**Until every field above is filled in, `ANTHROPIC_ZDR_CONFIRMED` (the Helm
chart's `values.yaml`, and the classification gate below) MUST remain
`false` — this is the fail-closed default `CONST-052` requires, and it's
deliberately not something to flip to `true` on an assumption that the
agreement is "probably fine" or "in progress."**
