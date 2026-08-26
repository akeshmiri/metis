package com.example.records.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;

/**
 * A project's own mapping stereotype, built exactly the way Spring builds
 * `@GetMapping` itself: meta-annotated with `@RequestMapping`. (It has to be
 * `@RequestMapping` and not `@GetMapping` — the latter is `@Target(METHOD)`,
 * so it cannot legally annotate an annotation type. `@RequestMapping` is
 * `@Target({TYPE, METHOD})`, and TYPE covers annotation declarations.)
 *
 * A pack that matches the literal names in `verbs` sees nothing here, so the
 * handler below is not an endpoint and the service appears to serve one fewer
 * route than it does. Silent under-extraction — the failure this corpus exists
 * to make loud.
 *
 * Deliberately NOT declared in `profile.json`: a project should not have to
 * enumerate its own stereotypes for Spring's own composition rule to work.
 */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@RequestMapping(method = RequestMethod.GET)
public @interface GetJson {
    String[] value() default {};
}
