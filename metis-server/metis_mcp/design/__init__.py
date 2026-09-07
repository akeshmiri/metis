"""Test design: what to test, how, at which level, and what nobody knows.

`inputs` is the gather-or-ask ledger, `sections` is the deterministic template
registry, `builders` computes the rows from what Métis recovered, `document`
renders and merges, and `areas` records which skill owns which section.

Pure throughout. The graph is read by `server.design_report`, which fills a
`builders.DesignContext` and hands it here — so the whole family runs in the
engine-free suite.
"""
