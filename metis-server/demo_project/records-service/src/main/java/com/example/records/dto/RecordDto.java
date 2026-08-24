package com.example.records.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * The request and response body. Every annotation here is a test-design input:
 * a required field is a 400 partition, a length bound is a boundary, and an
 * enum's constants are its equivalence classes.
 */
@Schema(description = "A stored record")
public record RecordDto(
        @Schema(description = "Server-assigned identifier", accessMode = Schema.AccessMode.READ_ONLY)
        String id,

        @NotBlank
        @Size(min = 1, max = 120)
        @Schema(description = "Human-readable title", requiredMode = Schema.RequiredMode.REQUIRED)
        String title,

        @NotBlank
        @Schema(description = "Owner of the record", requiredMode = Schema.RequiredMode.REQUIRED)
        String owner,

        @Schema(description = "Who may read this record", allowableValues = {"PRIVATE", "SHARED", "PUBLIC"})
        Visibility visibility) {

    /** Three constants, three equivalence classes. */
    public enum Visibility {
        PRIVATE,
        SHARED,
        PUBLIC
    }
}
