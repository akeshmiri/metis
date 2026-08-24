package com.example.records;

/** already archived */
public class RecordConflictException extends RuntimeException {
    public RecordConflictException(String id) {
        super("already archived: " + id);
    }
}
