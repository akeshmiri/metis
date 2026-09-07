package com.example.records;

import com.example.records.dto.RecordDto;

/**
 * The complexity condition (X-5a's neighbour): one method with real branching
 * and one with none, in the same class.
 *
 * <p>Nothing else in this service branches more than three times, so a
 * complexity metric extracted from it would be flat — and a flat metric is one
 * a test cannot tell from a broken one. This class exists so the extracted
 * figure has a spread with a known shape: {@code retentionDays} carries nested
 * conditions and boolean operators, {@code isRetained} carries none.
 *
 * <p>No persistence, like the rest of the demo. It is a parse target.
 */
public class RetentionPolicy {

    /** Deliberately branchy: the high end of the spread a test asserts against. */
    public int retentionDays(RecordDto record, String tier, boolean legalHold) {
        if (record == null) {
            return 0;
        }
        if (legalHold) {
            return Integer.MAX_VALUE;
        }

        int days = 30;
        if (record.visibility() == RecordDto.Visibility.PRIVATE) {
            if (tier != null && tier.equals("gold")) {
                days = 3650;
            } else if (tier != null && tier.equals("silver")) {
                days = 730;
            } else {
                days = 365;
            }
        } else if (record.visibility() == RecordDto.Visibility.PUBLIC) {
            days = tier == null || tier.isEmpty() ? 90 : 180;
        }

        if (record.owner() == null || record.owner().isEmpty()) {
            days = Math.min(days, 7);
        }
        for (char c : record.id().toCharArray()) {
            if (c == '-') {
                days += 1;
            }
        }
        return days;
    }

    /** Deliberately flat: the low end of the same spread, in the same class. */
    public boolean isRetained(int elapsedDays, int retentionDays) {
        return elapsedDays < retentionDays;
    }
}
