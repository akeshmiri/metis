"""The consolidated risk report: everything known about a register, in one place.

**One rule shapes the whole module: there is no overall risk score.**

A single headline number is the thing a consolidated report is most often asked
for and the thing it must not produce. Three separate reasons, each sufficient:

- A 5x5 exposure is an *ordinal rank*. Summing or averaging ordinals produces a
  figure that is not a quantity of anything, and it moves when the scale is
  re-worded rather than when the project changes.
- The register holds **two kinds of claim**. An authored risk carries somebody's
  judgement about likelihood; a model-derived one carries Métis's observation
  that something is untested. Averaging across them lets a coverage gap read as
  a forecast, which is C-11 one domain over.
- A model-derived risk has **no probability at all** until a person sets one.
  Any total over the register either invents one or silently drops the row, and
  both are worse than reporting the two populations apart.

So every figure here is either a count, or a figure within one derivation. The
report says what it will not compute and why, because a reader who wants one
number will otherwise construct it themselves from the parts.

**What it reports that a check does not.** `register.validate` answers *is this
register self-consistent*. This answers *what does it say* — the distribution
across bands and categories, which risks carry the exposure, whether the ones
above the threshold actually have owners and responses, and which categories
nobody has looked at. The second question is the one a review meeting asks.

**Absence is reported, never omitted.** A category with no risks is the
interesting one — either genuinely safe or nobody looked — so empty categories
are named rather than dropped from a distribution built out of present keys. The
same applies to a High risk with no response and a risk with no owner: those are
counted and listed, because a report that only shows what exists cannot show the
gap.
"""
from metis_mcp.risk.exposure import BANDS, exposure
from metis_mcp.risk.rbs import CATEGORIES
from metis_mcp.risk.register import (
    AUTHORED,
    CLOSED,
    MODEL,
    OPEN,
    STATUSES,
    UNKNOWN,
    _canonical,
    summarise,
    validate,
)

# Bands at or above which a risk is expected to carry a response and an owner.
# Not a policy — the project sets its own thresholds at planning time — but a
# report has to pick something to count against, and it says which it used.
ATTENTION_BANDS = ("High", "Very High")

NO_SINGLE_SCORE = (
    "there is deliberately no overall risk score: a 5x5 exposure is an ordinal "
    "rank rather than a quantity, the register holds two kinds of claim that "
    "must not be averaged together, and a model-derived risk has no probability "
    "until a person sets one"
)


def _rows(register) -> list[dict]:
    return register.get("risks", []) if isinstance(register, dict) else list(register)


def _score_of(risk: dict) -> int | None:
    """The exposure, recomputed — never the stored `score`.

    A register's `score` column goes stale the moment somebody re-rates without
    recalculating, which `RISK-SCORE-STALE` reports and which this must not
    propagate into a distribution. Returns None when either rating is missing,
    which is the normal state of a model-derived risk.
    """
    try:
        return exposure(risk.get("probability"), risk.get("impact")).score
    except Exception:                                        # noqa: BLE001
        return None


def _band_of(risk: dict) -> str | None:
    score = _score_of(risk)
    if score is None:
        return None
    for low, high, name in BANDS:
        if low <= score <= high:
            return name
    return None


