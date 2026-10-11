package com.sensorpulse.web;

import java.nio.charset.StandardCharsets;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {

    private static final byte[] BODY = "{\"status\":\"ok\"}".getBytes(StandardCharsets.UTF_8);

    @GetMapping("/health")
    public ResponseEntity<byte[]> health() {
        return Json.respond(HttpStatus.OK, BODY); // no DB access
    }
}
