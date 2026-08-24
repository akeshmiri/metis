package com.example.records.store;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

/**
 * The three query forms, in the order they actually occur in real code.
 * Measured on a real service: 11 files used derived methods, and `@Query`,
 * `EntityManager`, `JdbcTemplate` and native SQL appeared in **none**.
 */
public interface RecordRepository extends JpaRepository<RecordEntity, String> {

    /** Tier 1 — a derived method, translatable once the mapping resolves. */
    List<RecordEntity> findByOwnerAndArchived(String owner, boolean archived);

    /** Tier 1, with an operator that is not equality. */
    List<RecordEntity> findByTitleContainingIgnoreCase(String fragment);

    /** Tier 2 — native SQL, verbatim: there is nothing to translate. */
    @Query(value = "SELECT * FROM record WHERE owner_name = ?1 AND archived = false",
           nativeQuery = true)
    List<RecordEntity> activeForOwner(String owner);

    /** Tier 3 — JPQL, whose entity and field names need the same resolution. */
    @Query("SELECT r FROM RecordEntity r WHERE r.archived = true")
    List<RecordEntity> archived();
}
