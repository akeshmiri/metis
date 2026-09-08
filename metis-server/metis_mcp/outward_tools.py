"""
The MCP surface for writes that leave Métis (T-20).

Thin on purpose. Every one of these calls a connector in `publishing/`, which
owns the credential, the installation switch, and the check-before-create. What
lives here is the tool signature and the shape of the answer — putting the gate
logic in two places is how the two versions of it diverge.

**These are gated twice and say so.** `METIS_MCP_WRITE` makes them reachable;
`METIS_ALLOW_EXTERNAL_WRITES=yes` makes them permitted. A caller that has the
first and not the second gets a refusal naming the second, rather than a stack
trace from inside an HTTP client.
"""
from __future__ import annotations

from metis_mcp import policy
from metis_mcp.review.roles import PROPOSE


def file_defect(project: str, summary: str, description: str,
                issue_type: str = "Bug", labels: str = "",
                evidence: str = "", expected: str = "", actual: str = "",
                phase: str = "", actor: str = "", role: str = "") -> dict:
    """File one tracker issue, after checking it is not already filed.

    **Métis does not observe the failure.** Execution results *are* ingested
    (§8.7, revised), but they land against the `TestCase` that ran and never
    reach this tool — the evidence here is whatever the caller passes. Filing is
    still not a claim that Métis watched a test fail.

    **`evidence` is classified before anything is filed.** Passing the runner's
    output adds a root-cause label and, more usefully, what the evidence points
    at: the system, the test, or the environment. Getting that wrong is what
    sends an outage to a product team and a product defect to nobody.

    No priority is set. How urgent a defect is depends on what it blocks and who
    is waiting, and neither is in a stack trace.

    Refuses if an unresolved issue with this summary exists, and refuses if the
    check could not run: two defects for one failure is what a retry produces
    when the second run could not see the first.
    """
    from metis_mcp.defects import classify as classifier
    from metis_mcp.publishing.tracker_write import JiraWriter

    grant = policy.authorise(PROPOSE, actor, role)
    found = tuple(l.strip() for l in labels.split(",") if l.strip())

    reading = None
    if evidence or expected or actual:
        reading = classifier.describe(evidence, expected=expected,
                                      actual=actual, phase=phase)
        # The label rides along only when a rule actually matched. Tagging an
        # issue `unclassified` adds a word and no information, and it would
        # become a label somebody filters on.
        if reading["classified"]:
            found = found + (reading["label"],)

    writer = JiraWriter(project)
    result = writer.create_issue(
        summary, description, issue_type=issue_type, labels=found)
    result["filed_by"] = grant.identity.name
    if reading:
        result["classification"] = reading
    result["means"] = ("a described defect. Métis did not observe this failure "
                       "— the evidence is the caller's")
    return result


def open_merge_request(project_id: str, source_branch: str, target_branch: str,
                       title: str, description: str = "",
                       blocking_findings: str = "",
                       actor: str = "", role: str = "") -> dict:
    """Open a merge request, refusing over blocking review findings.

    `blocking_findings` is a newline-separated list the caller supplies. It is
    passed in rather than computed here because deciding what counts as blocking
    is a review judgement, and this module writes.
    """
    from metis_mcp.publishing.tracker_write import GitLabWriter

    grant = policy.authorise(PROPOSE, actor, role)
    findings = tuple(f.strip() for f in blocking_findings.splitlines() if f.strip())
    result = GitLabWriter(project_id).create_merge_request(
        source_branch, target_branch, title, description,
        blocking_findings=findings)
    result["opened_by"] = grant.identity.name
    return result


def tracker_folder(name: str, parent_id: str = "",
                   actor: str = "", role: str = "") -> dict:
    """Create a folder in the test-management tool to organise cases into."""
    from metis_mcp.publishing.zephyr import ZephyrScaleTransport

    policy.authorise(PROPOSE, actor, role)
    return {"ok": True, "folder_id": ZephyrScaleTransport().create_folder(
        name, parent_id)}


def tracker_cycle_add(cycle_key: str, case_key: str,
                      status: str = "Not Executed",
                      actor: str = "", role: str = "") -> dict:
    """Add a published case to a test cycle.

    **The status is scheduling, not a result.** Métis ingests no execution
    outcome (§8.7); saying a case is in a cycle is not saying it ran.
    """
    from metis_mcp.publishing.zephyr import ZephyrScaleTransport

    policy.authorise(PROPOSE, actor, role)
    run_id = ZephyrScaleTransport().add_to_cycle(cycle_key, case_key, status)
    return {"ok": True, "run_id": run_id,
            "means": "scheduled, not executed (§8.7)"}
