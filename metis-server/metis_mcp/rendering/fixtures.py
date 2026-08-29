"""
Authored selectors and values, for the fields extraction cannot recover.

**Why this file exists at all.** `rendering/payload.py` marks what it does not
know rather than inventing it: a UI step carries `element: UNRECOVERABLE`
because `js-ui` refuses to guess a selector, and `data_requirements` carry a
*condition* — "length 3..40, required" — never a value (T-9c, X-6e). Those are
the right answers for a model recovered from code, and they are not enough to
drive a browser or an HTTP client. Something has to supply the missing half.

**It is authored, and that is the whole design.** The alternative is inferring a
selector from a variable name or a value from a type, which produces automation
that looks right and binds to the wrong element — the failure X-6e exists to
prevent, arriving one layer later. So this is a file a person writes, reviewed
like any other, and a field with no entry stays `UNRECOVERABLE` and is reported.

**Refused, never degraded** — the same stance as `framework_config.load`. A
malformed fixtures file is an error with a reason, not a silently empty one: a
generator that quietly found no selectors emits a script full of TODOs and looks
like a modelling problem.

Format (`metis.fixtures/1`):

    version: metis.fixtures/1
    selectors:
      exportButton: "[data-testid=export]"
    values:
      title: "Quarterly report"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

FIXTURES_VERSION = "metis.fixtures/1"


class FixturesInvalid(ValueError):
    """The file could not be read as fixtures. Shape, not content."""


@dataclass(frozen=True)
class Fixtures:
    """Selectors and values a person supplied, keyed by the name the model uses.

    Two flat maps rather than one: a selector binds an element and a value fills
    a field, and a generator that confused them would put a CSS selector into a
    request body. Keeping them apart makes that a lookup miss instead.
    """

    version: str = FIXTURES_VERSION
    selectors: dict[str, str] = field(default_factory=dict)
    values: dict[str, object] = field(default_factory=dict)
    source: str = ""

    def selector_for(self, element: str) -> str:
        return self.selectors.get(element, "")

    def value_for(self, name: str):
        return self.values.get(name)

    @property
    def is_empty(self) -> bool:
        return not self.selectors and not self.values


EMPTY = Fixtures(source="(none supplied)")


def _flat_map(raw, *, where: str) -> dict:
    """One level of `name: scalar`, or a refusal naming the offender.

    Nesting is rejected rather than flattened: a nested map is somebody
    expressing structure this format does not have, and guessing which leaf they
    meant is how a value ends up bound to the wrong field.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise FixturesInvalid(f"{where} must be a mapping of name to value, "
                              f"got {type(raw).__name__}")
    out = {}
    for key, value in raw.items():
        name = str(key).strip()
        if not name:
            raise FixturesInvalid(f"{where} has an entry with an empty name")
        if isinstance(value, (dict, list, tuple)):
            raise FixturesInvalid(
                f"{where}.{name} is {type(value).__name__}; this format holds one "
                f"level of name to scalar. Express structure in the model, not here")
        out[name] = value
    return out


def load(data: dict, *, source: str = "") -> Fixtures:
    """Validate and build. Rejects with a reason rather than degrading."""
    if not isinstance(data, dict):
        raise FixturesInvalid(
            f"fixtures must be a mapping, got {type(data).__name__}")

    version = data.get("version", FIXTURES_VERSION)
    if version != FIXTURES_VERSION:
        raise FixturesInvalid(
            f"unknown fixtures version {version!r}; expected {FIXTURES_VERSION}")

    selectors = {k: str(v) for k, v in
                 _flat_map(data.get("selectors"), where="selectors").items()}
    for name, selector in selectors.items():
        if not selector.strip():
            raise FixturesInvalid(
                f"selectors.{name} is empty. An empty selector is not 'no "
                f"selector' — it binds to nothing and fails at run time; leave "
                f"the entry out and the field stays reported as unrecovered")

    unknown = set(data) - {"version", "selectors", "values"}
    if unknown:
        raise FixturesInvalid(
            f"unknown key(s) {sorted(unknown)}; expected `version`, `selectors`, "
            f"`values`. A misspelled key would otherwise be silently ignored and "
            f"read as a fixture that did not apply")

    return Fixtures(version=version, selectors=selectors,
                    values=_flat_map(data.get("values"), where="values"),
                    source=source or "(inline)")


def load_file(path: str | Path) -> Fixtures:
    """Read a fixtures file. A missing path is an error, not an empty set.

    `--fixtures nowhere.yaml` meaning "no fixtures" is how a typo becomes a
    script full of TODOs that reads as a modelling gap.
    """
    p = Path(path)
    if not p.is_file():
        raise FixturesInvalid(f"{p} does not exist")
    text = p.read_text()
    try:
        if p.suffix in (".yaml", ".yml"):
            import yaml

            data = yaml.safe_load(text)
        else:
            import json

            data = json.loads(text)
    except Exception as e:                      # noqa: BLE001 — re-raised with the path
        raise FixturesInvalid(f"{p} is not valid {p.suffix.lstrip('.') or 'json'}: {e}") from e
    return load(data or {}, source=str(p))
