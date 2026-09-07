# 01 — establish what is being compared

## Actions

1. Get the file list: either from the user, or by resolving a commit range.
2. Echo the resolved list back. A caller who asked about two commits is owed the
   files the answer was computed from — otherwise a mismatched path root looks
   identical to a narrow diff.
3. Record the commit the graph was extracted at, beside the range being reviewed.

## Forbidden substitutions

- Do not treat an empty file list as "nothing changed". Git returns nothing for
  an empty diff *and* for a range it cannot resolve.
- Do not re-extract silently to make the answer current. Say the model is stale
  and let the user choose.

## Drift check

The range should be the change under review. A range that includes unrelated
commits produces impact nobody asked about.

## Report

The range, the resolved files, and the graph's extraction commit.
