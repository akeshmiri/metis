"""
Test-level and existing-coverage tests (spec REQ-METIS-PG-01; §6.2, P-12).

Free to run: grading is pure.
"""
import sys

from metis_mcp.mbt.model import IMPLEMENTED, PLANNED, Model, State, Transition
from metis_mcp.mbt.test_levels import (
    API_FUNCTIONAL,
    COVERED,
    OUTCOME_UNPROVEN,
    UNCOVERED,
    ExistingTest,
    Inventory,
    expected_status,
    format_grades,
    from_pack,
    grade_transitions,
)


def _model() -> Model:
    m = Model(
        id="records-api",
        states={"Ready": State(id="Ready", name="Ready", surface="api", is_initial=True),
                "Ok200": State(id="Ok200", name="Ok200", surface="api"),
                "NoContent204": State(id="NoContent204", name="NoContent204", surface="api")},
        transitions={
            "ok": Transition(id="ok", source="Ready", trigger="GET /{id}",
                             target="Ok200", guard="NOT (t.isEmpty())"),
            "empty": Transition(id="empty", source="Ready", trigger="GET /{id}",
                                target="NoContent204", guard="t.isEmpty()"),
            "list": Transition(id="list", source="Ready", trigger="GET /all", target="Ok200"),
        })
    m.reindex()
    return m


def _inv(routes, asserts=()):
    return Inventory(tests=[ExistingTest(
        name="shallDoSomething", owner="RecordControllerIT", level=API_FUNCTIONAL,
        routes=tuple(routes), asserts=tuple(asserts))])


# --------------------------------------------------------------------------
# REQ-METIS-PG-01 : generation is additive
# --------------------------------------------------------------------------

def test_a_transition_whose_outcome_is_asserted_is_covered_and_skipped():
    grades = grade_transitions(_model(), _inv([("GET", "/metric/all")], ["200"]),
                               service="metric")
    assert grades["list"].grade == COVERED
    assert not grades["list"].should_generate
    assert "RecordControllerIT.shallDoSomething" in grades["list"].evidence


def test_a_transition_nothing_reaches_is_uncovered_and_generates():
    grades = grade_transitions(_model(), Inventory(), service="metric")
    assert all(g.grade == UNCOVERED for g in grades.values())
    assert all(g.should_generate for g in grades.values())


def test_the_reason_is_recorded_never_a_silent_skip():
    """P-12: the denominator is never quietly lowered."""
    grades = grade_transitions(_model(), _inv([("GET", "/metric/all")], ["200"]),
                               service="metric")
    assert grades["list"].detail
    assert "SKIP" in format_grades(grades, _model())


# --------------------------------------------------------------------------
# The subtlety: covering an ENDPOINT is not covering a TRANSITION
# --------------------------------------------------------------------------

def test_reaching_an_endpoint_does_not_excuse_an_unasserted_outcome():
    """The real the pilot estate case: a test calls GET /{id} and asserts 200. That is
    evidence for the 200 transition and says NOTHING about the 204 one."""
    grades = grade_transitions(
        _model(), _inv([("GET", "/metric/{id}")], ["200"]), service="metric")
    assert grades["ok"].grade == COVERED, "200 is asserted"
    assert grades["empty"].grade == OUTCOME_UNPROVEN, "204 is not"
    assert grades["empty"].should_generate, "an unproven outcome still generates"


def test_the_unproven_grade_is_distinct_from_both_others():
    """Promoting it to covered excuses gaps; demoting it to uncovered discards
    real evidence. It is its own grade."""
    grades = grade_transitions(
        _model(), _inv([("GET", "/metric/{id}")]), service="metric")
    assert grades["ok"].grade == OUTCOME_UNPROVEN
    assert grades["ok"].evidence, "the evidence is kept, not discarded"
    assert "happy path only" in grades["ok"].detail


def test_a_status_is_read_from_the_target_state_name():
    m = _model()
    assert expected_status(m.transitions["empty"], m) == "204"
    assert expected_status(m.transitions["ok"], m) == "200"


def test_a_state_naming_no_status_cannot_be_proven_by_a_status_assert():
    m = Model(
        id="x-api",
        states={"Ready": State(id="Ready", name="Ready", surface="api", is_initial=True),
                "Done": State(id="Done", name="Done", surface="api")},
        transitions={"t": Transition(id="t", source="Ready", trigger="GET /x", target="Done")})
    m.reindex()
    grades = grade_transitions(m, _inv([("GET", "/x")], ["200"]), service="x")
    assert grades["t"].grade == OUTCOME_UNPROVEN
    assert "not identifiable by status" in grades["t"].detail


