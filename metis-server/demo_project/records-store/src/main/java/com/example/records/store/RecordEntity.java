package com.example.records.store;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * **The entity→table mapping, stated in source.** Measured on a real service,
 * `@Entity`/`@Table`/`@Column` were in **zero** files — the entities lived in a
 * dependency jar — so the code could only ever *propose* a table name from
 * Spring's naming strategy and the catalogue had to confirm it.
 *
 * This entity states the mapping, so the confirmed path is exercised. The
 * unstated path is `TagEntity`, which declares no `@Table` at all.
 */
@Entity
@Table(name = "record")
public class RecordEntity {

    @Id
    @Column(name = "id")
    private String id;

    @Column(name = "title", length = 120, nullable = false)
    private String title;

    /** The column name differs from the field name on purpose. */
    @Column(name = "owner_name", nullable = false)
    private String owner;

    @Column(name = "archived", nullable = false)
    private boolean archived;

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
