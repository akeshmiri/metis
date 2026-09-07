# 1 · Assign the level and read what covers it

## Actions

1. `design_report(journey, surface, section="levels")`.
2. `coverage_report` for what could not be measured at all. Carry `unmeasured`
   into what you say — a coverage figure with an unstated denominator is the
   number C-11 warns about.
3. Report the three grades separately, with counts.

## Forbidden substitutions

- Do not treat `covered: 0, uncovered: 0` as full coverage. An empty model
  produces both, and so does a typo in the journey name.
- Do not read a missing grade as `uncovered`. Not measured and measured-as-zero
  are different facts, and only one is a design gap.

## Report

Level per behaviour, the three grade counts, and what could not be measured.
