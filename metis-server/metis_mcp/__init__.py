"""
Métis — behaviour recovered from code, compared against what somebody said the
system should do, and turned into human-executable test cases.

See `docs/metis-application-spec.md` for the rule ids this package cites inline.

This file exists so `metis_mcp` is a regular package rather than a namespace
one. Without it setuptools raised no warning while shipping a wheel that
contained four modules and none of the twelve subpackages.
"""
