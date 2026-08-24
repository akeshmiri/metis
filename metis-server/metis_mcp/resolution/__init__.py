"""
Joins that cannot be made yet (spec X-19).

**Two facts that belong together often arrive at different times, and until now
Métis dropped the join.** `BusinessEntity -STORED_IN-> Table` has been catalogued
since the evidence layer landed and nothing ever derived it. The authored page
structure and the extracted selectors join on element name — done by hand, in a
test. A repository names `RecordEntity` and only a database catalogue can say
which table that is.

Each of those is the same shape: **one side proposes, the other confirms, and
they do not arrive together.** So a proposal is a first-class record rather than
a step in a pipeline:

    PendingJoin(kind, from_ref, to_ref, basis, confidence, reason)

Three rules make it honest:

* **`basis` is named.** `naming-strategy`, `element-name`, `route-suffix` — never
  "it looked right". A reviewer weighs a join by how it was proposed.
* **An unresolved join is a `Finding`, not silence.** A missing half is visible,
  counted in the run summary, the same discipline X-6d applies to a fact the
  model cannot reach.
* **A refuted proposal stays refuted.** If the confirming side arrives and does
  NOT contain the target, no edge is written and the finding says so. That is the
  case that distinguishes this from a retry loop: "not yet" and "no" are
  different answers.

Resolution runs after every landing, so a join resolves as soon as its second
half exists — which is what "Métis should look at both sides and resolve when the
missing piece is added" means in code.

An intake declares what it can **propose** and what it can **confirm**; adding a
fourth intake adds rows to those declarations, not code here.
"""
from __future__ import annotations

from metis_mcp.resolution.joins import (
    CONFIRMED,
    KINDS,
    PROPOSED,
    REFUTED,
    JoinKind,
    PendingJoin,
    Resolution,
    edges_for,
    findings_for,
    properties_for,
    resolve,
)

__all__ = ["PendingJoin", "Resolution", "JoinKind", "KINDS", "resolve",
           "findings_for",
           "edges_for", "properties_for",
           "PROPOSED", "CONFIRMED", "REFUTED"]
