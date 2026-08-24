package com.example.records;

import com.example.records.dto.RecordDto;

/** No persistence: the demo is a parse target, not a runnable service. */
public class RecordService {

    public RecordDto create(RecordDto body) {
        if (body.title() == null) {
            throw new RecordConflictException("untitled");
        }
        return body;
    }

    public RecordDto get(String id) {
        if (id.isEmpty()) {
            throw new RecordNotFoundException(id);
        }
        return new RecordDto(id, "title", "owner", RecordDto.Visibility.PRIVATE);
    }

    public RecordDto[] list(String owner) {
        return new RecordDto[0];
    }

    public RecordDto replace(String id, RecordDto body) {
        return body;
    }

    public void delete(String id) {
        if (id.isEmpty()) {
            throw new RecordNotFoundException(id);
        }
    }

    public void archive(String id) {
        throw new RecordLockedException(id);
    }

    public String summarise(String id) {
        throw new SummaryUnavailableException(id);
    }
}
