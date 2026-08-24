package com.example.records.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.util.List;

/**
 * **The nested payload condition (X-6b).** Every field here exists to make one
 * part of the payload graph or the typed-validation vocabulary assertable.
 *
 * Without `Field -OF_TYPE-> Class` the `records` field below names `RecordDto`
 * in a string property and reaches it through nothing, so the payload a test case
 * has to construct is only ever one level deep.
 */
@Schema(description = "A batch of records submitted together")
public record RecordBatchDto(

        /** A nested declared type: the graph must continue through this. */
        @NotNull
        @Valid
        @Schema(description = "The records in this batch")
        List<RecordDto> records,

        /**
         * **`@Size` on a collection is cardinality, not length.** Calling both
         * `max_length` would be a quiet lie about what a fixture has to build,
         * so this lands as `expected_max_size`.
         */
        @Size(min = 1, max = 50)
        @Schema(description = "Tags applied to every record in the batch")
        List<String> tags,

        /** A String @Size: length, and the pair the collection above must not use. */
        @NotBlank
        @Size(min = 3, max = 40)
        @Schema(description = "Who submitted the batch")
        String submittedBy,

        /** A pattern is a partition a generator can satisfy or violate. */
        @Pattern(regexp = "[A-Z]{2}-[0-9]{4}")
        @Schema(description = "Batch reference")
        String reference,

        /** An enum field: its constants are the partitions, no bound needed. */
        @Schema(description = "How the batch should be processed")
        Mode mode,

        /**
         * **An unrecognised constraint must stay visible.** `@Audited` is
         * declared by the project profile with `role: ignore`, so it is a
         * constraint Métis recognises as a name and honours as no property. It
         * must remain in `constraints` rather than vanishing (X-5a).
         */
        @com.example.records.annotation.Audited
        @Schema(description = "Free-form note")
        String note) {

    /**
     * Its constants ARE the equivalence partitions of `mode`.
     *
     * **And it has a method on purpose.** An enum that declares one is the
     * condition that catches an edge planned against `:Class` when the node
     * carries `:Enum`: the ontology check passes, because `is_allowed` walks the
     * specialisation chain, and the merge then finds nothing. Measured on a real
     * service, three `DECLARES_METHOD` edges were reported unmatched for exactly
     * this reason. Remove `fromValue` and that guard stops guarding anything.
     */
    public enum Mode {
        IMMEDIATE,
        DEFERRED,
        DRY_RUN;

        /**
         * **Self-typed and private, and it must NOT be read as a constant.** A
         * real enum carried exactly this shape, and a test keyed only on the
         * field's type reported it as a fourth value — so a field of this type
         * offered a partition the value space does not contain, and a generated
         * case would have sent it as input.
         */
        private final Mode fallback = IMMEDIATE;

        public Mode getFallback() {
            return fallback;
        }

        public static Mode fromValue(String raw) {
            for (Mode candidate : values()) {
                if (candidate.name().equalsIgnoreCase(raw)) {
                    return candidate;
                }
            }
            return IMMEDIATE;
        }
    }
}
