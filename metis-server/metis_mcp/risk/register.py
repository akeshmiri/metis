"""
The risk register: its shape, and the incoherences a check can actually find.

**The register is a file, not a graph node** — the same arrangement the review
file and the knowledge file use, and for the same reason: it is reviewable before
any database exists, and it travels in the pull request beside the change it is
about. Whether `Risk` should also be a label is argued in
`docs/academy/PROPOSAL-risk-in-the-graph.md` and deliberately not decided by
writing one.

**What this validates is coherence, never judgement.** Whether a risk is real,
whether its probability is right, whether the response is wise -- none of that is
computable and none of it is attempted. What IS computable is whether the row
contradicts itself, and the register's worst failure mode is exactly that: a
`score` column that no longer equals `probability x impact` because somebody
re-rated the risk and did not recalculate. That row then sorts wrongly in every
report built from it, and looks entirely normal.

**`derived_from` is the field that keeps two kinds of claim apart, and it is
load-bearing.** A register here can hold both a probability a person asserted and
one derived from what Métis recovered -- an uncovered transition, behaviour
nothing validates. Those are different claims:

    authored   somebody judged this likely
    model      Métis observed this is untested

A model-derived risk is evidence about **what is untested**, never about what is
likely, and merging the two would let a coverage gap masquerade as a probability
estimate. That is C-11 one domain over: coverage is not correctness, and an
absence of tests is not a forecast. `summarise` therefore reports the split on
every figure rather than a single total, and refuses to average across it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from metis_mcp.risk.exposure import RiskInputRefused, exposure
from metis_mcp.risk.rbs import UnknownCategory, validate_category

# The two response sets. `Accept` and `Escalate` are in BOTH deliberately --
# they are the two moves that do not depend on which way the risk points.
THREAT_RESPONSES = ("Avoid", "Mitigate", "Transfer", "Accept", "Escalate")
OPPORTUNITY_RESPONSES = ("Exploit", "Enhance", "Share", "Accept", "Escalate")

THREAT, OPPORTUNITY = "threat", "opportunity"
POLARITIES = (THREAT, OPPORTUNITY)

OPEN, CLOSED = "Open", "Closed"
STATUSES = (OPEN, CLOSED)

AUTHORED, MODEL = "authored", "model"
DERIVATIONS = (AUTHORED, MODEL)
# Not a valid derivation — a summary bucket, so the split always sums to the
# total rather than dropping a row nobody recognised.
UNKNOWN = "unknown"

ERROR, WARNING = "error", "warning"


@dataclass(frozen=True)
class Finding:
    """One incoherence, with the fix. Shaped like `ac_quality.Finding`."""

    risk_id: str
    rule: str
    severity: str
    detail: str
    suggestion: str

    def describe(self) -> str:
        return (f"[{self.severity}] {self.risk_id} {self.rule}: {self.detail} "
                f"-> {self.suggestion}")


@dataclass
class Register:
    risks: list = field(default_factory=list)


def _finding(risk_id, rule, severity, detail, suggestion) -> Finding:
    return Finding(risk_id=str(risk_id or "?"), rule=rule, severity=severity,
                   detail=detail, suggestion=suggestion)


def _canonical(value, allowed: tuple[str, ...]) -> str:
    """The canonical spelling of `value` in `allowed`, matched case-insensitively.

    Every vocabulary in this module folds case, because none of them draws a
    meaningful distinction between `open` and `Open`. Flagging that as an error
    is worse than useless: it fills the finding list with noise and buries the
    one finding that matters — a score that no longer equals probability x
    impact. Returns "" when there is no match, so the caller still reports the
    genuinely unknown value.
    """
    wanted = str(value or "").strip().casefold()
    for candidate in allowed:
        if candidate.casefold() == wanted:
            return candidate
    return ""


def validate_risk(risk: dict) -> list[Finding]:
    """Everything wrong with one row that does not require judgement."""
    found: list[Finding] = []
    rid = risk.get("id") or risk.get("risk_id") or "?"

    for required in ("description", "category", "owner"):
        if not str(risk.get(required, "")).strip():
            found.append(_finding(
                rid, f"RISK-NO-{required.upper()}", ERROR,
                f"no {required}",
                "a risk nobody owns is a risk nobody works"
                if required == "owner" else f"state the {required}"))

    category = risk.get("category")
    if category:
        try:
            validate_category(category)
        except UnknownCategory as e:
            found.append(_finding(rid, "RISK-CATEGORY", ERROR, str(e),
                                  "use a category from the RBS"))

    polarity = str(risk.get("polarity", THREAT)).lower()
    if polarity not in POLARITIES:
        found.append(_finding(
            rid, "RISK-POLARITY", ERROR,
            f"polarity {polarity!r} is neither {THREAT} nor {OPPORTUNITY}",
            "a risk points one way or the other; the response sets differ"))
        polarity = THREAT

    # **The one that matters most.** A stale score sorts every report wrongly
    # and looks completely normal doing it.
    probability, impact = risk.get("probability"), risk.get("impact")
    if probability is not None and impact is not None:
        try:
            computed = exposure(probability, impact)
        except RiskInputRefused as e:
            found.append(_finding(rid, "RISK-SCALE", ERROR, str(e),
                                  "probability and impact are 1..5 ordinals"))
        else:
            stated = risk.get("score")
            if stated is not None and int(stated) != computed.score:
                found.append(_finding(
                    rid, "RISK-SCORE-STALE", ERROR,
                    f"score is {stated} and probability x impact is "
                    f"{computed.score}",
                    "recalculate, or say which of the three is wrong — a stale "
                    "score sorts this risk wrongly in every report and looks "
                    "normal doing it"))

    response = _canonical(risk.get("response", ""),
                          THREAT_RESPONSES + OPPORTUNITY_RESPONSES)
    if response:
        allowed = (THREAT_RESPONSES if polarity == THREAT
                   else OPPORTUNITY_RESPONSES)
        if response not in allowed:
            other = (OPPORTUNITY_RESPONSES if polarity == THREAT
                     else THREAT_RESPONSES)
            crossed = (f" {response!r} is a {OPPORTUNITY if polarity == THREAT else THREAT} "
                       f"strategy." if response in other else "")
            article = "an" if polarity == OPPORTUNITY else "a"
            found.append(_finding(
                rid, "RISK-RESPONSE-POLARITY", ERROR,
                f"{response!r} is not {article} {polarity} response.{crossed}",
                f"one of: {', '.join(allowed)}"))

    status = _canonical(risk.get("status", OPEN), STATUSES) or \
        str(risk.get("status", OPEN))
    if status not in STATUSES:
        found.append(_finding(rid, "RISK-STATUS", ERROR,
                              f"status {status!r} is not one of {STATUSES}",
                              "a risk is Open or Closed"))

    derived = str(risk.get("derived_from", AUTHORED))
    if derived not in DERIVATIONS:
        found.append(_finding(
            rid, "RISK-DERIVATION", ERROR,
            f"derived_from {derived!r} is not one of {DERIVATIONS}",
            "a probability somebody judged and one Métis observed are "
            "different claims and must stay distinguishable"))
    elif derived == MODEL and not str(risk.get("derived_by", "")).strip():
        found.append(_finding(
            rid, "RISK-DERIVATION-SOURCE", WARNING,
            "derived_from is `model` and nothing names what produced it",
            "name the tool — a model-derived figure whose source is unstated "
            "cannot be re-checked when the model moves"))

    return found


def validate(register) -> list[Finding]:
    """Every row, plus the one thing only the whole file can be wrong about."""
    risks = register.get("risks", []) if isinstance(register, dict) else list(register)
    found: list[Finding] = []
    for risk in risks:
        found.extend(validate_risk(risk))

    seen: dict[str, int] = {}
    for risk in risks:
        rid = str(risk.get("id") or risk.get("risk_id") or "")
        if rid:
            seen[rid] = seen.get(rid, 0) + 1
    for rid, count in sorted(seen.items()):
        if count > 1:
            found.append(_finding(
                rid, "RISK-DUPLICATE-ID", ERROR,
                f"{count} rows share this id",
                "an id that names two rows makes every reference ambiguous"))
    return found


def summarise(register) -> dict:
    """The counts, **split by derivation and never averaged across it**.

    A single "average score" over a register holding both kinds of claim is the
    figure this whole module exists to prevent: it would blend somebody's
    judgement about likelihood with Métis's observation that something is
    untested, and present the result as one number.
    """
    risks = register.get("risks", []) if isinstance(register, dict) else list(register)

    # `unknown` exists so the three buckets always sum to `total`. Without it a
    # row whose `derived_from` is neither value was counted in neither bucket and
    # vanished from the split — silently, in the one figure this module exists to
    # keep honest. `validate` reports the bad value as an error; the summary must
    # not quietly disagree with its own total in the meantime.
    by_derivation = {AUTHORED: 0, MODEL: 0, UNKNOWN: 0}
    open_count = closed_count = 0
    for risk in risks:
        derived = _canonical(risk.get("derived_from", AUTHORED), DERIVATIONS)
        by_derivation[derived or UNKNOWN] += 1
        # Case-folded like every other vocabulary here: `validate_risk` accepts
        # `closed`, and a summary that counted it as open would contradict the
        # validation of the same file.
        if _canonical(risk.get("status", OPEN), STATUSES) == CLOSED:
            closed_count += 1
        else:
            open_count += 1

    mixed = by_derivation[AUTHORED] > 0 and by_derivation[MODEL] > 0
    return {
        "total": len(risks),
        "open": open_count,
        "closed": closed_count,
        "by_derivation": dict(by_derivation),
        "mixed": mixed,
        "means": (
            "this register mixes claims a person judged with claims Métis "
            "observed. They are reported apart and must not be averaged: a "
            "model-derived risk says something is UNTESTED, not that it is "
            "LIKELY (C-11)" if mixed else
            "every risk here has the same derivation, so the counts carry one "
            "kind of claim"),
    }
