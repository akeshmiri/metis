package com.example.records.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * **The accessor-noise condition.** A classic POJO rather than a record, because
 * a record's accessors are bare names (`title()`) and the shape that floods a
 * graph is `getTitle`/`setTitle`.
 *
 * Measured on a real 12-endpoint service: 166 of 389 methods were accessors like
 * these and 23 more were `equals`/`hashCode`/`toString` — 49% of the method
 * nodes, and nothing in Métis reasons about any of them.
 *
 * What must survive is the **fields**: `@Schema` descriptions, `@NotBlank` and
 * `@Size` are test-design inputs, and they live here, not on the getter. Dropping
 * a getter must not drop its field.
 */
@Schema(description = "A condensed record for list views")
public class RecordSummaryDto {

    @NotBlank
    @Size(min = 1, max = 120)
    @Schema(description = "Human-readable title", requiredMode = Schema.RequiredMode.REQUIRED)
    private String title;

    @Schema(description = "Owner of the record")
    private String owner;

    @Schema(description = "Whether the record has been archived")
    private boolean archived;

    @Schema(description = "How many times delivery was retried")
    private Integer retries;

    // --- trivial accessors: these are the noise, and they must be dropped ---

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getOwner() {
        return owner;
    }

    public void setOwner(String owner) {
        this.owner = owner;
    }

    public boolean isArchived() {
        return archived;
    }

    public void setArchived(boolean archived) {
        this.archived = archived;
    }

    /**
     * **Named after a REAL field and still not an accessor.** `retries` exists,
     * so the name-and-field test says "accessor"; the branch says otherwise, and
     * a lazy default is behaviour a test can distinguish. This is the condition
     * that exercises the body check specifically — `getDisplayLabel` below has no
     * field behind it, so it is caught one test earlier and leaves the body check
     * unproven.
     */
    public int getRetries() {
        if (retries == null) {
            return 0;
        }
        return retries;
    }

    /**
     * **A getter that is not an accessor, and must be KEPT.** It is named like
     * one and has no field behind it, and it branches — so a filter keyed on the
     * name alone would delete a real decision.
     */
    public String getDisplayLabel() {
        if (archived) {
            return title + " (archived)";
        }
        return title;
    }

    // --- generated boilerplate: also noise ---

    @Override
    public boolean equals(Object other) {
        return other instanceof RecordSummaryDto
                && ((RecordSummaryDto) other).title.equals(title);
    }

    @Override
    public int hashCode() {
        return title == null ? 0 : title.hashCode();
    }

    @Override
    public String toString() {
        return "RecordSummaryDto[" + title + "]";
    }
}
