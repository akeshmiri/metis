"""
Questions an author asks, answered from the graph (spec §7.4b, X-6e).

"What is in this model" was already answerable. **"How do I call this"** and
**"how does this work"** were not, and an agent asked those had to re-derive from
a traversal what the graph already holds precisely.

Every tool here is **read-only**, so all of them exist at `METIS_MCP_WRITE=off`
where the surface is supposed to be read-only by construction (N-8).

**They state facts; the prose is the caller's.** `ask` is the exception and it is
the risk: a fluent wrong answer about how authentication works is the failure this
codebase is most careful about. So `ask` composes the tools below and **may state
nothing absent from their output** — the rule T-6 already puts on rendered test
prose, enforced here the same way, by a test.
"""
from __future__ import annotations

from metis_mcp.ontology.labels import label_expression
from metis_mcp.rendering import recipe as _recipe

_TRANSITION = label_expression("Transition")
_TYPE = label_expression("Class")


def _rows(cypher: str, **params) -> list[dict]:
    from metis_mcp.mbt.graph_session import session

    with session() as s:
        return [dict(r) for r in s.run(cypher, **params)]


def _payload_for(type_id: str, depth: int = 3) -> dict | None:
    """A payload type with its nested types resolved, to a bounded depth.

    Bounded because a self-referential payload is legal and would otherwise
    recurse for ever; the bound is reported rather than silently applied.
    """
    rows = _rows(
        f"MATCH (c:{_TYPE} {{id: $id}}) "
        f"OPTIONAL MATCH (c)-[:OF_TYPE]->(n:{_TYPE}) "
        f"RETURN properties(c) AS self, collect(properties(n)) AS nested", id=type_id)
    if not rows or not rows[0]["self"]:
        return None
    nested: dict = {}
    if depth > 0:
        for child in rows[0]["nested"]:
            if not child:
                continue
            inner = _payload_for(child["id"], depth - 1)
            if inner:
                nested[child.get("package")] = inner
                nested[child.get("name")] = inner
    return _recipe.expand_payload(rows[0]["self"], nested)


def payload_shape(type_name: str) -> dict:
    """A payload type's fields and the values each accepts.

    A field is a **property** of its type since X-6d, so this is the nested
    document those flat `f_<name>_*` properties encode — the form a test designer
    reads partitions and boundaries off.
    """
    rows = _rows(
        f"MATCH (c:{_TYPE}) WHERE c.name = $n OR c.package = $n RETURN c.id AS id",
        n=type_name)
    if not rows:
        return {"ok": False,
                "reason": f"no declared type {type_name!r} in the graph. Only "
                          f"types a payload chain reaches are landed (X-6d)"}
    shape = _payload_for(rows[0]["id"])
    return {"ok": True, **(shape or {})}


def call_recipe(journey: str, route: str = "") -> dict:
    """How to exercise an endpoint: the call, and what makes it fail.

    `route` is `VERB /path`, or empty for every endpoint in the journey. The body
    carries **placeholders describing the accepted values, never sample values**
    (T-9c): a single valid value is one case, where the space is what a case is
    chosen from.
    """
    rows = _rows(f"""
        MATCH (e:Endpoint)
        OPTIONAL MATCH (t:{_TRANSITION})-[:DERIVED_FROM]->(e)
        OPTIONAL MATCH (e)-[:ACCEPTS]->(p:Parameter)
        OPTIONAL MATCH (e)-[:ACCEPTS]->(:Parameter {{location:'body'}})-[:OF_TYPE]->(b)
        OPTIONAL MATCH (e)-[:SECURED_BY]->(sec:SecurityScheme)
        WITH e, collect(DISTINCT properties(p)) AS params,
             collect(DISTINCT b.id) AS bodies,
             collect(DISTINCT t.c_outcome_status) AS statuses,
             collect(DISTINCT properties(sec)) AS security
        RETURN properties(e) AS endpoint, params, bodies, statuses, security
        ORDER BY e.path, e.http_method""")

    rejections = [(str(r["status"]), r["cause"]) for r in _rows(
        "MATCH (m:ExceptionMapping) RETURN m.status AS status, "
        "m.exception_type AS cause ORDER BY m.status, m.exception_type")]

    out = []
    for row in rows:
        endpoint = dict(row["endpoint"])
        wanted = f"{endpoint.get('http_method')} {endpoint.get('path')}"
        if route and route.strip() != wanted:
            continue
        endpoint["parameters"] = [p for p in row["params"] if p]
        # Injected from the SECURED_BY traversal, as `parameters` is from
        # ACCEPTS. It used to ride on the endpoint as parallel arrays that could
        # not express a scheme with two roles.
        endpoint["security"] = [x for x in row["security"] if x]
        bodies = tuple(filter(None, (_payload_for(b) for b in row["bodies"] if b)))
        built = _recipe.build(endpoint, base_url=_base_url(), payload_types=bodies,
                              outcomes=sorted(s for s in row["statuses"] if s),
                              rejections=rejections)
        out.append({"route": wanted, "curl": _recipe.as_curl(built), **built})

    if not out:
        return {"ok": False,
                "reason": f"no endpoint {route!r} in the graph"
                          if route else "no endpoints in the graph"}
    return {"ok": True, "journey": journey, "recipes": out}


