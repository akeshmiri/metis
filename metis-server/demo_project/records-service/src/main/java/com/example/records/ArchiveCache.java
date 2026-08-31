package com.example.records;

import java.util.List;

/**
 * **The colliding-constant condition.**
 *
 * `ARCHIVE` here shares its simple name with {@link RoutePaths#ARCHIVE}, which
 * is a real route fragment. This one is not a route — it is a lookup list — but
 * its initialiser *contains a string literal*, and that is the only test the
 * structural pack applies when deciding whether a constant is a candidate route
 * fragment.
 *
 * Because {@link ArchiveController} reaches `ARCHIVE` through a static import,
 * the resolver has no owner to key on and resolves by simple name. Treating
 * every same-named constant as a rival answer finds two and refuses both, so a
 * route composed entirely of constants comes out `__unresolved__` because an
 * unrelated class reused the name.
 *
 * An initialiser that resolves to nothing is **no answer**, not a different
 * one. Two constants that both resolve, to different routes, must still refuse.
 */
final class ArchiveCache {

    static final List<String> ARCHIVE = List.of("archive-store");

    private ArchiveCache() {
    }
}
