package com.example.records;

import static com.example.records.RoutePaths.ARCHIVE;

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
 * 3. **The method's constant arrives by static import**, so it has no qualifier
 *    at the use site and must resolve by simple name — which is what makes
 *    {@link ArchiveCache}'s name collision reachable.
 *
 * This route is absent from `openapi.json` on purpose — the "code-only"
 * deviation.
 */
@RestController
@RequestMapping(ArchiveController.BASE)
public class ArchiveController {

    static final String BASE = "/record";

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
