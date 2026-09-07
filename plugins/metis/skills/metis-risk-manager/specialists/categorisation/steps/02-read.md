# 2 · Read the distribution

`risk_report` gives the distribution by category, with the derivations kept apart
and the empty categories named.

## The empty categories are the finding

A category with nothing recorded under it means one of two things, and **nothing
in the data distinguishes them**:

- the project genuinely has no exposure there, or
- nobody has looked.

Say which you believe and why. Reporting the count without the ambiguity is how
an unexamined category becomes an assurance. If you cannot tell, that is the
finding: schedule an identification pass targeting it.

## Concentration is a finding too

A register where seven of ten risks are Technical usually means the identifying
was done by engineers. That is not wrong, but it tells you which categories were
under-served, and it predicts what the project will be surprised by.

## Keep the derivations apart

Model-derived candidates land almost entirely in Quality and Technical, because
that is all Métis can observe. A category distribution that merges them will
always look engineering-heavy and will hide how little of the *authored* register
exists.

`risk_report` reports the split per band; carry it into the category view too.

## What to do with it

The distribution is an input to the next identification pass, not a report for
its own sake. Name the two or three categories to target, and hand them to
`metis-risk-manager-identification`.
