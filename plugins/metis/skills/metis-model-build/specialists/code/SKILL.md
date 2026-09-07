---
name: metis-model-build-code
description: Recover a behaviour model from a codebase through a code property graph, where every fact must trace to a source line and what could not be verified is counted rather than described. Use when building a model from source, re-extracting after code changed, or when a request names a repository, branch or commit.
allowed-tools:
  - list_workflows
  - run_status
  - ask
  - get_model
  - validate_model
  - coverage
  - model_sources
  - impact
  - sql_review
  - list_entities
  - get_entity
knowledge-from:
  - model_sources.landing
  - ontology.labels
---

# Métis model-build · code

The parent — `metis-model-build` — owns the pipeline, the approval gate and the
`unverified` count that blocks the handoff. Those are assumed here.

What is specific to this source is that **every fact has a line behind it, or it
is not landed**.

## Getting the repository

`metis checkout <remote> <path>` clones a disposable, shallow checkout. **A
checkout is an intake source, not the system under test** (X-7a) — reading a
repository is not calling the service it builds — so it needs no execution tier.

A remote that is a transport helper (`ext::`) or an option (`--upload-pack=…`)
is refused by shape: those are arbitrary command execution wearing a URL. A
token never goes in the URL (PLT-005); use the environment or git's credential
helper.

## Prerequisites, from the parent

1. ✅ Everything lands at `Quarantine` (S-4) — authoring is not approving
2. ✅ `unverified` is reported as a count, and a non-zero one blocks the handoff
3. ✅ Provenance is `static_analysis`, and a run says which source actually ran
4. ✅ Coverage versus correctness: a model with no intent-backed criteria yields
   coverage and never correctness (S-3)

## Anchors are the whole contract (X-6)

An element that cannot be traced back to a line is not emitted. Anchors are three
flat properties — file, line, commit — separate rather than joined, because a
reviewer filters on file.

That is also what makes `impact` possible: given a diff, which transitions were
recovered from those files.

## What is dropped, and on what grounds (X-5a)

Noise is dropped on **provable inertness**, never on visibility or reachability.
Both obvious axes were measured and are wrong:

- `private` was 59 of 389 methods on a real service, and two were reachable from
  a handler — one guarding an endpoint and raising the cause of a 400. Dropping
  on visibility deletes a rejection path.
- Call-reachability drops a service implementation's 31 business methods, because
  the frontend does not resolve interface dispatch.

**Fields are never filtered.** They are private by convention and carry the
schema, required-ness and bounds the type registry is built from.

The count dropped is always reported.

## Steps

`steps/01-extract.md`. The parent's landing, validation and gate steps still run.

The reasoning behind the engine this skill drives is in `knowledge/index.md`.

## What this skill must not do

1. **Never emit an element with no anchor** (X-6). Unanchored is not landed.
2. **Never drop a fact on visibility or reachability** (X-5a). Provable inertness
   or nothing.
3. **Never present a partial extraction as complete** (F-10). Report the skipped
   count and the reason.
4. **Never land `Approved`** (S-4). A source that approved its own output would
   bypass G1 entirely.
