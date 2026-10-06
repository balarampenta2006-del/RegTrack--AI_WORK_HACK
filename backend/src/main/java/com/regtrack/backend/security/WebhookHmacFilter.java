package com.regtrack.backend.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;

/**
 * Authenticates inbound automation webhooks (ChangeDetection.io / n8n) using either
 * an HMAC-SHA256 signature of the raw body (X-Webhook-Signature: sha256=&lt;hex&gt;)
 * or a static shared token (X-Webhook-Token).
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class WebhookHmacFilter extends OncePerRequestFilter {

    public static final String SIGNATURE_HEADER = "X-Webhook-Signature";
    public static final String TOKEN_HEADER = "X-Webhook-Token";

    @Value("${regtrack.security.webhook.secret}")
    private String webhookSecret;

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith("/api/webhooks/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        byte[] body = request.getInputStream().readAllBytes();

        if (!isValid(request, body)) {
            log.warn("Rejected webhook call to {} from {}", request.getRequestURI(), request.getRemoteAddr());
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json");
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write("{\"error\":\"invalid webhook signature or token\"}");
            return;
        }

        UsernamePasswordAuthenticationToken authentication = new UsernamePasswordAuthenticationToken(
                "webhook-system", null, List.of(new SimpleGrantedAuthority("ROLE_WEBHOOK")));
        SecurityContextHolder.getContext().setAuthentication(authentication);

        try {
            filterChain.doFilter(new CachedBodyHttpServletRequest(request, body), response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private boolean isValid(HttpServletRequest request, byte[] body) {
        String token = request.getHeader(TOKEN_HEADER);
        if (token != null && !token.isBlank()) {
            return constantTimeEquals(token.trim().getBytes(StandardCharsets.UTF_8),
                    webhookSecret.getBytes(StandardCharsets.UTF_8));
        }

        String signature = request.getHeader(SIGNATURE_HEADER);
        if (signature == null || signature.isBlank()) {
            return false;
        }
        String provided = signature.trim();
        if (provided.startsWith("sha256=")) {
            provided = provided.substring("sha256=".length());
        }
        String expected = hmacSha256Hex(body, webhookSecret);
        return constantTimeEquals(expected.toLowerCase().getBytes(StandardCharsets.UTF_8),
                provided.toLowerCase().getBytes(StandardCharsets.UTF_8));
    }

    public static String hmacSha256Hex(byte[] payload, String secret) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(payload));
        } catch (Exception ex) {
            throw new IllegalStateException("Unable to compute HMAC signature", ex);
        }
    }

    public static String sha256Hex(String content) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(content.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception ex) {
            throw new IllegalStateException("Unable to compute SHA-256 hash", ex);
        }
    }

    private boolean constantTimeEquals(byte[] a, byte[] b) {
        return MessageDigest.isEqual(a, b);
    }
}
