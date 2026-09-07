"""
The authoring surface (spec §7.4b, X-6e).

Free to run: the graph is stubbed at `_rows`, which is the one function that
opens a session. What is asserted is the routing and the composition rule — the
two parts where a wrong answer would be fluent and confident.
"""
from __future__ import annotations

import pytest

from metis_mcp import authoring as A


@pytest.fixture
def graph(monkeypatch):
    """A minimal service: one endpoint, two headers, no declared security."""
    def rows(cypher: str, **params):
        if "security_schemes IS NOT NULL" in cypher:
            return []
        # `auth_facts` reads headers out of the transition's `c_inputs` now that
        # `Parameter` is staged out — one row per transition, decoded and
        # counted in Python because Community has no APOC to parse JSON in
        # Cypher. Two headers over six and five endpoints, expressed the way
        # landing actually writes them.
        if "e.id AS endpoint" in cypher:
            import json
            both = json.dumps([
                {"name": "userId", "location": "header", "required": True,
                 "type_name": "java.lang.String", "constraints": []},
                {"name": "mfaSessionId", "location": "header", "required": True,
                 "type_name": "java.lang.String", "constraints": []}])
            only_user = json.dumps([
                {"name": "userId", "location": "header", "required": True,
                 "type_name": "java.lang.String", "constraints": []}])
            return ([{"inputs": both, "endpoint": f"ep:{i}"} for i in range(5)]
                    + [{"inputs": only_user, "endpoint": "ep:5"}])
        if "count(e) AS n" in cypher:
            return [{"n": 12}]
        if "is_initial" in cypher:
            return [{"name": "Ready"}]
        if "THEN]->(tgt" in cypher:
            return [{"trigger": "POST /challenge", "status": "200",
                     "guard": "", "from_state": "Ready", "to_state": "Ok200",
                     "causes": []},
                    {"trigger": "POST /challenge", "status": "400",
                     "guard": "NOT (accepted)", "from_state": "Ready",
                     "to_state": "Rejected400", "causes": ["BadThing"]}]
        return []
    monkeypatch.setattr(A, "_rows", rows)


# --------------------------------------------------------------------------
# Routing — and refusing to route
# --------------------------------------------------------------------------

@pytest.mark.parametrize("question,tool", [
    ("how should I pass MFA Auth", "auth_facts"),
    ("what token do I need", "auth_facts"),
    ("give me a curl for the challenge endpoint", "call_recipe"),
    ("what body does this endpoint want", "call_recipe"),
    ("how does MFA work", "journey_walkthrough"),
    ("explain the flow", "journey_walkthrough"),
])
def test_a_question_routes_to_the_tool_that_can_answer_it(graph, question, tool):
    assert A.ask(question, journey="mfa")["answered_by"] == tool


def test_a_question_no_tool_answers_is_refused_not_guessed(graph):
    """**The whole difference between this and guessing.** Métis can say how to
    call an endpoint and how a journey moves; it cannot say why a decision was
    taken, and answering from general knowledge is the failure this surface
    exists to avoid."""
    out = A.ask("why was this designed the way it is")
    assert out["ok"] is False
    assert "cannot answer from anything but the graph" in out["reason"]
    assert "answer" not in out, "nothing was produced"


@pytest.mark.parametrize("question,kind", [
    ("what happens when the token expires", "expiry and lifetime"),
    ("how long does a challenge last", "duration"),
    ("is this endpoint slow", "latency"),
    ("who owns this service and when was it last deployed", "deployment"),
])
def test_a_kind_of_fact_metis_does_not_hold_is_named(graph, question, kind):
    """**Checked before routing, and that ordering is the fix.**

    "What happens when the token expires" matches *token*, routes to
    `auth_facts`, and comes back with a confident list of headers — a different
    question, fluently answered wrong. The model is a state machine recovered
    from source: expiry, timing, retry, latency and ownership are categories it
    holds no facts about at all, so no amount of better routing helps and saying
    so IS the answer.
    """
    out = A.ask(question, journey="mfa")
    assert out["ok"] is False
    assert out["out_of_scope"] == kind
    assert "answer" not in out, "no tool was consulted"
    assert "behaves over time" in out["reason"] or kind in out["reason"]


