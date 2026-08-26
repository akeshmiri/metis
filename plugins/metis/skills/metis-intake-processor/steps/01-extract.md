# Capture one stated source — all three follow this pattern

**Used by:** `jira`, `scale`, `confluence` — [intake-processor](../SKILL.md)

**R** — Read. Run `metis intake fetch --system <s> --key <k> --base-url <url>
--token-env <NAME> --out <dir>`. Pass the NAME of the variable holding the
token, never the token (PLT-005). Stop and report if the source is unreachable:
a 401 reported as "no such issue" is the failure this step exists to avoid.

**P** — Check. `fetch` prints a conformance verdict per document. A document
marked `WILL BE REFUSED` is not landed; report the reason. An advisory is not a
defect — "this text is not EARS-conformant, so it will land as a `Finding`" is
correct behaviour, and saying it here is the point.

**I** — Land. Run `metis intake land <dir>/<key>.uif.json`. Report the per-label
counts it prints, and the count of claimed acceptance criteria it **declined**
— that number is evidence the S-13 refusal happened, not a warning.

**Gate** — Everything lands at `Quarantine` (S-4). Nothing here approves
anything, and nothing downstream may generate from it until a human passes G1.

## Where the files go

`--out` is a directory the caller names, and the UIF file is an inspectable
intermediate rather than a deliverable. There is no default output location
under a home directory: this step previously wrote into a sibling project's tmp
tree, which is the coupling the port exists to remove.
