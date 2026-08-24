"""
What a change touches (v1's `metis_impact_analysis`, rebuilt against the v2 graph).

**The data was already here and nothing read it.** `raw_landing._anchor_props`
writes `anchor_file` / `anchor_line` / `anchor_commit` as three flat properties,
and its docstring says why: *"separate rather than a joined string because a
reviewer filters on file."* Nothing filtered on file. Measured on the live mfa
graph: 60 anchored nodes across 3 files — `DeclaredOutcome` 24, `Method` 17,
`Endpoint` 12, `ExceptionMapping` 5, `Check` 2.

So this is a read, not a new fact: given the files in a diff, which transitions
were recovered from them, which criteria validate those, and what would have to
be re-run.

**Three ways this tool could lie, and what stops each:**

- *Reporting "no impact" for a file it simply did not recognise.* A file that
  matched nothing is counted and named. "Nothing depends on this" and "I have
  never seen this file" are different answers and only one is safe before a
  merge.
- *Implying the graph is current.* It holds what the last extraction ingested. A
  file added since is invisible, and no amount of querying reveals that. The
  answer carries the commits it matched against so a reader can check.
- *Silently normalising a path.* Anchors hold whatever path the CPG recorded and
  a caller passes whatever `git diff --name-only` printed. Matching is on
  suffix, the matched form is reported, and nothing is rewritten.
"""
from __future__ import annotations

from metis_mcp.ontology.labels import label_expression

_TRANSITION = label_expression("Transition")

# One bounded walk outward from a transition over the evidence relationships.
#
# Every anchored label is reachable this way and the set is explicit rather than
# a wildcard, so what counts as "touched" is readable:
#
#   Transition -DERIVED_FROM->  Endpoint | DeclaredOutcome | ExceptionMapping
#              -CONSTRAINED_BY-> Check
#   Endpoint   -DECLARES->      DeclaredOutcome
#              -HANDLED_BY->    Method
#   DeclaredOutcome -GUARDED_BY-> Check
#
# Depth 3 is what the longest of those needs. A wildcard depth would drag in
# `CALLS` and report a transition as impacted because something it reaches
# eventually calls something in the file, which is a different and much weaker
# claim.
IMPACT_CYPHER = f"""
UNWIND $suffixes AS suffix
MATCH (n)
WHERE n.anchor_file IS NOT NULL AND n.anchor_file <> ''
  AND n.anchor_file ENDS WITH suffix
OPTIONAL MATCH (t:{_TRANSITION})
              -[:DERIVED_FROM|DECLARES|GUARDED_BY|CONSTRAINED_BY|HANDLED_BY*1..3]
              ->(n)
OPTIONAL MATCH (ac:AcceptanceCriterion)-[:VALIDATES]->(t)
RETURN suffix                AS supplied,
       n.anchor_file         AS matched_file,
       n.anchor_commit       AS commit,
       labels(n)[0]          AS evidence_label,
       n.anchor_line         AS line,
       t.id                  AS transition,
       t.trigger             AS trigger,
       t.outcome_status      AS outcome_status,
       t.lifecycle_state     AS lifecycle_state,
       collect(DISTINCT {{id: ac.id, provenance: ac.provenance}}) AS criteria
ORDER BY supplied, matched_file, transition
"""

HOW_TO_READ = (
    "coverage, never correctness (C-11): this says which recovered behaviour a "
    "change touches, and nothing about whether that behaviour works")


def _rows(cypher: str, **params):
    from metis_mcp.mbt.graph_session import session

    with session() as s:
        return [dict(r) for r in s.run(cypher, **params)]


def impact(changed_files: list[str]) -> dict:
    """Which recovered behaviour a set of changed files touches.

    `changed_files` is what `git diff --name-only` prints — repo-relative paths.
    Matching is on **suffix**, because an anchor holds whatever path the CPG
    recorded and the two rarely share a root.
    """
    supplied = [f.strip() for f in (changed_files or []) if f and f.strip()]
    if not supplied:
        return {"ok": False,
                "reason": "no changed_files given — pass what `git diff "
                          "--name-only` printed"}

    try:
        rows = _rows(IMPACT_CYPHER, suffixes=supplied)
    except Exception as e:                       # graph not configured, etc.
        from metis_mcp.mbt.graph_session import GraphNotConfigured
        if isinstance(e, GraphNotConfigured):
            return {"ok": False,
                    "reason": "no graph is configured — set METIS_NEO4J_URI / "
                              "METIS_NEO4J_USER and provide "
                              "METIS_NEO4J_PASSWORD in the environment"}
        raise

    transitions: dict[str, dict] = {}
    evidence: list[dict] = []
    matched_paths: set[str] = set()
    commits: set[str] = set()
    matched_inputs: set[str] = set()

    for row in rows:
        matched_inputs.add(row["supplied"])
        matched_paths.add(row["matched_file"])
        if row["commit"]:
            commits.add(row["commit"])
        evidence.append({"file": row["matched_file"], "line": row["line"],
                         "label": row["evidence_label"],
                         "supplied_as": row["supplied"]})
        tid = row["transition"]
        if not tid:
            continue
        entry = transitions.setdefault(tid, {
            "id": tid, "trigger": row["trigger"],
            "outcome_status": row["outcome_status"],
            "lifecycle_state": row["lifecycle_state"],
            "reached_via": set(), "criteria": [], "files": set()})
        entry["reached_via"].add(row["evidence_label"])
        entry["files"].add(row["matched_file"])
        for criterion in row["criteria"] or []:
            if criterion.get("id") and criterion not in entry["criteria"]:
                entry["criteria"].append(criterion)

    # **The files that matched nothing.** Named, not summarised away: "nothing
    # depends on this" and "I have never seen this file" are different answers.
    unmatched = sorted(set(supplied) - matched_inputs)

    impacted = sorted(transitions.values(), key=lambda t: t["id"])
    for entry in impacted:
        entry["reached_via"] = sorted(entry["reached_via"])
        entry["files"] = sorted(entry["files"])

    return {
        "ok": True,
        "files_supplied": len(supplied),
        "files_matched": len(matched_inputs),
        "files_unmatched": unmatched,
        "matched_paths": sorted(matched_paths),
        "impacted_transitions": impacted,
        "validating_criteria": sorted(
            {c["id"] for t in impacted for c in t["criteria"]}),
        "evidence_touched": len(evidence),
        # What the answer is current as of. The graph holds what the last
        # extraction ingested; a file added since is invisible here and no
        # query reveals that.
        "graph_commits": sorted(commits),
        "as_of": ("these are the commits the matched anchors were recorded at. "
                  "A file changed or added since the last extraction is not in "
                  "the graph and cannot appear above"),
        "matching": ("suffix match on anchor_file — anchors hold the path the "
                     "CPG recorded, which rarely shares a root with a "
                     "repo-relative diff path. Nothing was rewritten"),
        "means": HOW_TO_READ,
    }
