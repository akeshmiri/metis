package com.example.records;

import com.example.records.dto.ErrorDto;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * A controller that handles its own exception. Spring scopes an in-controller
 * `@ExceptionHandler` to this controller alone, so the 422 below is a rejection
 * for `/summary/{id}` and for nothing else — the condition that separates a
 * scoped rejection from an estate-wide one.
 */
@RestController
@RequestMapping("/summary")
public class ScopedController {

    private final RecordService service;

    public ScopedController(RecordService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public ResponseEntity<String> summary(@PathVariable String id) {
        requireSummarisable(id);
        return ResponseEntity.ok(service.summarise(id));
    }

    /**
     * **A private method that carries behaviour, and must be KEPT.** It guards an
     * endpoint and raises the exception the handler below maps, so filtering by
     * visibility would delete a rejection path. Measured on a real service, two
     * private methods were reachable from a handler and a blanket private filter
     * would have lost both.
     */
    private void requireSummarisable(String id) {
        if (id == null || id.isEmpty()) {
            throw new SummaryUnavailableException(id);
        }
    }

    @ExceptionHandler(SummaryUnavailableException.class)
    public ResponseEntity<ErrorDto> unavailable(SummaryUnavailableException e) {
        return ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY)
                .body(new ErrorDto("summary_unavailable", e.getMessage()));
    }
}
