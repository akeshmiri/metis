"""
The query packs, run for real against the demo corpus (spec §13.2, §13.4, X-3, X-5).

**NOT free to run.** Every other test file in this suite is pure; this one builds
a CPG with Joern and executes the shipped `query.sc` packs over it. That is the
point. `test_code_analysis.py` covers the contract and the mapper — both pure —
and the packs themselves had no behavioural test whatsoever: the only assertions
on them were greps for a string inside the Scala, and their correctness claims
lived as prose in `pack.yaml` naming private repositories.

Every number below came from running the packs, never from a prediction. When a
real project exposes a defect, the condition that caused it belongs in
`demo_project/` and its assertion belongs here.
"""
from __future__ import annotations

import collections

from code_analysis import synthesis
from code_analysis.contract import validate_report
from metis_mcp.mbt.test_levels import (
    COVERED,
    OUTCOME_UNPROVEN,
    UNCOVERED,
    from_pack,
    grade_transitions,
)
from metis_mcp.model_sources.sources import _report_from_dict

# The recovered surface. Seven, not nine: `ArchiveClient` declares two mappings
# and is a @FeignClient, so they are calls this service MAKES.
EXPECTED_ENDPOINTS = {
    ("GET", "/record"),
    ("POST", "/record"),
    ("GET", "/record/{id}"),
    ("PUT", "/record/{id}"),
    ("DELETE", "/record/{id}"),
    ("POST", "/record/{id}/archive"),
    ("POST", "/record/batch"),
    ("GET", "/record/page"),
    ("GET", "/record/{id}/label"),
    ("GET", "/summary/{id}"),
}


def _routes(structural) -> set[tuple[str, str]]:
    return {(e["http_method"], e["path"]) for e in structural["endpoints"]}


# --------------------------------------------------------------------------
# The report is valid before anything is read out of it
# --------------------------------------------------------------------------

def test_both_reports_satisfy_the_contract(demo_structural, demo_behaviour):
    assert validate_report(_report_from_dict(demo_structural)) == []
    assert validate_report(_report_from_dict(demo_behaviour)) == []


def test_x5_nothing_was_left_unparsed(demo_structural):
    """A file that produced no type declaration means the frontend failed on it,
    and a partial extraction reported as total is the worst outcome available."""
    assert demo_structural["parse_errors"] == []
    assert demo_structural["partial"] is False


# --------------------------------------------------------------------------
# Endpoint recovery
# --------------------------------------------------------------------------

def test_every_endpoint_is_recovered_exactly(demo_structural):
    assert _routes(demo_structural) == EXPECTED_ENDPOINTS


def test_a_route_composed_from_constants_is_resolved_not_invented(demo_structural):
    """`ArchiveController` writes no path literal at all: the class prefix is
    `BASE` and the method's is `ID_SEGMENT + "/archive"`, itself built from
    another constant. A resolver that accepts only a leading quote fabricates a
    path here, and a fabricated route generates a test case nobody can run.
    """
    assert ("POST", "/record/{id}/archive") in _routes(demo_structural)


def test_an_outbound_client_is_not_an_api_surface(demo_structural):
    """`@FeignClient` mappings are calls this service makes of another one."""
    handlers = {e["handler_type"] for e in demo_structural["endpoints"]}
    assert "ArchiveClient" not in handlers
    assert not any("/store" in p for _, p in _routes(demo_structural))


def test_a_project_annotation_is_understood_only_because_the_profile_says_so():
    """`@DemoSecured` is known to nothing Métis ships. The profile is the only
    reason it becomes a declared security fact.

    This is also the regression test for `engine.annotation_table`, which handed
    a profile's raw JSON straight into `merge` and raised `AttributeError` for any
    project that declared an annotation at all — so the feature worked only for a
    profile that used none of it.
    """
    from code_analysis.engine import annotation_table

    table = annotation_table("spring-mvc", {"DemoSecured": {"role": "security",
                                                            "detail": "role"}})
    assert "DemoSecured\tsecurity\trole" in table


def test_the_declared_security_lands_on_exactly_the_annotated_handlers(demo_structural):
    secured = {e["handler_name"] for e in demo_structural["endpoints"] if e["security"]}
    assert secured == {"create", "remove"}, (
        "an endpoint with no entry declared nothing — never that it is open")


