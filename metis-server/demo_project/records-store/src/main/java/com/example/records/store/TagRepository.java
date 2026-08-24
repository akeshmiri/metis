package com.example.records.store;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

/**
 * Its entity declares no `@Table`, so every query here is a **proposal** until
 * the catalogue confirms it — and the catalogue refutes it. These must land as
 * unresolved rather than as edges to a table that does not exist.
 */
public interface TagRepository extends JpaRepository<TagEntity, Long> {

    List<TagEntity> findByTag(String tag);
}
