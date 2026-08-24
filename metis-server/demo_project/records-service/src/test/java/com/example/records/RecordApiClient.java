package com.example.records;

import com.example.records.dto.RecordDto;
import feign.RequestLine;

/**
 * The declared surface the integration tests drive. `@RequestLine` is what makes
 * a test's route recoverable: the inventory pack resolves a test's callee to the
 * route the callee declares. A test that writes its path as a bare literal has
 * no declaration to resolve, and is reported as unresolved rather than credited.
 */
public interface RecordApiClient {

    @RequestLine("GET /record/{id}")
    RecordDto one(String id);

    @RequestLine("POST /record")
    RecordDto create(RecordDto body);

    @RequestLine("DELETE /record/{id}")
    void remove(String id);
}