# --------------------------------------------------------------------------
# Route normalisation — the conventions genuinely differ per service
# --------------------------------------------------------------------------

def test_both_prefixed_and_bare_routes_match():
    """metric's Feign declares `/metric/all`; core's declares `/environment/all`.
    Normalising to one form graded three whole services as uncovered."""
    prefixed = grade_transitions(_model(), _inv([("GET", "/metric/all")], ["200"]),
                                 service="metric")
    bare = grade_transitions(_model(), _inv([("GET", "/all")], ["200"]),
                             service="metric")
    assert prefixed["list"].grade == COVERED
    assert bare["list"].grade == COVERED


def test_another_services_test_never_credits_this_one():
    """Feign clients declare bare paths: git's test declares `GET /summary` and
    metric's declares `GET /metric/summary`. Unscoped, git's test credited
    metric's endpoint — excusing a genuinely untested endpoint with another
    service's test."""
    gits = Inventory(tests=[ExistingTest(
        name="shallReturnRepositoryDashboardSummary", owner="GitRepositoryControllerIT",
        level=API_FUNCTIONAL, routes=(("GET", "/summary"),), asserts=("200",),
        service="git")])
    m = _model()
    m.transitions["sum"] = Transition(id="sum", source="Ready", trigger="GET /summary",
                                      target="Ok200")
    m.reindex()
    grades = grade_transitions(m, gits, service="metric")
    assert grades["sum"].grade == UNCOVERED, "git's test must not cover metric"

    same = Inventory(tests=[ExistingTest(
        name="x", owner="RecordControllerIT", level=API_FUNCTIONAL,
        routes=(("GET", "/summary"),), asserts=("200",), service="metric")])
    assert grade_transitions(m, same, service="metric")["sum"].grade == COVERED


def test_the_service_defaults_to_the_first_path_segment():
    """No profile, no convention: the module is the directory it is in.

    This used to be a regex matching one estate's directory naming, compiled into
    the engine. Against any other layout it matched nothing and `--service`
    reported "nothing recognisable" — true of the regex, false of the code.
    """
    from metis_mcp.mbt.test_levels import service_of_path

    assert service_of_path("records-service/src/main/java/X.java") == "records-service"
    assert service_of_path("archive-service/src/it/java/X.java") == "archive-service"
    assert service_of_path("X.java") == ""
    assert service_of_path("") == ""


def test_a_build_layout_directory_is_not_a_service_name():
    """A single-module repository has paths starting `src/`, and answering "src"
    was worse than answering nothing: `Inventory.reaching` treats "" as unscoped
    and still matches on the route, where a wrong service name blocks every match.
    Three recovered tests graded eight transitions as uncovered that way."""
    from metis_mcp.mbt.test_levels import service_of_path

    assert service_of_path("src/test/java/com/example/records/RecordIT.java") == ""
    assert service_of_path("main/java/X.java") == ""
    assert service_of_path("target/classes/X.java") == ""


def test_a_project_profile_overrides_the_default():
    """The migration path: any convention is expressible, none is assumed."""
    import re

    from metis_mcp.mbt.test_levels import service_of_path, set_service_resolver

    try:
        # A real convention: the deployable is named by a suffixed directory,
        # `<name>-boot/`, and everything else belongs to no module.
        pattern = re.compile(r"^([a-z]+)-boot/")
        set_service_resolver(
            lambda p: (pattern.search(p).group(1) if pattern.search(p) else ""))
        assert service_of_path("records-boot/src/it/java/X.java") == "records"
        assert service_of_path("records-service/src/main/java/X.java") == ""
    finally:
        set_service_resolver(None)
    # and it is really reset, so one test cannot leak a convention into another
    assert service_of_path("records-service/src/main/java/X.java") == "records-service"


def test_the_model_id_strip_takes_only_the_surface():
    """M-1 says `<journey>-<surface>`; it says nothing about a prefix."""
    from metis_mcp.mbt.test_levels import _service_of

    assert _service_of(Model(id="records-api")) == "records"
    assert _service_of(Model(id="records-api")) == "records"


