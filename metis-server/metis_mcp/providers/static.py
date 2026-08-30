"""
Static embeddings — a local provider with no network and no API key.

**Why a static model rather than a transformer.** `model2vec` distils a sentence
transformer into a lookup table: embedding is a token lookup and an average, so
there is no torch, no GPU, no inference server, and a model is tens of megabytes
rather than hundreds. It is weaker than a live transformer on paraphrase, and
that is the trade — a deployment that wants the stronger one names its own
provider, which is what `load_provider` exists for.

**Deterministic, which retrieval needs.** The same text produces the same vector
on every run and every machine, so two searches of an unchanged corpus rank
identically. A provider whose output moves would make `retrieval-bench` a
measurement of nothing.

**The model identity is the pinned name, not a nickname.** `retrieval` refuses a
query whose model disagrees with what the nodes were written with, and that guard
is only as good as the string it compares — so this reports exactly the
repository id the vectors came from.
"""
from __future__ import annotations

from functools import cached_property
from typing import Sequence

# Not a runtime dependency. Named here so the failure is one sentence rather than
# an ImportError from three frames down.
_MISSING = (
    "model2vec is not installed. This provider is an optional extra: "
    "`pip install -e \".[embeddings]\"`, or name a provider of your own with "
    "`--provider package.module:Attribute`."
)


class StaticProvider:
    """A `model2vec` static model, behind `retrieval.EmbeddingProvider`."""

    #: The repository id. Subclasses pin a different one; nothing infers it.
    repository = ""

    def __init__(self, repository: str = "") -> None:
        self._repository = repository or self.repository
        if not self._repository:
            raise ValueError(
                "a provider must name its model — the identity is what "
                "`retrieval` compares a query against")

    @cached_property
    def _model(self):
        try:
            from model2vec import StaticModel
        except ImportError as e:  # pragma: no cover - exercised by the extra
            raise RuntimeError(_MISSING) from e
        return StaticModel.from_pretrained(self._repository)

    @property
    def model(self) -> str:
        return self._repository

    @cached_property
    def dimensions(self) -> int:
        """Read from the model rather than declared.

        A declared width that disagrees with the model is the failure
        `check_vector` catches per vector; reading it means the mismatch cannot
        be introduced in the first place.
        """
        return int(self._model.dim)

    def embed(self, text: str) -> Sequence[float]:
        return [float(x) for x in self._model.encode([text])[0]]

    def embed_many(self, texts: Sequence[str]) -> list[Sequence[float]]:
        """One call for a whole label.

        `cmd_embed` prefers this where a provider offers it — a network provider
        charges per request and a local one pays a per-call overhead that a
        batch amortises.
        """
        return [[float(x) for x in row] for row in self._model.encode(list(texts))]


class Potion(StaticProvider):
    """`minishlab/potion-base-8M` — 256 dimensions, ~30 MB."""

    repository = "minishlab/potion-base-8M"


class PotionLarge(StaticProvider):
    """`minishlab/potion-base-32M` — 512 dimensions, stronger and larger."""

    repository = "minishlab/potion-base-32M"