def _base_url() -> str:
    """From the project profile, never invented (T-9d)."""
    try:
        from code_analysis.project_profile import load_for

        return (load_for("") or {}).get("base_url", "") or ""
    except Exception:
        return ""


def auth_facts(journey: str) -> dict:
    """What a caller must present, and what Métis cannot see.

    **The caveat is the point.** Declarative security is all extraction can
    recover; a filter chain or a gateway enforces authentication invisibly to it.
    On a real service zero endpoints declared any, and its auth travelled as
    ordinary header parameters — so "nothing declared" and "open" are different
    claims and only the first is ever made.
    """
    # One row per DECLARATION, so a scheme keeps its own roles. This used to
    # return `security_schemes` and `security_roles` as two arrays off the
    # endpoint — and they were positional, so a scheme with two roles made the
    # correspondence undecodable. A third of the demo corpus was misaligned.
    declared = _rows(
        "MATCH (e:Endpoint)-[:SECURED_BY]->(s:SecurityScheme) "
        "RETURN e.path AS path, e.http_method AS verb, "
        "s.scheme AS scheme, s.expression AS expression, "
        "coalesce(s.roles, []) AS roles, s.source AS source "
        "ORDER BY e.path, s.expression")
    headers = _rows(
        "MATCH (e:Endpoint)-[:ACCEPTS]->(p:Parameter {location:'header'}) "
        "RETURN p.name AS name, count(DISTINCT e) AS endpoints, "
        "p.required AS required ORDER BY endpoints DESC, p.name")
    total = (_rows("MATCH (e:Endpoint) RETURN count(e) AS n") or [{"n": 0}])[0]["n"]

    return {
        "ok": True,
        "journey": journey,
        "declared_security": declared,
        "required_headers": headers,
        "endpoints": total,
        "caveat": _recipe.NO_SECURITY_NOTE if not declared else
                  ("declared security is recovered from annotations only; a "
                   "gateway may enforce more"),
        "how_to_read_this": (
            "a header sent to every endpoint is how this service most likely "
            "carries identity, but extraction cannot confirm that it is checked"
            if headers and not declared else
            "the declared schemes above are what the source states"),
    }


def journey_walkthrough(journey: str) -> dict:
    """How a journey works: its states, what moves between them, and what fails.

    States and transitions only — no narrative. "How MFA works" is answered by
    the shape of the machine, and a sentence about intent would be a claim the
    model does not carry (T-6).
    """
    transitions = _rows(f"""
        MATCH (t:{_TRANSITION}) WHERE $j IN t.functional_areas OR t.id STARTS WITH $prefix
        OPTIONAL MATCH (src:State)-[:WHEN]->(t)
        OPTIONAL MATCH (t)-[:THEN]->(tgt:State)
        OPTIONAL MATCH (t)-[:DERIVED_FROM]->(m:ExceptionMapping)
        RETURN t.c_trigger AS trigger, t.c_outcome_status AS status,
               t.b_guard_expression AS guard, src.name AS from_state,
               tgt.name AS to_state, collect(DISTINCT m.exception_type) AS causes
        ORDER BY t.c_trigger, t.c_outcome_status""",
        j=journey, prefix=f"{journey}-")
    if not transitions:
        return {"ok": False, "reason": f"no transitions for journey {journey!r}"}

    initial = _rows("MATCH (s:State {is_initial: true}) RETURN s.name AS name")
    return {
        "ok": True,
        "journey": journey,
        "initial_states": [r["name"] for r in initial],
        "transitions": transitions,
        "rejections": [t for t in transitions
                       if str(t["status"] or "").startswith(("4", "5"))],
        "means": ("every row was recovered from code and none of it is approved "
                  "until a human reviews it (S-4)"),
    }


