"""
Readers of a live system (the `observe` tier of `execution.py`).

**Nothing in this package is imported unless the tier allows it.** That is what
makes `METIS_EXECUTE=off` structural rather than a promise —
`test_execution.py::test_the_off_default_is_structural` asserts these modules are
absent from `sys.modules` in a default deployment.

Everything here READS. A module that changed the system it observed would belong
in `runners/`, behind a further tier and a literal, and the split is the point:
reading a replica is recoverable and making something happen is not.

**What comes back is labelled `observed_from_running_system`**, always. A fact
read from a live system and a fact recovered from source are different claims
about different things, and §8.7 stages out the execution labels precisely
because merging them turns a coverage figure into a correctness one (C-11).
"""
