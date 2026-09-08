# Risk-based testing — ISO/IEC/IEEE 29119-2

**A side reference, not loaded by default.** Consult it when a test strategy has
to be justified as risk-based against the published process, or when somebody
asks why a design is ordered the way it is.

It would still be true if Métis were deleted, which is why it is a reference
rather than knowledge.

## What the standard is

29119-2 is the **test processes** part of the series. It defines processes at
three levels — organisational test process, test management, and dynamic testing
— and it is the part that makes **risk-based testing** the organising principle
rather than an optional technique: test effort is allocated against product risk,
and the allocation is recorded.

## The part Métis computes

Métis does not run an organisation's test management. It computes the arithmetic
those processes consume, and each piece names the module that owns it:

| What | Where |
|---|---|
| product risk factors behind a band — branching, coupling, size, repair history | `risk/product.py`, `product_risk` |
| the prioritisation keys that order both a design's rows and a generated batch | `risk/prioritisation.py`, `risk_priority` |
| the risk breakdown taxonomy, product and process | `risk/rbs.py`, `risk_categories` |
| depth warranted against depth achievable | reported as an **open question with an owner**, never as a figure |

**One wire is asserted rather than assumed.** A design's rows and the batch
generated from it are ordered by the same keys, and `test_design_sections.py`
asserts the two orderings are equal — so a design and the tests built from it
cannot disagree about what matters first.

## The refusal that keeps it honest

**A band ranks; it never forecasts.** No design table carries a probability
column, and `test_no_section_carries_a_probability` forbids one. A model-derived
band says *this behaviour is complex and untested*, which is a statement about
evidence. *This will probably break* is a statement about the future, and nothing
in the recovered model supports it.

`product.technical_profile` returns the individual factors deliberately, so the
answer to a band is a specific response rather than "test this more" — and an
unmeasured factor is **a row saying so**, because a blank among counts reads as
zero and zero reads as simple.

## What this reference does not do

It does not reproduce the standard, and Métis claims no conformance to it. 29119-2
describes processes an organisation runs; Métis computes inputs to them. Whether
the resulting strategy satisfies an obligation is a judgement about the
obligation.
