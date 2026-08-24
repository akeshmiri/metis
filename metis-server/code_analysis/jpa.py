"""
What a repository actually asks the database (spec X-19a).

Measured on a real twelve-endpoint service before any of this was designed:

    @Query, EntityManager, JdbcTemplate, native SQL   0 files
    JpaRepository / CrudRepository                   12 files
    derived methods (findByUserIdAndQuestionIdIn)    11 files   <- the shape
    @Entity, @Table, @Column, @Id                     0 files   <- not in source

The last line is the constraint everything here bends around. The entities lived
in a dependency jar, so the code can only ever **propose** that `MfaTransaction`
is stored in `mfa_transaction` — Spring's default naming strategy — and only a
real catalogue can confirm it. A proposal is a `PendingJoin`, never an edge.

Four tiers, in the order they occur:

    derived   findByOwnerAndArchived  -> parsed to (property, operator) pairs,
                                         translated once the mapping resolves
    native    @Query(nativeQuery=true) -> verbatim; nothing to translate
    jpql      @Query("SELECT r FROM …") -> entity and field names through the
                                         same resolution
    opaque    anything else            -> a JpaQuery node carrying the raw form
                                         and a reason, for a person to complete

**An untranslated query is never presented as translated.** `confidence` is
`catalogue-confirmed` only where a real table and real columns matched, and a
guessed SQL string would be worse than the JPQL it came from — it looks runnable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

DERIVED = "derived"
NATIVE = "native"
JPQL = "jpql"
OPAQUE = "opaque"

PROPOSED = "naming-strategy-proposed"
CONFIRMED = "catalogue-confirmed"
UNRESOLVED = "unresolved"

# Spring Data's own vocabulary. Ordered longest-first so `GreaterThanEqual` is
# not matched as `GreaterThan`.
_OPERATORS = (
    ("IsGreaterThanEqual", ">="), ("GreaterThanEqual", ">="),
    ("IsLessThanEqual", "<="), ("LessThanEqual", "<="),
    ("IsGreaterThan", ">"), ("GreaterThan", ">"),
    ("IsLessThan", "<"), ("LessThan", "<"),
    ("IsNotNull", "IS NOT NULL"), ("NotNull", "IS NOT NULL"),
    ("IsNull", "IS NULL"), ("Null", "IS NULL"),
    ("ContainingIgnoreCase", "ILIKE"), ("Containing", "LIKE"),
    ("StartingWith", "LIKE"), ("EndingWith", "LIKE"),
    ("NotIn", "NOT IN"), ("In", "IN"),
    ("IsNot", "<>"), ("Not", "<>"),
    ("Between", "BETWEEN"), ("Like", "LIKE"),
    ("Is", "="), ("Equals", "="),
)

_SUBJECT = re.compile(r"^(find|read|get|query|search|stream|count|exists|delete|remove)"
                      r"(All|First\d*|Top\d*|Distinct)*By")
_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")


@dataclass(frozen=True)
class Predicate:
    property_path: str
    operator: str


@dataclass(frozen=True)
class RepositoryQuery:
    """One thing a repository asks, before any table is known."""

    method: str
    entity: str
    form: str
    predicates: tuple[Predicate, ...] = ()
    raw: str = ""
    reason: str = ""


def snake(name: str) -> str:
    """`MfaTransaction` -> `mfa_transaction`.

    Spring's `CamelCaseToUnderscoresNamingStrategy`, which is the default and
    therefore the only defensible guess. It is still a guess: this is what
    `basis` records so a reviewer can weigh it, and what the catalogue confirms
    or refutes.
    """
    return _CAMEL.sub("_", name).lower()


def parse_derived(method: str) -> tuple[Predicate, ...] | None:
    """`findByOwnerAndArchived` -> `[(owner, =), (archived, =)]`.

    Returns `None` when the name is not a derived query at all, which is a
    different answer from a derived query with no predicates (`findAll`).
    """
    match = _SUBJECT.match(method)
    if not match:
        return None
    rest = method[match.end():]
    if not rest:
        return ()
    out: list[Predicate] = []
    # `And`/`Or` both separate predicates. Which one it is changes the SQL and
    # not the tables, and this module's job stops at the tables — recording the
    # connective without honouring it would be a claim nothing checks.
    for part in re.split(r"And(?=[A-Z])|Or(?=[A-Z])", rest):
        if not part:
            continue
        operator = "="
        for suffix, sql in _OPERATORS:
            if part.endswith(suffix) and len(part) > len(suffix):
                operator = sql
                part = part[: -len(suffix)]
                break
        out.append(Predicate(property_path=part[:1].lower() + part[1:],
                             operator=operator))
    return tuple(out)


def classify(method: str, entity: str, *, annotation: str = "",
             native: bool = False) -> RepositoryQuery:
    """Which tier this method falls into, and why if it is opaque."""
    if annotation and native:
        return RepositoryQuery(method, entity, NATIVE, raw=annotation)
    if annotation:
        return RepositoryQuery(method, entity, JPQL, raw=annotation)

    predicates = parse_derived(method)
    if predicates is None:
        return RepositoryQuery(
            method, entity, OPAQUE,
            reason=f"{method!r} is neither a Spring Data derived name nor a "
                   f"@Query. What it asks the database is not recoverable from "
                   f"the signature, so it needs a person")
    return RepositoryQuery(method, entity, DERIVED, predicates=predicates)


@dataclass
class Translation:
    sql: str = ""
    table: str = ""
    columns: tuple[str, ...] = ()
    confidence: str = UNRESOLVED
    reason: str = ""


def translate(query: RepositoryQuery, *, table: str = "", columns=None,
              column_for=None) -> Translation:
    """A derived query as SQL, but only as far as the mapping is known.

    `table` and `columns` come from the catalogue. Absent, the result is
    `UNRESOLVED` with the reason — **not a guessed SQL string**, because a
    plausible statement is worse than none: it looks runnable and it is not.
    """
    if query.form == NATIVE:
        return Translation(sql=query.raw, table=table, confidence=CONFIRMED
                           if table else PROPOSED,
                           reason="native SQL, verbatim — nothing to translate")
    if query.form == OPAQUE:
        return Translation(confidence=UNRESOLVED, reason=query.reason)
    if not table:
        return Translation(
            confidence=UNRESOLVED,
            reason=f"no table confirmed for entity {query.entity!r}; the naming "
                   f"strategy proposes {snake(query.entity)!r} and no catalogue "
                   f"has been read")

    known = set(columns or ())
    resolved: list[str] = []
    missing: list[str] = []
    for predicate in query.predicates:
        name = (column_for or snake)(predicate.property_path)
        (resolved if not known or name in known else missing).append(name)
    if missing:
        return Translation(
            table=table, confidence=UNRESOLVED,
            reason=f"{table!r} declares no column for {', '.join(missing)} — the "
                   f"property was mapped by naming strategy and the catalogue "
                   f"refutes it")

    if query.form == JPQL:
        return Translation(
            table=table, columns=tuple(resolved), confidence=CONFIRMED,
            sql=f"-- from JPQL: {query.raw}\nSELECT * FROM {table};",
            reason="JPQL over one entity; the projection is not translated")

    where = " AND ".join(
        f"{c} {p.operator}" + ("" if p.operator.startswith("IS") else " ?")
        for c, p in zip(resolved, query.predicates))
    return Translation(
        sql=f"SELECT * FROM {table}" + (f" WHERE {where}" if where else "") + ";",
        table=table, columns=tuple(resolved), confidence=CONFIRMED,
        reason="derived method, every property matched a real column")
