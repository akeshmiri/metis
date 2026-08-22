"""
The model sources (application spec §4.5, §4.6, §5).

    HumanAuthoredSource   implemented   — a modelling session, expressed as a file
    CodeExtractedSource   implemented   — §5, from a query pack's validated report
    WebExtractedSource    implemented   — §5, the ui surface
    ACMinedSource         implemented   — §4.5, from acceptance-criteria prose

All four are real. `ModelSource.available` / `why_unavailable` remain part of the
interface anyway: a source that cannot run says why rather than being absent, and
§4.3's layered architecture depends on reconciliation being able to name a source
it could not compare against.

**ACMinedSource makes no model call**, despite what an earlier version of this
docstring said. Criteria written to EARS or Given/When/Then are parseable
deterministically (TR-4), so free prose is *blocked and reported* rather than
guessed at — a miss, never a fabrication. Turning prose INTO those shapes is a
judgement and happens in a skill session, gated by `model_sources.knowledge`.
"""
from __future__ import annotations

import json
from pathlib import Path

from metis_mcp.mbt.model import QUARANTINE, Model, State, Transition
from metis_mcp.model_sources.base import (
    AC_MINED,
    DECLARED_CONTRACT,
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
                outcome_status=entry.get("outcome_status"),
                guard_anchor=entry.get("guard_anchor", ""),
                source_state_unresolved=bool(entry.get("source_state_unresolved", False)),
                inputs=tuple(entry.get("inputs", ()) or ()),
                security=tuple(entry.get("security", ()) or ()),
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

    **This used to be permanently unavailable, and the consequence was a real
    provenance defect.** Extraction genuinely worked -- the Joern packs plus
    `code_analysis.synthesis` produced all thirteen models of the pilot estate --
    but it ran outside the source registry, and its output was landed through
    `HumanAuthoredSource` with `--author joern-jvm`. So every one of those models
    recorded `extraction_method: hand_authored`: the graph said a person wrote
    what a static analyser had inferred, which is exactly the claim M-13's
    provenance exists to prevent.

    It reads the packs' already-emitted reports rather than invoking Joern
    itself. That is the honest boundary: running the CPG engine is a separate,
    long, environment-dependent step (X-1a pins the version), and a source whose
    `available` depended on a working Joern install would report "unavailable" for
    reasons that have nothing to do with Métis. What this owns is the step from
    validated pack output to a model -- which is the part §5.3 specifies.
    """

    name = "code"
    extraction_method = STATIC_ANALYSIS

    @property
    def available(self) -> bool:
        return True

    def why_unavailable(self) -> str:
        return ""

    def produce(self, path: str | Path = "", author: str = "",
                endpoints: str | Path = "", journey: str = "",
                surface: str = "api", service: str = "", **kwargs) -> SourceResult:
        """`path` is the behaviour pack's report; `endpoints` the structural one.

        `service` scopes a multi-module report to one deployable. **Omitting it
        on a monorepo report is a real error, not a wider default**: the pilot
        estate's single report carries 405 outcomes across seven services, so an
        unscoped run produces one 145-transition model wearing one service's
        name. That is worse than failing, because it looks like a result.
        """
        from code_analysis.contract import validate_report
        from code_analysis.synthesis import synthesise

        if not path:
            raise ValueError(
                "code source requires the behaviour pack's report "
                "(packs/jvm-behaviour). Extraction is not re-run here — this reads "
                "what the pack already emitted (spec §5.3)")

        behaviour = _report_from_dict(json.loads(Path(path).read_text()))
        errors = validate_report(behaviour)
        if errors:
            # X-5: a pack's output is validated before anything consumes it.
            # Synthesising from a report that failed its own contract would put
            # unvalidated machine output into the graph.
            raise ValueError(
                f"{path} failed the pack contract ({len(errors)} error(s)): "
                f"{errors[0]}")

        # The structural report is read twice, for two different things: the raw
        # endpoint dicts the synthesiser joins on, and the full report whose
        # Layer 3 members and `@ExceptionHandler` map are what let a declared
        # rejection be attributed to bean validation rather than left generic.
        structural = None
        endpoint_facts = (json.loads(Path(endpoints).read_text())
                          if endpoints else [])
        if isinstance(endpoint_facts, dict):
            structural = _report_from_dict(endpoint_facts)
            endpoint_facts = endpoint_facts.get("endpoints", [])

        services = _services_in(behaviour)
        if service:
            if service not in services:
                raise ValueError(
                    f"no facts anchored to service {service!r}; this report covers "
                    f"{', '.join(sorted(services)) or 'nothing recognisable'}")
            behaviour = _scope_to_service(behaviour, service)
            endpoint_facts = [e for e in endpoint_facts
                              if _service_of(_anchor_file(e)) == service]
            # `structural` is deliberately NOT scoped. Its two remaining uses are
            # cross-service by construction: `GlobalExceptionHandler` lives in
            # athena-common and the DTOs in athena-model, so scoping it to a
            # deployable would empty both and every rejection would silently fall
            # back to the generic precondition.
        elif len(services) > 1:
            raise ValueError(
                f"this report spans {len(services)} services "
                f"({', '.join(sorted(services))}) and no --service was given. "
                f"Synthesising them together would produce one model wearing one "
                f"service's name — pass --service to scope it")

        result = synthesise(behaviour, endpoint_facts,
                            journey=journey, surface=surface,
                            structural=structural)
        if not result.ok:
            raise ValueError("; ".join(result.errors)
                             or "synthesis produced no model")

        return SourceResult(
            model=result.model,
            extraction_method=self.extraction_method,
            source_connector=self.name,
            evidence={"behaviour_report": str(path),
                      "endpoints_report": str(endpoints or ""),
                      "repo": behaviour.repo, "commit": behaviour.commit,
                      "engine": f"{behaviour.engine} {behaviour.engine_version}",
                      "pack": f"{behaviour.pack} {behaviour.pack_version}"},
            skipped=[(e, "synthesis finding") for e in result.findings],
            # M-13 / N-10: the analyser is the proposer. Naming a person here
            # would let them approve their own machine's output unchallenged.
            proposed_by=author or f"{behaviour.pack}@{behaviour.pack_version}",
        )


def _anchor_file(fact) -> str:
    """The file an anchor points at, whether the fact is a dataclass or a dict."""
    anchor = fact.get("anchor") if isinstance(fact, dict) else getattr(fact, "anchor", None)
    if isinstance(anchor, dict):
        return anchor.get("file", "")
    return getattr(anchor, "file", "") or ""


def _service_of(file_path: str) -> str:
    """`athena-boot-metric/src/main/...` -> `metric`.

    The same derivation `mbt/test_levels.service_of_path` uses, so the module a
    test is attributed to and the module a transition is extracted from cannot
    disagree.
    """
    from metis_mcp.mbt.test_levels import service_of_path
    return service_of_path(file_path)


def _services_in(report) -> set[str]:
    return {s for s in (_service_of(_anchor_file(o)) for o in report.outcomes) if s}


def _scope_to_service(report, service: str):
    """Keep only the facts anchored inside one deployable.

    Checks are filtered by the outcomes that survive rather than by their own
    anchors: a guard is only meaningful as the condition on some outcome, and
    dropping one an outcome still references would leave a transition whose
    guard silently disappeared -- an unguarded transition that reads as
    unconditional when it is not.
    """
    import dataclasses

    outcomes = [o for o in report.outcomes
                if _service_of(_anchor_file(o)) == service]
    kept_checks = {cid for o in outcomes for cid in (o.guarding_check_ids or ())}
    return dataclasses.replace(
        report,
        outcomes=outcomes,
        checks=[c for c in report.checks if c.id in kept_checks],
        methods=[m for m in report.methods
                 if _service_of(_anchor_file(m)) == service],
        endpoints=[e for e in report.endpoints
                   if _service_of(_anchor_file(e)) == service],
    )


def _report_from_dict(data: dict) -> "ExtractionReport":
    """Rehydrate the pack's JSON into the contract's own dataclasses."""
    from code_analysis import contract

    def anchor_of(row: dict):
        a = row.get("anchor")
        return contract.Anchor(**a) if isinstance(a, dict) else a

    def rows(key, cls):
        """Rehydrate, converting nested rows to their own dataclasses.

        `cls(**row)` alone leaves `parameters` as a list of plain dicts, so
        `EndpointFact.parameters[0].name` raises and every downstream reader
        silently sees "no parameters" instead. Nested structure has to be
        converted here or it does not survive the file boundary at all.
        """
        out = []
        for row in data.get(key, ()):
            row = dict(row)
            if "anchor" in row:
                row["anchor"] = anchor_of(row)
            if "parameters" in row:
                row["parameters"] = tuple(
                    contract.ParameterFact(
                        name=p["name"], location=p["location"],
                        type_name=p.get("type_name", ""),
                        required=bool(p.get("required", True)),
                        constraints=tuple(p.get("constraints", ())))
                    for p in row.get("parameters") or ())
            if "security" in row:
                row["security"] = tuple(
                    contract.SecurityFact(
                        scheme=s.get("scheme", ""), expression=s.get("expression", ""),
                        roles=tuple(s.get("roles", ())))
                    for s in row.get("security") or ())
            for key_name in ("consumes", "produces", "layers", "guarding_check_ids",
                             "constraints"):
                if key_name in row and row[key_name] is not None:
                    row[key_name] = tuple(row[key_name])
            out.append(cls(**row))
        return out

    return contract.ExtractionReport(
        contract_version=data.get("contract_version", contract.CONTRACT_VERSION),
        pack=data.get("pack", ""), pack_version=data.get("pack_version", ""),
        engine=data.get("engine", ""), engine_version=data.get("engine_version", ""),
        repo=data.get("repo", ""), commit=data.get("commit", ""),
        frontend=data.get("frontend", ""), layers=tuple(data.get("layers", ())),
        methods=rows("methods", contract.MethodFact),
        calls=rows("calls", contract.CallFact),
        endpoints=rows("endpoints", contract.EndpointFact),
        members=rows("members", contract.MemberFact),
        checks=rows("checks", contract.CheckFact),
        outcomes=rows("outcomes", contract.OutcomeFact),
        exception_mappings=rows("exception_mappings", contract.ExceptionMappingFact),
        parse_errors=list(data.get("parse_errors", ())),
        partial=bool(data.get("partial", False)),
    )


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
                # Which criterion produced which transition (S-14). Counting the
                # spans and discarding them lost the one fact that makes a mined
                # transition traceable to its own source text -- and without it
                # the criterion lands as an orphan beside behaviour it wrote.
                "criterion_transitions": {
                    cid: sorted({e.element_id for e in result.elements
                                 if e.kind == "transition" and e.span.criterion_id == cid})
                    for cid in sorted({e.span.criterion_id for e in result.elements
                                       if e.kind == "transition"})
                },
            },
            # S-13's blocked proposals ride out as `skipped`, so a caller sees
            # what was refused rather than only what was produced.
            skipped=[(b.criterion_id, f"{b.reason}: {b.detail}") for b in result.blocked],
        )


class WebExtractedSource(ModelSource):
    """Page machines recovered from a frontend (spec §5.2, M-2).

    The Web counterpart of `CodeExtractedSource`, and separate for the reason
    the two synthesisers are separate: a screen is not a status code (M-3), and
    the packs recover genuinely different things. Registering it closes a real
    gap -- **neither UI synthesiser was reachable from anywhere**, so the six
    landed UI models were hand-derived off-pipeline and recorded
    `hand_authored`, exactly the provenance defect the code source had.

    Two frontends are supported and they are not interchangeable: `react-ui`
    recovers page status regions, `js-ui` recovers DOM event handlers. The pack
    that produced a report is read from the report itself rather than guessed.
    """

    name = "web"
    extraction_method = STATIC_ANALYSIS

    @property
    def available(self) -> bool:
        return True

    def produce(self, path: str | Path = "", author: str = "", journey: str = "",
                screens: str = "", **kwargs) -> SourceResult:
        from code_analysis.react_ui_synthesis import synthesise_react_ui
        from code_analysis.ui_synthesis import synthesise as synthesise_js_ui

        if not path:
            raise ValueError(
                "web source requires a UI pack report (packs/react-ui or "
                "packs/js-ui). Extraction is not re-run here — this reads what "
                "the pack already emitted (§5.3)")

        facts = json.loads(Path(path).read_text())
        pack = facts.get("pack", "")
        wanted = {s.strip() for s in (screens or "").split(",") if s.strip()}

        if pack == "react-ui":
            outcome = synthesise_react_ui(facts, journey=journey,
                                          screens=wanted or None)
            skipped = ([(u.split(":")[0], u) for u in outcome.unresolved]
                       + [(f, f) for f in outcome.findings])
            evidence = {"report": str(path), "pack": pack,
                        "pages": ", ".join(sorted(outcome.pages)),
                        "repo": facts.get("repo", ""), "commit": facts.get("commit", "")}
        elif pack == "js-ui":
            outcome = synthesise_js_ui(facts, journey=journey)
            skipped = [(u, u) for u in getattr(outcome, "unrecoverable", ())]
            evidence = {"report": str(path), "pack": pack,
                        "repo": facts.get("repo", ""), "commit": facts.get("commit", "")}
        else:
            raise ValueError(
                f"unknown UI pack {pack!r}; expected 'react-ui' or 'js-ui'. The two "
                f"emit different keys, and feeding one to the other's synthesiser "
                f"reports 'nothing recovered' — true, and misleading")

        if not outcome.ok:
            raise ValueError("; ".join(outcome.errors) or "synthesis produced no model")

        return SourceResult(
            model=outcome.model,
            extraction_method=self.extraction_method,
            source_connector=self.name,
            evidence=evidence,
            skipped=skipped,
            proposed_by=author or f"{pack}@{facts.get('pack_version', '?')}",
        )



class OpenAPISource(ModelSource):
    """Behaviour declared by an OpenAPI document (§5.2; X-2).

    **Its own source, and its own extraction method, on purpose.** The document
    flows through the same `contract.ExtractionReport` a code pack emits, so
    `synthesise` needs no change -- but what it produces is not what
    `CodeExtractedSource` produces, and the graph must not say it is. A code
    model records what the system *does*; this records what its contract
    *declares*. Where they differ, that difference is the finding (§4.1), and it
    is invisible if both arrive wearing `static_analysis`.

    **The honest limit, stated where it will be read.** A document declares which
    statuses occur and never under what conditions, so every transition from it
    carries an empty guard. `validation.check_guard_completeness` will report
    that correctly. It is not a defect in the adapter: the contract genuinely
    does not contain the conditions, and inventing them is what S-13 forbids.
    """

    name = "openapi"
    extraction_method = DECLARED_CONTRACT

    def produce(self, path: str | Path = "", journey: str = "",
                surface: str = "api", repo: str = "", commit: str = "",
                author: str = "", **kwargs) -> SourceResult:
        from code_analysis.contract import validate_report
        from code_analysis.openapi import load as load_spec
        from code_analysis.openapi import to_dict, to_report
        from code_analysis.synthesis import synthesise

        if not path:
            raise ValueError("openapi source requires a document path")

        adapter = to_report(load_spec(path), repo=repo or journey or "openapi",
                            commit=commit, document=str(path))
        errors = validate_report(adapter.report)
        if errors:
            # X-5's gate, unchanged. A human-written document gets no exemption.
            raise ValueError(
                f"{path} failed the contract ({len(errors)} error(s)): {errors[0]}")

        endpoints = to_dict(adapter.report)["endpoints"]
        result = synthesise(adapter.report, endpoints,
                            journey=journey or adapter.report.repo, surface=surface,
                            structural=adapter.report)
        if result.model is None:
            raise ValueError(
                "no model could be synthesised from this document; nothing is "
                "written (S-17). " + "; ".join(result.errors))

        return SourceResult(
            model=result.model,
            extraction_method=self.extraction_method,
            source_connector=self.name,
            evidence={
                "document": str(path),
                "version": adapter.report.commit,
                "endpoints": len(adapter.report.endpoints),
                "declared_outcomes": len(adapter.report.outcomes),
                "constrained_fields": sum(1 for m in adapter.report.members
                                          if m.constraints),
            },
            # Disclosed limits ride out as `skipped`, so a caller sees what the
            # document contained and this could not carry -- the same channel
            # S-13's blocked proposals use.
            skipped=[("document", note) for note in adapter.notes],
            proposed_by=author or "openapi",
        )


AUTHORED = register(HumanAuthoredSource())
WEB = register(WebExtractedSource())
CODE = register(CodeExtractedSource())
AC_MINED_SOURCE = register(ACMinedSource())


OPENAPI = register(OpenAPISource())
