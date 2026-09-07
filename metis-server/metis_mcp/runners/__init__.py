"""
Things that make something happen (the `run` tier of `execution.py`).

**Separate from `observers/` because the decisions are different sizes.**
Reading a replica is recoverable. Driving load at a host somebody mistyped is an
outage, so it costs a further tier AND the literal word `execute` in the call —
the same shape the G1 and G2 gates use, and for the same reason: a confirmation
that a caller can supply by accident is not a confirmation.

Nothing here is imported unless `METIS_EXECUTE=run`.
"""
