"""
Product risk — the thing being built, as distinct from the project building it.

**Two taxonomies, and the reference this family was built from has only one.**
A project risk is "the vendor may be late"; a product risk is "this endpoint's
authorisation is asserted by nothing". They are rated by different people
against different objectives, and `rbs.CATEGORIES` — Strategic, Financial,
Schedule, Procurement — has nowhere to put the second. ISO/IEC/IEEE 29119-2 and
ISTQB both treat product risk as the thing that drives testing; this module is
where Métis holds it.

**The split is PRISMA's, and Métis arrived at the same shape independently.**
Product RISk MAnagement scores a risk item on two groups of factors:

    technical  (likelihood)  complexity, degree of re-use, interrelations,
                             size, technology, team experience
    business   (impact)      business importance, financial or safety damage,
                             usage intensity, external visibility, cost of
                             rework, defect history

and its operative rule is that *likelihood factors go to technical experts and
impact factors go to business representatives*. That is `risk/inputs.py`'s
`GATHERED` / `ASKED` split, written down years earlier in a different vocabulary.
So the technical half is gathered here from the model Métis recovered, and the
business half stays asked — every one of those six is a statement about what the
organisation values, and no amount of static analysis produces one.

**Risk items are typed, because the taxonomy of risk-based testing types them.**
The RBT taxonomy (Felderer & Ramler) distinguishes generic risks, test cases,
runtime artifacts, functional artifacts, architectural artifacts and development
artifacts. Métis has a node for every one of those categories already, which is
why this maps rather than invents: a risk attaches to the thing it threatens, and
"which kind of thing" decides which factors can even be gathered.

**What this module refuses.** It produces no probability. The defect-prediction
literature supports the claim that a large, highly-coupled, heavily-branching
component is more defect-prone than a small isolated one, and that is a
*ranking* signal, not a failure rate. `technical_profile` returns the factors and
a band; converting a band into a probability is a person's act and
`specialists/requirement-risk/steps/02-ask.md` requires the converter to be
named. Nothing here writes a `probability` field, and `test_risk_product.py`
asserts it.

**Measured during code processing, not joined afterwards.** `jvm-structural`
emits McCabe complexity and size for every method it keeps; the mapper resolves
each endpoint's `handler_method_id` to its figure, synthesis carries it onto the
`Transition`, and this module reads it off the model.

That ordering is the whole point, and the alternative is what made it necessary:
a `Transition` reaches a `Class` only through `REQUIRES` and `EXPECTS`, which are
its **payload** types. The class that *implements* the handler is not reachable
once the model exists — `Transition -DERIVED_FROM-> Endpoint` exists and
`Endpoint -> Class` does not. So the figure either travels with the endpoint from
the moment it is measured, or it needs a reviewed ontology edge to get home.
Measuring once, where the handler is still identifiable, is cheaper and truer.

**`0` means not measured, and is reported as absence rather than banded.** A
source with no code behind it — an OpenAPI document, an authored model, a UI
surface with no JVM handler — has no complexity to state, and calling that
"simple" would rank the least-known behaviour in a service as its safest.

Pure: a `Model` and ids. No session, no graph, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass

from metis_mcp.risk.inputs import ASKED, Input

#: The RBT taxonomy's risk-item types, mapped onto the labels Métis actually
#: writes. The mapping is the point: a risk attaches to the thing it threatens,
#: and the kind of thing decides which factors are gatherable at all.
RISK_ITEM_TYPES: dict[str, tuple[str, ...]] = {
    "functional": ("Requirement", "Feature", "AcceptanceCriterion"),
    "architectural": ("Endpoint", "Page", "Class"),
    "behavioural": ("Transition", "ApiCall", "UiAction", "State"),
    "test": ("TestCase", "Scenario"),
    "development": ("Episode",),
}

#: Each factor is scored onto 1..5 before anything is added, which is PRISMA's
#: "weighted criteria" and is not optional. Summing the raw counts lets whichever
#: factor happens to have the largest natural range decide the band on its own --
#: measured here, `fan_in` did exactly that and rated an ordinary transition
#: "Very High" because six things pointed at its target.
#:
#: The thresholds are a **convention**, the same way `exposure.BANDS` is one, and
#: they are stated rather than tuned: a project that disagrees should change them
#: deliberately in one place.
THRESHOLDS: dict[str, tuple[int, ...]] = {
    # value >= threshold[i] scores i+1. First entry is always 0 → score 1.
    "branching": (0, 1, 2, 4, 6),
    "fan_in": (0, 2, 4, 7, 11),
    "fan_out": (0, 2, 4, 7, 11),
    # Steeper on purpose: M-17 is fail-closed, and a condition nobody can read
    # is worse than a complicated one somebody can.
    "unverifiable_guards": (0, 1, 1, 2, 2),
    # McCabe's own convention is the anchor: 1-10 is simple, 11-20 moderate,
    # 21-50 complex, 50+ untestable. Compressed onto 1..5 with the top band
    # starting where he put "high risk".
    "code_complexity": (0, 5, 11, 21, 51),
    "code_size": (0, 20, 50, 100, 200),
    # Repairs are steep at the low end on purpose: the interesting jump is from
    # "never fixed" to "fixed twice", not from twenty to thirty.
    "repairs": (0, 1, 2, 4, 8),
}

#: Up to six factors, each 1..5. The band is taken on the MEAN rather than the
#: sum, because the number of factors varies: a behaviour with no code behind it
#: is scored on four and one with a JVM handler on six, and a sum would rank the
#: measured one higher for being better known.
BANDS = ((1.0, 1.9, "Low"), (2.0, 2.9, "Medium"),
         (3.0, 3.9, "High"), (4.0, 5.0, "Very High"))

MEANS = (
    "a defect-proneness ranking, not a failure rate. It orders risk items by how "
    "much there is to get wrong, which is what the defect-prediction literature "
    "supports; it does not say any of them IS wrong. No probability is set here "
    "-- a person converts a band into a rating and is named when they do"
)


@dataclass(frozen=True)
class Factor:
    """One technical factor, its PRISMA name, and what its absence means."""

    name: str
    prisma: str
    why: str
    absent_means: str


#: The technical half. Each names the PRISMA factor it stands in for, so a
#: reader can see which of the six are covered and which are not yet.
TECHNICAL_FACTORS: tuple[Factor, ...] = (
    Factor("branching", "complexity",
           "how many distinct conditions decide what this does",
           "no guard was recovered, which is not the same as no branching"),
    Factor("fan_in", "interrelations",
           "how many other behaviours reach this one, so how far a break travels",
           "the model has no incoming edge — an isolated node or an unlinked one"),
    Factor("fan_out", "interrelations",
           "how many behaviours this one can reach",
           "no outgoing edge was recovered"),
    Factor("unverifiable_guards", "complexity",
           "conditions the checker could not parse, which are the ones a reader "
           "cannot confirm either (M-17)",
           "no guard here was unparseable, which is a real and good answer"),
    Factor("code_complexity", "complexity",
           "McCabe complexity of the handler, measured at extraction",
           "NOT MEASURED — this behaviour has no code behind it that the packs "
           "read, which is not the same as code that is simple"),
    Factor("code_size", "size",
           "source lines of the handler, from the same measurement",
           "NOT MEASURED — see `code_complexity`"),
    Factor("repairs", "defect history",
           "how often this handler's file has been repaired in a stated window "
           "— the strongest single predictor in the defect-prediction "
           "literature",
           "NO WINDOW — nobody asked for a repair count, which is not the same "
           "as a file that has never been fixed"),
)

#: The business half. Declared as `Input`s so they travel through the same
#: gathered/asked machinery as every other question, and so `absent_means` is
#: mandatory on each. All six are PRISMA's impact factors.
BUSINESS_FACTORS: tuple[Input, ...] = (
    Input("business_importance",
          "whether this is something the product is bought for",
          ASKED,
          question="If this behaviour were missing or wrong, would a customer "
                   "still buy the product?",
          absent_means="IMPACT IS UNRATED — no exposure can be computed, and a "
                       "technical band alone ranks by effort, not by what is at stake"),
    Input("damage",
          "the worst outcome a failure here produces — money, safety, or a breach",
          ASKED,
          question="If this fails in production, what is the worst thing that "
                   "happens — and to whom?",
          absent_means="the consequence is unstated, so severity is a guess"),
    Input("usage_intensity",
          "how often it runs, which decides how quickly a defect is met",
          ASKED,
          question="How often is this used — every request, once a day, or once "
                   "a quarter?",
          absent_means="frequency unknown; a rare path and a hot path are rated alike"),
    Input("external_visibility",
          "whether a failure is seen outside the team",
          ASKED,
          question="If this breaks, who notices first — us, or a customer?",
          absent_means="visibility unknown, and an internally-caught failure and a "
                       "public one are not the same risk"),
    Input("cost_of_rework",
          "what fixing it after release costs, which is not what fixing it now costs",
          ASKED, required=False,
          question="If this ships broken, what does putting it right cost — a "
                   "patch, a migration, or a customer conversation?",
          absent_means="rework cost unknown; the case for testing it now cannot be priced"),
    Input("defect_history",
          "failures a person knows about that the repository cannot show — "
          "production incidents, support escalations, a defect fixed in a branch "
          "nobody merged",
          ASKED, required=False,
          question="Has this area failed in ways the commit history would not "
                   "show — an incident, an escalation, a near miss?",
          # **Kept ASKED even though repairs are now gathered**, because they are
          # different claims and this module's whole shape says those are never
          # merged. `repairs` counts commits somebody wrote; this asks about
          # failures somebody LIVED, and a defect found in staging and fixed
          # before release leaves a commit while an outage may leave none.
          absent_means="no lived history offered. `repairs` counts what the "
                       "repository records, which is not the same as what went "
                       "wrong"),
)


def band_for(score: float) -> str:
    for low, high, band in BANDS:
        if low <= score <= high:
            return band
    raise ValueError(f"no band covers {score}")


def _rate(factor: str, value: int) -> int:
    """One raw count onto 1..5, against this factor's stated thresholds."""
    score = 1
    for i, threshold in enumerate(THRESHOLDS[factor]):
        if value >= threshold:
            score = i + 1
    return min(score, 5)


