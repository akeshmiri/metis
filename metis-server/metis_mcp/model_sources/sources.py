"""
The three model sources (application spec §4.5, §4.6, §5).

    HumanAuthoredSource   implemented   — a modelling session, expressed as a file
    CodeExtractedSource   registered    — §5, needs the CPG engine (X-1a)
    ACMinedSource         registered    — §4.5, needs Jira evidence and a model call

The two unimplemented ones raise with a reason rather than being absent. Their
presence is what makes §4.3's layered architecture real: reconciliation compares
candidates from several sources, and a source that does not exist cannot be
compared with.
"""
from __future__ import annotations

import json
from pathlib import Path

from metis_mcp.mbt.model import QUARANTINE, Model, State, Transition
from metis_mcp.model_sources.base import (
    AC_MINED,
    HAND_AUTHORED,
    STATIC_ANALYSIS,
    ModelSource,
    SourceResult,
    register,
)


class HumanAuthoredSource(ModelSource):
    """A model authored by a person, expressed as a file.

    The simplest source, and the only one available without an external
    dependency. Everything it produces lands at Quarantine like any other
    source's output -- authoring is not approving (spec S-4, E-11).
    """

    name = "authored"
    extraction_method = HAND_AUTHORED

    def produce(self, path: str | Path = "", author: str = "", **kwargs) -> SourceResult:
        if not path:
            raise ValueError("authored source requires a model file path")
        data = json.loads(Path(path).read_text())

        states = {}
        skipped: list[tuple[str, str]] = []
        for entry in data.get("states", []):
            states[entry["id"]] = State(
                id=entry["id"], name=entry.get("name", entry["id"]),
                surface=entry.get("surface", "api"),
                is_initial=bool(entry.get("is_initial", False)),
                lifecycle_state=QUARANTINE,
            )

        transitions = {}
        for entry in data.get("transitions", []):
            if entry["source"] not in states or entry["target"] not in states:
                # Reported, not silently dropped: a dangling reference is a
                # modelling defect and shrinking the model would hide it.
                skipped.append((entry["id"], "source or target state not in this model"))
                continue
            transitions[entry["id"]] = Transition(
                id=entry["id"], source=entry["source"], trigger=entry["trigger"],
                target=entry["target"], guard=entry.get("guard", ""),
                implementation_status=entry.get("implementation_status", "implemented"),
                lifecycle_state=QUARANTINE,
            )

        return SourceResult(
            model=Model(id=data["id"], states=states, transitions=transitions),
            extraction_method=self.extraction_method,
            source_connector=self.name,
            evidence={"path": str(path), "author": author or "unknown"},
            skipped=skipped,
            proposed_by=author or "unknown",
        )


class CodeExtractedSource(ModelSource):
    """State machines recovered from source by state-variable abstraction (§5).

    Registered so the architecture is honest about it, and so `availability()`
    can report *why* it cannot run rather than leaving the option invisible.
    """

    name = "code"
    extraction_method = STATIC_ANALYSIS

    @property
    def available(self) -> bool:
        return False

    def why_unavailable(self) -> str:
        return ("needs the code-property-graph engine (spec X-1a: Joern, pinned) "
                "and a query pack; N-16 stage 3")

    def produce(self, **kwargs) -> SourceResult:
        raise NotImplementedError(self.why_unavailable())


class ACMinedSource(ModelSource):
    """Behaviour mined from acceptance-criteria prose (§4.5).

    Its honest limitation is worth restating where it will be read: acceptance
    criteria rarely describe a complete state machine, so AC-mined models are
    typically partial and will correctly fail §2.6's completeness check. They are
    valuable as the *intent* side of a comparison, rarely sufficient alone.
    """

    name = "ac-mined"
    extraction_method = AC_MINED

    @property
    def available(self) -> bool:
        """Available, and with no model call.

        The earlier stub said this needed "a gated model call (MIN-010)". It does
        not: criteria written to EARS or Given/When/Then are parseable
        deterministically, and TR-4 prefers deterministic code to generated
        judgement wherever it will do. Criteria in free prose are *blocked and
        reported* rather than guessed at -- which is a miss, not a fabrication.
        """
        return True

    def why_unavailable(self) -> str:
        return ""

    def produce(self, criteria: list | None = None, model_id: str = "",
                surface: str = "api", initial_state: str | None = None,
                path: str | Path = "", **kwargs) -> SourceResult:
        """Mine a model from acceptance criteria (spec §4.5).

        `criteria` may be passed directly, or read from a JSON file of
        `{"id", "text", "requirement_id"}` objects.
        """
        from metis_mcp.model_sources.ac_mining import Criterion, mine

        if criteria is None:
            if not path:
                raise ValueError("ac-mined source requires criteria or a criteria file")
            criteria = [
                Criterion(id=e["id"], text=e["text"],
                          requirement_id=e.get("requirement_id"))
                for e in json.loads(Path(path).read_text())
            ]
        criteria = [c if isinstance(c, Criterion)
                    else Criterion(id=c["id"], text=c["text"],
                                   requirement_id=c.get("requirement_id"))
                    for c in criteria]

        result = mine(criteria, model_id=model_id or "ac-mined",
                      surface=surface, initial_state=initial_state)
        if result.model is None:
            raise ValueError(
                "no transition could be mined; nothing is written (S-13, S-17).\n"
                + "\n".join(f"  {b.describe()}" for b in result.blocked))

        return SourceResult(
            model=result.model,
            extraction_method=self.extraction_method,
            source_connector=self.name,
            evidence={
                "criteria": len(criteria),
                "grounded_spans": len(result.elements),
                "blocked": len(result.blocked),
                "notes": result.notes,
            },
            # S-13's blocked proposals ride out as `skipped`, so a caller sees
            # what was refused rather than only what was produced.
            skipped=[(b.criterion_id, f"{b.reason}: {b.detail}") for b in result.blocked],
        )


AUTHORED = register(HumanAuthoredSource())
CODE = register(CodeExtractedSource())
AC_MINED_SOURCE = register(ACMinedSource())
