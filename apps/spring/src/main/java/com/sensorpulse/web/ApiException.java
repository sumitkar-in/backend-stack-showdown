package com.sensorpulse.web;

import org.springframework.http.HttpStatus;

public class ApiException extends RuntimeException {
    private final HttpStatus status;
    private final byte[] body;

    private ApiException(HttpStatus status, String body) {
        super(body, null, false, false); // no stack trace: cheap to throw
        this.status = status;
        this.body = body.getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }

    public static ApiException badRequest() {
        return new ApiException(HttpStatus.BAD_REQUEST, "{\"error\":\"bad_request\"}");
    }

    public static ApiException invalid() {
        return new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "{\"error\":\"validation_error\"}");
    }

    public static ApiException unauthorized() {
        return new ApiException(HttpStatus.UNAUTHORIZED, "{\"error\":\"unauthorized\"}");
    }

    public static ApiException notFound() {
        return new ApiException(HttpStatus.NOT_FOUND, "{\"error\":\"not_found\"}");
    }

    public HttpStatus status() {
        return status;
    }

    public byte[] body() {
        return body;
    }
}
