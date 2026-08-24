package com.example.records;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.example.records.dto.RecordDto;
import org.junit.jupiter.api.Test;

/**
 * `*IT` + `*Controller` in the name is what grades these `api_functional`.
 *
 * Three conditions:
 *   - `shallReadOne` asserts its status inline.
 *   - `shallCreate` asserts through a private helper — the assertion is one hop
 *     away, and collecting literals from the test method alone finds nothing and
 *     grades a genuinely covered outcome as unproven.
 *   - `shallRemove` reaches a route and asserts NO status, which is the
 *     outcome-unproven grade rather than either covered or uncovered.
 */
class RecordControllerIT {

    private final RecordApiClient client = null;

    @Test
    void shallReadOne() {
        RecordDto found = client.one("r-1");
        assertEquals(200, statusOf(found));
    }

    @Test
    void shallCreate() {
        createAndVerify(new RecordDto(null, "title", "owner", RecordDto.Visibility.PRIVATE));
    }

    @Test
    void shallRemove() {
        client.remove("r-1");
    }

    private void createAndVerify(RecordDto body) {
        RecordDto saved = client.create(body);
        assertEquals(201, statusOf(saved));
    }

    private int statusOf(RecordDto dto) {
        return dto == null ? 0 : 200;
    }
}