def test_an_in_scope_question_is_not_swallowed_by_the_scope_check(graph):
    """The check must not become a refusal machine: everything Métis genuinely
    answers still routes."""
    for question in ("how should I pass MFA Auth", "how does MFA work",
                     "give me a curl for the challenge endpoint"):
        assert A.ask(question, journey="mfa").get("answered_by"), question


def test_the_refusal_names_what_can_be_answered(graph):
    out = A.ask("what is the meaning of this")
    assert set(out["tools"]) == {"call_recipe", "auth_facts", "payload_shape",
                                 "journey_walkthrough"}


# --------------------------------------------------------------------------
# `ask` composes; it does not narrate
# --------------------------------------------------------------------------

def test_ask_states_nothing_the_tool_did_not(graph, monkeypatch):
    """T-6, applied to the answering surface. Every string `ask` returns is
    either the tool's own output or a fixed frame — never a sentence about the
    system that the tool did not produce."""
    sentinel = {"ok": True, "declared_security": [], "required_headers": [],
                "endpoints": 0, "caveat": "CAVEAT-TEXT",
                "how_to_read_this": "READ-TEXT"}
    monkeypatch.setattr(A, "auth_facts", lambda journey: sentinel)

    out = A.ask("how do I authenticate", journey="mfa")
    assert out["answer"] is sentinel, "the tool's output, unmodified"

    frame = {out["question"], out["answered_by"], out["rule"]}
    strings = {v for v in out.values() if isinstance(v, str)}
    assert strings <= frame, f"ask added prose of its own: {strings - frame}"


def test_ask_says_where_every_claim_came_from(graph):
    out = A.ask("how should I pass MFA Auth", journey="mfa")
    assert out["answered_by"] == "auth_facts"
    assert "came from the graph" in out["rule"]


# --------------------------------------------------------------------------
# The auth answer, which is the one most likely to be read as a guarantee
# --------------------------------------------------------------------------

def test_no_declared_security_is_never_reported_as_open(graph):
    """A filter chain or a gateway enforces authentication invisibly to
    extraction. "Nothing declared" is the only claim available, and the answer
    has to carry that or a reader takes silence for a finding."""
    out = A.auth_facts("mfa")
    assert out["declared_security"] == []
    assert "not the same as open" in out["caveat"]


def test_the_headers_are_offered_as_a_likelihood_not_a_fact(graph):
    """On a real service the auth travels as ordinary header parameters, and
    saying so is useful — but extraction cannot confirm anything checks them."""
    out = A.auth_facts("mfa")
    assert [h["name"] for h in out["required_headers"]] == ["userId", "mfaSessionId"]
    assert "cannot confirm" in out["how_to_read_this"]


# --------------------------------------------------------------------------
# The walkthrough
# --------------------------------------------------------------------------

def test_a_walkthrough_separates_the_rejections(graph):
    out = A.journey_walkthrough("mfa")
    assert len(out["transitions"]) == 2
    assert [t["status"] for t in out["rejections"]] == ["400"]


def test_a_walkthrough_states_that_none_of_it_is_approved(graph):
    """Everything recovered lands at Quarantine (S-4), so a walkthrough that read
    as settled fact would misrepresent it."""
    assert "none of it is approved" in A.journey_walkthrough("mfa")["means"]


def test_an_unknown_journey_is_reported(graph, monkeypatch):
    monkeypatch.setattr(A, "_rows", lambda *a, **k: [])
    out = A.journey_walkthrough("nope")
    assert out["ok"] is False and "nope" in out["reason"]


# --------------------------------------------------------------------------
# Routing to the academy, and what happens when it cannot be decided
# --------------------------------------------------------------------------

def test_the_routing_words_are_removed_before_searching():
    """**The trigger and the query are different jobs done by one string.**
    "Métis" is what routes a question to the academy and appears in all eight
    lessons, so it carries no information about WHICH one answers. Measured:
    "what is a state and what is a transition" retrieves `The shape of the
    model`; prefix it with "in Metis" and the same query retrieves `What Métis
    does not do`, because the name pulls toward the lesson that says it most.
    """
    from metis_mcp.authoring import _for_search

    assert "metis" not in _for_search("in Metis what is a state").lower()
    assert "state" in _for_search("in Metis what is a state")


