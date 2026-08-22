"""
The evidence layer (application spec D-12, D-13, D-14, X-2, X-6, REQ-CGA-010).

The processed intake was never in the graph. 91 endpoints, 245 parameters, 1,581
DTO fields, 405 outcomes and 102 checks lived in JSON files under `/tmp`, so a
transition's entire provenance was a `source_episode_id` property naming the
*ingest* — never the endpoint, the outcome or the field.

**Two rules carry the design and both are about refusing to invent.** A `Class`
node exists only for a type this repository declares, so a parameter typed
`java.lang.Long` gets no edge rather than a stub node (REQ-CGA-010). And what
lands is `contract`'s own dataclasses, never the engine's graph (X-2/D-12) — the
distinction that lets §8.7's staged labels return without contradicting X-2.

Free to run: the planner is pure, and the writer is exercised by
`test_batched_writer.py`.
"""
from __future__ import annotations

import sys

from code_analysis.contract import (
    Anchor,
    CheckFact,
    EndpointFact,
    ExceptionMappingFact,
    ExtractionReport,
    MemberFact,
    MethodFact,
    OutcomeFact,
    ParameterFact,
)
from metis_mcp.model_sources.raw_landing import (
    class_id,
    endpoint_id,
    endpoints_by_handler,
    field_id,
    plan_raw_landing,
    type_names_in,
)

A = Anchor("MetricController.java", 42, "sha1")
DTO_A = Anchor("MetricDto.java", 12, "sha1")
REPO = "athena"


def _structural(**kw) -> ExtractionReport:
    return ExtractionReport(
        pack="jvm-structural", pack_version="0.1.0", engine="joern",
        engine_version="4.0.604", repo=REPO, commit="sha1", frontend="javasrc2cpg",
        methods=kw.get("methods", [
            MethodFact(id="c.MetricController.save:R(D)", name="save",
                       type_name="MetricController", signature="R(D)", anchor=A)]),
        endpoints=kw.get("endpoints", [
            EndpointFact(id="e1", http_method="POST", path="/metric",
                         handler_method_id="c.MetricController.save:R(D)", anchor=A,
                         handler_type="MetricController", handler_name="save",
                         validated=True, response_type="ResponseEntity<Void>",
                         response_body="",
                         parameters=(
                             ParameterFact("metricDto", "body",
                                           "org.catools.athena.model.MetricDto"),
                             ParameterFact("page", "query", "int"),
                         ))]),
        members=kw.get("members", [
            MemberFact("MetricDto", "duration", "java.lang.Long", DTO_A,
                       constraints=("@NotNull",)),
            MemberFact("MetricDto", "project", "java.lang.String", DTO_A)]),
        exception_mappings=kw.get("mappings", [
            ExceptionMappingFact("MethodArgumentNotValidException", 400,
                                 "GlobalExceptionHandler", A)]),
    )


def _behaviour() -> ExtractionReport:
    return ExtractionReport(
        pack="jvm-behaviour", pack_version="0.1.0", engine="joern",
        engine_version="4.0.604", repo=REPO, commit="sha1", frontend="javasrc2cpg",
        checks=[CheckFact("chk-1", "t.isEmpty()", 1, A)],
        outcomes=[OutcomeFact(
            id="c.MetricController.save:R(D)::POST::201",
            endpoint_id="c.MetricController.save:R(D)::POST",
            signature="201/created", status=201, discriminator="created",
            guarding_check_ids=("chk-1",), link="name-match", anchor=A)],
    )


def _plan(**kw):
    return plan_raw_landing(_structural(**kw), journey="athena", repo=REPO,
                            behaviour=kw.get("behaviour", _behaviour()),
                            ui_facts=kw.get("ui_facts"),
                            include_call_graph=kw.get("include_call_graph", True))


def _labels(plan):
    from collections import Counter
    return Counter(n.label for n in plan.nodes)


def _edges(plan):
    from collections import Counter
    return Counter(f"{e.from_label}-{e.rel_type}->{e.to_label}" for e in plan.edges)


# --------------------------------------------------------------------------
# It lands, and it lands legally.
# --------------------------------------------------------------------------

def test_the_plan_passes_the_same_gate_every_other_write_does():
    """Under Community the application gate is the SOLE guarantee that required
    properties exist (D-8a/D-8b), so an evidence node gets no exemption."""
    plan = _plan()
    assert plan.is_legal, plan.errors


def test_every_layer_of_the_intake_becomes_nodes():
    labels = _labels(_plan())
    for label in ("Endpoint", "Parameter", "Class", "Field", "Method",
                  "DeclaredOutcome", "Check", "ExceptionMapping"):
        assert labels[label] >= 1, f"nothing landed for {label}"


def test_every_evidence_node_carries_its_anchor():
    """X-6: an element that cannot be traced back to a line is not emitted."""
    plan = _plan()
    anchored = {"Endpoint", "Field", "Method", "DeclaredOutcome", "Check",
                "ExceptionMapping"}
    for node in plan.nodes:
        if node.label in anchored:
            assert node.properties.get("anchor_file"), f"{node.label} has no anchor"
            assert node.properties.get("anchor_commit"), f"{node.label} has no commit"


def test_everything_points_at_the_episode_that_justifies_it():
    plan = _plan()
    for node in plan.nodes:
        if node.label == "Episode":
            continue
        assert node.properties["source_episode_id"] == plan.episode_id


# --------------------------------------------------------------------------
# Identity (D-8).
# --------------------------------------------------------------------------

