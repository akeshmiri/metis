"""
Hybrid retrieval: keyword, semantic, and the fusion of the two.

**What this module does and does not add.** Neo4j performs both searches — Lucene
for keywords, a vector index for similarity — so ranking, tokenisation, stemming
and nearest-neighbour lookup all cost nothing beyond the database that was
already required. The single thing Python must supply is the query VECTOR, and
that is the only place a model enters. It lives behind `EmbeddingProvider` and a
default install never loads one.

**Why fusion is not a model.** Reciprocal Rank Fusion merges two ranked lists by
position rather than by score, so it needs no training, no reranker, and no
calibration between two scoring schemes that are not comparable — a Lucene score
of 0.5 and a cosine similarity of 0.5 mean nothing to each other, and averaging
them is a category error dressed as arithmetic. RRF is deterministic: the same
two lists always fuse to the same order.

**The failure this module refuses to have.** An embedding is meaningless outside
the model that produced it. Query with a different model than wrote the vectors
and every result is confidently wrong, with no error and no signal — the exact
shape of the Joern 2.x/4.x break that X-3 exists to prevent. So a vector carries
the model that wrote it, and a query whose model disagrees is refused rather than
answered.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

# The rank-fusion constant from Cormack et al. Larger values flatten the
# advantage of a top-1 hit; 60 is the published default and is kept rather than
# tuned, because tuning it against one corpus is how a retrieval system becomes
# accidentally specific to its test data.
RRF_K = 60


def fold(text: str) -> str:
    """ASCII-folded text, for the search copy stored beside the original.

    **Why a second copy rather than a different analyzer.** Neo4j offers
    `english`, which stems but does not fold accents, and `standard-folding`,
    which folds but does not stem. Measured on the academy: with `english`,
    searching `Metis` returned NOTHING for a corpus about Métis — the product's
    own name, unfindable from an English keyboard. With `standard-folding`,
    `locks` stopped matching `locking`, which is half the reason to want full
    text at all.

    Indexing both forms gets both properties, because the analyzer applies to
    every property in the index: the original keeps its accents and its stemming,
    and this copy is what an unaccented query matches. The cost is storing the
    searchable text twice, which is the honest price of Neo4j not shipping an
    analyzer that does both.

    NFKD then dropping combining marks — the standard decomposition. `Métis`
    becomes `Metis`; text with no accents is returned unchanged, so the copy is
    redundant for most content and free to compute.
    """
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def split_identifiers(text: str) -> str:
    """`valid_to` also contributes `valid` and `to`.

    Lucene's tokenizer does not split on underscores, so a snake_case identifier
    stays one token and is invisible to a natural-language query. Measured on the
    academy: the lesson about validity mentions `valid_from` / `valid_to` eight
    times, and searching `valid` reached none of them — a reader asking about
    validity in ordinary words missed the lesson that is entirely about it.

    The identifier is KEPT alongside its parts rather than replaced, because
    somebody searching `valid_to` exactly should still find it — and would be
    surprised to be told a property they can see in the schema does not exist.
    """
    import re

    extra = []
    for token in re.findall(r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+", text):
        extra.extend(token.split("_"))
    return " ".join(extra)


def search_text_for(*values: str) -> str:
    """The folded copy for one node, from whatever it has to search over.

    Carries three things: the text folded to ASCII, and the parts of any
    snake_case identifier in it. Empty values are dropped rather than joined into
    runs of separators.

    This copy exists to be MATCHED, never displayed — nothing renders it — so
    duplication inside it costs storage and nothing else.
    """
    joined = " ".join(v for v in values if v)
    return fold(joined + " " + split_identifiers(joined)).strip()


class RetrievalRefused(RuntimeError):
    """A retrieval could not be performed honestly, and was not attempted."""


class EmbeddingProvider(Protocol):
    """Turns text into a vector. Supplied by the deployment, never bundled.

    Deliberately a Protocol with no implementation in this repository. Shipping
    one would mean either a network client and an API key, or a local model and
    the several hundred megabytes it arrives with — and a default install that
    cannot answer a question without a model is a different product from the one
    this is.
    """

    @property
    def model(self) -> str:
        """The pinned identity, e.g. `openai/text-embedding-3-small`."""

    @property
    def dimensions(self) -> int:
        """Vector width. Must match the index, which fixes it at creation."""

    def embed(self, text: str) -> Sequence[float]:
        """The vector for one piece of text."""


@dataclass(frozen=True)
class Hit:
    """One result, with where it came from.

    `sources` is not decoration: a hit found by both searches is better evidence
    than one found by either, and a reviewer asking why something ranked where it
    did needs to see which retriever proposed it.
    """

    id: str
    label: str
    name: str
    body: str
    rank: int
    sources: tuple[str, ...]


def reciprocal_rank_fusion(*rankings: Sequence[str], k: int = RRF_K) -> list[str]:
    """Merge ranked id lists into one, by position.

    Ties break on the id, so the result is total and stable — two documents that
    fuse to the same score must still come back in the same order on every run,
    or a diff of two searches is noise.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for position, identifier in enumerate(ranking):
            scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (k + position + 1)
    return sorted(scores, key=lambda i: (-scores[i], i))