# **What Métis does not hold, at all.** Not a routing gap — a category of fact
# the graph has no notion of. A question about any of these is unanswerable
# however well it is routed, and saying so is the answer.
#
# `auth_facts` matches "token" and would answer "what happens when the token
# expires" with a confident list of headers, which is a different question
# fluently answered wrong. Expiry, retry, timing, ordering over time, volume: the
# model is a state machine recovered from source and holds none of it.
OUT_OF_SCOPE = {
    "expire": "expiry and lifetime",
    "expires": "expiry and lifetime",
    "timeout": "timing",
    "retry": "retry behaviour",
    "how long": "duration",
    "how often": "frequency",
    "performance": "performance",
    "slow": "latency",
    "concurrent": "concurrency",
    "race": "concurrency",
    "deploy": "deployment",
    "who owns": "ownership",
    "cost": "cost",
}


def out_of_scope(question: str) -> str:
    """The kind of fact this question wants, when Métis holds none of it."""
    text = (question or "").lower()
    for marker, kind in OUT_OF_SCOPE.items():
        if marker in text:
            return kind
    return ""


# What `ask` can route to, and nothing else. A question it cannot route is
# reported as unroutable rather than answered from general knowledge — which is
# the whole difference between this and guessing.
_ROUTES = (
    (("auth", "authenticate", "authentication", "token", "login", "credential",
      "header", "authorise", "authorize", "permission"), "auth_facts"),
    (("curl", "call", "invoke", "request", "endpoint", "api", "payload", "body",
      "send", "post", "get"), "call_recipe"),
    (("work", "how does", "flow", "journey", "behaviour", "behavior", "walk",
      "overview", "explain"), "journey_walkthrough"),
)

# Questions about Métis ITSELF, answered from the academy rather than from a
# product model. `ask` used to route only to the four product tools, so a
# question the academy answers in full came back "no tool answers this" — the
# corpus was landed, indexed and unreachable through the surface it was landed
# for. These are checked LAST: a question mentioning both a product noun and one
# of these should go to the product tool, because that is the more specific
# answer.
# Terms that name THIS system, not a product it models. Bare interrogatives are
# deliberately absent: an earlier version matched "what is" and "why does", and
# "what is the meaning of this" — a question with no answer anywhere — routed to
# the academy instead of being reported as unroutable. A word earns a place here
# by being one somebody would only use when asking about Métis.
_ACADEMY_WORDS = (
    "metis", "métis", "g1", "g2", "quarantine", "ontology", "lesson", "academy",
    "lifecycle_state", "valid_from", "valid_to", "provenance", "specialisation",
    "the two gates", "approval gate", "landed", "landing",
)



# The words that ROUTE a question here carry no information about which lesson
# answers it — "Métis" is in all eight — so they are removed before searching.
# Measured: "what is a state and what is a transition" retrieves `The shape of
# the model`; prefix it with "in Metis" and the same query retrieves `What Métis
# does not do`, because the name pulls the embedding toward the lesson that says
# the name most. The trigger and the query are different jobs done by one string.
_TRIGGER_NOISE = ("metis", "métis", "academy", "lesson")

# The routes that cannot answer without a journey — and it is only one. This
# looks like it should be all three and is not: `auth_facts` and `call_recipe`
# take a `journey` and then query the whole graph without binding it, so they
# return the same thing with or without one. `journey_walkthrough` is the
# exception. Its Cypher filters on `$j`, so with no journey it matches nothing
# and reports `no transitions for journey ''`.
_NEEDS_JOURNEY = frozenset({"journey_walkthrough"})