def test_validation_is_recorded_where_it_is_declared(demo_structural):
    validated = {e["handler_name"] for e in demo_structural["endpoints"] if e["validated"]}
    assert validated == {"create", "replace", "submitBatch"}


# --------------------------------------------------------------------------
# Rejection paths — every one of these was reported as ZERO before the demo
# --------------------------------------------------------------------------

def test_exception_mappings_are_recovered_from_a_constructed_status(demo_structural):
    """**`ResponseEntity.status(HttpStatus.X).body(...)` is the only form that can
    carry a body with a 4xx** — `notFound()` returns a HeadersBuilder — so it is
    what every real error handler writes. The constructor table matched bare
    method names only, so all four handlers here resolved to nothing and
    `exception_mappings` came back 0.
    """
    got = {(m["exception_type"], m["status"], m["advice_type"])
           for m in demo_structural["exception_mappings"]}
    assert got == {
        ("RecordNotFoundException", 404, "RecordAdvice"),
        ("RecordConflictException", 409, "RecordAdvice"),
        ("RecordLockedException", 423, "RecordAdvice"),
        ("RecordLockedException", 409, "LegacyAdvice"),
        ("SummaryUnavailableException", 422, "ScopedController"),
    }


def test_a_rejection_carries_its_body_type(demo_structural):
    """An empty `response_body` is a claim that there is NO body, and a generated
    case would assert it. Every rejection here answers with `ErrorDto`."""
    assert {m["response_body"] for m in demo_structural["exception_mappings"]} == {"ErrorDto"}


# --------------------------------------------------------------------------
# Outcomes: the status must be the real one
# --------------------------------------------------------------------------

def test_a_builder_chain_does_not_collapse_to_200(demo_behaviour):
    """`returnCalls` takes the direct child of `return`, which for
    `noContent().build()` is `build` and for `status(CREATED).body(x)` is `body`.
    Neither carries a status, so both fell through to the spring-serialisation
    default and were reported as **200** — a 201 and a 204 silently wrong.
    """
    by_status = collections.Counter(o["status"] for o in demo_behaviour["outcomes"])
    assert by_status == {200: 7, 201: 1, 202: 1, 204: 2}


def test_the_discriminator_names_what_set_the_status(demo_behaviour):
    """It becomes a state name a person reads. Named after the trailing builder
    call it produced `RecordCreateBody201` and `RecordRemoveBuild204`."""
    named = {o["status"]: o["discriminator"] for o in demo_behaviour["outcomes"]}
    assert named[201] == "created"
    assert named[204] == "noContent"


def test_response_status_and_construction_are_distinguished(demo_behaviour):
    links = {o["status"]: o["link"] for o in demo_behaviour["outcomes"]}
    assert links[202] == "response-status", "@ResponseStatus(ACCEPTED) on a void handler"
    assert links[201] == "constructed", "status(CREATED).body(...)"


# --------------------------------------------------------------------------
# Synthesis: what a reviewer actually sees
# --------------------------------------------------------------------------

def _synthesise(structural, behaviour):
    return synthesis.synthesise(
        _report_from_dict(behaviour), structural["endpoints"],
        journey="records", surface="api", structural=_report_from_dict(structural))


def test_the_model_covers_every_endpoint_and_the_scoped_rejection(
        demo_structural, demo_behaviour):
    model = _synthesise(demo_structural, demo_behaviour).model
    triggers = collections.Counter(t.trigger for t in model.transitions.values())
    assert len(model.transitions) == 12
    assert triggers["GET /summary/{id}"] == 2, "a 200 and the scoped 422"
    # Named from the route since I-2, so that the code intake and the OpenAPI
    # intake reach the SAME node for one behaviour — see `landing.
    # graph_transition_id`. The scoped 422 is still its own state; only the
    # basis of its name changed.
    states = {model.states[t.target].name for t in model.transitions.values()}
    assert "GetSummaryId422" in states