def fuse(keyword: Sequence[dict], semantic: Sequence[dict],
         limit: int = 20) -> list[Hit]:
    """Both rankings into one list, keeping which retriever found what."""
    by_id = {row["id"]: row for row in list(semantic) + list(keyword)}
    keyword_ids = [row["id"] for row in keyword]
    semantic_ids = [row["id"] for row in semantic]

    found_in: dict[str, list[str]] = {}
    for name, ids in (("keyword", keyword_ids), ("semantic", semantic_ids)):
        for identifier in ids:
            found_in.setdefault(identifier, []).append(name)

    order = reciprocal_rank_fusion(keyword_ids, semantic_ids)
    hits = []
    for rank, identifier in enumerate(order[:limit], start=1):
        row = by_id[identifier]
        hits.append(Hit(
            id=identifier,
            label=row.get("label", ""),
            name=row.get("name", ""),
            body=row.get("body", ""),
            rank=rank,
            sources=tuple(found_in.get(identifier, ())),
        ))
    return hits


def load_provider(spec: str) -> EmbeddingProvider:
    """`package.module:Attribute` -> an `EmbeddingProvider`.

    **Why a dotted path and not a setting naming a bundled model.** None is
    bundled (see `EmbeddingProvider`), so the only honest way to accept one is
    to let a deployment name something it installed itself. This imports what it
    is told and checks the shape; it never falls back to a default, because a
    provider that silently was not the one you asked for produces rankings you
    cannot account for.

    The attribute may be a class (instantiated with no arguments) or an instance.
    """
    import importlib

    if ":" not in spec:
        raise RetrievalRefused(
            f"{spec!r} is not `package.module:Attribute` — name the module and "
            f"the provider in it, e.g. `myco.embeddings:OpenAIProvider`")
    module_name, _, attribute = spec.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise RetrievalRefused(
            f"cannot import {module_name!r}: {e}. A provider is supplied by the "
            f"deployment and must be importable from this interpreter") from e
    try:
        candidate = getattr(module, attribute)
    except AttributeError as e:
        raise RetrievalRefused(
            f"{module_name!r} has no {attribute!r}") from e

    provider = candidate() if isinstance(candidate, type) else candidate

    # Checked here rather than at first use: a provider missing `model` fails
    # inside `require_matching_model` with a message about the corpus, which
    # sends the reader to the graph for a defect in their own class.
    missing = [m for m in ("model", "dimensions", "embed") if not hasattr(provider, m)]
    if missing:
        raise RetrievalRefused(
            f"{spec} is not an EmbeddingProvider: no {', '.join(missing)}. "
            f"It needs `model` (str), `dimensions` (int) and `embed(text)`")
    if not callable(provider.embed):
        raise RetrievalRefused(f"{spec}.embed is not callable")
    return provider


def check_vector(vector, *, dimensions: int, what: str = "vector") -> list[float]:
    """A vector that is safe to store, or a refusal.

    **A NaN does not error; it just never ranks.** A poisoned vector leaves the
    node present, indexed and permanently unreachable by similarity, and the
    symptom is "semantic search does not seem to help" rather than a failure.
    Measured on a hand-rolled provider that reinterpreted hash bytes as floats:
    3 NaNs in 1536, and the only visible effect was that two identical texts
    compared unequal.
    """
    import math

    values = [float(x) for x in vector]
    if len(values) != dimensions:
        raise RetrievalRefused(
            f"{what}: {len(values)} dimensions, index expects {dimensions}. "
            f"The width is fixed when the index is created")
    bad = [i for i, x in enumerate(values) if not math.isfinite(x)]
    if bad:
        raise RetrievalRefused(
            f"{what}: {len(bad)} non-finite value(s) at {bad[:5]} — refusing to "
            f"store. Such a node is indexed and never ranks, which reads as poor "
            f"retrieval rather than as bad data")
    return values


