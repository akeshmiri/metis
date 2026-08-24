package com.example.records;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;

/**
 * **Not an API surface.** These mappings declare calls this service MAKES of a
 * different one. Counted as endpoints they become behaviour this service does not
 * have, and then test cases nobody can run. Two mappings here, and the endpoint
 * count must be blind to both.
 */
@FeignClient(name = "archive-store")
public interface ArchiveClient {

    @GetMapping("/store/{id}")
    String fetch(@PathVariable String id);

    @PostMapping("/store")
    String put(String payload);
}