def test_gd9_a_contested_exception_is_reported_and_not_resolved(
        demo_structural, demo_behaviour):
    """Two advices map `RecordLockedException` to different statuses and neither
    declares an `@Order`. Precedence is not statically decidable, so picking one
    would be a guess dressed as a finding."""
    findings = _synthesise(demo_structural, demo_behaviour).findings
    contested = [f for f in findings if "more than one status" in f]
    assert len(contested) == 1
    assert "RecordLockedException" in contested[0]


def test_an_estate_wide_rejection_is_reported_rather_than_dropped(
        demo_structural, demo_behaviour):
    """A `@ControllerAdvice` applies to every controller, so nothing says which
    endpoints reach the throw and no transition is attributed. Saying nothing at
    all is how a recovered 404 disappears between two stages that both report
    success."""
    findings = _synthesise(demo_structural, demo_behaviour).findings
    estate = [f for f in findings if "estate-wide @ControllerAdvice" in f]
    assert {"RecordNotFoundException", "RecordConflictException"} <= {
        f.split()[0] for f in estate}


# --------------------------------------------------------------------------
# The existing-test inventory (REQ-METIS-PG-01)
# --------------------------------------------------------------------------

def test_the_test_inventory_is_read_from_a_test_rooted_cpg(demo_inventory):
    """javasrc2cpg ignores test directories **by name** — a `src/test/java` file
    with no imports at all is still dropped, and rooting the parse at `src` does
    not help. This was recorded as a dependency-resolution problem pointing at
    `--fetch-dependencies`, which reaches Maven Central and would not have helped.
    """
    assert demo_inventory["feign_routes_indexed"] == 3
    got = {(t["owner"], t["name"]) for t in demo_inventory["tests"]}
    assert got == {("RecordControllerIT", "shallReadOne"),
                   ("RecordControllerIT", "shallCreate"),
                   ("RecordControllerIT", "shallRemove")}


def test_an_assertion_one_hop_inside_a_helper_is_still_found(demo_inventory):
    """`shallCreate` asserts 201 inside a private helper. Collecting literals from
    the test method alone grades a genuinely covered outcome as unproven."""
    create = next(t for t in demo_inventory["tests"] if t["name"] == "shallCreate")
    assert create["asserts"] == ["201"]


def test_a_test_whose_route_cannot_be_resolved_is_reported_never_credited(
        demo_inventory):
    """Crediting a bare literal would need a guess that this string is the route a
    model calls `/summary/{id}`, and a wrong guess excuses an untested endpoint."""
    assert [u["name"] for u in demo_inventory["unresolved"]] == [
        "shallReachSummaryByLiteralPath"]


def test_the_anchor_stays_repo_relative_despite_the_test_rooted_parse(
        demo_inventory):
    """The CPG is rooted inside the repo, so its filenames start at
    `com/example/...`. `service_of_path` read `com` as the module name, every test
    was scoped to a service called `com`, and three recovered tests graded eight
    transitions as uncovered."""
    files = {t["anchor"]["file"] for t in demo_inventory["tests"]}
    assert all(f.startswith("src/test/java/") for f in files), files


def test_generation_is_additive_against_the_recovered_inventory(
        demo_structural, demo_behaviour, demo_inventory):
    """REQ-METIS-PG-01, end to end and for the first time with real recovered
    tests. The middle grade is the one that matters: `shallRemove` reaches
    `DELETE /record/{id}` and asserts no status, which is neither covered nor
    uncovered."""
    model = _synthesise(demo_structural, demo_behaviour).model
    grades = grade_transitions(model, from_pack(demo_inventory))
    by_trigger = {model.transitions[tid].trigger: g.grade for tid, g in grades.items()}
    assert by_trigger["GET /record/{id}"] == COVERED
    assert by_trigger["POST /record"] == COVERED
    assert by_trigger["DELETE /record/{id}"] == OUTCOME_UNPROVEN
    assert by_trigger["GET /record"] == UNCOVERED
    assert not any(g.should_generate for g in grades.values() if g.grade == COVERED)


# --------------------------------------------------------------------------
# Code against contract — the same service described twice, on purpose
# --------------------------------------------------------------------------
#
# `demo_project/openapi.json` disagrees with the Java in three ways, one per
# category of deviation. They are asserted structurally — each lands in exactly
# one bucket and no fourth appears — so these survive the corpus growing.

import json as _json
from pathlib import Path as _Path

