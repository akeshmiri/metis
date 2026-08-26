package com.example.records;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

/**
 * Spring MVC, not REST. `@Controller` does NOT imply `@ResponseBody`, so the
 * String returned here is a **view name** handed to a template resolver — not
 * a response body a caller ever receives.
 *
 * A pack that reads the mapping annotation without checking the class
 * stereotype models this as an API returning the literal text "record-list",
 * and generation then writes a test asserting a body that cannot appear. Same
 * shape as the `@FeignClient` defect: behaviour claimed that the service does
 * not have.
 */
@Controller
public class ViewController {

    @GetMapping("/ui/records")
    public String list() {
        return "record-list";
    }
}
