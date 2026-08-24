"""
Land a product's Spec Kit acceptance criteria into the graph.

**This exists because its predecessor did not.** The 66 criteria of the pilot
estate were loaded by a script under `/tmp` that no longer exists, so when the
graph was lost there was no way to rebuild the intent side at all -- the models
could be re-extracted from committed sources and the criteria could not. RD-9
says recovery is re-ingestion rather than migration, and that only works if every
ingestion path is committed.

**What it does and does not claim.** It writes `AcceptanceCriterion` nodes with
`provenance: code_derived` -- the weakest grade -- because the pilot estate's specs are
retro-documentation: their own `plan.md` says they document what was built, and
several criteria carry a `Code reference:` line. A criterion written from the
code and used to check that code can only report agreement (§4.1), so it lands as
documentation and stays there until a person edits or affirms it (S-19).

It does **not** create `VALIDATES` edges. A match between a criterion and a
transition is a judgement, held for human confirmation (F-7, X-18); minting them
here would manufacture the confirmed matches the reconciliation report counts.

Usage:
    METIS_NEO4J_PASSWORD=... python3 demo_data/land_spec_criteria.py <specs-dir>
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from metis_mcp.mbt.graph_session import session                    # noqa: E402
from metis_mcp.model_sources.spec_kit import read_specs            # noqa: E402
from metis_mcp.ontology import validate                            # noqa: E402
from metis_mcp.ontology.labels import (                            # noqa: E402
    CODE_DERIVED,
    HUMAN_CONFIRMED,
)

EPISODE_CONNECTOR = "spec-kit"


def episode_id_for(root: Path) -> str:
    """Content-derived (D-8), so re-running over unchanged specs is a no-op."""
    return "ep-spec-" + hashlib.sha256(str(root).encode()).hexdigest()[:16]


def plan(root: Path) -> tuple[dict, list[dict]]:
    """Build the Episode and criterion rows. Pure -- nothing is written."""
    features = read_specs(root)
    episode = {
        "id": episode_id_for(root),
        "name": f"spec-kit: {root.name}",
        "t_recorded": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_connector": EPISODE_CONNECTOR,
        "job_id": "land-spec-criteria",
        "evidence": f"root={root}",
        # N-10: the specs are the proposer, so a reviewer is a distinct identity.
        "proposed_by": EPISODE_CONNECTOR,
    }

    rows: list[dict] = []
    for feature in features:
        for criterion in feature.criteria:
            rows.append({
                "id": f"ac:{feature.name}:{criterion.id}",
                "source_episode_id": episode["id"],
                "name": criterion.title or criterion.id,
                "text": criterion.text,
                "revision": 1,
                "lifecycle_state": "Quarantine",
                # S-19. Retro-documentation cannot arrive as intent.
                "provenance": CODE_DERIVED,
                "is_behavioural": criterion.is_behavioural,
                "code_reference": criterion.code_reference,
                # The transition this criterion was generated from, where the
                # document says so. Carried onto the node so the VALIDATES edge
                # below is a fact read out of the source, not a match.
                "transition_id": criterion.transition_id,
                "edited_by_hand": criterion.edited_by_hand,
            })
    return episode, rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("specs_dir",
                        help="the Spec Kit `specs` directory (holding <feature>/spec.md)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.specs_dir)
    episode, rows = plan(root)

    # D-10: every write goes through the gate, and on Community that gate is the
    # only guarantee the required properties are there at all (D-8a).
    errors: list[str] = []
    for row in rows:
        outcome = validate("AcceptanceCriterion", row)
        if not outcome.valid:
            errors.extend(outcome.errors)
    if errors:
        print(f"REFUSED: {len(errors)} validation error(s) — nothing written")
        for e in errors[:5]:
            print(f"    {e}")
        return 1

    behavioural = sum(1 for r in rows if r["is_behavioural"])
    print(f"{len(rows)} criteria from {root} "
          f"({behavioural} behavioural, {len(rows) - behavioural} narrative)")
    if args.dry_run:
        print("  --dry-run: nothing was written")
        return 0

    with session() as s:
        s.run("MERGE (e:Episode {id:$id}) SET e += $props",
              id=episode["id"], props=episode)
        for row in rows:
            # `provenance` and `lifecycle_state` are HUMAN facts: a reviewer
            # promoting a criterion to `human_confirmed` is the one thing
            # re-reading the document cannot reproduce. They were in the
            # unconditional SET, so every re-run of this script silently demoted
            # every promotion back to `code_derived` — the same defect as
            # landing resetting approvals to Quarantine.
            human = {k: row[k] for k in ("provenance", "lifecycle_state") if k in row}
            machine = {k: v for k, v in row.items()
                       if k not in human and k not in ("edited_by_hand", "transition_id")}
            s.run("MERGE (a:AcceptanceCriterion {id:$id}) "
                  "ON CREATE SET a += $human "
                  "SET a += $machine",
                  id=row["id"], human=human, machine=machine)

        # **S-19's ladder, climbed by an edit.** A criterion is documentation
        # "until a person edits or affirms one", and a rewritten clause is that
        # edit — the fingerprint `specgen` stamped no longer matches the words
        # in the file.
        #
        # Promotion only, never demotion: `code_derived` may become
        # `human_confirmed`, and nothing here can move a grade back down. That
        # is why this is a separate statement rather than part of the `SET`
        # above, which is `ON CREATE` precisely so a re-land cannot demote.
        promoted = [r for r in rows if r.get("edited_by_hand")]
        for row in promoted:
            s.run("MATCH (a:AcceptanceCriterion {id:$id}) "
                  "WHERE coalesce(a.provenance,'') = $weakest "
                  "SET a.provenance = $confirmed",
                  id=row["id"], weakest=CODE_DERIVED, confirmed=HUMAN_CONFIRMED)
        if promoted:
            print(f"  {len(promoted)} criterion/criteria promoted to "
                  f"{HUMAN_CONFIRMED} — a person rewrote the wording a generator "
                  f"produced, which is what S-19 counts as intent")

        # The binding, where the document carried one. Confirmed by the source
        # rather than by a person, because nothing was judged: `specgen` wrote
        # the id and `spec_kit` read it back.
        bound = [r for r in rows if r.get("transition_id")]
        for row in bound:
            s.run("MATCH (a:AcceptanceCriterion {id:$ac}) "
                  "MATCH (t:Transition|ApiCall|UiAction {id:$tid}) "
                  "MERGE (a)-[:VALIDATES]->(t)",
                  ac=row["id"], tid=row["transition_id"])
        if bound:
            print(f"  {len(bound)} VALIDATES edge(s) from bindings the documents "
                  f"carried — read, not matched")
        unbound = len(rows) - len(bound)
        if unbound:
            print(f"  {unbound} criterion/criteria carry no binding — hand-written, "
                  f"so a match stays a judgement for a human (F-7, X-18)")
    print(f"  landed under episode {episode['id']}")
    untouched = len(rows) - sum(1 for r in rows if r.get("edited_by_hand"))
    print(f"  {untouched} of {len(rows)} at provenance={CODE_DERIVED} — documentation "
          f"until a person edits or affirms one (S-19)")
    # The two lines above already report what was and was not bound. This used
    # to assert unconditionally that NO edges were created, which is now false
    # the moment a generated spec is landed — a summary contradicting the run it
    # summarises, printed two lines under the opposite claim.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