def test_stripping_never_empties_the_question():
    """A question that is ONLY routing words still has to be searched with
    something — an empty query matches everything, ranked arbitrarily."""
    from metis_mcp.authoring import _for_search

    assert _for_search("Métis").strip()
    assert _for_search("academy").strip()


def test_an_unroutable_question_offers_the_academy_rather_than_hiding_it():
    """Deciding "is this about Métis?" from the text was measured three ways and
    none holds — so `ask` does not classify. It says no tool answered and names
    what the academy would have offered, with the claim explicitly withheld."""
    from metis_mcp.authoring import _academy_suggestion

    suggestion = _academy_suggestion("what is a state and what is a transition")
    if suggestion is None:
        return                                    # no graph configured here
    assert suggestion["title"]
    assert "not an answer" in suggestion["note"]
    # A suggestion carries no body: handing back prose would be answering.
    assert "body" not in suggestion


def test_a_configured_provider_is_optional_and_absent_by_default(monkeypatch):
    """`None` is the supported answer. A default install has no provider and
    every caller falls back to keyword and says so."""
    from metis_mcp.retrieval import PROVIDER_ENV, configured_provider

    monkeypatch.delenv(PROVIDER_ENV, raising=False)
    monkeypatch.setattr("metis_mcp.mbt.graph_session._load_config",
                        lambda: ({}, None))
    assert configured_provider() is None


def test_a_misconfigured_provider_raises_rather_than_degrading(monkeypatch):
    """Falling back to keyword silently would mean a deployment that configured
    semantic search got keyword results with no signal."""
    import pytest

    from metis_mcp.retrieval import PROVIDER_ENV, RetrievalRefused, configured_provider

    monkeypatch.setenv(PROVIDER_ENV, "not_a_dotted_path")
    with pytest.raises(RetrievalRefused):
        configured_provider()


# --------------------------------------------------------------------------
# A product route that cannot run does not outrank the academy
# --------------------------------------------------------------------------

_ACADEMY_SENTINEL = {"ok": True, "answered_by": "academy",
                     "answer": {"lesson": "lesson:stub"}}


@pytest.fixture
def academy(monkeypatch):
    """`_ask_academy` without a graph, and a record of whether it was asked."""
    calls = []

    def fake(question):
        calls.append(question)
        return dict(_ACADEMY_SENTINEL)

    monkeypatch.setattr(A, "_ask_academy", fake)
    return calls


def test_a_route_that_needs_a_journey_and_has_none_yields_to_the_academy(
        graph, academy):
    """**The bug this pins.** `ask` matched *how does*, called
    `journey_walkthrough('')` and returned `no transitions for journey ''` — for
    a question the academy answers in full. A route that was never given the one
    argument it needs is not the more specific answer; it is the one that cannot
    answer at all."""
    out = A.ask("What is Métis and how does it decide what to test?")

    assert out["answered_by"] == "academy"
    assert academy == ["What is Métis and how does it decide what to test?"]


def test_a_product_route_with_a_journey_still_wins(graph, academy):
    """The ordering rule is unchanged where it was right: a question naming both
    a product noun and Métis wants the product tool, when that tool can run."""
    out = A.ask("how does Métis handle this journey", journey="mfa")

    assert out["answered_by"] == "journey_walkthrough"
    assert academy == [], "the academy must not be consulted when the route runs"


def test_a_question_with_no_academy_word_gets_the_tools_own_failure(graph, academy):
    """Narrow on purpose. Without a word naming this system there is nothing to
    suggest the academy is the better source, and the tool's own refusal — which
    names the journey it wanted — is the honest answer."""
    out = A.ask("explain the flow")

    assert out["answered_by"] == "journey_walkthrough"
    assert academy == []


def test_the_academy_declining_falls_through_to_the_product_route(graph, monkeypatch):
    """`_ask_academy` returns `None` when nothing matched. That must land on
    exactly the behaviour that was there before, not on a refusal invented
    here."""
    monkeypatch.setattr(A, "_ask_academy", lambda question: None)

    assert A.ask("how does Métis work")["answered_by"] == "journey_walkthrough"


