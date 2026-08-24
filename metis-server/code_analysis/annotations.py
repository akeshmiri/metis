"""
What an annotation MEANS, as configuration (spec X-4, X-10b, §5.8).

**Métis defines the roles; a config says which annotations play them.** Before
this the packs carried hardcoded tables — twelve Spring annotations in
`jvm-structural`, six security ones, a handful of validation triggers — and were
blind to everything else. A codebase whose conventions differ was silently
under-modelled: `@ProjectSecured` on every endpoint recovered no security fact at
all, and nothing reported that anything had been missed.

**The role set is closed**, for the same reason the ontology is (D-2): a role
with no code behind it is a promise Métis cannot keep. An unknown role is
refused, naming the nine that exist.

Every role targets a label that already exists — this is about *reaching* the
fifty-six labels, not adding to them:

    entry_point       Endpoint, Transition.trigger
    route_prefix      Endpoint.path
    outcome_status    DeclaredOutcome, Transition.outcome_status
    exception_mapping ExceptionMapping -> a rejection Transition
    security          Transition.security, Check (authentication/authorization)
    validation        Check (validation), Field.constraints
    schema            description / required / allowed values on Class, Field, Parameter
    outbound_client   excluded — it declares calls MADE, not endpoints SERVED
    ignore            known and deliberately irrelevant

**Two layers, one schema.** `framework_config` ships the framework's own; a
project profile adds its own and wins on conflict. Métis ships framework
knowledge; a project ships its own.
"""
from __future__ import annotations

from dataclasses import dataclass

ENTRY_POINT = "entry_point"
ROUTE_PREFIX = "route_prefix"
OUTCOME_STATUS = "outcome_status"
EXCEPTION_MAPPING = "exception_mapping"
SECURITY = "security"
VALIDATION = "validation"
SCHEMA = "schema"
OUTBOUND_CLIENT = "outbound_client"
IGNORE = "ignore"

ROLES = (ENTRY_POINT, ROUTE_PREFIX, OUTCOME_STATUS, EXCEPTION_MAPPING,
         SECURITY, VALIDATION, SCHEMA, OUTBOUND_CLIENT, IGNORE)

# Security schemes, matching what `securityJson` already emits.
SCHEME_ROLE = "role"
SCHEME_EXPRESSION = "expression"
SCHEMES = (SCHEME_ROLE, SCHEME_EXPRESSION)

HTTP_VERBS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "ANY")


class AnnotationInvalid(ValueError):
    """Raised when an annotation declaration cannot be used as written."""


@dataclass(frozen=True)
class AnnotationSpec:
    """One annotation and the role it plays.

    `detail` is the role's one extra fact: an HTTP verb for `entry_point`, a
    scheme for `security`. Roles that need nothing carry "". A second free-form
    field would be the beginning of an open mapping, which is what lets a config
    write anything anywhere.
    """

    name: str
    role: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise AnnotationInvalid(
                f"@{self.name}: {self.role!r} is not a role Métis can honour. "
                f"Known: {', '.join(ROLES)}. A role with no code behind it is a "
                f"promise the extractor cannot keep, so it is refused rather "
                f"than accepted and ignored")
        if self.role == ENTRY_POINT and self.detail not in HTTP_VERBS:
            raise AnnotationInvalid(
                f"@{self.name} is an {ENTRY_POINT} and needs a verb "
                f"({', '.join(HTTP_VERBS)}); got {self.detail or 'none'}. "
                f"Without one the trigger has no method and every route on this "
                f"annotation collides")
        if self.role == SECURITY and self.detail not in SCHEMES:
            raise AnnotationInvalid(
                f"@{self.name} is a {SECURITY} annotation and needs a scheme "
                f"({', '.join(SCHEMES)}); got {self.detail or 'none'}. "
                f"`role` reads its arguments as role names, `expression` keeps "
                f"the expression verbatim — a reviewer weighs them differently")


def _spec(name: str, entry: dict) -> AnnotationSpec:
    if not isinstance(entry, dict):
        raise AnnotationInvalid(
            f"@{name}: expected an object with a 'role', got {type(entry).__name__}")
    role = entry.get("role", "")
    detail = str(entry.get("verb") or entry.get("scheme") or entry.get("detail") or "")
    return AnnotationSpec(name=name.lstrip("@"), role=role, detail=detail)


def load(data: dict | None, where: str = "") -> dict[str, AnnotationSpec]:
    """Validate a mapping of `annotation name -> declaration`."""
    out: dict[str, AnnotationSpec] = {}
    for name, entry in (data or {}).items():
        spec = _spec(name, entry)
        if spec.name in out:
            raise AnnotationInvalid(
                f"{where or 'annotations'}: @{spec.name} is declared twice; "
                f"which one wins would be an accident of file order")
        out[spec.name] = spec
    return out


def merge(framework: dict[str, AnnotationSpec],
          project: dict[str, AnnotationSpec]) -> dict[str, AnnotationSpec]:
    """Framework first, project on top.

    A project overriding a framework annotation is legitimate and worth allowing:
    a codebase that meta-annotates `@GetMapping` inside its own `@ProjectRead` needs
    to say so. It is not silent — `describe` prints which layer each came from.
    """
    merged = dict(framework)
    merged.update(project)
    return merged


def to_pack_table(specs: dict[str, AnnotationSpec]) -> str:
    """The table a query pack reads: `name<TAB>role<TAB>detail`, one per line.

    Deliberately not JSON. A pack is Scala run by Joern, and parsing JSON there
    means a library dependency inside the one place X-3 pins to an exact engine
    build. Three tab-separated fields need no parser and can be read by eye when
    an extraction surprises somebody.
    """
    lines = ["# annotation\trole\tdetail — generated; edit the config, not this"]
    for name in sorted(specs):
        spec = specs[name]
        lines.append(f"{spec.name}\t{spec.role}\t{spec.detail}")
    return "\n".join(lines) + "\n"


def describe(framework: dict[str, AnnotationSpec],
             project: dict[str, AnnotationSpec]) -> str:
    merged = merge(framework, project)
    by_role: dict[str, list[str]] = {}
    for name, spec in sorted(merged.items()):
        origin = "project" if name in project else "framework"
        by_role.setdefault(spec.role, []).append(
            f"@{name}" + (f" ({spec.detail})" if spec.detail else "") +
            ("" if origin == "framework" else " [project]"))
    lines = [f"Annotations ({len(merged)} declared)", ""]
    for role in ROLES:
        if role in by_role:
            lines.append(f"  {role}")
            lines.append(f"    {', '.join(by_role[role])}")
    unused = [r for r in ROLES if r not in by_role]
    if unused:
        lines += ["", f"  no annotation declared for: {', '.join(unused)}"]
    return "\n".join(lines)