def require_matching_model(provider: EmbeddingProvider, written_with: set[str]) -> None:
    """Refuse a query whose model disagrees with what wrote the vectors.

    `written_with` is the set of `embedding_model` values actually present on the
    nodes. More than one means a partial re-embedding was interrupted, and the
    honest answer there is also a refusal: half the corpus would be silently
    unreachable, and a search that quietly cannot see half its data is worse than
    one that says so.
    """
    if not written_with:
        raise RetrievalRefused(
            "no node carries an embedding, so semantic search would rank nothing. "
            "Populate `embedding` before enabling it, or use keyword search.")
    if len(written_with) > 1:
        raise RetrievalRefused(
            f"vectors were written by more than one model {sorted(written_with)}; "
            f"they are not comparable and part of the corpus would be silently "
            f"unreachable. Re-embed everything with one model.")
    written = next(iter(written_with))
    if written != provider.model:
        raise RetrievalRefused(
            f"the corpus was embedded with {written!r} and this query would use "
            f"{provider.model!r}. Vectors are meaningless across models, and the "
            f"results would be confidently wrong with no error (X-3's lesson, "
            f"applied to embeddings). Re-embed, or query with {written!r}.")


# ---------------------------------------------------------------------------
# Retrieval quality, measured
# ---------------------------------------------------------------------------
#
# **A retrieval system with no query set is not measurable, and everyone's
# instinct about it is wrong.** Two findings from the academy corpus make the
# case: `Metis` returned nothing for a corpus about Métis, and a fix that was
# obviously going to help a particular query did not move it at all. Neither was
# visible without a set of questions whose right answers were written down first.
#
# The scoring is pure so it can be tested without a database, and so the same
# report can be produced from any ranking — including one produced by hand while
# arguing about whether an embedding provider is worth its dependency.


@dataclass(frozen=True)
class Miss:
    """One question whose expected answer was not ranked first."""

    question: str
    expected: str
    rank: int | None          # None when the expected answer is absent entirely
    got: tuple[str, ...]      # what won instead, best first


@dataclass(frozen=True)
class BenchmarkReport:
    total: int
    top1: int
    top3: int
    absent: int
    misses: tuple[Miss, ...]

    @property
    def top1_rate(self) -> float:
        return self.top1 / self.total if self.total else 0.0

    def describe(self) -> str:
        lines = [
            f"  {self.top1}/{self.total} top-1"
            f"   {self.top3}/{self.total} top-3"
            f"   {self.absent}/{self.total} absent",
        ]
        if self.misses:
            lines.append("")
            lines.append("  Not ranked first:")
            for miss in self.misses:
                where = str(miss.rank) if miss.rank else "absent"
                lines.append(f"    {miss.question}")
                lines.append(f"      want {miss.expected} (rank {where})"
                             f" | got {', '.join(miss.got) or 'nothing'}")
        return "\n".join(lines)


def score(rankings: dict[str, Sequence[str]],
          expected: dict[str, str]) -> BenchmarkReport:
    """Rank the expected answer for each question.

    **`absent` is counted separately from a bad rank**, because they are different
    defects: a wrong order is a scoring problem, and a missing answer means the
    document was not retrievable at all — which is what the accent-folding bug
    looked like, and no amount of reranking would have fixed it.
    """
    top1 = top3 = absent = 0
    misses: list[Miss] = []
    for question, want in expected.items():
        ranked = list(rankings.get(question, ()))
        position = ranked.index(want) + 1 if want in ranked else None
        if position == 1:
            top1 += 1
            top3 += 1
            continue
        if position is None:
            absent += 1
        elif position <= 3:
            top3 += 1
        misses.append(Miss(question=question, expected=want, rank=position,
                           got=tuple(r for r in ranked[:2] if r != want)))
    return BenchmarkReport(total=len(expected), top1=top1, top3=top3,
                           absent=absent, misses=tuple(misses))


def load_questions(path) -> dict[str, str]:
    """`question<TAB>expected_id` per line; `#` comments and blanks ignored.

    Deliberately the dullest possible format. A question set is written by hand
    by somebody who knows the corpus, and anything needing a schema would be one
    more thing to get wrong before the first measurement exists.
    """
    from pathlib import Path

    questions: dict[str, str] = {}
    for number, raw in enumerate(Path(path).read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("\t") if p.strip()]
        if len(parts) != 2:
            raise RetrievalRefused(
                f"{path}:{number}: expected `question<TAB>expected_id`")
        questions[parts[0]] = parts[1]
    if not questions:
        raise RetrievalRefused(f"{path} defines no questions")
    return questions