def _atoms(guard: str) -> int:
    from metis_mcp.mbt.techniques import _atoms as split

    return len(split(guard or ""))


def unverifiable_ids(model) -> frozenset[str]:
    """The transitions M-17 could not verify — the validator's own answer.

    Reused rather than re-derived. `mbt/validation.py` already decides this, is
    already tested, and is already fail-closed; a second notion of "unverifiable"
    living here would drift from it, and the two would disagree about the same
    guard without either being obviously wrong. `validation.py` says the same
    thing about `behavior_model`'s interval arithmetic: reimplementing it "would
    produce two subtly different notions of overlap".

    Computed once per model and passed in, because it walks every transition.
    """
    from metis_mcp.mbt.validation import validate

    ids: set[str] = set()
    for finding in validate(model).unverifiable:
        ids.update(finding.element_ids)
    return frozenset(ids)


def technical_profile(model, transition_id: str, unverifiable=None) -> dict:
    """The gathered half for one behaviour, with the factors kept visible.

    Returns the individual factors as well as the total, deliberately. A single
    band says *how much there is to get wrong* and hides *what* — and the answer
    changes the response: high branching is met with more test cases, high fan-in
    is met with a contract nobody may break.
    """
    transition = model.transitions.get(transition_id)
    if transition is None:
        raise KeyError(f"{transition_id} is not in {model.id}")

    if unverifiable is None:
        unverifiable = unverifiable_ids(model)

    siblings = model.outgoing(transition.source, generatable_only=False)
    observed = {
        "branching": _atoms(transition.guard),
        "fan_in": len(model.incoming(transition.target, generatable_only=False)),
        "fan_out": len(siblings),
        "unverifiable_guards": sum(1 for t in siblings if t.id in unverifiable),
    }
    # Measured at extraction. Absent (0) is carried as absence: it is left out of
    # `observed` and named in `not_measured`, so it neither inflates a band nor
    # reads as a simple handler.
    not_measured = []
    for name, value in (("code_complexity", getattr(transition, "complexity", 0)),
                        ("code_size", getattr(transition, "size", 0))):
        if value:
            observed[name] = value
        else:
            not_measured.append(name)

    # **Repairs are different: zero is a real answer, and absence is not.**
    # A file that was counted and never repaired scores 1; a file nobody counted
    # has no score at all. `repairs_window` is what separates them — it is empty
    # exactly when no window was asked for, which is why the count is never read
    # without it.
    window = getattr(transition, "repairs_window", "")
    if window:
        observed["repairs"] = getattr(transition, "repairs", 0)
    else:
        not_measured.append("repairs")

    rated = {name: _rate(name, value) for name, value in observed.items()}
    score = round(sum(rated.values()) / len(rated), 2) if rated else 1.0
    return {
        "transition_id": transition_id,
        # Both halves: the rating is what orders, the raw count is what a reader
        # disagrees with. Reporting only the rating hides the measurement.
        "observed": observed,
        "factors": rated,
        "score": score,
        "band": band_for(score),
        "covers": sorted({f.prisma for f in TECHNICAL_FACTORS
                          if f.name in observed}),
        # Factors this behaviour has no measurement for, named rather than
        # scored. An unmeasured factor contributes nothing to the band and is
        # never silently treated as its best value.
        "not_measured": not_measured,
        # Carried beside the count, never apart from it.
        "repairs_window": window,
        # Named so a reader sees which of PRISMA's six this cannot yet answer.
        "not_covered": ["degree of re-use", "technology", "team experience"],
        "means": MEANS,
    }


def business_inputs() -> tuple[Input, ...]:
    """The asked half. Never derived, and the reason is the whole split."""
    return BUSINESS_FACTORS


def item_type_for(label: str) -> str | None:
    """Which RBT risk-item category a Métis label belongs to."""
    for kind, labels in RISK_ITEM_TYPES.items():
        if label in labels:
            return kind
    return None
