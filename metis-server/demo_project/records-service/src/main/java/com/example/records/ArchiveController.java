package com.example.records;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * Two conditions live here.
 *
 * 1. **The route is composed from constants**, never written as a literal. A
 *    resolver that only accepts a string starting with a quote invents a path
 *    here instead of resolving one.
 * 2. **`@ResponseStatus` sets the outcome**, so the annotated path is exercised
 *    distinctly from status-by-construction.
 *
 * This route is absent from `openapi.json` on purpose — the "code-only"
 * deviation.
 */
@RestController
@RequestMapping(ArchiveController.BASE)
public class ArchiveController {

    static final String BASE = "/record";
    private static final String ID_SEGMENT = "/{id}";
    private static final String ARCHIVE = ID_SEGMENT + "/archive";

    private final RecordService service;

    public ArchiveController(RecordService service) {
        this.service = service;
    }

    @PostMapping(ARCHIVE)
    @ResponseStatus(HttpStatus.ACCEPTED)
    public void archive(@PathVariable String id) {
        service.archive(id);
    }
}