def test_re_landing_the_same_report_is_a_no_op():
    """Content-derived ids mean a second ingest MERGEs onto the same nodes."""
    first, second = _plan(), _plan()
    assert [n.properties["id"] for n in first.nodes] == \
           [n.properties["id"] for n in second.nodes]


def test_ids_exclude_the_commit_so_a_new_commit_updates_in_place():
    """Including it would duplicate the whole 6,885-node estate on every ingest.
    The commit stays where it belongs — on the anchor."""
    later = _structural()
    later.commit = "sha2"
    plan = plan_raw_landing(later, journey="athena", repo=REPO,
                            behaviour=_behaviour())
    endpoints = [n for n in plan.nodes if n.label == "Endpoint"]
    assert endpoints[0].properties["id"] == endpoint_id(REPO, "POST", "/metric")
    assert endpoints[0].properties["anchor_commit"] == "sha1", (
        "the anchor still records which commit this fact came from")


def test_two_repositories_declaring_one_type_stay_two_nodes():
    assert class_id("athena", "MetricDto") != class_id("other", "MetricDto")


# --------------------------------------------------------------------------
# REQ-CGA-010: nothing external is invented.
# --------------------------------------------------------------------------

def test_a_parameter_typed_by_a_jdk_class_gets_no_edge_and_no_stub_node():
    """`int` and `java.lang.Long` are not declared here. A `Class` node for them
    would be a fabricated node; an edge to one would dangle."""
    plan = _plan()
    class_names = {n.properties["name"] for n in plan.nodes if n.label == "Class"}
    assert "MetricDto" in class_names
    assert not {"int", "Long", "String"} & class_names

    # The body parameter resolves; the `int` query parameter does not.
    assert _edges(plan)["Parameter-OF_TYPE->Class"] == 1


def test_the_unresolved_type_is_reported_rather_than_dropped_silently():
    plan = _plan()
    assert any("does not declare" in why for _, why in plan.skipped)


def test_the_type_name_survives_on_the_parameter_even_with_no_class_node():
    """Nothing is lost — only the traversal is absent, correctly."""
    plan = _plan()
    query = next(n for n in plan.nodes
                 if n.label == "Parameter" and n.properties["location"] == "query")
    assert query.properties["type_name"] == "int"


def test_a_generic_response_mentions_every_type_it_names():
    assert type_names_in("PageDto<EnvironmentDto>") == ["PageDto", "EnvironmentDto"]
    assert type_names_in("List<MetricTrendPointDto>") == ["List", "MetricTrendPointDto"]
    assert type_names_in("") == []


# --------------------------------------------------------------------------
# The join the two packs need.
# --------------------------------------------------------------------------

def test_the_two_packs_endpoint_keys_are_joined():
    """The behaviour pack keys on handler+verb because it owns no routes; the
    structural pack keys on method+path. Without the join,
    `Endpoint-[:DECLARES]->DeclaredOutcome` is catalogued and never written."""
    by_handler = endpoints_by_handler(_structural(), REPO)
    assert by_handler["c.MetricController.save:R(D)::POST"] == \
           endpoint_id(REPO, "POST", "/metric")
    assert _edges(_plan())["Endpoint-DECLARES->DeclaredOutcome"] == 1


def test_an_outcome_whose_endpoint_was_never_recovered_still_lands():
    """O-2c: a recovery gap. The node keeps its `endpoint_ref` so the join can be
    made later; dropping it would lose a real fact."""
    behaviour = _behaviour()
    behaviour.outcomes[0] = OutcomeFact(
        id="ghost::200", endpoint_id="GhostController.x::GET",
        signature="200/ok", status=200, discriminator="ok", anchor=A)
    plan = _plan(behaviour=behaviour)
    outcome = next(n for n in plan.nodes if n.label == "DeclaredOutcome")
    assert outcome.properties["endpoint_ref"] == "GhostController.x::GET"
    assert _edges(plan)["Endpoint-DECLARES->DeclaredOutcome"] == 0
    assert any("no endpoint" in why for _, why in plan.skipped)


def test_a_guard_reaches_the_check_that_justifies_it():
    assert _edges(_plan())["DeclaredOutcome-GUARDED_BY->Check"] == 1


# --------------------------------------------------------------------------
# D-13: the call graph is landed ahead of its reader, reversibly.
# --------------------------------------------------------------------------

def test_the_call_graph_can_be_left_out_without_a_code_change():
    """D-1 requires a reader. Impact analysis — `Method`'s stated trigger — is
    not built, so the flag keeps that choice reversible."""
    assert _labels(_plan(include_call_graph=True))["Method"] == 1
    assert _labels(_plan(include_call_graph=False))["Method"] == 0


def test_leaving_out_the_call_graph_keeps_the_rest_intact():
    plan = _plan(include_call_graph=False)
    assert plan.is_legal, plan.errors
    labels = _labels(plan)
    assert labels["Endpoint"] == 1 and labels["Field"] == 2
    assert _edges(plan)["Endpoint-HANDLED_BY->Method"] == 0


# --------------------------------------------------------------------------
# Degrading honestly.
# --------------------------------------------------------------------------

def test_a_missing_behaviour_report_yields_a_partial_layer_not_an_error():
    plan = plan_raw_landing(_structural(), journey="athena", repo=REPO)
    assert plan.is_legal
    assert _labels(plan)["Endpoint"] == 1
    assert _labels(plan)["DeclaredOutcome"] == 0


def test_the_field_id_is_keyed_on_its_owning_type():
    """Two DTOs both declaring `id` must not become one node."""
    assert field_id(REPO, "MetricDto", "id") != field_id(REPO, "ProjectDto", "id")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:                                    # noqa: BLE001
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