def test_only_the_route_that_binds_the_journey_needs_one(graph, academy):
    """**The asymmetry is real and worth pinning.** `auth_facts` and
    `call_recipe` take a `journey` and never bind it — they query the whole
    graph — so they answer the same with or without one and must not yield.
    `journey_walkthrough` filters on `$j` and is the only member of the set."""
    from metis_mcp.authoring import _NEEDS_JOURNEY

    assert _NEEDS_JOURNEY == {"journey_walkthrough"}
    assert A.ask("give me a curl for Métis")["answered_by"] == "call_recipe"
    assert A.ask("what token does Métis need")["answered_by"] == "auth_facts"
    assert academy == []


# --------------------------------------------------------------------------
# More than one academy in one graph
# --------------------------------------------------------------------------

class _Rows(list):
    def single(self):
        return self[0] if self else None


class _FakeSession:
    """Answers the two corpus queries and nothing else."""

    def __init__(self, roots=(), lessons=()):
        self.roots, self.lessons = tuple(roots), tuple(lessons)

    def run(self, cypher, params=None, **kw):
        if "toLower(root.name) AS name" in cypher:
            return _Rows({"name": n} for n in self.roots)
        if "collect(DISTINCT l.id) AS ids" in cypher:
            return _Rows([{"ids": list(self.lessons)}])
        return _Rows()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def two_corpora(monkeypatch):
    """A graph holding a Métis academy and an Athena one."""
    fake = _FakeSession(roots=("metis", "athena"),
                        lessons=("lesson:01-what-athena-is",))
    monkeypatch.setattr("metis_mcp.mbt.graph_session.session", lambda: fake)
    return fake


def test_a_landed_corpus_is_routable_without_an_edit(graph, two_corpora, academy):
    """**The failure this closes.** A second academy — `system: athena` — landed,
    embedded and correctly ranked by `search_knowledge`, could not be reached
    through `ask`: no word in a question about Athena appears in a vocabulary
    hand-listed about Métis. The routing vocabulary now comes from the corpus
    roots in the graph, so landing an academy is enough."""
    assert A.ask("what modules does Athena have")["answered_by"] == "academy"
    assert academy == ["what modules does Athena have"]


def test_the_hand_listed_words_still_route(graph, two_corpora, academy):
    """`g1`, `quarantine` and the rest name Métis without saying it, and no
    corpus root would supply them."""
    assert A.ask("why is everything sitting in Quarantine")["answered_by"] == "academy"


def test_a_question_naming_no_system_is_not_routed_to_a_corpus(graph, two_corpora,
                                                               academy):
    out = A.ask("why was this designed the way it is")
    assert out.get("answered_by") is None
    assert academy == []


def test_naming_a_corpus_scopes_the_answer_to_it(two_corpora):
    """Asked "what is Athena and what does it collect", search returned
    `What Métis does not do` first — a confident answer from the wrong system,
    which is worse than no answer."""
    from metis_mcp.authoring import _academy_hits

    mixed = [{"label": "Lesson", "id": "lesson:01-what-metis-does-not-do"},
             {"label": "Lesson", "id": "lesson:01-what-athena-is"}]
    import metis_mcp.mbt.graph_loader as gl
    orig = gl.search_knowledge
    gl.search_knowledge = lambda s, q, limit=20: mixed
    try:
        hits = _academy_hits(two_corpora, "what is Athena and what does it collect")
    finally:
        gl.search_knowledge = orig

    assert [h["id"] for h in hits] == ["lesson:01-what-athena-is"], (
        "a question naming one corpus must not be answered from another")


def test_two_corpus_names_scope_to_neither(two_corpora):
    """"How does Métis model Athena" is a question about the pair. Picking one
    would answer half of it while looking certain."""
    from metis_mcp.authoring import _named_corpus

    assert _named_corpus(two_corpora, "how does métis model athena") == ""
    assert _named_corpus(two_corpora, "what modules does athena have") == "athena"


def test_the_corpus_name_is_stripped_before_searching(two_corpora):
    """The word that ROUTES a question to a corpus appears in every document in
    it, so it cannot say which one answers."""
    from metis_mcp.authoring import _for_search, corpus_words

    query = _for_search("what modules does Athena have", corpus_words(two_corpora))
    assert "athena" not in query.lower()
    assert "modules" in query


