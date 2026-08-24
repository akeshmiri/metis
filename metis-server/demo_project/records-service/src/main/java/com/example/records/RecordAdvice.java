package com.example.records;

import com.example.records.dto.ErrorDto;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** Estate-wide rejections: the 404 and 409 every endpoint can reach. */
@RestControllerAdvice
public class RecordAdvice {

    @ExceptionHandler(RecordNotFoundException.class)
    public ResponseEntity<ErrorDto> notFound(RecordNotFoundException e) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ErrorDto("record_not_found", e.getMessage()));
    }

    @ExceptionHandler(RecordConflictException.class)
    public ResponseEntity<ErrorDto> conflict(RecordConflictException e) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ErrorDto("record_conflict", e.getMessage()));
    }

    /** One half of the contested mapping — see LegacyAdvice. */
    @ExceptionHandler(RecordLockedException.class)
    public ResponseEntity<ErrorDto> locked(RecordLockedException e) {
        return ResponseEntity.status(HttpStatus.LOCKED)
                .body(new ErrorDto("record_locked", e.getMessage()));
    }
}
