package com.sensorpulse.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/** Registers the JWT interceptor only when AUTH_MODE=jwt. /health stays public; unknown routes stay 404. */
@Configuration
@ConditionalOnProperty(name = "app.auth.mode", havingValue = "jwt")
public class AuthConfig implements WebMvcConfigurer {

    private final String secret;

    public AuthConfig(@Value("${app.auth.jwt-secret}") String secret) {
        this.secret = secret;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new JwtInterceptor(secret)).addPathPatterns("/readings", "/readings/**");
    }
}
