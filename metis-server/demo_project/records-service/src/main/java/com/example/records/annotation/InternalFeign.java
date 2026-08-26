package com.example.records.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.cloud.openfeign.FeignClient;

/**
 * The same composition rule, pointed at the exclusion instead of the inclusion.
 *
 * `isOutboundClient` matches the literal name `FeignClient`, so a house
 * stereotype wrapping it escapes the exclusion and its mappings are counted as
 * endpoints this service serves. That is exactly the defect `ArchiveClient`
 * was added to prevent, reachable again by one indirection.
 */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@FeignClient
public @interface InternalFeign {
    String name() default "";
}
