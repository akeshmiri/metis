# 1 · Narrow the taxonomy to this organisation

The ten categories `risk_categories()` returns are a starting point, not a
standard. An RBS is organisational and tailoring is expected.

## Narrow in one place, once

The failure mode is not having the wrong categories — it is having them defined
in three places. Pick the set, write it down where the register lives, and use it
everywhere.

## What tailoring usually means

- **Split** where the organisation has real depth. A regulated business will
  split Compliance into data protection, financial reporting and licensing,
  because those have different owners and different escalation paths.
- **Merge** where a distinction changes nothing. A small internal project rarely
  needs Procurement and Financial as separate columns.
- **Rename** to the words the organisation already uses. A taxonomy people have
  to translate is one they will stop using.

## The test for whether a category earns its place

**Would a risk in it go to a different person?** Categories exist to prompt, to
reveal absence and to aggregate — and all three depend on the category
corresponding to something real about how the organisation works. If two
categories always land on the same owner with the same response, they are one
category.

## Depth

Two levels is usually right: a category, and a sub-category naming the source.
Three levels is a taxonomy nobody maintains.

## Record the decision

Which set, and why it differs from the default. Without that, the next person
re-tailors it differently and the register becomes uncomparable with its own
history.


## Three taxonomies, not one to tailor

`risk_categories` returns `categories` (project), `product_categories` (ISO
25010) and `process_categories` (the quality work itself). Tailoring applies to
each **separately**, and a risk validates against any of them — `rbs.taxonomy_of`
reports which family a category belongs to.

**Never merge them into one distribution.** A chart with `Procurement` beside
`Test environment` beside `Security` has three owners and no reader. Draw one
distribution per family and say which you are showing.

The one that usually needs the least tailoring is `process_categories`: it came
from the test process rather than from an organisation, so its entries mean the
same thing in most places. The one that usually needs the most is the project
taxonomy, which is where organisational vocabulary actually differs.
