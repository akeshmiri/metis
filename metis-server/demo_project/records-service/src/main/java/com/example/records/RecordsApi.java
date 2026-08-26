package com.example.records;

import com.example.records.dto.RecordDto;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;

/**
 * The API contract as an interface — the shape springdoc generates and that
 * teams share between a client and the service that serves it.
 *
 * The mapping lives HERE; the implementation below carries none. Spring
 * resolves a handler's mapping through the methods it overrides, so the route
 * belongs to the implementing method — the one with a body, and therefore the
 * only one the behaviour pack can read guards and outcomes from.
 *
 * Attributing it to this abstract method instead is not a missing route but a
 * worse fault: the endpoint is recovered, points at a method with no body, and
 * the behaviour beneath it silently comes back empty.
 */
@RequestMapping("/contract")
public interface RecordsApi {

    @GetMapping("/{id}")
    RecordDto byId(@PathVariable String id);
}