CONTRACT = _Path(__file__).parent / "demo_project" / "openapi.json"


def _contract_routes() -> set[tuple[str, str]]:
    from code_analysis.openapi import load, to_dict, to_report

    result = to_report(load(str(CONTRACT)), repo="demo-records", commit="demo")
    report = to_dict(result.report)
    return {(e["http_method"], e["path"]) for e in report["endpoints"]}


def test_the_contract_is_read_by_the_openapi_intake():
    assert len(_contract_routes()) == 10


def test_the_three_deviations_and_no_others(demo_structural):
    code = _routes(demo_structural)
    contract = _contract_routes()
    assert contract - code == {("POST", "/record/{id}/restore")}, "contract-only"
    assert code - contract == {("POST", "/record/{id}/archive")}, "code-only"
    assert len(code & contract) == 9, "everything else agrees on its route"


def test_the_disagreement_is_on_a_route_both_sources_declare(demo_behaviour):
    """`DELETE /record/{id}`: the contract documents 200, the code returns 204
    from `ResponseEntity.noContent()`. Route agreement is not outcome agreement,
    and this is the deviation a route-level comparison cannot see."""
    contract = _json.loads(CONTRACT.read_text())
    documented = set(contract["paths"]["/record/{id}"]["delete"]["responses"])
    assert documented == {"200"}

    remove = next(o for o in demo_behaviour["outcomes"]
                  if o["discriminator"] == "noContent")
    assert remove["status"] == 204


def test_the_two_sources_mint_different_ids_for_the_same_endpoint(demo_structural):
    """Recorded because it is the reason the two intakes cannot simply both be
    landed into one journey: they agree on the route and disagree on the id, so a
    naive merge produces two disjoint machines in one model rather than one model
    with two sources. `identity.keys.transition_key` is the natural key that
    fixes it, and landing does not use it yet.
    """
    from code_analysis.openapi import load, to_dict, to_report

    contract = to_dict(to_report(load(str(CONTRACT)), repo="d", commit="c").report)
    contract_ids = {e["id"] for e in contract["endpoints"]}
    code_ids = {e["id"] for e in demo_structural["endpoints"]}

    assert contract_ids & code_ids == set(), "no id is shared"
    assert "getRecord::GET" in contract_ids, "the contract keys on operationId"
    assert any(i.startswith("com.example.records.RecordController.one:")
               for i in code_ids), "the code keys on the handler signature"


# --------------------------------------------------------------------------
# The UI surfaces
# --------------------------------------------------------------------------

def test_routes_come_from_the_router_config(demo_ui):
    """jssrc2cpg lowers `createBrowserRouter([{path: '/x'}])` into an assignment
    `_tmp.path = "/x"`, so the key is structurally present even though the JSX is
    not. `<Route path="...">` in JSX stays unrecoverable and is not guessed at."""
    assert sorted(r["path"] for r in demo_ui["routes"]) == [
        "/", "/records", "/records/:id", "/summary/:id"]


def test_a_regex_literal_is_not_a_route(demo_ui):
    """**The refusal is what makes the recogniser worth anything.** A JS regex
    reaches the extractor as `/\\s+/g` — it starts with `/` exactly like a path.
    Run against a real React app the earlier detector reported six routes and all
    six were false positives, which is worse than reporting none (X-4)."""
    paths = {r["path"] for r in demo_ui["routes"]}
    assert not any("\\s" in p or p.endswith("/g") or p.endswith("/gi")
                   for p in paths), paths
    assert len(paths) == 4, "four routes exist and nothing else was admitted"


def test_an_interpolated_path_is_reported_not_resolved(demo_ui):
    """`requestJson(apiRoots.record, `/${id}`)` lowers to
    `<operator>.formatString("/", id, "")`. Reading its first literal fragment
    reported the endpoint as `/record/` — not the route, not the fragment, and
    marked as neither."""
    reasons = {u["reason"] for u in demo_ui["unresolved_calls"]}
    assert any("template literal" in r for r in reasons), reasons
    assert not any(c["endpoint"] == "/record/" and c["screen"] == "RecordDetailPage"
                   for c in demo_ui["api_calls"])


