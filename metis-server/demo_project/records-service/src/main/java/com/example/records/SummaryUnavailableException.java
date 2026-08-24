package com.example.records;

/** summary cannot be produced */
public class SummaryUnavailableException extends RuntimeException {
    public SummaryUnavailableException(String id) {
        super("summary cannot be produced: " + id);
    }
}
