package com.sensorpulse.web;

import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.HttpMediaTypeException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.NoHandlerFoundException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/** Normalizes every error to {"error": ...}. */
@RestControllerAdvice
public class ApiErrors {

    private static final byte[] INTERNAL = "{\"error\":\"internal\"}".getBytes(StandardCharsets.UTF_8);

    @ExceptionHandler(ApiException.class)
    ResponseEntity<byte[]> api(ApiException e) {
        if (e.status() == HttpStatus.UNAUTHORIZED) {
            return ResponseEntity.status(e.status())
                    .header("WWW-Authenticate", "Bearer")
                    .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                    .body(e.body());
        }
        return Json.respond(e.status(), e.body());
    }

    // Unknown route or wrong method -> not_found.
    @ExceptionHandler({
        NoHandlerFoundException.class,
        NoResourceFoundException.class,
        HttpRequestMethodNotSupportedException.class
    })
    ResponseEntity<byte[]> notFound(Exception e) {
        return api(ApiException.notFound());
    }

    // Missing/unsupported content type, unreadable body, bad request line -> bad_request.
    @ExceptionHandler({HttpMediaTypeException.class, org.springframework.http.converter.HttpMessageNotReadableException.class})
    ResponseEntity<byte[]> badRequest(Exception e) {
        return api(ApiException.badRequest());
    }

    // FK (23503) / CHECK (23514) violations -> 422.
    @ExceptionHandler(DataIntegrityViolationException.class)
    ResponseEntity<byte[]> integrity(DataIntegrityViolationException e) {
        for (Throwable t = e; t != null; t = t.getCause()) {
            if (t instanceof SQLException sql && ("23503".equals(sql.getSQLState()) || "23514".equals(sql.getSQLState()))) {
                return api(ApiException.invalid());
            }
        }
        return internal(e);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<byte[]> internal(Exception e) {
        return Json.respond(HttpStatus.INTERNAL_SERVER_ERROR, INTERNAL);
    }
}