def test_the_suggestion_does_not_claim_the_academy_is_about_metis(two_corpora):
    """It said "the academy is about Métis itself" and "ask again naming Métis"
    — false with a second corpus landed, and advice that would not have worked."""
    from metis_mcp.authoring import _academy_suggestion

    suggestion = _academy_suggestion("what is the definition of done")
    if suggestion is None:
        return                                    # nothing matched here
    assert "Métis" not in suggestion["note"]


def test_the_provider_spec_resolves_without_loading_the_model(monkeypatch):
    """**One resolver, and asking must be cheap.** `rebuild_graph.sh` has to name
    a provider on the `embed` command line, and a shell script re-deriving
    "environment, then the config file" would be a second answer to one question.
    Returning the STRING matters too: loading a provider imports the model and,
    the first time, downloads it — asking "is anything configured" must not."""
    from metis_mcp.retrieval import PROVIDER_ENV, configured_provider_spec

    monkeypatch.setenv(PROVIDER_ENV, "some.module:Provider")
    assert configured_provider_spec() == "some.module:Provider"


def test_no_configured_provider_is_an_empty_spec_not_an_error(monkeypatch):
    """A default install has none, and the rebuild reports that and carries on."""
    from metis_mcp.retrieval import PROVIDER_ENV, configured_provider_spec

    monkeypatch.delenv(PROVIDER_ENV, raising=False)
    monkeypatch.setattr("metis_mcp.mbt.graph_session._load_config",
                        lambda: ({}, None))
    assert configured_provider_spec() == ""


def test_the_config_file_supplies_the_spec_when_the_environment_does_not(monkeypatch):
    from metis_mcp.retrieval import PROVIDER_ENV, configured_provider_spec

    monkeypatch.delenv(PROVIDER_ENV, raising=False)
    monkeypatch.setattr("metis_mcp.mbt.graph_session._load_config",
                        lambda: ({"embedding": {"provider": "pkg.mod:P"}}, None))
    assert configured_provider_spec() == "pkg.mod:P"


# --------------------------------------------------------------------------
# The caveat has to be true of the corpus it is attached to
# --------------------------------------------------------------------------

def test_the_academy_caveat_does_not_name_the_wrong_system(monkeypatch):
    """**A caveat that names the wrong system is a wrong statement.**

    The rule line hardcoded "somebody wrote about Métis" and was attached to
    every academy answer, so each of the six Athena lessons came back captioned
    as writing about Métis. Same bug as the routing note, one string over.

    The name is dropped rather than computed: the sentence's point is
    *authored, not recovered*, which holds for any corpus, and using the
    QUESTION's corpus to caption the LESSON would only be a new way to be
    wrong.
    """
    fake = _FakeSession(roots=("metis", "athena"),
                        lessons=("lesson:01-what-athena-is",))
    monkeypatch.setattr("metis_mcp.mbt.graph_session.session", lambda: fake)
    monkeypatch.setattr(A, "_academy_hits", lambda s, q: [
        {"id": "lesson:01-what-athena-is", "name": "What Athena is",
         "body": "Athena collects quality metrics.", "matched_passage": ""}])
    monkeypatch.setattr("metis_mcp.mbt.graph_loader.related_by_topic",
                        lambda s, i: {"topics": ["athena-overview"], "related": []})

    answer = A._ask_academy("what is Athena and what does it collect")

    assert answer["answered_by"] == "academy"
    assert answer["answer"]["lesson"] == "lesson:01-what-athena-is"
    rule = answer["rule"]
    assert "Métis" not in rule and "Metis" not in rule, (
        f"the caveat names a system it cannot know is the right one: {rule!r}")
    assert "authored" in rule and "not a fact extracted" in rule, (
        f"dropping the name must not drop the point of the caveat: {rule!r}")


def test_the_no_graph_message_does_not_name_the_wrong_system(monkeypatch):
    """The same hardcoded name on the path where the graph is unreachable."""
    from metis_mcp.mbt.graph_session import GraphNotConfigured

    def unreachable():
        raise GraphNotConfigured("no bolt URI configured")

    monkeypatch.setattr("metis_mcp.mbt.graph_session.session", unreachable)

    answer = A._ask_academy("what is Athena and what does it collect")

    assert answer["ok"] is False
    reason = answer["reason"]
    assert "Métis" not in reason and "Metis" not in reason, (
        f"the unreachable-graph message names a system too: {reason!r}")
    assert "academy" in reason and "no bolt URI configured" in reason, (
        "the message must still say what is unreachable and why")


