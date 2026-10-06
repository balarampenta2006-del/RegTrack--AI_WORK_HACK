package com.regtrack.backend.security;

import com.regtrack.backend.model.Role;

public record UserPrincipal(Long id, String email, Role role, Long companyId) {

    public String authority() {
        return "ROLE_" + role.name();
    }
}
