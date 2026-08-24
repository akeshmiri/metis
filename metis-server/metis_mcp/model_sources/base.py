"""
Model sources: one interface, five implementations (application spec §4.2, R9).

Every source produces **candidate** elements and none writes an approved model
(spec S-4). The MBT engine never learns which source produced a model (F-29),
which is why they are interchangeable and why deferring one costs no rework.

`authored`, `code`, `web`, `openapi` and `ac-mined` are all registered and all
implemented -- `cli sources` reports availability from the registry rather than
from a list here, so that command is the answer and this docstring is not.

`ModelSource.produce` still raises `NotImplementedError` as its base behaviour.
That is deliberate: a source registered without an implementation must fail at
the point someone runs it, carrying the reason, rather than be absent from the
registry and look like a capability nobody thought of.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from metis_mcp.mbt.model import Model

HAND_AUTHORED = "hand_authored"
STATIC_ANALYSIS = "static_analysis"
AC_MINED = "ac_mined"

# Matches Transition.extraction_method's enum in ontology.labels.
# A published contract is not static analysis of code. Reusing `static_analysis`
# for an OpenAPI document would repeat the exact provenance defect
# `CodeExtractedSource` records: extraction ran outside the registry, its output
# landed through the authored source, and the graph said a person wrote what a
# machine had inferred. A reviewer weighs "the code does this" and "the document
# says this" very differently, and M-13 exists so they can.
DECLARED_CONTRACT = "declared_contract"
EXTRACTION_METHODS = (HAND_AUTHORED, STATIC_ANALYSIS, AC_MINED, DECLARED_CONTRACT)


@dataclass
class SourceResult:
    """What a source produced, plus what it could not.

    `proposed_by` is who or what put this forward, and it is a field rather than
    an `evidence` entry because N-10 depends on reading it back: the identity
    that proposed an element may not approve it. It used to survive only inside
    the Episode's joined `evidence` string, which meant `check_self_approval`
    received `None` for every landed element and the separation-of-duties gate
    had never once fired on a real model.
    """

    model: Model
    extraction_method: str
    source_connector: str
    evidence: dict = field(default_factory=dict)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    proposed_by: str = ""
    # The already-parsed pack reports, by name (`structural`, `behaviour`).
    #
    # Carried so the workflow can land the EVIDENCE layer beside the model
    # without re-reading and re-validating files the source has already read.
    # `evidence` above holds provenance strings for the Episode; this holds the
    # contract objects themselves, and a source with none simply has none.
    reports: dict = field(default_factory=dict)


class ModelSource:
    """Interface every source implements.

    `extraction_method` is recorded on every element it produces (spec M-13), so
    provenance survives into the graph and into the review file.
    """

    name: str = ""
    extraction_method: str = ""

    def produce(self, **kwargs) -> SourceResult:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        return True

    def why_unavailable(self) -> str:
        return ""


_REGISTRY: dict[str, ModelSource] = {}


def register(source: ModelSource) -> ModelSource:
    _REGISTRY[source.name] = source
    return source


def get(name: str) -> ModelSource:
    if name not in _REGISTRY:
        raise ValueError(
            f"unknown model source {name!r}; registered: {', '.join(sorted(_REGISTRY))}"
        )
    return _REGISTRY[name]


def registered() -> dict[str, ModelSource]:
    return dict(_REGISTRY)


def availability() -> list[tuple[str, bool, str]]:
    """(name, available, reason) for every registered source.

    Used by the CLI to report what could produce a model when none exists, rather
    than silently choosing one on the user's behalf (spec S-17, S-18).
    """
    return [(name, s.available, s.why_unavailable())
            for name, s in sorted(_REGISTRY.items())]
