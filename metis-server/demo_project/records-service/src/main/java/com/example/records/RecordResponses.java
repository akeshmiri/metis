package com.example.records;

import com.example.records.dto.RecordDto;
import org.springframework.http.ResponseEntity;

/**
 * **The guard conditions.** A handler that returns a helper puts its branch point
 * inside that helper, and the behaviour pack recovers the ternary as a `Check`.
 * Two shapes live here and they behave differently on purpose:
 *
 *   `listOrEmpty`  branches to `ok` and `noContent`, which are internal methods
 *                  named after declared response constructors — so each branch
 *                  resolves to a status, an outcome is emitted, and the outcome
 *                  REFERENCES the check. This is the normal form.
 *
 *   `labelFor`     branches to `publicLabel` and `privateLabel`, which name no
 *                  status at all. The check is still recovered — it is a real
 *                  condition in real code — and no outcome references it, so it
 *                  is **stranded**. On a real service both recovered checks were
 *                  of this shape and both landed connected to nothing.
 */
final class RecordResponses {

    private RecordResponses() {
    }

    /** The resolvable guard: both branches name a status. */
    static ResponseEntity<RecordDto[]> listOrEmpty(RecordDto[] found) {
        return found.length == 0 ? noContent() : ok(found);
    }

    static ResponseEntity<RecordDto[]> ok(RecordDto[] found) {
        return ResponseEntity.ok(found);
    }

    static ResponseEntity<RecordDto[]> noContent() {
        return ResponseEntity.noContent().build();
    }

    /** The stranded guard: neither branch names a status. */
    static String labelFor(RecordDto record) {
        return record.visibility() == RecordDto.Visibility.PUBLIC
                ? publicLabel(record)
                : privateLabel(record);
    }

    static String publicLabel(RecordDto record) {
        return record.title();
    }

    static String privateLabel(RecordDto record) {
        return "hidden";
    }
}
