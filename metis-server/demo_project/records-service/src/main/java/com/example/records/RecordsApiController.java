package com.example.records;

import com.example.records.dto.RecordDto;
import org.springframework.web.bind.annotation.RestController;

/**
 * Carries no mapping annotation of its own. Every route it serves is inherited
 * from `RecordsApi`, and `byId` is where the behaviour actually lives.
 */
@RestController
public class RecordsApiController implements RecordsApi {

    private final RecordService service;

    public RecordsApiController(RecordService service) {
        this.service = service;
    }

    @Override
    public RecordDto byId(String id) {
        if (id == null || id.isBlank()) {
            throw new RecordNotFoundException(id);
        }
        return service.get(id);
    }
}
