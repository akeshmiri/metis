package com.example.records;

import com.example.records.annotation.Audited;
import com.example.records.annotation.DemoSecured;
import com.example.records.dto.RecordBatchDto;
import com.example.records.dto.RecordDto;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * The demo's primary surface. Five handlers, mixed verbs, one of every outcome
 * shape the behaviour pack knows how to read.
 */
@RestController
@RequestMapping("/record")
public class RecordController {

    private final RecordService service;

    public RecordController(RecordService service) {
        this.service = service;
    }

    /** 201 by construction: `ResponseEntity.status(...)`, not an annotation. */
    @PostMapping
    @DemoSecured({"records:write"})
    @Audited
    public ResponseEntity<RecordDto> create(@Valid @RequestBody RecordDto body) {
        RecordDto saved = service.create(body);
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }

    /** 200, and a 404 contributed by RecordAdvice when the id is unknown. */
    @GetMapping("/{id}")
    public ResponseEntity<RecordDto> one(@PathVariable String id) {
        return ResponseEntity.ok(service.get(id));
    }

    /** A plain-object return: the Spring serialisation contract, not ResponseEntity. */
    @GetMapping
    public RecordDto[] list(@RequestParam(required = false) String owner) {
        return service.list(owner);
    }

    /**
     * The resolvable guard: `listOrEmpty` branches to two internal methods named
     * after response constructors, so both branches resolve to a status and the
     * outcome references the recovered check.
     */
    @GetMapping("/page")
    public ResponseEntity<RecordDto[]> page(@RequestParam(required = false) String owner) {
        return RecordResponses.listOrEmpty(service.list(owner));
    }

    /**
     * The stranded guard: `labelFor` branches to two methods that name no status,
     * so the check is recovered and no outcome references it. It must be attached
     * to this endpoint rather than landing connected to nothing.
     */
    @GetMapping("/{id}/label")
    public String label(@PathVariable String id,
                        @CookieValue(name = "session", required = false) String session) {
        return RecordResponses.labelFor(service.get(id));
    }

    /**
     * 204. The contract in `demo_project/openapi.json` documents 200 for this
     * route on purpose — the "disagreement" deviation.
     */
    @DeleteMapping("/{id}")
    @DemoSecured({"records:write", "records:admin"})
    public ResponseEntity<Void> remove(@PathVariable String id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }

    /**
     * The nested-payload entry point: its body is a batch of records, so the
     * payload graph has to continue Parameter -> RecordBatchDto -> RecordDto.
     */
    @PostMapping("/batch")
    public ResponseEntity<RecordDto[]> submitBatch(@Valid @RequestBody RecordBatchDto body) {
        return ResponseEntity.ok(service.list(null));
    }

    @PutMapping("/{id}")
    public ResponseEntity<RecordDto> replace(@PathVariable String id,
                                             @Valid @RequestBody RecordDto body) {
        return ResponseEntity.ok(service.replace(id, body));
    }
}
