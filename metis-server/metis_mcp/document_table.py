"""Editable generated tables: the machinery a regenerated document shares.

**The rule, borrowed from SP-1** (`specgen/specification.py`) and first written
down in `risk/document.py`: the structure is regenerated every run, the
judgement is owned by whoever wrote it, and regeneration never overwrites the
second. Without that the second run silently deletes every decision anybody
recorded -- and it looks like a successful regeneration while doing it.

**Why this is its own module.** The risk assessment and the test design are two
documents with different tables, different columns and the same three problems:
a cell that must survive a pipe, a table that must be found among several in one
file, and a merge that must keep a hand-edited column and a hand-added row. That
was ~120 lines inside `risk/document.py`, and copying it into a second family is
how the two would start disagreeing about what `—` means. One implementation,
two callers, and `test_risk.py` is the regression guard on the extraction.

**What stays with the caller.** Everything domain-shaped: which columns a person
owns, what a carried-over row means, and what the document says about itself.
This module knows about cells, headings and ids. It does not know what a risk or
a design condition is, and a function here that did would be the beginning of a
third place to state it.

**Scoped section reads, always.** A generated document holds several
pipe-delimited tables, and parsing every one of them as the table you want is a
real defect this has already produced: reading the whole file for risk rows
flagged the three-column *gathered facts* table as six malformed risks, so a
correct regeneration printed a warning about things that were never risks. A
warning that cries wolf is one people learn to ignore, which then hides the case
it exists for. So every read here takes the heading it lives under and the
heading that ends it.
"""
from __future__ import annotations

import re

#: How every table here writes "not set". A cell is never empty: an empty cell
#: and a missing column look identical in rendered Markdown, and only one of
#: them is a value somebody has to supply.
NOT_SET = "—"

#: A table row: an id in the first column, everything else read by position.
ROW = re.compile(r"^\|\s*(?P<id>[A-Za-z0-9_.:@+-]+)\s*\|(?P<rest>.*)\|\s*$")

#: A two-column `| name | value |` row, for the pair tables (answers on record).
PAIR = re.compile(r"^\|(?P<name>[^|]+)\|(?P<value>[^|]*)\|\s*$")

#: Ids that are the table's own furniture rather than a row.
FURNITURE = ("ID", "---", "—", "")


def cell(value) -> str:
    """One table cell: never empty, never a pipe that would break the row."""
    text = "" if value is None else str(value)
    text = text.replace("|", "\\|").replace("\n", " ").strip()
    return text or NOT_SET


def uncell(text: str):
    """A cell back to a value. `NOT_SET` is how these files write 'not set'."""
    stripped = text.strip().replace("\\|", "|")
    return None if stripped in ("", NOT_SET) else stripped


def header(columns: tuple[str, ...]) -> tuple[str, str]:
    """The header line and the rule beneath it, for a table of `columns`.

    Generated rather than written out, so a column added to a registry cannot
    leave a header naming one fewer thing than the rows below it -- which
    renders as a table Markdown silently truncates.
    """
    return ("| " + " | ".join(columns) + " |",
            "|" + "---|" * len(columns))


def row(values) -> str:
    """One rendered row. Every value goes through `cell`."""
    return "| " + " | ".join(cell(v) for v in values) + " |"


def section(text: str, heading: str, ends: tuple[str, ...] = ()) -> list[str]:
    """Only the lines under `heading`, stopping at any of `ends`.

    An absent heading returns nothing rather than raising: a document a person
    has edited down is a document to read what is left of, not one to refuse.
    """
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines)
                     if line.strip() == heading)
    except StopIteration:
        return []
    rest = lines[start + 1:]
    for i, line in enumerate(rest):
        if line.strip() in ends:
            return rest[:i]
    return rest


def parse_rows(text: str, *, heading: str, ends: tuple[str, ...],
               columns: tuple[str, ...]) -> dict[str, dict]:
    """The rows of one table, keyed by id, read by position.

    A row that has lost its shape is skipped and named by `row_problems`, never
    silently dropped -- a discarded edit is the same defect as an overwritten
    one, and the caller is expected to report the difference.
    """
    rows: dict[str, dict] = {}
    for line in section(text, heading, ends):
        match = ROW.match(line.strip())
        if not match:
            continue
        identifier = match.group("id").strip()
        if identifier in FURNITURE:
            continue
        cells = match.group("rest").split("|")
        if len(cells) < len(columns):
            continue
        rows[identifier] = {"id": identifier,
                            **{name: uncell(cells[i])
                               for i, name in enumerate(columns)}}
    return rows


def row_problems(text: str, *, heading: str, ends: tuple[str, ...],
                 columns: tuple[str, ...]) -> list[str]:
    """Ids of rows inside the table that could not be read."""
    problems: list[str] = []
    for line in section(text, heading, ends):
        match = ROW.match(line.strip())
        if not match:
            continue
        identifier = match.group("id").strip()
        if identifier in FURNITURE:
            continue
        if len(match.group("rest").split("|")) < len(columns):
            problems.append(identifier)
    return problems


def parse_pairs(text: str, *, heading: str, ends: tuple[str, ...],
                furniture: tuple[str, ...] = ()) -> dict[str, str]:
    """A two-column `| name | value |` table, as a mapping.

    Values are read as text, deliberately. Nothing here coerces `high` into a
    rating: converting an answer into a number is a person's judgement, and the
    skills that use these documents require the converter to be named.
    """
    skip = set(FURNITURE) | set(furniture)
    pairs: dict[str, str] = {}
    for line in section(text, heading, ends):
        match = PAIR.match(line.strip())
        if not match:
            continue
        name = match.group("name").strip()
        if name in skip:
            continue
        value = uncell(match.group("value"))
        if value is not None:
            pairs[name] = value
    return pairs


def merge_rows(generated: list[dict], previous: dict[str, dict], *,
               human_columns: tuple[str, ...],
               id_key: str = "id") -> tuple[list[dict], list[dict]]:
    """`generated` with the human columns restored, and what was left over.

    Returns `(merged, carried)`. `merged` is this run's rows with every column a
    person owns taken from the file that was already there. `carried` is every
    row in the file this run did not produce -- somebody's hand-added row, or a
    row for a fact that is no longer true.

    **Both are kept, and deciding between them is not Métis's call.** A row a
    person added is the thing an editable document exists for; a row whose fact
    has gone is evidence of a change somebody may want to see. The caller
    decorates `carried` with whatever its domain says about provenance.
    """
    remaining = dict(previous)
    merged: list[dict] = []
    for item in generated:
        prior = remaining.pop(str(item.get(id_key)), None)
        if not prior:
            merged.append(item)
            continue
        kept = dict(item)
        for column in human_columns:
            value = prior.get(column)
            if value is not None:
                kept[column] = value
        merged.append(kept)
    return merged, list(remaining.values())