def test_the_verb_must_still_match():
    grades = grade_transitions(_model(), _inv([("POST", "/metric/all")], ["200"]),
                               service="metric")
    assert grades["list"].grade == UNCOVERED


def test_a_non_http_trigger_is_uncovered_not_crashed():
    m = Model(
        id="login-api",
        states={"A": State(id="A", name="A", surface="api", is_initial=True),
                "B": State(id="B", name="B", surface="api")},
        transitions={"t": Transition(id="t", source="A", trigger="submit_credentials",
                                     target="B")})
    m.reindex()
    grades = grade_transitions(m, Inventory(), service="login")
    assert grades["t"].grade == UNCOVERED
    assert "not an HTTP route" in grades["t"].detail


def test_planned_transitions_are_not_graded():
    """P-11: nothing built, nothing to cover."""
    m = _model()
    m.transitions["future"] = Transition(id="future", source="Ready", trigger="GET /new",
                                         target="Ok200", implementation_status=PLANNED)
    m.reindex()
    assert "future" not in grade_transitions(m, Inventory(), service="metric")


# --------------------------------------------------------------------------
# Reading the pack's output
# --------------------------------------------------------------------------

def test_an_inventory_is_built_from_the_pack_report():
    inv = from_pack({
        "tests": [{"name": "shallX", "owner": "RecordControllerIT",
                   "level": API_FUNCTIONAL,
                   "routes": [{"verb": "GET", "path": "/metric/all"}],
                   "asserts": ["200"],
                   "anchor": {"file": "a/b/RecordControllerIT.java", "line": 42}}],
        "unresolved": [{"name": "helperish", "reason": "no Feign route reached"}]})
    assert len(inv.tests) == 1
    assert inv.tests[0].anchor == "RecordControllerIT.java:42"
    assert inv.levels_present == {API_FUNCTIONAL}
    assert inv.unresolved == [("helperish", "no Feign route reached")]


def test_an_unresolved_test_covers_nothing_but_is_kept():
    """It must not silently license a duplicate, and must not vanish."""
    inv = from_pack({"tests": [], "unresolved": [{"name": "x", "reason": "y"}]})
    assert inv.reaching("GET", ("/anything",)) == []
    assert inv.unresolved


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
        except Exception as e:
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)


def test_an_unfolded_creator_is_still_gradeable():
    """**Two representations of one status, and the reader picked the fragile
    one.**

    `expected_status` read the status out of the TARGET STATE'S NAME —
    `Created201` yields 201. M-6 unfolding repoints a creator's target to the
    resource state it produces (`RecordPresent`), whose name carries no status,
    so the creator became ungradeable and dropped from `covered` to "this
    outcome is not identifiable by status" without anything reporting it.

    `unfolding` says of that repointing: "Its status is not lost -- it lives on
    `outcome_status`." That was true of the data and false of this reader.

    Latent rather than theoretical: every `*Present` state in a recovered model
    has a creator whose target was repointed, so every one was ungradeable. It
    stays invisible on a corpus where no existing test reaches a creator, which
    is why it survived — the graph was right and only the conclusion was wrong.
    """
    from metis_mcp.mbt.model import Model, State, Transition
    from metis_mcp.mbt.test_levels import expected_status

    unfolded = Model(
        id="records-api",
        states={"Record": State(id="Record", name="Record", is_initial=True),
                "RecordPresent": State(id="RecordPresent", name="RecordPresent")},
        transitions={"create": Transition(
            id="create", source="Record", trigger="POST /record",
            target="RecordPresent", outcome_status=201)},
    )
    assert expected_status(unfolded.transitions["create"], unfolded) == "201", (
        "an unfolded creator still answers 201; the state name just stopped "
        "saying so")


def test_the_target_name_is_still_read_when_the_transition_has_no_status():
    """The fallback stays: an authored model may name its states and carry no
    `outcome_status` at all, and that was the only source before."""
    from metis_mcp.mbt.model import Model, State, Transition
    from metis_mcp.mbt.test_levels import expected_status

    authored = Model(
        id="a-api",
        states={"Ready": State(id="Ready", name="Ready", is_initial=True),
                "Created201": State(id="Created201", name="Created201")},
        transitions={"t": Transition(id="t", source="Ready", trigger="POST /x",
                                     target="Created201")},
    )
    assert expected_status(authored.transitions["t"], authored) == "201"
