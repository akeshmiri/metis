package com.example.records;

/**
 * **The compaction condition: nothing here is user-facing and nothing reaches it
 * from the model.** No endpoint accepts or returns it, no payload field is typed
 * by it, and no handler is it. On a real service 44 classes, 126 fields and 187
 * methods were of exactly this kind — 52% of the graph, and the model could lead
 * you to none of it.
 *
 * It must be classified `internal` and must not be landed. Delete this file and
 * the compaction test stops testing anything.
 */
final class InternalAudit {

    private static final String PREFIX = "audit";

    private final StringBuilder buffer = new StringBuilder();

    void record(String event) {
        buffer.append(PREFIX).append(':').append(event).append('\n');
    }

    String drain() {
        String out = buffer.toString();
        buffer.setLength(0);
        return out;
    }
}
