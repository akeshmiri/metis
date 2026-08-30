"""
The bundled-as-an-extra embedding providers (`metis_mcp/providers/`).

**Why any exist.** `retrieval.EmbeddingProvider` is a Protocol with no
implementation, so a default install loads no model — that stands. What it did
not give a deployment was a supported option, so each one wrote its own and
re-derived the vector guards: the width check, the NaN check, the model-identity
pin. These providers are thin on purpose. They hold a model identity and produce
vectors; every guard stays in `retrieval`, where one implementation serves all.

**Free to run without the extra.** Everything that needs `model2vec` skips when
it is absent, so a default install's suite is unaffected — which is the property
the extra exists to preserve. The shape tests below run either way.
"""
from __future__ import annotations

import pytest

from metis_mcp.providers.static import Potion, PotionLarge, StaticProvider
from metis_mcp.retrieval import RetrievalRefused, load_provider

try:  # noqa: SIM105
    import model2vec  # noqa: F401
    HAVE_MODEL = True
except ImportError:
    HAVE_MODEL = False

needs_model = pytest.mark.skipif(
    not HAVE_MODEL, reason="the `embeddings` extra is not installed")


# ---------------------------------------------------------------------------
# Shape — no model needed
# ---------------------------------------------------------------------------

def test_a_provider_must_name_its_model():
    """The identity is what `retrieval` compares a query against, so a provider
    without one would make the mismatch guard compare `''` to `''` and pass."""
    with pytest.raises(ValueError):
        StaticProvider()


def test_the_declared_repositories_are_pinned_not_inferred():
    assert Potion.repository == "minishlab/potion-base-8M"
    assert PotionLarge.repository == "minishlab/potion-base-32M"
    assert Potion().model == Potion.repository


def test_the_loader_accepts_them_by_dotted_path():
    """`load_provider` is the only supported way in, and it never falls back."""
    assert load_provider("metis_mcp.providers.static:Potion").model == \
        "minishlab/potion-base-8M"


def test_an_unknown_provider_is_refused_not_defaulted():
    with pytest.raises(RetrievalRefused):
        load_provider("metis_mcp.providers.static:NoSuchProvider")
    with pytest.raises(RetrievalRefused):
        load_provider("not_a_dotted_path")


# ---------------------------------------------------------------------------
# Behaviour — needs the extra
# ---------------------------------------------------------------------------

@needs_model
def test_the_width_is_read_from_the_model_not_declared():
    """A declared width that disagrees with the model is a per-vector failure
    `check_vector` catches; reading it means it cannot be introduced."""
    assert Potion().dimensions == 256


@needs_model
def test_a_vector_is_finite_and_the_right_width():
    """A NaN does not error — it just never ranks, leaving a node indexed and
    permanently unreachable. `check_vector` exists for that; this asserts the
    provider does not produce the problem in the first place."""
    import math

    from metis_mcp.retrieval import check_vector

    v = Potion().embed("a state is one observable situation on one surface")
    assert len(v) == 256
    assert all(math.isfinite(x) for x in v)
    check_vector(v, dimensions=256)          # refuses on width or NaN


@needs_model
def test_the_same_text_embeds_identically():
    """Determinism is not a nicety: `retrieval-bench` measures ranking, and a
    provider whose output moved would make it a measurement of nothing."""
    p = Potion()
    assert p.embed("the two gates") == p.embed("the two gates")


@needs_model
def test_related_text_scores_above_unrelated():
    """The only test here that checks the model is a MODEL rather than a
    well-shaped random number generator."""
    import math

    p = Potion()
    def cos(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))

    q = p.embed("what is a state and what is a transition")
    near = p.embed("states and transitions: the shape of the model")
    far = p.embed("how do I authenticate against the API")
    assert cos(q, near) > cos(q, far)


@needs_model
def test_a_batch_matches_one_at_a_time():
    """`cmd_embed` prefers `embed_many` where a provider offers it. If the two
    disagreed, the corpus would hold vectors a query could never reproduce."""
    p = Potion()
    texts = ["the two gates", "deferred joins"]
    assert p.embed_many(texts) == [p.embed(t) for t in texts]
