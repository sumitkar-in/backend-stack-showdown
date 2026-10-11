package com.sensorpulse.security;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sensorpulse.web.ApiException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.regex.Pattern;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * Verifies an HS256 bearer token on every request (no caching of verified tokens).
 * Rules (identical in all stacks): "Bearer " prefix, three non-empty segments, header alg == HS256,
 * valid HMAC-SHA256 signature, integer exp in the future, non-empty sub.
 */
public class JwtInterceptor implements HandlerInterceptor {

    private static final Pattern B64URL = Pattern.compile("^[A-Za-z0-9_-]+$");
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final Base64.Decoder DECODER = Base64.getUrlDecoder();

    private final SecretKeySpec key;
    private final ThreadLocal<Mac> mac;

    public JwtInterceptor(String secret) {
        this.key = new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
        this.mac = ThreadLocal.withInitial(() -> {
            try {
                Mac m = Mac.getInstance("HmacSHA256");
                m.init(key);
                return m;
            } catch (Exception e) {
                throw new IllegalStateException(e);
            }
        });
    }

    @Override
    public boolean preHandle(HttpServletRequest req, HttpServletResponse res, Object handler) {
        if (!verify(req.getHeader("Authorization"))) {
            throw ApiException.unauthorized();
        }
        return true;
    }

    boolean verify(String header) {
        if (header == null || !header.startsWith("Bearer ")) {
            return false;
        }
        String[] parts = header.substring(7).split("\\.", -1);
        if (parts.length != 3 || parts[0].isEmpty() || parts[1].isEmpty() || parts[2].isEmpty()) {
            return false;
        }
        try {
            for (String p : parts) {
                if (!B64URL.matcher(p).matches()) {
                    return false;
                }
            }
            byte[] sig = DECODER.decode(parts[2]);
            Mac m = mac.get();
            m.reset();
            byte[] expected = m.doFinal((parts[0] + "." + parts[1]).getBytes(StandardCharsets.US_ASCII));
            if (!MessageDigest.isEqual(sig, expected)) {
                return false;
            }
            JsonNode hdr = MAPPER.readTree(DECODER.decode(parts[0]));
            if (!hdr.isObject() || !"HS256".equals(hdr.path("alg").asText(null))) {
                return false;
            }
            JsonNode claims = MAPPER.readTree(DECODER.decode(parts[1]));
            JsonNode sub = claims.get("sub");
            JsonNode exp = claims.get("exp");
            return sub != null && sub.isTextual() && !sub.textValue().isEmpty()
                    && exp != null && exp.isIntegralNumber() && exp.canConvertToLong()
                    && exp.longValue() > System.currentTimeMillis() / 1000;
        } catch (Exception e) {
            return false;
        }
    }
}
