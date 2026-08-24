"""
Web and data scaffolds: a Page Object per page, a query per table (X-6e).

The counterpart to `recipe.py`, and it inherits one hard limit. **No pack can
recover a selector** — `model_sources/structure.py` exists and is authored for
exactly that reason, and its own header records that `js-ui`'s element selector
is "frequently NOT recoverable". So a Page Object is generatable precisely as far
as somebody has written the structure file, and no further.

That limit is stated in the output rather than worked around. An element with no
authored selector renders as a **marked stub**:

    def export(self):
        raise NotImplementedError(
            "no selector recovered for 'Export' — the page code never names "
            "it in a literal lookup (X-19: element_selector, refuted)")

A guessed `#export-button` would look usable, which is what makes it worse than
nothing (T-9d). The same rule the automation payload already applies to an
unrecoverable step.

**Methods chain because navigation is modelled.** A `Navigation` element carries
`navigates_to`, so the method returns the Page Object it leads to and scenarios
compose:

    RecordsListPage(driver).new_record().save()

For data, a `SELECT` is written from the catalogue's own columns. **Executing it
is not here**: nothing in this codebase opens a database connection, and doing so
against a real system is a capability decision rather than a rendering one.
"""
from __future__ import annotations

import keyword
import re

_NON_WORD = re.compile(r"[^0-9a-zA-Z]+")

NO_SELECTOR = "no selector recovered"


def _snake(text: str) -> str:
    out = _NON_WORD.sub("_", text or "").strip("_").lower() or "element"
    if out[0].isdigit():
        out = "_" + out
    return out + "_" if keyword.iskeyword(out) else out


def _pascal(text: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in _NON_WORD.split(text or "") if p) \
        or "Page"


def page_object(page: str, elements: list[dict]) -> str:
    """One page's controls as a class. `elements` is flat: id, kind, name,
    selector, on_event, navigates_to."""
    class_name = _pascal(page) + "Page"
    lines = [
        f"class {class_name}:",
        f'    """Generated for page {page!r}.',
        "",
        "    What is ON the page comes from the authored structure; how to REACH",
        "    it comes from the page code. Derived, never authored (T-9b): a",
        "    selector is extracted — `js-ui` reads `document.getElementById(...)`",
        "    — and an element the code never names in a literal lookup is a stub",
        "    rather than a guess (T-9d).",
        '    """',
        "",
        "    def __init__(self, driver):",
        "        self.driver = driver",
    ]

    located = [e for e in elements if e.get("selector")]
    if located:
        lines += ["", "    # Locators, verbatim from the page code."]
        for element in sorted(located, key=lambda e: e.get("name") or ""):
            lines.append(f"    {_snake(element.get('name'))}_locator = "
                         f"{element['selector']!r}")

    actionable = [e for e in elements
                  if e.get("kind") in ("Action", "Navigation")]
    for element in sorted(actionable, key=lambda e: e.get("name") or ""):
        name = _snake(element.get("name"))
        lines.append("")
        if not element.get("selector"):
            lines += [
                f"    def {name}(self):",
                f'        raise NotImplementedError(',
                f'            "{NO_SELECTOR} for {element.get("name")!r} — the '
                f'page code never names it in a literal lookup")',
            ]
            continue
        target = element.get("navigates_to")
        lines.append(f"    def {name}(self):")
        lines.append(f"        self.driver.click(self.{name}_locator)")
        if target:
            # Chainable because the structure says where this goes: a scenario
            # is a sequence of these, and the return type is what lets it be one.
            lines.append(f"        return {_pascal(target)}Page(self.driver)")
        else:
            lines.append("        return self")
    return "\n".join(lines) + "\n"


def select_query(table: str, columns: list[dict], *, schema: str = "",
                 where: tuple[str, ...] = ()) -> str:
    """A `SELECT` over one table, from the catalogue's own columns.

    Columns are named rather than `*`, because a test asserting on a result set
    should break when a column is removed rather than silently see one fewer.
    """
    qualified = f"{schema}.{table}" if schema else table
    names = [c["name"] for c in columns] or ["*"]
    sql = "SELECT " + ",\n       ".join(names) + f"\n  FROM {qualified}"
    if where:
        sql += "\n WHERE " + "\n   AND ".join(where)
    return sql + ";"


def query_scaffold(table: str, columns: list[dict], *, schema: str = "",
                   dialect: str = "") -> dict:
    """The query plus what a caller must supply to run it.

    Generation only. **Nothing here executes SQL**, and nothing in this codebase
    can: a connection to a real database is an external capability, not a
    rendering concern, and it is gated separately if it is built at all.
    """
    required = [c["name"] for c in columns
                if "NOT NULL" in (c.get("constraints") or ())]
    keys = [c["name"] for c in columns
            if "PRIMARY KEY" in (c.get("constraints") or ())]
    return {
        "schema": "metis.query-scaffold/1",
        "dialect": dialect or "unknown",
        "table": table,
        "sql": select_query(table, columns, schema=schema),
        "by_key": (select_query(table, columns, schema=schema,
                                where=tuple(f"{k} = :{k}" for k in keys))
                   if keys else None),
        "required_on_insert": required,
        "executes": False,
        "note": ("generated from the authored catalogue; Métis does not execute "
                 "it — no database connection exists in this codebase"),
    }
