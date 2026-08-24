package com.example.records.dto;

import io.swagger.v3.oas.annotations.media.Schema;

/**
 * The body every rejection carries. It exists so a rejection's `response_body`
 * is a populated type rather than the empty string — an empty body is a claim,
 * not a gap, and a generated case would assert it.
 */
@Schema(description = "A refusal, with a stable machine-readable code")
public record ErrorDto(
        @Schema(description = "Stable error code") String code,
        @Schema(description = "Human-readable detail") String detail) {
}
