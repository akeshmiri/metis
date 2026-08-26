package com.example.records;

import com.example.records.annotation.GetJson;
import com.example.records.dto.RecordDto;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * One handler, reached only through a meta-annotated mapping stereotype
 * (`@GetJson`, itself a `@GetMapping`). The route it serves is
 * `GET /json/{id}`.
 */
@RestController
@RequestMapping("/json")
public class JsonController {

    private final RecordService service;

    public JsonController(RecordService service) {
        this.service = service;
    }

    @GetJson("/{id}")
    public RecordDto one(@PathVariable String id) {
        return service.get(id);
    }
}
