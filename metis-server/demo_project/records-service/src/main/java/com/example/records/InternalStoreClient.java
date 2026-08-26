package com.example.records;

import com.example.records.annotation.InternalFeign;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

/**
 * Not an API surface, and not marked with the literal `@FeignClient` either.
 * One mapping, which must appear in NO endpoint — same claim `ArchiveClient`
 * makes, one meta-annotation removed.
 */
@InternalFeign(name = "internal-store")
public interface InternalStoreClient {

    @GetMapping("/internal-store/{id}")
    String peek(@PathVariable String id);
}
