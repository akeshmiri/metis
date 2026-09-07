# 2 · Elicit, and write each one as cause → event → effect

## The form

Not "database". Not "performance". Each candidate:

> **If** *(cause — a condition that exists now or may arise)*, **then**
> *(event — the uncertain thing)*, **resulting in** *(effect — the consequence
> to the project)*.

The form is not bureaucracy. It is what makes a risk respondable: the cause is
what a mitigation acts on, the event is what an indicator watches for, and the
effect is what determines the impact rating. A row missing any of the three
cannot be responded to, monitored, or rated, and will sit in the register
untouched until it occurs.

## Assign a category as you go

Use `risk_categories()` and validate against it. Free text is how a register
grows `Tech`, `Technical` and `technical` as three rows in one chart.

## Add the model-derived candidates

Run `risk_candidates(...)` with the change under consideration and, where a
journey is known, pass it — otherwise positive-path-only behaviour produces no
candidate and the list is short for a reason that has nothing to do with safety.

Keep them tagged `derived_from: model` and leave `probability` null.

## Then stop

Do not rate. Do not sort. Do not respond. Hand the candidate list to the
qualitative specialist.

## Report the gaps

Finish by naming which categories produced nothing. `rbs.distribution` reports
empty categories rather than dropping them, and an empty category is the
interesting one: either genuinely safe, or nobody looked. Say which you believe
and why.
