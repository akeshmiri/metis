package com.example.records.store;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;

/**
 * **No `@Table`, so the table name can only be PROPOSED** — Spring's default
 * strategy turns `TagEntity` into `tag_entity`, and the catalogue in
 * `catalogue.json` declares `record_tag` instead.
 *
 * The proposal must therefore be **refuted**, reported as unresolved with its
 * basis named, and no edge written. Give this class a `@Table` and the refute
 * case stops existing.
 */
@Entity
public class TagEntity {

    @Id
    private Long id;

    private String tag;
}
