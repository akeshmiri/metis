package com.example.records;

import com.example.records.dto.ErrorDto;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * **The contested mapping (GD-9).** This advice maps `RecordLockedException` to
 * 409 while `RecordAdvice` maps it to 423, and neither declares an `@Order`.
 * Spring's precedence between two unordered advices is not statically decidable,
 * so the correct behaviour is to attribute no rejection and say why — not to pick
 * whichever was seen first.
 */
@RestControllerAdvice
public class LegacyAdvice {

    @ExceptionHandler(RecordLockedException.class)
    public ResponseEntity<ErrorDto> stillLocked(RecordLockedException e) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ErrorDto("legacy_locked", e.getMessage()));
    }
}
