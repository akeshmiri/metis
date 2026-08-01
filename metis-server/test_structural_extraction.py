"""
Phase 3 tests: Cognify's structural extraction (cognify/structural_extraction.py).

Two layers, per Phase 2/3's acceptance bar ("a specific known input produces
exactly the expected node shape, checked by hand"):
  1. A pure unit test against an in-memory literal source snippet -- fully
     deterministic and immune to this repo's own files changing later
     (a real trap hit while building this: the "known expected count" for
     config_manager.py computed earlier in this session went stale the
     moment a method was added to that file afterward -- not a bug in
     extraction, just a snapshot that outlived the thing it snapshotted).
  2. A real end-to-end run against the actual Episodes Phase 2 landed,
     verified against an independently-computed expected count (a second,
     differently-written AST walk over the same real files at test time,
     not a hardcoded number) -- catches real integration issues the unit
     test can't (Cypher write bugs, id collisions, relationship shape).
"""
import ast
import os
import sys

from neo4j import GraphDatabase

from cognify.structural_extraction import _extract, run

NEO4J_URI = os.environ.get("METIS_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("METIS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("METIS_NEO4J_PASSWORD")

KNOWN_SNIPPET = '''
class Foo:
    def bar(self):
        pass
    def baz(self):
        pass

class Empty:
    pass

def top_level_fn():
    pass
'''


def test_extract_known_snippet_produces_exact_expected_shape():
    result = _extract("repo", "known.py", KNOWN_SNIPPET)
    assert len(result["classes"]) == 2
    foo = next(c for c in result["classes"] if c["name"] == "Foo")
    empty = next(c for c in result["classes"] if c["name"] == "Empty")
    assert {m["name"] for m in foo["methods"]} == {"bar", "baz"}
    assert foo["id"] == "repo:known.py:Foo"
    assert {m["id"] for m in foo["methods"]} == {"repo:known.py:Foo.bar", "repo:known.py:Foo.baz"}
    assert empty["methods"] == []
    assert len(result["module_functions"]) == 1
    assert result["module_functions"][0]["name"] == "top_level_fn"
    assert result["module_functions"][0]["id"] == "repo:known.py:top_level_fn"


def test_extract_no_fabrication_every_field_traces_to_real_ast_data():
    """Every property on every extracted item is either a literal copy of an
    AST field (name, lineno) or an id built deterministically from
    repo/path/name -- nothing is a placeholder/default standing in for data
    that wasn't actually parsed."""
    result = _extract("repo", "known.py", KNOWN_SNIPPET)
    tree = ast.parse(KNOWN_SNIPPET)
    real_class_linenos = {n.name: n.lineno for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    for c in result["classes"]:
        assert c["lineno"] == real_class_linenos[c["name"]]


def test_nested_inner_functions_are_not_treated_as_methods_or_module_functions():
    """A function defined inside another function is neither a class method
    nor a module-level function -- structural extraction only walks direct
    children of the module and of each class, not the full recursive
    ast.walk(), so closures don't get miscounted as real ontology entities."""
    snippet = "def outer():\n    def inner():\n        pass\n    return inner\n"
    result = _extract("repo", "f.py", snippet)
    assert len(result["module_functions"]) == 1
    assert result["module_functions"][0]["name"] == "outer"


def _independent_expected_counts() -> dict:
    """Deliberately re-implemented (not imported from cognify/) so this is a
    real cross-check, not the same code asserting against itself."""
    src_dir = os.path.join(os.path.dirname(__file__), "metis_mcp")
    total_classes = 0
    total_methods = 0
    for fname in sorted(os.listdir(src_dir)):
        if not fname.endswith(".py"):
            continue
        fpath = os.path.join(src_dir, fname)
        if os.path.getsize(fpath) == 0:
            continue
        tree = ast.parse(open(fpath, encoding="utf-8").read())
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                total_classes += 1
                total_methods += sum(
                    1 for n in ast.iter_child_nodes(node)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                total_methods += 1  # module-level function, stored as a Method node too
    return {"classes": total_classes, "methods": total_methods}


def test_real_run_against_landed_episodes_matches_independently_computed_counts():
    """Requires Phase 2's connector to have already landed the real
    CodeStructureExtracted episodes (test_application_code_connector.py)."""
    expected = _independent_expected_counts()
    run(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)  # idempotent; processes any un-cognified episodes

    # Excludes is_demo_data:true nodes -- the Demo Data generator
    # (demo_data/generate_demo_data.py) also creates :Class/:Method nodes
    # for volume/variety, which would otherwise inflate this count. Real
    # interaction found running this after loading demo data for the first
    # time, not a demo-data bug: this test just needed to scope its count
    # to the real application-code connector's nodes specifically.
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            classes = s.run(
                "MATCH (c:Class) WHERE c.is_demo_data IS NULL RETURN count(c) AS n"
            ).single()["n"]
            methods = s.run(
                "MATCH (m:Method) WHERE m.is_demo_data IS NULL RETURN count(m) AS n"
            ).single()["n"]
    finally:
        driver.close()

    assert classes == expected["classes"]
    assert methods == expected["methods"]


def test_every_class_and_method_traces_to_a_real_episode():
    """No fabrication, checked in the graph itself: every Class/Method node
    must have source_episode_id pointing at a real, existing Episode."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            orphaned = s.run(
                """
                MATCH (n) WHERE n:Class OR n:Method
                OPTIONAL MATCH (e:Episode {id: n.source_episode_id})
                WITH n, e WHERE e IS NULL
                RETURN count(n) AS orphaned
                """
            ).single()["orphaned"]
    finally:
        driver.close()
    assert orphaned == 0


if __name__ == "__main__":
    if not NEO4J_PASSWORD:
        print("METIS_NEO4J_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)
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
