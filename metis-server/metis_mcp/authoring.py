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


def _inputs_of(raw) -> list[dict]:
    """A transition's `c_inputs` as the parameter dicts a recipe reads.

    Tolerant of the empty and the malformed on purpose: a recipe missing its
    query parameters is a worse answer than one that says so, but an exception
    here would take out the whole tool for one bad row. `_recipe.build` already
    marks what it could not recover.
    """
    import json

    if not raw:
        return []
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, dict)]
    try:
        loaded = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [p for p in loaded if isinstance(p, dict)] if isinstance(loaded, list) else []


def call_recipe(journey: str, route: str = "") -> dict:
    """How to exercise an endpoint: the call, and what makes it fail.

    `route` is `VERB /path`, or empty for every endpoint in the journey. The body
    carries **placeholders describing the accepted values, never sample values**
    (T-9c): a single valid value is one case, where the space is what a case is
    chosen from.
    """
    # **Asked of the BEHAVIOUR, not of the endpoint.** This walked
    # `Endpoint-[:ACCEPTS]->Parameter` until `Parameter` was staged out: a
    # parameter node carried the same five values as its entry in the
    # transition's `c_inputs` and nothing else but bookkeeping, so the graph
    # held one fact twice.
    #
    # The consequence is deliberate and is the whole direction of the tool: an
    # endpoint no transition models has no recipe, because there is no modelled
    # behaviour to exercise. It is reported as an `unmodelled` Finding instead
    # of being answered with a call nobody has specified.
    rows = _rows(f"""
        MATCH (t:{_TRANSITION})-[:DERIVED_FROM]->(e:Endpoint)
        OPTIONAL MATCH (t)-[:EXPECTS|REQUIRES]->(b:{_TYPE})
        OPTIONAL MATCH (e)-[:SECURED_BY]->(sec:SecurityScheme)
        WITH e, t.c_inputs AS inputs,
             collect(DISTINCT b.id) AS bodies,
             collect(DISTINCT t.c_outcome_status) AS statuses,
             collect(DISTINCT properties(sec)) AS security
        RETURN properties(e) AS endpoint, inputs, bodies, statuses, security
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
        # `c_inputs` is the flat form of exactly what `Parameter` nodes held:
        # name, location, required, type_name, constraints. Decoded through
        # `ontology.facts` so the encoder and the reader cannot drift.
        endpoint["parameters"] = _inputs_of(row["inputs"])
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
    # **Counted from the behaviour, and decoded here rather than in Cypher.**
    # This read `Endpoint-[:ACCEPTS]->Parameter{location:'header'}` until
    # `Parameter` was staged out. The same facts live in the transition's
    # `c_inputs`, which is JSON — and this deployment is Community with no APOC,
    # so there is no `fromJsonList` to filter with. Pulling the rows and
    # counting in Python is the honest version of that constraint; the
    # alternative was a string `CONTAINS` that would match a header named inside
    # somebody's description.
    from collections import Counter

    seen_by: dict[str, set] = {}
    required_of: dict[str, bool] = {}
    for row in _rows(f"""
            MATCH (t:{_TRANSITION})-[:DERIVED_FROM]->(e:Endpoint)
            RETURN t.c_inputs AS inputs, e.id AS endpoint"""):
        for parameter in _inputs_of(row["inputs"]):
            if parameter.get("location") != "header":
                continue
            name = parameter.get("name", "")
            seen_by.setdefault(name, set()).add(row["endpoint"])
            # Required anywhere is required: a header one call may omit and
            # another may not is still one a caller has to know about.
            required_of[name] = required_of.get(name, False) or bool(
                parameter.get("required"))
    headers = sorted(
        ({"name": name, "endpoints": len(endpoints),
          "required": required_of.get(name, False)}
         for name, endpoints in seen_by.items()),
        key=lambda h: (-h["endpoints"], h["name"]))
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

# The corpus roots, as Cypher. A `Topic` with no parent that has lessons beneath
# it is an academy's root, and `lessons.system_of` names it after the SYSTEM the
# corpus documents -- `topic:metis`, `topic:athena`.
_CORPUS_ROOTS = """
MATCH (l:Lesson)-[:BELONGS_TO]->(:Topic)-[:BELONGS_TO*0..]->(root:Topic)
WHERE NOT (root)-[:BELONGS_TO]->(:Topic)
RETURN DISTINCT toLower(root.name) AS name
"""


def corpus_words(session) -> frozenset:
    """Every system this graph holds an academy about.

    **`_ACADEMY_WORDS` names one system, and the graph holds as many as somebody
    lands.** A second corpus -- `system: athena` -- landed, embedded and
    correctly ranked by `search_knowledge`, was unreachable through `ask`: no
    word in a question about Athena appears in a hand-listed vocabulary about
    Métis, so the question fell through to unroutable. That is the exact failure
    `_ask_academy` was written to fix, reproduced one corpus later, because the
    fix was a list rather than a lookup.

    Read from the graph rather than configured. The name is already declared,
    once, in the corpus's own `README.md`, and `lessons.system_of` refuses a
    corpus that does not declare it -- so the routing vocabulary and the topic
    tree cannot disagree about what a corpus is called.
    """
    try:
        return frozenset(r["name"] for r in session.run(_CORPUS_ROOTS)
                         if (r["name"] or "").strip())
    except Exception:                              # noqa: BLE001 - routing aid
        return frozenset()                         # never worth an error


def _for_search(question: str, extra_noise=()) -> str:
    """The question with its routing words removed, or unchanged if that empties it.

    `extra_noise` carries the corpus names this graph actually holds. The reason
    is the one measured for "Métis" and applies to any corpus name: the word that
    ROUTES a question to a corpus appears in every document in it, so it says
    nothing about WHICH document answers, and leaving it in pulls the ranking
    toward whichever lesson repeats the name most.
    """
    import re

    from metis_mcp.retrieval import fold

    extra = {w for w in extra_noise if w} | {fold(w) for w in extra_noise if w}
    words = tuple(_TRIGGER_NOISE) + tuple(sorted(extra))
    stripped = re.sub(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", " ",
                      question, flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", stripped).strip(" ,.?!")
    return stripped or question


_CORPUS_LESSONS = """
MATCH (l:Lesson)-[:BELONGS_TO]->(:Topic)-[:BELONGS_TO*0..]->(root:Topic)
WHERE toLower(root.name) = $name AND NOT (root)-[:BELONGS_TO]->(:Topic)
RETURN collect(DISTINCT l.id) AS ids
"""


def _named_corpus(session, text: str) -> str:
    """The corpus this question names, or `""` if it names none.

    Only a corpus NAME scopes an answer. A question matching `_ACADEMY_WORDS`
    alone -- "why is everything sitting in Quarantine" -- names no system and is
    searched across everything, which is what it was before a second corpus
    existed.
    """
    # **Folded on both sides.** A corpus root is named from its own README, so
    # `system: métis` is as legal as `system: metis`, and a reader typing
    # `Metis` on an English keyboard must still reach it. This is the same
    # accent problem `retrieval.fold` exists for, and getting it wrong here
    # scoped "how does Métis model Athena" to Athena alone, because only the
    # unaccented name matched.
    from metis_mcp.retrieval import fold

    folded = fold(text)
    named = [w for w in corpus_words(session)
             if w in text or fold(w) in folded]
    # Two corpus names in one question scopes to neither: "how does Métis model
    # Athena" is a question about the pair, and picking one of them would answer
    # half of it while looking certain.
    return named[0] if len(named) == 1 else ""


def _lessons_in(session, corpus: str) -> frozenset:
    row = session.run(_CORPUS_LESSONS, {"name": corpus}).single()
    return frozenset((row or {}).get("ids") or ())


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

    query = _for_search(question, corpus_words(session))

    # **A question that names a corpus is answered from that corpus.** Asked
    # "what is Athena and what does it collect", search returned
    # `What Métis does not do` first -- a confident answer from the wrong system,
    # which is worse than no answer. Scoping fixes it at the only point where the
    # intent is known.
    #
    # The window widens when scoped, because filtering the top 5 of a mixed
    # ranking can leave nothing: the right lesson placed 6th is a truncation
    # artefact, not an absence.
    corpus = _named_corpus(session, question.lower())
    keep = _lessons_in(session, corpus) if corpus else None
    window = limit * 4 if keep else limit

    def finish(rows):
        rows = [r for r in rows if r.get("label") == "Lesson"]
        if keep is not None:
            rows = [r for r in rows if r.get("id") in keep]
        return rows[:limit]

    if provider is not None:
        try:
            hits = [h.__dict__ if hasattr(h, "__dict__") else dict(h)
                    for h in hybrid_search(session, query,
                                           provider=provider, limit=window)]
            return finish(hits)
        except RetrievalRefused:
            # A corpus embedded with another model. Refusing the whole question
            # would be worse than answering it the way a default install does.
            pass
    return finish(search_knowledge(session, query, limit=window))


def _names_a_system(text: str) -> bool:
    """Does this question name a system some academy in this graph documents?

    The hand-listed vocabulary stays: `g1`, `quarantine`, `lifecycle_state` and
    the rest name Métis without saying "Métis", and no corpus root would supply
    them. What the graph adds is the corpus NAMES, so landing an academy makes
    `ask` able to route to it without an edit here.
    """
    if any(w in text for w in _ACADEMY_WORDS):
        return True
    from metis_mcp.mbt.graph_session import GraphNotConfigured, session

    from metis_mcp.retrieval import fold

    folded = fold(text)
    try:
        with session() as s:
            return any(name in text or fold(name) in folded
                       for name in corpus_words(s))
    except (GraphNotConfigured, Exception):        # noqa: BLE001 - routing aid
        return False


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
        # **The note used to name Métis.** With a second corpus landed it told a
        # reader asking about Athena that "the academy is about Métis itself" and
        # to "ask again naming Métis" — false, and advice that would not have
        # worked. What is true of any corpus is that nothing checked the question
        # belongs to it, which is the whole reason this is a suggestion.
        "note": "not an answer — no tool routed this question, and nothing "
                "checked that the corpus this came from is the right one. Name "
                "the system you are asking about to have it answered from there.",
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
    if routed in _NEEDS_JOURNEY and not journey and _names_a_system(text):
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

    if _names_a_system(text):
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
