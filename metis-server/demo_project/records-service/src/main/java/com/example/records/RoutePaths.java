package com.example.records;

/**
 * Route fragments a controller reaches through a **static import**.
 *
 * Holding them outside the controller is the point: a constant used through a
 * static import carries no qualifier at the use site, so the resolver cannot
 * key on its owner and must fall back to the simple name — which is where
 * {@link ArchiveCache}'s collision becomes reachable.
 */
public final class RoutePaths {

    public static final String ID_SEGMENT = "/{id}";
    public static final String ARCHIVE = ID_SEGMENT + "/archive";

    private RoutePaths() {
    }
}
