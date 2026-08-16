# Knowledge Index — intake-processor

No fragments extracted yet. All 6 supported sources share one generic extraction procedure
(see `steps/01-extract.md`) — this is a single-step skill dispatched by a source→extractor→config
lookup table (kept in `../SKILL.md`), not a multi-route skill with distinct per-source procedures.
The 5 Hard Rules stay directly in `../SKILL.md` since they are always-enforced regardless of source.
