"""
Land a source's output in the graph (application spec S-4, D-8b, §16.1).

Closes the provenance gap: until now nothing wrote an `Episode` through a real
source path, so `source_episode_id` pointed at a hand-seeded node. Every element
landed here carries the id of the Episode that justifies it (spec P1).

Pure planner, thin writer -- and under Community edition that split is not a
stylistic preference. The application gate is the *sole* guarantee that required
properties exist (D-8a/D-8b), so a plan is validated in full before any statement
reaches the database.

Everything lands at **Quarantine**. Authoring is not approving (E-11): a model
produced by any source, including a human sitting at a keyboard, is a candidate
until someone else decides otherwise (N-10).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from metis_mcp.mbt.guard_language import describe_guard
from metis_mcp.mbt.model import QUARANTINE
from metis_mcp.mbt.naming import transition_display_name
from metis_mcp.model_sources.base import SourceResult
from metis_mcp.ontology import validate, validate_relationship
from metis_mcp.ontology.labels import (
    NEED_REVIEW, NEEDS_REVIEW_STATES, PROJECT_PROPERTY,
)


# **Human facts. A write path may never assert these.**
#
# Machine facts are re-derived on every run — guards, triggers, anchors, inputs,
# outcomes, evidence — so a writer asserts them freely. These four are not
# reproducible by any amount of re-extraction: a reviewer decided them.
#
# They were in the unconditional `SET n += row`, which is why every re-ingest
# reset the whole estate to Quarantine and re-approving 206 transitions was the
# standing cost of keeping the graph current. They now go through
# `ON CREATE SET`, so a NEW node still starts at Quarantine (S-4) and an existing
# one keeps what a human gave it.
#
# `ON CREATE SET` alone is not sufficient and is not the whole mechanism: it
# would also keep an approval whose behaviour has since changed, which is the
# dangerous direction. Two things supply the revocation, one per kind of fact:
#
#   ELEMENTS  `identity.carry_human_facts` revokes approval where behaviour
#             changed, before the plan is ever built (I-17, I-18). A transition
#             persists across a guard edit, so its approval has to be taken away
#             explicitly.
#   CLAIMS    identity does the work instead. A `Requirement` whose text changes
#             is a DIFFERENT node under `claim_id`, so it lands at Quarantine
#             because it is new -- and the earlier revision keeps the approval a
#             human gave it, which is what I-19 means by retaining the prior
#             decision in history. `plan_supersession` closes the old window.
#
# The claim half did not exist, and the gap was exactly the shape this comment
# describes: `lifecycle_state` rode in `ON CREATE SET` and `text` did not, so an
# Approved requirement silently acquired new wording and stayed Approved.
HUMAN_FACTS = ("lifecycle_state", "name", "name_tier", "provenance")

# Set once, when the node first appears, and never re-asserted.
#
# **Not a human fact** -- no reviewer decided it -- but it needs the same
# mechanism for a different reason, which is why it is a second name rather than
# an addition to the tuple above. Whoever adds a field here has to answer which
# reason applies.
#
# An Episode's id is content-derived (D-8), so the same node means the same
# ingested content, and `t_recorded` is therefore "when this content was first
# seen". Re-deriving it on a later run does not record a new fact; it restates
# the clock.
#
# It used to ride in the unconditional `SET n += row.machine`, so re-landing
# unchanged content rewrote the timestamp and no two runs ever produced the same
# graph. TR-6 held for identity -- no duplicate node -- and failed for bytes,
# which is the half anyone diffing two runs actually needs.
# **`revision` belongs here, and rode in the rewritten clause instead.**
# It is set when a claim node is created and is never re-derived: a revision
# counts how many times the claim CHANGED, and re-landing identical content did
# not change it. Every writer hardcoded `"revision": 1`, so an unconditional
# `SET` reset it to 1 on every land -- the property `Requirement` declares as
# required, that §8.4 is named for, and that nothing could ever increment.
FIRST_SEEN_FACTS = ("t_recorded", "revision")

# Set at creation and changed only by a deliberate act, never by re-landing.
#
# `valid_to` is the dangerous one, and the reason this is not simply left as a
# machine fact. Invalidation SETS `valid_to`; if landing re-asserted it, the next
# routine extraction would reset it to "" and silently resurrect a superseded
# fact. An invalidation that an unrelated re-run can undo is not an invalidation.
#
# `valid_from` is here for the ordinary first-seen reason: the instant a claim
# started being true does not change because somebody re-ran extraction.
VALIDITY_FACTS = ("valid_from", "valid_to")

# Everything written by `ON CREATE SET`. Three reasons, one clause — kept as
# three names because whoever adds a field has to answer which reason applies.
ON_CREATE_FACTS = HUMAN_FACTS + FIRST_SEEN_FACTS + VALIDITY_FACTS


def split_row(row: dict) -> dict:
    """One planned node's properties, split into what MERGE may re-assert.

    Pure and named so the rule is inspectable: the split used to be an inline
    comprehension inside `land`, reachable only with a live session, so the one
    thing worth asserting about it could not be asserted without a database.
    """
    return {
        "id": row["id"],
        "on_create": {k: v for k, v in row.items() if k in ON_CREATE_FACTS},
        "machine": {k: v for k, v in row.items() if k not in ON_CREATE_FACTS},
    }


# Which edge each kind of evidence gets. One place, so a transition cannot point
# at an `Endpoint` with one relationship type here and another somewhere else.
EVIDENCE_RELATIONSHIPS = {
    "Endpoint": "DERIVED_FROM",
    "DeclaredOutcome": "DERIVED_FROM",
    "ExceptionMapping": "DERIVED_FROM",
    # No `Field`: a field is a property of its type, not a node (X-6d), and the
    # label is staged out. The entry outlived the label, and because a mapped
    # label is *planned* before it is validated, a single field on a rejection
    # made `validate_relationship` reject `(ApiCall)-[:REQUIRES]->(Field)`, put
    # "unknown label 'Field'" into `plan.errors`, and refuse the WHOLE model
    # with "nothing was written". `test_evidence_relationships_name_real_labels`
    # now fails the moment this map names a label the ontology does not have.
    "Class": "EXPECTS",
    "Check": "CONSTRAINED_BY",
}


# A classified transition is written as `:ApiCall` or `:UiAction` **instead of**
# `:Transition` (see `ontology.labels`), so anything planning an edge INTO a
# transition has to name the label the node actually carries.
#
# Shared rather than inlined because getting it wrong is silent: the ontology
# check walks the specialisation chain and passes, and then the write emits
# `MATCH (b:Transition {id: ...})` against a node labelled `:ApiCall` and merges
# nothing. `land` reports that as `unmatched`; it does not fail.
TRANSITION_LABELS = {"api": "ApiCall", "ui": "UiAction"}


def transition_label_for(surface: str) -> str:
    return TRANSITION_LABELS.get(surface, "Transition")


# The same rule one level up. `RestServer` and `WebServer` specialise
# `Component`, and a specialisation is written INSTEAD of its parent -- so
# without this they were declared, catalogued, and written by nothing, while
# `graph_loader` carried a comment asserting they were. A comment the code does
# not back is worse than no comment.
COMPONENT_LABELS = {"api": "RestServer", "ui": "WebServer"}


def component_label_for(surface: str) -> str:
    """`RestServer` / `WebServer`, or the generic parent when the surface is
    unknown -- which leaves `:Component` meaning "unclassified" and therefore
    findable, exactly as `:Transition` does."""
    return COMPONENT_LABELS.get(surface, "Component")


def namespaced_id(model_id: str, element_id: str) -> str:
    """`admin-api::ac::LoggedOut::Submit::Failed1` — the id a node is written with.

    Shared for the same reason `transition_label_for` is: an edge planned against
    the bare id passes every check and then merges nothing, because no node
    carries that id. `identity.keys.bare_id` is the inverse.
    """
    return f"{model_id}::{element_id}"


def graph_transition_id(model, transition_id: str) -> str:
    """The id a transition is WRITTEN with — its natural key, not its source's id.

    **This is what lets two intakes describe one behaviour once** (I-2, R12).
    A transition's id comes from whatever recovered it: the code intake mints a
    Java signature, the OpenAPI intake mints an operationId. Measured on the demo
    corpus, `POST /record` reaches the graph as

        code     com.example.records.RecordController.create:…ResponseEntity(…)::POST
        OpenAPI  createRecord::POST->PostRecord201

    — two nodes for one behaviour, and a model that then claims twice the
    behaviour the service has, with no edge between the halves and nothing
    reporting it.

    `identity.keys.transition_key` has defined the natural key all along —
    `(model, source state, trigger, target state)` — and no writer used it.
    Landing does now, so the same behaviour recovered twice MERGEs onto one node
    and a deviation is what is left over rather than what has to be hunted for.

    Every writer of a transition id must go through here. One that mints its own
    plans an edge against a node that does not exist, which `land` reports as
    unmatched rather than failing.
    """
    from metis_mcp.identity.keys import short, transition_key

    transition = model.transitions.get(transition_id)
    if transition is None:
        return ensure_namespaced(model.id, transition_id)
    return f"{model.id}::{short(transition_key(model.id, transition, model))}"


def ensure_namespaced(model_id: str, element_id: str) -> str:
    """`namespaced_id`, but idempotent — safe on an id that already carries it.

    Both forms are real and reach the same writers. A model read from a **file**
    has bare ids (`Ready`); the same model read from the **graph** comes back
    already namespaced (`archive-api::Ready`), because that is what landing
    wrote. `plan_persist` takes either, so applying `namespaced_id`
    unconditionally produced `archive-api::archive-api::Ready` and every
    edge matched nothing.

    The test is a prefix check, **not** `"::" in element_id`: a Web element id
    is `ui::ApiSpecDetailPage::/spec/::Ok200`, which contains `::` while being
    entirely un-namespaced. That containment test is what left
    `records-spec-ui`'s findings unattached.
    """
    prefix = f"{model_id}::"
    return element_id if element_id.startswith(prefix) else prefix + element_id


@dataclass(frozen=True)
class PlannedNode:
    label: str
    properties: dict
    # Kept for nodes that genuinely carry more than one label. Transitions do
    # not: a classified transition is written as `:ApiCall` or `:UiAction`
    # **instead of** `:Transition`, which leaves the generic label meaning
    # "unclassified" and therefore findable.
    also: tuple = ()


@dataclass(frozen=True)
class PlannedEdge:
    from_label: str
    from_id: str
    rel_type: str
    to_label: str
    to_id: str
    # **Facts about the relationship itself.** There was no such field, so no
    # edge anywhere could carry one -- and `LINKS_TO` is the case that made the
    # absence visible: the intake reads a tracker link's `relation` (`parent`,
    # `blocks`, `duplicates`), plans the edge, and had nowhere to put the kind.
    # Every link landed indistinguishable from every other, and
    # `read.requirement_hierarchy` honestly reported `"type": "unknown"` for all
    # of them, which makes "what are this epic's children" unanswerable.
    #
    # Empty for almost every edge, and that is correct: a `HAS_AC` or a
    # `VALIDATES` says everything by existing. Only a relationship whose KIND
    # varies needs this.
    properties: dict = field(default_factory=dict)


class PlanBuilder:
    """Propose a node or an edge, validating it first and refusing on failure.

    **Why this is a class and not a closure each caller writes.** It was the
    latter: nine modules each defined a local `add_node`/`add_edge` over their
    own `plan`, and six of the `add_edge` bodies were byte-identical while the
    `add_node` bodies differed only in which name the validator had been
    imported under. That is not nine decisions, it is one decision copied nine
    times -- and the copies had already drifted in the way that matters: only
    `plan_landing`'s validated the `also` labels, and only `intake_landing`'s
    could carry edge properties, so which facts a plan could legally express
    depended on which module happened to build it.

    Deliberately a plain mixin rather than a base dataclass: `LandingPlan`
    declares `episode_id` with no default, and inheriting fields that have one
    would make that a field-ordering error.

    Both methods return whether the thing was accepted, so a caller that must
    not build on a refused node can branch; the callers that append
    unconditionally ignore it, which is what the previous `-> None` closures did.
    """

    nodes: list[PlannedNode]
    edges: list[PlannedEdge]
    errors: list[str]

    @property
    def is_legal(self) -> bool:
        return not self.errors

    def by_label(self, label: str) -> list[PlannedNode]:
        return [n for n in self.nodes if n.label == label]

    def add_node(self, label: str, props: dict, also: tuple = ()) -> bool:
        outcome = validate(label, props)
        if not outcome.valid:
            self.errors.extend(outcome.errors)
            return False
        # Each additional label is validated too: a specialisation narrows its
        # parent (an `ApiCall` may not carry `surface: ui`), and writing one
        # without checking would put a node in the graph that its own label
        # forbids.
        for extra in also:
            extra_outcome = validate(extra, props)
            if not extra_outcome.valid:
                self.errors.extend(extra_outcome.errors)
                return False
        self.nodes.append(
            PlannedNode(label=label, properties=props, also=tuple(also)))
        return True

    def add_edge(self, from_label: str, from_id: str, rel: str, to_label: str,
                 to_id: str, properties: dict | None = None) -> bool:
        outcome = validate_relationship(from_label, rel, to_label)
        if not outcome.valid:
            self.errors.extend(outcome.errors)
            return False
        self.edges.append(PlannedEdge(from_label, from_id, rel, to_label, to_id,
                                      dict(properties or {})))
        return True


@dataclass
class LandingPlan(PlanBuilder):
    episode_id: str
    nodes: list[PlannedNode] = field(default_factory=list)
    edges: list[PlannedEdge] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    # Which project everything in this plan belongs to. Stamped onto every node
    # as `m_project` by `land`, so "everything belonging to Athena" is a property
    # lookup rather than a guess from an id prefix.
    #
    # Empty is legal and means "not stated". It is not silently fine: a plan that
    # names no project lands nodes `storage export` cannot claim, and export
    # reports that count rather than quietly emitting a short file.
    project: str = ""


def _wording(transition):
    """The guard in business language, from the resource its trigger names."""
    from code_analysis.unfolding import resource_noun, resource_of

    _, _, path = (getattr(transition, "trigger", "") or "").partition(" ")
    return describe_guard(getattr(transition, "guard", ""),
                          resource_noun(resource_of(path)))


def episode_id_for(result: SourceResult, content_key: str) -> str:
    """Content-derived (spec D-8): re-landing identical output is a no-op."""
    basis = "|".join((result.source_connector, result.model.id, content_key))
    return "ep-" + hashlib.sha256(basis.encode()).hexdigest()[:16]


def _content_key(result: SourceResult) -> str:
    model = result.model
    parts = [model.id]
    for sid in model.state_ids():
        s = model.states[sid]
        parts.append(f"S|{s.id}|{s.name}|{s.surface}|{s.is_initial}")
    # Property names carry a prefix naming what each is FOR: `c_` the call,
    # `b_` the behaviour, `p_` the page. A node shows its properties in one
    # alphabetical table, so the prefix is what makes the grouping visible where
    # somebody actually reads it. `rendering.contract.graph_name` is the rule;
    # `test_generation_contract` asserts these keys match it.
    for tid in model.transition_ids():
        t = model.transitions[tid]
        parts.append(f"T|{t.id}|{t.source}|{t.trigger}|{t.target}|{t.guard}|"
                     f"{t.implementation_status}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def plan_landing(result: SourceResult, journey: str,
                 job_id: str = "manual", t_recorded: str | None = None) -> LandingPlan:
    """Build a fully-validated landing plan. No session, no writes."""
    content_key = _content_key(result)
    episode_id = episode_id_for(result, content_key)
    recorded = t_recorded or datetime.now(timezone.utc).isoformat(timespec="seconds")

    plan = LandingPlan(episode_id=episode_id, skipped=list(result.skipped))

    # The Episode is exempt from source_episode_id -- it is the provenance record
    # and cannot point at one (spec D-8, BASELINE_EXEMPT).
    plan.add_node("Episode", {
        "id": episode_id,
        "name": f"{result.source_connector}: {result.model.id}",
        "t_recorded": recorded,
        "source_connector": result.source_connector,
        "job_id": job_id,
        "content_key": content_key,
        "evidence": ", ".join(f"{k}={v}" for k, v in sorted(result.evidence.items())),
        # Spec N-10. Every element landed by this Episode was proposed by this
        # identity, so the separation-of-duties check has something to compare a
        # reviewer against. Carried as its own property, not parsed back out of
        # `evidence`: a gate that depends on splitting a joined string is a gate
        # that stops working the first time a value contains a comma.
        "proposed_by": result.proposed_by or "unknown",
        # **The commit, promoted out of `evidence` for the reason directly
        # above.** P-16 says a coverage figure states the version and commit it
        # refers to, and a report could say neither until `persist` ran: the
        # `Component` node carries them and is created at generation time.
        #
        # Landing knows the commit — every code source puts it in `evidence` —
        # and it was reachable only by splitting that joined string, which is
        # exactly what the `proposed_by` comment says not to depend on. So it is
        # its own property, on the same argument.
        #
        # It does NOT make a Component: that label requires `version`, and a
        # version means "what was generated and published". Landing has no
        # version and inventing one would put a fiction where P-16 wants a fact.
        # What this gives a report is the honest half — *the commit this model
        # was extracted at* — which is strictly better than "not recorded".
        "commit": str(result.evidence.get("commit", "") or ""),
    })

    model = result.model
    surface = model.id.rpartition("-")[2] or "api"

    def graph_state_id(state_id: str) -> str:
        """Namespace a state id by its model (spec I-2, D-8).

        A state's natural key is `(model, surface, observable_signature)` --
        `identity/keys.py` has said so all along, but this writer used the bare
        id. With one model landed that is invisible; with seven it is severe.
        Every synthesised API model calls its initial state `Ready`, so all seven
        MERGE-d onto ONE node: 145 transitions hung off it, and landing a UI model
        whose `Ready` is not initial silently flipped `is_initial` to false for
        every API model at once. Caught because validation then reported "no
        initial state" for all seven.
        """
        return ensure_namespaced(model.id, state_id)

    # Web surface: the pages a state belongs to become their own nodes, so
    # "which pages does this component have, and what condition is each in" is a
    # query rather than a substring search inside a transition id. A Page is a
    # grouping node and never a link in the walk, so path generation is untouched.
    pages: dict[str, str] = {}
    for sid in model.state_ids():
        page = getattr(model.states[sid], "page", "")
        if page and page not in pages:
            page_id = f"{model.id}::page::{page}"
            pages[page] = page_id
            plan.add_node("Page", {
                "id": page_id, "source_episode_id": episode_id, "name": page,
                "component": model.id, "surface": "ui",
            })

    for sid in model.state_ids():
        state = model.states[sid]
        plan.add_node("State", {
            "id": graph_state_id(sid), "source_episode_id": episode_id, "name": state.name,
            # The model this element belongs to, as its own property.
            #
            # It is already the first half of the id (`{model_id}::{element_id}`,
            # see `namespaced_id`), so this adds no information — it adds
            # QUERYABILITY. "Every element of this model" was a string operation
            # on the id (`STARTS WITH 'records-api::'`), which no index serves
            # and which breaks on any id containing `::` for another reason.
            "model_id": model.id,
            "b_surface": state.surface, "b_is_initial": state.is_initial,
            "lifecycle_state": QUARANTINE, "functional_areas": [journey],
            "p_page": getattr(state, "page", ""),
            "p_condition": getattr(state, "condition", ""),
            "x_name_tier": getattr(state, "name_tier", ""),
        })
        page = getattr(state, "page", "")
        if page:
            plan.add_edge("Page", pages[page], "SHOWS", "State", graph_state_id(sid))

    # The specific label where the surface is known, the generic one where it is
    # not. `MATCH (t:Transition)` is then a worklist rather than a synonym for
    # every transition in the graph.
    transition_label = transition_label_for(surface)

    for tid in model.transition_ids():
        transition = model.transitions[tid]
        plan.add_node(transition_label, {
            "id": graph_transition_id(model, tid), "source_episode_id": episode_id,
            # See the note on State above. Same reason: `graph_transition_id`
            # namespaces this too, so the value is a duplicate of the id's
            # prefix and what it buys is an indexed lookup rather than a
            # `STARTS WITH` scan.
            "model_id": model.id,
            # D-8: `name` is display data, not identity. It used to be the id --
            # a Java signature with a return type in it -- so every review screen
            # and every report showed a reviewer the implementation instead of
            # the behaviour they were being asked to decide about.
            "name": transition_display_name(transition, model.states),
            "c_trigger": transition.trigger,
            "b_guard_expression": transition.guard,
            "b_implementation_status": transition.implementation_status,
            "b_surface": surface,
            "x_extraction_method": result.extraction_method,
            "lifecycle_state": QUARANTINE, "functional_areas": [journey],
            "x_guard_anchor": transition.guard_anchor,
            "x_source_state_unresolved": transition.source_state_unresolved,
            "c_outcome_status": transition.outcome_status,
            # See labels.py: structure cannot be a Neo4j property, so the detail
            # is JSON and the two facts worth filtering on are their own columns.
            "c_inputs": json.dumps(list(transition.inputs), sort_keys=True),
            "c_security": json.dumps(list(transition.security), sort_keys=True),
            # `c_input_count` and `c_requires_body` were lifted out of the
            # inputs blob "to carry the parts worth filtering on". Nothing ever
            # filtered on them — no reader anywhere in the tree, and
            # `validation.check_callability` computes the same predicate in
            # Python over an in-memory model. Two properties on every transition
            # to answer a question nobody asked.
            "x_outcome_source": getattr(transition, "outcome_source", "") or "constructed",
            "x_guard_claim": getattr(transition, "guard_claim", ""),
            # GD-3's variants. A list of strings IS a legal Neo4j property, so
            # unlike `inputs` these need no JSON envelope -- and a reviewer
            # reading the rejection sees the constraints it is about.
            "data_requirements": list(getattr(transition, "data_requirements", ()) or ()),
            # The expected response. Empty `response_body` means NO body (a 204,
            # or a `ResponseEntity<Void>`), which is a fact a test can assert --
            # not a recovery failure.
            "c_response_body": getattr(transition, "response_body", ""),
            "c_media_types": list(getattr(transition, "media_types", ()) or ()),
            # X-8. The guard in business language, and which tier said it --
            # `verbatim` means nothing has translated it yet, which is the
            # worklist a reviewer or an acceptance criterion works through.
            # Computed here where a source did not supply it. Synthesis words
            # its own guards; a hand-authored model landed from a file does not,
            # and 17 login-example transitions therefore carried no tier at all
            # -- which makes "show me everything still in implementation
            # language" quietly answer for part of the graph.
            "x_guard_wording": (getattr(transition, "guard_wording", "")
                              or _wording(transition).text),
            "x_guard_tier": (getattr(transition, "guard_tier", "")
                           or _wording(transition).tier),
            "x_name_tier": getattr(transition, "name_tier", ""),
        })
        plan.add_edge("State", graph_state_id(transition.source), "WHEN",
                 transition_label, graph_transition_id(model, tid))
        plan.add_edge(transition_label, graph_transition_id(model, tid), "THEN", "State",
                 graph_state_id(transition.target))

        # D-14: provenance is an edge. Each pair is `(label, evidence node id)`
        # computed by synthesis while the raw facts were still in hand; the
        # relationship type follows from the label, so this cannot drift from
        # the catalogue without `validate_relationship` refusing it.
        for label, node_id in getattr(transition, "evidence", ()) or ():
            rel = EVIDENCE_RELATIONSHIPS.get(label)
            if rel:
                plan.add_edge(transition_label, graph_transition_id(model, tid), rel,
                         label, node_id)

    # **What the source could not model, carried into the graph.** These were
    # printed by `metis land` and nothing else — the reason scrolled past in a
    # terminal and was gone, so a state the extraction could not connect arrived
    # in the graph with no record of why.
    #
    # The cost of that is concrete: `react_ui_synthesis` reports
    # "RecordDetailPage.page: no 'loading' state recovered; its ['error','ready']
    # state(s) have no recovered entry" — a precise, actionable recall gap. It
    # went nowhere, and M-18 later reported the same states as "unreachable — a
    # dead state, or a transition into it is missing", which sends a reader
    # looking for a modelling mistake instead of a ternary the pack cannot read.
    #
    # X-5a's rule is that what is not landed is counted and reported. This is the
    # other half: what IS landed but unusable says so too.
    for element_id, reason in getattr(result, "skipped", ()) or ():
        finding_id = "finding:" + hashlib.sha256(
            f"unmodelled|{model.id}|{element_id}|{reason}".encode()).hexdigest()[:16]
        if plan.add_node("Finding", {
            "id": finding_id, "source_episode_id": episode_id,
            "name": "unmodelled", "finding_type": "unmodelled",
            "severity": "advisory",
            # Some sources already carry the element id inside the reason —
            # `react-ui` splits its own message to produce one, and passes the
            # whole message as both for a finding. Prefixing again stutters.
            "detail": (reason if reason == element_id
                       or reason.startswith(f"{element_id}:")
                       else f"{element_id}: {reason}"),
            "remedy": "the source could not model this; recover it upstream or "
                      "author the missing element",
            "resolution": "open", "lifecycle_state": QUARANTINE,
        }):
            plan.add_edge("Finding", finding_id, "ABOUT",
                     component_label_for(surface), model.id)

    return plan


@dataclass
class LandingResult:
    episode_id: str = ""
    nodes_written: int = 0
    edges_written: int = 0
    refused: str | None = None
    # Edges whose plan was legal but whose endpoints were not both present when
    # the statement ran. See `land` -- this is the difference between what was
    # planned and what the database actually holds.
    unmatched: list = field(default_factory=list)
    # Claims this landing replaced: one entry per requirement, criterion,
    # specification or intent whose text changed. Reported rather than counted,
    # because a superseded requirement is the single thing in a landing a
    # reviewer most needs to be told about -- it is a claim somebody had already
    # approved that now says something else.
    superseded: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.refused is None


def _with_marker(node: PlannedNode, props: dict) -> tuple:
    """`node.also`, plus `:NeedReview` when this node still owes a decision.

    **Applied here rather than in each planner, and that is the whole point.**
    Eight planners produce nodes -- behaviour, documentation, glossary, intent,
    structure, intake, spec documents, features -- and every one of them lands
    at Quarantine (S-4). Marking them one by one would mean the ninth planner
    somebody writes is unmarked, and nothing would notice: the node would look
    settled while being unreviewed, which is the safest-looking way to get the
    dangerous answer.

    Driven off `lifecycle_state`, which stays authoritative. A node with no
    lifecycle at all -- an `Episode`, an `Endpoint` -- is a fact rather than a
    candidate, and facts are not reviewed.
    """
    state = props.get("lifecycle_state")
    if state in NEEDS_REVIEW_STATES:
        return tuple(dict.fromkeys((*node.also, NEED_REVIEW)))
    return node.also


def land(session, plan: LandingPlan) -> LandingResult:
    """Execute an already-legal plan. Refuses an illegal one outright.

    **One statement per group, not per row.** This used to run a `session.run`
    for every node and every edge, which is invisible at ~250 nodes and is not at
    the ~23,000 writes an evidence layer produces. Rows are grouped by label and
    by `(from, rel, to)` triple and written with `UNWIND`; the MERGE semantics
    and the id-keying are unchanged, so a plan lands identically either way.

    **Counts come back from the database, never from `len(rows)`.** This project
    has already shipped that bug twice -- `persist_invokes` reported "91 INVOKES"
    into a graph holding zero, because an edge statement opens with two `MATCH`es
    and merges nothing when either id is absent, while the counter incremented
    regardless. `RETURN count(*)` is what the database did; the difference is
    reported as `unmatched` rather than rounded away.
    """
    if not plan.is_legal:
        return LandingResult(refused=f"{len(plan.errors)} validation error(s): "
                                     f"{plan.errors[0]}")

    # **Supersession, before anything is written.** A claim whose text changed
    # is a new node under `claim_id`, so the graph would otherwise end up with
    # two open validity windows for one requirement and no way to tell which is
    # current. Reading first, stamping the revision, then closing the previous
    # window after the write is the order that leaves no moment where the old
    # claim is closed and the new one does not exist yet.
    from metis_mcp.identity.keys import logical_key_of
    from metis_mcp.ontology.labels import VALIDITY_LABELS

    claim_keys = {logical_key_of(n.properties.get("id", ""))
                  for n in plan.nodes if n.label in VALIDITY_LABELS}
    # Edges naming a claim by its logical key need the same read, so both go
    # through one lookup: the keys the plan MENTIONS, not only the ones it
    # writes.
    from metis_mcp.ontology.labels import VALIDITY_LABELS as _VL

    claim_keys |= {e.to_id for e in plan.edges if e.to_label in _VL}
    current = current_claims(session, claim_keys)
    superseding = plan_supersession(plan, current)
    revisions = superseding.revisions
    unresolved_claims = resolve_claim_edges(plan, current)

    by_label: dict[tuple, list[dict]] = {}
    for node in plan.nodes:
        props = {k: v for k, v in node.properties.items() if v is not None}
        # Stamped here rather than by each plan builder: there are five of them
        # and a project is a property of the RUN, not of any one fact in it.
        # Setting it in one place means a new builder cannot forget it.
        if plan.project:
            props.setdefault(PROJECT_PROPERTY, plan.project)
        # Stamped from what the graph already holds, never from the plan. Every
        # claim writer hardcodes `"revision": 1` because a plan builder cannot
        # know how many times a claim has changed before -- that is a property of
        # the graph, not of the document being landed.
        if node.label in VALIDITY_LABELS and props.get("id") in revisions:
            props["revision"] = revisions[props["id"]]
        by_label.setdefault((node.label, _with_marker(node, props)), []).append(props)

    nodes_written = 0
    for (label, also), rows in by_label.items():
        # **After the ON CREATE clause, not before it.** `ON CREATE SET` has to
        # follow `MERGE` immediately, so appending the label here produced
        # `MERGE (...) SET n:X ON CREATE SET ...` — a syntax error. The `also`
        # path had never been exercised (no node carried a second label until
        # `:NeedReview`), so the bug shipped latent and surfaced the first time
        # something used it.
        extra = "".join(f" SET n:{extra_label}" for extra_label in also)
        # Split in Python, not in Cypher. The map-manipulation this needs in
        # Cypher is an APOC function, and this deployment is Community with no
        # APOC -- but the plainer reason is that two named maps read as what they
        # are, where a `[k IN keys(row) WHERE ...]` comprehension does not.
        split = [split_row(row) for row in rows]
        result = session.run(
            f"UNWIND $rows AS row "
            f"MERGE (n:{label} {{id: row.id}}) "
            f"ON CREATE SET n += row.on_create "
            f"SET n += row.machine{extra} "
            f"RETURN count(n) AS written", rows=split)
        nodes_written += _count(result)

    by_edge: dict[tuple, list[dict]] = {}
    for edge in plan.edges:
        key = (edge.from_label, edge.rel_type, edge.to_label)
        by_edge.setdefault(key, []).append(
            {"a": edge.from_id, "b": edge.to_id,
             "properties": dict(edge.properties or {})})

    edges_written = 0
    unmatched: list[tuple[str, str, str]] = []
    for (from_label, rel_type, to_label), rows in by_edge.items():
        result = session.run(
            f"UNWIND $rows AS row "
            f"MATCH (a:{from_label} {{id: row.a}}), (b:{to_label} {{id: row.b}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            # `+=` rather than `=`: an edge re-landed by a source that knows
            # less about it must not erase what another source recorded. Empty
            # properties are a no-op, which is what keeps this free for the
            # edges that carry none.
            f"SET r += row.properties "
            f"RETURN count(r) AS written", rows=rows)
        written = _count(result)
        edges_written += written
        if written < len(rows):
            unmatched.append(
                (f"{from_label}-[:{rel_type}]->{to_label}",
                 f"{len(rows) - written} of {len(rows)}",
                 "one or both endpoints were absent when this ran — an evidence "
                 "layer must land before the model that derives from it"))

    # **After the write, never before.** Closing first would leave a window in
    # which the old claim is superseded and the new one does not exist, so a read
    # landing there sees no valid requirement at all. Closing after means the
    # worst case is two open windows, which `current_claims` resolves
    # deterministically and a re-run repairs.
    #
    # `invalidate` is the same function `backfill-validity` and the CLI use, and
    # it had no production caller at all until this one: the bi-temporal design
    # was written, tested and never invoked, which is why `valid_to` was `""` on
    # every node in every real graph.
    superseded = []
    if superseding.supersedes:
        closed_at = _superseded_at(plan)
        invalidate(session, superseding.to_close, valid_to=closed_at)
        # **Reopen the window on the node supersession just made current.**
        #
        # `valid_to` is in `VALIDITY_FACTS`, so landing writes it ON CREATE only
        # -- correctly, because a routine re-extraction must never resurrect a
        # superseded fact. That leaves one hole, and it is silent: a claim whose
        # text REVERTS to an earlier wording produces a `claim_id` that already
        # exists with `valid_to` set. The MERGE matches the closed node, does not
        # reopen it, and the supersession above has just closed the one that WAS
        # current -- so the requirement ends with every revision closed and no
        # current one, invisible to every validity-respecting read, while the
        # landing reports success and a new revision number.
        #
        # Measured: state REQ-3 as 409, revise to 423, revise to 410, revise back
        # to 409. Three nodes, all closed, zero current, "landed 2 node(s)".
        #
        # Narrow on purpose. This is not "landing reopens windows" -- it is
        # "supersession reopens the window of the node it has just designated
        # current", which is a deliberate act on one named id, not a side effect
        # of re-running anything.
        #
        # **It prevents the state; it does not repair one already reached.** A
        # graph that lost its current revision before this existed cannot heal by
        # re-landing: `current_claims` finds nothing current for the key, so the
        # plan reads as first-seen, no supersession occurs and this never runs.
        # `graph_smoke.py` asserts the invariant so such a graph is detected
        # rather than quietly read as empty, and `backfill-validity` does not fix
        # it -- that verb sets `valid_from` on pre-validity nodes and nothing
        # reopens a closed window by design.
        _reopen(session, [s.new_id for s in superseding.supersedes])
        superseded = [
            {"label": s.label, "logical_key": s.logical_key,
             "previous_id": s.previous_id, "new_id": s.new_id,
             "revision": s.revision, "closed_at": closed_at}
            for s in superseding.supersedes
        ]

    if unresolved_claims:
        # Named, not counted, and reported as `unmatched` beside the edges that
        # genuinely failed to match -- because that is what they will do. The
        # difference worth stating is WHY: not "the endpoint had not landed yet"
        # but "no claim with this key exists at all".
        unmatched.append(
            ("claim reference", f"{len(unresolved_claims)} unresolved",
             "edges name claims that do not exist in this graph: "
             + ", ".join(sorted(set(unresolved_claims))[:5])))

    return LandingResult(episode_id=plan.episode_id,
                         nodes_written=nodes_written, edges_written=edges_written,
                         unmatched=unmatched, superseded=superseded)


def _superseded_at(plan: LandingPlan) -> str:
    """When the previous claim stopped being true.

    The new claim's own `valid_from`, not `now()`. The two must be the same
    instant or an as-at read between them finds either no valid claim or two,
    and both are wrong. Falls back to now only when a plan carries no
    `valid_from` at all, which no claim writer does.
    """
    from metis_mcp.ontology.labels import VALIDITY_LABELS

    for node in plan.nodes:
        if node.label in VALIDITY_LABELS:
            recorded = node.properties.get("valid_from")
            if recorded:
                return str(recorded)
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _count(result) -> int:
    """The `written` column, tolerating a driver stub that returns nothing.

    A real driver always returns a `Result`; `None` only comes from a recording
    fake in a test, and crashing on one would make the writer untestable without
    a container. Zero is the honest answer there — the stub did not claim to
    write anything.
    """
    if result is None:
        return 0
    for row in result:
        return int(row["written"])
    return 0


# ---------------------------------------------------------------------------
# Invalidation (bi-temporal; see ontology.labels.VALIDITY_LABELS)
# ---------------------------------------------------------------------------

INVALIDATE_CYPHER = """
UNWIND $ids AS wanted
MATCH (n {id: wanted})
WHERE (n.valid_to IS NULL OR n.valid_to = '')
SET n.valid_to = $valid_to
RETURN count(n) AS written
"""


@dataclass(frozen=True)
class Supersede:
    """One claim replacing an earlier revision of itself."""

    label: str
    logical_key: str
    previous_id: str
    new_id: str
    previous_revision: int

    @property
    def revision(self) -> int:
        return self.previous_revision + 1


@dataclass
class SupersessionPlan:
    """What a landing must close, and what revision each new claim carries."""

    supersedes: list[Supersede] = field(default_factory=list)
    # Claim ids appearing for the first time. Revision 1, nothing to close.
    first_seen: list[str] = field(default_factory=list)
    # Claim ids already present and unchanged. TR-6's no-op.
    unchanged: list[str] = field(default_factory=list)

    @property
    def revisions(self) -> dict[str, int]:
        """`{new claim id: revision}` for every claim in the plan."""
        out = {cid: 1 for cid in self.first_seen}
        out.update({s.new_id: s.revision for s in self.supersedes})
        return out

    @property
    def to_close(self) -> list[str]:
        return [s.previous_id for s in self.supersedes]


def plan_supersession(plan: LandingPlan, current: dict) -> SupersessionPlan:
    """Which claims in this plan replace an earlier revision. **Pure.**

    `current` maps a logical key to the currently-valid node already in the
    graph: `{logical_key: (node_id, revision)}`. The caller reads it; this
    decides what follows, so the decision is assertable with no database — the
    same split `plan`/`land` already uses.

    Three outcomes, and keeping them apart is the point:

      * **first seen** — nothing has this logical key. Revision 1, nothing to
        close, lands at `Quarantine` like any new node (S-4).
      * **unchanged** — the same logical key AND the same content digest. A
        re-land of identical content is a no-op (TR-6); closing a window here
        would move the instant a fact stopped being true to whenever somebody
        happened to re-run extraction.
      * **superseded** — the same logical key, a different digest. The claim
        changed. The previous node's window closes, the new node is a genuinely
        new node at `Quarantine`, and the old one keeps whatever lifecycle a
        human gave it, because I-19 retains the prior approval in history rather
        than retracting it.

    Note what does **not** appear here: a lifecycle mutation. Supersession is not
    a review decision (D-15) and does not disturb one. The new revision is
    unapproved because it is new, not because anything revoked it — which is the
    difference between a mechanism and a special case.
    """
    from metis_mcp.identity.keys import logical_key_of
    from metis_mcp.ontology.labels import VALIDITY_LABELS

    result = SupersessionPlan()
    for node in plan.nodes:
        if node.label not in VALIDITY_LABELS:
            continue
        new_id = node.properties.get("id", "")
        key = logical_key_of(new_id)
        if not key:
            continue
        existing = current.get(key)
        if existing is None:
            result.first_seen.append(new_id)
            continue
        previous_id, previous_revision = existing
        if previous_id == new_id:
            result.unchanged.append(new_id)
            continue
        result.supersedes.append(Supersede(
            label=node.label, logical_key=key, previous_id=previous_id,
            new_id=new_id, previous_revision=int(previous_revision or 1)))
    return result


def resolve_claim_edges(plan: LandingPlan, current: dict) -> list[str]:
    """Point edges at the claim revision that is current. **Pure.**

    An authored file cross-references a claim by its LOGICAL key -- a
    specification names `REQ-3`, not `REQ-3@6baff72b`, because the author cannot
    know which revision is live and should not have to. Where that claim is
    landed by the same plan the writer already substituted the minted id; where
    it was landed by another source, the bare key is all there is.

    Left alone, such an edge is the exact failure this codebase has shipped
    twice: it passes `validate_relationship` (the labels are legal), then
    `MERGE` matches no node and the edge count silently comes up short. `land`
    reports that as `unmatched`, which is a report nobody reads for an edge that
    was never going to match.

    Returns the ids it could not resolve, so the caller can say so rather than
    letting them fail quietly. An unresolved key is left exactly as written: a
    claim that genuinely does not exist yet must read as absent, not be pointed
    at something plausible.
    """
    from metis_mcp.identity.keys import CLAIM_SEPARATOR
    from metis_mcp.ontology.labels import VALIDITY_LABELS

    in_plan = {n.properties.get("id") for n in plan.nodes}
    unresolved: list[str] = []
    for index, edge in enumerate(plan.edges):
        if edge.to_label not in VALIDITY_LABELS:
            continue
        if edge.to_id in in_plan or CLAIM_SEPARATOR in edge.to_id:
            continue
        existing = current.get(edge.to_id)
        if existing is None:
            unresolved.append(edge.to_id)
            continue
        plan.edges[index] = replace(edge, to_id=existing[0])
    return unresolved


CURRENT_CLAIMS_CYPHER = """
UNWIND $keys AS wanted
MATCH (n)
WHERE any(l IN labels(n) WHERE l IN $labels)
  AND (n.valid_to IS NULL OR n.valid_to = '')
  AND (n.id = wanted OR n.id STARTS WITH wanted + $separator)
