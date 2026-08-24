package com.example.records;

/** no such record */
public class RecordNotFoundException extends RuntimeException {
    public RecordNotFoundException(String id) {
        super("no such record: " + id);
    }
}
