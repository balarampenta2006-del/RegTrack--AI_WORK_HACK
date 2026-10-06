package com.regtrack.backend.security;

import com.regtrack.backend.model.Role;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;

@Service
public class JwtService {

    private final SecretKey key;
    private final long expirationSeconds;
    private final String issuer;

    public JwtService(
            @Value("${regtrack.security.jwt.secret}") String secret,
            @Value("${regtrack.security.jwt.expiration-seconds}") long expirationSeconds,
            @Value("${regtrack.security.jwt.issuer}") String issuer) {
        if (secret == null || secret.getBytes(StandardCharsets.UTF_8).length < 32) {
            throw new IllegalStateException("regtrack.security.jwt.secret must be at least 32 bytes");
        }
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.expirationSeconds = expirationSeconds;
        this.issuer = issuer;
    }

    public String generate(UserPrincipal principal) {
        Instant now = Instant.now();
        return Jwts.builder()
                .subject(principal.email())
                .issuer(issuer)
                .claim("uid", principal.id())
                .claim("role", principal.role().name())
                .claim("companyId", principal.companyId())
                .issuedAt(Date.from(now))
                .expiration(Date.from(now.plusSeconds(expirationSeconds)))
                .signWith(key)
                .compact();
    }

    public UserPrincipal parse(String token) {
        Claims claims = Jwts.parser()
                .verifyWith(key)
                .requireIssuer(issuer)
                .clockSkewSeconds(30)
                .build()
                .parseSignedClaims(token)
                .getPayload();

        Long uid = claims.get("uid", Number.class) != null ? claims.get("uid", Number.class).longValue() : null;
        String roleName = claims.get("role", String.class);
        Role role = roleName != null ? Role.valueOf(roleName) : Role.VIEWER;
        Long companyId = claims.get("companyId", Number.class) != null
                ? claims.get("companyId", Number.class).longValue()
                : null;

        return new UserPrincipal(uid, claims.getSubject(), role, companyId);
    }

    public long expirationSeconds() {
        return expirationSeconds;
    }
}