# --------------------------------------------------------------------------
# call_recipe: the scope it claims, and the half a test asserts on
# --------------------------------------------------------------------------

@pytest.fixture
def recipe_graph(monkeypatch):
    """One journey's worth of rows, recording what the query was asked for."""
    seen: dict = {"queries": []}

    def rows(cypher: str, **params):
        seen["queries"].append((cypher, params))
        if "properties(e) AS endpoint" in cypher:
            return [{
                "endpoint": {"id": "ep:1", "http_method": "GET",
                             "path": "/version/{id}"},
                "inputs": "[]",
                # The two sides arrive separately or they cannot be told apart.
                "request_bodies": [],
                "response_bodies": ["cls:VersionDto"],
                "statuses": ["200"],
                "security": [],
            }]
        if "m.exception_type AS cause" in cypher:
            return [{"status": "400", "cause": "IllegalArgumentException"}]
        return []

    monkeypatch.setattr(A, "_rows", rows)
    return seen


def test_call_recipe_scopes_to_the_journey_it_was_asked_for(recipe_graph):
    """**The claim has to be backed by the query.** `journey` reached the
    signature and the returned label and nothing in between, so asking for
    athena-core returned all 91 endpoints across seven modules -- git's
    `/commit` included -- each stamped `"journey": "athena-core"`. Correctly
    scoped, athena-core is 20.
    """
    out = A.call_recipe("athena-core")
    assert out["journey"] == "athena-core"

    endpoint_q = [(c, p) for c, p in recipe_graph["queries"]
                  if "properties(e) AS endpoint" in c]
    assert endpoint_q, "no endpoint query ran"
    cypher, params = endpoint_q[0]
    assert "functional_areas" in cypher, (
        "the journey never reaches the query; the label on the way out is a "
        "claim the rows do not support")
    assert params.get("journey") == "athena-core"


def test_the_rejections_are_scoped_too(recipe_graph):
    """Five ExceptionMapping nodes in the whole graph appeared on all 91
    recipes, git's mappings included."""
    A.call_recipe("athena-core")
    mapping_q = [(c, p) for c, p in recipe_graph["queries"]
                 if "m.exception_type AS cause" in c]
    assert mapping_q, "no mapping query ran"
    cypher, params = mapping_q[0]
    assert "functional_areas" in cypher, "rejections are not scoped to the journey"
    assert params.get("journey") == "athena-core"
    # **Direction, asserted explicitly.** The transition points at the mapping.
    # Written the other way the query is still scoped, still parameterised, and
    # matches nothing.
    assert "(t:" in cypher.split("-[:DERIVED_FROM]->")[0], (
        f"the transition must be the source of DERIVED_FROM:\n{cypher}")


def test_a_scoped_rejection_still_reaches_the_recipe(recipe_graph):
    """**Scoping must narrow the rejections, not delete them.**

    Asserting the query text alone passed against a query whose endpoints were
    reversed, so it matched nothing and every recipe silently lost its
    rejections -- the bug being fixed, reintroduced by its own fix. This fails
    on an empty result.
    """
    rec = A.call_recipe("athena-core")["recipes"][0]
    assert ("400", "IllegalArgumentException") in [
        tuple(r) for r in rec.get("rejections") or []], (
        f"the scoped mapping never reached the recipe: {rec.get('rejections')!r}")
    assert "400 when IllegalArgumentException" in rec["curl"]


def test_a_response_type_is_asserted_on_not_sent_as_a_body(recipe_graph):
    """**The ontology distinguishes these and the recipe did not.**

        REQUIRES -> "A payload type whose field constraints a case must
                     satisfy or violate"      (the request)
        EXPECTS  -> "The response body a case should assert"

    `OPTIONAL MATCH (t)-[:EXPECTS|REQUIRES]->(b)` collected both into one
    `bodies` list rendered as `-d`, so every GET carried its own response
    schema as a request payload -- and the assertion half of the test was not
    merely lost, it had been moved into the request half.
    """
    rec = A.call_recipe("athena-core")["recipes"][0]

    assert rec["method"] == "GET"
    assert rec["body"] is None, (
        f"a GET with no REQUIRES must carry no request body, got {rec['body']!r}")
    assert " -d " not in rec["curl"] and "-d '" not in rec["curl"], (
        f"the curl sends a body it has no request type for:\n{rec['curl']}")
    assert rec.get("asserts") == ["cls:VersionDto"], (
        "the response type is what a case asserts on; it has to survive "
        f"somewhere, got {rec.get('asserts')!r}")