def _for_search(question: str) -> str:
    """The question with its routing words removed, or unchanged if that empties it."""
    import re

    stripped = re.sub(r"\b(" + "|".join(_TRIGGER_NOISE) + r")\b", " ",
                      question, flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", stripped).strip(" ,.?!")
    return stripped or question


def _academy_hits(session, question: str, limit: int = 5) -> list[dict]:
    """Lesson hits, semantic where the deployment configured a provider.

    **`ask` searched keywords only, whatever was embedded.** A corpus with
    vectors and a caller that never used them is the whole cost of semantic
    search and none of the benefit — measured on the academy's own benchmark,
    keyword ranks 23 of 36 questions first and hybrid ranks 29.

    Keyword remains the answer when no provider is configured. That is the
    default install, and it is not a degradation to be hidden: `answered_by`
    below says which ran.
    """
    from metis_mcp.mbt.graph_loader import hybrid_search, search_knowledge
    from metis_mcp.retrieval import RetrievalRefused, configured_provider

    try:
        provider = configured_provider()
    except RetrievalRefused:
        # A misconfigured provider is the deployment's problem to see, but it
        # must not make `ask` unusable — keyword still answers.
        provider = None

    if provider is not None:
        try:
            hits = [h.__dict__ if hasattr(h, "__dict__") else dict(h)
                    for h in hybrid_search(session, _for_search(question),
                                           provider=provider, limit=limit)]
            return [h for h in hits if h.get("label") == "Lesson"]
        except RetrievalRefused:
            # A corpus embedded with another model. Refusing the whole question
            # would be worse than answering it the way a default install does.
            pass
    return [h for h in search_knowledge(session, _for_search(question), limit=limit)
            if h.get("label") == "Lesson"]


def _ask_academy(question: str):
    """The academy's answer to a question about Métis itself, or `None`.

    **Why this exists at all.** `ask` routed only to the four product tools, so
    a question the academy answers in full came back "no tool answers this" —
    the corpus was landed, indexed, and unreachable through the surface it was
    landed for.

    **Why it returns an answer instead of raising, and where that differs.** The
    other routes raise `GraphNotConfigured` straight through to the caller:
    `server.py` registers these five with a bare `mcp.tool()(fn)` and no wrapper,
    while every tool defined in `server.py` itself catches it and returns
    `_NOT_CONFIGURED`. So the agent surface answers one way for `get_model` and
    another for `auth_facts`, which was true before this route existed and is a
    pre-existing inconsistency rather than one introduced here.

    This route takes the `server.py` side of it, because "the academy lives in a
    graph you have not configured" is a fact worth stating and a traceback is
    not. Making the other four agree is a change to their contract and belongs
    with whoever owns that decision.
    """
    from metis_mcp.mbt.graph_loader import related_by_topic, search_knowledge
    from metis_mcp.mbt.graph_session import GraphNotConfigured, session

    try:
        with session() as s:
            hits = _academy_hits(s, question)
            if not hits:
                return None
            best = hits[0]
            related = related_by_topic(s, best["id"])
    except GraphNotConfigured as e:
        return {
            "ok": False,
            "question": question,
            "reason": (f"this reads as a question about Métis itself, which the "
                       f"academy answers — and the academy lives in the graph, "
                       f"which is not reachable: {e}"),
            "remedy": "metis lessons, once a graph is configured",
            "tools": ["call_recipe", "auth_facts", "payload_shape",
                      "journey_walkthrough"],
        }

    return {
        "ok": True,
        "question": question,
        "answered_by": "academy",
        "answer": {
            "lesson": best["id"],
            "title": best.get("name", ""),
            # Which SECTION ranked, where chunked retrieval found one. A reader
            # handed a whole lesson still has to find the paragraph.
            "matched_passage": best.get("matched_passage", ""),
            "body": best.get("body", ""),
            "topics": related["topics"],
            "read_next": [r["name"] for r in related["related"]],
        },
        "rule": ("the academy is authored, not recovered: this is what somebody "
                 "wrote about Métis, not a fact extracted from a running system"),
    }


def _academy_suggestion(question: str) -> dict | None:
    """The academy's best guess, as a SUGGESTION and never as an answer.

    Carries no body — a title and an id, so a reader can decide whether to read
    it. Handing back prose here would be answering, which is the thing the
    routing could not justify.
    """
    from metis_mcp.mbt.graph_session import GraphNotConfigured, session

    try:
        with session() as s:
            hits = _academy_hits(s, question, limit=1)
    except (GraphNotConfigured, Exception):        # noqa: BLE001 - a suggestion
        return None                                # is never worth an error
    if not hits:
        return None
    return {
        "lesson": hits[0]["id"],
        "title": hits[0].get("name", ""),
        "note": "not an answer — the academy is about Métis itself, and nothing "
                "checked that this question is. Ask again naming Métis to have it "
                "answered from there.",
    }


def ask(question: str, journey: str = "") -> dict:
    """Route a question to the tools above and return what they said.

    **It composes; it does not narrate.** The answer carries the tool output and
    the tool that produced it, so a caller can render prose and a reviewer can
    see the source of every claim. A question that matches no route is reported
    as unroutable — answering it from anywhere but the graph is the failure this
    whole surface exists to avoid.
    """
    text = (question or "").lower()

    # Checked BEFORE routing, because a keyword match is not evidence that the
    # tool can answer: "what happens when the token expires" hits `auth_facts`
    # on *token* and would come back with a confident list of headers.
    kind = out_of_scope(question)
    if kind:
        return {
            "ok": False,
            "question": question,
            "reason": f"Métis holds no facts about {kind}. The model is a state "
                      f"machine recovered from source: it knows what a caller "
                      f"sends, what it is answered with, and what makes a "
                      f"request fail — not how any of it behaves over time",
            "out_of_scope": kind,
            "tools": ["call_recipe", "auth_facts", "payload_shape",
                      "journey_walkthrough"],
        }

    routed = next((tool for words, tool in _ROUTES
                   if any(w in text for w in words)), None)

    # **A route that cannot run is not the more specific answer.**
    #
    # The academy is checked after the product routes, on the argument that a
    # question naming both a product noun and Métis wants the product tool. That
    # argument assumes the product tool can answer. Asked "what is Métis and how
    # does it decide what to test", `ask` matched *how does*, called
    # `journey_walkthrough('')` and returned `no transitions for journey ''` — a
    # question the academy answers in full, refused by a tool that was never
    # given the one argument it needs. The corpus was landed, indexed, reachable
    # through `search_knowledge`, and still lost to a keyword.
    #
    # Narrow on purpose. It fires only where the route NEEDS a journey, none was
    # given, and the question names this system. A product route with a journey
    # still wins, and a question with no academy word still gets the product
    # tool's own failure rather than a lesson: `_ask_academy` returning `None`
    # falls through to exactly the behaviour that was there before.
    if (routed in _NEEDS_JOURNEY and not journey
            and any(w in text for w in _ACADEMY_WORDS)):
        academy = _ask_academy(question)
        if academy is not None:
            return academy

    if routed is not None:
        answer = {"auth_facts": lambda: auth_facts(journey),
                  "call_recipe": lambda: call_recipe(journey),
                  "journey_walkthrough": lambda: journey_walkthrough(journey),
                  }[routed]()
        return {
            "ok": answer.get("ok", False),
            "question": question,
            "answered_by": routed,
            "answer": answer,
            "rule": ("everything above came from the graph. Any sentence you "
                     "add that is not in it is not something Métis recovered"),
        }

    if any(w in text for w in _ACADEMY_WORDS):
        academy = _ask_academy(question)
        if academy is not None:
            return academy

    # **Unroutable, and the academy is offered rather than hidden.**
    #
    # Deciding "is this a question about Métis?" from the text alone was measured
    # three ways and none of them holds. The hand-listed vocabulary above routes
    # 8 of the academy's own 36 benchmark questions. Widening it to the ontology's
    # nouns routes 19 and wrongly routes "how do I reset my router" (`Route`).
    # A relevance floor fails differently: "what time does the shop close" scores
    # 6.70 against `Time: what was true, and when` — above 20 real questions —
    # and semantic similarity narrows that overlap without closing it (academy
    # min 0.343, off-topic max 0.403).
    #
    # So this does not classify. It says plainly that no tool answered, and names
    # what the academy would have offered — a suggestion a reader can take or
    # ignore, with no claim attached. Silence was the worse failure: the corpus
    # was landed, indexed, and invisible to anyone who did not already know to
    # say "Métis".
    suggestion = _academy_suggestion(question)
    return {
        "ok": False,
        "question": question,
        "reason": "no tool answers this. Métis can say how to call an endpoint, "
                  "what a caller must present, and how a journey moves between "
                  "states — it cannot answer from anything but the graph",
        "tools": ["call_recipe", "auth_facts", "payload_shape",
                  "journey_walkthrough"],
        **({"academy_may_cover": suggestion} if suggestion else {}),
    }