RETURN wanted AS logical_key, n.id AS id,
       coalesce(n.revision, 1) AS revision
ORDER BY n.valid_from DESC
"""


def current_claims(session, logical_keys) -> dict:
    """`{logical_key: (node_id, revision)}` for the claims still valid.

    Matches the bare key as well as the `key@digest` form, so a graph landed
    before claim ids existed is read rather than treated as empty — which would
    make every legacy requirement look new and land a duplicate beside it.

    Ordered by `valid_from` descending and first-wins, so if a graph somehow
    holds two open windows for one key the newer is treated as current rather
    than an arbitrary one. That state should not occur; picking silently at
    random when it does is how it would stay invisible.
    """
    from metis_mcp.identity.keys import CLAIM_SEPARATOR
    from metis_mcp.ontology.labels import VALIDITY_LABELS

    wanted = sorted({k for k in logical_keys if k})
    if not wanted:
        return {}
    out: dict[str, tuple[str, int]] = {}
    for row in session.run(CURRENT_CLAIMS_CYPHER, keys=wanted,
                           labels=list(VALIDITY_LABELS),
                           separator=CLAIM_SEPARATOR):
        out.setdefault(row["logical_key"], (row["id"], row["revision"]))
    return out


REOPEN_CYPHER = """
UNWIND $ids AS id
MATCH (n) WHERE n.id = id AND n.valid_to <> ''
SET n.valid_to = ''
RETURN count(n) AS written
"""


def _reopen(session, ids) -> int:
    """Clear `valid_to` on claims supersession has just made current.

    The complement of `invalidate`, and deliberately not exposed as a verb: the
    only legitimate caller is the supersession step, which knows which single
    node it has designated current. A general "reopen" command would be a way to
    undo an invalidation by accident, which is the thing `VALIDITY_FACTS` exists
    to prevent.

    Matches only nodes whose window is CLOSED, so it is a no-op for the ordinary
    case where the new revision was created a moment ago with `valid_to = ''`.
    """
    wanted = [i for i in (ids or []) if i]
    if not wanted:
        return 0
    return _count(session.run(REOPEN_CYPHER, ids=wanted))


def invalidate(session, ids, valid_to: str, actor: str = "") -> dict:
    """Close the validity window on facts that have stopped being true.

    **Nothing is deleted.** The node stays, its edges stay, and an as-at read
    still finds it — "what did we believe in March" is a question this graph
    should answer rather than one it should have forgotten. That is the whole
    difference between a validity window and a `DELETE`.

    **Not a lifecycle decision, and deliberately not routed through one.**
    Approving is a judgement about whether a claim is right; invalidating records
    that the world moved. A superseded criterion keeps whatever review state a
    human gave it, because retracting the approval would misrepresent what they
    decided.

    **Already-closed windows are left alone.** The `WHERE` clause means a second
    call is a no-op rather than a rewrite: re-invalidating would move the instant
    a fact stopped being true to whenever somebody happened to run this, which is
    the same class of error `FIRST_SEEN_FACTS` exists to prevent.

    Returns what was closed and what was not found, because "nothing matched"
    and "everything was already closed" are different answers and a single count
    cannot tell them apart.
    """
    wanted = sorted(set(ids))
    if not wanted:
        return {"closed": 0, "already_closed": 0, "missing": []}
    if not valid_to.strip():
        raise ValueError(
            "invalidation needs the instant the fact stopped being true; "
            "an empty `valid_to` is what 'still valid' means")

    present = {row["id"] for row in session.run(
        "UNWIND $ids AS wanted MATCH (n {id: wanted}) RETURN n.id AS id",
        ids=wanted)}
    closed = _count(session.run(INVALIDATE_CYPHER, ids=wanted, valid_to=valid_to))
    return {
        "closed": closed,
        "already_closed": len(present) - closed,
        "missing": sorted(set(wanted) - present),
        "actor": actor,
    }


# ---------------------------------------------------------------------------
# Backfilling validity onto nodes that predate it
# ---------------------------------------------------------------------------

BACKFILL_VALIDITY_CYPHER = """
MATCH (n)
WHERE any(l IN labels(n) WHERE l IN $labels) AND n.valid_from IS NULL
SET n.valid_from = $valid_from,
    n.valid_to = coalesce(n.valid_to, '')
