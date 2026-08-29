"""
The data-requirements block, rendered the same way by every emitter.

**Why this exists.** `resolve_payload` joins an authored fixture value onto the
requirement whose condition it is keyed by, reports it as `supplied`, and both
emitters then dropped it: `metis generate --fixtures ...` produced output
byte-identical to `metis generate` without them. A person wrote a value, the
tool said it had been supplied, and no artefact contained it — the failure mode
this codebase hunts for, in the one feature whose whole purpose is to carry that
value across.

**Why a comment and not a bound parameter.** A fixture value is keyed by the
CONDITION it satisfies — `credentials_valid AND NOT account_locked` — and a
condition is not a field. Which parameter `alice / correct-horse` fills is not
derivable from the model, so emitting `.body(...)` from it would invent a
binding, which is the same fabrication as an invented selector one layer along
(X-6e). What is honest is to put the condition, the value a person supplied for
it, and the fact that a person supplied it, where whoever finishes the test will
read them.

**Why shared across emitters.** The runners differ in language, and the module
docstring beside this one is right that there is no shared template. This block
is the exception: both targets are `//`-comment languages and the content is
identical because it is payload, not code. Two copies would drift, and a data
requirement that appears in the Java and not the TypeScript is exactly the kind
of difference nobody notices.
"""
from __future__ import annotations

from metis_mcp.rendering.payload import UNRECOVERABLE


def _one_line(value) -> str:
    """A value that cannot escape its comment.

    A multi-line fixture value would put the rest of itself on lines that are no
    longer comments — valid-looking source that does not compile, or worse, does.
    """
    return " ".join(str(value).splitlines())


def lines(payload: dict, *, indent: str) -> list[str]:
    """The block, or nothing at all when the case states no data requirement."""
    note = (payload.get("data_note") or "").strip()
    requirements = payload.get("data_requirements") or ()
    if not requirements and not note:
        return []

    out: list[str] = []
    if note:
        # What distinguishes this case from its siblings over the same walk.
        # Without it a boundary-coverage run emits three near-identical tests
        # and nothing says which is the one below the limit.
        out.append(f"{indent}// why this case: {_one_line(note)}")
    if not requirements:
        return out

    supplied = sum(1 for r in requirements if "value" in r)
    out.append(f"{indent}// data requirements: {len(requirements)}, "
               f"{supplied} supplied by fixtures")
    for requirement in requirements:
        kind = requirement.get("kind") or "condition"
        steps = requirement.get("steps") or []
        where = f" (step{'s' if len(steps) != 1 else ''} "
        where += f"{', '.join(str(s) for s in steps)})" if steps else ""
        out.append(f"{indent}//   [{kind}]{where if steps else ''} "
                   f"{_one_line(requirement.get('condition', '?'))}")
        if "value" in requirement:
            # Named as authored, because the reader has to be able to tell it
            # from something the model recovered. That distinction is the whole
            # reason the join produces a separate document.
            out.append(f"{indent}//     value: {_one_line(requirement['value'])}"
                       f"   <- authored fixture, not recovered")
        else:
            out.append(f"{indent}//     TODO: no fixture supplies a value for "
                       f"this condition")
    return out


def guard_lines(step: dict, *, indent: str) -> list[str]:
    """The precondition, where it came from, and the order it is evaluated in.

    **Three facts the model held and no artefact carried.**

      * `guard_wording` — the condition in business language. It reached the
        prose objective and stopped there, so a machine consumer saw only the
        code's own expression (D-8: the raw guard is authoritative, this is a
        rendering of it, and both belong in front of a reader).
      * `guard_anchor` — `file:line@commit` for the condition itself. T-9a: a
        condition a reviewer cannot trace is one they take on trust, and the
        traceability stopped at the payload.
      * `guard_checks` — the ordered conditions. This is the one that changes
        what a tester does: if check 1 short-circuits, no fixture reaches check 3
        without satisfying check 1 first, so the order is a data requirement and
        not documentation. The expressions previously reached the payload only
        inside `target_key`, which is an identity string.

    Rendered together because they answer one question — what must be true, in
    what order, and says who.
    """
    guard = step.get("guard")
    checks = step.get("guard_checks") or ()
    anchor = step.get("anchor")
    wording = (step.get("guard_wording") or "").strip()
    if not (guard or checks):
        return []

    out: list[str] = []
    if guard:
        out.append(f"{indent}// precondition: {_one_line(guard)}")
    if wording and wording != guard:
        out.append(f"{indent}//   as stated: {_one_line(wording)}")
    if anchor and anchor != UNRECOVERABLE:
        out.append(f"{indent}//   recovered from: {_one_line(anchor)}")

    if len(checks) > 1:
        out.append(f"{indent}//   evaluated in order — a fixture reaching a later "
                   f"check must satisfy the earlier ones first:")
    for position, check in enumerate(checks, start=1):
        dimension = check.get("dimension_class") or ""
        suffix = f"   [{dimension}]" if dimension else ""
        out.append(f"{indent}//     {position}. {_one_line(check.get('expression', '?'))}{suffix}")
        check_anchor = check.get("anchor")
        if check_anchor and check_anchor != UNRECOVERABLE:
            out.append(f"{indent}//        {_one_line(check_anchor)}")
    return out
