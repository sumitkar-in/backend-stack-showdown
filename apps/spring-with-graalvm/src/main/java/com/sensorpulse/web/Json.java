package com.sensorpulse.web;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

/** Explicit byte[] bodies: Content-Length is always set (never chunked). */
public final class Json {
    private Json() {}

    private static final ObjectMapper MAPPER =
            new ObjectMapper().enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

    public static ResponseEntity<byte[]> respond(HttpStatus status, byte[] body) {
        return ResponseEntity.status(status).contentType(MediaType.APPLICATION_JSON).body(body);
    }

    public static ResponseEntity<byte[]> respond(HttpStatus status, Object value) {
        try {
            return respond(status, MAPPER.writeValueAsBytes(value));
        } catch (JsonProcessingException e) {
            throw new IllegalStateException(e);
        }
    }

    /** Stage 1: malformed / empty JSON -> 400. */
    public static JsonNode parse(byte[] body) {
        try {
            JsonNode node = MAPPER.readTree(body);
            if (node == null || node.isMissingNode()) {
                throw ApiException.badRequest();
            }
            return node;
        } catch (java.io.IOException e) {
            throw ApiException.badRequest();
        }
    }
}