def consolidate(register) -> dict:
    """Everything the register says, with the two derivations kept apart."""
    rows = _rows(register)
    findings = validate(register)
    summary = summarise(register)

    by_band: dict[str, dict[str, int]] = {
        name: {AUTHORED: 0, MODEL: 0, UNKNOWN: 0} for _, _, name in BANDS}
    unrated: dict[str, int] = {AUTHORED: 0, MODEL: 0, UNKNOWN: 0}
    by_category = {name: 0 for name in CATEGORIES}
    uncategorised = 0

    needs_attention: list[dict] = []
    unowned: list[str] = []
    unresponded: list[str] = []

    for risk in rows:
        rid = str(risk.get("id") or risk.get("risk_id") or "?")
        derived = _canonical(risk.get("derived_from", AUTHORED),
                             (AUTHORED, MODEL)) or UNKNOWN

        band = _band_of(risk)
        if band is None:
            # Counted, not dropped. A register whose model-derived half is all
            # unrated looks empty in a band chart, and the reason is that nobody
            # has rated it — which is the finding, not a gap in the data.
            unrated[derived] += 1
        else:
            by_band[band][derived] += 1

        category = _canonical(risk.get("category", ""), tuple(CATEGORIES))
        if category:
            by_category[category] += 1
        else:
            uncategorised += 1

        status = _canonical(risk.get("status", OPEN), STATUSES) or OPEN
        if status == CLOSED:
            continue

        if band in ATTENTION_BANDS:
            needs_attention.append({
                "id": rid,
                "band": band,
                "score": _score_of(risk),
                "category": category or "(uncategorised)",
                "derived_from": derived,
                "description": str(risk.get("description", ""))[:120],
                "response": str(risk.get("response", "")) or None,
                "owner": str(risk.get("owner", "")) or None,
            })
            if not str(risk.get("response", "")).strip():
                unresponded.append(rid)
        if not str(risk.get("owner", "")).strip():
            unowned.append(rid)

    needs_attention.sort(key=lambda r: (-(r["score"] or 0), r["id"]))
    empty = sorted(name for name, count in by_category.items() if not count)

    return {
        "totals": summary,
        "by_band": by_band,
        "unrated": unrated,
        "by_category": by_category,
        "empty_categories": empty,
        "uncategorised": uncategorised,
        "needs_attention": needs_attention,
        "attention_bands": list(ATTENTION_BANDS),
        "without_owner": sorted(set(unowned)),
        "without_response": sorted(set(unresponded)),
        "findings": [f.describe() for f in findings],
        "errors": len([f for f in findings if f.severity == "error"]),
        "warnings": len([f for f in findings if f.severity == "warning"]),
        "no_single_score": NO_SINGLE_SCORE,
        "empty_means": (
            "a category with no risks is either genuinely safe or unexamined, "
            "and this cannot tell them apart — it is reported so somebody can"),
        "scores_recomputed": (
            "bands are recomputed from probability x impact, never read from a "
            "stored `score`, so a stale column cannot move the distribution"),
    }


def format_report(report: dict) -> str:
    """The consolidated report as text, for a CLI and for a review meeting."""
    totals = report["totals"]
    split = totals["by_derivation"]
    out: list[str] = []

    out.append(f"{totals['total']} risk(s) — {totals['open']} open, "
               f"{totals['closed']} closed")
    line = (f"  authored {split[AUTHORED]}, model-derived {split[MODEL]}")
    if split.get(UNKNOWN):
        line += f", unrecognised {split[UNKNOWN]}"
    out.append(line)
    if totals["mixed"]:
        out.append("  mixed register — the two are never totalled together")

    out.append("")
    out.append("Exposure")
    for _, _, name in BANDS:
        counts = report["by_band"][name]
        total = sum(counts.values())
        detail = f"authored {counts[AUTHORED]}, model {counts[MODEL]}"
        if counts.get(UNKNOWN):
            detail += f", unrecognised {counts[UNKNOWN]}"
        out.append(f"  {name:<10} {total:>3}   ({detail})")
    if sum(report["unrated"].values()):
        u = report["unrated"]
        out.append(f"  {'unrated':<10} {sum(u.values()):>3}   "
                   f"(authored {u[AUTHORED]}, model {u[MODEL]}) "
                   f"— no probability set")

    out.append("")
    out.append("By category")
    for name, count in sorted(report["by_category"].items()):
        if count:
            out.append(f"  {name:<14} {count}")
    if report["uncategorised"]:
        out.append(f"  {'(none)':<14} {report['uncategorised']}")
    if report["empty_categories"]:
        out.append(f"  nothing recorded under: "
                   f"{', '.join(report['empty_categories'])}")
        out.append("    (either safe or unexamined — this cannot tell you which)")

    if report["needs_attention"]:
        out.append("")
        out.append(f"Needs attention ({' / '.join(report['attention_bands'])}, open)")
        for row in report["needs_attention"]:
            flags = []
            if not row["owner"]:
                flags.append("NO OWNER")
            if not row["response"]:
                flags.append("NO RESPONSE")
            suffix = f"  [{', '.join(flags)}]" if flags else ""
            out.append(f"  {row['id']:<12} {row['band']:<10} "
                       f"{row['score']:>2}  {row['derived_from']:<9} "
                       f"{row['description'][:52]}{suffix}")

    if report["findings"]:
        out.append("")
        out.append(f"Coherence — {report['errors']} error(s), "
                   f"{report['warnings']} warning(s)")
        for finding in report["findings"]:
            out.append(f"  {finding}")

    out.append("")
    out.append("No overall score is computed.")
    out.append("  A 5x5 exposure is an ordinal rank, the register holds two kinds")
    out.append("  of claim, and a model-derived risk has no probability until a")
    out.append("  person sets one. Any single number would hide all three.")
    return "\n".join(out)