def test_auth_facts_scopes_to_the_journey_it_was_asked_for(monkeypatch):
    """The same unused parameter, three queries over.

    `auth_facts("athena-core")` reported `endpoints: 91` -- the whole graph,
    seven modules -- beside `"journey": "athena-core"`. Declared schemes and
    required headers were gathered just as widely, so a header required only by
    the tms module was reported as required for core.
    """
    seen = []

    def rows(cypher: str, **params):
        seen.append((cypher, params))
        return []

    monkeypatch.setattr(A, "_rows", rows)
    out = A.auth_facts("athena-core")
    assert out["journey"] == "athena-core"

    assert seen, "no query ran"
    for cypher, params in seen:
        assert "functional_areas" in cypher, (
            f"unscoped query in auth_facts:\n{cypher}")
        assert params.get("journey") == "athena-core", (
            f"journey not passed to:\n{cypher}")


def test_a_failed_route_offers_the_academy_without_displacing_its_own_refusal(
        graph, monkeypatch):
    """**The bug, and the wrong fix for it, both pinned.**

    `"can I approve my own work"` hits `journey_walkthrough` on *how do*, gets no
    journey, and comes back `no transitions for journey ''` — useless, for a
    question the academy answers outright (N-10). The pre-route guard cannot
    catch it because the sentence never names this system.

    Returning the lesson INSTEAD was tried and is worse: `"explain the flow"`
    then answers with a lesson rather than with the refusal that tells the caller
    to pass a journey, which is the more useful of the two. So the tool's own
    failure survives and the suggestion rides alongside it.
    """
    monkeypatch.setattr(A, "_academy_suggestion",
                        lambda q: {"lesson": "lesson:05-the-two-gates",
                                   "title": "The two gates", "note": "x"})
    # The real shape of the bug: the route runs with no journey and finds
    # nothing, which is what `journey_walkthrough('')` does against a live graph.
    monkeypatch.setattr(A, "journey_walkthrough",
                        lambda j: {"ok": False,
                                   "reason": f"no transitions for journey {j!r}"})
    out = A.ask("can I approve my own work")

    # The refusal is still the answer, and it still says what it wanted.
    assert out["answered_by"] == "journey_walkthrough"
    assert out["ok"] is False
    assert "no transitions" in out["answer"]["reason"]
    # And the academy is offered, with a caveat that describes THIS path.
    assert out["academy_may_cover"]["lesson"] == "lesson:05-the-two-gates"
    assert "journey_walkthrough" in out["academy_may_cover"]["note"]
    assert "not an answer" in out["academy_may_cover"]["note"]


def test_a_route_that_succeeds_is_not_given_an_academy_suggestion(graph, monkeypatch):
    """A working answer must not be decorated with an unrelated lesson."""
    called = []
    monkeypatch.setattr(A, "_academy_suggestion",
                        lambda q: called.append(q) or {"lesson": "x", "title": "x",
                                                       "note": "x"})
    out = A.ask("how does this journey move", journey="mfa")
    assert out["ok"] is True
    assert "academy_may_cover" not in out
    assert called == []


def test_a_route_given_a_journey_that_fails_gets_no_suggestion(graph, monkeypatch):
    """Scoped to the *missing journey*, not to failure in general.

    A caller who passed `journey="nope"` and got nothing back has a real
    product-side answer — that journey is not in the graph — and burying it under
    a lesson would be the same displacement the test above forbids.
    """
    called = []
    monkeypatch.setattr(A, "_academy_suggestion",
                        lambda q: called.append(q) or {"lesson": "x", "title": "x",
                                                       "note": "x"})
    monkeypatch.setattr(A, "journey_walkthrough",
                        lambda j: {"ok": False,
                                   "reason": f"no transitions for journey {j!r}"})
    out = A.ask("how does this journey move", journey="no-such-journey")
    assert out["ok"] is False
    assert "academy_may_cover" not in out
    assert called == []