def test_the_ui_state_vocabulary_is_recovered_including_ternary_branches(demo_ui):
    """`setStatus(record ? "ready" : "error")` is two real states, and reading
    only the immediate argument found neither — a ternary is a call, so
    `argument.isLiteral` is empty.

    The setter pattern is `set<Name>Status`. It was a literal list naming two
    screens from the codebase the pack was first written against, which made
    every other project's setter invisible.
    """
    got = {(s["setter"], s["value"]) for s in demo_ui["ui_states"]}
    assert ("setStatus", "loading") in got
    assert ("setSummaryStatus", "ready") in got, "a differently-named setter"
    assert ("setSummaryStatus", "error") in got, "the other ternary branch"


def test_the_dom_pack_reads_handlers_a_react_app_does_not_have(demo_page):
    """`js-ui` keys on `addEventListener`, of which a React application has none.
    The two packs exist because the two shapes differ; this pack was marked
    `unwired` and verified only against a repository nobody else can check out."""
    assert len(demo_page["triggers"]) == 5
    assert len(demo_page["api_calls"]) == 2


def test_a_selector_is_extracted_from_the_code_that_looks_it_up(demo_page):
    """**Selectors are extracted, never authored.** They were briefly a field
    somebody filled in by hand, and that was the wrong source: a plain-DOM page
    names its elements in its own code — `document.getElementById("archive")` —
    and that literal is structurally recoverable where a JSX prop is not.
    """
    resolved = {t["element"]: t["selector"] for t in demo_page["triggers"]
                if t["selector"]}
    assert resolved == {"filterOwner": "#filter-owner",
                        "applyFilter": "#apply-filter",
                        "archiveButton": "#archive",
                        "newRecord": "#new-record"}


def test_an_element_reached_by_walking_the_dom_is_reported_unresolved(demo_page):
    """`exportButton` is `rows.querySelector("tr").children[2].firstElementChild`
    — no literal names it, and the walk's own `"tr"` is emphatically not its
    selector. A wrong selector in a Page Object fails at run time against the
    wrong element, which is worse than a stub that refuses to run."""
    export = next(t for t in demo_page["triggers"] if t["element"] == "exportButton")
    assert export["selector"] == ""
    assert "walking the DOM" in export["selector_link"]


# --------------------------------------------------------------------------
# Intake noise — what extraction deliberately leaves out (X-5a, A-6a)
# --------------------------------------------------------------------------
#
# A 12-endpoint service put 389 methods into the graph and 189 were accessors or
# generated boilerplate. The reduction is worth having, and every assertion here
# is about not overreaching: the three KEPT cases are the point of the tests, not
# the dropped ones.

def _names(structural) -> set[str]:
    return {m["name"] for m in structural["methods"]}


def test_inert_accessors_and_boilerplate_are_dropped(demo_structural):
    dropped = {"getTitle", "setTitle", "getOwner", "setOwner", "isArchived",
               "setArchived", "equals", "hashCode", "toString"}
    assert dropped & _names(demo_structural) == set()


def test_a_getter_that_branches_is_kept(demo_structural):
    """`getDisplayLabel()` is named like an accessor, has no field behind it, and
    branches on `archived`. A filter keyed on the name alone deletes a real
    decision — which is why the test is that this one SURVIVES."""
    assert "getDisplayLabel" in _names(demo_structural)


def test_a_getter_named_after_a_real_field_that_branches_is_still_kept(
        demo_structural):
    """**This is the case that actually tests the body check**, and it was missing.

    `getRetries()` has a field `retries` behind it, so the name-and-field test
    calls it an accessor; only the body check saves it. Found by deleting the body
    check and watching every test still pass — `getDisplayLabel` has no matching
    field, so it is caught one condition earlier and leaves this one unproven.
    """
    assert "getRetries" in _names(demo_structural)


def test_a_private_method_that_carries_behaviour_is_kept(demo_structural):
    """**Visibility is the wrong axis, and this is the case that proves it.**
    `requireSummarisable` is private, guards `GET /summary/{id}` and raises the
    exception `ScopedController`'s own `@ExceptionHandler` maps to 422. Measured
    on a real service, `private` was 59 of 389 methods and two of them were
    reachable from a handler — so filtering on it deletes a rejection path and
    leaves every getter in place.
    """
    assert "requireSummarisable" in _names(demo_structural)


