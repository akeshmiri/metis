package com.example.records;

/** record is locked */
public class RecordLockedException extends RuntimeException {
    public RecordLockedException(String id) {
        super("record is locked: " + id);
    }
}
