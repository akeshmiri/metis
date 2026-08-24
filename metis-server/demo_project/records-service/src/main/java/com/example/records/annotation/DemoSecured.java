package com.example.records.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * A project's own security annotation. Métis ships no knowledge of it; the
 * project profile declares `role: security, scheme: role` and that is the only
 * reason it is understood.
 */
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
public @interface DemoSecured {
    String[] value();
}