def test_the_fields_an_accessor_exposed_are_untouched(demo_structural):
    """`@Schema`, `@NotBlank` and `@Size` sit on the field, not on its getter, and
    they are test-design inputs. Dropping `getTitle` must not drop `title` —
    which is also why "drop private" would be exactly backwards for members."""
    summary = [m for m in demo_structural["members"]
               if m.get("type_name") == "RecordSummaryDto"]
    assert {m["name"] for m in summary} >= {"title", "owner", "archived"}
    titled = next(m for m in summary if m["name"] == "title")
    assert titled.get("description"), "the @Schema description survived"
    assert titled.get("constraints"), "the validation constraints survived"


def test_the_reduction_is_reported_never_silent(demo_structural):
    """A reduction nobody can see is indistinguishable from a codebase that never
    had those elements — the same failure `partial` exists to prevent, one level
    down."""
    f = demo_structural["filtered"]
    assert f["accessors_dropped"] == 7, (
        "seven trivial accessors — six on RecordSummaryDto plus Mode.getFallback. "
        "getRetries and getDisplayLabel are NOT among them, which is the whole "
        "point of the two tests above")
    assert f["boilerplate_dropped"] == 3
    assert f["methods_declared"] == len(demo_structural["methods"]) + \
        f["accessors_dropped"] + f["boilerplate_dropped"], "the arithmetic closes"
    assert "dropNoise=no" in f["reason"], "the way to turn it off is in the report"


def test_nothing_downstream_of_the_filter_changed(demo_structural, demo_behaviour):
    """The filter is upstream of everything, so the cheapest way for it to be
    wrong is to take a method some later stage needed."""
    assert _routes(demo_structural) == EXPECTED_ENDPOINTS
    assert len(demo_structural["exception_mappings"]) == 5
    assert len(demo_behaviour["outcomes"]) == 11


def test_the_filter_can_be_turned_off_per_project(demo_profile):
    """`drop_noise: false` in the profile, for a codebase whose getters carry
    logic. Asserted on the extraction, because a flag that is read and ignored
    looks exactly like one that works."""
    import json

    from code_analysis import engine

    from conftest import PROFILE, SERVICE, tree_hash

    unfiltered = engine.extract(
        SERVICE, language="javasrc", project="demo-records-unfiltered",
        framework="spring-mvc", project_annotations=demo_profile["annotations"],
        commit=tree_hash(SERVICE, PROFILE), skip_preflight=True, drop_noise=False)
    report = json.loads(unfiltered.structural.read_text())
    assert "getTitle" in _names(report), "the accessor is back"
    assert report["filtered"]["accessors_dropped"] == 0


# --------------------------------------------------------------------------
# The payload graph and its validation (X-6b, A-6b)
# --------------------------------------------------------------------------

def _member(structural, owner: str, name: str) -> dict:
    return next(m for m in structural["members"]
                if m["type_name"] == owner and m["name"] == name)


def test_validation_lands_as_data_not_as_annotation_text(demo_structural):
    """`constraints: ["@Size(max = 40)"]` is a string every consumer must
    re-parse, and two consumers parsing it differently is a defect nobody can
    see. A boundary criterion needs the number."""
    field = _member(demo_structural, "RecordBatchDto", "submittedBy")
    assert field["expected_max_length"] == 40
    assert field["required"] == "true"


def test_overlapping_bounds_compose_to_the_strongest(demo_structural):
    """**This was affirmatively wrong, which is worse than missing.**
    `@NotBlank @Size(min = 3, max = 40)` means length >= 3. Taking the first
    constraint seen reported `expected_min_length: 1` from `@NotBlank` — weaker
    than the code — so a boundary case would offer a 1-character value as valid
    against a field that rejects it. Every constraint has to hold, so the
    effective minimum is the largest of them.
    """
    assert _member(demo_structural, "RecordBatchDto", "submittedBy")[
        "expected_min_length"] == 3


def test_size_on_a_collection_is_cardinality_not_length(demo_structural):
    """Calling both `max_length` would be a quiet lie about what a fixture has to
    build: forty characters and forty elements are different things."""
    tags = _member(demo_structural, "RecordBatchDto", "tags")
    assert tags["expected_min_size"] == 1 and tags["expected_max_size"] == 50
    assert "expected_max_length" not in tags


