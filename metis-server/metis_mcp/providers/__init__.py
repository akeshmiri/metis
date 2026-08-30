"""
Embedding providers, supplied as an optional extra.

**Why anything lives here at all.** `retrieval.EmbeddingProvider` is deliberately
a Protocol with no implementation, on the argument that bundling one means either
a network client and an API key or a local model and the hundreds of megabytes it
arrives with — and a default install that cannot answer without a model is a
different product. That argument stands, and nothing in this package is imported
unless a deployment names it: `metis embed --provider metis_mcp.providers.static:Potion`.

What it does not stand against is a SUPPORTED option. Leaving every deployment to
write its own means each one re-derives the vector guards — the width check, the
NaN check, the model-identity pin — and gets one of them wrong quietly. The
providers here are thin: they hold the model identity and produce vectors, and
every guard stays in `retrieval` where one implementation serves all of them.

Install with `pip install -e ".[embeddings]"`. A default install has none of
this, and `metis embed` without `--provider` remains impossible.
"""
