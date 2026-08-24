"""
The annotation vocabulary (spec X-4, X-10b, §5.8).

**Métis defines the roles; a config says which annotations play them.** The role
set is closed for the same reason the ontology is: a role with no code behind it
is a promise the extractor cannot keep. These tests pin the refusals, because a
config that is accepted and then contributes nothing produces an extraction that
finds nothing and reports "no behaviour".

Free to run: pure.
"""
import pytest

from code_analysis.annotations import (
    ROLES,
    SCHEMES,
    AnnotationInvalid,
    AnnotationSpec,
    describe,
    load,
    merge,
    to_pack_table,
)


def test_the_role_set_is_closed_and_an_unknown_one_names_the_known():
    with pytest.raises(AnnotationInvalid) as e:
        load({"ProjectThing": {"role": "put_it_somewhere_useful"}})
    for role in ROLES:
        assert role in str(e.value), f"{role} is not offered in the refusal"
    assert "cannot keep" in str(e.value)


def test_an_entry_point_without_a_verb_is_refused():
    """Without one the trigger has no method and every route collides."""
    with pytest.raises(AnnotationInvalid) as e:
        load({"ProjectRead": {"role": "entry_point"}})
    assert "needs a verb" in str(e.value)
    assert load({"ProjectRead": {"role": "entry_point", "verb": "GET"}})["ProjectRead"].detail == "GET"


def test_a_security_annotation_without_a_scheme_is_refused():
    """`role` reads arguments as role names, `expression` keeps them verbatim —
    a reviewer weighs them differently, so the difference cannot be guessed."""
    with pytest.raises(AnnotationInvalid) as e:
        load({"ProjectSecured": {"role": "security"}})
    for scheme in SCHEMES:
        assert scheme in str(e.value)


def test_a_verb_that_is_not_a_verb_is_refused():
    with pytest.raises(AnnotationInvalid):
        load({"ProjectRead": {"role": "entry_point", "verb": "FETCH"}})


def test_roles_needing_nothing_take_nothing():
    for role in ("route_prefix", "validation", "schema", "outbound_client",
                 "ignore", "exception_mapping", "outcome_status"):
        assert load({"X": {"role": role}})["X"].role == role


def test_a_leading_at_sign_is_accepted_because_people_write_it():
    assert "ProjectSecured" in load({"@ProjectSecured": {"role": "ignore"}})


def test_declaring_one_twice_is_refused():
    # A dict cannot hold a duplicate key, so the collision that matters is
    # `@X` and `X` in the same file — which reads as two and is one.
    with pytest.raises(AnnotationInvalid) as e:
        load({"@ProjectSecured": {"role": "ignore"}, "ProjectSecured": {"role": "ignore"}})
    assert "accident of file order" in str(e.value)


# --------------------------------------------------------------------------
# The two layers
# --------------------------------------------------------------------------

def test_a_project_overrides_the_framework_and_it_is_visible():
    framework = load({"GetMapping": {"role": "entry_point", "verb": "GET"}})
    project = load({"GetMapping": {"role": "ignore"},
                    "ProjectSecured": {"role": "security", "scheme": "role"}})
    merged = merge(framework, project)
    assert merged["GetMapping"].role == "ignore", "the project wins"
    assert "[project]" in describe(framework, project), "and it is not silent"


def test_the_shipped_spring_table_covers_what_the_packs_hardcoded():
    """Everything the packs carried as literals is now declared in one place."""
    from code_analysis.framework_config import default

    spring = default().get("spring-mvc", "api").annotations
    for name in ("GetMapping", "PostMapping", "RequestMapping", "ResponseStatus",
                 "ExceptionHandler", "PreAuthorize", "Secured", "Valid",
                 "FeignClient"):
        assert name in spring, f"@{name} was hardcoded in a pack and is not declared"
    assert spring["FeignClient"].role == "outbound_client"
    assert spring["GetMapping"].detail == "GET"
    # springdoc: 71 @Schema in one service, none of them read before this.
    assert spring["Schema"].role == "schema"


# --------------------------------------------------------------------------
# What the packs receive
# --------------------------------------------------------------------------

def test_the_pack_table_is_three_tab_separated_fields():
    """Not JSON: a pack is Scala run by Joern, and a parser there is a
    dependency inside the one place X-3 pins to an exact engine build."""
    table = to_pack_table(load({
        "GetMapping": {"role": "entry_point", "verb": "GET"},
        "Valid": {"role": "validation"}}))
    rows = [l for l in table.splitlines() if not l.startswith("#")]
    assert rows == ["GetMapping\tentry_point\tGET", "Valid\tvalidation\t"]


def test_the_engine_merges_both_layers_into_the_table():
    from code_analysis.engine import annotation_table

    table = annotation_table("spring-mvc", load(
        {"ProjectSecured": {"role": "security", "scheme": "role"}}))
    assert "ProjectSecured\tsecurity\trole" in table
    assert "GetMapping\tentry_point\tGET" in table


def test_a_profiles_raw_json_reaches_the_table():
    """**The shape a real profile actually has**, and it used to crash.

    `annotation_table` passed the profile's raw JSON straight into `merge`, which
    wants parsed specs, so a project declaring even one annotation raised
    `AttributeError: 'dict' object has no attribute 'name'`. The whole
    project-annotation feature therefore worked only for a profile that declared
    nothing. Nothing caught it: this test used to pre-parse with `load`, which is
    the one input shape a profile never provides.
    """
    import json
    from code_analysis.engine import annotation_table

    raw = json.loads('{"ProjectSecured": {"role": "security", "detail": "role"},'
                     ' "Audited": {"role": "ignore"}}')
    table = annotation_table("spring-mvc", raw)
    assert "ProjectSecured\tsecurity\trole" in table
    assert "Audited\tignore\t" in table
    assert "GetMapping\tentry_point\tGET" in table, "the framework layer survives"


def test_a_profile_declaring_an_unknown_role_is_refused_at_the_table():
    """The validation `load` performs must not be skippable by going through the
    engine, which is the path a real run takes."""
    from code_analysis.engine import annotation_table

    try:
        annotation_table("spring-mvc", {"Whatever": {"role": "nonsense"}})
    except AnnotationInvalid as e:
        assert "nonsense" in str(e) and "entry_point" in str(e), str(e)
    else:
        raise AssertionError("an unknown role reached the packs")


def test_an_undeclared_framework_yields_only_the_project_table():
    """Reported by `analyse`'s X-4 check before extraction; here it must at
    least not invent a framework's annotations."""
    from code_analysis.engine import annotation_table

    table = annotation_table("no-such-framework", None)
    assert [l for l in table.splitlines() if not l.startswith("#")] == []