def test_a_pattern_is_carried_verbatim(demo_structural):
    assert _member(demo_structural, "RecordBatchDto", "reference")[
        "expected_pattern"] == "[A-Z]{2}-[0-9]{4}"


def test_the_raw_annotation_survives_alongside_the_typed_property(demo_structural):
    """The vocabulary is closed, so an annotation outside it becomes no property —
    and it has to stay visible here or it vanishes, which is X-5a's failure."""
    field = _member(demo_structural, "RecordBatchDto", "submittedBy")
    assert "@NotBlank" in field["constraints"]
    assert any("@Size" in c for c in field["constraints"])


def test_a_record_reads_its_annotations_from_the_canonical_constructor(
        demo_structural):
    """**A Java record puts component annotations on the constructor parameter,
    not the member.** Probed against `RecordDto`: every member reported an empty
    annotation list and every constructor parameter reported the real set, so a
    record DTO — increasingly the default shape for a Spring payload — landed
    with no descriptions, no constraints and no required-ness at all.
    """
    title = _member(demo_structural, "RecordDto", "title")
    assert title["description"] == "Human-readable title"
    assert title["required"] == "true"
    assert title["expected_max_length"] == 120


# --- the Enum specialisation ---

def test_an_enum_is_recognised_as_one(demo_structural):
    assert _member(demo_structural, "RecordDto", "visibility")["type_is_enum"]
    assert _member(demo_structural, "RecordBatchDto", "mode")["type_is_enum"]


def test_an_enums_constants_become_the_partitions_of_a_field_of_that_type(
        demo_structural):
    """An enum is the one type whose value space is fully known from source, so a
    field of that type needs no boundary analysis. Before this, `allowed_values`
    came only from `@Schema(allowableValues=...)` — a second, hand-written copy —
    and across a real service **zero** fields carried any."""
    allowed = _member(demo_structural, "RecordBatchDto", "mode")["allowed_values"]
    assert allowed == ["IMMEDIATE", "DEFERRED", "DRY_RUN"]
    # `Mode.fallback` is private, self-typed, and NOT a value a caller can send.
    # A real enum carried exactly that shape and it was reported as a fourth
    # constant, so a generated case would have offered it as input.
    assert "fallback" not in allowed


def test_a_hand_written_allowable_values_outranks_the_inference(demo_structural):
    """`RecordDto.visibility` declares them in `@Schema`. A person's statement
    beats an inference, even a sound one."""
    assert _member(demo_structural, "RecordDto", "visibility")["allowed_values"] == [
        "PRIVATE", "SHARED", "PUBLIC"]


# --- the nested payload ---

def test_a_collection_field_names_its_element_type(demo_structural):
    """`type_full_name` erases the generic: a `List<RecordDto>` field reports
    `java.util.List`, which is true and useless — the type a fixture builds is
    `RecordDto`, and stopping at the collection left every list-valued payload
    one level short."""
    records = _member(demo_structural, "RecordBatchDto", "records")
    assert records["type_full_name"] == "java.util.List"
    assert records["element_type"] == "RecordDto"


def test_the_payload_graph_reaches_the_nested_type(demo_structural):
    """Planned rather than landed, because the graph needs a database and this
    suite does not. What is asserted is that the edge is planned at all, and that
    it stops at the JDK boundary."""
    from metis_mcp.model_sources.raw_landing import plan_raw_landing
    from metis_mcp.model_sources.sources import _report_from_dict

    plan = plan_raw_landing(_report_from_dict(demo_structural),
                            journey="records", repo="demo-records",
                            job_id="test")
    # Type to type since X-6d, not field to type: which field carries it is on
    # `f_<name>_type`, because `landing.PlannedEdge` has no properties.
    nested = [e for e in plan.edges
              if e.rel_type == "OF_TYPE" and e.from_label in ("Class", "Enum")]
    assert nested, "a field's own type continues the payload graph"
    # And nothing was invented for a type this repository does not declare.
    targets = {e.to_label for e in nested}
    assert targets <= {"Class", "Enum"}


