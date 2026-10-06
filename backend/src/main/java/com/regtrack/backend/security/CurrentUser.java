package com.regtrack.backend.security;

import com.regtrack.backend.exception.UnauthorizedException;
import org.springframework.security.core.Authentication;

public final class CurrentUser {

    private CurrentUser() {
    }

    public static UserPrincipal require(Authentication authentication) {
        if (authentication == null
                || !(authentication.getPrincipal() instanceof UserPrincipal principal)) {
            throw new UnauthorizedException("Authentication required");
        }
        return principal;
    }
}
