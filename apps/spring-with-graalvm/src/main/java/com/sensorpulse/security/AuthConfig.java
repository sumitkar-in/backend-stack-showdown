package com.sensorpulse.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Registers the JWT interceptor only when AUTH_MODE=jwt. /health stays public; unknown routes stay 404.
 * The mode is checked at runtime: a @ConditionalOnProperty is resolved when the native image is built (AUTH_MODE
 * is not set then), which would leave the interceptor out of the image for good.
 */
@Configuration
public class AuthConfig implements WebMvcConfigurer {

    private final String secret;
    private final boolean enabled;

    public AuthConfig(@Value("${app.auth.jwt-secret}") String secret, @Value("${app.auth.mode}") String mode) {
        this.secret = secret;
        this.enabled = "jwt".equals(mode);
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        if (!enabled) {
            return;
        }
        registry.addInterceptor(new JwtInterceptor(secret)).addPathPatterns("/readings", "/readings/**");
    }
}
