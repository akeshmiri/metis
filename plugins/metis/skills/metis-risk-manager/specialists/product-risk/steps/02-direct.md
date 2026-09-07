# 2 · Turn the profile into where effort goes

## Order, and say what the order is by

`risk_priority(journey, surface)` sorts by detectability first, defect-proneness
second, id third. Report the axis order with the list — an ordering whose key is
unstated is one the reader has to trust.

The third key is not decoration: it makes the order **total**, so a regenerated
suite diffs cleanly (P-7). Two items alike on both axes never swap between runs.

## Match test depth to the band, which is the PRISMA quadrant rule

PRISMA's product risk matrix exists to produce *differentiated* test approaches,
not one approach applied harder. `test_design` gives the techniques; the band
decides how many of them are worth applying.

| Band | Approach |
|---|---|
| Very High | every technique `test_design` offers — boundaries, each partition, the negative cases |
| High | boundaries and partitions; negatives on the paths that carry data |
| Medium | one case per partition |
| Low | one positive case, and say that is what it is |

**This is a starting point that a person adjusts, not an allocation.** The bands
came from thresholds somebody chose in `product.THRESHOLDS`; a project that
disagrees changes them there rather than arguing case by case.

## Report what the ordering does not know

`risk_priority` ranks on the two gathered axes. Until the business half is
answered it has ordered the work by effort, not by what is at stake — a trivial
endpoint nothing covers outranks a payment path with one weak test. Say so
plainly, then get the impact ratings from the people who hold them.

## Hand off

- The response to *untested behaviour* is a test, not money — the
  test-generation workflow, not a contingency reserve.
- A **failing** item is a defect and leaves this skill entirely. It needs a fix,
  and tracking it as a risk is how a known break becomes a forecast nobody acts on.
- Residual risk and the exit decision belong to `release-risk`, which consumes
  readiness and does not recompute it.