def test_an_enum_target_is_labelled_enum_not_class(demo_structural):
    """A specialisation is written INSTEAD of its parent, so an edge planned
    against `:Class` matches no enum node. That exact mistake left three
    `DECLARES_METHOD` edges unmatched against a real service — `is_allowed` walks
    the specialisation chain, so the ontology check passed and the merge found
    nothing."""
    from metis_mcp.model_sources.raw_landing import plan_raw_landing
    from metis_mcp.model_sources.sources import _report_from_dict

    # `include_call_graph=True` because the condition only exists there: the
    # call graph is off by default now, so `Mode.fromValue` is not landed and
    # `DECLARES_METHOD` never fires from an enum. The assertion below caught that
    # the moment the default flipped, which is what it is for.
    plan = plan_raw_landing(_report_from_dict(demo_structural),
                            journey="records", repo="demo-records",
                            job_id="test", include_call_graph=True)
    enum_nodes = {n.properties["id"] for n in plan.nodes if n.label == "Enum"}
    assert enum_nodes, "the demo declares two enums"
    # And one of them declares a method, which is what makes the check below
    # capable of failing: an enum with no methods never reaches DECLARES_METHOD.
    assert any(e.rel_type == "DECLARES_METHOD" and e.from_id in enum_nodes
               for e in plan.edges), (
        "no enum in the demo declares a method, so this test guards nothing — "
        "see RecordBatchDto.Mode.fromValue")
    for edge in plan.edges:
        if edge.to_id in enum_nodes:
            assert edge.to_label == "Enum", (
                f"{edge.rel_type} planned against {edge.to_label} for an enum node")
        if edge.from_id in enum_nodes:
            assert edge.from_label == "Enum", edge.rel_type


# --------------------------------------------------------------------------
# One behaviour, two intakes, one node (I-2, R12)
# --------------------------------------------------------------------------

def _both_models(demo_api):
    from metis_mcp.model_sources import get

    code = get("code").produce(path=str(demo_api.behaviour),
                               endpoints=str(demo_api.structural),
                               journey="records", surface="api").model
    spec = get("openapi").produce(path=str(CONTRACT), journey="records",
                                  surface="api").model
    return code, spec


def test_the_two_intakes_reach_the_same_node_for_the_same_behaviour(demo_api):
    """**The whole reason identity is a natural key.**

    A transition's id comes from whatever recovered it: the code intake mints a
    Java signature, the OpenAPI intake an operationId. Landed on those, one
    endpoint became two nodes and the graph claimed twice the behaviour the
    service has — with no edge between the halves and nothing reporting it.

    Ten of the demo's twelve code transitions are also in the contract, and all
    ten must land on one node each.
    """
    from metis_mcp.model_sources.landing import graph_transition_id

    code, spec = _both_models(demo_api)
    code_ids = {graph_transition_id(code, t) for t in code.transitions}
    spec_ids = {graph_transition_id(spec, t) for t in spec.transitions}
    assert len(code_ids & spec_ids) == 10, sorted(code_ids ^ spec_ids)[:4]


def test_the_leftovers_are_exactly_the_real_deviations(demo_api):
    """What does NOT merge is the answer to "where do the two disagree" — which
    stops being a hunt and becomes a set difference."""
    from metis_mcp.model_sources.landing import graph_transition_id

    code, spec = _both_models(demo_api)
    code_only = {code.transitions[t].trigger for t in code.transitions
                 if graph_transition_id(code, t) not in
                 {graph_transition_id(spec, s) for s in spec.transitions}}
    assert "POST /record/{id}/archive" in code_only, "code-only: undocumented"
    assert "DELETE /record/{id}" in code_only, (
        "the disagreement: the code answers 204, the contract documents 200")


def test_the_element_id_is_the_natural_key_not_the_source_id(demo_api):
    """A Java signature and an operationId are representation. Rename the
    handler and the id must not change (I-16) — which is the same property that
    makes two intakes converge."""
    from metis_mcp.model_sources.landing import graph_transition_id

    code, _ = _both_models(demo_api)
    tid = next(t for t in code.transitions if "create" in t)
    landed = graph_transition_id(code, tid)
    assert "com.example" not in landed, "no Java signature in the id"
    assert landed.startswith("records-api::")
