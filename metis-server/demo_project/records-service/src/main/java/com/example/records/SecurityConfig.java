package com.example.records;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

/**
 * Security declared in the filter chain rather than on a handler.
 *
 * The pack reads security only from annotations, and its own comment concedes
 * the rest: "Security enforced in a filter chain or at a gateway is invisible
 * to this pack." That is honest, and it is also the reason Métis can only ever
 * say "nothing was declared here" — never "this route is protected" or "this
 * route is deliberately public".
 *
 * Three claims live in this chain, and they are three different facts:
 *   /ui/**        permitAll  — deliberately public
 *   /record/**    a role     — protected, and by what
 *   anyRequest    a fallback — the estate-wide default every other route gets
 *
 * `permitAll` here is the ONLY shape in the corpus that licenses the word
 * "open". Everywhere else, absence of a declaration is not evidence of one.
 */
@Configuration
public class SecurityConfig {

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/ui/**").permitAll()
                        .requestMatchers("/record/**").hasRole("RECORDS")
                        .anyRequest().authenticated())
                .build();
    }
}
