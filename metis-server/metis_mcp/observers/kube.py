"""
Read a live Kubernetes namespace (observe tier).

Ported from Atlas's `k8s-observer`. What crossed is the collection shape and the
one discipline that makes the evidence usable; what did not is Atlas's cluster
names, namespaces and workload list.

**The buffered window is the ported discipline.** Evidence is collected from a
fixed margin BEFORE the failure started and AFTER it ended — 20 seconds and 5
seconds — because the cause of a failure is almost never inside the window the
failure was noticed in. A reader given exactly the failing interval sees the
symptom and none of the run-up, concludes the wrong thing, and has no way to
know they were looking at a truncated picture.

**It reads. It never restarts, scales, deletes or applies.** Those would be the
`run` tier and they are deliberately not written here: an observer that could
also act is one `METIS_EXECUTE=observe` no longer describes.
"""
from __future__ import annotations

from metis_mcp.execution import authorise, record

# The margin, in seconds. Named constants rather than call arguments: a caller
# who narrows the window to the failing interval gets a picture that looks
# complete and is not, and that is exactly the mistake this exists to prevent.
BEFORE_SECONDS = 20
AFTER_SECONDS = 5


def collect(namespace: str, selector: str = "", *, since_seconds: int = 300,
            actor: str = "", context: str = "") -> dict:
    """Logs, events and restart counts for a namespace, with the margin applied.

    `since_seconds` is the failure window the caller cares about; the request
    actually issued is wider by `BEFORE_SECONDS`, and the response says so, so
    nobody reads the extra lines as noise or the window as exact.
    """
    contact = authorise("kubernetes", f"{context or 'current-context'}/{namespace}",
                        actor=actor)

    from kubernetes import client, config                # the `execute` extra

    config.load_kube_config(context=context or None)
    api = client.CoreV1Api()

    window = since_seconds + BEFORE_SECONDS
    pods = api.list_namespaced_pod(namespace, label_selector=selector or None)

    collected, unreadable = [], []
    for pod in pods.items:
        name = pod.metadata.name
        statuses = pod.status.container_statuses or []
        entry = {
            "pod": name,
            "phase": pod.status.phase,
            "restarts": sum(s.restart_count for s in statuses),
            "ready": all(s.ready for s in statuses) if statuses else False,
        }
        try:
            entry["logs"] = api.read_namespaced_pod_log(
                name, namespace, since_seconds=window, timestamps=True,
                tail_lines=500)
        except Exception as e:                                   # noqa: BLE001
            # Named, never dropped. A pod whose logs could not be read is a hole
            # in the evidence, and a collection that silently omits it presents
            # a partial picture as a complete one (F-10).
            unreadable.append({"pod": name, "reason": str(e)[:160]})
        collected.append(entry)

    events = [
        {"reason": e.reason, "message": e.message, "object": e.involved_object.name,
         "count": e.count, "type": e.type}
        for e in api.list_namespaced_event(namespace).items
        if e.type != "Normal"
    ]

    record(contact, f"read {len(collected)} pod(s)",
           {"unreadable": len(unreadable)})
    return {
        "ok": True,
        "namespace": namespace,
        "pods": collected,
        "events": events,
        # Never summarised away.
        "unreadable": unreadable,
        "window": {
            "requested_seconds": since_seconds,
            "collected_seconds": window,
            "margin_before": BEFORE_SECONDS,
            "margin_after": AFTER_SECONDS,
            "why": ("the cause is rarely inside the window the failure was "
                    "noticed in; a reader given the exact interval sees the "
                    "symptom and none of the run-up"),
        },
        "provenance": "observed_from_running_system",
        "means": ("what this namespace did, once. Not what the code says it "
                  "does, and not evidence a test passed (§8.7, C-11)"),
    }
