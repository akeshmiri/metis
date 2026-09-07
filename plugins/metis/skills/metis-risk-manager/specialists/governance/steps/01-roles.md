# 1 · Who owns, who acts, who may accept

Three roles that get collapsed into one, and each collapse causes a specific
failure.

| Role | Does | Collapsing it causes |
|---|---|---|
| **Risk owner** | watches the indicator, keeps the row current, calls the trigger | with no single owner, the risk is watched by nobody and discovered when it occurs |
| **Action owner** | executes one response action | with no action owner, the response is "the team's" and does not happen |
| **Acceptor** | takes the residual on behalf of the organisation | if this is the risk owner, the person with an interest in the risk being acceptable is the one who decides it is |

The risk owner and the action owner may be the same person. **The acceptor should
not be**, above the agreed threshold.

## Who may accept what

Set this against the bands, at planning time, and write it down:

| Band | Who may accept the residual |
|---|---|
| Low | the risk owner |
| Medium | the project manager |
| High | the sponsor |
| Very High | the sponsor, with the decision recorded outside the project |

The numbers are examples; the **shape** is the point — acceptance authority rises
with exposure, and nobody accepts their own risk above the line.

## Why this mirrors Métis's own gates

The same rule runs through the system: N-10 stops an author approving their own
requirement, G1 halts model approval for a human, G2 requires a literal from a
person in the same run. In each case the point is not ceremony — it is that a
decision has a name attached, so it can be reviewed by somebody who was not in
the room.

`describe_policy` shows what is enforced for those. Risk acceptance is the same
discipline applied to a file, and the `risk-review` workflow's
`risk-acceptance` gate is where it is recorded.
