# 2 · Rank, band, and check the register is coherent

## Sort and band

Order by score descending. Apply the thresholds agreed in planning — which band
requires a documented response, which requires a senior owner, which blocks a
release. The band is a decision rule; without the thresholds it is decoration.

## Break ties on impact

Two risks scoring 12 as 3×4 and 4×3 are not equivalent. Prefer the higher-impact
one: a low-probability, high-impact risk has a fatter tail and usually needs a
contingency plan rather than a mitigation. Say that you did.

## Run the coherence check

`risk_register_check(register_json)` reports what is self-contradictory:

- **`RISK-SCORE-STALE`** — the score no longer equals probability × impact. This
  is the one that matters most. It means somebody re-rated and did not
  recalculate, and the row now sorts wrongly in every report while looking
  entirely normal.
- **`RISK-RESPONSE-POLARITY`** — a threat strategy on an opportunity or the
  reverse. Almost always a miscategorised risk rather than a wrong strategy.
- **`RISK-DERIVATION-SOURCE`** — a derivation that is neither `authored` nor
  `model`.

Fix these before reporting anything. A ranked list built on a stale score is
wrong in a way no reader can see.

## Then decide whether to go further

Ranking is often the whole answer. Hand off to the **quantitative** specialist
(`specialists/quantitative/`, starting at `steps/01-select.md`) only when a
decision turns on a figure that a rank cannot supply.