RETURN count(n) AS written
"""


def backfill_validity(session, valid_from: str, labels=None) -> dict:
    """Give pre-validity nodes a window, so reads can stop tolerating their absence.

    **This exists so the `IS NULL` tolerance can be removed.** Reads used to
    accept a missing `valid_to` as "still valid", which kept an existing graph
    readable on the day validity shipped. That tolerance also means a node whose
    validity was never set is indistinguishable from one deliberately left open —
    so once every node carries a window, the reads can require one and the
    ambiguity goes.

    **`valid_from` is the caller's to choose, and it is a claim.** These facts
    were true before this ran; the honest value is when the data was believed
    from — a release date, the commit the model was extracted at — not the moment
    of the migration. There is no default for that reason.

    Idempotent: only nodes with no `valid_from` are touched, so running it twice
    does not move a window that was already set.
    """
    from metis_mcp.ontology.labels import VALIDITY_LABELS

    if not valid_from.strip():
        raise ValueError(
            "backfill needs the instant these facts were believed from; there is "
            "no sensible default, and 'now' would claim they became true at "
            "migration time")
    targets = list(labels or VALIDITY_LABELS)
    written = _count(session.run(BACKFILL_VALIDITY_CYPHER,
                                 labels=targets, valid_from=valid_from))
    remaining = session.run(
        "MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) "
        "AND n.valid_from IS NULL RETURN count(n) AS c",
        labels=targets).single()["c"]
    return {"written": written, "still_missing": remaining, "labels": targets}
