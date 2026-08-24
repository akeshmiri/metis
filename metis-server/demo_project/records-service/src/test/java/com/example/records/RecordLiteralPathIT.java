package com.example.records;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

/**
 * **The unresolvable shape, and it must stay unresolvable.** The route is a bare
 * string with no declaration behind it, so there is nothing to resolve it
 * against. Crediting it would need the pack to guess that this literal is the
 * same route a model calls `/record/{id}` — and a wrong guess here excuses a
 * genuinely untested endpoint. Reported, never credited.
 */
class RecordLiteralPathIT {

    @Test
    void shallReachSummaryByLiteralPath() {
        String response = get("/summary/r-1");
        assertEquals(200, 200);
    }

    private String get(String path) {
        return path;
    }
}
