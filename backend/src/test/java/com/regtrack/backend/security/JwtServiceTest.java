package com.regtrack.backend.security;

import com.regtrack.backend.model.Role;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class JwtServiceTest {

    private final JwtService jwtService =
            new JwtService("test-secret-0123456789-abcdefghijklmnopqrstuvwxyz-0123456789", 3600, "regtrack-backend");

    @Test
    void generatesAndParsesToken() {
        UserPrincipal principal = new UserPrincipal(42L, "officer@example.com", Role.COMPLIANCE_OFFICER, 7L);

        String token = jwtService.generate(principal);
        UserPrincipal parsed = jwtService.parse(token);

        assertThat(parsed.id()).isEqualTo(42L);
        assertThat(parsed.email()).isEqualTo("officer@example.com");
        assertThat(parsed.role()).isEqualTo(Role.COMPLIANCE_OFFICER);
        assertThat(parsed.companyId()).isEqualTo(7L);
        assertThat(parsed.authority()).isEqualTo("ROLE_COMPLIANCE_OFFICER");
    }

    @Test
    void rejectsTamperedToken() {
        UserPrincipal principal = new UserPrincipal(1L, "a@b.com", Role.ADMIN, null);
        String token = jwtService.generate(principal);
        String tampered = token.substring(0, token.length() - 3) + "abc";

        assertThatThrownBy(() -> jwtService.parse(tampered)).isInstanceOf(Exception.class);
    }

    @Test
    void rejectsTokenFromDifferentIssuer() {
        JwtService other = new JwtService("another-secret-0123456789-abcdefghijklmnop-01234567", 3600, "other-issuer");
        String token = other.generate(new UserPrincipal(1L, "a@b.com", Role.ADMIN, null));

        assertThatThrownBy(() -> jwtService.parse(token)).isInstanceOf(Exception.class);
    }

    @Test
    void rejectsShortSigningSecret() {
        assertThatThrownBy(() -> new JwtService("short", 3600, "x"))
                .isInstanceOf(IllegalStateException.class);
    }
}
